"""LangFuse v2与主项目0.3兼容回调；仅在显式开启后初始化。"""
from typing import Any
from agents.middleware_audit import TokenUsageCounter, mask_pii
from settings import Settings


def tracing_config(claim_id: str, settings: Settings | None = None) -> tuple[dict[str, Any], Any]:
    cfg = settings or Settings()
    usage = TokenUsageCounter()
    callbacks: list[Any] = [usage]
    handler = None
    if cfg.langfuse_enabled:
        from langfuse.callback import CallbackHandler
        handler = CallbackHandler(public_key=cfg.langfuse_public_key,
            secret_key=cfg.langfuse_secret_key.get_secret_value(), host=cfg.langfuse_host,
            session_id=claim_id, trace_name='claims-review', metadata={'claim_id': claim_id, 'app': 'claims-agent'},
            mask=mask_pii, enabled=True)
        callbacks.append(handler)
    return {'callbacks': callbacks, 'metadata': {'claim_id': claim_id}, 'run_name': 'claims-review',
            'configurable': {'thread_id': claim_id}, 'recursion_limit': 40, 'max_concurrency': 3}, handler
