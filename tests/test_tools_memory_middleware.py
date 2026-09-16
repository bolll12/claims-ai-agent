"""工具权限、幂等、记忆隔离及中间件的离线行为测试。"""
import asyncio

import fakeredis
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import ToolException

from adapters.business import DemoBackend, BusinessBackend
from agents.memory import ClaimContextManager
from agents.middleware_audit import MiddlewareChain, RateLimitMiddleware, mask_pii, TTLCache
from tools.claim_tool import build_claim_tools, tool_round
from tools.claim_write_producer import Outbox


def test_all_eight_tools_and_demo_labels():
    tools = build_claim_tools(DemoBackend())
    assert len(tools.select()) == 8
    policy = tools.tools['query_policy'][1].invoke({'policy_id': 'POL-2024-001'})
    assert policy['demo'] and policy['source']
    with pytest.raises(ToolException):
        tools.tools['query_policy'][1].invoke({'policy_id': 'UNKNOWN'})
    with pytest.raises(RuntimeError, match='not_configured'):
        BusinessBackend().call('verify_insurance_coverage')


def test_write_requires_trusted_exact_approval_and_is_idempotent(tmp_path):
    outbox = Outbox(tmp_path/'outbox.sqlite')
    data = {'claim_id': 'C1', 'amount': '100', 'payee_id': 'P1', 'idempotency_key': 'K1'}
    denied = build_claim_tools(DemoBackend(), outbox=outbox)
    with pytest.raises(ToolException):
        denied.tools['create_settlement_order'][1].invoke(data)
    allowed = build_claim_tools(DemoBackend(), outbox=outbox, authorize=lambda action, payload: payload == data)
    # Decimal转JSON保持输入表示，按服务端核准具体金额进行比较。
    result = allowed.tools['create_settlement_order'][1].invoke(data)
    assert result['status'] == 'queued' and result['paid'] is False
    assert allowed.tools['create_settlement_order'][1].invoke(data) == result
    with pytest.raises(ValueError):
        outbox.publish('C1', 'create_settlement_order', {'amount': '200'}, 'K1')
    calls = []
    assert outbox.consume_one(lambda action, payload, key: calls.append(key))
    assert not outbox.consume_one(lambda *args: calls.append('duplicate'))
    assert calls == ['K1']
    assert outbox.reconcile({'K1'}) == {'missing_remote': [], 'missing_local': []}


def test_tool_messages_keep_original_history():
    tools = build_claim_tools(DemoBackend()).select('query')
    original = [HumanMessage(content='请查询演示保单')]
    class Model:
        def bind_tools(self, tools, **kwargs):
            assert kwargs == {'tool_choice': 'required', 'parallel_tool_calls': True}
            return self
        async def ainvoke(self, messages):
            if len(messages) == 1:
                return AIMessage(content='', tool_calls=[{'id': '1', 'name': 'query_policy', 'args': {'policy_id': 'POL-2024-001'}}])
            assert messages[0] == original[0] and messages[-1].tool_call_id == '1'
            return AIMessage(content='这是演示信息，需要真实核实。')
    history = asyncio.run(tool_round(Model(), original, tools, choice='required'))
    assert len(history) == 4 and len(original) == 1


def test_memory_redis_entity_conflicts_and_isolation():
    redis = fakeredis.FakeRedis()
    memory = ClaimContextManager('系统角色', redis_client=redis, token_counter=len, max_tokens=1000)
    memory.add_message('a', 'human', '报案信息', important=True)
    memory.remember_entity('a', 'policy', 'P1', .8, '用户')
    memory.remember_entity('a', 'policy', 'P2', .9, '材料')
    assert memory.sessions['a'].entities['policy']['value'] == 'P1'
    assert len(memory.sessions['a'].conflicts) == 1
    assert all('报案信息' not in str(message.content) for message in memory.get_context('b'))
    memory.save_session('a')
    restored = ClaimContextManager('系统角色', redis_client=redis, token_counter=len, max_tokens=1000)
    assert restored.load_session('a')
    assert any(message.content == '报案信息' for message in restored.get_context('a'))
    restored.clear('a')
    assert not restored.load_session('a')


def test_memory_summary_and_important_over_budget():
    manager = ClaimContextManager('系统', recent_turns=2, max_tokens=100, token_counter=len,
                                  summarizer=lambda old, messages: '已记录的旧对话摘要')
    for i in range(10):
        manager.add_message('a', 'human', '信息')
        manager.add_message('a', 'ai', '已记录')
    assert manager.sessions['a'].summary
    manager.add_message('a', 'human', '关键'*100, important=True)
    with pytest.raises(ValueError, match='超过预算'):
        manager.get_context('a')


def test_masking_rate_and_cache_do_not_cross_cases():
    safe = mask_pii({
        'text': '电话13812345678，身份证110101199001011234，密钥sk-example123',
        'api_key': 'secret',
    })
    assert '13812345678' not in safe['text'] and safe['api_key'] == '[REDACTED]'
    assert 'sk-example123' not in safe['text']
    limiter = RateLimitMiddleware(capacity=1, clock=lambda: 0)
    limiter.check('a')
    with pytest.raises(RuntimeError):
        limiter.check('a')
    limiter.check('b')
    assert TTLCache.key({'a': 1, 'b': 2}) == TTLCache.key({'b': 2, 'a': 1})
    chain = MiddlewareChain()
    calls = []
    async def call(data):
        calls.append(data)
        return {'confidence': .5, 'amount': 10}
    async def run():
        for case in ('a', 'a', 'b'):
            result = await chain.ainvoke(case, {'text': '13812345678'}, call, model_parameters={'model': 'test'})
            assert result['requires_manual_review']
    asyncio.run(run())
    assert len(calls) == 2 and chain.cache.hits == 1
