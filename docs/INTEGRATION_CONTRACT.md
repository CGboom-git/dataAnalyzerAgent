# 平台接入契约（0.2.0）

## 宿主职责

组件属于 EasyAIoT AI 的一部分。宿主提供认证身份、VIDEO 委托凭证、数据范围、
多进程会话单写控制、状态/审计保留策略和平台 Vue 页面。
配置真实 VIDEO 后，HTTP 路由缺少 identity_resolver 会拒绝数据请求。

~~~python
from flask import g
from easyaiot_face_agent import AgentRuntime
from easyaiot_face_agent.api import register_agent_routes
from easyaiot_face_agent.adapters.video_client import VideoApiClient
from easyaiot_face_agent.config import AgentConfig
from easyaiot_face_agent.tools.service import FaceAnalysisTools

config = AgentConfig.from_env()
video = VideoApiClient(
    config,
    # g.auth 由真实平台认证中间件设置；禁止直接信任客户端提供的租户头。
    scope_headers_provider=lambda: {
        "Authorization": "Bearer " + g.auth.video_delegation_token,
    },
)
runtime = AgentRuntime(config, tools=FaceAnalysisTools(config, video_client=video))
register_agent_routes(
    app, runtime, url_prefix="/api/agent/face",
    identity_resolver=lambda: {
        "tenant_id": g.auth.tenant_id, "user_id": g.auth.user_id,
    },
)
~~~

委托 token 只是接入示例，现有 VIDEO 必须按平台协议验证其真实授权范围。
会话隔离或共享服务 token 均不能替代数据行级授权。宿主应用退出时调用 runtime.close()。

## 路由

本地前缀 /v1，挂载默认前缀 /api/agent/face。
- GET /health、/tools、/skills。
- POST /chat：message、history、images、conversation_id。
- GET /runs/{thread_id}：统一信封形式的当前状态。
- GET /runs/{thread_id}/checkpoints：checkpoint_id、next、created_at。
- POST /runs/{thread_id}/resume：approved、proposal_digest。
- POST /runs/{thread_id}/rollback：checkpoint_id；创建分支并继续。
- POST /runs/{thread_id}/cancel：只取消暂停任务。

请求 JSON 里的 tenant_id/user_id 不参与授权。它们必须由 identity_resolver 给出。

## 统一响应

~~~json
{
  "contract_version": "easyaiot.face-agent.v1",
  "trace_id": "<本轮或回放的新 trace>",
  "conversation_id": "<授权会话>",
  "thread_id": "<同一公开会话标识>",
  "status": "awaiting_approval",
  "assistant_reply": "等待确认后继续执行。",
  "agent_steps": [],
  "analysis_results": [],
  "analysis_report": {},
  "evidence_refs": [],
  "pending_interrupt": [{"kind":"tool_approval","tools":[],"proposal_digest":"<摘要>"}],
  "replayed_from": null,
  "run_record_status": "not_configured"
}
~~~

status 为 running、awaiting_approval、completed、completed_with_errors、cancelled、failed。
chat/resume/rollback 使用同一信封；不再混用 reply 与 assistant_reply。
失效审批、未结束任务冲突返回 409，找不到授权任务/检查点返回 404，缺少认证上下文返回 401。
请求错误返回 400，模型服务错误返回 502；不要把这些错误解释为“查无记录”。

## VIDEO 已有端点

| 工具 | 路径 | 重要参数 |
| --- | --- | --- |
| get_face_overview | GET /video/face/analysis/overview | 无 |
| search_people | GET /video/face/analysis/people | q、isBlacklist、limit |
| summarize_face_activity | GET /video/face/analysis/activity | startTime、endTime |
| compare_face_activity | 两次 activity | 两组明确边界 |
| trace_person | GET /video/face/analysis/people/{id}/trajectory | startTime、endTime、limit |
| 图片预检 | POST /video/face/analysis/image-search | multipart image、topK |

内部 start_time/end_time 显式映射为 startTime/endTime。当前平台时间结束边界沿用 VIDEO 约定，
不能由组件单方面改成不同统计口径。两期查询不是数据库快照事务，期间数据可能变化。

## 模型与审计

模型适配器调用配置的 /v1/chat/completions 协议，验证 choices/message，凭证不进入 Prompt。
Reviewer/Reporter 无工具。工具提案仍经过程序校验，模型返回任意函数名不能直接执行。
审计可注入 AgentRunRecorder 或 PlatformRunRecorderAdapter；暂停记录 finished_at=null，
human_review_required=true，恢复后的终态重新记录。宿主按 trace/阶段选择事件或 upsert 策略。

## 有界数据与图片

默认最多三图，每图解码后不超过 10 MiB；同时校验支持的格式和签名，
复杂解码/人脸质量检查仍由 VIDEO 负责。HTTP 总请求限制 44 MiB，与宿主/代理共同设置。
图片原文不写 checkpoint，但检索结果、用户文本和业务引用仍有隐私属性。

## 验证层次

tests/test_http_integration.py 通过真实 localhost HTTP 检查模型兼容请求和 VIDEO 响应。
examples/smoke_live.py 是显式配置后的只读真实联调入口；未运行时不得声称已通过真实模型或平台验证。
