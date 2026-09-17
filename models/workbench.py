"""理赔工作台的单证识别与问答契约。"""

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from models.schemas import ClaimRequest, ClaimResponse


FieldName = Annotated[str, Field(min_length=1, max_length=50)]
FieldValue = Annotated[str, Field(max_length=300)]
WarningText = Annotated[str, Field(min_length=1, max_length=500)]
IntentName: TypeAlias = Literal[
    "理赔报案",
    "材料审核",
    "进度查询",
    "条款咨询",
    "补充材料",
    "一般咨询",
]


class DocumentAnalysis(BaseModel):
    """单份附件的结构化识别结果。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    document_id: str = Field(min_length=1, max_length=64)
    file_name: str = Field(min_length=1, max_length=255)
    document_type: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=2000)
    fields: dict[FieldName, FieldValue] = Field(default_factory=dict, max_length=20)
    confidence: float | None = Field(default=None, ge=0, le=1)
    warnings: list[WarningText] = Field(default_factory=list, max_length=10)


class DocumentBatchResponse(BaseModel):
    """批量附件识别响应。"""

    documents: list[DocumentAnalysis]


class ChatTurn(BaseModel):
    """浏览器传回的有限对话历史。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)
    intent: IntentName | None = None


class AssistantRequest(BaseModel):
    """基于案件和已识别单证的问答请求。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=4000)
    claim_id: str | None = Field(default=None, max_length=64)
    documents: list[DocumentAnalysis] = Field(default_factory=list, max_length=6)
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)
    material_round: int = Field(default=0, ge=0, le=3)


class IntentResult(BaseModel):
    """模型对当前用户消息的意图识别结果。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    intent: IntentName
    confidence: float = Field(ge=0, le=1)


class DemoClaimRunResponse(BaseModel):
    """本地合成案件的一次完整状态机运行结果。"""

    claim: ClaimRequest
    documents: list[DocumentAnalysis]
    result: ClaimResponse
    trace: list[dict[str, Any]]
