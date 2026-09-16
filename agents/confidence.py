"""第四章置信度算法；参数来自教学示例，不直接批准赔付或拒赔。

融合前各输入须针对同一个目标事件；LLM 自报分数不等于校准概率。
"""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

FloatArray = NDArray[np.float64]
CATEGORIES = ("受理", "不受理", "调查")


def _probability(value: float, name: str) -> float:
    """校验概率范围及有限性。"""
    number = float(value)
    if not np.isfinite(number) or not 0 <= number <= 1:
        raise ValueError(f"{name} 必须是 [0, 1] 内的有限数值")
    return number


def _matrix(values: ArrayLike) -> FloatArray:
    """校验非空的样本×类别矩阵。"""
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 2 or array.shape[0] == 0 or array.shape[1] < 2:
        raise ValueError("输入形状必须为 (N, C)，N >= 1 且 C >= 2")
    if not np.all(np.isfinite(array)):
        raise ValueError("输入不得包含 NaN 或无穷值")
    return array


def _labels(values: ArrayLike, shape: tuple[int, ...]) -> NDArray[np.int64]:
    """校验真实标签与样本逐一对应。"""
    labels = np.asarray(values)
    if labels.shape != (shape[0],) or labels.dtype.kind not in "iu":
        raise ValueError("labels 必须是长度为 N 的整数标签向量")
    if np.any(labels < 0) or np.any(labels >= shape[1]):
        raise ValueError("labels 超出类别索引范围")
    return labels.astype(np.int64)


def softmax_probabilities(logits: Sequence[float]) -> FloatArray:
    """使用数值稳定 Softmax 返回受理、不受理、调查三个类别概率。"""
    array = np.asarray(logits, dtype=np.float64)
    if array.shape != (3,) or not np.all(np.isfinite(array)):
        raise ValueError("理赔 logits 必须包含三个有限分数")
    with np.errstate(over="ignore"):
        scores = np.exp(array - np.max(array))
    return scores / scores.sum()


def softmax_confidence(logits: Sequence[float]) -> tuple[str, float]:
    """返回最高概率类别及概率；并列时按类别定义顺序选择。"""
    probabilities = softmax_probabilities(logits)
    index = int(np.argmax(probabilities))
    return CATEGORIES[index], float(probabilities[index])


def entropy_confidence(probabilities: Sequence[float]) -> float:
    """计算 1-H(p)/log(C)，确定分布为 1，均匀分布为 0。"""
    array = np.asarray(probabilities, dtype=np.float64)
    if array.ndim != 1 or array.size < 2:
        raise ValueError("概率向量至少需要两个类别")
    if not np.all(np.isfinite(array)) or np.any(array < 0) or np.any(array > 1):
        raise ValueError("概率必须是 [0, 1] 内的有限值")
    if not np.isclose(array.sum(), 1.0, rtol=0, atol=1e-8):
        raise ValueError("概率总和必须为 1")
    positive = array[array > 0]  # 0*log(0) 按极限定义为 0。
    entropy = -float(np.sum(positive * np.log(positive)))
    return float(np.clip(1 - entropy / np.log(array.size), 0, 1))


class BayesianConfidence:
    """单案贝叶斯更新；调用方验证证据来源和条件独立假设。

    0.05 为培训示例，不代表实际欺诈率。每案创建新实例。
    相同名称证据不重复计数；相关证据需先用联合似然建模。
    """

    def __init__(self, prior_fraud: float = 0.05) -> None:
        self.p_fraud = _probability(prior_fraud, "prior_fraud")
        self._evidence_log: list[dict[str, Any]] = []

    @property
    def evidence_log(self) -> list[dict[str, Any]]:
        """返回副本，防止外部改写证据日志。"""
        return deepcopy(self._evidence_log)

    def update(self, evidence_name: str, likelihood_if_fraud: float,
               likelihood_if_normal: float) -> float:
        """使用调用方提供的条件似然更新后验，不编造证据。"""
        name = evidence_name.strip()
        if not name or any(row["evidence"] == name for row in self._evidence_log):
            raise ValueError("证据名称必须非空且不得重复")
        fraud = _probability(likelihood_if_fraud, "likelihood_if_fraud")
        normal = _probability(likelihood_if_normal, "likelihood_if_normal")
        prior = self.p_fraud
        denominator = fraud * prior + normal * (1 - prior)
        if denominator == 0:
            raise ValueError("证据总概率为 0，后验无定义")
        posterior = fraud * prior / denominator
        self._evidence_log.append({
            "evidence": name, "prior": prior, "posterior": posterior,
            "change": posterior - prior, "likelihood_if_fraud": fraud,
            "likelihood_if_normal": normal,
        })
        self.p_fraud = posterior
        return posterior

    def get_confidence(self) -> dict[str, Any]:
        """保留材料字段；confidence 仅表示非欺诈后验。"""
        return {
            "fraud_probability": self.p_fraud, "normal_probability": 1 - self.p_fraud,
            "confidence": 1 - self.p_fraud, "evidence_count": len(self._evidence_log),
            "evidence_log": self.evidence_log,
        }


