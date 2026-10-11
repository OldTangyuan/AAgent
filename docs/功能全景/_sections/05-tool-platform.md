# 05 工具平台（tool_server + tool_provider）

本节的结论全部来自 `tool_server/` 与 `tool_provider/` 的源码逐行审计，并与 `docs/17-Tool Server设计.md`、`docs/18-Tool Server内核实现.md`、`docs/19-Workflow本地与远程Tool节点拆分.md` 交叉印证。凡是设计文档声称而代码未实现的，均在 `## 5.11 与设计文档的差异对照` 中逐条列出。

## 5.1 定位、进程边界与部署事实

| 维度 | 事实 | 依据 |
| --- | --- | --- |
| 两个独立进程/镜像 | `tool_server`（FastAPI + uvicorn，端口 8083）与 `tool_provider`（纯 Python 线程进程，无 HTTP 端口） | `tool_server/Dockerfile:10`、`tool_provider/Dockerfile:14` |
| Tool Server 职责 | 工具目录、Provider 连接、任务状态机、等待与 callback 投递；**不执行工具** | `tool_server/main.py:180-330` |
| Tool Provider 职责 | 工具实现、注册、心跳、内部有界队列、Consumer 并发、结果回传 | `tool_provider/runtime.py:19-247` |
| 传输方向 | Provider → Server 单条 WebSocket 长连接（`/ws/providers`）；调用方 → Server 同步 HTTP | `tool_server/main.py:299`、`agent/tool_server_client.py:31-35` |
| 单实例调度权威 | 注册表 `ProviderRegistry._providers` 是**进程内内存 dict**，无 Redis 共享；多实例 Tool Server 会各自持有不同工具子集 | `tool_server/provider_registry.py:22-23` |
| 跨进程共享状态 | 仅 Redis（任务、通知、callback outbox、providers 快照 Hash）与 MongoDB（任务日志） | `tool_server/main.py:44-48` |
| 认证 | **全链路无认证**：HTTP 无鉴权头、WS 无握手凭据、callback queue 由调用方任意指定 | `tool_server/main.py:169-330` 全文无 auth 代码 |
| 安全响应头 | 所有 HTTP 响应统一加 CSP/`Cache-Control: no-store`/`nosniff`/`X-Frame-Options: DENY`/`no-referrer` | `tool_server/main.py:169-177` |
| 健康检查 | `/api/health` 同时 ping Redis 与 Mongo `admin.command("ping")`；compose healthcheck 依赖它 | `tool_server/main.py:180-186`、`docker-compose.yml:184-188` |
| 启动/关闭钩子 | lifespan 里建 Mongo 索引、起 callback worker；关闭时 cancel worker、关 Redis、关 Mongo | `tool_server/main.py:152-163` |

## 5.2 代码地图与依赖

| 文件 | 行数 | 角色 |
| --- | --- | --- |
| `tool_server/main.py` | 330 | FastAPI 应用、全部路由、WS 处理、callback worker、启动钩子 |
| `tool_server/models.py` | 57 | Pydantic 协议模型（ToolSchema/RegisterMessage/CallbackSpec/ToolCallRequest/ProviderEvent） |
| `tool_server/settings.py` | 50 | 冻结 dataclass + `from_env()` 环境变量解析 |
| `tool_server/provider_registry.py` | 117 | 内存注册表、连接对象、发送队列与 writer 任务 |
| `tool_server/task_store.py` | 155 | Redis 任务仓储、Lua 原子状态迁移、阻塞等待 |
| `tool_server/task_log_repository.py` | 71 | MongoDB 任务日志（索引、写入、最近列表、最新快照） |
| `tool_server/static/index.html` | 115 | 控制台页面骨架（三个面板 + 两个 dialog） |
| `tool_server/static/console.js` | 365 | 控制台全部渲染与交互逻辑 |
| `tool_server/static/auto-refresh.js` | 24 | 定时器/暂停按钮的自动刷新调度器 |
| `tool_server/static/css/base.css`、`tool-server.css` | 36 / 136 | 全局骨架样式与页面/弹窗/Schema 树样式（含 3 个响应式断点） |
| `tool_server/test_task_store.py` | 72 | 4 个用例：create/transition 的任务日志写入语义 |
| `tool_server/test_task_log_repository.py` | 62 | 3 个用例：`list_recent` 聚合管道、`get_latest` |
| `tool_provider/main.py` | 39 | 入口：读环境变量、`discover`、`start`、阻塞 join |
| `tool_provider/runtime.py` | 247 | ToolProvider：连接会话、心跳、事件队列、Consumer、结果校验与回传 |
| `tool_provider/tool.py` | 35 | `Tool` ABC、`ToolContext`、`schema()` 组装 |
| `tool_provider/tools/system.py` | 23 | `system.echo` |
| `tool_provider/tools/qq.py` | 64 | `qq.send_group_msg`、`qq.send_private_msg` |
| `tool_provider/tools/qqapi.py` | 36 | QQ HTTP API 客户端（供 qq.py 使用，本身不是工具模块） |
| `tool_provider/tools/bilibili.py` | 158 | B 站下载→转 mp3→ASR；短链转 BV 号 |
| `tool_provider/tools/documents.py` | 266 | 7 个 MongoDB 文档工具 + 模块级 MongoClient |
| `tool_provider/README.md` | 91 | 工具开发规范（含 `x-workflow-port-type` 约定） |
| `tool_provider/requirements.txt` | 5 | `jsonschema`、`websocket-client`、`requests`、`pydub`、`pymongo`（均未锁版本） |
| `tool_server/requirements.txt` | 5 | `fastapi==0.116.1`、`jsonschema==4.25.1`、`pymongo==4.13.2`、`redis==6.2.0`、`uvicorn[standard]==0.35.0` |

## 5.3 协议数据模型（`tool_server/models.py`）

| 模型 | 字段与约束 | 位置 |
| --- | --- | --- |
| `ToolSchema` | `name` 正则 `^[A-Za-z0-9_-]+\.[A-Za-z0-9_.-]+$` 且 ≤128；`description` ≤4096；`inputSchema`/`outputSchema` 任意 dict；`annotations` dict；`extra="forbid"` | `models.py:6-13` |
| `RegisterMessage` | `type` 常量 `"register"`；`provider_id` 1..128；`revision` ≥1；`tools` ≤256 项；`extra="forbid"` | `models.py:16-22` |
| `CallbackSpec` | `type` 常量 `"redis"`；`queue` 1..256；`event_type` 1..128；`on` ⊆ `{working,completed,failed}`，1..3 项，默认全集 | `models.py:25-35` |
| `ToolCallRequest` | `arguments` dict；`mode` ∈ `{wait,async}` 默认 `wait`；`timeout_ms` ≥1 默认 30000；`callback` 可空；`extra="forbid"` | `models.py:38-44` |
| `ProviderEvent` | `type` ∈ `{accepted,rejected,status,result,pong,ping}`；`task_id`/`status`/`message`/`success`/`output`/`error` 可空；`progress` 0..1；**`extra="allow"`** | `models.py:47-57` |

注意两点协议不对称：`ProviderEvent` 允许额外字段（向前兼容），而 `RegisterMessage`/`ToolCallRequest`/`ToolSchema` 一律 `extra="forbid"`（多一个字段即整条消息 422/关闭连接）。

## HTTP 接口全表

共 **8 个显式注册端点（7 个 HTTP + 1 个 WebSocket）**，外加 1 个挂在 `/` 的静态目录。全部无鉴权。

| # | 方法 | 路径 | 参数 | 成功响应 | 错误响应 | 用途 | 位置 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | GET | `/api/health` | — | `200 {"status":"ok"}` | `503 {"status":"unavailable","error":str}` | Redis + Mongo 双探活 | `main.py:180-186` |
| 2 | GET | `/api/tools` | — | `200 {"tools":[ToolSchema + provider_id + revision]}`，按工具名排序 | — | 远程工具目录（Workflow 编辑器经 `workflow_editor` 代理后使用） | `main.py:189-191`、`provider_registry.py:78-88` |
| 3 | GET | `/api/overview` | query `limit`（默认 100，`max(1,min(limit,200))` 截断） | `200 {providers, tools, tasks, summary{providers,tools,tasks,statuses{pending,working,completed,failed}}, fetched_at}` | — | 控制台单次聚合拉取（前端固定 `limit=100`） | `main.py:194-217`、`console.js:249` |
| 4 | GET | `/api/tools/{tool_name}` | path `tool_name` | `200 ToolSchema` | `404 {"detail":"tool not found"}` | 单工具元数据（含 inputSchema/outputSchema，供控制台 Schema 树渲染） | `main.py:220-225` |
| 5 | POST | `/api/tools/{tool_name}/calls` | body `ToolCallRequest` | `200` 终态任务 / `202` 任务快照（异步或未派发/等待超时） | `400` callback 类型不允许；`422` 入参不合 Schema；`409` task_id 冲突；`503` 工具不可用 | 同步调用 / 异步提交 / 回调提交（三合一） | `main.py:228-280` |
| 6 | GET | `/api/task-logs/{task_id}` | path `task_id` | `200` Mongo 中最新任务快照 | `404 {"detail":"task log not found"}` | 控制台任务详情（历史快照，可跨 Redis TTL） | `main.py:283-288` |
| 7 | GET | `/api/tasks/{task_id}` | path `task_id` | `200` Redis 实时任务 | `404 {"detail":"task not found"}` | 权威实时状态查询（供异步轮询） | `main.py:291-296` |
| 8 | WS | `/ws/providers` | 首帧 `RegisterMessage`，后续 `ProviderEvent` | `registered` / `pong` / `invoke` | 关闭码 `1008` + 原因（校验失败） | Provider 控制通道（注册/心跳/派发/回传） | `main.py:299-326` |
| — | GET | `/`（StaticFiles，`html=True`） | — | `index.html`、`/console.js`、`/auto-refresh.js`、`/css/*` | — | 控制台静态资源 | `main.py:329-330` |

### `POST /api/tools/{tool_name}/calls` 的判定顺序（按代码执行序）

