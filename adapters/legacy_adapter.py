"""材料6.5.2：保单协议适配、三态熔断、只读缓存及显式降级。

只实现材料给出的HTTP报文。SOAP/RPC通过注入传输函数扩展，
没有协议定义时不虚构请求。构造和导入均不触发网络请求。
"""
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import os
import threading
import time
from typing import Any, Literal

import requests
from pydantic import Field, StrictBool

from models.schemas import Contract, Money


class CoreSystemUnavailable(RuntimeError):
    """无法获得可用的已核实保单数据，调用方应显式转人工。"""


class PolicyQueryResult(Contract):
    """适配后的保单快照；缓存降级不等于实时查询成功。"""
    policy_id: str = Field(min_length=1, max_length=64)
    status: Literal['有效', '无效', '已脱保']
    coverage: Money
    holder: str = Field(min_length=1)
    ocr_flag: StrictBool
    data_fresh_at: datetime
    source: str = Field(min_length=1)
    degraded: bool = False
    degraded_reason: str | None = None


class CircuitBreaker:
    """线程安全三态熔断；半开状态只允许一个试探请求。"""
    def __init__(self, failure_threshold: int = 5, open_timeout_s: float = 30,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if failure_threshold < 1 or open_timeout_s <= 0:
            raise ValueError('熔断阈值及恢复等待时间必须为正')
        self.failure_threshold = failure_threshold
        self.open_timeout_s = open_timeout_s
        self.failures = 0
        self.state = 'CLOSED'
        self.opened_at = 0.0
        self._clock = clock
        self._lock = threading.Lock()

    def allow(self) -> bool:
        """获取一次调用资格，半开期间其余请求立即降级。"""
        with self._lock:
            if self.state == 'HALF_OPEN':
                return False
            if self.state == 'OPEN':
                if self._clock() - self.opened_at < self.open_timeout_s:
                    return False
                self.state = 'HALF_OPEN'
            return True

    def on_success(self) -> None:
        """只有传输和结果契约都成功才恢复闭合。"""
        with self._lock:
            # 已进入OPEN时，较早发出的慢成功请求不应绕过冷却期。
            if self.state != 'OPEN':
                self.failures = 0
                self.state = 'CLOSED'

    def on_failure(self) -> None:
        """半开试探失败立即重新断开。"""
        with self._lock:
            self.failures += 1
            if self.state == 'HALF_OPEN' or self.failures >= self.failure_threshold:
                self.state = 'OPEN'
                self.opened_at = self._clock()


class HTTPPolicyTransport:
    """材料指定的HTTP POST + Basic Auth；密钥仅从环境读取。"""
    def __init__(self, url: str, account: str, password: str) -> None:
        if not url.startswith(('http://', 'https://')) or not account or not password:
            raise ValueError('需要有效的CORE_QUERY_URL/ACCOUNT/PASSWORD')
        self.url, self.auth = url, (account, password)

    def __call__(self, policy_id: str) -> Mapping[str, Any]:
        response = requests.post(
            self.url, json={'op': 'POLICY_QUERY', 'pid': policy_id, 'chn': 'AI_CLAIM'},
            auth=self.auth, timeout=(3, 15),
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError('核心系统返回值必须是JSON对象')
        return data


class CoreSystemAdapter:
    """调用方可注入已核实协议的传输函数；查询结果经过契约后才入缓存。"""
    def __init__(self, transport: Callable[[str], Mapping[str, Any]], *,
                 source: str = 'core_system', breaker: CircuitBreaker | None = None,
                 results_ttl: float = 300, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if results_ttl <= 0 or not source:
            raise ValueError('缓存TTL和来源标识必须有效')
        self.routes = {'query_policy': transport}
        self.source = source
        self.breaker = breaker or CircuitBreaker(clock=clock)
        self.results_ttl = results_ttl
        self._clock, self._sleep = clock, sleep
        self._cache: dict[str, tuple[float, PolicyQueryResult]] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> 'CoreSystemAdapter':
        """显式创建，缺少配置时清晰报错；不打印凭证。"""
        names = ('CORE_QUERY_URL', 'CORE_QUERY_ACCOUNT', 'CORE_QUERY_PASSWORD')
        missing = [name for name in names if not os.getenv(name)]
        if missing:
            raise ValueError('缺少配置：' + ', '.join(missing))
        return cls(HTTPPolicyTransport(*(os.environ[name] for name in names)))

    def query_policy(self, policy_id: str) -> PolicyQueryResult:
        """优先实时查询；最多三次请求，失败只使用TTL内缓存或抛错。"""
        if not policy_id.strip() or len(policy_id) > 64:
            raise ValueError('保单号长度必须为1至64')
        if not self.breaker.allow():
            return self._degrade(policy_id, 'circuit_open')
        reason = 'unavailable'
        for attempt in range(3):
            try:
                raw = self.routes['query_policy'](policy_id)
                result = self._map(policy_id, raw)
            except (requests.Timeout, requests.ConnectionError):
                if attempt < 2:
                    self._sleep(0.5 * 2 ** attempt)
                    continue
            except requests.HTTPError as exc:
                code = exc.response.status_code if exc.response is not None else None
                if code is not None and (code >= 500 or code == 429) and attempt < 2:
                    self._sleep(0.5 * 2 ** attempt)
                    continue
                reason = 'http_error'
            except (ValueError, KeyError, TypeError):
                reason = 'invalid_response'
            else:
                self.breaker.on_success()
                with self._lock:
                    self._cache[policy_id] = (self._clock(), result)
                return result.model_copy(deep=True)
            break
        self.breaker.on_failure()
        return self._degrade(policy_id, reason)

    def _degrade(self, policy_id: str, reason: str) -> PolicyQueryResult:
        with self._lock:
            cached = self._cache.get(policy_id)
            if cached and self._clock() - cached[0] < self.results_ttl:
                return cached[1].model_copy(update={'degraded': True, 'degraded_reason': reason}, deep=True)
            self._cache.pop(policy_id, None)
        raise CoreSystemUnavailable(f'core_system_unavailable:{reason}')

    def _map(self, policy_id: str, raw: Mapping[str, Any]) -> PolicyQueryResult:
        statuses = {'1': '有效', '0': '无效', '2': '已脱保'}
        status = statuses[str(raw['sts'])]  # 未知值拒绝映射，不默认为“无效”。
        if raw.get('pid', policy_id) != policy_id:
            raise ValueError('核心系统返回了其他保单')
        holder = raw['holder']
        if not isinstance(holder, str) or not holder.strip():
            raise ValueError('缺少投保人信息')
        return PolicyQueryResult(
            policy_id=policy_id, status=status, coverage=raw['amt'], holder=holder.strip()[0] + '**',
            ocr_flag=raw['need_ocr'], data_fresh_at=datetime.now(timezone.utc),
            source=self.source,
        )
