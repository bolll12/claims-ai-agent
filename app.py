"""理赔 Agent HTTP 服务，使用 uvicorn app:app 启动。"""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from models.schemas import ClaimRequest, ClaimResponse

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
app = FastAPI(title="理赔 Agent 服务", version="0.1.0")

# 环境变量可配置多个前端来源，使用逗号分隔。
cors_origins: list[str] = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOW_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


class HealthResponse(BaseModel):
    """服务存活状态，不代表外部依赖可用。"""

    status: Literal["ok"] = "ok"


@app.get("/health", response_model=HealthResponse, tags=["健康检查"])
async def health() -> HealthResponse:
    """返回 HTTP 服务存活状态。"""
    return HealthResponse()


@app.post("/api/claims/process", response_model=ClaimResponse, tags=["理赔处理"])
async def process_claim(request: ClaimRequest) -> ClaimResponse:
    """返回符合契约的占位响应。"""
    # TODO：接入理赔状态机，将执行结果映射为响应契约。
    # 当前不执行推理、不持久化案件，也不创建后台任务。
    return ClaimResponse(
        claim_id=request.claim_id,
        decision="pending",
        message="占位响应：理赔状态机尚未接入。",
    )
