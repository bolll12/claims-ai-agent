"""置信度算法的边界、数值稳定性及真实拟合回归测试。"""
import numpy as np
import pytest

from agents.confidence import (
    BayesianConfidence, MultiModelConfidence, TemperatureScaler,
    calibration_curve, entropy_confidence, softmax_confidence, softmax_probabilities,
)


def test_softmax_stable_and_translation_invariant():
    expected = softmax_probabilities([2.5, 0.3, -1])
    actual = softmax_probabilities([10002.5, 10000.3, 9999])
    assert actual == pytest.approx(expected)
    assert actual.sum() == pytest.approx(1)
    assert softmax_confidence([2.5, 0.3, -1])[0] == '受理'


@pytest.mark.parametrize('values', [[], [1, 2], [1, 2, float('nan')], [float('inf'), 1, 2]])
def test_invalid_logits(values):
    with pytest.raises(ValueError):
        softmax_confidence(values)


def test_entropy_extremes():
    assert entropy_confidence([1, 0, 0]) == 1
    assert entropy_confidence([1/3] * 3) == pytest.approx(0, abs=1e-15)
    with pytest.raises(ValueError):
        entropy_confidence([0.2, 0.2])


def test_bayesian_exact_update_isolation_and_atomic_failure():
    first, second = BayesianConfidence(), BayesianConfidence()
    assert first.update('证据A', 0.6, 0.15) == pytest.approx(0.03 / 0.1725)
    assert second.p_fraud == 0.05
    original = first.get_confidence()
    original['evidence_log'].clear()
    assert len(first.evidence_log) == 1
    for name, a, b in [('证据A', 0.6, 0.15), ('无定义', 0, 0), ('越界', 2, 0.1)]:
        with pytest.raises(ValueError):
            first.update(name, a, b)
    assert len(first.evidence_log) == 1


def test_fusion_checks_and_dynamic_boundaries():
    with pytest.raises(ValueError):
        MultiModelConfidence(-0.1, 0.9, 0.2)
    with pytest.raises(ValueError):
        MultiModelConfidence(0.4, 0.4, 0.4)
    model = MultiModelConfidence()
    assert model.calculate(0.9, 0.9, 0.9)['final_confidence'] == pytest.approx(0.9)
    assert model.calculate(1, 0, 0)['final_confidence'] < 0.4
    assert model.calculate(1, 1, 1, {'amount': 4999})['weights']['classifier'] == 0.5
    assert model.calculate(1, 1, 1, {'amount': 5000})['weights']['classifier'] == 0.4
    assert model.calculate(1, 1, 1, {'amount': 50001})['weights']['llm'] == 0.5


def test_ece_counts_probability_one_and_is_weighted():
    result = calibration_curve([[1, 0], [0, 1], [0.6, 0.4]], [0, 0, 0])
    assert sum(result['bin_counts']) == 3
    assert result['bin_counts'][-1] == 2
    assert result['ECE'] == pytest.approx((1 + 0.4) / 3)
    with pytest.raises(ValueError):
        calibration_curve([], [])


def test_temperature_real_fit_improves_nll_and_preserves_class():
    # 合成验证集：预测自信但仅50%正确，用于检验优化器，不是业务评测。
    logits = np.array([[10., 0., 0.]] * 12)
    labels = np.array([0] * 6 + [1] * 3 + [2] * 3)
    model = TemperatureScaler().fit(logits, labels)
    assert model.fitted and model.temperature > 1
    assert model.nll_after < model.nll_before
    probabilities = model.transform(logits)
    assert probabilities.sum(axis=1) == pytest.approx(np.ones(12))
    assert np.all(probabilities.argmax(axis=1) == logits.argmax(axis=1))
    assert probabilities[0, 0] == pytest.approx(0.5, abs=1e-3)


def test_temperature_extreme_logits_and_invalid_targets():
    model = TemperatureScaler()
    assert model.transform([[1e300, 0, -1e300]])[0] == pytest.approx([1, 0, 0])
    with pytest.raises(ValueError):
        model.fit([[1, 2, 3]], [3])
    with pytest.raises(ValueError):
        model.fit([[1, 2, 3]], [1.5])
