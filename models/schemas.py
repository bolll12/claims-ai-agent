"""理赔 HTTP 接口请求与响应契约。"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated
from pydantic import AfterValidator, model_validator

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ClaimRequest(BaseModel):
    """理赔处理请求。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    claim_id: str = Field(..., min_length=1, max_length=64, description="案件标识")
    description: str = Field(..., min_length=1, max_length=10000, description="报案描述", validation_alias=AliasChoices('description', 'claim_text'))
    policy_id: str | None = Field(default=None, min_length=1, max_length=64)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)


class ClaimResponse(BaseModel):
    """审核工作流响应，决定为建议，不代表付款已执行。"""

    model_config = ConfigDict(extra="forbid")
    claim_id: str = Field(..., min_length=1, max_length=64, description="案件标识")
    decision: Literal["pending", "review", "accept", "reject", "investigate"] = "pending"
    phase: str = "pending"
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    demo: bool = False
    message: str = Field(..., description="处理情况说明")


# 下列业务契约来自材料模块05，HTTP响应映射工作流状态。



def _cents(value: Decimal) -> Decimal:
    """拒绝分以下精度，避免隐式舍入改变实际金额。"""
    if not value.is_finite() or value != value.quantize(Decimal('0.01')):
        raise ValueError('金额必须为有限数且精确到分')
    return value


Money = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2), AfterValidator(_cents)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2), AfterValidator(_cents)]
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
ClaimId = Annotated[str, Field(pattern=r'^CLM-\d{4}-\d{3,}$', max_length=32)]


class Contract(BaseModel):
    """拒绝未声明字段和非有限值，统一业务模型配置。"""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)


class ClaimDecision(str, Enum):
    """审核建议；审核建议不代表已经完成赔付。"""
    ACCEPT = '受理'
    REJECT = '不受理'
    INVESTIGATE = '调查'
    MANUAL_REVIEW = '人工复核'


class ClaimBase(Contract):
    """报案基础信息；未知业务事实不提供虚构默认值。"""
    claim_id: ClaimId
    policy_id: str = Field(min_length=1, max_length=64)
    accident_type: str = Field(min_length=1, max_length=100)
    reported_at: datetime


class ClaimInfo(ClaimBase):
    """报案及补充材料。"""
    claim_text: str = Field(min_length=1, max_length=10000)
    amount: Money | None = None
    materials: list[str] = Field(default_factory=list)


class PolicyInfo(Contract):
    """真实保单信息；是否覆盖事故责任需要结合具体条款另行核验。"""
    policy_id: str = Field(min_length=1, max_length=64)
    policy_type: str = Field(min_length=1)
    status: Literal['有效', '无效', '已脱保', '待核实']
    coverage: Money
    deductible: Money
    valid_from: datetime
    valid_until: datetime
    clauses: list[str] = Field(default_factory=list)
    source: str = Field(min_length=1)

    @model_validator(mode='after')
    def validate_dates(self) -> 'PolicyInfo':
        """保单期间必须有序，起止时间时区表示也应一致。"""
        if (self.valid_from.tzinfo is None) != (self.valid_until.tzinfo is None):
            raise ValueError('保险期间的时区表示必须一致')
        if self.valid_until <= self.valid_from:
            raise ValueError('保单终止时间必须晚于开始时间')
        return self


class StructuredClaimResult(Contract):
    """经校验的审核建议，拒赔不得携带正赔付金额。"""
    schema_version: Literal['2'] = '2'
    claim_id: ClaimId
    decision: ClaimDecision
    liability_ratio: Probability
    confidence_score: Probability
    estimated_amount: PositiveMoney | None = None
    reason: str = Field(min_length=20, max_length=500)
    risk_factors: list[str] = Field(default_factory=list)
    clause_basis: list[str] = Field(default_factory=list)
    next_action: str = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def reject_has_no_payment(self) -> 'StructuredClaimResult':
        """禁止拒赔建议同时携带赔付金额。"""
        if self.decision == ClaimDecision.REJECT and self.estimated_amount is not None:
            raise ValueError('不受理案件不应有赔付金额')
        return self


class ClaimReviewResult(StructuredClaimResult):
    """模块10的审核结果命名，与模块05结构化契约一致。"""


class SettlementDetail(Contract):
    """计算明细只描述建议，不执行付款。"""
    amount: Money
    deductible: Money
    formula: str = Field(min_length=1)
    payment_method: str = Field(min_length=1)


class FraudAssessment(Contract):
    """风险证据与评估；风险等级映射由已批准的业务规则决定。"""
    risk_score: Probability
    risk_level: Literal['低', '中', '高', '待核实']
    risk_factors: list[str]
    recommended_actions: list[str]
    evidence_sources: list[str]


class ConfidenceMetrics(Contract):
    """评分与校准状态分开记录，避免把未经校准的分数当概率。"""
    score: Probability
    calibrated: bool
    method: str = Field(min_length=1)
    evidence_count: int = Field(ge=0)


class FullClaimReport(Contract):
    """整合报案、审核、风险及赔付建议，跨模型检查案件和金额。"""
    claim: ClaimInfo
    review: ClaimReviewResult
    fraud: FraudAssessment
    settlement: SettlementDetail | None = None
    confidence: ConfidenceMetrics | None = None

    @model_validator(mode='after')
    def consistent_report(self) -> 'FullClaimReport':
        """报告只能关联同一案件；拒赔报告不能包含正金额结算。"""
        if self.claim.claim_id != self.review.claim_id:
            raise ValueError('报告中的报案号不一致')
        if self.review.decision == ClaimDecision.REJECT and self.settlement and self.settlement.amount > 0:
            raise ValueError('不受理报告不能包含正金额结算')
        return self
