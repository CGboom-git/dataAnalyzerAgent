# Agent 机制与验证边界（0.2.0）

## 检查点与会话

默认进程内 InMemorySaver。设置 AGENT_CHECKPOINT_DB 并安装 persistence extra 后使用 SQLite。
同一租户/用户/会话映射到同一内部线程；不同用户的同名会话互不复用。
短期对话作为 checkpoint 的 dialogue 字段保存，max_history_messages=0 时完全关闭保存。
进程内按线程串行化；跨进程单写需宿主实现。

## 审批、中断、取消

AGENT_REQUIRE_TOOL_APPROVAL=true 时，图片发往 VIDEO/模型前先审批，
模型提议的每一批工具也独立审批。payload 包含具体提案、scope 和 proposal_digest。
resume 必须同时提交 approved 布尔值和当前摘要，旧摘要和重复提交被拒绝。
拒绝结束当前执行，不再调用模型来重新申请同一查询。
cancel 只支持暂停任务，不表示能立即抢占已经发出的 HTTP 请求。

## 历史回放

rollback API 查找授权线程内的目标 checkpoint，在该历史配置上分叉，
设置新 trace/replayed_from，再运行后续节点。已结束或缺少任务状态的 checkpoint 被拒绝。
返回最新分支状态，可能再次等待审批；没有撤销外部查询、改写过去审计或承诺事务补偿。

依据：[LangGraph Time Travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)、
[Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)。

## 长期记忆与图片

记忆必须由用户明确确认，只允许语言枚举、报告样式枚举和有效时区。
包含任意身份描述、轨迹或“新指令”的自由文本不接受为偏好。
内存与 SQLite 开发适配器均按租户和用户检索/删除，并在检索时清理过期项。
这是有限偏好读取，不是语义检索，不等于服务器案例 RAG。

图片默认保留在进程内临时存储，checkpoint 中没有原图字节或 data URL。
进程重启/过期后图片引用不可用，检索返回 image_payload_expired；
需要图片持久恢复的宿主应注入具备隔离、保留、删除策略的 ImageStore。
用户文本、工具记录和引用仍需受控保存。

## Prompt、Skill 与角色

角色 Prompt 带版本；技能从包内 Markdown 资源加载。当前五个技能：
概览、档案检索、人员轨迹、活动统计、组合分析。轨迹技能允许先查人员档案。
模型候选工具在每轮开放目录和运行时校验中受限；Skill 本身不能提升权限。
Reviewer 接收当前返回证据但不再次查询原始来源，多角色共用配置模型服务。
离线模型是确定性模拟，不作为真实模型质量证据。

## MCP

Provider 提供已认证服务的目录与调用接口；白名单键为 server_id/tool_name。
桥接暴露稳定模型别名、冻结目录并验证 JSON Schema，拒绝外部 Schema 引用；
不同服务的同名工具不会混用。read_only 元数据需要可信宿主审核，不是安全证明。
桥接归一化 isError、异常和无效结果；实际连接、协商与时间限制由 Provider 实现。
未默认连接任何真实 MCP 服务。

## 证据

控制流、SQLite 重建、隔离、回放和 HTTP 协议检查见 tests/ 和 VERIFICATION.md。
已测试的协议桩不能替代真实 Qwen、真实权限、真实人脸或生产规模验证。
