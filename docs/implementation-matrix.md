# 培训材料实现追踪

来源：`/Users/chengang/Desktop/claims-langchain-training.md`。

本清单按原文【文件】逐项抽取，不把原文教学代码视为已实现或已验证。重复文件落点合并实现，但保留原文条目便于验收。

原文 SHA256：`f5b9ea788e7e126c7e31e785a01d8fbf9422211bbe792c3da4c4ee52f9bef543`，共 5676 行，64 个文件落点。

| 原文行号 | 章节 | 原文落点 | 状态 |
| --- | --- | --- | --- |
| 188 | 模块00 项目脚手架搭建（动手前准备） | 新建：claims-agent-app/ 项目目录（含 agents/tools/prompts/models/tests 各包与 __init__.py）。 | 已实现并验证：分层包及公共入口齐全 |
| 216 | 模块00 项目脚手架搭建（动手前准备） | 新建：claims-agent-app/requirements.txt，整套依赖清单。 | 已实现并验证：主环境可一次安装且pip check通过 |
| 242 | 模块00 项目脚手架搭建（动手前准备） | 新建：claims-agent-app/config.py，模型工厂与三个模型别名。 | 已实现并验证：本地默认、百炼可选、四档缓存工厂 |
| 276 | 模块00 项目脚手架搭建（动手前准备） | 新建：claims-agent-app/app.py，FastAPI 服务入口与占位业务路由。 | 已实现并验证：HTTP状态机及恢复接口已实际启动 |
| 323 | 搭建验证 | 修改：claims-agent-app/ 运行环境，在 claims-agent-app/ 目录下执行安装、启动与测试命令。 | 已实现并验证：安装、测试、启动和HTTP检查脚本 |
| 360 | 安装与依赖 | 修改：claims-agent-app/requirements.txt，安装依赖并配置环境变量的命令作用于项目目录。 | 已实现并验证：环境模板和完整锁文件 |
| 383 | 本地推理服务模型的统一创建 | 修改：claims-agent-app/config.py，_chat 工厂与理赔任务路由表。 | 已实现并验证：本地兼容模型及任务路由 |
| 419 | 流式调用与多参数分析 | 新建演示脚本 demos/module02_demo.py，演示同步、流式与多参数调用。 | 已实现并验证：同步/流式/多参数代码，真实模型待联调 |
| 473 | 多参数深度剖析 | 新建演示脚本 demos/module02_demo.py，三档参数与异步批量调用演示。 | 已实现并验证：三档参数和有序异步批量 |
| 505 | 多种Message类型 | 新建演示脚本 demos/module04_demo.py，演示多轮对话与消息类型。 | 已实现并验证：Message角色及ToolMessage配对 |
| 529 | ChatPromptTemplate 注入方式 | 新建演示脚本 demos/module04_demo.py，演示六种 Prompt 注入方式。 | 已实现并验证：六种Prompt方式及partial兼容修复 |
| 591 | 多种工具创建方法 | 修改/新建：claims-agent-app/tools/policy_tool.py、claim_tool.py、medical_tool.py，三种方式创建工具。 | 已实现并验证：装饰器、StructuredTool、异步医保工具 |
| 646 | 强制工具调用 | 修改：claims-agent-app/tools/claim_tool.py，强制与并行工具调用编排。 | 已实现并验证：auto/required/指定及并行工具消息闭环 |
| 740 | 多实操案例：理赔工具集 | 修改：claims-agent-app/tools/policy_tool.py、claim_tool.py、medical_tool.py，理赔完整工具集。 | 已实现并验证：八工具注册；真实接口需适配器配置 |
| 847 | 四种输出模式与选型 | 修改：claims-agent-app/models/schemas.py，定义理赔结构化模型与四种输出模式。 | 已实现并验证：契约、四解析模式、有限修复及迁移 |
| 937 | Agent创建方法 | 修改：claims-agent-app/agents/claim_agent.py，端到端理赔 Agent。 | 已实现并验证：AgentExecutor与端到端LangGraph |
| 1023 | Agent三种基础用法 | 修改：claims-agent-app/agents/claim_agent.py，三种基础用法。 | 已实现并验证：单轮、多步、对话历史封装 |
| 1104 | Agent四种高级用法 | 修改：claims-agent-app/agents/claim_agent.py，规划/多Agent/HITL 高级编排。 | 已实现并验证：plan-execute、多专家、HITL |
| 1239 | 核心中间件示例 | 修改/新建：claims-agent-app/agents/middleware_audit.py，审计/合规/限流等中间件链。 | 已实现并验证：脱敏/审计/限流/缓存/重试/熔断/HITL |
| 1492 | LangFuse 接入与使用步骤 | 新建：demos/langfuse_demo.py（演示 LangFuse 接入并现场跑通）；生产接入在各 Agent 的 callbacks 配置。 | 代码已实现：LangFuse v2回调；需真实自托管项目联调 |
| 1540 | LangFuse 接入与使用步骤 | 新建：demos/LangFuse使用流程.md，存放该 Mermaid 图源码。 | 已实现并审阅：五步Mermaid源码 |
| 1572 | 短期记忆与长期记忆 | 修改：claims-agent-app/agents/claim_agent.py，会话记忆与 Redis 持久化。 | 已实现并验证：窗口/摘要/实体冲突/Redis接口 |
| 1680 | RAG五大核心流程 | 新建：demos/RAG五大核心流程图.md，存放该 Mermaid 图源码。 | 已实现并审阅：RAG五步Mermaid源码 |
| 1737 | Docker安装Milvus向量数据库 | 修改：claims-agent-app/ 运行环境，在项目目录执行 Milvus docker-compose 部署命令。 | 配置已实现：本机无Docker，Milvus实际联调由CI执行 |
| 1754 | Docker安装Milvus向量数据库 | 新建：claims-agent-app/docker-compose.yml，Milvus standalone 三容器编排。 | 配置已实现并通过YAML解析；本机无Docker未启动 |
| 1795 | 完整RAG流程：保单条款检索 | 修改/新建：claims-agent-app/tools/rag_retrieval.py，保单条款 RAG 与混合检索。 | 已实现并离线验证；真实Milvus集成测试待Docker/CI |
| 2299 | 11.1 Agent：结构化输出策略 | 修改：claims-agent-app/agents/deep_claims_agent.py，结构化输出审核 Agent。 | 已实现并验证：独立环境官方结构化输出策略 |
| 2341 | 11.2 Middleware：中间件流水线 | 修改/新建：claims-agent-app/agents/middleware.py，脱敏与审计中间件流水线。 | 已实现并验证：官方中间件钩子及主项目中间件 |
| 2378 | 11.3 Memory：持久化记忆 | 修改：claims-agent-app/agents/deep_claims_agent.py，Redis 持久化记忆。 | 已实现：RedisConversation；真实Redis待联调 |
| 2411 | 11.4 HITL：人在环路（人机协同） | 修改：claims-agent-app/agents/deep_claims_agent.py，HITL 大额人工审核。 | 已实现并验证：interrupt_on写操作与主图HITL |
| 2442 | 11.5 Fuse：LangFuse 全链路运维监控 | 修改：claims-agent-app/agents/deep_claims_agent.py，LangFuse 全链路追踪。 | 代码已实现：独立LangFuse v3回调；真实平台待联调 |
| 2470 | 11.6 RAG：Agentic RAG 智能检索增强 | 修改：claims-agent-app/agents/deep_claims_agent.py，AgenticRAG 按需检索。 | 已实现：以RAG工具按需检索；真实Milvus待联调 |
| 2500 | 11.7 Deep：Deep Agents Harness 编排引擎 | 修改：claims-agent-app/agents/deep_claims_agent.py，Harness 并行编排。 | 已实现并验证：官方create_deep_agent和subagents替代虚构Harness |
| 2532 | 11.8 Deep Agents 理赔上岗实战（端到端） | 新建：claims-agent-app/agents/deep_claims_agent.py，整合七大能力的端到端理赔 Agent。 | 已实现并验证：官方SDK真实运行时测试通过 |
| 2649 | 核心一：确定性流程与条件路由 | 修改：claims-agent-app/agents/claim_agent.py，确定性流程与条件路由状态机。 | 已实现并验证：确定性节点及证据优先路由 |
| 2706 | 核心二：循环回流（材料不齐自动追问） | 修改：claims-agent-app/agents/claim_agent.py，材料不齐自动追问循环回流。 | 已实现并验证：interrupt补材料且最多三轮 |
| 2732 | 核心三：并行扇出（三专家同时作业） | 修改：claims-agent-app/agents/claim_agent.py，三专家并行扇出。 | 已实现并验证：Send并行三专家及operator.add聚合 |
| 2773 | 核心四：状态持久化与人在回路 | 修改：claims-agent-app/agents/claim_agent.py，checkpointer 状态持久与断点续跑。 | 已实现并验证：SQLite检查点、人工中断、重启恢复 |
| 2803 | 核心五：端到端总图 | 新建：demos/理赔Agent端到端状态机图.md，存放该 Mermaid 图源码。 | 已实现并审阅：端到端流程Mermaid |
| 2846 | 进阶 API | 修改：claims-agent-app/agents/claim_agent.py，recursion_limit 调用写法。 | 已实现并验证：recursion_limit=40 |
| 2860 | 进阶 API | 修改：claims-agent-app/agents/claim_agent.py，max_concurrency 并发控制。 | 已实现并验证：max_concurrency=3 |
| 2874 | 进阶 API | 修改：claims-agent-app/agents/claim_agent.py，三专家评审子图。 | 已实现并验证：三专家子图复用 |
| 2890 | 进阶 API | 修改：claims-agent-app/agents/claim_agent.py，plan-execute 规划执行编排。 | 已实现并验证：有界规划执行 |
| 2912 | 进阶 API | 新建：demos/理赔状态机图.md，存放生成的 Mermaid 图源码。 | 已实现并审阅：状态恢复Mermaid |
| 2928 | 回归测试 | 新建：claims-agent-app/tests/test_langgraph_agent.py，条件路由与循环回流回归用例。 | 已实现并验证：LangGraph回归用例 |
| 2967 | 方法一：Softmax概率置信度 | 修改：claims-agent-app/agents/confidence.py，Softmax 概率置信度。 | 已实现并验证：稳定Softmax |
| 3012 | 方法二：香农熵度量不确定性 | 修改：claims-agent-app/agents/confidence.py，香农熵置信度。 | 已实现并验证：归一化熵 |
| 3065 | 方法三：贝叶斯动态置信度 | 修改：claims-agent-app/agents/confidence.py，贝叶斯动态置信度。 | 已实现并验证：单案贝叶斯和证据日志 |
| 3167 | 方法四：多模型融合置信度 | 修改：claims-agent-app/agents/confidence.py，多模型融合置信度。 | 已实现并验证：统一目标事件的多模型融合 |
| 3296 | 温度缩放（Temperature Scaling） | 修改：claims-agent-app/agents/confidence.py，温度缩放校准。 | 已实现并验证：正温度和稳定NLL |
| 3381 | 校准曲线分析 | 修改：claims-agent-app/agents/confidence.py，校准曲线与 ECE 计算。 | 已实现并验证：包含概率1的加权ECE |
| 3450 | 4.5 完整置信度系统搭建 | 新建：demos/置信度评估系统架构图.md，存放该 Mermaid 图源码。 | 已实现并审阅：置信度架构Mermaid |
| 3496 | 4.5 完整置信度系统搭建 | 新建：claims-agent-app/agents/confidence.py，整合四法与校准的评估系统。 | 已实现并验证：整合四法、低分不拒赔 |
| 3690 | 5.2 路径一：OpenAI兼容模式接入 | 新建演示脚本 demos/module05_demo.py，本地推理兼容模式接入演示。 | 已实现：聊天及Embedding本地兼容演示；真实模型待联调 |
| 3751 | 项目结构 | 新建：claims-agent-app/ 高代码部署项目结构（含 Dockerfile、deploy.sh 等部署文件）。 | 已实现并验证静态配置：Docker/Compose/部署/监控/CI |
| 3789 | app.py：本地容器化应用入口 | 新建：claims-agent-app/app.py，本地容器化应用入口。 | 已实现并实际启动：FastAPI工作流服务 |
| 3933 | requirements.txt | 新建：claims-agent-app/requirements.txt，高代码部署依赖清单。 | 已实现并验证：主环境完整安装和pip check |
| 3964 | 5.4 部署架构图 | 新建：demos/本地部署架构图.md，存放该 Mermaid 图源码。 | 已实现并审阅：本地部署Mermaid |
| 4118 | 6.1 完整理赔Agent项目 | 新建：根目录 claims_agent.py，单文件完整理赔 Agent 演示。 | 已实现并验证：分层复用的单文件入口及离线demo |
| 4442 | 6.2 测试用例 | 新建：claims-agent-app/tests/test_claim_agent.py，单元/集成/数据驱动测试。 | 已实现并验证：81项主项目测试、81%目标模块覆盖率 |
| 5329 | 6.5.2.3 完整适配层实现：协议路由 + 熔断 + 降级 | 新建：claims-agent-app/adapters/legacy_adapter.py，存量系统对接适配层。 | 已实现并验证：HTTP适配、三态熔断和显式降级 |
| 5444 | 6.5.2.4 大流量回写：用消息队列异步解耦（避免 Agent 同步阻塞） | 新建：claims-agent-app/tools/claim_write_producer.py，异步回写消息队列工具。 | 已实现并验证：SQLite Outbox、幂等、租约及对账 |
| 5517 | 6.5.3 难点6：灰度发布与试点（从"不敢放量"到"放心放量"） | 新建：claims-agent-app/deploy/shadow_mode.py，Agent 与存量规则影子对拍。 | 已实现并验证：只读影子对拍 |
| 5568 | 6.5.4 难点7：上线评测门禁（给"能不能放量"一个量化标尺） | 新建：claims-agent-app/deploy/regression_gate.py，上线评测门禁。 | 已实现并验证：完整评测门禁 |

