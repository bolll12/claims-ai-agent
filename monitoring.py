"""材料6.4六组Prometheus指标；标签不使用案件号，避免高基数。"""
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

REGISTRY = CollectorRegistry()
REQUESTS = Counter('claims_requests_total', '已完成HTTP理赔请求数', ['decision'], registry=REGISTRY)
ERRORS = Counter('claims_errors_total', '处理异常数', ['kind'], registry=REGISTRY)
LATENCY = Histogram('claims_latency_seconds', '理赔处理耗时', buckets=(.1, .5, 1, 2, 5, 10, 30, 120), registry=REGISTRY)
CONFIDENCE = Histogram('claims_confidence', '已计算置信度分布', buckets=(.1, .3, .5, .7, .9, 1), registry=REGISTRY)
TOKENS = Counter('claims_tokens_total', '服务端实际报告token用量', ['kind'], registry=REGISTRY)
ITERATIONS = Histogram('claims_iterations', '每案专家及补充轮次', buckets=(1, 2, 3, 4, 6, 8, 12), registry=REGISTRY)
CACHE = Counter('claims_cache_total', '缓存访问结果', ['result'], registry=REGISTRY)


def metrics() -> bytes:
    """导出本进程累计指标，不推测未知的服务端token数量。"""
    return generate_latest(REGISTRY)
