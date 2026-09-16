# 理赔 Agent 培训材料实现

依据 `claims-langchain-training.md` 实现分层代码、演示、测试和部署配置。主项目保持Python 3.10+、LangChain 0.3.14、langchain-openai 0.2.14；官方Deep Agents单独安装。默认连接本地推理，百炼需显式选择。真实模式未配置业务适配器会转人工，不返回假保单或虚构定损。

完整逐项映射及验证边界见 [实现验收清单](docs/implementation-matrix.md)；原文API与业务规则修正见 [差异记录](docs/material-differences.md)。

## 结构与职责

```text
claims-agent-app/
├── app.py                      # FastAPI、状态查询、补材料、授权审核恢复
├── settings.py                 # Pydantic环境配置与密钥校验
├── config.py                   # 本地模型工厂、四档缓存和任务参数
├── claims_agent.py             # 端到端入口与明确标注的离线演示
├── confidence_system.py        # 置信度公共入口，复用agents实现
├── requirements.txt            # 主项目及传递依赖精确锁定
├── .env.example                # 环境模板，不包含真实密钥
├── agents/                     # 审核编排、风险分析、置信度、记忆和中间件
│   ├── __init__.py             # Python包声明
│   ├── claim_agent.py          # LangGraph、Send并行、HITL、规划执行
│   ├── risk_agent.py           # 结构化专家意见与本地模型调用
│   ├── confidence.py           # Softmax/熵/贝叶斯/融合/温度/ECE
│   ├── memory.py               # 窗口、摘要、实体冲突与Redis持久化
│   ├── middleware_audit.py     # 脱敏、限流、缓存、重试、审计、Token统计
│   ├── middleware.py           # 中间件公共入口
│   ├── observability.py        # LangFuse v2嵌套追踪和脱敏回调
│   └── deep_claims_agent.py    # 独立Deep Agents环境的延迟入口
├── tools/                      # 八类业务工具及模型、检索、回写能力
│   ├── __init__.py             # Python包声明
│   ├── policy_tool.py          # 保单及理赔历史查询
│   ├── medical_tool.py         # 异步医保核验
│   ├── claim_tool.py           # 工具注册、审批绑定与并行消息闭环
│   ├── llm_calls.py            # 同步与流式调用
│   ├── rag_retrieval.py        # 文档加载、Milvus、混合检索及引用校验
│   └── claim_write_producer.py # 幂等Outbox、重试及对账
├── adapters/                   # 真实接口与演示后端，未配置显式失败
├── prompts/                    # 四场景模板、动态规则与本地固定版本
├── models/                     # Pydantic契约、有限修复和Schema迁移
├── tests/                      # 单元、SDK协议、状态机、HTTP与可选Milvus集成
├── demos/                      # 参数/消息/本地接口/LangFuse演示及Mermaid源码
├── isolated_deep/              # 官方Deep Agents独立依赖、运行时和测试
├── scripts/                    # 安装验证、解析基准与Schema迁移
├── deploy/                     # 对拍、门禁、环境配置、监控告警和运维手册
├── monitoring.py               # Prometheus六组业务指标
├── health_check.py             # 三条HTTP健康与状态机验证
├── Dockerfile                  # 非root、8001端口、单工作进程
├── docker-compose.yml          # 应用及Redis/Milvus基础设施
├── docker-compose.langfuse.yml # 独立自托管LangFuse
├── deploy.sh                   # 固定镜像版本发布与失败回退
└── .github/workflows/deploy.yml # 检查、测试、容器集成、构建及可选发布
```

agents/tools/prompts/models/tests及新增Python包均有`__init__.py`。

## 安装和离线验证

在项目根目录执行。Python 3.10兼容；本机3.10发行版会注入其他项目依赖，因此本次完整安装使用干净的Python 3.12。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
# 首次创建；已有.env不要覆盖。
if [ ! -f .env ]; then cp .env.example .env; chmod 600 .env; fi
python -m pytest -q
python claims_agent.py --demo
python -m demos.module04_demo --prompts
python -m scripts.benchmark_parsers
```

这些离线演示不代表真实模型、赔付系统或向量服务已联通。模型服务需支持OpenAI兼容聊天、JSON、tools；部分流式服务不返回usage，此时用量标记未知，不能声称零成本。固定seed只尽力复现。

## 启动HTTP服务

```bash
source .venv/bin/activate
uvicorn app:app --host 127.0.0.1 --port 8001
# 另一个终端
curl -fsS http://127.0.0.1:8001/health
python health_check.py
```

启动后访问 `http://127.0.0.1:8001/` 使用理赔智能助手。页面采用普通对话形式，支持对话意图识别、PDF/DOCX/文本抽取、图片视觉识别，以及结合识别结果的流式问答。五类理赔意图进入理赔专用提示和合规约束；一般咨询交给通用基模回答。附件仅在请求内存中处理，不落盘；图片识别要求配置的模型支持 OpenAI 兼容多模态消息。

