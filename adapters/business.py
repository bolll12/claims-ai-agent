"""真实与演示业务后端：示例结果明确标记，真实接口未配置则失败。"""
from collections.abc import Callable
from typing import Any

from adapters.legacy_adapter import CoreSystemAdapter


class BusinessBackend:
    """组织内适配器注册表；不猜测材料未提供的医疗/通知/支付协议。"""
    demo = False

    def __init__(self, adapters: dict[str, Callable[..., dict[str, Any]]] | None = None) -> None:
        self.adapters = adapters or {}
        self._core: CoreSystemAdapter | None = None

    def call(self, action: str, **parameters: Any) -> dict[str, Any]:
        if action in self.adapters:
            return self.adapters[action](**parameters)
        if action == 'query_policy':
            if self._core is None:
                self._core = CoreSystemAdapter.from_env()
            return self._core.query_policy(parameters['policy_id']).model_dump(mode='json')
        raise RuntimeError(f'business_adapter_not_configured:{action}')


class DemoBackend(BusinessBackend):
    """材料固定案例仅在显式demo模式可用，未知案件不返回万能有效保单。"""
    demo = True

    def call(self, action: str, **parameters: Any) -> dict[str, Any]:
        result: dict[str, Any]
        if action == 'query_policy':
            if parameters['policy_id'] != 'POL-2024-001':
                raise ValueError('演示数据中没有该保单')
            result = {'policy_id': 'POL-2024-001', 'policy_type': '机动车商业险',
                      'coverage': '500000.00', 'deductible': '500.00', 'status': '有效'}
        elif action == 'calculate_claim_amount':
            prices = {'轻微': 500, '中度': 2000, '重度': 5000}
            result = {'estimated_amount': str(prices[parameters['severity']]), 'currency': 'CNY',
                      'basis': '培训材料按严重程度的示例价格，非真实车型定损'}
        elif action == 'calculate_liability':
            rules = {('追尾', '对方'): 0., ('追尾', '己方'): 1., ('变道', '对方'): 0., ('变道', '双方'): .5}
            key = (parameters['accident_type'], parameters['violation_side'])
            if not parameters['has_evidence'] or key not in rules:
                return {'demo': True, 'source': '教学规则', 'requires_manual_review': True, 'our_ratio': None}
            result = {'our_ratio': rules[key], 'other_ratio': 1 - rules[key]}
        elif action == 'query_claim_history':
            result = {'records': [], 'message': '合成空历史，不代表真实投保人无历史理赔'}
        elif action == 'verify_insurance_coverage':
            result = {'covered': None, 'requires_manual_review': True, 'message': '未查询真实医保系统'}
        elif action == 'search_policy_clause':
            result = {'documents': [], 'message': '需导入适用条款后检索，演示不虚构免责条款'}
        else:
            raise RuntimeError(f'演示后端不执行外部写操作：{action}')
        return dict(result, demo=True, source='培训材料合成示例，非业务事实')
