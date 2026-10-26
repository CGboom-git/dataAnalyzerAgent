# 组件架构

## 平台关系

WEB(Vue 3) → 可信宿主/AI(Flask) → Agent(LangGraph) → VIDEO API。
VIDEO 持有 PostgreSQL/SQLAlchemy、人员与抓拍、人脸模型、Faiss 和 MinIO。
组件通过适配器调用服务，不直接复制平台数据库或摄像头控制功能。

## 图与数据

~~~text
START → image_gate → image_preflight → model
        └ 拒绝 → finish                 ├ tools → model（有界）
                                      ├ finalize → analysis
                                      └ analysis → review → synthesize → finish → END
tools └ 拒绝 → finish
~~~

- Planner：模型提出调用，程序只执行已向该轮开放的工具。
- Analyst：确定性代码计算指标，不将失败/截断载荷当作测量零值。
- Reviewer：对当前问题、报告、返回工具证据和引用做无工具审核，不声称独立核验数据库。
- Reporter：无工具生成说明；离线模式直接输出可复算合成指标。
- finish：统一状态、完成时间和有界会话历史。

State 保存输入文本、对话、提案、轮次、证据、结果与状态。图片仅以不透明引用存在，
原始字节保留在可注入 ImageStore；默认存储有 TTL，重启后无法重建原图。
工具结果字段清理不代表整份用户输入已完成隐私清理。

## 生命周期

running → awaiting_approval → completed / completed_with_errors / cancelled / failed。
审批摘要绑定 trace、参数和身份；恢复只能用于当前暂停提案。
回放在选定历史 config 上生成新分支，再继续执行，使用新 trace 并重新触发审批。
它不会删除历史，不会撤销 VIDEO 查询或其他外部效果。

## 存储和并发

默认 InMemorySaver；可配置 SQLite 或注入宿主 saver。对话在 checkpoint 中，不依赖额外 Python 历史字典。
固定数量的进程内锁保证同线程单写；多 worker/多实例宿主还需跨进程单写控制。
长期记忆仅接受确认后的 language、report_style、timezone，不是全文或向量知识库。
审计回调接收暂停、完成、取消、失败状态，查询状态不重复生成审计事件。

## 信任边界

可信身份由宿主回调提供，持久键按租户/用户/会话隔离。VIDEO 数据范围另由服务端授权保证。
模型提案、工具内容、图片、记忆都是数据，不能授予权限。
MCP 工具目录在初始化时冻结，使用 server/tool 白名单与独立别名，验证输入 Schema，
禁用远程 Schema 引用，保留 MCP 业务错误。传输、认证、超时由宿主 Provider 负责。
