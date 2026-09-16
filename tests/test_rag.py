"""RAG离线测试：实际文档解析、融合、引用验证和评测指标。"""
import asyncio
import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage
from tools.rag_retrieval import load_documents, HybridRetriever, PolicyClauseRAG, retrieval_metrics


def corpus():
    return [Document(page_content='保险条款车辆损失保障', metadata={'doc_id': 'a', 'insurance_type': 'auto', 'version': '1'}),
            Document(page_content='医疗住院费用', metadata={'doc_id': 'b', 'insurance_type': 'health', 'version': '1'})]


def test_load_split_and_metadata(tmp_path):
    path = tmp_path/'policy.txt'
    path.write_text('第一条 车辆损失\n' + '保险责任。'*200, encoding='utf-8')
    chunks = load_documents(path, insurance_type='auto', version='1', effective_date='2026-01-01')
    assert len(chunks) > 1 and all(len(doc.page_content) <= 500 for doc in chunks)
    assert all(doc.metadata['version'] == '1' and doc.metadata['source'] == str(path) for doc in chunks)
    assert len({doc.metadata['doc_id'] for doc in chunks}) == len(chunks)


def test_hybrid_filters_and_metrics():
    retriever = HybridRetriever(lambda query, k: corpus(), corpus())
    results = retriever.retrieve('车辆保障', insurance_type='auto')
    assert [doc.metadata['doc_id'] for doc in results] == ['a']
    assert retrieval_metrics(['x', 'a'], {'a', 'b'}) == {'recall_at_k': .5, 'mrr': .5}


def test_rag_rejects_fabricated_citation_and_no_hit_skips_model():
    class Model:
        def bind(self, **kwargs): return self
        async def ainvoke(self, messages):
            return AIMessage(content='{"answer":"这是回答","citation_ids":["invented"]}')
    rag = PolicyClauseRAG(HybridRetriever(lambda q, k: corpus(), corpus()), Model())
    with pytest.raises(ValueError, match='有效引用'):
        asyncio.run(rag.ask('车辆', insurance_type='auto'))
    result = asyncio.run(rag.ask('车辆', insurance_type='life'))
    assert result['requires_manual_review'] and result['citations'] == []
