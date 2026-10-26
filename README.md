# EasyAIoT Face Analysis Agent

面向 EasyAIoT 平台的人脸数据分析组件。使用 **LangGraph + Flask** 编排自然语言查询、受限工具调用、确定性统计、证据审核和报告输出。

它依赖平台 VIDEO 提供真实人员、抓拍、轨迹和图片相似检索。组件可通过合成数据独立验证关键逻辑；真实 PostgreSQL/SQLAlchemy、Faiss、人脸模型、MinIO 和 Vue 3 界面仍属于平台。

**版本：0.2.0。平台 Agent 组件源码展示；尚未指定开源许可证，见 [LICENSE_STATUS.md](LICENSE_STATUS.md)。**

实际服务接入进展见 [联调记录](docs/LIVE_INTEGRATION.md)：真实 Qwen、WSL 的实际 VIDEO 分析代码和 PostgreSQL 只读快照已完成查询联调。快照的人脸表为空，未验证非空人脸数据、真实图片或完整平台启动。

## 能展示什么

| 能力 | 组件实现 | 展示边界 |
| --- | --- | --- |
| 工具编排 | 总览、人员、活动、两期对比、轨迹 | 图片检索由 VIDEO 提供 |
| 报告 | Python 确定性统计、覆盖率、限制、证据 | 无数据不当成测量零值 |
| 角色 | Planner → Analyst → Reviewer → Reporter | Analyst 是代码；Reviewer 不独立查询 DB |
| 人审 | 图片外发前、工具执行前暂停；摘要绑定提案 | 可配置，不是所有只读查询都默认弹窗 |
| 恢复/回放 | SQLite 可选持久化、历史分叉和新审批 | 只恢复图，外部操作不会被撤销 |
| 短期记忆 | 检查点内有界对话 | 同一会话在宿主中须保证单写者 |
| 长期记忆 | 确认后的语言、报告风格和时区 | 不接受任意文本，不是语义 RAG |
| Skill | 五个版本化包内技能、组合路由、工具约束 | 不执行外部 Markdown/代码 |
| MCP | 宿主 Provider、限定服务/工具、Schema 校验 | 不是完整 MCP 传输实现 |
| 平台边界 | 可信身份回调、可注入 VIDEO 委托凭证、审计回调 | VIDEO 必须独立校验数据范围 |

## 五分钟合成演示

在独立 Python 3.11/3.12 环境内执行，不要覆盖平台已有虚拟环境：

~~~bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,persistence]"
python -m pytest -q
python examples/demo.py --output artifacts/demo.json
~~~

系统缺少 venv/ensurepip 时先按本机发行版安装虚拟环境支持。示例显式使用合成配置，不读取你的生产端点；包含：
- 3 个虚构人员、51 条虚构抓拍；
- 概览、活动、人员、轨迹、两期比较；
- 先暂停、重建 Runtime/SQLite 连接、再恢复；
- 拒绝调用后终止、历史回放后重新审批。

生成的 artifacts/demo.json 不进入版本控制。预期总览为 3 人、51 条记录；本地图片检索不可用是明确限制，不会模拟“识别成功”。真实执行证据见 [验证记录](docs/VERIFICATION.md)。

## 本地 HTTP API

~~~bash
export AGENT_REQUIRE_TOOL_APPROVAL=true
export AGENT_CHECKPOINT_DB=.local/checkpoints.sqlite3
export AGENT_MEMORY_DB=.local/preferences.sqlite3
python -m easyaiot_face_agent
~~~

进程默认只绑定 127.0.0.1:8765。环境变量由进程读取，组件不会自动加载 .env。

~~~bash
curl -sS http://127.0.0.1:8765/v1/health
curl -sS -X POST http://127.0.0.1:8765/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"overview","conversation_id":"demo-01"}'
~~~

若状态为 awaiting_approval，读取 pending_interrupt[0].proposal_digest，再提交：

~~~http
POST /v1/runs/demo-01/resume
Content-Type: application/json

{"approved":true,"proposal_digest":"<返回的提案摘要>"}
~~~

chat、resume、rollback 返回相同结果信封，统一使用 assistant_reply。图片和工具可能形成两个独立暂停点；不要默认一次确认会批准所有后续提案。

| 路径 | 功能 |
| --- | --- |
| GET /v1/health | 基础模式与 saver 类型，不证明下游已就绪 |
| GET /v1/tools、/v1/skills | 工具和技能 |
| POST /v1/chat | 开始一轮或继续已完成会话 |
| GET /v1/runs/{thread_id} | 当前状态 |
| GET /v1/runs/{thread_id}/checkpoints | 历史位置 |
| POST /v1/runs/{thread_id}/resume | 确认/拒绝指定提案 |
| POST /v1/runs/{thread_id}/rollback | 按 checkpoint_id 分叉并执行到结束或下一暂停 |
| POST /v1/runs/{thread_id}/cancel | 取消暂停任务；不抢占正在进行的网络调用 |

