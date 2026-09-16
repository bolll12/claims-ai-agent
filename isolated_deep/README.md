# 官方Deep Agents隔离环境

主项目LangChain 0.3与官方Deep Agents依赖范围冲突。此目录锁定真实的`deepagents==0.2.8`及其解析依赖，使用Python 3.11+，已用Python 3.12验证；不要安装进主项目虚拟环境。

```bash
python3.12 -m venv .venv-deep
.venv-deep/bin/python -m pip install -r isolated_deep/requirements.txt
.venv-deep/bin/python -m pip check
.venv-deep/bin/python -m pytest -q isolated_deep/tests
```

入口为`agents.deep_claims_agent.create_deep_claims_agent()`，实际实现为`isolated_deep.runtime`。模型由LOCAL_LLM_BASE_URL/API_KEY/LOCAL_PRO_MODEL环境变量配置；独立运行时不自动读取主项目.env。原文的`deep_agents.Memory/Harness/Fuse/AgenticRAG`不是这里使用的官方API，分别映射为RedisConversation、create_deep_agent/subagents、LangFuse CallbackHandler和检索工具。

默认文件工具使用官方状态后端，不授予宿主文件系统或shell权限。三个专家通过官方task工具委派；是否一次产生并行调用取决于本地模型能力。写工具全部interrupt_on，恢复用LangGraph Command。即使人工恢复，真正入队仍需服务端注册Outbox和核对具体业务参数的authorize函数，模型不能伪造审批。

RedisConversation提供按案件隔离的2小时历史；主项目SQLite保存审核检查点。独立示例的MemorySaver检查点只在进程内，跨进程审核恢复应使用经组织验证的持久化checkpointer。LangFuse v3回调路径与主项目v2不同，已分别隔离。当前测试验证真实SDK调度与结构化输出，但没有真实推理服务或LangFuse项目联调证据。