| 序 | 条件 | 结果 | 位置 |
| --- | --- | --- | --- |
| 1 | `registry.get_tool` 返回 None | `503 "tool provider is unavailable"`（**工具名不存在也返回 503，不返回 404**） | `main.py:230-232` |
| 2 | `callback.event_type` 不在 `settings.callback_event_types` | `400 "callback event type is not allowed"` | `main.py:233-234` |
| 3 | `check_schema(tool.inputSchema)` 或参数校验失败 | `422` + jsonschema 异常字符串 | `main.py:235-239` |
| 4 | Redis `SET NX` 失败（task_id 冲突） | `409 "task id collision"` | `main.py:255-256` |
| 5 | 生成 task，`provider_id` 由 `next(...)` 从 `list_tools()` 反查并写入 | 任务进入 `pending` | `main.py:241-260` |
| 6 | `registry.send` 入队失败 | 回写 `provider_id: null` | `main.py:271-272` |
| 7 | `mode=="async"` 或未派发 | `202` + 任务快照 | `main.py:274-276` |
| 8 | `mode=="wait"` 且已派发 | `wait_for_terminal(min(timeout_ms, max_wait_ms)/1000)`；终态 `200`，否则 `202` | `main.py:278-280` |

要点：`deadline` 用的是**未截断**的 `request.timeout_ms`（`main.py:268`），而等待上限用截断后的 `min(timeout_ms, TOOL_MAX_WAIT_MS)`（`main.py:278`）——Provider 侧看到的期限长于服务端等待窗口，这是有意的（`docs/审查日志/2026-10-11-全项目-审查报告.md:89` 已确认为一致行为）。

## 5.4 WebSocket 协议（`/ws/providers`）

### 5.4.1 握手与注册

| 阶段 | 消息 | 结构与约束 | 位置 |
| --- | --- | --- | --- |
| 服务端 | `accept()` 后 `asyncio.wait_for(receive_json(), timeout=10)` | **10 秒注册超时**，超时走 `asyncio.TimeoutError` 分支静默关闭 | `main.py:301-304`、`main.py:321` |
| Provider → Server | `{"type":"register","provider_id":str,"revision":int≥1,"tools":[ToolSchema...]}` | `extra="forbid"`；`tools` ≤256；每个工具的 `inputSchema`/`outputSchema` 都做 `Draft202012Validator.check_schema` | `models.py:16-22`、`main.py:305-308` |
| 注册表校验 | `revision` 必须**严格大于**同 provider_id 现存连接的 revision；工具名不得被**其他** provider 占用 | 违规抛 `ValueError` → `1008` 关闭 | `provider_registry.py:26-36` |
| 幂等替换 | 同 provider_id 重注册成功时，先 `_remove_locked` 旧连接（弹出注册表、`outgoing.put(None)` 终止旧 writer 任务） | 支持 Schema 更新与重连 | `provider_registry.py:37-52`、`provider_registry.py:59-64` |
| Server → Provider | `{"type":"registered","provider_id":...}` | Provider 侧必须收到它，否则抛 `ValueError("registration rejected: ...")` | `main.py:310`、`runtime.py:127-129` |
| Server → Redis | `HSET tool:providers <provider_id> <RegisterMessage 全量 JSON>`；断开时 `HDEL` | **只写不读**：全仓无任何读取方 | `main.py:311-315`、`main.py:326` |

### 5.4.2 心跳与在线状态

| 项 | 事实 | 位置 |
| --- | --- | --- |
| Provider → Server | 每 `TOOL_PROVIDER_HEARTBEAT_SECONDS`（默认 20s）发 `{"type":"ping"}` | `runtime.py:132-137`、`main.py:29` |
| Server → Provider | 收到 `ping` 即向该连接 `outgoing` 队列投 `{"type":"pong"}` | `main.py:83-85` |
| Provider 收 `pong` | 主循环 `_handle_message` **不识别 `pong`**（静默忽略，无分支） | `runtime.py:157-164` |
| 反向心跳 | Server 从不主动 ping；协议允许 Server 发 `ping`，Provider 回 `pong`（`runtime.py:163-164`），但服务端无任何发起方 | `runtime.py:163-164` |
| 在线判定 | **没有超时判定**。在线 == 注册表内有该连接对象；只靠 TCP 断开触发 `finally` 注销 | `main.py:323-326` |
| 无响应连接的后果 | 半开连接（对端假死不 close）不会被清退，工具继续显示在线，任务可被派发进队列后永无结果，直到任务 TTL（默认 86400s） | `provider_registry.py:66-76`、`task_store.py:143-155` |
| 连接异常 | `(WebSocketDisconnect, asyncio.TimeoutError)` 静默；`(PydanticValidationError, SchemaError, ValueError)` → `close(1008, reason=str(error)[:120])`；`jsonschema.ValidationError` **不在捕获列表**（见缺陷 D1） | `main.py:319-322` |

### 5.4.3 任务下发消息

```json
{"type":"invoke","task_id":"<32位hex>","tool":"<domain.action>",
 "arguments":{...},"deadline":"<ISO8601 UTC>"}
```

位置：`main.py:261-270`。注意 `deadline = now + request.timeout_ms`（`main.py:268`）。Provider 侧 `_handle_message` 只处理 `invoke`/`cancel`/`ping`，其余类型静默丢弃（`runtime.py:157-164`）。协议允许但**服务端从不发送** `invoke` 之外的 `cancel`。

### 5.4.4 结果回传消息

Provider → Server 的事件集（`models.py:47-57`）：

| `type` | 附加字段 | 服务端处理与状态迁移 | 位置 |
| --- | --- | --- | --- |
| `accepted` | `task_id` | 期望 `{pending}` → `working`，触发 callback | `main.py:98-100` |
| `rejected` | `task_id`,`message` | 期望 `{pending}` → 回 `pending` 且 `provider_id=null`，**不触发 callback** | `main.py:101-106` |
| `status` | `task_id`,`status`（必须为 `"working"`）,`progress`,`message` | 期望 `{working}` → 更新 `progress`/`message`，触发 callback；`status != "working"` 抛 `ValueError` → 关连接 | `main.py:107-111` |
| `result` | `task_id`,`success`,`output`,`error` | `success` 缺失抛 `ValueError`；`success=true` → 用 `outputSchema` 校验后 `completed`；`false` → `failed` + `error` | `main.py:112-121` |
| `ping` | — | 回 `pong` | `main.py:83-85` |
| `pong` | — | 忽略 | `main.py:86-87` |

通用前置检查（`main.py:88-96`）：除 ping/pong 外必须有 `task_id`（否则 `ValueError` → 关连接）；任务不存在只记 `warning` 并返回（幂等丢弃）；`task["provider_id"] != connection.provider_id` 抛 `ValueError` → 关连接。

### 5.4.5 断线、重连与清理

| 侧 | 行为 | 位置 |
| --- | --- | --- |
| Server 侧清理 | `finally` 中 `registry.unregister(connection)`（仅当注册表里仍是同一个连接对象）+ `HDEL tool:providers <provider_id>` | `main.py:323-326`、`provider_registry.py:54-57` |
| Server 侧不做的 | 不失败该 Provider 在飞的任务、不重路由、不记任务日志；`pending`/`working` 任务原地等 TTL | `main.py:323-326` 无任务处理 |
| Provider 重连 | 外层 `while not _stop_event` 循环捕获 `(OSError, TimeoutError, ValueError, WebSocketConnectionClosedException, WebSocketTimeoutException)`，退避 `1→2→4→…→30s` 封顶；连上并注册成功后重置为 1s | `runtime.py:90-101` |
| Provider 注册被拒 | 服务端返回非 `registered` 时抛 `ValueError`，被同一退避循环接住 → 无限重试。**若服务端残留同 provider_id 且 revision ≥ 新连接 revision 的旧连接，将永久重试失败**（`TOOL_PROVIDER_REVISION` 是静态配置，不会自增） | `runtime.py:127-129`、`provider_registry.py:29-30` |
| Provider 收尾 | `finally` 中置 `_websocket=None` 并 `close()`；`stop()` 置 stop 事件、置所有 cancellation、close socket、join 主线程 | `runtime.py:145-147`、`runtime.py:106-115` |
| Consumer 退出 | 主线程 finally 里对每个 consumer `join(timeout=5)`；consumer 靠 `tasks.get(timeout=0.5)` 轮询 stop 标志退出 | `runtime.py:102-104`、`runtime.py:192-200` |
| Provider 心跳期间的事件冲刷 | 每次主循环迭代先 `_flush_events` 把 `events` 队列排空发送，再判断是否需要发 ping，再 `recv()`（socket timeout=1s，`WebSocketTimeoutException` 即 continue 形成 1s tick） | `runtime.py:133-144`、`runtime.py:148-155` |

### 5.4.6 并发控制与队列

| 队列 | 位置 | 容量 | 满时行为 |
| --- | --- | --- | --- |
| Server 每连接 outgoing 队列 | `provider_registry.py:40` | **1024**（硬编码） | `send()` 用 `put_nowait`，`QueueFull` → 返回 `False` → `call_tool` 把 `provider_id` 置空并返回 `202` | 
| Server writer 任务 | `provider_registry.py:47`、`:108-117` | 每连接 1 个 | 由 `None` 哨兵终止 |
| Provider 内部任务队列 | `runtime.py:35` | `TOOL_PROVIDER_QUEUE_SIZE`，默认 **128** | `put_nowait` → `QueueFull` → 回 `rejected "provider queue is full"` 并清理 cancellation |
| Provider Consumer 线程 | `runtime.py:83-88`、`runtime.py:38` | `max(1, TOOL_PROVIDER_CONSUMERS)`，默认 **1** | 每 Consumer 同时执行 1 个任务，**最大执行并发 = Consumer 数** |
| Provider 事件队列 | `runtime.py:36` | 无界 `queue.Queue()` | 无背压（进度上报过密会占内存） |
| 全局并发上限 | 无。不同 Provider 之间独立；同 Provider 只受上述两个队列约束 | — | — |

## 5.5 任务生命周期

### 5.5.1 状态机

