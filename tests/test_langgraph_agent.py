"""真实LangGraph运行时测试，外部模型与核心系统通过假服务隔离。"""
import asyncio
from langgraph.types import Command
from agents.claim_agent import build_claim_graph, build_plan_execute, WorkflowServices


class Services(WorkflowServices):
    def __init__(self, risk=.1, verified=True):
        self.risk, self.verified = risk, verified
        self.active = self.peak = 0

    async def policy(self, claim):
        return {'status': '有效', 'source': 'test_fixture'}

    async def verify(self, claim, policy):
        return {'coverage_verified': self.verified}

    async def expert(self, role, claim, policy, config):
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(.01)
        self.active -= 1
        return {'expert': role, 'recommendation': 'accept', 'confidence': .95,
                'risk_score': self.risk if role == 'risk' else None}


def execute(graph, payload, thread='case'):
    return asyncio.run(graph.ainvoke(payload, config={'configurable': {'thread_id': thread}, 'recursion_limit': 30, 'max_concurrency': 3}))


def initial(policy=True, amount=100):
    return {'claim_id': 'CLM-2026-001', 'claim_data': {'description': '测试', 'amount': amount, **({'policy_id': 'P1'} if policy else {})}, 'expert_results': [], 'rounds': 0}


def test_parallel_experts_and_accept():
    service = Services()
    graph = build_claim_graph(service)
    result = execute(graph, initial())
    assert service.peak == 3
    assert len(result['expert_results']) == 3
    assert result['decision'] == 'accept'


def test_high_risk_investigate_without_reject():
    result = execute(build_claim_graph(Services(risk=.8)), initial())
    assert result['decision'] == 'investigate'


def test_missing_evidence_and_high_amount_interrupt_then_resume():
    for service, amount in ((Services(verified=False), 100), (Services(), 50001)):
        graph = build_claim_graph(service)
        execute(graph, initial(amount=amount))
        config = {'configurable': {'thread_id': 'case'}}
        assert graph.get_state(config).next == ('review',)
        result = execute(graph, Command(resume={'decision': 'review', 'reviewer': 'test-reviewer', 'reason': '补材料'}))
        assert result['phase'] == 'complete' and result['decision'] == 'review'


def test_three_material_rounds_are_bounded():
    graph = build_claim_graph(Services())
    execute(graph, initial(policy=False))
    for _ in range(3):
        execute(graph, Command(resume={'policy_id': ''}))
    snapshot = graph.get_state({'configurable': {'thread_id': 'case'}})
    assert snapshot.values['rounds'] == 3
    assert snapshot.next == ('review',)


def test_policy_supplement_resumes_without_losing_claim():
    graph = build_claim_graph(Services())
    execute(graph, initial(policy=False))
    result = execute(graph, Command(resume={'policy_id': 'P1', 'confidence': 1}))
    assert result['decision'] == 'accept'
    assert result['confidence'] == .95


def test_plan_execution_is_bounded_and_ordered():
    graph = build_plan_execute(lambda _: ['查询', '核实'], lambda step: step + '完成')
    result = graph.invoke({'input': '审核'})
    assert result['results'] == ['查询完成', '核实完成']
