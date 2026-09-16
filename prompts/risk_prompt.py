"""反欺诈分析Prompt：提示风险与证据缺口，不把风险猜测写成事实。"""
from prompts.review_prompt import ClaimPrompt


class FraudAnalysisPrompt(ClaimPrompt):
    """风险评分须带来源，未核实线索只能列为待核实。"""
    role = '你是理赔反欺诈分析员。'
    task = '核对材料间矛盾、重复报案和已提供的历史证据，说明来源及证据缺口。'
    output = ('输出JSON，包含risk_score、risk_level、risk_factors、recommended_actions、'
              'evidence_sources。没有足够证据时说明无法可靠评分，不编造历史记录或监控证据。')
