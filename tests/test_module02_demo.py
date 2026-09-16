"""验证本地配置、并发顺序与单案失败隔离，不发起真实推理。"""

import asyncio
import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from demos import module02_demo as demo
from models.schemas import ClaimRequest


@pytest.mark.parametrize("tier", list(demo.PROFILES))
def test_local_profiles(monkeypatch: pytest.MonkeyPatch, tier: str) -> None:
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("LOCAL_LLM_API_KEY", "test-placeholder")
    model = demo.build_model(tier)
    assert model.openai_api_base == "http://127.0.0.1:8000/v1"
    assert model.openai_api_key.get_secret_value() == "test-placeholder"
    assert model.seed == 42
    assert model.model_kwargs["response_format"] == {"type": "json_object"}
    assert model.temperature == demo.PROFILES[tier].temperature
    assert model.top_p == demo.PROFILES[tier].top_p


def test_batch_order_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        last_finished = asyncio.Event()
        completed: list[str] = []

        class FakeModel:
            async def ainvoke(self, messages: list[Any]) -> AIMessage:
                claim_id = json.loads(messages[-1].content)["claim_id"]
                if claim_id == "1":
                    await last_finished.wait()
                completed.append(claim_id)
                if claim_id == "3":
                    last_finished.set()
                if claim_id == "2":
                    return AIMessage(content="not valid JSON")
                return AIMessage(content=json.dumps({
                    "claim_id": claim_id,
                    "recommendation": "pending",
                    "rationale": "缺少保单条款",
                    "missing_information": ["保单条款"],
                }))

        monkeypatch.setattr(demo, "build_model", lambda tier: FakeModel())
        claims = [ClaimRequest(claim_id=str(i), description="测试") for i in range(1, 4)]
        results = await asyncio.wait_for(demo.review_nightly(claims, concurrency=3), timeout=2)
        assert completed == ["2", "3", "1"]
        assert [r.claim_id for r in results] == ["1", "2", "3"]
        assert [r.status for r in results] == ["success", "error", "success"]

    asyncio.run(scenario())


def test_empty_batch() -> None:
    assert asyncio.run(demo.review_nightly([])) == []
    with pytest.raises(ValueError):
        asyncio.run(demo.review_nightly([], concurrency=0))