也可先停止8001端口的现有本项目服务，再运行`bash scripts/verify.sh`完成启动与pytest两条验证链路。

| 路由 | 行为 |
| --- | --- |
| GET /health | 仅进程存活，不代表模型可用 |
| POST /api/claims/process | 创建审核工作流；缺保单号进入补材料中断 |
| GET /api/claims/{claim_id} | 查询已持久化案件状态 |
| POST /api/claims/{claim_id}/supplement | 仅补材料阶段接受policy_id |
| POST /api/claims/{claim_id}/review | X-Reviewer-Key认证后恢复人工审核 |
| GET /metrics | Prometheus格式指标 |
| GET /docs | 自动生成的接口文档 |
| GET / | 理赔智能工作台 |
| POST /api/documents/analyze | 内存解析并识别最多6份理赔单证 |
| POST /api/assistant/stream | 结合案件和单证上下文流式问答 |

请求支持description或claim_text，以及可选policy_id、amount。返回的是审核建议，不执行支付。SQLite检查点保存在`.data/checkpoints.sqlite`，重启可恢复。拒赔需授权人工提供条款依据；低置信度、证据不足和大额转人工。生产必须配置CLAIMS_API_KEY和REVIEWER_API_KEY；示例不支持多租户行级权限，也不能直接横向扩容。

## 本地模型与可选百炼

MODEL_PROVIDER默认local，使用LOCAL_LLM_BASE_URL/API_KEY和LOCAL_FAST/MAIN/PRO/VISION_MODEL。名称必须与推理服务实际注册名一致。本地服务端口默认8000，应用端口8001。

只有设置MODEL_PROVIDER=bailian才使用OPENAI_BASE_URL/API_KEY及QWEN_*_MODEL；已有百炼密钥无需删除，但不会自动用于本地模式。三个qwen别名分别映射通用、强推理、轻量模型。

## 业务、RAG与记忆接入

- `BusinessBackend(adapters={...})`注册组织内真实协议。保单HTTP实现来自材料；其余接口没有协议，必须显式注册，不能靠默认成功返回值闭环。
- `DemoBackend`仅提供材料里的固定教学案例。`claims_agent.py --demo`还使用明确标记的合成专家结果。未执行实际模型调用。
- 写工具只有服务端authorize核对案件、金额、收款方等参数后才入Outbox。通知也需要审批。消费者须向下游传递相同幂等键并对账。
- `load_documents`要求险种、版本、生效日期；`ClaimVectorStore`默认不删除旧集合。混合检索使用加权RRF，重排通过已核实的reranker函数注入。扫描PDF需另接OCR。
- `ClaimContextManager`可注入Redis客户端、摘要链和实体抽取器；Qwen需注入匹配模型的token_counter，默认cl100k_base只作教学计数，首次使用需准备tiktoken缓存。

## 追踪、基础设施及部署

```bash
# 需要Docker；未装Docker的机器不能执行以下联调。
docker compose --profile infra up -d --wait etcd minio milvus redis
RUN_MILVUS_TESTS=1 python -m pytest -q tests/test_milvus_integration.py
# 配置LangFuse数据库密码、认证secret和salt后：
docker compose -f docker-compose.langfuse.yml up -d
# 在控制台创建项目、填写.env里的public/secret key并开启LANGFUSE_ENABLED后：
python -m demos.langfuse_demo --invoke
```

LangSmith演示已移除，自动追踪关闭；`langsmith`包仍是LangChain 0.3强制传递依赖，不能删除后还宣称依赖兼容。Deep Agents使用独立环境及LangFuse v3，详见`isolated_deep/README.md`。

上线前运行固定历史数据集门禁：`python -m deploy.regression_gate metrics.json --cost-budget 实际预算`。CI的自动部署默认关闭，须配置生产环境审批、SSH信任、固定镜像和目标检出版本后启用。部署操作和真实业务通知均未在此次实现中执行。
