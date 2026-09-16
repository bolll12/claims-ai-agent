"""材料模块03/05的模板、契约与结构化输出回归。"""
import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from demos.module04_demo import build_prompt_examples
from models.parsers import ManualReviewRequired, SafePydanticOutputParser, migrate_v1_to_v2
from models.schemas import StructuredClaimResult
from prompts import ClaimReviewPrompt, PromptRegistry


def valid_result():
    return dict(claim_id='CLM-2026-001', decision='受理', liability_ratio=1,
                confidence_score=0.9, estimated_amount='100.00',
                reason='这是教学用审核理由，真实案件需要核实保单与事故材料后才能决定。', next_action='人工核实')


@pytest.mark.parametrize('changes', [
    {'claim_id': 'bad'}, {'confidence_score': float('nan')}, {'confidence_score': 1.1},
    {'estimated_amount': '1.001'}, {'estimated_amount': 'Infinity'},
    {'decision': '不受理'}, {'unknown': '不可接受'},
])
def test_contract_rejects_invalid_or_contradictory_output(changes):
    with pytest.raises(ValidationError):
        StructuredClaimResult(**(valid_result() | changes))


def test_decimal_and_rejection_without_payment():
    assert StructuredClaimResult(**valid_result()).estimated_amount == Decimal('100.00')
    assert StructuredClaimResult(**(valid_result() | {'decision': '不受理', 'estimated_amount': None}))


def test_repair_feedback_and_bounded_manual_fallback():
    calls = []
    def repair(original, candidate, error):
        calls.append((original, candidate, error))
        return '{}'
    parser = SafePydanticOutputParser(StructuredClaimResult, repair)
    result = parser.parse('bad', claim_id='CLM-2026-001', original_prompt='原始问题')
    assert isinstance(result, ManualReviewRequired)
    assert result.attempts == 3 and len(calls) == 2
    assert calls[0][0] == '原始问题' and calls[0][2]


def test_repair_correct_output_and_wrong_case_rejected():
    parser = SafePydanticOutputParser(StructuredClaimResult, lambda *args: json.dumps(valid_result()))
    assert isinstance(parser.parse('bad', claim_id='CLM-2026-001', original_prompt='请求'), StructuredClaimResult)
    assert isinstance(parser.parse(json.dumps(valid_result()), claim_id='CLM-2026-999', original_prompt='请求'), ManualReviewRequired)


def test_migration_is_explicit_and_detects_conflicts():
    data = valid_result()
    data['confidence'] = data.pop('confidence_score')
    data['amount'] = data.pop('estimated_amount')
    result = migrate_v1_to_v2(data)
    assert result['schema_version'] == '2'
    with pytest.raises(ValueError):
        migrate_v1_to_v2(data | {'confidence_score': 0.1})


def test_all_six_prompt_types_render():
    prompts = build_prompt_examples()
    assert len(prompts) == 6
    values = dict(policy_type='车险', input='报案', policy_info='待核实', claim_text='案件',
                  question='需哪些材料', history=[], chat_history=[])
    for prompt in prompts.values():
        messages = prompt.invoke(values).to_messages()
        assert messages[0].type == 'system' and messages[-1].type == 'human'


def test_review_variables_json_braces_and_dynamic_rules():
    prompt = ClaimReviewPrompt()
    with pytest.raises(ValueError, match='policy_info'):
        prompt.format({'input': '案件'})
    value = prompt.format({'input': '案件', 'policy_info': '{"status":"待核实"}', 'exclusions': '未提供'}, rules=['仅引用已核实数据'])
    assert '仅引用已核实数据' in value.to_messages()[0].content
    assert '{"status":"待核实"}' in value.to_messages()[-1].content


def test_version_fallback_is_exact_and_immutable(tmp_path):
    registry = PromptRegistry(tmp_path)
    registry.save('review', '1.0.0', [('system', '角色'), ('human', '{input}')])
    def unavailable(*args):
        raise ConnectionError('offline')
    assert registry.load('review', '1.0.0', unavailable).invoke({'input': '案件'})
    with pytest.raises(FileExistsError):
        registry.save('review', '1.0.0', [('human', '覆盖')])
    with pytest.raises(ValueError):
        registry.load('review', '1.0.0', lambda *args: {'name': 'review', 'version': '2.0.0'})
    with pytest.raises(ValueError):
        registry.load('../secret', '1.0.0')
