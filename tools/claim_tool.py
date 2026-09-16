"""模块04完整工具集、可信审批绑定和并行工具调用闭环。"""
import asyncio
from collections.abc import Callable, Sequence
import json
from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import Field, StrictBool

from adapters.business import BusinessBackend
from models.schemas import Contract, PositiveMoney
from tools.policy_tool import build_policy_tools
from tools.medical_tool import build_medical_tool
from tools.claim_write_producer import Outbox


class ClaimCalcInput(Contract):
    damage_type: str = Field(min_length=1, max_length=100, description='损失类型，如刮擦')
    damage_area: str = Field(min_length=1, max_length=100, description='车辆受损部位')
    severity: Literal['轻微', '中度', '重度'] = Field(description='受损严重程度')
    vehicle_model: str = Field(min_length=1, max_length=100, description='车型，真实定损需价格依据')


class LiabilityCalcInput(Contract):
    accident_type: str = Field(min_length=1, max_length=100, description='事故类型')
    violation_side: Literal['己方', '对方', '双方'] = Field(description='已核实的违规方')
    has_evidence: StrictBool = Field(description='是否具备核实后的事故证据')


class ClauseInput(Contract):
    query: str = Field(min_length=1, max_length=1000, description='条款自然语言查询')
    insurance_type: str = Field(default='auto', min_length=1, max_length=32, description='险种检索范围')


class SettlementInput(Contract):
    claim_id: str = Field(min_length=1, max_length=64, description='案件标识')
    amount: PositiveMoney = Field(description='核准金额（元），精确到分')
    payee_id: str = Field(min_length=1, max_length=64, description='收款人在核心系统的内部标识')
    idempotency_key: str = Field(min_length=1, max_length=128, description='同一业务操作稳定不变的幂等键')


class NotificationInput(Contract):
    claim_id: str = Field(min_length=1, max_length=64, description='案件标识')
    phone: str = Field(pattern=r'^1[3-9]\d{9}$', description='接收通知手机号')
    template: str = Field(min_length=1, max_length=64, description='经过审核的通知模板标识')
    parameters: dict[str, str] = Field(description='模板参数')
    idempotency_key: str = Field(min_length=1, max_length=128, description='通知幂等键')


class ClaimToolsRegistry:
    """工具按单一职责注册，动态描述变更使用副本。"""
    def __init__(self) -> None:
        self.tools: dict[str, tuple[str, BaseTool]] = {}

    def register(self, category: str, tool: BaseTool) -> None:
        if tool.name in self.tools:
            raise ValueError('工具名称重复：' + tool.name)
        self.tools[tool.name] = (category, tool)

    def select(self, category: str | None = None) -> list[BaseTool]:
        return [tool for group, tool in self.tools.values() if category is None or category == group]

    def describe(self, name: str, description: str) -> None:
        if not description.strip():
            raise ValueError('工具说明不能为空')
        category, tool = self.tools[name]
        self.tools[name] = category, tool.model_copy(update={'description': description})


def build_claim_tools(backend: BusinessBackend, *, outbox: Outbox | None = None,
                      authorize: Callable[[str, dict[str, Any]], bool] | None = None) -> ClaimToolsRegistry:
    """审批函数来自认证后的服务端上下文，模型参数不能伪造approved标记。"""
    registry = ClaimToolsRegistry()
    for tool in build_policy_tools(backend):
        registry.register('query', tool)
    registry.register('query', build_medical_tool(backend))

    def add(name: str, schema: type[Contract], category: str, description: str) -> None:
        def execute(**kwargs: Any) -> dict[str, Any]:
            try:
                if category == 'operation':
                    payload = schema.model_validate(kwargs).model_dump(mode='json')
                    if authorize is None or not authorize(name, payload):
                        raise PermissionError('操作未经服务端审批')
                    if outbox is None:
                        raise RuntimeError('未配置Outbox')
                    # 审批必须核对具体金额、收款方、案件及操作，不仅核对工具名。
                    return outbox.publish(payload['claim_id'], name, payload, payload['idempotency_key'])
                return backend.call(name, **kwargs)
            except Exception as exc:
                raise ToolException(f'{name}失败：{type(exc).__name__}，不得当作成功结果') from exc
        registry.register(category, StructuredTool.from_function(execute, name=name, description=description, args_schema=schema))

    add('calculate_claim_amount', ClaimCalcInput, 'calculation', '根据损失、部位、程度、车型查询已核实价格依据；demo价格仅用于教学。')
    add('calculate_liability', LiabilityCalcInput, 'calculation', '根据已核实证据及适用规则分析责任；无证据转人工，不默认五五责。')
    add('search_policy_clause', ClauseInput, 'retrieval', '检索限定险种的条款及来源，查无资料时不得编造条款。')
    add('create_settlement_order', SettlementInput, 'operation', '经服务端逐项审批后将赔付单写入队列；入队不代表已支付。')
    add('send_claim_notification', NotificationInput, 'operation', '经服务端审批后将通知写入队列；不代表已发送。')
    return registry


async def tool_round(model: Any, messages: Sequence[BaseMessage], tools: list[BaseTool],
                     *, choice: str = 'auto', max_concurrency: int = 4) -> list[BaseMessage]:
    """保留完整历史，实际并行执行独立调用，再交模型续答；返回输入顺序。"""
    if max_concurrency < 1:
        raise ValueError('并发数必须为正')
    # OpenAI required 表示至少一个工具；不是auto。
    bound = model.bind_tools(tools, tool_choice=choice, parallel_tool_calls=True)
    answer = await bound.ainvoke(list(messages))
    if not isinstance(answer, AIMessage):
        raise TypeError('工具规划需要AIMessage')
    history = [*messages, answer]
    by_name = {tool.name: tool for tool in tools}
    semaphore = asyncio.Semaphore(max_concurrency)
    async def run(call: dict[str, Any]) -> ToolMessage:
        async with semaphore:
            try:
                output = await by_name[call['name']].ainvoke(call['args'])
            except Exception as exc:
                output = {'error': type(exc).__name__, 'requires_manual_review': True}
            return ToolMessage(content=json.dumps(output, ensure_ascii=False, default=str), tool_call_id=call['id'], name=call['name'])
    ids = [call.get('id') for call in answer.tool_calls]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError('工具调用id必须非空且唯一')
    if answer.tool_calls:
        history.extend(await asyncio.gather(*(run(call) for call in answer.tool_calls)))
        history.append(await model.ainvoke(history))
    return history
