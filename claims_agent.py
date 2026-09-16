"""材料第六章端到端入口：复用分层实现，不维护第二套业务逻辑。

python claims_agent.py --demo：显式离线教学样例。
真实模式须提供本地模型、保单和证据核验适配器。
"""
import argparse
import asyncio
import json
from typing import Any

from adapters.business import DemoBackend
from agents.claim_agent import WorkflowServices, build_claim_graph
from agents.confidence import ClaimConfidenceSystem
from agents.middleware_audit import mask_pii


class DemoServices(WorkflowServices):
    """纯合成固定案例，不请求真实LLM；所有输出仅验证工作流。"""
    def __init__(self, scenario: str = 'normal') -> None:
        super().__init__(DemoBackend())
        self.scenario = scenario

    async def verify(self, claim: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
        return {'coverage_verified': self.scenario == 'normal', 'demo': True,
                'source': '合成核验结果，非真实案件证据'}

    async def expert(self, role: str, claim: dict[str, Any], policy: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        return {'expert': role, 'recommendation': 'accept', 'confidence': .95,
                'risk_score': .8 if self.scenario == 'risk' else .1,
                'missing_information': [], 'demo': True, 'source': '合成专家结果，未调用模型'}


async def process_claim(claim_id: str, claim_text: str, policy_id: str | None = None,
                        amount: float | None = None, *, services: WorkflowServices | None = None) -> dict[str, Any]:
    """真实模式不编造分类logits或贝叶斯证据，置信度来自明确专家输出。"""
    graph = build_claim_graph(services)
    config = {'configurable': {'thread_id': claim_id}, 'recursion_limit': 40, 'max_concurrency': 3}
    result = await graph.ainvoke({'claim_id': claim_id, 'claim_data': mask_pii({'claim_id': claim_id, 'description': claim_text,
        'policy_id': policy_id, 'amount': amount}), 'expert_results': [], 'rounds': 0}, config=config)
    snapshot = await graph.aget_state(config)
    return {'state': result, 'pending_nodes': list(snapshot.next), 'demo': isinstance(services, DemoServices)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--scenario', choices=['normal', 'risk', 'missing'], default='normal')
    parser.add_argument('--claim-id', default='CLM-2026-001')
    parser.add_argument('--policy-id')
    parser.add_argument('--text', default='教学示例：停车场车辆刮擦，材料需要核实。')
    args = parser.parse_args()
    service = DemoServices(args.scenario) if args.demo else None
    policy = 'POL-2024-001' if args.demo and args.scenario != 'missing' else args.policy_id
    result = asyncio.run(process_claim(args.claim_id, args.text, policy, services=service))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


__all__ = ['process_claim', 'DemoServices', 'ClaimConfidenceSystem', 'build_claim_graph']
if __name__ == '__main__':
    main()
