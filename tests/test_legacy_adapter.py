"""使用可控时钟和假传输验证存量接口治理，不连接真实核心系统。"""
import pytest
import requests
from adapters.legacy_adapter import CircuitBreaker, CoreSystemAdapter, CoreSystemUnavailable


def test_half_open_has_only_one_probe():
    now = [0.0]
    breaker = CircuitBreaker(1, 30, clock=lambda: now[0])
    assert breaker.allow()
    breaker.on_failure()
    assert not breaker.allow()
    now[0] = 30
    assert breaker.allow() and breaker.state == 'HALF_OPEN'
    assert not breaker.allow()
    breaker.on_failure()
    assert breaker.state == 'OPEN'
    now[0] = 60
    assert breaker.allow()
    breaker.on_success()
    assert breaker.state == 'CLOSED' and breaker.failures == 0


def test_cache_is_explicit_degraded_and_expires():
    now, failing, calls = [0.0], [False], []
    def transport(pid):
        calls.append(pid)
        if failing[0]:
            raise requests.Timeout()
        return {'sts': '1', 'amt': '50000', 'holder': '张三', 'need_ocr': False}
    adapter = CoreSystemAdapter(transport, clock=lambda: now[0], sleep=lambda _: None)
    assert not adapter.query_policy('P1').degraded
    failing[0] = True
    result = adapter.query_policy('P1')
    assert result.degraded and result.holder == '张**'
    assert len(calls) == 4
    now[0] = 301
    with pytest.raises(CoreSystemUnavailable):
        adapter.query_policy('P1')


@pytest.mark.parametrize('change', [{'sts': 'unknown'}, {'amt': -1}, {'need_ocr': 'false'}, {'pid': 'OTHER'}])
def test_invalid_response_never_becomes_valid_policy(change):
    raw = {'sts': '1', 'amt': '100', 'holder': '张三', 'need_ocr': False} | change
    adapter = CoreSystemAdapter(lambda _: raw)
    with pytest.raises(CoreSystemUnavailable, match='invalid_response'):
        adapter.query_policy('P1')
    assert adapter.breaker.failures == 1