class MultiModelConfidence:
    """教学融合评分，三路概率必须针对同一事件。

    默认权重来自第四章代码，非经过业务验证的权重。
    标准差惩罚为启发式规则，不保证融合分数具有统计校准性质。
    """

    def __init__(self, weight_classifier: float = 0.4, weight_llm: float = 0.4,
                 weight_rule: float = 0.2) -> None:
        self.weights = dict(zip(
            ("classifier", "llm", "rule"),
            (_probability(weight_classifier, "weight_classifier"),
             _probability(weight_llm, "weight_llm"),
             _probability(weight_rule, "weight_rule")),
        ))
        if not np.isclose(sum(self.weights.values()), 1, rtol=0, atol=1e-8):
            raise ValueError("融合权重之和必须为 1")

    def calculate(self, prob_classifier: float, prob_llm: float, prob_rule: float,
                  claim_data: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """按材料金额档位调整权重；缺失金额时保留配置值。"""
        scores = np.array([
            _probability(prob_classifier, "prob_classifier"),
            _probability(prob_llm, "prob_llm"), _probability(prob_rule, "prob_rule"),
        ])
        weights = dict(self.weights)
        if claim_data is not None and "amount" in claim_data:
            amount = float(claim_data["amount"])
            if not np.isfinite(amount) or amount < 0:
                raise ValueError("案件金额必须为有限的非负数")
            if amount < 5000:
                weights = {"classifier": 0.5, "llm": 0.3, "rule": 0.2}
            elif amount > 50000:
                weights = {"classifier": 0.2, "llm": 0.5, "rule": 0.3}
        fused = float(np.dot(scores, list(weights.values())))
        std_dev = float(np.std(scores))
        penalty = max(0.0, 1 - 2 * std_dev)
        return {
            "final_confidence": fused * penalty, "fused_confidence": fused,
            "consistency_penalty": penalty,
            "model_scores": dict(zip(("classifier", "llm", "rule_engine"), scores.tolist())),
            "weights": weights, "std_dev": std_dev,
        }


class TemperatureScaler:
    """在带真实标签的独立验证集上最小化 NLL，学习正温度参数。"""

    def __init__(self) -> None:
        self.temperature = 1.0
        self.fitted = False
        self.nll_before: float | None = None
        self.nll_after: float | None = None

    def fit(self, logits: ArrayLike, labels: ArrayLike) -> "TemperatureScaler":
        """拟合 log(T)，用边界避免负温度或无限温度。"""
        from scipy.optimize import minimize
        from scipy.special import logsumexp

        values = _matrix(logits)
        targets = _labels(labels, values.shape)
        with np.errstate(over="raise", invalid="raise"):
            try:
                centered = values - values.max(axis=1, keepdims=True)
            except FloatingPointError as exc:
                raise ValueError("logits 动态范围超过浮点数范围") from exc

        def loss(log_temperature: FloatArray) -> float:
            scaled = centered / np.exp(log_temperature[0])
            return float(np.mean(
                logsumexp(scaled, axis=1) - scaled[np.arange(len(targets)), targets]
            ))

        before = loss(np.array([0.0]))
        result = minimize(loss, x0=np.array([0.0]), method="L-BFGS-B", bounds=[(-6, 6)])
        if not result.success or not np.isfinite(result.fun):
            raise RuntimeError(f"温度拟合失败：{result.message}")
        if float(result.fun) > before + 1e-8:
            raise RuntimeError("拟合后 NLL 增大，保留原有温度")
        self.temperature = float(np.exp(result.x[0]))
        self.nll_before, self.nll_after = before, float(result.fun)
        self.fitted = True
        return self

    def transform(self, logits: ArrayLike) -> FloatArray:
        """返回每行和为 1 的概率；未拟合时等价于 Softmax。"""
        values = _matrix(logits)
        if not np.isfinite(self.temperature) or self.temperature <= 0:
            raise ValueError("温度必须为有限正数")
        with np.errstate(over="ignore"):
            scaled = (values - values.max(axis=1, keepdims=True)) / self.temperature
        scores = np.exp(scaled)
        return scores / scores.sum(axis=1, keepdims=True)


def calibration_curve(probs: ArrayLike, labels: ArrayLike, n_bins: int = 10) -> dict[str, Any]:
    """等宽分箱校准曲线和 ECE；最后一个桶包含置信度 1。"""
    values = _matrix(probs)
    targets = _labels(labels, values.shape)
    if isinstance(n_bins, bool) or not isinstance(n_bins, int) or n_bins < 1:
        raise ValueError("n_bins 必须为正整数")
    if np.any(values < 0) or np.any(values > 1) or not np.allclose(
        values.sum(axis=1), 1, rtol=0, atol=1e-8
    ):
        raise ValueError("每行必须是合法概率分布")
    centers = (np.arange(n_bins) + 0.5) / n_bins
    confidences = values.max(axis=1)
    correct = values.argmax(axis=1) == targets
    bucket_ids = np.minimum((confidences * n_bins).astype(int), n_bins - 1)
    counts: list[int] = []
    accuracy: list[float] = []
    confidence: list[float] = []
    for bucket in range(n_bins):
        mask = bucket_ids == bucket
        count = int(mask.sum())
        counts.append(count)
        accuracy.append(float(correct[mask].mean()) if count else 0.0)
        confidence.append(float(confidences[mask].mean()) if count else float(centers[bucket]))
    ece = sum(abs(a - c) * n / len(targets) for a, c, n in zip(accuracy, confidence, counts))
    return {"bin_centers": centers.tolist(), "bin_accuracy": accuracy,
            "bin_confidence": confidence, "bin_counts": counts, "ECE": float(ece)}


__all__ = ["softmax_probabilities", "softmax_confidence", "entropy_confidence",
           "BayesianConfidence", "MultiModelConfidence", "TemperatureScaler", "calibration_curve"]


class ClaimConfidenceSystem:
    """整合材料第四章方法；每次评估重置证据，避免跨案泄漏。

    综合值为教学评分而非经验证的赔付概率。只有同一受理目标事件的
    分类/LLM/规则概率可融合；没有真实分类logits不得编造替代输入。
    """
    def __init__(self, prior_fraud: float = .05) -> None:
        self.prior_fraud = _probability(prior_fraud, 'prior_fraud')
        self.fusion = MultiModelConfidence()
        self.temperature_scaler = TemperatureScaler()

    def evaluate(self, claim_data: dict[str, Any], classifier_logits: Sequence[float],
                 llm_confidence: float, rule_result: float,
                 evidence_list: list[dict[str, Any]]) -> dict[str, Any]:
        bayesian = BayesianConfidence(self.prior_fraud)
        probabilities = softmax_probabilities(classifier_logits)
        entropy = entropy_confidence(probabilities)
        for evidence in evidence_list:
            bayesian.update(evidence['name'], evidence['p_if_fraud'], evidence['p_if_normal'])
        # 统一成“受理”的概率，不将“不受理”的最大概率拿来加分。
        fusion = self.fusion.calculate(float(probabilities[0]), llm_confidence, rule_result, claim_data)
        calibrated = float(self.temperature_scaler.transform([classifier_logits])[0, 0])
        normal = 1 - bayesian.p_fraud
        score = .35 * fusion['final_confidence'] + .25 * calibrated + .2 * normal + .2 * entropy
        # 低置信度不拒赔；高分也只形成建议，不直接付款。
        decision, level = ('建议受理', 'P0') if score > .9 else (
            ('快速复核', 'P1') if score > .7 else ('人工复核', 'P2') if score > .5 else ('调查', 'P3'))
        if not claim_data.get('evidence_complete', False) or float(claim_data.get('amount', 0)) > 50000:
            decision, level = '人工复核', 'P2'
        return {'final_confidence': score, 'decision': decision, 'level': level,
                'calibrated': self.temperature_scaler.fitted,
                'score_kind': '教学启发式评分，须经真实案件回测',
                'components': {'softmax': float(probabilities[0]), 'entropy': entropy,
                               'bayesian': normal, 'fusion': fusion, 'calibrated': calibrated},
                'bayesian_details': bayesian.get_confidence(),
                'risk_assessment': {'fraud_probability': bayesian.p_fraud, 'evidence_count': len(evidence_list)}}


__all__.append('ClaimConfidenceSystem')
