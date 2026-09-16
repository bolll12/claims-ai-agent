# 原文差异与确认记录

用户于本次会话确认：主项目保持LangChain 0.3，Deep Agents独立环境；本地推理+LangFuse，百炼可选并移除LangSmith演示；演示与真实接口分离，未配置真实接口报错；低置信度/缺证据转人工或调查，不能凭分数拒赔。

| 原文问题或缺失 | 实现处理 |
| --- | --- |
| `deep_agents.Harness/Fuse/Memory/AgenticRAG`接口未经官方SDK证实 | 独立安装真实deepagents 0.2.8，使用create_deep_agent、subagents、middleware、interrupt_on；Redis历史及LangFuse回调独立接入 |
| LangChain 0.3与Deep Agents新版LangChain冲突 | 两套venv和锁文件；已分别pip check |
| 0.4/0.3/0.3与0.4/0.4/0.2权重不一致 | 采用代码版0.4/0.4/0.2，可配置，并标记教学参数 |
| 分类最高概率可能代表“不受理”，却被用于受理加分 | 综合评分统一取“受理”目标概率，调用方LLM及规则概率也须同一目标 |
| 低置信度“调查/拒赔” | 只调查/人工；授权拒赔必须提供核实后的条款依据 |
| ECE分箱遗漏概率1 | 最后一桶闭区间包含1，添加回归测试 |
| 温度优化可能得到负T或exp溢出 | 优化log(T)、稳定NLL、检查收敛；T不必一定大于1，取决于验证数据 |
| 默认保单有效、未知责任五五分、虚构监控证据 | 仅明确demo提供固定教学值，真实模式缺接口/缺证据失败或转人工 |
| “任意工具必调”使用auto | 使用OpenAI required；并行工具显式parallel_tool_calls及asyncio.gather |
| 原文解析失败用UNKNOWN报案号构造严格模型 | 独立ManualReviewRequired，保留请求案件号，不伪装拒赔 |
| 模板相加丢失partial变量（当前固定版本） | 拼接后重新绑定partial_variables，实际测试验证 |
| token_counter=len被当作精确token | 注入模型分词器；cl100k_base明确只为教学计数，不能冒充Qwen分词 |
| LangFuse元数据放在configurable内部 | 使用实际回调构造参数session_id/metadata，LangChain config携带callbacks |
| 本地embedding参数名错误或发送token数组 | 使用api_key/base_url与check_embedding_ctx_length=False |
| 第六章Docker端口和现有项目不一致 | 应用统一8001，本地推理默认8000 |
| 持久化要求与MemorySaver示例差异 | 独立构图保留MemorySaver教学，FastAPI用SQLite持久检查点并测试重启恢复 |
| 没有业务协议、真实条款、训练/评测数据、模型单价 | 提供适配器及评测入口，缺配置显式失败；不编造协议、准确率、成本或GCN模型 |
| 字段保留2位小数与阈值比较风险 | 概率内部保留精度，金额以Decimal验证到分；展示层可自行格式化，不能先四舍五入再判阈值 |

官方API依据：[Deep Agents 0.2.8](https://pypi.org/project/deepagents/0.2.8/)、[LangFuse 2.60.8](https://pypi.org/project/langfuse/2.60.8/)、[SciPy 1.14.1](https://docs.scipy.org/doc/scipy-1.14.1/reference/generated/scipy.optimize.minimize.html)。实际安装后检查了构造器签名，并通过对应SDK运行时测试；未声称不存在的服务已联通。
