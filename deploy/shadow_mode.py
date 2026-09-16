"""材料6.5.3只读影子对拍；本模块不执行Agent，也不执行赔付或通知。

传入两条链路已经产生的审核建议，避免影子链路再次触发写操作。
"""
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def _amount(value: Any) -> Decimal:
    """比较前校验金额，缺失金额不默认为0。"""
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0:
            raise ValueError('影子对拍金额必须为有限非负数')
        return result
    except InvalidOperation as exc:
        raise ValueError('影子对拍缺少合法金额') from exc


def shadow_compare(agent: dict[str, Any], legacy: dict[str, Any], claim_id: str,
                   *, csv_path: Path | None = None) -> bool:
    """严格比较决定和分位金额，CSV仅记录标识与差异，不保存原始材料。"""
    if not claim_id.strip():
        raise ValueError('报案号不能为空')
    for result in (agent, legacy):
        if result.get('claim_id', claim_id) != claim_id or not result.get('decision'):
            raise ValueError('影子结果缺少决定或报案号不匹配')
    amount_agent, amount_legacy = _amount(agent['amount']), _amount(legacy['amount'])
    same = agent['decision'] == legacy['decision'] and amount_agent == amount_legacy
    if csv_path is not None:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        # 每个批次使用独立文件；并发汇总交由上层队列单写者执行。
        new_file = not csv_path.exists() or csv_path.stat().st_size == 0
        with csv_path.open('a', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            if new_file:
                writer.writerow(['claim_id', 'same_decision', 'same_amount', 'agreement'])
            # CSV注入防护：不把模型文本或公式直接写入表格。
            safe_id = "'" + claim_id if claim_id.lstrip().startswith(('=', '+', '-', '@')) else claim_id
            writer.writerow([safe_id, agent['decision'] == legacy['decision'], amount_agent == amount_legacy, same])
    return same