## 额外范围

模块10 SDD（原文1910–2268行）还要求模型工厂、Prompt版本、工具注册、输出解析、记忆与RAG评估，不能只实现【文件】所在代码块。第六章部署提示词（4933–5266行）还要求Docker、CI/CD、监控和运维。概念性GCN/图谱没有训练集或接口，不能宣称已训练或有效。

## 已确认的实现原则

用户已确认：主项目保持LangChain 0.3，Deep Agents独立环境；本地推理与LangFuse为主，百炼可选；演示数据和真实接口明确分离；低置信度或缺证据转人工/调查，拒赔须核实条款及授权审核。

## 已修正的可证明代码问题

- 第四章ECE最后一个分箱原文排除了概率1；实现将其纳入最后一桶。
- 温度拟合原文不约束T且直接exp可能溢出；实现优化log(T)，用logsumexp计算NLL并检查收敛。
- 贝叶斯更新原文对零概率分母无保护；实现拒绝无定义的证据，且日志返回副本。
- 未知保单状态不能通过默认值映射成“无效”，否则会误导后续判责；适配器已实现为未知值显式失败。
- 原文金额、先验、风险分数和自动化率不作为项目实测结果。

## 实际验证结果

2026-09-16主项目干净Python 3.12环境：`pip check`通过，`81 passed, 1 skipped`，目标模块覆盖率81%，Ruff、Mypy和Bandit通过。跳过项是需要Docker的真实Milvus集成测试。

