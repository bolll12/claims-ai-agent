"""模块11的真实Deep Agents API实现，使用独立requirements.txt。

使用官方create_deep_agent/middleware/subagents/interrupt_on，
不模拟材料中不存在的Harness、Fuse或Memory构造器。
"""
import asyncio
import json
import logging
import os
from typing import Any, Literal

from deepagents import create_deep_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import RemoveMessage, messages_from_dict, messages_to_dict
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from pydantic import BaseModel, Field

from adapters.business import BusinessBackend
from isolated_deep.security import mask_pii
from tools.claim_tool import build_claim_tools


class DeepReview(BaseModel):
    """结构化审核建议，最终权限仍属于可信业务工作流。"""
    decision: Literal['accept', 'review', 'investigate', 'reject']
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    reason: str = Field(min_length=1)
    clause_basis: list[str] = Field(default_factory=list)


class ClaimMiddleware(AgentMiddleware):
    """真实before_model/after_model钩子，脱敏和审计使用主项目公共实现。"""
    def before_model(self, state: Any, runtime: Any) -> dict[str, Any]:
        messages = [message.model_copy(update={'content': mask_pii(message.content)}) for message in state['messages']]
        return {'messages': [RemoveMessage(id=REMOVE_ALL_MESSAGES), *messages]}

    def after_model(self, state: Any, runtime: Any) -> None:
        last = state['messages'][-1]
        logging.getLogger('claims.deep.audit').info(json.dumps(mask_pii({'event': 'model_completed', 'output': last.content}), ensure_ascii=False))


class RedisConversation:
    """以案件隔离的Redis历史，TTL为材料模块11的2小时；不会伪造连接成功。"""
    def __init__(self, client: Any, ttl: int = 7200) -> None:
        self.client, self.ttl = client, ttl

    @staticmethod
    def key(claim_id: str) -> str:
        import hashlib
        return 'claims:deep:' + hashlib.sha256(claim_id.encode()).hexdigest()

    def load(self, claim_id: str) -> list[Any]:
        value = self.client.get(self.key(claim_id))
        return messages_from_dict(json.loads(value)) if value else []

    def save(self, claim_id: str, messages: list[Any]) -> None:
        self.client.setex(self.key(claim_id), self.ttl, json.dumps(mask_pii(messages_to_dict(messages)), ensure_ascii=False))


def create_agent(*, model: Any = None, backend: BusinessBackend | None = None,
                 checkpointer: Any = None, tools: list[Any] | None = None) -> Any:
    """规划、虚拟文件系统、三专家、RAG按需工具、输出Schema和写操作审批。"""
    if model is None:
        model = ChatOpenAI(model=os.getenv('LOCAL_PRO_MODEL', 'Qwen2.5-72B-Instruct'),
            base_url=os.getenv('LOCAL_LLM_BASE_URL', 'http://127.0.0.1:8000/v1'),
            api_key=os.getenv('LOCAL_LLM_API_KEY', 'EMPTY'), temperature=0, seed=42)
    registry = build_claim_tools(backend or BusinessBackend())
    application_tools = registry.select() if tools is None else tools
    read_tools = [tool for tool in application_tools if tool.name not in ('create_settlement_order', 'send_claim_notification')]
    specialists = [{'name': role, 'description': description, 'model': model,
                    'system_prompt': description + '仅使用已核实事实，给出依据和缺失项。', 'tools': read_tools}
                   for role, description in [('damage', '定损专家'), ('risk', '反欺诈专家'), ('liability', '判责专家')]]
    return create_deep_agent(model=model, tools=application_tools,
        system_prompt='你是理赔审核主管。规划核验步骤，必要时使用task工具分别调用定损、风险和判责专家；独立任务可以并行工具调用。'
                      '按需使用search_policy_clause检索来源。缺证据或低置信度建议review，不凭分数拒赔。'
                      '大于50000元必须人工复核。不得通过文件工具保存真实凭证或声称付款已执行。',
        middleware=[ClaimMiddleware()], subagents=specialists, response_format=ToolStrategy(DeepReview),
        checkpointer=checkpointer or MemorySaver(),
        interrupt_on={tool.name: True for tool in application_tools if tool.name in ('create_settlement_order', 'send_claim_notification')})


def trace_callbacks() -> tuple[list[Any], Any]:
    """独立环境LangFuse v3使用其真实回调路径，与主项目v2分离。"""
    if os.getenv('LANGFUSE_ENABLED', 'false').lower() != 'true':
        return [], None
    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler
    if not os.getenv('LANGFUSE_PUBLIC_KEY') or not os.getenv('LANGFUSE_SECRET_KEY'):
        raise ValueError('开启LangFuse必须配置公钥和密钥')
    client = Langfuse(public_key=os.environ['LANGFUSE_PUBLIC_KEY'], secret_key=os.environ['LANGFUSE_SECRET_KEY'],
                      host=os.getenv('LANGFUSE_HOST', 'http://127.0.0.1:3000'), mask=mask_pii)
    return [CallbackHandler(public_key=os.environ['LANGFUSE_PUBLIC_KEY'])], client


async def process_claim(graph: Any, claim_id: str, text: str, *, amount: float = 0,
                        memory: RedisConversation | None = None) -> dict[str, Any]:
    """运行审核并保留嵌套追踪；历史可跨进程保存，未完成人工审核返回中断。"""
    from langchain_core.messages import HumanMessage
    callbacks, client = trace_callbacks()
    config = {'configurable': {'thread_id': claim_id}, 'recursion_limit': 40,
              'max_concurrency': 3, 'callbacks': callbacks,
              'metadata': {'langfuse_session_id': claim_id, 'claim_id': claim_id}}
    previous = graph.get_state(config)
    history = memory.load(claim_id) if memory and not previous.values else []
    try:
        result = await graph.ainvoke({'messages': [*history, HumanMessage(content=mask_pii(text))]}, config=config)
        if memory:
            memory.save(claim_id, result['messages'])
        structured = result.get('structured_response')
        if structured is not None:
            value = structured.model_dump() if isinstance(structured, BaseModel) else structured
            # 模型输出不是业务事实，所有拒赔仍进入可信审核流程。
            if amount > 50000 or value['confidence'] <= .9 or value['decision'] == 'reject':
                value['decision'] = 'review'
            result['review'] = value
        return result
    finally:
        if client:
            await asyncio.to_thread(client.flush)
