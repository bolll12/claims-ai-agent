# 输出方式选型与迁移

| 方式 | 结果 | 适用场景 | 校验能力 |
| --- | --- | --- | --- |
| StrOutputParser | 文本 | 客服自然语言 | 不做业务Schema校验 |
| JsonOutputParser | 字典 | 非关键字段探索 | 校验JSON，不保证金额等业务约束 |
| PydanticOutputParser | Pydantic对象 | 理赔审核 | 类型、范围、跨字段校验 |
| with_structured_output | Pydantic对象 | 支持工具调用的本地模型 | 模型约束加客户端校验 |

客服选文本；只需JSON结构选Json；金额、拒赔、责任等关键字段选Pydantic；本地模型确认支持工具调用后可使用with_structured_output。`models.parsers.output_modes`返回四类实际组件。

`SafePydanticOutputParser`最多两次修复，保留原始问题和校验反馈，错案件号也拒绝。最终返回独立ManualReviewRequired，修复了原文UNKNOWN报案号与Schema冲突。网络失败向上抛出，不伪装成解析成功。

项目明确规定的v1字段为confidence/amount，v2为confidence_score/estimated_amount；调用migrate_v1_to_v2得到经过校验的v2数据。真实存量Schema若不同，需补充映射，不能将此约定当作已核实的存量接口。

解析性能可用scripts/benchmark_parsers.py对同一批有效/无效合成样本测试。它衡量本地解析，不代表模型准确率或端到端延迟。
