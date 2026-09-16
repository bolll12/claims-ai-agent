"""仅显式开启时连接真实Milvus；每次使用独立临时集合并清理。"""
import hashlib
import os
import uuid
import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding
from tools.rag_retrieval import ClaimVectorStore


@pytest.mark.skipif(os.getenv('RUN_MILVUS_TESTS') != '1', reason='需要实际Milvus服务；CI infrastructure作业启用')
def test_milvus_crud():
    insurance = 'test_' + uuid.uuid4().hex[:16]
    vector = ClaimVectorStore(insurance, embeddings=DeterministicFakeEmbedding(size=16), uri=os.getenv('MILVUS_URI', 'http://127.0.0.1:19530'))
    identifier = hashlib.sha256(b'test-document').hexdigest()
    doc = Document(page_content='合成车辆条款测试', metadata={'doc_id': identifier, 'insurance_type': insurance, 'version': '1'})
    try:
        assert vector.add([doc]) == [identifier]
        found = vector.search(doc.page_content, version='1')
        assert found and found[0].metadata['doc_id'] == identifier
        vector.delete([identifier])
    finally:
        if vector.store.col is not None:
            vector.store.col.drop()
