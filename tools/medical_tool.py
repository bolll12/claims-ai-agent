"""异步医保核验工具，接口由组织适配器实现。"""
import asyncio
from typing import Any
from langchain_core.tools import tool, ToolException
from pydantic import Field
from models.schemas import Contract
from adapters.business import BusinessBackend


class MedicalInput(Contract):
    patient_id: str = Field(min_length=1, max_length=64, description='内部患者标识')
    diagnosis: str = Field(min_length=1, max_length=500, description='待核验诊断或医疗编码')


def build_medical_tool(backend: BusinessBackend) -> Any:
    @tool(args_schema=MedicalInput)
    async def verify_insurance_coverage(patient_id: str, diagnosis: str) -> dict:
        """异步核验医保报销责任；未知责任不能推断为已覆盖。"""
        try:
            return await asyncio.to_thread(backend.call, 'verify_insurance_coverage', patient_id=patient_id, diagnosis=diagnosis)
        except Exception as exc:
            raise ToolException(f'医保核验失败：{type(exc).__name__}') from exc
    return verify_insurance_coverage
