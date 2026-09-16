"""材料指定的Deep Agents落点：只在独立环境中延迟导入官方运行时。"""
from typing import Any


def create_deep_claims_agent(**kwargs: Any) -> Any:
    try:
        from isolated_deep.runtime import create_agent
    except ImportError as exc:
        raise RuntimeError('请使用独立环境：.venv-deep/bin/python；安装isolated_deep/requirements.txt') from exc
    return create_agent(**kwargs)