Deep Agents隔离Python 3.12环境：`pip check`通过，官方`deepagents==0.2.8`真实调度和结构化输出测试通过。

FastAPI新版服务已在`127.0.0.1:8001`实际启动：`/health`、`/openapi.json`和`POST /api/claims/process`通过；合成请求进入`awaiting_information`，没有调用模型或外部业务系统。

未完成真实联调：本地Qwen聊天/Embedding服务、Milvus、Redis、自托管LangFuse、核心保单/医疗/支付/通知系统、生产Docker和部署目标。缺少这些外部系统时，项目不会虚构准确率、token、延迟、成本或业务成功结果。

## API核验来源

- [SciPy 1.14.1 minimize](https://docs.scipy.org/doc/scipy-1.14.1/reference/generated/scipy.optimize.minimize.html)：实际使用受边界约束的优化，并校验优化结果。
- [SciPy 1.14.1发行页](https://pypi.org/project/scipy/1.14.1/)：Python 3.10测试环境已实际安装。
- [官方Deep Agents快速入门](https://docs.langchain.com/oss/python/deepagents/quickstart)：使用`deepagents.create_deep_agent`；不能直接照抄材料未核实的`deep_agents.Harness/Fuse/Memory`。

## 完整性结论

64个原文【文件】落点均已有对应代码、配置、图或测试。以“材料代码落盘和可离线验证”为口径，已覆盖；以“真实生产闭环全部跑通”为口径，尚不完全，剩余项均依赖材料未提供的模型服务、基础设施、业务协议、真实标注集或部署凭证。详细边界见`docs/material-differences.md`和本表状态。
