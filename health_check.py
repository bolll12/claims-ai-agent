"""验证HTTP存活、OpenAPI契约及理赔状态机；不调用真实模型或业务接口。"""
import argparse
import os
import time
import uuid
import httpx


def check(base_url: str, max_latency: float = 5) -> dict[str, float]:
    timings = {}
    headers = {'X-API-Key': os.getenv('CLAIMS_API_KEY', '')}
    with httpx.Client(base_url=base_url, headers=headers, timeout=max_latency, trust_env=False) as client:
        for path in ('/health', '/openapi.json'):
            start = time.monotonic()
            response = client.get(path)
            response.raise_for_status()
            data = response.json()
            if path == '/health' and data != {'status': 'ok'}:
                raise ValueError('健康检查契约不匹配')
            if path == '/openapi.json' and '/api/claims/process' not in data['paths']:
                raise ValueError('缺少理赔路由契约')
            timings[path] = time.monotonic() - start
        start = time.monotonic()
        response = client.post('/api/claims/process', json={'claim_id': 'health-' + uuid.uuid4().hex, 'description': '健康检查合成报案，缺少保单信息，不触发真实推理。'})
        response.raise_for_status()
        if response.json()['phase'] != 'awaiting_information':
            raise ValueError('状态机未进入预期的补材料阶段')
        timings['/api/claims/process'] = time.monotonic() - start
    if any(value >= max_latency for value in timings.values()):
        raise RuntimeError('健康检查超过延迟阈值')
    return timings


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8001')
    args = parser.parse_args()
    print(check(args.url))
