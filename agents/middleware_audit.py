"""模块07：脱敏、审计、限流、缓存、重试、降级及Token回调。"""
import asyncio
from collections.abc import Awaitable, Callable, Mapping
from decimal import Decimal
import hashlib
import json
import logging
import re
import threading
import time
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from adapters.legacy_adapter import CircuitBreaker

LOGGER = logging.getLogger('claims.audit')


def mask_pii(value: Any) -> Any:
    """递归脱敏常见标识；地址只处理显式标签，不宣称覆盖所有自由文本PII。"""
    if isinstance(value, Mapping):
        return {str(k): '[REDACTED]' if re.search(r'api.?key|password|secret|authorization|身份证|银行卡|手机号|地址', str(k), re.I)
                else mask_pii(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [mask_pii(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r'(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]+', '[密钥]', value)
        value = re.sub(r'(?<!\d)\d{17}[\dXx](?!\d)', '[身份证]', value)
        value = re.sub(r'(?<!\d)1[3-9]\d{9}(?!\d)', '[手机号]', value)
        value = re.sub(r'(?<!\d)\d{16,19}(?!\d)', '[银行卡]', value)
        return re.sub(r'(?:住址|家庭地址|详细地址)\s*[:：]\s*[^\n，。；;]+', '地址：[已脱敏]', value)
    return value


def input_guardrail(text: str) -> str:
    """限制输入规模并脱敏，用户材料不能改变应用权限。"""
    if not text.strip() or len(text) > 10000:
        raise ValueError('输入长度必须为1至10000字符')
    return mask_pii(text)


def output_guardrail(text: str) -> str:
    """拦截不当承诺并脱敏输出，规则可按已批准合规清单扩展。"""
    if any(word in text for word in ('保证赔付', '一定赔付', '绕过审核', '内部系统密码')):
        raise ValueError('输出触发合规复核')
    return mask_pii(text)


class AuditLogMiddleware:
    """以JSON记录脱敏输入输出和耗时，不记录异常正文中的潜在凭证。"""
    def record(self, claim_id: str, input_data: Any, output: Any, elapsed: float,
               *, error: str | None = None) -> None:
        LOGGER.info(json.dumps(mask_pii(dict(claim_id=claim_id, input=input_data,
            output=output, latency_s=elapsed, error=error)), ensure_ascii=False, default=str))


class ComplianceMiddleware:
    """提供统一的递归脱敏入口。"""
    def __call__(self, data: Any) -> Any:
        return mask_pii(data)


class RateLimitMiddleware:
    """每案件令牌桶，使用单调时钟；闲置桶定期清理。"""
    def __init__(self, capacity: int = 10, refill_per_second: float = 1,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if capacity < 1 or refill_per_second <= 0:
            raise ValueError('令牌桶参数必须为正')
        self.capacity, self.rate, self.clock = capacity, refill_per_second, clock
        self.buckets: dict[str, tuple[float, float]] = {}
        self.lock = threading.Lock()

    def check(self, claim_id: str) -> None:
        with self.lock:
            now = self.clock()
            self.buckets = {k: v for k, v in self.buckets.items() if now - v[1] < 3600}
            tokens, previous = self.buckets.get(claim_id, (float(self.capacity), now))
            tokens = min(self.capacity, tokens + (now - previous) * self.rate)
            if tokens < 1:
                self.buckets[claim_id] = (tokens, now)
                raise RuntimeError('rate_limit_exceeded')
            self.buckets[claim_id] = (tokens - 1, now)


class TTLCache:
    """按案件、提示词、模型参数、版本生成键，避免跨案污染。"""
    def __init__(self, ttl: float = 3600, clock: Callable[[], float] = time.monotonic) -> None:
        self.ttl, self.clock = ttl, clock
        self.items: dict[str, tuple[float, Any]] = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(data: Any) -> str:
        return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str,
                                         allow_nan=False).encode()).hexdigest()

    def get(self, key: str) -> Any:
        now = self.clock()
        self.items = {k: v for k, v in self.items.items() if v[0] > now}
        item = self.items.get(key)
        if item is not None:
            self.hits += 1
            return json.loads(json.dumps(item[1]))
        self.misses += 1
        return None

    def put(self, key: str, value: Any) -> None:
        self.items[key] = (self.clock() + self.ttl, json.loads(json.dumps(value)))


class TokenUsageCounter(BaseCallbackHandler):
    """线程安全累计真实usage；缺失usage标记未知，不假设零成本。"""
    def __init__(self, rates: dict[str, tuple[Decimal, Decimal]] | None = None) -> None:
        self.rates = rates or {}  # 每百万输入/输出token单价，由项目提供。
        self.prompt_tokens = self.completion_tokens = self.unknown_calls = 0
        self.known_cost = Decimal('0')
        self.unpriced_calls = 0
        self.lock = threading.Lock()

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        output = response.llm_output or {}
        usage = output.get('token_usage')
        model = output.get('model_name', '')
        if usage is None and response.generations:
            message = getattr(response.generations[0][0], 'message', None)
            native = getattr(message, 'usage_metadata', None)
            if native:
                usage = {'prompt_tokens': native['input_tokens'], 'completion_tokens': native['output_tokens']}
                model = getattr(message, 'response_metadata', {}).get('model_name', model)
        with self.lock:
            if not usage:
                self.unknown_calls += 1
                return
            prompt, completion = int(usage.get('prompt_tokens', 0)), int(usage.get('completion_tokens', 0))
            self.prompt_tokens += prompt
            self.completion_tokens += completion
            if model in self.rates:
                a, b = self.rates[model]
                self.known_cost += (prompt * a + completion * b) / Decimal(1000000)
            else:
                self.unpriced_calls += 1

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return dict(prompt_tokens=self.prompt_tokens, completion_tokens=self.completion_tokens,
                        total_tokens=self.prompt_tokens + self.completion_tokens,
                        known_cost=str(self.known_cost), unknown_usage_calls=self.unknown_calls,
                        unpriced_calls=self.unpriced_calls)


class HumanInTheLoopMiddleware:
    """缺证据、低置信或大额必须复核，绝不在此直接执行支付。"""
    def __call__(self, result: dict[str, Any]) -> dict[str, Any]:
        output = dict(result)
        if (float(output.get('amount', 0)) > 50000 or float(output.get('confidence', 0)) <= .9
                or not output.get('evidence_complete', False)):
            output['requires_manual_review'] = True
        return output


class MiddlewareChain:
    """固定安全边界下可切换限流/缓存，顺序为限流→合规→缓存→推理→审计→HITL。"""
    def __init__(self, *, cache_enabled: bool = True, rate_limit_enabled: bool = True) -> None:
        self.limiter, self.cache = RateLimitMiddleware(), TTLCache()
        self.audit, self.hitl = AuditLogMiddleware(), HumanInTheLoopMiddleware()
        self.breaker = CircuitBreaker()
        self.cache_enabled, self.rate_limit_enabled = cache_enabled, rate_limit_enabled

    async def ainvoke(self, claim_id: str, data: dict[str, Any],
                      call: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]], *,
                      model_parameters: dict[str, Any],
                      fallback: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] | None = None) -> dict[str, Any]:
        start = time.monotonic()
        safe = mask_pii(data)
        try:
            if self.rate_limit_enabled:
                self.limiter.check(claim_id)
            key = self.cache.key({'claim_id': claim_id, 'input': safe, 'model': model_parameters})
            result = self.cache.get(key) if self.cache_enabled else None
            if result is None:
                if not self.breaker.allow():
                    raise RuntimeError('circuit_open')
                for attempt in range(3):
                    try:
                        result = await call(safe)
                        self.breaker.on_success()
                        break
                    except Exception:
                        if attempt == 2:
                            self.breaker.on_failure()
                            if fallback is None:
                                raise
                            LOGGER.warning('主模型不可用，调用已配置备用链路')
                            result = await fallback(safe)
                            result['degraded'] = True
                        else:
                            await asyncio.sleep(.1 * 2 ** attempt)
                if self.cache_enabled and result is not None and not result.get('degraded'):
                    self.cache.put(key, mask_pii(result))
            if result is None:
                raise RuntimeError('模型链路没有返回结果')
            output_guardrail(json.dumps(result, ensure_ascii=False))
            result = self.hitl(mask_pii(result))
            self.audit.record(claim_id, safe, result, time.monotonic() - start)
            return result
        except Exception as exc:
            self.audit.record(claim_id, safe, None, time.monotonic() - start, error=type(exc).__name__)
            raise


def configure_logging(path: str | None = None) -> None:
    """日志只收集应用审计，外部SDK保持WARNING以免泄露请求内容。"""
    handler = logging.FileHandler(path, encoding='utf-8') if path else logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    LOGGER.handlers = [handler]
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False
