"""同样本比较三种本地解析器；模型结构化模式需真实模型另行测量。"""
import json
import time
from langchain_core.output_parsers import JsonOutputParser, PydanticOutputParser, StrOutputParser
from models.schemas import StructuredClaimResult


def benchmark(samples: list[str], repeats: int = 100) -> dict:
    if not samples or repeats < 1:
        raise ValueError('样本和重复次数不能为空')
    result = {}
    for name, parser in [('text', StrOutputParser()), ('json', JsonOutputParser()), ('pydantic', PydanticOutputParser(pydantic_object=StructuredClaimResult))]:
        success = 0
        start = time.perf_counter()
        for _ in range(repeats):
            for sample in samples:
                try:
                    parser.invoke(sample)
                    success += 1
                except Exception:
                    pass
        count = len(samples) * repeats
        result[name] = {'parse_success_rate': success / count, 'mean_latency_ms': (time.perf_counter() - start) * 1000 / count, 'samples': count}
    return result


if __name__ == '__main__':
    data = {'claim_id': 'CLM-2026-001', 'decision': '人工复核', 'liability_ratio': 0,
            'confidence_score': .5, 'reason': '仅用于教学的合成案件，缺少核实材料需要人工复核，不能自动赔付。', 'next_action': '补充材料'}
    print(json.dumps(benchmark([json.dumps(data, ensure_ascii=False), 'not-json']), ensure_ascii=False, indent=2))
