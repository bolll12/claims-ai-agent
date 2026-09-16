"""模块06及LangGraph专题：有界补材料、并行三专家、条件路由与HITL。"""
import asyncio
from collections.abc import Callable
from decimal import Decimal
import operator
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from adapters.business import BusinessBackend
from agents.middleware_audit import MiddlewareChain
from agents.risk_agent import run_expert
from config import ClaimLLMFactory


class ClaimState(TypedDict, total=False):
    claim_id: str
    claim_data: dict[str, Any]
    policy_info: dict[str, Any]
    verified: dict[str, Any]
    messages: list[Any]
    rounds: int
    expert_results: Annotated[list[dict[str, Any]], operator.add]
    risk_score: float | None
    confidence: float
    decision: str
    message: str
    phase: str
    error: str
    human_decision: dict[str, Any]


class WorkflowServices:
    """默认真实后端，未配置查询或证据适配器则显式降级。"""
    def __init__(self, backend: BusinessBackend | None = None) -> None:
        self.backend = backend or BusinessBackend()
        self.middleware = MiddlewareChain()

    async def policy(self, claim: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self.backend.call, 'query_policy', policy_id=claim['policy_id'])

    async def verify(self, claim: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
        if self.backend.demo:
            return {'demo': True, 'coverage_verified': False, 'exclusion_verified': False,
                    'reason': '教学保单不足以证明当前案件责任，需要人工核实'}
        return await asyncio.to_thread(self.backend.call, 'verify_claim_evidence', claim=claim, policy=policy)

    async def expert(self, role: str, claim: dict[str, Any], policy: dict[str, Any],
                     config: dict[str, Any]) -> dict[str, Any]:
        tier = 'pro' if role == 'liability' else 'main'
        async def primary(data: dict[str, Any]) -> dict[str, Any]:
            return await run_expert(ClaimLLMFactory.create(tier, max_retries=0), role, data['claim'], data['policy'], config)
        async def fallback(data: dict[str, Any]) -> dict[str, Any]:
            return await run_expert(ClaimLLMFactory.create('fast', max_retries=0), role, data['claim'], data['policy'], config)
        return await self.middleware.ainvoke(str(claim.get('claim_id', config.get('configurable', {}).get('thread_id', 'unknown'))),
            {'claim': claim, 'policy': policy}, primary,
            model_parameters={'role': role, 'tier': tier, 'prompt_version': '1.0.0'}, fallback=fallback)


def route_decision(state: ClaimState) -> str:
    """业务规则优先于模型分数：证据不足或大额转人工，高风险调查。"""
    if state.get('error') or state.get('policy_info', {}).get('degraded'):
        return 'review'
    risk = state.get('risk_score')
    if risk is None:
        return 'review'
    if risk > .7:
        return 'investigate'
    verified = state.get('verified', {})
    if Decimal(str(state.get('claim_data', {}).get('amount') or 0)) > 50000:
        return 'review'
    if not verified.get('coverage_verified'):
        return 'review'
    if verified.get('exclusion_verified') and verified.get('clause_ids'):
        return 'review'  # 拒赔建议必须再由授权人工确认具体条款。
    opinions = state.get('expert_results', [])
    if (risk > .4 or state.get('confidence', 0) <= .9 or len(opinions) != 3
            or any(item.get('recommendation') != 'accept' or item.get('missing_information') or item.get('degraded') for item in opinions)):
        return 'review'
    return 'auto'


def build_expert_graph(services: WorkflowServices) -> Any:
    """Send扇出及operator.add汇总，直接作为主图子图复用。"""
    graph = StateGraph(ClaimState)
    def dispatch(state: ClaimState) -> list[Send]:
        return [Send('expert', {'role': role, 'claim_data': state['claim_data'], 'policy_info': state['policy_info']})
                for role in ('damage', 'risk', 'liability')]
    async def expert(state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await services.expert(state['role'], state['claim_data'], state['policy_info'], config)
        except Exception as exc:
            result = {'expert': state['role'], 'recommendation': 'review', 'confidence': 0,
                      'risk_score': None, 'missing_information': ['专家调用未成功'], 'error': type(exc).__name__}
        return {'expert_results': [result]}
    def aggregate(state: ClaimState) -> dict[str, Any]:
        opinions = state['expert_results']
        risk = next((item.get('risk_score') for item in opinions if item['expert'] == 'risk'), None)
        return {'confidence': min(float(item['confidence']) for item in opinions), 'risk_score': risk}
    graph.add_node('expert', expert)
    graph.add_node('aggregate', aggregate)
    graph.add_conditional_edges(START, dispatch, ['expert'])
    graph.add_edge('expert', 'aggregate')
    graph.add_edge('aggregate', END)
    return graph.compile()


def build_claim_graph(services: WorkflowServices | None = None, checkpointer: Any = None) -> Any:
    """构建可恢复的审核状态机，所有写业务仍交由外部授权Outbox。"""
    services = services or WorkflowServices()
    graph = StateGraph(ClaimState)

    def intake(state: ClaimState) -> dict[str, Any]:
        claim = dict(state['claim_data'])
        rounds = state.get('rounds', 0)
        if not claim.get('policy_id'):
            if rounds >= 3:
                return {'phase': 'exhausted', 'decision': 'review', 'message': '补充材料已达3轮，转人工复核', 'rounds': rounds}
            update = interrupt({'kind': 'information', 'claim_id': state['claim_id'], 'missing': ['policy_id'], 'round': rounds + 1})
            # 只接收这一阶段允许补充的字段，不能通过resume注入confidence或verified。
            if isinstance(update, dict):
                policy_id = update.get('policy_id')
                if isinstance(policy_id, str) and 0 < len(policy_id.strip()) <= 64:
                    claim['policy_id'] = policy_id.strip()
            rounds += 1
            return {'claim_data': claim, 'rounds': rounds, 'phase': 'ready' if claim.get('policy_id') else 'collecting'}
        return {'phase': 'ready'}

    async def policy(state: ClaimState) -> dict[str, Any]:
        try:
            info = await services.policy(state['claim_data'])
            evidence = await services.verify(state['claim_data'], info)
            return {'policy_info': info, 'verified': evidence}
        except Exception as exc:
            return {'error': type(exc).__name__, 'policy_info': {}, 'verified': {}, 'phase': 'review'}

    def auto(state: ClaimState) -> dict[str, Any]:
        return {'decision': 'accept', 'phase': 'complete', 'message': '满足已核实条件，形成受理建议；未执行付款。'}

    def investigate(state: ClaimState) -> dict[str, Any]:
        return {'decision': 'investigate', 'phase': 'complete', 'message': '风险较高，建议调查核实；不能仅凭风险评分拒赔。'}

    def review(state: ClaimState) -> dict[str, Any]:
        answer = interrupt({'kind': 'review', 'claim_id': state['claim_id'], 'reason': state.get('error', '需要人工核实证据或大额审批'),
                            'allowed': ['review', 'accept', 'reject']})
        if not isinstance(answer, dict) or answer.get('decision') not in ('review', 'accept', 'reject'):
            raise ValueError('人工审核决定不合法')
        # 服务端必须先认证审核员；程序也检查拒赔条款与人工核实说明。
        if not answer.get('reviewer') or not answer.get('reason'):
            raise ValueError('人工审核必须记录审核员和理由')
        if answer['decision'] == 'reject' and not answer.get('clause_basis'):
            raise ValueError('拒赔必须提供已核实的条款依据')
        return {'decision': answer['decision'], 'human_decision': answer, 'phase': 'complete', 'message': '已记录人工审核意见；未执行付款或通知。'}

    graph.add_node('intake', intake)
    graph.add_node('policy', policy)
    graph.add_node('experts', build_expert_graph(services))
    graph.add_node('auto', auto)
    graph.add_node('investigate', investigate)
    graph.add_node('review', review)
    graph.add_edge(START, 'intake')
    graph.add_conditional_edges('intake', lambda s: 'review' if s['phase'] == 'exhausted' else 'policy' if s['phase'] == 'ready' else 'intake')
    graph.add_conditional_edges('policy', lambda s: 'review' if s.get('error') else 'experts')
    graph.add_conditional_edges('experts', route_decision, {'review': 'review', 'auto': 'auto', 'investigate': 'investigate'})
    for node in ('auto', 'investigate', 'review'):
        graph.add_edge(node, END)
    return graph.compile(checkpointer=checkpointer or MemorySaver())


def create_basic_agent(model: Any, tools: list[Any]) -> AgentExecutor:
    """模块06：单轮/多步AgentExecutor；历史由调用方传入。"""
    prompt = ChatPromptTemplate.from_messages([
        ('system', '你是理赔助手。依次收集报案、核实保单、分析损失、评估风险、给出审核建议。'
         '没有证据时转人工；工具失败不等于事实成立。不得承诺已付款。'),
        MessagesPlaceholder('chat_history', optional=True), ('human', '{input}'), MessagesPlaceholder('agent_scratchpad'),
    ])
    return AgentExecutor(agent=create_tool_calling_agent(model, tools, prompt), tools=tools,
                         max_iterations=8, return_intermediate_steps=True, verbose=False)


def build_plan_execute(planner: Callable[[str], list[str]], executor: Callable[[str], str], max_steps: int = 8) -> Any:
    """有界Plan-and-Execute，规划和执行函数可分别绑定pro/main模型。"""
    class PlanState(TypedDict, total=False):
        input: str
        plan: list[str]
        results: Annotated[list[str], operator.add]
        step: int
    graph = StateGraph(PlanState)
    def plan(state: PlanState) -> dict[str, Any]:
        steps = planner(state['input'])
        if not steps or len(steps) > max_steps or any(not isinstance(step, str) or not step.strip() for step in steps):
            raise ValueError('规划为空或超过执行上限')
        return {'plan': steps, 'step': 0}
    def execute(state: PlanState) -> dict[str, Any]:
        return {'results': [executor(state['plan'][state['step']])], 'step': state['step'] + 1}
    graph.add_node('planner', plan)
    graph.add_node('execute', execute)
    graph.add_edge(START, 'planner')
    graph.add_edge('planner', 'execute')
    graph.add_conditional_edges('execute', lambda s: END if s['step'] >= len(s['plan']) else 'execute')
    return graph.compile()


def create_conversational_agent(model: Any, tools: list[Any], history_factory: Callable[[str], Any] | None = None) -> Any:
    """RunnableWithMessageHistory按session_id隔离，多实例可注入Redis历史工厂。"""
    from langchain_core.chat_history import InMemoryChatMessageHistory
    from langchain_core.runnables.history import RunnableWithMessageHistory
    histories: dict[str, Any] = {}
    def default_history(session_id: str) -> Any:
        return histories.setdefault(session_id, InMemoryChatMessageHistory())
    return RunnableWithMessageHistory(create_basic_agent(model, tools), history_factory or default_history,
                                      input_messages_key='input', history_messages_key='chat_history', output_messages_key='output')


def create_model_plan_execute() -> Any:
    """pro模型规划、main模型执行，只分析不把模型计划直接当成系统命令。"""
    import json
    def planner(question: str) -> list[str]:
        reply = ClaimLLMFactory.create('pro', response_format='json_object').invoke(
            '将理赔核实工作拆成最多8步，只输出JSON对象，steps为字符串数组。报案资料：' + question)
        return json.loads(reply.content)['steps']
    def executor(step: str) -> str:
        return str(ClaimLLMFactory.create('main').invoke('分析这一步所需证据，不声称执行了未调用的操作：' + step).content)
    return build_plan_execute(planner, executor)