```
create ──► pending ──accepted──► working ──result(success)──► completed  (终态)
              │  ▲                  │
              │  └──rejected───────┘ (回到 pending, provider_id=null)
              │                     └──result(failure)────► failed      (终态)
              └── 派发失败 / mode=async / 等待超时 ──► 保持 pending
```

| 状态 | 定义 | 进入条件 | 位置 |
| --- | --- | --- | --- |
| `pending` | 已创建、等待/正在派发 | `store.create()`；`rejected`；派发失败回滚 | `main.py:247`、`main.py:105`、`main.py:272` |
| `working` | Provider 已接单执行中 | `accepted`（期望 `pending`）；`status`（期望 `working`） | `main.py:99`、`main.py:110` |
| `completed` | 终态，结果不可变 | `result` 且 `success=true`（期望 `{pending,working}`） | `main.py:119`、`main.py:73-79` |
| `failed` | 终态，错误不可变 | `result` 且 `success=false` | `main.py:121` |

终态不可变由 Lua 脚本保证：状态为 `completed`/`failed` 时任何写入直接返回 `{0,'terminal'}`（`task_store.py:20-22`）。期望状态不匹配返回 `{0,'conflict'}`（`task_store.py:32-34`）。**每次 transition 的返回值都被调用方忽略**（`main.py:74-79`、`main.py:100-121` 均未检查 `changed`），因此冲突/终态拒绝是静默的、不产生任何日志（缺陷 D10）。

缺失的状态：**没有 `cancelled`、`timeout`、`expired` 状态**，也没有任何看门狗把 `working` 任务推进到终态。`expires_at` 字段被写入任务记录（`main.py:250`）但全代码无任何读取方——过期只由 Redis 原生 TTL 实现。

### 5.5.2 `task_id` 生成

`task_id = uuid.uuid4().hex`（32 位小写十六进制，无连字符），`main.py:241`。设计文档示例写的是 `"01J..."`（ULID/UUIDv7 风格），实现是 v4 随机串，与此不同但语义等价。冲突时 `SET NX` 失败返回 `409`（`main.py:255-256`）。

### 5.5.3 同步等待机制

| 步骤 | 实现 | 位置 |
| --- | --- | --- |
| 通知队列 | `tool:task:{task_id}:updates`（List） | `task_store.py:73-75` |
| 写入方式 | Lua 中 `LPUSH updates <新状态>` + `LTRIM 0 0` + `EXPIRE ttl`：**只保留最新 1 个信号**，与任务同 TTL | `task_store.py:44-46` |
| 等待方式 | `redis.blpop(updates_key, timeout=remaining)`——**事件驱动，无固定轮询间隔** | `task_store.py:155` |
| 循环 | ①`GET` 任务；②为 None 或终态 → 返回；③算剩余时间，≤0 → 再 `GET` 一次并返回；④`BLPOP` 唤醒后回到 ① | `task_store.py:147-155` |
| 超时上限 | `min(request.timeout_ms, settings.max_wait_ms)`（默认 30000ms） | `main.py:278` |
| 语义约束 | 一条 List 信号只唤醒一个 `BLPOP`；**每任务只允许一个阻塞等待者**（多调用方需自行轮询 `GET /api/tasks/{id}`） | `docs/18:104`、`task_store.py:155` |
| 超时返回值 | `202 + 任务快照`（任务继续在服务端执行，不会取消） | `main.py:280` |

### 5.5.4 结果存储与过期清理

| 项 | 事实 | 位置 |
| --- | --- | --- |
| 权威存储 | Redis String `tool:task:{task_id}`，值为任务 JSON（`ensure_ascii=False`） | `task_store.py:70-71`、`task_store.py:78-84` |
| 结果字段 | `result`（成功时 `output` 原文）/`error`（失败时为 `{"code": 异常类名, "message": str(error)}`） | `main.py:119-121`、`runtime.py:242-247` |
| 大结果外置 | **未实现**。设计文档要求大结果存外部存储、任务记录只留引用（`docs/18:121`），代码把结果直接内联进 Redis String | `task_store.py:78` |
| 过期 | Redis `EX` = `TOOL_TASK_TTL_SECONDS`（默认 86400s），每次 transition 刷新 TTL | `task_store.py:43` |
| 最近索引 | ZSET `tool:tasks:recent`（member=task_id，score=created_at 时间戳）；`create` 时 `ZREMRANGEBYSCORE -inf (created_at-ttl)` 懒清理 | `task_store.py:88-89` |
| 孤儿成员清理 | `list_recent` 读到已过期的 id 时 `ZREM` 掉 | `task_store.py:106-108` |
| Mongo 日志 | 每次 `create` 与每次**成功** transition 各插一条文档（含完整任务快照）；**无 TTL 索引**，永久增长 | `task_log_repository.py:27-39`、`task_store.py:90-91`、`task_store.py:139-140` |
| 无后台清理任务 | 全服务只有 1 个后台任务（callback worker），没有任务 reaper / 索引重建定时器 | `main.py:155` |

## 5.6 回调（callback）机制

### 5.6.1 请求契约与准入

| 项 | 事实 | 位置 |
| --- | --- | --- |
| 结构 | `{"type":"redis","queue":key,"event_type":str,"on":["working","completed","failed"]}` | `models.py:25-35` |
| `type` | 只接受字面量 `"redis"`——其他 sink 类型无法通过校验（扩展点见 `## 扩展槽`） | `models.py:28` |
| `queue` | 任意 1..256 字符字符串，**无白名单、无 key 格式校验**（设计文档要求校验 key 格式，未实现） | `models.py:29` |
| `event_type` | 必须在 `TOOL_CALLBACK_EVENT_TYPES` 内（默认仅 `async_result`），否则 `400` | `main.py:233-234`、`settings.py:33-37` |
| `on` | 缺省为三个状态全开 | `models.py:31-35` |
| 保存位置 | 整个 callback 对象 `model_dump()` 后存进 `task["callback"]` | `main.py:253` |

### 5.6.2 outbox 结构与投递链

```text
状态迁移(Lua)                      callback_worker(main.py:124-149)
  ├ SET task (EX ttl)              ├ 启动: LRANGE processing 0 -1
  ├ LPUSH updates + LTRIM          │        → 逐条 LPUSH 回 outbox + DEL processing
  └ LPUSH tool:callback:outbox     ├ BRPOPLPUSH outbox → processing (timeout=5)
      {"queue":k,"event":{...}}    ├ LPUSH <queue> <event JSON>
                                   ├ LREM processing 1 <item>
                                   └ 异常: LREM + LPUSH 回 outbox + sleep 1s
```

| 项 | 事实 | 位置 |
| --- | --- | --- |
| 入队点 | 与状态写入在**同一个 Lua 脚本**内完成（`ARGV[5]` 非空时 `LPUSH tool:callback:outbox`），天然「状态已改必有 outbox 记录」 | `task_store.py:47-49` |
| 已处理队列 | `tool:callback:processing`（List），实现「至少一次」的关键 | `main.py:126` |
| 启动恢复 | 把 processing 中残留条目全部搬回 outbox 后 `DEL processing`，用事务 pipeline 保证 | `main.py:127-133` |
| 投递动作 | 仅 `redis.lpush(record["queue"], json.dumps(event, ensure_ascii=False))`——**只做一次 LPUSH，不执行调用方提供的任何 Redis 命令** | `main.py:141` |
| 触发状态集合 | `CALLBACK_STATUSES = {"working","completed","failed"}`，脚本外再与 `task["callback"]["on"]` 求交 | `main.py:49-70` |
| 事件 payload | `{task_id, tool, status, result, error, progress, message}`——**全部由服务端从任务记录生成** | `main.py:56-69` |
| 重试 | 只捕 `(KeyError, TypeError, ValueError, RedisError)`；固定 `sleep(1)`，**无指数退避、无最大次数、无保留期限** | `main.py:143-149` |
| 投递语义 | 至少一次（BRPOPLPUSH + 失败回灌）；消费方需按 `task_id` 去重（文档 `docs/17:250` 已声明） | `main.py:136-148` |
| 失败分类缺陷 | Redis 连接整体不可用时，`lrem`/`lpush` 也会抛 `RedisError`，被包在同一个 `try` 之外 → 异常逃出 `callback_worker` **整个后台任务死亡**（`lifespan` 只在关闭时 cancel，不会重启） | `main.py:143-148` |

### 5.6.3 回调与调用模式的关系

- 回调**与 `mode` 无关**：`mode="wait"` 也照样投递 callback（`main.py:274` 只影响 HTTP 返回）。
- `working` 会触发**多次**回调（`accepted` 一次 + 每次 `status` 一次），实际是本系统的进度推送通道。
- `rejected` 不触发回调（目标状态是 `pending`，不在 `CALLBACK_STATUSES`）。
- 任务若因 Provider 消失而永久停留 `working`，则只有 `working` 回调、永无终态回调。
- `docs/18:123` 要求 outbox「保留到成功投递或超过明确的保留期限」——**保留期限未实现**，outbox 无 TTL，条目会无限堆积。

## 5.7 工具注册表

### 5.7.1 声明与发现

| 环节 | 机制 | 位置 |
| --- | --- | --- |
| 基类 | `Tool(ABC)`，类属性 `name`/`description`/`input_schema`/`output_schema`/`annotations`，抽象方法 `execute(arguments, context)` | `tool.py:17-35` |
| 装饰器 | **无**。没有 `@tool` 装饰器、没有自动扫描包、没有纯声明式 YAML/JSON 注册 | `tool.py`、`runtime.py:45-59` |
| 发现方式 | `importlib.import_module(module_name)` → `inspect.getmembers(module, inspect.isclass)` → 过滤 `is Tool`、非 `Tool` 子类、`inspect.isabstract` → **无参实例化** | `runtime.py:45-59` |
| 模块清单 | 环境变量 `TOOL_MODULES`，逗号分隔，默认 `tools.system,tools.qq,tools.bilibili,tools.documents`；在 `main.py` 中剥空白并过滤空项 | `tool_provider/main.py:15-21` |
| 去重 | 同名工具（跨模块）直接 `raise ValueError("duplicate tool name: ...")`，进程启动即失败 | `runtime.py:54-56` |
| 空注册表 | `discover` 返回空 → `ValueError("no Tool subclasses discovered")` | `runtime.py:57-58` |
| 启动期校验 | 每个工具名必须含 `.`（否则 `ValueError`）；`input_schema`/`output_schema` 都必须通过 `check_schema`（2020-12） | `runtime.py:61-68` |
| 运行时双重校验 | Provider 收到 invoke 后校验 `input_schema`，执行后再校验 `output_schema` | `runtime.py:234`、`runtime.py:236` |
| Server 侧第三重校验 | `POST /calls` 用 `inputSchema` 校验参数；`result` 用 `outputSchema` 校验输出 | `main.py:236-237`、`main.py:117-118` |

