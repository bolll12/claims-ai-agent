"""理赔工作台页面、单证识别和流式问答测试。"""

import json
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app import create_app


class FakeWorkbenchModel:
    """只验证应用协议，不连接外部推理服务。"""

    def __init__(self) -> None:
        self.stream_system_prompts: list[str] = []
        self.classification_inputs: list[str] = []

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        if '意图分类器' in messages[0].content:
            classification_input = messages[-1].content
            self.classification_inputs.append(classification_input)
            general = 'Python' in classification_input or '"intent": "一般咨询"' in classification_input
            follow_up = '"intent": "理赔报案"' in classification_input
            return AIMessage(content=json.dumps({
                'intent': '一般咨询' if general else '补充材料' if follow_up else '材料审核',
                'confidence': 0.93,
            }, ensure_ascii=False))
        return AIMessage(content=json.dumps({
            'document_type': '医疗费用发票',
            'summary': '合成测试发票，仅用于验证接口。',
            'fields': {'金额': '128.00'},
            'confidence': 0.96,
            'warnings': [],
        }, ensure_ascii=False))

    async def astream(self, messages: list[Any]):
        self.stream_system_prompts.append(messages[0].content)
        yield AIMessage(content='请补充')
        yield AIMessage(content='费用清单。')


def test_workbench_page_and_assets() -> None:
    model = FakeWorkbenchModel()
    with TestClient(create_app(
        database=':memory:', document_text_model=model,
        document_vision_model=model, assistant_model=model, intent_model=model,
    )) as client:
        page = client.get('/')
        assert page.status_code == 200
        assert '理赔智能助手' in page.text
        assert client.get('/static/styles.css').status_code == 200


def test_text_document_analysis_and_streaming_question() -> None:
    model = FakeWorkbenchModel()
    with TestClient(create_app(
        database=':memory:', document_text_model=model,
        document_vision_model=model, assistant_model=model, intent_model=model,
    )) as client:
        analyzed = client.post(
            '/api/documents/analyze',
            files={'files': ('invoice.txt', '医疗费用合计128元'.encode(), 'text/plain')},
        )
        assert analyzed.status_code == 200
        document = analyzed.json()['documents'][0]
        assert document['document_type'] == '医疗费用发票'
        assert document['fields']['金额'] == '128.00'

        response = client.post('/api/assistant/stream', json={
            'question': '还缺什么材料？', 'claim_id': 'CLM-TEST-001',
            'documents': [document], 'history': [],
        })
        assert response.status_code == 200
        assert '请补充' in response.text and '费用清单' in response.text
        assert '材料审核' in response.text
        assert '保险理赔客服助手' in model.stream_system_prompts[-1]
        assert response.headers['content-type'].startswith('text/event-stream')


def test_document_validation_rejects_unsupported_and_mismatched_files() -> None:
    model = FakeWorkbenchModel()
    with TestClient(create_app(
        database=':memory:', document_text_model=model,
        document_vision_model=model, assistant_model=model, intent_model=model,
    )) as client:
        unsupported = client.post('/api/documents/analyze', files={'files': ('data.exe', b'MZ', 'application/octet-stream')})
        mismatched = client.post('/api/documents/analyze', files={'files': ('fake.pdf', b'not-pdf', 'application/pdf')})
        assert unsupported.status_code == 422
        assert mismatched.status_code == 422


def test_general_intent_routes_to_base_model_prompt() -> None:
    model = FakeWorkbenchModel()
    with TestClient(create_app(
        database=':memory:', document_text_model=model,
        document_vision_model=model, assistant_model=model,
        intent_model=model, general_model=model,
    )) as client:
        response = client.post('/api/assistant/stream', json={
            'question': 'Python列表推导式是什么？',
            'documents': [], 'history': [],
        })
        assert response.status_code == 200
        assert '一般咨询' in response.text
        assert model.stream_system_prompts
        assert '通用智能助手' in model.stream_system_prompts[-1]
        assert '保险理赔客服助手' not in model.stream_system_prompts[-1]


def test_follow_up_intent_receives_recent_history_and_previous_intent() -> None:
    model = FakeWorkbenchModel()
    with TestClient(create_app(
        database=':memory:', document_text_model=model,
        document_vision_model=model, assistant_model=model,
        intent_model=model, general_model=model,
    )) as client:
        response = client.post('/api/assistant/stream', json={
            'question': '那还需要准备什么？',
            'documents': [],
            'history': [
                {'role': 'user', 'content': '我发生交通事故，怎么申请理赔？'},
                {'role': 'assistant', 'content': '请先完成报案。', 'intent': '理赔报案'},
            ],
        })
        assert response.status_code == 200
        assert '补充材料' in response.text
        assert '我发生交通事故' in model.classification_inputs[-1]
        assert '"intent": "理赔报案"' in model.classification_inputs[-1]
        assert '保险理赔客服助手' in model.stream_system_prompts[-1]


def test_general_follow_up_inherits_topic_and_explicit_question_can_switch_topic() -> None:
    model = FakeWorkbenchModel()
    app = create_app(
        database=':memory:', document_text_model=model,
        document_vision_model=model, assistant_model=model,
        intent_model=model, general_model=model,
    )
    with TestClient(app) as client:
        inherited = client.post('/api/assistant/stream', json={
            'question': '再举个例子。', 'documents': [],
            'history': [
                {'role': 'user', 'content': 'Python列表推导式是什么？'},
                {'role': 'assistant', 'content': '它是创建列表的简洁语法。', 'intent': '一般咨询'},
            ],
        })
        switched = client.post('/api/assistant/stream', json={
            'question': 'Python列表推导式是什么？', 'documents': [],
            'history': [
                {'role': 'user', 'content': '我需要申请理赔。'},
                {'role': 'assistant', 'content': '请先报案。', 'intent': '理赔报案'},
            ],
        })
        assert '一般咨询' in inherited.text
        assert '一般咨询' in switched.text
        assert all('通用智能助手' in prompt for prompt in model.stream_system_prompts[-2:])
