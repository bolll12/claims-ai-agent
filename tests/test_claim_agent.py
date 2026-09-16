"""完整服务端测试：案件持久化、幂等、审核授权和重启恢复。"""
import asyncio
from fastapi.testclient import TestClient
from app import create_app
from claims_agent import DemoServices, process_claim
from agents.confidence import ClaimConfidenceSystem


def test_api_persists_and_resumes_across_restart(tmp_path, monkeypatch):
    monkeypatch.setenv('REVIEWER_API_KEY', 'test-only-reviewer-key')
    database = str(tmp_path/'checkpoints.db')
    payload = {'claim_id': 'CLM-2026-991', 'description': '教学报案', 'policy_id': 'POL-2024-001', 'amount': 60000}
    with TestClient(create_app(DemoServices(), database=database)) as client:
        first = client.post('/api/claims/process', json=payload)
        assert first.status_code == 200 and first.json()['phase'] == 'awaiting_review'
        assert client.post('/api/claims/process', json=payload).json() == first.json()
        assert client.post('/api/claims/process', json=payload | {'description': '覆盖'}).status_code == 409
    with TestClient(create_app(DemoServices(), database=database)) as client:
        assert client.get('/api/claims/CLM-2026-991').json()['phase'] == 'awaiting_review'
        decision = {'decision': 'reject', 'reviewer': '测试审核员', 'reason': '条款待核实'}
        route = '/api/claims/CLM-2026-991/review'
        assert client.post(route, json=decision).status_code == 403
        headers = {'X-Reviewer-Key': 'test-only-reviewer-key'}
        assert client.post(route, json=decision, headers=headers).status_code == 422
        result = client.post(route, json=decision | {'decision': 'review'}, headers=headers)
        assert result.status_code == 200 and result.json()['phase'] == 'complete'
        assert client.get('/metrics').status_code == 200


def test_supplement_and_demo_routes(tmp_path):
    with TestClient(create_app(DemoServices(), database=str(tmp_path/'db'))) as client:
        first = client.post('/api/claims/process', json={'claim_id': 'C1', 'claim_text': '合成报案'})
        assert first.json()['phase'] == 'awaiting_information'
        response = client.post('/api/claims/C1/supplement', json={'policy_id': 'POL-2024-001'})
        assert response.json()['decision'] == 'accept'
    normal = asyncio.run(process_claim('CLM-2026-001', '合成', 'POL-2024-001', services=DemoServices()))
    assert normal['demo'] and normal['state']['decision'] == 'accept'
    risk = asyncio.run(process_claim('CLM-2026-002', '合成', 'POL-2024-001', services=DemoServices('risk')))
    assert risk['state']['decision'] == 'investigate'


def test_confidence_no_cross_case_evidence_and_low_score_not_reject():
    system = ClaimConfidenceSystem()
    evidence = [{'name': '教学证据', 'p_if_fraud': .9, 'p_if_normal': .1}]
    first = system.evaluate({}, [0, 4, 1], .1, .1, evidence)
    second = system.evaluate({}, [0, 4, 1], .1, .1, [])
    assert first['risk_assessment']['evidence_count'] == 1
    assert second['risk_assessment']['fraud_probability'] == .05
    assert first['decision'] in ('人工复核', '调查')