### 5.7.2 工具元数据结构

`schema()` 产出的注册元数据（`tool.py:24-31`）→ 服务端 `ToolSchema`（`models.py:6-13`）：

| 字段 | 来源 | 说明 |
| --- | --- | --- |
| `name` | 类属性 | 必须 `domain.action`，服务端再限制字符集与长度 |
| `description` | 类属性 | ≤4096 |
| `inputSchema` | 类属性 `input_schema` | 命名映射差异：Provider 用 snake_case，协议用 camelCase |
| `outputSchema` | 类属性 `output_schema` | 同上；README 要求根为 object、声明 `required`、`additionalProperties:false` |
| `annotations` | 类属性 `annotations` | 默认 `{}`；MCP 风格 hints 预留位；**类级可变默认值被所有实例共享**（缺陷 D19） |

**没有** `sync`/`async` 标记：`execute` 一律是阻塞同步函数，一个 Consumer 线程跑一个任务；「同步/异步」只存在于**调用侧** `mode` 字段（`models.py:42`）。**没有**返回值类型标记：返回类型由 `output_schema` 与 `execute` 的 Python 注解共同表达，但注解不参与校验。

Workflow 端口类型靠 `x-workflow-port-type`（JSON Schema 扩展关键字，值 ∈ `content`/`message`/`list-content`/`list-message`）在 `outputSchema` 一级属性上声明，例如 `qq.py:22-26`、`bilibili.py:121`、`documents.py:63`。该字段**不参与** Tool Server 的 JSON Schema 校验（`docs/19:178`），只被 `workflow_editor` 消费。

### 5.7.3 远程与本地工具的区分

| 维度 | 本地工具 | 远程工具 |
| --- | --- | --- |
| 注册表 | Agent 进程 Redis Hash `aagent:tools`（`AGENT_TOOLS_KEY`），OpenAI Function `function.parameters` 结构 | Provider 内存注册表 → WS 注册 → `ProviderRegistry._tools`，`inputSchema` 结构 |
| 执行 | Agent 进程内 handler | Provider 进程内 Consumer 线程 |
| Workflow 节点 | `local_tool` | `remote_sync_tool` / `remote_async_tool` |
| 目录 API | `GET /api/tools/local` | `GET /api/tools/remote`（编辑器后端代理 Tool Server `/api/tools`） |
| 依据 | `docs/19:47-74`、`docs/19:232-236` | 同左 |
| 现状重叠 | `agent/tools/documents.py`、`agent/tools/qqapi.py`、`agent/tools/1.py` 是**已有远程实现之后残留的本地副本/试验脚本，全仓无 import 方**（`docs/审查日志/2026-10-11-全项目-审查报告.md:69`、`:111`） |

## 内置工具全表

`tools/` 下共 **12 个工具类**（4 个模块）。`tool_provider/tools/__pycache__/echo.cpython-312.pyc` 是**无源码的孤儿字节码**（全仓 `echo.py` 不存在），不计入。

| # | 工具名 | 用途 | 参数（`*` 为必填） | 返回值 | 位置 |
| --- | --- | --- | --- | --- | --- |
| 1 | `system.echo` | 原样返回输入值，调试 Tool 调用链路 | `value*`（任意 JSON） | `{value}` | `tools/system.py:6-23` |
| 2 | `qq.send_group_msg` | 发送 QQ 群消息 | `group_id*`(str), `message*`(str) | `{message_id:int}` | `tools/qq.py:7-34` |
| 3 | `qq.send_private_msg` | 发送 QQ 私聊消息 | `user_id*`(str), `message*`(str) | `{message_id:int}` | `tools/qq.py:37-64` |
| 4 | `bilibili.gain_content_from_bvid` | 下载 B 站视频音频 → 转 mp3 → ASR 转写文本 | `bvid*`(str) | `{text:str}` | `tools/bilibili.py:106-129` |
| 5 | `bilibili.shorturl_to_bvid` | 短链跳转后取末段作为 BV 号 | `short_url*`(str) | `{bvid:str}`（正则 `^BV[0-9A-Za-z]+$`） | `tools/bilibili.py:132-158` |
| 6 | `documents.query_by_name` | 按标题精确查询，返回**全部**同名文档 | `title*`(str, 1..200) | `{documents:[DOCUMENT]}` | `tools/documents.py:73-98` |
| 7 | `documents.query_by_id` | 按 ObjectId 查询单个文档 | `doc_id*`(str) | `DOCUMENT` | `tools/documents.py:101-113` |
| 8 | `documents.create` | 新建文档 | `title`(默认「未命名文档」,1..200), `content`(默认 `""`,≤1e6) | `DOCUMENT` | `tools/documents.py:116-152` |
| 9 | `documents.append` | 在文档末尾追加内容 | `doc_id*`, `append_content*`(str) | `DOCUMENT` | `tools/documents.py:155-181` |
| 10 | `documents.rewrite` | 整体重写文档内容 | `doc_id*`, `content*`(str,≤1e6) | `DOCUMENT` | `tools/documents.py:184-211` |
| 11 | `documents.rename` | 重命名文档 | `doc_id*`, `title*`(1..200) | `DOCUMENT` | `tools/documents.py:214-242` |
| 12 | `documents.pin` | 设置钉住状态 | `doc_id*`, `pinned*`(bool) | `DOCUMENT` | `tools/documents.py:245-266` |

`DOCUMENT` = `{id,title,content,pinned,created_at,updated_at}`，全字段 required、`additionalProperties:false`（`tools/documents.py:58-70`）。`content` 带 `x-workflow-port-type: content`。

| # | 工具 | 外部服务依赖 | 环境变量 | 错误处理 | 限制 |
| --- | --- | --- | --- | --- | --- |
| 1 | `system.echo` | 无 | 无 | 无（不会失败） | 无参数大小限制；`arguments` 全文走 WS+Redis，超大值会放大内存 |
| 2/3 | `qq.*` | QQ HTTP API（NapCat 类实现） | `QQ_API_BASE_URL`（**`os.environ[...]` 直接索引**）、`QQ_API_TOKEN` | `requests.raise_for_status()` 抛 `HTTPError`；JSON 缺 `data` 抛 `KeyError`；两者都被 runtime 兜底成 `failed` + `{"code":类名,"message":...}` | 单请求 `timeout=15`；无重试、无限流；缺环境变量时在**调用时**才 `KeyError`（非启动校验） |
| 4 | `bilibili.gain_content_from_bvid` | `api.bilibili.com`（view / wbi playurl）、音频 CDN、硬编码 ASR 服务 `https://frp-dry.com:63030/`（模型 `Qwen3-asr-1.7b-fp16`） | `BILIBILI_COOKIE`（默认空串）、`BILIBILI_DOWNLOAD_DIR`（默认 `/tmp/aagent-downloads`） | HTTP 非 2xx 抛 `HTTPError`；取消时抛 `RuntimeError("download cancelled")`；`view["data"]`、`streams[quality]["audio"][0]` 缺失抛 `KeyError`/`IndexError`/`max()` 空序列 `ValueError` | 下载分块 8KiB 并上报进度；支持 `Range` 断点续传（按 URL sha256 命名 `.m4s`）；**无文件大小上限、无并发限制**；mp3 固定 192k；ASR `timeout=(10,120)`；取消不删除半成品文件 |
| 5 | `bilibili.shorturl_to_bvid` | `b23.tv` 等短链服务 | `BILIBILI_COOKIE`（用于请求头） | `raise_for_status()` | 纯 `HEAD` 跟随重定向 `timeout=10`；把 URL 末段当 BV 号，**不校验结果形态**（响应 schema 有正则，会在 runtime 输出校验处失败） |
| 6-12 | `documents.*` | MongoDB | `MONGO_HOST`、`MONGO_PORT`、`MONGO_USER`、`MONGO_PASS`、`MONGO_DATABASE`、`MONGO_DOCUMENT_COLLECTION` | `_object_id` 对非法 id 抛中文 `ValueError`；文档不存在抛 `ValueError`；append 超长抛 `ValueError` | 标题 ≤200 字符、内容 ≤1,000,000 字符（`documents.py:11-12`）；`serverSelectionTimeoutMS=5000`；`query_by_name` **无 `limit`、无索引**（标题无索引，全集合扫描且返回全部命中） |

补充事实：

- `tools/documents.py` 的 `MongoClient` 是**模块级单例**，import 时即建立（`documents.py:14-30`），因此 Mongo 不可用时**不影响** Provider 启动，只在调用时超时 5s。
- 7 个 documents 工具中，`create`/`append`/`rewrite`/`rename` 会更新 `updated_at`，`pin` **不更新** `updated_at`（`documents.py:259-265`），是字段语义不一致点（缺陷 D22）。
- 所有工具都没有实现 `context.cancelled()` 检查，**只有 B 站下载循环检查了**（`bilibili.py:55`、`bilibili.py:88`）。其余工具即使收到 `cancel` 也会执行到底。
- 没有任何工具检查 `context.deadline`（`ToolContext.deadline` 是纯信息字段，`runtime.py:226`）。

## 5.8 控制台前端

### 5.8.1 页面区块（`static/index.html`）

