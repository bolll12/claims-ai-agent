"""理赔工作台页面、单证识别和流式问答测试。"""

import json
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app import create_app


class FakeWorkbenchModel:
    """只验证应用协议，不连接外部推理服务。"""

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        if '意图分类器' in messages[0].content:
            return AIMessage(content=json.dumps({
                'intent': '材料审核', 'confidence': 0.93,
            }, ensure_ascii=False))
        return AIMessage(content=json.dumps({
            'document_type': '医疗费用发票',
            'summary': '合成测试发票，仅用于验证接口。',
            'fields': {'金额': '128.00'},
            'confidence': 0.96,
            'warnings': [],
        }, ensure_ascii=False))

    async def astream(self, messages: list[Any]):
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
