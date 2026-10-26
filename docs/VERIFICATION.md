# 本地验证记录

日期：2026-10-26。组件版本：0.2.0。环境：WSL Ubuntu，Python 3.12.3，独立 .venv。
这里记录实际执行结果，未列为通过的外部系统不因接口或文件存在而视为已验证。

## 已执行

| 检查 | 命令/方法 | 结果 |
| --- | --- | --- |
| 依赖安装 | pip install -e ".[dev,persistence]" | 成功 |
| 依赖一致性 | python -m pip check | No broken requirements found |
| 测试集 | python -m pytest -q | **48 passed** |
| 五类合成查询 | python examples/demo.py --output artifacts/demo.json | 全部 completed |
| 本地持久恢复 | 关闭 Runtime/SQLite 连接后创建新 Runtime，再恢复提案 | completed，trace 一致 |
| 拒绝与重放 | 合成演示和控制流测试 | 拒绝不执行查询；回放生成新 trace 和审批 |
| 本地 HTTP 协议 | tests/test_http_integration.py | 模型兼容端点 + VIDEO 桩端点真实 localhost HTTP 通过 |
| CLI 启动 | python scripts/verify_local_server.py | 自有子进程启动、health 与合成 chat 通过，结束后清理进程 |
| 构建 | python -m build | sdist、wheel 成功 |
| wheel 资源与运行 | scripts/verify_wheel.py dist/*.whl | 临时安装目标中加载五个技能及 51 条合成数据，查询通过 |
| 真实模型工具调用 | 已有 Ollama 的 qwen3-vl:8b | 返回 get_face_overview 调用 |
| 真实模型图执行 | examples/smoke_model.py | 审批恢复、51 条合成数据、模型审核报告，completed |
| 离线容器构建 | deploy/Dockerfile.offline，缓存 Python 3.11 | 构建成功，容器 pip check 通过 |
| Nginx 容器与路由 | Nginx 1.25、隔离 Docker network | nginx -t、health、chat/resume 通过 |
| 容器与真实模型 | Nginx → Agent → qwen3-vl:8b | 合成数据审批恢复与报告 completed，57.52 秒 |
| 同容器重启 | 重启本次 Agent 容器，再经 Nginx 获取运行状态 | SQLite 中 completed 状态及 51 条合成统计保留 |
| 实际 VIDEO 与 PostgreSQL | WSL 平台原 Blueprint + 已停平台库的隔离快照 | overview/activity 与直接聚合一致，人员/人脸均为 0 |
| 实际模型与 VIDEO 链路 | Qwen → 审批恢复 → VIDEO → PG → 审核报告 | completed，52.71 秒，仅空数据 |
| 只读宿主边界 | 无令牌、人员/图片禁用、数据库只读事务 | 401/403，数据库拒绝 UPDATE；非生产租户授权证明 |

测试覆盖：字段映射、工具与参数拒绝、零历史配置、统计复算、租户/用户会话隔离、
审批摘要与重复提交、SQLite 运行重建、历史分叉、轮数边界、失败状态与审计、
图片先审批及 checkpoint 无原图、重启图片失效、偏好白名单/删除/到期、
MCP Schema/同名工具/错误/远程引用限制、API 响应契约和宿主身份。

wheel 验证使用临时安装目录并断言导入位置，不从源码目录加载组件；第三方依赖复用已验证环境，
不是另一套完全独立的依赖环境。Python 3.11 的 GitHub Actions 矩阵已配置，尚未在远端运行。

## 可复算结果

合成档案 3 人，抓拍 51 条。两期记录 17 → 34，增加 17 条；
相同约 7 天窗口，日均约 2.43 → 4.86。所有身份与摄像头均为 demo 标记。
完整本地输出在忽略提交的 artifacts/demo.json，摘要见 examples/DEMO_OUTPUT.md。

## 未验证/待外部条件

- 完整 VIDEO 服务恢复、实时数据库、非空人脸数据与行级授权；实际 VIDEO 代码配合真实 PG 快照的空数据联调已通过。见 LIVE_INTEGRATION.md。
- 真实人脸检测/特征/Faiss/MinIO 与平台 Vue 展示；仍属于平台。
- 在线 Dockerfile 与 docker compose 构建：服务器的镜像源/依赖源证书失败；已在服务器通过 Python 3.11 离线镜像和 Nginx 容器运行检查，WSL 本机仍无 Docker/Nginx。
- 多 worker/多实例并发、负载、长时间运行、依赖漏洞审查和生产数据保留策略。
- 自主多 Agent 群、完整 MCP 传输实现、语义长期记忆和 RCVR 研究闭环。
- 适用 LICENSE 和第三方权属审核；用户已指定 GitHub 源码展示仓库，公开展示不自动授予开源许可。

requirements-dev.lock 记录本次 Python 3.12 环境的解析版本，用于本地复现参考，
不要直接替换平台 GPU/旧服务环境，也不声称已验证所有 Python 3.11 组合。

工程验证通过不自动解决公开权属。公开前按 PUBLICATION_CHECKLIST.md 完成其余事项。