| 区块 | 元素 id / 类 | 内容 | 位置 |
| --- | --- | --- | --- |
| 顶栏 | `.topbar` | 品牌、连接状态灯、搜索框、最后同步时间、刷新间隔下拉、暂停/立即刷新按钮 | `index.html:12-29` |
| 概览条 | `.summary` | 4 个 KPI：在线 Provider / 可用工具 / 执行中 / 失败任务 | `index.html:32-37`（数据来自 `summary.statuses.working/failed`） |
| 错误提示条 | `#notice` | 拉取失败时的红条文案 | `index.html:39` |
| Provider 面板 | `#providerList` | 每个 Provider：名称、`revision N`、`N queued`、工具标签云 | `index.html:42-45`、`console.js:183-197` |
| 工具目录面板 | `#toolList` + `.tool-columns` | 列：工具 / Provider / Revision / 调用按钮 | `index.html:47-51`、`console.js:199-213` |
| 任务流水面板 | `#taskList` + `.task-filters` | 状态筛选按钮组 + 任务行（状态点、工具名、task_id 前 12 位、状态标签、更新时间） | `index.html:53-62`、`console.js:222-237` |
| 调用弹窗 | `#invokeDialog` | Schema 可视化（输入/输出并排）、参数 JSON textarea、模式下拉、等待上限、callback 折叠区 | `index.html:66-102` |
| 任务详情弹窗 | `#taskDialog` | task_id/status/provider/created_at/updated_at 网格 + 结果或错误 JSON 块 | `index.html:104-110`、`console.js:282-291` |
| 空态模板 | `#emptyTemplate` | 「暂无数据」 | `index.html:112` |

### 5.8.2 自动刷新（`static/auto-refresh.js`）

`createAutoRefresh` 返回 `{schedule}`；`schedule()` 清掉旧定时器后 `setTimeout(refresh, interval.value)`——即**单次链式调度**（上一次请求结束才排下一次），不会并发堆积（`auto-refresh.js:5-8`）。间隔下拉可选 500/1000/2000/3000/5000/10000ms，默认 **2000ms**（`index.html:25`）。暂停时 `schedule()` 不排新定时器；恢复时直接 `onResume()`（即立刻刷新一次），而不是重新排定时器（`auto-refresh.js:11-21`、`console.js:357-363`）。

## 控制台控件表

| 控件 | 行为 | 调用的接口 | 位置 |
| --- | --- | --- | --- |
| 连接状态灯 `#connectionState` | 拉取成功 → `online`「服务在线」；失败 → `error`「连接异常」；初始 `checking`「连接中」 | 由 `/api/overview` 成败驱动 | `console.js:40-43`、`console.js:250-257`、`index.html:18` |
| 搜索框 `#searchInput` | 输入即小写化存入 `state.query`，对 **Provider（id+工具名）/ 工具（name+description+provider_id）/ 任务（task_id+tool+provider_id+status）** 做子串过滤，只重渲染不重新请求 | 无（本地过滤） | `console.js:54-57`、`console.js:184/200/218`、`console.js:352-355` |
| 刷新间隔 `#interval` | 变更即重排下一次自动刷新定时器 | 无 | `auto-refresh.js:10` |
| 暂停/继续 `#pauseButton` | 切换 `paused`；切类名与图标；改 title/aria-label；文案切「自动刷新已暂停/已开启」；恢复时立即刷新一次 | 恢复时触发 `refresh()` → `/api/overview` | `auto-refresh.js:11-21` |
| 立即刷新 `#refreshButton` | 手动 `refresh()`；请求期间按钮 `disabled`（`:disabled { cursor:wait; opacity:.55 }`） | `GET /api/overview?limit=100` | `console.js:356`、`console.js:246-263` |
| 任务状态筛选组 `.task-filters button` | 4 个按钮（全部/执行中/完成/异常）互斥切换 `active` 类并设 `state.status`，本地过滤重渲染 | 无 | `index.html:55-60`、`console.js:345-350`、`console.js:215-220` |
| 工具行「调用」按钮 `.invoke-button` | 打开调用弹窗：按 `inputSchema` 生成示例 JSON 填入参数框、渲染输入/输出 Schema 树、重置 callback 区 | 无（用的是 `/api/overview` 已带回的 Schema） | `console.js:210`、`console.js:265-280` |
| 任务行 `.task-item`（点击 / 回车） | 打开任务详情弹窗 | `GET /api/task-logs/{task_id}` | `console.js:233-234`、`console.js:293-301` |
| 参数 JSON `#argumentsInput` | 提交时 `JSON.parse`，语法错误显示「参数不是有效的 JSON。」 | 无 | `console.js:311`、`console.js:335` |
| 调用模式 `#modeInput` | 下拉：`async`（默认）/ `wait` | 作为请求 `mode` | `index.html:82`、`console.js:329` |
| 等待上限 `#timeoutInput` | number，`min=1 max=30000`，默认 30000（与服务端 `TOOL_MAX_WAIT_MS` 默认一致）；**仅在 `wait` 模式影响返回，`async` 模式仍作为 `deadline` 使用** | 作为请求 `timeout_ms` | `index.html:83`、`console.js:329`、`main.py:268` |
| callback 复选框 `#callbackInput` | 勾选才显示 `#callbackOptions`，否则 `callback=null` | 无 | `console.js:340-342`、`console.js:313` |
| 回调 queue `#callbackQueueInput` | 默认 `main_agent_queue`，`maxlength=256` | 作为 `callback.queue` | `index.html:88`、`console.js:273` |
| 回调事件类型 `#callbackEventTypeInput` | 默认 `async_result`，`maxlength=128`；不在服务端允许集时提交收到 `400` 并显示在 `#invokeError` | 作为 `callback.event_type` | `index.html:89`、`console.js:274` |
| 触发状态三复选框 `#callbackWorking/Completed/FailedInput` | 默认全选；全不选时前端抛「至少选择一个回调终态。」，不发请求 | 作为 `callback.on` | `console.js:314-319` |
| 「派发任务」提交按钮 | POST 调用 → 关闭弹窗 → `refresh()` → 打开该任务的详情弹窗 | `POST /api/tools/{name}/calls` + `GET /api/overview` + `GET /api/task-logs/{id}` | `console.js:327-337` |
| 「取消」/ 关闭按钮 `[data-close]` | 关闭对应 dialog | 无 | `console.js:344` |
| 调用错误 `#invokeError` | 显示 JSON 语法错误或服务端 `detail`/`error` 文案 | — | `console.js:334-337` |

**不存在的控件（重要缺口）**：控制台**没有**任务「重试」按钮、**没有**任务「取消」按钮、**没有** Provider 强制断开按钮、**没有**分页或时间范围选择、**没有**手动指定 `provider_id` 的入口。原因在服务端：Tool Server 既不提供 cancel/retry API，也不解析 `cancel` 消息（`tool_server/main.py` 全文无 cancel 相关代码）。

## 5.9 配置与环境变量

### `tool_server`（`settings.py:9-50`）

| 环境变量 | 默认值 | 作用 | 位置 |
| --- | --- | --- | --- |
| `REDIS_URL` | 空 → 由下列项拼装 | 完整 Redis DSN，优先级最高 | `settings.py:25` |
| `REDIS_HOST` | `redis` | 拼装 `redis://[:pass@]host:port/db` | `settings.py:27,32` |
| `REDIS_PORT` | `6379` | 同上 | `settings.py:28` |
| `REDIS_DB` | `0` | 同上 | `settings.py:29` |
| `REDIS_PASSWORD` | 未设 | 设了才生成 `:pass@` 凭据段 | `settings.py:30-31` |
| `MONGO_HOST` | `mongodb` | Mongo 主机 | `settings.py:40` |
| `MONGO_PORT` | `27017` | Mongo 端口 | `settings.py:41` |
| `MONGO_USER` | 未设 | 设了才启用 `authSource="admin"` | `settings.py:42`、`main.py:37-42` |
| `MONGO_PASS` | 未设 | Mongo 密码 | `settings.py:43` |
| `MONGO_DATABASE` | `agent` | 任务日志库 | `settings.py:44` |
| `MONGO_TOOL_TASK_LOG_COLLECTION` | `tool_task_logs` | 任务日志集合 | `settings.py:45` |
| `TOOL_TASK_TTL_SECONDS` | `86400` | 任务/通知/最近索引 TTL（秒） | `settings.py:46` |
| `TOOL_MAX_WAIT_MS` | `30000` | 同步等待上限；`timeout_ms` 超出被截断 | `settings.py:47`、`main.py:278` |
| `TOOL_DISPATCH_TIMEOUT_SECONDS` | `5` | **死配置**：被解析进 `Settings` 但全仓无任何读取方 | `settings.py:20,48`、`grep` 全仓仅 3 处命中 |
| `TOOL_CALLBACK_EVENT_TYPES` | `async_result` | 逗号分隔的事件类型白名单，剥空白、滤空项 | `settings.py:33-37` |

### `tool_provider`（`main.py:10-30`）

| 环境变量 | 默认值（代码） | compose 默认 | 作用 |
| --- | --- | --- | --- |
| `TOOL_MODULES` | `tools.system,tools.qq,tools.bilibili,tools.documents` | 相同 | 工具模块导入清单 |
| `TOOL_SERVER_WS_URL` | `ws://tool_server:8083/ws/providers` | 相同（硬编码） | Tool Server WS 地址 |
| `TOOL_PROVIDER_ID` | `provider-default-01` | `provider-default-01` | 注册身份；同一 id 重注册会替换旧连接 |
| `TOOL_PROVIDER_REVISION` | **`3`** | **`5`** | 注册版本号，必须严格递增才能重注册 |
| `TOOL_PROVIDER_CONSUMERS` | `1` | `1` | Consumer 线程数 = 最大执行并发 |
| `TOOL_PROVIDER_QUEUE_SIZE` | `128` | `128` | 内部任务队列容量 |
| `TOOL_PROVIDER_HEARTBEAT_SECONDS` | `20` | `20` | Provider 发 `ping` 的间隔 |
| `MONGO_HOST`/`MONGO_PORT`/`MONGO_USER`/`MONGO_PASS`/`MONGO_DATABASE` | `mongodb`/`27017`/—/—/`agent` | 同 | `tools/documents.py` 使用（模块 import 时读取） |
| `MONGO_DOCUMENT_COLLECTION` | `documents` | `documents` | 文档集合（模块 import 时读取） |
| `QQ_API_BASE_URL` | **无默认，`os.environ[...]`** | `.env` 提供 | QQ API 基址 |
| `QQ_API_TOKEN` | **无默认，`os.environ[...]`** | `.env` 提供 | QQ API Bearer Token |
| `BILIBILI_COOKIE` | `""` | `.env.example:54` 提供 `changeme` | B 站请求 Cookie |
| `BILIBILI_DOWNLOAD_DIR` | `/tmp/aagent-downloads` | 未入 compose/env.example | 音频下载目录 |

