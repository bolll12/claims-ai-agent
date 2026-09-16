"""验证客服消息角色、工具配对及自然文本调用配置。"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from demos import module04_demo as demo


def test_role_order() -> None:
    history = demo.build_conversation()
    assert [item.type for item in history] == ["system", "human", "ai", "human", "ai", "human", "ai", "human"]


def test_tool_pair_and_history_unchanged() -> None:
    history = demo.build_conversation()
    result = demo.with_demo_tool(history)
    assert len(history) == 8
    assert isinstance(result[-2], AIMessage)
    assert isinstance(result[-1], ToolMessage)
    assert result[-2].tool_calls[0]["id"] == result[-1].tool_call_id
    assert "模拟" in result[-1].content


def test_orphan_and_mismatched_tools_rejected() -> None:
    with pytest.raises(ValueError):
        demo.inject_tool_results([HumanMessage(content="报案")], {"missing": {}})
    call = AIMessage(content="", tool_calls=[{"name": "lookup_policy", "args": {}, "id": "correct"}])
    with pytest.raises(ValueError):
        demo.inject_tool_results([call], {"wrong": {}})


def test_reply_uses_text_and_complete_history(monkeypatch: pytest.MonkeyPatch) -> None:
    history = demo.build_conversation()

    class FakeModel:
        def bind(self, **kwargs):
            assert kwargs == {"response_format": {"type": "text"}, "stop": []}
            return self

        def invoke(self, messages):
            assert messages == history
            return AIMessage(content="请保留照片，下一步核实保单信息。")

    def build(tier):
        assert tier == "flexible"
        return FakeModel()

    monkeypatch.setattr(demo, "build_model", build)
    assert isinstance(demo.reply(history), AIMessage)
