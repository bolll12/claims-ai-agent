"""使用真实Deep Agents调度器和确定性假模型验证接口，禁止外部调用。"""
import asyncio
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from isolated_deep.runtime import create_agent, process_claim
from isolated_deep.security import mask_pii


class FakeToolModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def test_real_deep_agent_structured_output_and_high_amount_review():
    model = FakeToolModel(responses=[AIMessage(content='', tool_calls=[{
        'name': 'DeepReview', 'id': 'review-1', 'args': {'decision': 'accept', 'confidence': .95,
        'reason': '仅用于SDK接口回归的合成输出', 'clause_basis': []}}])])
    graph = create_agent(model=model, tools=[])
    result = asyncio.run(process_claim(graph, 'test-case', '合成案件，不连接真实系统', amount=60000))
    assert result['review']['decision'] == 'review'
    assert result['structured_response'].confidence == .95


def test_isolated_runtime_masks_sensitive_data_without_main_project_imports():
    result = mask_pii({'text': '电话13812345678，密钥sk-example123', 'api_key': 'secret'})
    assert result == {'text': '电话[手机号]，密钥[密钥]', 'api_key': '[REDACTED]'}
