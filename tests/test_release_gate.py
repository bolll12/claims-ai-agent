"""上线门禁失败闭合，影子对拍不遗漏金额差异。"""
import pytest
from deploy.regression_gate import GateFailure, eval_gate
from deploy.shadow_mode import shadow_compare


def measured():
    return dict(regression_pass_rate=.99, pii_leak=0, false_rejection_rate=0,
                shadow_agree_rate=.98, p95_latency_s=4.9, cost_per_claim=.1,
                sample_count=100, dataset_version='test-v1', model_version='fake-v1', prompt_version='1')


def test_gate_all_dimensions():
    assert eval_gate(measured(), cost_budget=.1)
    data = measured() | dict(pii_leak=1, false_rejection_rate=.01, p95_latency_s=5, cost_per_claim=.2)
    with pytest.raises(GateFailure) as error:
        eval_gate(data, cost_budget=.1)
    assert len(error.value.failed) == 4


def test_gate_missing_measurements_and_nan_rejected():
    with pytest.raises(ValueError):
        eval_gate({}, cost_budget=.1)
    with pytest.raises(ValueError):
        eval_gate(measured() | {'p95_latency_s': float('nan')}, cost_budget=.1)


def test_shadow_amount_and_csv(tmp_path):
    result = dict(decision='受理', amount='100.00')
    assert shadow_compare(result, result, 'CLM-2026-001', csv_path=tmp_path/'comparison.csv')
    assert not shadow_compare(result, result | {'amount': '100.01'}, 'CLM-2026-001')
    with pytest.raises(ValueError):
        shadow_compare(result, result | {'amount': 'NaN'}, 'CLM-2026-001')
