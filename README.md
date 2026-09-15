# 理赔 Agent 分层启动项目

本项目落实本地模型工厂、FastAPI 占位接口和环境验证脚本。业务流程尚未接入，理赔处理始终返回 `pending`。

## 模块落点

```text
claims-agent-app/
├── app.py                  # 主入口（FastAPI）
├── config.py               # 配置、模型初始化与任务参数路由
├── requirements.txt        # 精确锁定直接及传递依赖
├── .env.example            # 环境变量模板
├── agents/                 # 理赔、风控 Agent 与置信度
│   ├── __init__.py         # Python 包声明
│   ├── claim_agent.py      # 理赔 Agent（LangGraph 状态机落点）
│   ├── risk_agent.py       # 风控 Agent 落点
│   └── confidence.py       # 置信度子系统落点
├── tools/                  # 保单、理算、医保工具与共享调用能力
│   ├── __init__.py         # Python 包声明
│   └── llm_calls.py        # 同步、流式和结构化模型调用
├── prompts/                # 审核、风控 Prompt
│   └── __init__.py         # Python 包声明
├── models/                 # Pydantic 契约
│   ├── __init__.py         # Python 包声明
│   └── schemas.py          # 请求与响应契约
├── tests/                  # 单元与集成测试
│   ├── __init__.py         # Python 包声明
│   ├── test_smoke.py       # HTTP 接口冒烟测试
│   └── test_llm_parameters.py # 模型请求参数验证
├── scripts/                # venv 搭建及服务验证脚本
└── README.md               # 启动与开发说明
```

五个 Python 包均包含 `__init__.py`。

三个 Agent 模块当前预留职责，尚未实现状态机、风控及置信度算法。
模型调用统一从 `tools.llm_calls` 导入，任务模型从 `config.get_model` 获取。

## 搭建与验证

在本目录使用 macOS/Linux bash 执行：

```bash
bash scripts/setup_and_verify.sh
```

脚本依次创建并激活 `.venv`、安装依赖、检查约束、运行 pytest，随后在 `8001` 端口启动服务并验证 `/health` 和理赔接口。验证完成自动停止服务，保留临时日志。默认本地推理服务使用 `8000` 端口，与 HTTP 应用分开。

依赖文件的安装基线是 Python 3.10 / macOS ARM64；其他平台与 Python 版本需要重新验证，尤其是 Milvus Lite 和 NumPy 的二进制支持。

单独启动：

```bash
source .venv/bin/activate
python -m uvicorn app:app --host 127.0.0.1 --port 8001
```

## 配置

按需复制 `.env.example` 为 `.env`。部署环境变量优先于文件。`OPENAI_BASE_URL` 默认指向 `http://127.0.0.1:8000/v1`；`OPENAI_API_KEY` 默认 `EMPTY` 仅适用于无鉴权的本地服务。真实密钥通过环境注入，`.env` 不提交。

三个模型别名 `qwen_plus`、`qwen_max`、`qwen_flash` 分别用于通用、强推理、轻量降级任务，共用服务地址。通过 `QWEN_*_MODEL` 配置服务实际注册的模型名称。工厂默认温度为 0，自动降级和状态机留给后续模块实现。

`CORS_ALLOW_ORIGINS` 为逗号分隔的前端来源，默认包含本地 3000 端口。默认冒烟测试按该配置验证 CORS。

## 接口

- `GET /health`：返回 `{"status":"ok"}`，仅表示进程存活。
- `POST /api/claims/process`：接收 `claim_id` 和 `description`，返回案件标识、`pending` 状态及占位说明；缺少必填字段或空白输入返回 422。

接口冒烟测试不请求本地推理服务，不写入案件数据。
