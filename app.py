"""FastAPI入口：真实状态机、持久检查点、补材料、审核恢复和可观测指标。"""
import asyncio
from contextlib import asynccontextmanager
import hmac
import os
from pathlib import Path
import time
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict, Field

from adapters.business import BusinessBackend, DemoBackend
from agents.claim_agent import WorkflowServices, build_claim_graph
from agents.middleware_audit import configure_logging, mask_pii, RateLimitMiddleware
from agents.observability import tracing_config
from models.schemas import ClaimRequest, ClaimResponse
from monitoring import metrics, REQUESTS, ERRORS, LATENCY, CONFIDENCE, ITERATIONS, TOKENS
from settings import Settings


class HealthResponse(BaseModel):
    status: Literal['ok'] = 'ok'


class Supplement(BaseModel):
    model_config = ConfigDict(extra='forbid')
    policy_id: str = Field(min_length=1, max_length=64)


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decision: Literal['review', 'accept', 'reject']
    reviewer: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=1000)
    clause_basis: list[str] = Field(default_factory=list)


def create_app(services: WorkflowServices | None = None, *, database: str | None = None) -> FastAPI:
    cfg = Settings()
    backend = DemoBackend() if cfg.business_mode == 'demo' else BusinessBackend()
    service = services or WorkflowServices(backend)
    limiter = RateLimitMiddleware()
    locks: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        if os.getenv('APP_ENV') == 'production' and (not os.getenv('CLAIMS_API_KEY') or not os.getenv('REVIEWER_API_KEY')):
            raise RuntimeError('生产环境必须配置CLAIMS_API_KEY和REVIEWER_API_KEY')
        path = database or os.getenv('CLAIMS_CHECKPOINT_DB', '.data/checkpoints.sqlite')
        if path != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        configure_logging()
        async with AsyncSqliteSaver.from_conn_string(path) as saver:
            await saver.setup()
            application.state.graph = build_claim_graph(service, saver)
            yield

    application = FastAPI(title='理赔 Agent 服务', version='0.2.0', lifespan=lifespan)
    application.add_middleware(CORSMiddleware,
        allow_origins=[value.strip() for value in os.getenv('CORS_ALLOW_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',')],
        allow_credentials=False, allow_methods=['GET', 'POST'], allow_headers=['Content-Type', 'Authorization', 'X-API-Key', 'X-Reviewer-Key'])

    def authenticate(x_api_key: str = Header(default='')) -> None:
        expected = os.getenv('CLAIMS_API_KEY', '')
        if os.getenv('APP_ENV') == 'production' and not expected:
            raise HTTPException(503, '生产环境尚未配置API认证')
        if expected and not hmac.compare_digest(x_api_key, expected):
            raise HTTPException(401, 'API认证失败')

    def authenticate_reviewer(x_reviewer_key: str = Header(default='')) -> None:
        expected = os.getenv('REVIEWER_API_KEY', '')
        if not expected:
            raise HTTPException(503, '尚未配置审核员认证')
        if not hmac.compare_digest(x_reviewer_key, expected):
            raise HTTPException(403, '需要授权审核员')

    def graph_config(claim_id: str) -> dict[str, Any]:
        return {'configurable': {'thread_id': claim_id}}

    async def status(claim_id: str) -> ClaimResponse:
        snapshot = await application.state.graph.aget_state(graph_config(claim_id))
        state = snapshot.values
        if not state:
            raise HTTPException(404, '未找到案件')
        pending = snapshot.next
        phase = 'awaiting_information' if 'intake' in pending else 'awaiting_review' if 'review' in pending else state.get('phase', 'pending')
        return ClaimResponse(claim_id=claim_id,
            decision='pending' if phase == 'awaiting_information' else 'review' if phase == 'awaiting_review' else state.get('decision', 'pending'),
            phase=phase, confidence=state.get('confidence'), demo=getattr(service.backend, 'demo', False),
            message=mask_pii(state.get('message') or ('需要补充保单编号' if phase == 'awaiting_information' else '等待人工审核')))

    async def invoke(claim_id: str, payload: Any) -> ClaimResponse:
        config, handler = tracing_config(claim_id, cfg)
        start = time.monotonic()
        try:
            limiter.check(claim_id)
            await application.state.graph.ainvoke(payload, config=config)
            result = await status(claim_id)
            REQUESTS.labels(result.decision).inc()
            if result.confidence is not None:
                CONFIDENCE.observe(result.confidence)
            snapshot = await application.state.graph.aget_state(graph_config(claim_id))
            ITERATIONS.observe(len(snapshot.values.get('expert_results', [])) + snapshot.values.get('rounds', 0))
            usage = config['callbacks'][0].snapshot()
            TOKENS.labels('input').inc(usage['prompt_tokens'])
            TOKENS.labels('output').inc(usage['completion_tokens'])
            return result
        except HTTPException:
            raise
        except ValueError as exc:
            ERRORS.labels('validation').inc()
            raise HTTPException(422, '审核输入或模型结果不符合契约') from exc
        except Exception as exc:
            ERRORS.labels(type(exc).__name__).inc()
            if str(exc) == 'rate_limit_exceeded':
                raise HTTPException(429, '该案件请求过于频繁') from exc
            raise HTTPException(503, '处理链路暂不可用，请查询案件状态或转人工') from exc
        finally:
            LATENCY.observe(time.monotonic() - start)
            if handler is not None:
                await asyncio.to_thread(handler.flush)

    @application.get('/health', response_model=HealthResponse, tags=['健康检查'])
    async def health() -> HealthResponse:
        return HealthResponse()

    @application.get('/metrics', dependencies=[Depends(authenticate)])
    async def export_metrics() -> Response:
        return Response(content=metrics(), media_type='text/plain; version=0.0.4')

    @application.post('/api/claims/process', response_model=ClaimResponse, dependencies=[Depends(authenticate)])
    async def process_claim(request: ClaimRequest) -> ClaimResponse:
        async with locks.setdefault(request.claim_id, asyncio.Lock()):
            existing = await application.state.graph.aget_state(graph_config(request.claim_id))
            if existing.values:
                # 同案号不同内容不能悄悄覆盖检查点。
                if existing.values['claim_data'] != mask_pii(request.model_dump(mode='json')):
                    raise HTTPException(409, '案件已存在；请使用补材料或审核接口')
                return await status(request.claim_id)
            return await invoke(request.claim_id, {'claim_id': request.claim_id,
                'claim_data': mask_pii(request.model_dump(mode='json')), 'rounds': 0, 'expert_results': []})

    @application.get('/api/claims/{claim_id}', response_model=ClaimResponse, dependencies=[Depends(authenticate)])
    async def get_claim(claim_id: str) -> ClaimResponse:
        return await status(claim_id)

    @application.post('/api/claims/{claim_id}/supplement', response_model=ClaimResponse, dependencies=[Depends(authenticate)])
    async def supplement(claim_id: str, body: Supplement) -> ClaimResponse:
        async with locks.setdefault(claim_id, asyncio.Lock()):
            current = await status(claim_id)
            if current.phase != 'awaiting_information':
                raise HTTPException(409, '当前案件不处于补材料阶段')
            return await invoke(claim_id, Command(resume=body.model_dump()))

    @application.post('/api/claims/{claim_id}/review', response_model=ClaimResponse,
                      dependencies=[Depends(authenticate), Depends(authenticate_reviewer)])
    async def review(claim_id: str, body: ReviewInput) -> ClaimResponse:
        if body.decision == 'reject' and not body.clause_basis:
            raise HTTPException(422, '拒赔必须提供核实后的条款依据')
        async with locks.setdefault(claim_id, asyncio.Lock()):
            current = await status(claim_id)
            if current.phase != 'awaiting_review':
                raise HTTPException(409, '当前案件不处于人工审核阶段')
            return await invoke(claim_id, Command(resume=mask_pii(body.model_dump())))

    return application


app = create_app()