**配置漂移**（已有报告登记）：`TOOL_PROVIDER_REVISION` 三处不一致——代码 `3`（`tool_provider/main.py:25`）/ compose `5`（`docker-compose.yml:204`）/ `.env.example` `2`（`.env.example:37`）；`.env.example:41` 的 `TOOL_MODULES=tools.qq,tools.bilibili` 少了 `tools.system`，照抄示例会丢掉 `system.echo`（`docs/审查日志/2026-10-11-全项目-审查报告.md:110`）。

## 5.10 持久化结构

### Redis

| 键 | 类型 | 值/字段 | TTL | 写入方 | 读取方 |
| --- | --- | --- | --- | --- | --- |
| `tool:task:{task_id}` | String | 任务 JSON：`task_id, tool, provider_id, status, created_at, updated_at, expires_at, result, error, callback` | `TOOL_TASK_TTL_SECONDS`，每次 transition 刷新 | `task_store.create/transition` | `task_store.get/list_recent`、`GET /api/tasks/{id}` |
| `tool:task:{task_id}:updates` | List | 仅 1 个元素：最新状态字符串（`LPUSH` + `LTRIM 0 0`） | 同任务 TTL | Lua 脚本 | `wait_for_terminal` 的 `BLPOP` |
| `tool:tasks:recent` | ZSET | member=task_id，score=`created_at` 时间戳 | 无 TTL，靠 `ZREMRANGEBYSCORE`/`ZREM` 懒清理 | `task_store.create` | `task_store.list_recent` |
| `tool:callback:outbox` | List | `{"queue":str,"event":{event_type,payload}}` JSON | **无 TTL** | `create/transition` 的 Lua | `callback_worker` 的 `BRPOPLPUSH` |
| `tool:callback:processing` | List | 同 outbox 条目（在飞） | **无 TTL** | `BRPOPLPUSH`；启动恢复时整表回灌 | `callback_worker` |
| `tool:providers` | Hash | field=`provider_id`，value=注册消息全量 JSON | 无 TTL | WS 注册时 `HSET`，断开时 `HDEL` | **无读取方** |

设计文档提到的「Hash 保存工具 Schema 和 Provider 元数据」（`docs/18:54`）只有 `tool:providers` 这一处落地且无人读；工具注册表实际**只存在于进程内存**（`provider_registry.py:22-23`）。

### MongoDB

| 项 | 值 | 位置 |
| --- | --- | --- |
| 库 | `MONGO_DATABASE`，默认 `agent` | `main.py:45` |
| 集合 | `MONGO_TOOL_TASK_LOG_COLLECTION`，默认 `tool_task_logs` | `main.py:45` |
| 文档字段 | `task_id`(str)、`tool`(str)、`provider_id`(str\|null)、`status`(str)、`event_type`(`"created"`\|`"transition"`)、`logged_at`(tz-aware datetime)、`task`(整份任务快照) | `task_log_repository.py:29-39` |
| 索引 | `task_id_logged_at` = `(task_id ASC, logged_at ASC)`；`logged_at_desc` = `(logged_at DESC)`；**无 TTL 索引** | `task_log_repository.py:17-25` |
| `list_recent` 管道 | `$sort logged_at:-1` → `$group _id:$task_id first(task,logged_at)` → `$sort logged_at:-1` → `$limit` → `$replaceWith $task`（即「每个任务取最新快照，再取最近 N 个任务」） | `task_log_repository.py:47-63` |
| `get_latest` | `find_one({task_id}, {_id:0, task:1}, sort=logged_at DESC)` | `task_log_repository.py:65-71` |
| 写入失败处理 | 捕 `PyMongoError` 记 `logger.exception` 后**吞掉**，不影响任务流程 | `task_log_repository.py:40-45` |
| 写入时机 | `create` 成功后 1 条 `created`；每次**成功** transition 1 条 `transition`（冲突/终态拒绝不写） | `task_store.py:90-91`、`task_store.py:139-140` |

## 扩展槽

以下逐项说明「加什么」需要改哪里，以及必须遵守的不变量。

### E1 新增一个 Provider（最完整、无需改 Tool Server 代码）

1. 写工具模块与 `Tool` 子类（见 E2）；
2. 起一个 `ToolProvider` 进程，配置 `TOOL_SERVER_WS_URL`、**唯一的 `TOOL_PROVIDER_ID`**、`TOOL_PROVIDER_REVISION`、`TOOL_PROVIDER_CONSUMERS`（并发）、`TOOL_PROVIDER_QUEUE_SIZE`；
3. `docs/19:76` 明确「两种远程节点都不保存 provider_id，Provider 选择由 Tool Server 负责」——注册表靠**工具名唯一**路由（`provider_registry.py:32-35`），因此新 Provider 不能与既有 Provider 抢同名工具，否则注册被拒 `1008`；
4. 不变量：`provider_id` 全局唯一且稳定；`revision` 每次 Schema 变更必须**严格递增**且大于服务端现存连接的 revision；注册首帧必须在 **10 秒**内到达（`main.py:304`）；工具名必须落在 `ToolSchema.name` 正则内。

### E2 新增一个工具

1. 在 `tool_provider/tools/` 新建模块，继承 `Tool`，声明 `name`（必须含 `.`）、`description`、`input_schema`、`output_schema`、`annotations`，实现 `execute(arguments, context)`；
2. 把模块名加入 `TOOL_MODULES`（或放进已列模块）；
3. **不变量**：`output_schema` 必填（runtime 会对输出做校验）；根应为 object、声明 `required`、`additionalProperties: false`（`README.md:42`）；需要 Workflow 端口类型时在属性上标 `x-workflow-port-type` ∈ `{content,message,list-content,list-message}`；类必须可**无参实例化**（`runtime.py:53`）；`name` 在全部模块内唯一；**必须递增 `TOOL_PROVIDER_REVISION`**（`README.md:81`），否则服务端会以「revision must increase」拒绝重注册（`provider_registry.py:29-30`）；
4. 陷阱：`discover` 用的是 `inspect.getmembers(module, isclass)`，**模块命名空间里被 import 进来的具体 Tool 子类也会被当作本模块工具注册**——不要在工具模块里 `from tools.other import SomeToolClass`，否则会撞重名或注册到意外模块；
5. 陷阱：`annotations` 是**类级可变默认 dict**（`tool.py:22`），不要就地修改 `self.annotations`。

### E3 新增一种「任务类型」

**当前架构不支持**。可扩展面只有四项硬编码枚举，全部需要改代码：

| 扩展目标 | 必须改的点 | 位置 |
| --- | --- | --- |
| 新任务状态（如 `cancelled`） | `models.py` 状态相关字面量、`main.py` 的 `CALLBACK_STATUSES`、`task_store.py` 的 `TERMINAL_STATUSES`、Lua 脚本的终态判定、`console.js` 的 `statusNames`、`api/overview` 的 `status_counts` 初始化、Workflow 客户端映射 | `main.py:49`、`task_store.py:11`、`task_store.py:20`、`console.js:20-25`、`main.py:202` |
| 新回调状态 | `CallbackSpec.on` 的 `Literal`、`CALLBACK_STATUSES` | `models.py:31-35`、`main.py:49` |
| 新 Provider 事件类型 | `ProviderEvent.type` 的 `Literal` + `handle_provider_event` 分支 | `models.py:50`、`main.py:82-121` |
| 新调用模式（如 `stream`） | `ToolCallRequest.mode` 的 `Literal` + `call_tool` 分支 | `models.py:42`、`main.py:274-280` |

### E4 替换存储后端

| 替换目标 | 抽象边界 | 说明 |
| --- | --- | --- |
| 任务状态存储 | `TaskStore`（`task_store.py:58-155`）是唯一抽象类，但**没有 Protocol/ABC**，且 `main.py:47` 直接构造具体类 | 换后端需保持 5 个方法签名：`task_key`/`updates_key`(staticmethod)、`create`、`get`、`list_recent`、`transition`、`wait_for_terminal`；`transition` 返回 `(changed, payload)`，`wait_for_terminal` 返回任务或 None |
| 原子迁移与唤醒 | 关键不变量在 **Lua 脚本内**（`task_store.py:13-51`）：条件更新 + 终态不可变 + 状态写入与通知写入同脚本 + 回调入队同脚本 + 同 TTL | 换成非 Redis 后端时必须自行提供等价事务语义，否则会丢唤醒或覆盖终态 |
| 任务日志 | `TaskLogRepository`（`task_log_repository.py:13-71`）只依赖 pymongo `AsyncCollection` 的 `create_index`/`insert_one`/`aggregate`/`find_one` | 直接注入另一个 collection 即可；`main.py:44-46` 是构造点 |
| Provider 注册表 | **无持久化抽象**，`ProviderRegistry` 是内存 dict | 换存储需新增一层并改 `main.py:48`、`main.py:309`、`main.py:325` |
| 回调投递 | 硬编码 Redis List 语义（`BRPOPLPUSH`/`LPUSH`/`LREM`），无抽象 | 换 MQ 需重写 `callback_worker`（`main.py:124-149`），并同步改 Lua 中的 `LPUSH KEYS[3]` |

### E5 水平扩展 Tool Server

**设计上明确禁止**（`docs/17:17`、`docs/18:9`），代码事实也确认无法直接扩展：

