"""支持进程内和真实 HTTP 的服务冒烟测试。"""

import os
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app import app
from models.schemas import ClaimResponse


@pytest.fixture
def client() -> Iterator[httpx.Client]:
    """设置 SMOKE_BASE_URL 时测试运行中的服务，否则使用测试客户端。"""
    base_url = os.getenv("SMOKE_BASE_URL")
    if base_url:
        with httpx.Client(base_url=base_url, timeout=5.0, trust_env=False) as session:
            yield session
    else:
        with TestClient(app) as session:
            yield session


def test_health(client: httpx.Client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_process_claim(client: httpx.Client) -> None:
    response = client.post(
        "/api/claims/process",
        json={"claim_id": "CLM-001", "description": "医疗费用理赔"},
    )
    assert response.status_code == 200
    result = ClaimResponse.model_validate(response.json())
    assert result.claim_id == "CLM-001"
    assert result.decision == "pending"
    assert result.message


@pytest.mark.parametrize("payload", [{}, {"claim_id": "CLM-001"}, {"claim_id": " ", "description": "理赔"}])
def test_invalid_claim(client: httpx.Client, payload: dict[str, str]) -> None:
    assert client.post("/api/claims/process", json=payload).status_code == 422


def test_cors(client: httpx.Client) -> None:
    response = client.options(
        "/api/claims/process",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
