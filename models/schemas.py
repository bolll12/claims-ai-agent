"""理赔 HTTP 接口请求与响应契约。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ClaimRequest(BaseModel):
    """理赔处理请求。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    claim_id: str = Field(..., min_length=1, max_length=64, description="案件标识")
    description: str = Field(..., min_length=1, max_length=10000, description="报案描述")


class ClaimResponse(BaseModel):
    """理赔处理响应，当前仅支持占位状态。"""

    model_config = ConfigDict(extra="forbid")
    claim_id: str = Field(..., min_length=1, max_length=64, description="案件标识")
    decision: Literal["pending"] = "pending"
    message: str = Field(..., description="处理情况说明")
