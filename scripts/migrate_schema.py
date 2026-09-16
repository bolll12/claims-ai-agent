"""JSONL审核结果v1→v2；先完整校验再输出，不覆盖原始文件。"""
import argparse
import json
from pathlib import Path
from models.parsers import migrate_v1_to_v2


def migrate(source: Path, destination: Path) -> int:
    results = [migrate_v1_to_v2(json.loads(line)) for line in source.read_text(encoding='utf-8').splitlines() if line.strip()]
    with destination.open('x', encoding='utf-8') as output:
        output.write('\n'.join(json.dumps(result, ensure_ascii=False) for result in results) + '\n')
    return len(results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(f'已迁移{migrate(args.source, args.destination)}条')
