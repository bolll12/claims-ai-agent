"""模块05四种输出模式及有限次数的结构化修复。

修复失败返回独立的人工复核结果，避免原文UNKNOWN报案号违反Schema。
"""
from collections.abc import Callable
from typing import Any, Generic, TypeVar

from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import JsonOutputParser, PydanticOutputParser, StrOutputParser
from pydantic import BaseModel, Field

from models.schemas import Contract, StructuredClaimResult

T = TypeVar('T', bound=BaseModel)


class ManualReviewRequired(Contract):
    """技术失败记录，不伪装成已完成的业务判责。"""
    claim_id: str = Field(min_length=1)
    requires_manual_review: bool = True
    reason: str = '结构化结果经修复仍未通过校验，需要人工核实原始材料。'
    attempts: int = Field(ge=1)


class SafePydanticOutputParser(Generic[T]):
    """保留原始请求上下文，由调用方注入模型修复函数。"""
    def __init__(self, model: type[T], repair: Callable[[str, str, str], str],
                 max_retries: int = 2) -> None:
        if not 0 <= max_retries <= 2:
            raise ValueError('最多允许2次修复')
        self.parser = PydanticOutputParser(pydantic_object=model)
        self.repair = repair
        self.max_retries = max_retries

    def parse(self, text: str, *, claim_id: str, original_prompt: str) -> T | ManualReviewRequired:
        """校验失败把错误反馈给修复函数；成功输出仍需绑定当前案件。"""
        candidate = text
        for attempt in range(self.max_retries + 1):
            try:
                result = self.parser.parse(candidate)
                if getattr(result, 'claim_id', claim_id) != claim_id:
                    raise OutputParserException('模型输出报案号与请求不一致')
                return result
            except OutputParserException as exc:
                if attempt == self.max_retries:
                    break
                # 不捕获网络/认证错误并伪装成解析成功，由上层显式降级。
                candidate = self.repair(original_prompt, candidate, str(exc))
        return ManualReviewRequired(claim_id=claim_id, attempts=self.max_retries + 1)


def output_modes(model: Any) -> dict[str, Any]:
    """创建四种输出组件；实际调用由演示或业务链显式执行。"""
    return {
        'text': StrOutputParser(),
        'json': JsonOutputParser(),
        'pydantic': PydanticOutputParser(pydantic_object=StructuredClaimResult),
        'structured_model': model.with_structured_output(StructuredClaimResult, method='function_calling'),
    }


def migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """显式迁移旧confidence/amount字段；冲突或未知版本拒绝静默覆盖。"""
    migrated = dict(data)
    version = str(migrated.get('schema_version', '1'))
    if version not in ('1', '2'):
        raise ValueError(f'不支持的Schema版本：{version}')
    if version == '1':
        for old, new in (('confidence', 'confidence_score'), ('amount', 'estimated_amount')):
            if old in migrated:
                if new in migrated and migrated[new] != migrated[old]:
                    raise ValueError(f'新旧字段冲突：{old}/{new}')
                migrated[new] = migrated.pop(old)
    migrated['schema_version'] = '2'
    return StructuredClaimResult.model_validate(migrated).model_dump(mode='json')