1. `ProviderRegistry` 是进程内内存（`provider_registry.py:22-23`），两个实例各自只看到连到自己的 Provider；
2. WS 连接无法在实例间迁移，`send()` 只查本进程注册表，路由不到别的实例；
3. `TaskStore` 的 `BLPOP` 等待是**跨实例可见**的（都在同一 Redis），因此 B 实例可以等到 A 实例推进的状态；但任务创建与派发绑定在同一实例（`call_tool` 内先 create 再 send），没有转发层；
4. 若强行多实例：`tool:callback:outbox` 是共享 List，多个 callback_worker 会并发 `BRPOPLPUSH`（语义仍安全，至少一次），但 `tool:tasks:recent`、`tool:providers` 会成为多写方；
5. 结论：**扩吞吐只能加 Provider 和 `TOOL_PROVIDER_CONSUMERS`，不能加 Tool Server 实例**。若必须 HA，需先引入「连接归属 + 任务转发」层，属于架构级改造。

### E6 其他注册点与抽象方法清单

| 可扩展点 | 机制 | 位置 | 需要改动的代码 |
| --- | --- | --- | --- |
| 工具发现 | 动态 import + `issubclass` 扫描 | `runtime.py:45-59` | 换约定（装饰器/entry_points）只需改 `discover` |
| 工具契约 | `Tool` ABC 唯一抽象方法 `execute` | `tool.py:33-35` | 新增抽象方法会破坏所有既有工具 |
| 工具上下文 | `ToolContext`（`task_id`/`deadline`/`cancelled`/`report_progress`） | `tool.py:9-14` | 加字段需同步 `runtime.py:224-229` 的构造点 |
| 回调 sink | `CallbackSpec.type` 只允许 `"redis"` | `models.py:28` | 新 sink = 改 Literal + `callback_worker` 投递分支 |
| 回调事件类型 | 环境变量 `TOOL_CALLBACK_EVENT_TYPES` | `settings.py:33-37`、`main.py:233` | **纯配置，无需改代码** |
| Provider 事件 | `ProviderEvent.type` Literal | `models.py:50` | 需加 Literal 值与 `handle_provider_event` 分支 |
| 工具模块 | `TOOL_MODULES` | `tool_provider/main.py:15-21` | **纯配置** |
| HTTP 路由 | FastAPI 装饰器 | `main.py:180-330` | 直接新增；注意静态目录挂在 `/`，会吞掉未定义路径 |

### E7 扩展时不可违反的协议不变量

1. 工具名 `^[A-Za-z0-9_-]+\.[A-Za-z0-9_.-]+$`，≤128；`description` ≤4096；单次注册 ≤256 个工具（`models.py:9-22`）。
2. `revision` 严格递增；同 provider_id 重注册会替换旧连接（`provider_registry.py:29-30`、`:37-40`）。
3. 工具名全局唯一跨 Provider（`provider_registry.py:32-35`）。
4. 终态 `completed`/`failed` 不可覆盖，任何迟到消息被静默丢弃（`task_store.py:20-22`）。
5. `accepted`/`rejected` 只接受来自 `pending` 的任务；`status` 只接受 `working` 且 `event.status=="working"`（`main.py:99-111`）。
6. `result` 必须有 `success`；`success=true` 时 `output` 必须通过已注册的 `outputSchema`（`main.py:113-118`）。
7. Provider 上报的 `task_id` 必须属于该连接（`main.py:95-96`），否则连接被关。
8. 状态写入与唤醒信号、callback 入队必须在同一原子操作内（`task_store.py:13-51`）。
9. 返回 `task_id` 之前任务必须已可查询（`main.py:255` 先 create 后返回）。
10. callback payload 的全部字段由服务端生成，`on`/`event_type` 随任务持久化，重试不重算（`main.py:52-70`、`main.py:253`）。
11. Workflow 侧远程契约：`inputSchema.properties` → 输入端口；对象型 `outputSchema.properties` → 输出端口；标量/数组 → 单端口 `result`（`docs/19:241-247`）。

## 已知缺陷与占位代码

### 占位/死代码扫描结果

| 模式 | 命中 | 判定 |
| --- | --- | --- |
| `TODO` / `FIXME` / `XXX` / `HACK` | 在 `tool_server/`、`tool_provider/`（含 static）**零命中** | 无显式待办标记 |
| `pass` | `tool_server/main.py:322`（`except (WebSocketDisconnect, asyncio.TimeoutError): pass`） | 有意静默，但导致断线无日志 |
| `NotImplementedError` | `tool_provider/tool.py:35`（ABC 抽象方法体） | 正常写法，非缺陷 |
| 缺失实现 | `tool_provider/tools/__pycache__/echo.cpython-312.pyc` 无对应 `echo.py` | **孤儿字节码**，无源码、无引用（`grep echo` 仅命中 `system.echo`） |
| 死配置 | `TOOL_DISPATCH_TIMEOUT_SECONDS` → `Settings.dispatch_timeout_seconds` 无读取方 | `settings.py:20,48` |
| 只写键 | Redis `tool:providers` 无读取方 | `main.py:311-315,326` |
| 死协议分支 | Provider 支持 `cancel`（`runtime.py:161-162,184-190`），Tool Server 无任何发送方 | 无 API、无 UI |
| 死协议分支 | 协议允许 Server→Provider `ping`（`runtime.py:163-164`），Server 无发送方 | `main.py` 无 ping 发送 |
| 死字段 | `task["expires_at"]` 写入后无读取方 | `main.py:250` |
| 死字段 | `ProviderEvent.status` 仅在 `"working"` 一种取值下被接受，其余触发关连接 | `main.py:108-109` |

### 缺陷清单（按严重度）

