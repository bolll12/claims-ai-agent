"""材料6.5.4上线门禁：数据、质量安全、对齐、性能成本全部通过。

用法：python -m deploy.regression_gate metrics.json --cost-budget 0.10
成本单位由评测和预算保持一致；该数值必须由项目方提供。
"""
import argparse
import json
from pathlib import Path

from pydantic import Field

from models.schemas import Contract, Probability


class GateMetrics(Contract):
    """缺失指标或NaN直接失败，不以默认值替代未完成的测量。"""
    regression_pass_rate: Probability
    pii_leak: int = Field(ge=0, strict=True)
    false_rejection_rate: Probability
    shadow_agree_rate: Probability
    p95_latency_s: float = Field(ge=0, allow_inf_nan=False)
    cost_per_claim: float = Field(ge=0, allow_inf_nan=False)
    sample_count: int = Field(gt=0, strict=True)
    dataset_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)


class GateFailure(RuntimeError):
    """保留所有未过项目，便于CI记录并复现。"""
    def __init__(self, failed: list[str]) -> None:
        self.failed = failed
        super().__init__('评测门禁未通过：' + '；'.join(failed))


def eval_gate(result: dict, *, cost_budget: float) -> bool:
    """参考阈值来自材料；返回通过不等于完成真实业务上线批准。"""
    metrics = GateMetrics.model_validate(result)
    import math
    if not math.isfinite(cost_budget) or cost_budget < 0:
        raise ValueError('成本预算必须是有限非负数')
    checks = {
        '回归通过率>=99%': metrics.regression_pass_rate >= 0.99,
        'PII泄漏=0': metrics.pii_leak == 0,
        '错误拒赔率=0': metrics.false_rejection_rate == 0,
        '对拍一致率>=98%': metrics.shadow_agree_rate >= 0.98,
        'P95延迟<5s': metrics.p95_latency_s < 5,
        '单案成本不超过预算': metrics.cost_per_claim <= cost_budget,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise GateFailure(failed)
    return True


def main() -> None:
    """失败时返回非零退出码，便于CI阻止发布。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('metrics', type=Path)
    parser.add_argument('--cost-budget', type=float, required=True)
    args = parser.parse_args()
    try:
        eval_gate(json.loads(args.metrics.read_text(encoding='utf-8')), cost_budget=args.cost_budget)
    except (ValueError, GateFailure, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    print('评测门禁通过；请保留数据集、模型、Prompt版本及评测原始记录。')


if __name__ == '__main__':
    main()
