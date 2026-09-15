"""拦截实际 SDK HTTP 请求，确认任务参数被序列化发送。"""

import json

import httpx
import pytest

from config import MODEL_ROUTING, STOP_MARKER, TASK_PROFILES
from tools.llm_calls import _messages


@pytest.mark.parametrize("task", list(TASK_PROFILES))
def test_request_parameters(task: str) -> None:
    """使用模拟传输层，不访问百炼、不使用真实密钥。"""
    captured: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "test", "object": "chat.completion", "created": 0,
            "model": "test", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": '{"decision":"pending"}'}}],
        })

    with httpx.Client(transport=httpx.MockTransport(handle)) as http_client:
        # 复用路由模型的全部生成参数，但替换客户端与认证信息。
        source = MODEL_ROUTING[task]
        model = type(source)(
            model=source.model_name,
            temperature=source.temperature,
            top_p=source.top_p,
            max_tokens=source.max_tokens,
            stop=source.stop,
            frequency_penalty=source.frequency_penalty,
            presence_penalty=source.presence_penalty,
            seed=source.seed,
            model_kwargs=source.model_kwargs,
            base_url="http://127.0.0.1:8000/v1",
            api_key="test-placeholder",
            http_client=http_client,
            max_retries=0,
        )
        model.invoke(_messages(task, "测试案件"))

    payload = captured[0]
    profile = TASK_PROFILES[task]
    assert payload["temperature"] == profile.temperature
    assert payload["top_p"] == profile.top_p
    # langchain-openai 0.2.14 在发送前将 max_tokens 转为此协议字段。
    assert payload["max_completion_tokens"] == profile.max_tokens
    assert payload["frequency_penalty"] == profile.frequency_penalty
    assert payload["presence_penalty"] == profile.presence_penalty
    assert payload["seed"] == 42
    assert payload["stop"] == [STOP_MARKER]
    assert payload["response_format"] == {"type": profile.response_format}
    if profile.response_format == "json_object":
        assert "json" in payload["messages"][0]["content"].lower()