| ID | 级别 | 缺陷 | 位置 | 影响 |
| --- | --- | --- | --- | --- |
| D1 | 中（已登记 A3） | Provider 输出不符合 `outputSchema` 时 `jsonschema.ValidationError` **不是** `ValueError` 子类，逃出 `except (PydanticValidationError, SchemaError, ValueError)`，异常穿透 `finally` 并把该 Provider 的 WebSocket 整条打断 | `main.py:118`、`main.py:319-322` | Provider 掉线；在飞任务停在 `working` 直到 TTL；同步调用方等到自身超时才拿 202。`docs/审查日志/2026-10-11-全项目-审查报告.md:42-47` |
| D2 | 低（已登记 A4） | 先 `registry.get_tool` 判存在，再 `list_tools()` + `next(...)` 反查 `provider_id`，两次加锁之间 Provider 掉线 → `StopIteration` → 500 | `main.py:230`、`main.py:258-259` | 偶发 500，应为 503 或回退到未派发分支。`docs/审查日志/2026-10-11-全项目-审查报告.md:49-53` |
| D3 | 中 | `handle_provider_event` 对冲突/终态拒绝的返回值完全不检查：`transition` 返回 `(False, "conflict"/"terminal")` 被丢弃，无日志无计数 | `main.py:74-79`、`main.py:99-121` | 迟到消息、错序消息、`rejected` 在 `working` 后到达等全部静默丢失，排障无痕迹 |
| D4 | 中 | 协议违规一律 `raise ValueError` → 关整条 WS 连接。单个畸形消息（缺 `task_id`、`status` 值非法、`success` 缺失、`task_id` 不属于该 Provider）即可踢掉整个 Provider 及其全部工具 | `main.py:89,96,109,114` | 单点畸形载荷放大为全 Provider 故障；行为等价于 D1 的放大器 |
| D5 | 中 | `callback_worker` 只要 `lrem`/`lpush` 抛 `RedisError`（Redis 短时不可用即会），异常即逃出 `while True`，**后台任务永久死亡**；`lifespan` 只在关闭时 cancel，不会重启 | `main.py:143-148` | Redis 抖动一次即永久失去回调投递能力（进程仍健康、`/api/health` 甚至可能恢复为 ok），故障静默 |
| D6 | 中 | 重试用固定 `sleep(1)`，**无指数退避、无最大次数、无保留期限**，且 outbox/processing **无 TTL** | `main.py:149`、`main.py:141` | 毒消息造成无限重试+日志洪水；不可投递条目永久占用内存。与 `docs/18:110,123` 的「退避策略」「明确的保留期限」不符 |
| D7 | 低 | `callback_worker` 用 `lrem(processing, 1, item)` 按**值**删除。当 outbox 中存在两条完全相同的 JSON 时可能删错一条 | `main.py:142`、`main.py:146` | 概率极低但会破坏至少一次语义。`docs/审查日志/2026-10-11-全项目-审查报告.md:73` |
| D8 | 中 | **无心跳超时判定、无任务看门狗**。半开连接不被清退；任务没有 `timeout` 状态，`working` 任务永不被判失败 | `main.py` 全文无定时器；`task_store.py` 无超时迁移 | 半开连接下所有在飞任务挂到 TTL（默认 24h）才消失，调用方只能靠自己超时；`rejected` 后重新路由也无人做（`pending` 任务不会被重派） |
| D9 | 低 | Provider 重连退避循环把 `ValueError` 也当网络错误；服务端若残留同 `provider_id` 且 revision ≥ 新连接的旧连接，注册会被永久拒绝，而 `TOOL_PROVIDER_REVISION` 是静态配置不会自增 | `runtime.py:96-101`、`runtime.py:127-129`、`provider_registry.py:29-30` | 需要人工重启/改版本号才能恢复 |
| D10 | 中 | **无取消能力**：无 HTTP cancel 接口、无 WS cancel 发送方、控制台无取消按钮；Provider 侧 `cancel` 分支是死代码 | `main.py:228-280` 无 cancel；`runtime.py:161-162,184-190` | 长任务（如 B 站 ASR，可跑数分钟）无法中止；`docs/19:63` 已确认「当前没有 cancel API」 |
| D11 | 中 | `deadline` 下发后**无人执行**：Provider 只把它塞进 `ToolContext`，没有超时中断、没有超时判定；除 B 站下载外的工具也不检查 `cancelled()` | `runtime.py:226`、`bilibili.py:55,88`（唯一检查点） | Provider 执行时限纯装饰；同步调用方超时后任务仍在跑（副作用可能已发生） |
| D12 | 低 | `/api/health` 只探 Redis/Mongo，不反映 callback worker 存活、也不反映任何 Provider 在线状态 | `main.py:180-186` | D5 类故障对健康检查不可见 |
| D13 | 低 | 未知工具返回 `503 "tool provider is unavailable"` 而非 `404`；`409`/`503` 与 `422` 的错误体风格不统一（`HTTPException.detail` vs 字符串） | `main.py:230-232` | 客户端难以区分「工具从未存在」与「工具当前离线」 |
| D14 | 低 | Redis `tool:providers` 只写不读；Tool Server 重启后**不清空**该 Hash，陈旧 Provider 条目永久残留（只有正常断开才 `HDEL`） | `main.py:311-315,326` | 若将来有读取方会读到幽灵 Provider |
| D15 | 低 | Mongo 任务日志**无 TTL 索引/清理策略**，每次 create + 每次成功迁移各插一条含完整任务快照的文档 | `task_log_repository.py:17-25`、`task_store.py:90-91,139-140` | 长期运行线性膨胀；`/api/overview` 默认每 2 秒触发一次聚合查询（`console.js:249` + `auto-refresh.js:7`） |
| D16 | 低 | 大结果不外置，`result` 直接内联进 Redis String（设计文档要求外置存引用） | `task_store.py:78` | 大输出放大 Redis 与 WS 报文；与控制台/客户端的内存占用直接相关 |
| D17 | 低 | `TOOL_DISPATCH_TIMEOUT_SECONDS` 是死配置 | `settings.py:20,48` | 运维以为派发有独立超时，实际由队列满/连接存在与否决定 |
| D18 | 低 | `ToolContext.annotations` 是类级可变默认 `{}`；`ToolProvider.discover` 会把模块命名空间里 import 进来的具体 Tool 子类一并注册 | `tool.py:22`、`runtime.py:50-56` | 前者是共享可变状态陷阱，后者是隐蔽的重名/串模块风险 |
| D19 | 低 | Provider 事件队列无界（`queue.Queue()`），`report_progress` 无节流 | `runtime.py:36`、`runtime.py:215-222` | 高频进度工具可把内存推高；而服务端 `progress` 只写字段，不落 Mongo |
| D20 | 低 | 输出 schema 校验在 Provider（`runtime.py:236`）与 Server（`main.py:118`）各做一次，且 Server 侧那次会打断连接（D1） | `runtime.py:236`、`main.py:118` | 同一份校验两处实现、两套失败语义（Provider 转 `failed` 事件；Server 断连） |
| D21 | 低 | `qqapi` 用 `os.environ[...]` 直接索引，缺 `QQ_API_BASE_URL`/`QQ_API_TOKEN` 时在**调用时**才 `KeyError`，无启动期校验 | `qqapi.py:7,9` | 配置缺失延后到生产调用才暴露，错误以「任务 failed, code=KeyError」的形式出现 |
| D22 | 低 | `documents.pin` 修改 `pinned` 时**不更新** `updated_at`，而 create/append/rewrite/rename 都更新 | `documents.py:259-265` | 任务流水中「最后修改时间」对钉住操作失真 |
| D23 | 低 | `documents.query_by_name` 无 `limit`、标题字段无索引，返回**全部**命中文档 | `documents.py:96-98` | 大集合下既是全表扫描又是无界响应体；输出校验通过（schema 只约束形状） |
| D24 | 低 | `bilibili` 硬编码外部 ASR 地址 `https://frp-dry.com:63030/`、模型名 `Qwen3-asr-1.7b-fp16` 写死在代码里；凭据仅 `BILIBILI_COOKIE`（可空） | `bilibili.py:94-103` | 非标准端口 + 无环境变量开关，换 ASR 服务必须改代码；无 Cookie 时只能拿低清/受限资源 |
| D25 | 低 | `bilibili._download_bvid` 中 `quality = max(streams)` 在 `streams` 为空时抛 `ValueError`；`streams[quality]["audio"][0]` 在无音轨时抛 `IndexError`；`_download` 被取消时返回而未清理半成品文件 | `bilibili.py:81-82`、`bilibili.py:55-56` | 错误信息对使用者不可读；`/tmp/aagent-downloads` 会积累残缺 `.m4s`（下次运行按 sha256 命中同一路径并尝试续传） |
| D26 | 低 | `CallbackSpec.queue` 无 key 格式/白名单校验，`event_type` 长度 ≤128 但内容任意（仅受环境白名单约束） | `models.py:29-30`、`main.py:233` | 与 `docs/17:263`「限制 key 格式、消息大小」的安全约束部分不符；调用方可把回调写进任意 Redis List |
| D27 | 低 | 消息大小无限制：`ToolCallRequest.arguments`、`event.output`、`message` 均无 bytes 上限（`description` 有 4096 限制，参数没有） | `models.py:38-57` | 与 `docs/17:262`「限制参数、结果、消息体和并发任务大小」不符 |
| D28 | 低 | 控制台缺少重试/取消控件，且任务详情走 Mongo（`/api/task-logs`）而列表也走 Mongo 快照，`/api/tasks/{id}` 的实时状态在 UI 中无入口 | `console.js` 全文、`console.js:249,253,296` | 运维只能看历史快照；`pending`→`working` 的中间态在 UI 上可能延迟一个刷新周期 |
| D29 | 低 | `ProviderEvent` `extra="allow"`，而 `RegisterMessage`/`ToolCallRequest`/`ToolSchema` `extra="forbid"` | `models.py:7,17,39,48` | Provider 可发送任意多余字段被静默接受；调用方多写一个字段即 422，契约宽严不对称 |
| D30 | 低 | 任务不存在时 Provider 事件只记 `warning` 并返回（幂等丢弃），但**没有任何计数/指标** | `main.py:91-93` | 幂等行为正确，但无法观测「任务丢失」规模 |

### 与测试覆盖的关系

`tool_server` 仅 2 个测试文件、7 个用例，全部围绕 `TaskStore` 的日志写入语义与 `TaskLogRepository` 的查询管道（`test_task_store.py` 4 例、`test_task_log_repository.py` 3 例，`docs/审查日志/2026-10-11-全项目-审查报告.md:14` 记为 7 用例全通过）。**`main.py` 的路由、WS 处理、callback worker、`provider_registry.py`、`settings.py` 与工具实现零测试覆盖**——上述 D1/D3/D4/D5/D7 全都落在无覆盖区。

## 5.11 与设计文档的差异对照

| 设计文档要求 | 代码事实 | 位置 |
| --- | --- | --- |
| 注册时校验 Schema 的大小、深度和 `$ref`，默认禁止远程 `$ref`（`docs/17:260`） | 只做 `check_schema` 合法性校验，**无大小/深度/`$ref` 限制** | `main.py:306-308` |
| Provider 和 HTTP 调用方分别认证（`docs/17:258`） | **无任何认证** | `main.py:169-330` |
| callback 失败按退避策略重试、超保留期限（`docs/18:110,123`） | 固定 1s 重试、无上限、无保留期限、无 TTL | `main.py:143-149` |
| 大结果保存到外部存储，任务记录只保存引用（`docs/18:121`） | 结果内联在 Redis String | `task_store.py:78` |
| 限制参数、结果、消息体和并发任务大小（`docs/17:262`） | 无任何 payload 大小限制 | `models.py:38-57` |
| 限制 callback key 格式与消息大小（`docs/17:263`） | 只限制长度，无格式校验 | `models.py:29` |
| 记录调用方、工具、Provider、耗时、状态和错误用于审计（`docs/17:264`） | Mongo 记录 task_id/tool/provider_id/status/event_type/logged_at；**不记录调用方、不记录耗时** | `task_log_repository.py:29-39` |
| Hash 保存工具 Schema 和 Provider 元数据（`docs/18:54`） | `tool:providers` 只写不读，注册表在进程内存 | `main.py:311`、`provider_registry.py:22` |
| 未收到 `accepted` 的任务保持 `pending`，等待**重新路由**或超时（`docs/18:45`） | 保持 `pending` 正确，但**无重新路由、无超时处理** | `main.py:271-272` |
| 每个 Task 只允许一个阻塞等待者（`docs/18:104`） | 一致（List `LPUSH+LTRIM 0 0` + 单 `BLPOP` 语义） | `task_store.py:44-46,155` |
| 状态更新与通知写入用事务或 Lua，先状态后通知（`docs/18:102`） | 一致，且 callback 入队也在同一脚本 | `task_store.py:13-51` |
| 任务终态不可变，迟到状态只记日志（`docs/18:122`） | 终态不可变一致；**迟到消息被静默丢弃，不记日志** | `task_store.py:20-22`、`main.py:74-79` |
| `task_id` 形如 `01J...`（`docs/17:222`） | `uuid4().hex`，32 位十六进制 | `main.py:241` |

## 5.12 交叉引用与上下游

| 方向 | 对接方 | 契约要点 |
| --- | --- | --- |
| 上游调用方 | `agent/tool_server_client.py` | `POST /api/tools/{tool}/calls`；`202 + async + task_id` → 返回 task_id；`202` 其他 → 抛「任务仍在服务端继续」；`200` 且 `status=="completed"` → 返回 `result`；其余 → 抛错并携带 `task_id`（`agent/tool_server_client.py:45-59`） |
| 上游调用方 | `agent/workflow_nodes.py` 的 `workflow_remote_sync_tool` / `workflow_remote_async_tool` | 见 `docs/19:286-349`；`202` 不轮询、不取消，副作用可能已发生（`docs/19:310-314`） |
| 上游调用方 | `workflow_editor/main.py:51` | 代理 `GET /api/tools` 作为 `/api/tools/remote`，浏览器不直连内部地址（`docs/19:233`） |
| 下游 | Redis | 任务、通知、callback outbox、providers 快照 |
| 下游 | MongoDB | `agent.tool_task_logs` |
| 下游 | 外部服务 | QQ API（`QQ_API_BASE_URL`）、`api.bilibili.com`、`frp-dry.com:63030`（ASR）、MongoDB（documents 工具） |
