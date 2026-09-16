"""理赔场景提示词与版本管理公共接口。"""
from prompts.review_prompt import ClaimIntakePrompt, ClaimReviewPrompt, ClaimServicePrompt, PromptRegistry
from prompts.risk_prompt import FraudAnalysisPrompt

__all__ = ['ClaimIntakePrompt', 'ClaimReviewPrompt', 'ClaimServicePrompt', 'FraudAnalysisPrompt', 'PromptRegistry']
