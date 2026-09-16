"""保单与历史查询工具：应用注入后端，查询异常使用ToolException。"""
from typing import Any
from langchain_core.tools import tool, ToolException
from pydantic import Field
from models.schemas import Contract
from adapters.business import BusinessBackend


class PolicyQueryInput(Contract):
    policy_id: str = Field(min_length=1, max_length=64, description='待查询保单号')


class HistoryInput(Contract):
    policyholder_id: str = Field(min_length=1, max_length=64, description='投保人内部标识，不是身份证号码')
    limit: int = Field(default=10, ge=1, le=100, description='最多返回记录条数')


def build_policy_tools(backend: BusinessBackend) -> list[Any]:
    @tool(args_schema=PolicyQueryInput)
    def query_policy(policy_id: str) -> dict:
        """查询保单实时状态及来源；降级数据须转人工核实，不能自动判有效。"""
        try:
            return backend.call('query_policy', policy_id=policy_id)
        except Exception as exc:
            raise ToolException(f'保单查询失败：{type(exc).__name__}，需人工核实') from exc

    @tool(args_schema=HistoryInput)
    def query_claim_history(policyholder_id: str, limit: int = 10) -> dict:
        """查询投保人历史理赔；查询失败不等于没有历史记录。"""
        try:
            return backend.call('query_claim_history', policyholder_id=policyholder_id, limit=limit)
        except Exception as exc:
            raise ToolException(f'历史查询失败：{type(exc).__name__}') from exc

    return [query_policy, query_claim_history]
