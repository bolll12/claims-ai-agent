"""理赔对话的材料完整性核查，不用模型猜测材料是否存在。"""

from dataclasses import dataclass

from models.workbench import DocumentAnalysis


@dataclass(frozen=True)
class MaterialCheck:
    """当前会话已具备和仍缺少的材料类别。"""

    present: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.missing


def check_claim_materials(documents: list[DocumentAnalysis]) -> MaterialCheck:
    """按已识别内容核查通用理赔预审所需的三类基础材料。"""
    evidence_names = " ".join(
        f"{document.document_type} {document.file_name}" for document in documents
    )
    checks = {
        # 报案单里引用编号不等于已经提交保单或保险凭证原件。
        "保单信息": any(token in evidence_names for token in ("保单", "保险凭证")),
        "事故或出险证明": any(
            token in evidence_names
            for token in ("事故", "出险", "报案", "交警", "诊断证明", "病历", "现场照片")
        ),
        "费用或损失凭证": any(
            token in evidence_names
            for token in ("发票", "费用清单", "维修报价", "定损", "损失凭证", "结算单")
        ),
    }
    return MaterialCheck(
        present=tuple(name for name, available in checks.items() if available),
        missing=tuple(name for name, available in checks.items() if not available),
    )


__all__ = ["MaterialCheck", "check_claim_materials"]
