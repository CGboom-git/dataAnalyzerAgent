# 实际联调记录与复现

日期：2026-10-26。此记录区分真实模型、合成数据、VIDEO 服务和部署检查。

## 模型：真实 Qwen 已通过

从 WSL 的组件环境连接已有 Ollama OpenAI 兼容接口，模型为 qwen3-vl:8b。
先验证真实模型返回 get_face_overview 工具调用，再运行 examples/smoke_model.py：

- 模型规划查询；
- LangGraph 暂停审批；
- 确认当前提案后恢复；
- 合成仓库执行查询，51 条记录；
- 模型参与证据审核和报告，状态 completed。

检查名 live_model_synthetic_video，passed=true。这个检查没有调用真实 VIDEO，
没有读取真实人员或图片，不能作为图像理解或真实人脸检索的证明。

~~~bash
export AGENT_MODEL_BASE_URL='<已授权模型服务的兼容 API 根地址>'
export AGENT_MODEL_NAME='qwen3-vl:8b'
# 根据宿主要求设置 AGENT_MODEL_API_KEY；私有地址按本机代理策略设置 NO_PROXY。
python examples/smoke_model.py
~~~

smoke_model 明确使用合成数据与临时内存状态；它只对本地合成查询自动确认审批。
真实 VIDEO 检查 examples/smoke_live.py 不会自动批准工具执行。

## VIDEO：第一轮发现的阻塞

- 检查时 WSL 未运行平台 VIDEO、AI、Qwen 服务，也没有 Docker/Nginx 命令。
- 原服务器 VIDEO 标准端口未监听，平台界面标准端口也未监听。
- 原服务器现有目录未发现组件所需的 app/blueprints/face_analysis.py；WSL 平台存在该模块。
- WSL 配置的数据端点在本次短时连接检查中未成功连接。

因此没有获得真实 VIDEO 查询通过的结果，也没有启动平台完整 run.py：
该启动入口包含数据库和后台任务初始化，不适合仅为只读联调直接执行。
下一步应恢复现有平台服务或确定新的部署位置，核对人脸分析路由、委托身份和数据授权，
再执行 overview 只读检查。不同版本的接口不能仅通过更换地址视为兼容。

## VIDEO：第二轮只读恢复与实际查询通过

进一步确认原平台 PostgreSQL 容器自 2026-08-05 停止；原端口被另一个项目占用。
没有重启该容器、替换其他项目服务或对原数据库执行迁移。
复制已停止数据库目录得到约 300 MB 隔离快照，使用缓存的同版本 PostgreSQL 16 启动，
数据库监听仅限服务器 loopback，经 SSH 转发接到 WSL。

WSL 通过 examples/platform_readonly_host.py 加载平台原有的 models.py 与
face_analysis Blueprint。没有复制平台代码进公开仓库，也没有导入会建表/启动后台任务的 run.py。
这个入口只是集成验证宿主，不能代替完整 VIDEO 部署。

实际通过的检查：

- PostgreSQL transaction_read_only=on；对 WHERE false 的 UPDATE 也被只读事务拒绝，无数据修改。
- 实际 VIDEO overview/activity HTTP 路由查询成功，与数据库直接聚合一致。
- 未授权请求返回 401；人员明细/图片路由禁用，返回 403；Agent 图片输入禁用。
- 真实 qwen3-vl:8b → LangGraph → 审批暂停/恢复 → 实际 VIDEO → PostgreSQL 快照 → 审核报告，completed。
- 整条模型查询约 52.71 秒；不是离线规则模型，也不是模拟 VIDEO HTTP 桩。

该快照有 15 台设备，但人员 0、人脸记录 0。因此这次证明实际接口、数据库与控制流连通，
只覆盖空数据情形；不证明非空数据分析、轨迹质量、人脸识别/图像搜索、数据新鲜度或生产租户授权。
集成宿主使用单个受信任操作员 token，只是本地调用方认证，不是行级权限验证。
原完整平台服务仍未恢复；该快照也不能称为当前线上实时库。

复现宿主需要组件可选依赖和外部平台源码：

~~~bash
python -m pip install -e '.[persistence,platform-probe]'
# 仅用明确授权的只读数据库；connection.json 与 token 不得提交。
export AGENT_INTEGRATION_TOKEN='<本机随机生成的至少 32 字符私有令牌>'
python examples/platform_readonly_host.py --platform-root /path/to/platform \
  --db-config /private/path/connection.json --port 18765
~~~

私有数据库 JSON 字段：host、port、user、password、dbname。使用自己的服务地址与模型环境变量，
向接口传 Authorization: Bearer 令牌。宿主仅绑定 127.0.0.1，禁止把它当作生产认证网关。

## 离线容器构建

服务器访问 Docker Hub/PyPI 时证书校验失败。未关闭 TLS 校验。
提供 deploy/Dockerfile.offline，以已有受信任基础镜像和预下载 wheelhouse 构建。
默认基础镜像仍是 Python 3.12；PYTHON_BASE 可选择项目支持的 Python 3.11。

~~~bash
python -m build
mkdir -p .local/offline/wheelhouse
python -m pip download --only-binary=:all: --python-version 3.11 \
  --implementation cp --abi cp311 \
  --platform manylinux_2_28_x86_64 --platform manylinux2014_x86_64 \
  --dest .local/offline/wheelhouse \
  'dist/easyaiot_face_analysis_agent-0.2.0-py3-none-any.whl[persistence]' gunicorn
cp deploy/Dockerfile.offline .local/offline/Dockerfile
docker build --build-arg PYTHON_BASE=python:3.11-slim \
  -t easyaiot-face-agent:local .local/offline
~~~

wheel 必须匹配目标 Python/ABI/平台；不要将本机虚拟环境直接复制进容器。
在线 Dockerfile 构建仍需修复宿主镜像源和依赖源的证书链。

### 本次实际执行结果

- 使用服务器已缓存的 Python 3.11 基础镜像，离线构建成功；没有关闭证书验证。
- 单独的 Docker network 内启动 Agent 和已有 Nginx 1.25 镜像，只在宿主 loopback 映射临时端口。
- nginx -t、容器内 pip check、经 Nginx 的 health 检查通过。
- 经 Nginx 发起 chat，真实 qwen3-vl:8b 生成工具调用，审批暂停并恢复，
  得到 completed 和正确的 51 条合成数据概况；全流程约 57.52 秒。
- 检查名 docker_nginx_live_qwen_synthetic_video，passed=true。
- 同一个 Agent 容器重启后，通过 Nginx 仍可读取 completed 状态与合成统计；
  这验证 SQLite 在该容器可写层保留，不等于删除并重建容器后的卷持久化测试。

这证明实际容器、反向代理、真实模型和组件控制流能够连通。
数据源为 synthetic_demo，仍未证明真实 VIDEO、宿主用户认证、真实图片能力或生产负载。
本次使用 docker run 隔离验证，没有执行平台 docker compose 或修改现有 Nginx 配置。
检查结束后清理本次创建的两个测试容器和专用 network；保留离线测试镜像及临时构建日志供复查。

## 请求等待时间

同步模型请求可能超过 Gunicorn 默认的 30 秒。两个 Dockerfile 已设置单 worker、600 秒 timeout，
Nginx 示例同样为 600 秒。这个设置覆盖本次检查，不是容量和极端参数的保证。
增加轮数/模型超时或用于多用户场景时，应重新设计任务队列/异步运行与超时预算。
不应为提高并发直接增加 worker：当前每会话锁在进程内，跨进程需要宿主管理单写者。