thread_id 是调用方可见的会话标识；实际持久化键由可信租户、用户和会话共同派生。新请求不能覆盖暂停中的执行。

## 挂载平台

~~~python
from flask import g
from easyaiot_face_agent import AgentRuntime
from easyaiot_face_agent.api import register_agent_routes
from easyaiot_face_agent.config import AgentConfig

runtime = AgentRuntime(AgentConfig.from_env())

# g.auth 必须由平台认证中间件设置，不能直接信任 JSON 或原始请求头。
register_agent_routes(
    app, runtime,
    url_prefix="/api/agent/face",
    identity_resolver=lambda: {
        "tenant_id": g.auth.tenant_id,
        "user_id": g.auth.user_id,
    },
)
~~~

配置 VIDEO 后，没有可信身份回调的 HTTP 路由会拒绝数据请求。会话隔离不替代 VIDEO 行级授权；共享服务 token 不自动授予当前用户全部数据。宿主可以注入 scope_headers_provider，为每次 VIDEO 请求提供经过验证的委托凭证，见 [接入契约](docs/INTEGRATION_CONTRACT.md)。

真实模型配置：
- AGENT_MODEL_BASE_URL：兼容 Chat Completions 的配置端点；
- AGENT_MODEL_NAME：实际部署模型名，例如你自己的 Qwen 部署别名；
- AGENT_MODEL_API_KEY：可选服务凭证；
- FACE_ANALYTICS_BASE_URL / FACE_ANALYTICS_API_TOKEN：平台 VIDEO；
- AGENT_SMOKE_TENANT / AGENT_SMOKE_USER：opt-in 冒烟身份。

~~~bash
python examples/smoke_live.py
~~~

该脚本只读查询概况，不自动批准真实调用。没有实际端点时，不可把协议桩测试写成“真实 Qwen 已联调”。

## Docker / Nginx

~~~bash
docker compose up --build
~~~

compose.yaml 使用单 worker、loopback 端口和持久卷演示本地组件。示例不带生产认证。Nginx 路径适配片段在 deploy/nginx.conf.example。是否实际完成 Docker 构建见验证记录，不以配置文件存在代替运行验证。

## 目录与阅读顺序

~~~text
api/            Flask 接入、统一运行接口、宿主身份
core/           LangGraph、审批摘要、持久状态、临时图片引用
tools/          工具 Schema、校验和只读分发
analytics/      可复算统计与报告质量
skills/         包内技能资源及路由
prompts/        角色提示词与版本
memory/         结构化偏好，内存/SQLite
integrations/   受限 MCP Provider 桥接
adapters/       模型、VIDEO、宿主审计
demo/ + data/   合成数据适配
tests/          控制流、隔离、统计与真实 localhost HTTP 协议测试
examples/       可复现演示与 opt-in 真实联调脚本
~~~

先读 tools/service.py 和 adapters/video_client.py，再读 core/runtime.py、analytics/report_builder.py 和 tests/test_runtime.py。

## 验证与限制

~~~bash
python -m pip check
python -m pytest -q
python -m build
python scripts/verify_wheel.py dist/*.whl
python scripts/release_check.py
~~~

GitHub Actions 已配置 Python 3.11/3.12 检查；本地执行不等于远端 CI 已运行。当前保留 Flask 2.3 技术线，生产使用前仍需按宿主兼容性做依赖安全审查。

- SQLite 是本地持久化选项，生产可注入宿主 LangGraph saver；未做多机吞吐承诺。
- 进程内图片载荷不写入 checkpoint，TTL/重启后会失效；持久图片恢复需注入有权限和保留策略的 ImageStore。
- 事件数据、证据 ID、用户文本仍可能敏感，应保护状态 DB 和审计存储。
- 没有通用运行中抢占取消、跨服务补偿或自治 Agent 群。
- Kafka/Redis 属于平台及后续扩展，不是当前组件已经集成的能力。
- 完整 Vue 页面、人脸模型质量、平台权限、生产规模和真实 Qwen 质量不由合成演示证明。

更多：[运行机制](docs/AGENT_RUNTIME.md) · [架构](ARCHITECTURE.md) · [公开检查表](docs/PUBLICATION_CHECKLIST.md) · [安全边界](SECURITY.md)。

简历对应范围见 [RESUME_MAPPING.md](docs/RESUME_MAPPING.md)。发布前可运行
python scripts/release_check.py --for-publication；许可审核未完成时返回状态码 2，作为待办提示。本仓库已按用户要求公开展示源码，未因此自动获得开源许可证。
