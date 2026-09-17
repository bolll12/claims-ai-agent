"""可重复运行的合成理赔案件，仅用于本地演示和链路验证。"""

from decimal import Decimal

from models.schemas import ClaimRequest
from models.workbench import DocumentAnalysis


def build_mock_claim() -> tuple[ClaimRequest, list[DocumentAnalysis]]:
    """返回一件材料齐全、可进入自动审核路径的合成车险案件。"""
    claim = ClaimRequest(
        claim_id="CLM-DEMO-2026-001",
        description="停车场低速倒车时与固定护栏发生轻微刮擦，无人员受伤，申请车辆维修理赔。",
        policy_id="POL-2024-001",
        amount=Decimal("1286.40"),
    )
    documents = [
        DocumentAnalysis(
            document_id="DOC-DEMO-001",
            file_name="演示事故报案单.txt",
            document_type="机动车事故报案单",
            summary="合成报案单：记录停车场低速刮擦、无人员受伤及维修报价。",
            fields={
                "案件号": claim.claim_id,
                "保单号": claim.policy_id or "",
                "报案金额": str(claim.amount),
                "事故类型": "单方轻微刮擦",
            },
            confidence=0.97,
            warnings=[],
        )
    ]
    return claim, documents


__all__ = ["build_mock_claim"]
