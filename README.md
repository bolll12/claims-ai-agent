# 理赔 Agent 分层启动项目

本项目落实本地模型工厂、FastAPI 占位接口和环境验证脚本。业务流程尚未接入，理赔处理始终返回 `pending`。

## 模块落点

```text
agents/             # 理赔 Agent 与状态机
tools/              # 业务工具
prompts/            # 提示词与模板
models/schemas.py   # 请求与响应契约
tests/              # 接口冒烟测试
config.py           # 本地 ChatOpenAI 模型工厂
app.py              # FastAPI 入口
requirements.txt    # 精确锁定直接及传递依赖
scripts/            # venv 搭建及真实 HTTP 验证
```

五个 Python 包均包含 `__init__.py`。

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
