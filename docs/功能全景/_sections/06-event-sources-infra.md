# 06 事件源适配器与基础设施

> 类型:审计报告（分节草稿）。
> 性质:现行文档。
> 归属:`qqbot/` + `qqbot_consumer/` + `基础设施`。
> 适用版本:平台 `0.1.0+`。

> 审计范围：`qqbot/`、`qqbot_consumer/`、根目录 compose / `.env` 模板 / git 配置、全部 8 个 `Dockerfile` 与 `requirements.txt`。
> 交叉印证：`docs/20-Event协议与流转.md`、`docs/24-Event绑定与Workflow路由设计.md`（只读）。
> 原则：**以源码为准**。凡文档与代码冲突，本节记录代码事实并登记到「已知缺陷与不一致」。
> 引用格式：`文件:行号`。

---

## 6.1 QQ 事件源：qqbot（OneBot 接入层）

代码清单：`qqbot/listener.py`（81 行）、`qqbot/queue_client.py`（29 行）、`qqbot/Dockerfile`（8 行）、`qqbot/.dockerignore`（6 行）、`qqbot/requirements.txt`（3 行）。

### 6.1.1 连接方式与协议

| 项目 | 代码事实 | 依据 |
| --- | --- | --- |
| 连接方向 | **主动外连的 WebSocket 客户端**（不是反向 WS 服务端）。目标由 `QQ_WS_URI` 给出，`.env.example` 默认 `ws://host.docker.internal:3001` | `qqbot/listener.py:49-55`、`.env.example:14` |
| 协议 | OneBot v11 正向 WebSocket 事件推送。判据：字段名 `post_type` / `notice_type` / `sub_type` / `status_text` / `message_type` / `sender` / `raw_message` / `message_id` / `real_id` / `real_seq` / `target_id` / `message_format: 'array'`，其中 `real_seq` / `target_id` 是 NapCat 系扩展 | `qqbot/listener.py:22`（notice 样例）、`qqbot/listener.py:32`（message 样例） |
| 消息格式 | `message_format` 为 `array`，即 `message` 是 OneBot 消息段数组，不是 CQ 字符串 | `qqbot/listener.py:32,40` |
| 连接参数 | `open_timeout=10`、`ping_interval=20`、`ping_timeout=20`；无 `max_size`、无 `close_timeout` | `qqbot/listener.py:52-54` |
| 客户端库 | `websockets`（**未锁版本**），用的是 `additional_headers` 关键字——该名称自 websockets 12 起取代 `extra_headers`；解析到 <12 时连接阶段直接 `TypeError` | `qqbot/requirements.txt:2`、`qqbot/listener.py:51` |
| 启动方式 | 镜像无 `CMD`；由 compose 提供 `["python", "listener.py"]` | `qqbot/Dockerfile:1-8`、`docker-compose.yml:26` |

### 6.1.2 鉴权

- 仅一种：请求头 `Authorization: Bearer ${QQ_WS_TOKEN}`，在握手时下发，不做重试、不做轮换。
  `qqbot/listener.py:10-12`
- `QQ_WS_URI` 与 `QQ_WS_TOKEN` 都用 `os.environ[...]` 强读 —— **缺失即 `KeyError`，容器启动崩溃**。
  `qqbot/listener.py:9,11`

### 6.1.3 订阅的事件类型与过滤规则

`parse_event()` 是唯一的过滤器，只认两种形状，其余一律返回 `None` 丢弃（`qqbot/listener.py:17-43`）：

| 上游形状 | 产出的 payload | 依据 |
| --- | --- | --- |
| `post_type == "notice"` 且 `sub_type == "input_status"` | `{"post_type": "inputing", "user_id": ...}` | `qqbot/listener.py:21-30` |
| `post_type == "message"`（任意 `message_type`） | `{"post_type": "message", "user_id", "group_id", "raw_message", "message"}` | `qqbot/listener.py:31-42` |
| 其他一切（`meta_event`、`request`、其他 notice、`notice_type != notify` 等） | 返回 `None` → 不写队列 | `qqbot/listener.py:43` |

过滤规则逐条登记：

| 规则 | 现状 | 依据 |
| --- | --- | --- |
| 目标用户过滤 | **不存在**。`TARGET_USER_ID` 在 `:14` 读入后**全文件再无引用**（死变量）。授权判定只在消费端做 | `qqbot/listener.py:14` vs `qqbot_consumer/queue_consumer.py:27` |
| 私聊 / 群聊过滤 | **不存在**。群消息与私聊消息同等投递到 `qq:events`；`group_id` 原样透传 | `qqbot/listener.py:31-42` |
| 机器人自身消息过滤 | **不存在**。`self_id` 从未被读取，`QQ_BOT_ID` 全仓库无读取方 | 见 §6.E.2 |
| `user_id` 存在性 | 唯一硬门槛：`if user_id:` 为假则丢弃（无 `user_id` 的心跳/元事件因此被挡掉） | `qqbot/listener.py:20` |
| `inputing` 噪音 | **未被过滤**，一路写入 Redis；消费端归档后被丢弃 | `qqbot/listener.py:23-30`、`qqbot_consumer/queue_consumer.py:21,30-31` |
| `notice_type` 校验 | 未校验，只看 `sub_type` | `qqbot/listener.py:23` |
| 消息段内容过滤（@、图片、CQ 码） | 无 | `qqbot/listener.py:33-42` |

### 6.1.4 去重、断线重连、异常处理

- **去重：完全没有。** 不读 `message_id` / `real_id` / `real_seq` / `time`，这些字段也不进入 payload（`qqbot/listener.py:33-42`），因此下游连幂等键都没有。
- **断线重连**：`while True` + `except Exception` → `print` → `asyncio.sleep(5)` → 重连。
  `qqbot/listener.py:47,75-77`
  - 固定 5 秒退避，无指数退避、无抖动、无最大次数。
  - 连接被正常关闭（`ConnectionClosed` 是 `Exception` 子类）也走同一条 sleep(5) 路径。
  - `ping_interval=20/ping_timeout=20` 负责半开连接探测（`qqbot/listener.py:53-54`）。
  - `asyncio.CancelledError` 在 3.11 不继承 `Exception`，因此 SIGTERM 取消不会被吞掉。
- **异常处理**：
  - JSON 解析失败 → `print` 后 `continue`，坏帧不影响连接（`qqbot/listener.py:62-64`）。
  - Redis 写入失败 → 异常冒泡到外层 `except` → sleep(5) → 重连。**该事件已被丢弃，不会重发**（无本地缓冲、无 ack）。
  - `print(event)` 全量打印每个事件（`qqbot/listener.py:65`），私聊原文进容器日志。
  - `publish_to_queue` 每次调用 `get_connection()` 新建 `redis.Redis` 客户端（无复用、无连接池共享）：`qqbot/queue_client.py:13-19`。
  - 写队列用 `asyncio.to_thread` 串行执行，`await` 逐条阻塞 —— 吞吐受单次 Redis 往返限制（`qqbot/listener.py:68-72`）。
- **Redis 客户端参数**：只有 `host` / `port` / `decode_responses`。**无 `socket_timeout`、无 `password`、无 `db`**（`qqbot/queue_client.py:13-14`）。

### 6.1.5 写入 Redis 的键名与方向

| 项 | 值 | 依据 |
| --- | --- | --- |
| 键 | `QQ_QUEUE_NAME`，默认 `qq:events` | `qqbot/queue_client.py:10` |
| 方向 | `LPUSH`（左侧入） | `qqbot/queue_client.py:19` |
| 消费端方向 | `BLPOP`（左侧出）→ **整体为 LIFO：后到的事件先被处理** | `qqbot_consumer/queue_client.py:23-26` |
| 编码 | `json.dumps(..., ensure_ascii=False)`，不保证紧凑分隔符 | `qqbot/queue_client.py:19` |
| 连接目标 | `REDIS_HOST` 默认 `redis`、`REDIS_PORT` 默认 `6379` | `qqbot/queue_client.py:7-8` |
| 反方向 API | `pop_from_queue()` 存在但 `qqbot` 内无调用方（死代码） | `qqbot/queue_client.py:23-29` |
| 依赖声明 | `requirements.txt` 列了 `pymongo` 但本服务无任何 Mongo 代码 | `qqbot/requirements.txt:3` |

---

## 6.2 QQ 适配器：qqbot_consumer

代码清单：`qqbot_consumer/queue_consumer.py`（54 行）、`queue_client.py`（34 行）、`history_repository.py`（32 行）、`Dockerfile`（8 行）、`requirements.txt`（2 行）。

### 6.2.1 消费与存档

| 项 | 值 | 依据 |
| --- | --- | --- |
| 消费队列 | `QQ_QUEUE_NAME`，默认 `qq:events` | `qqbot_consumer/queue_client.py:8`、`queue_consumer.py:40` |
| 出队语义 | `BLPOP`，`timeout=5`；超时返回 `None` 后 `continue` | `qqbot_consumer/queue_client.py:23-29`、`queue_consumer.py:40-42` |
| 存档时机 | **出队后立刻无条件存档**，早于任何筛选 | `queue_consumer.py:21` |
| 存档库/集合 | `MONGO_DATABASE`（默认 `agent`）/ `QQ_HISTORY_COLLECTION`（默认 `qq_event_history`） | `history_repository.py:10-11,24` |
| 索引 | `created_at_desc` = `(created_at DESC)`；`event_type_created_at` = `(event_type ASC, created_at DESC)` | `history_repository.py:25-26` |
| 连接 | 惰性单例（模块级 `_client` / `_collection`），`serverSelectionTimeoutMS=5000`、`tz_aware=True` | `history_repository.py:13-27` |
| 认证 | 仅当 `MONGO_USER` 存在时加 `username/password/authSource="admin"` —— 即**以 Mongo root 账号写入** | `history_repository.py:21-22`、`docker-compose.yml:239-240` |
| 无 TTL | 集合没有 TTL 索引，`inputing` 噪音永久累积 | `history_repository.py:25-26` |

文档字段（逐个列出，来源 `history_repository.py:31` 的 `{**event, "created_at": ...}`）：

| 字段 | 类型 | 何时存在 | 来源 |
| --- | --- | --- | --- |
| `_id` | ObjectId | 恒有 | MongoDB 生成 |
| `event_type` | `"qq"` | 恒有 | `qqbot/listener.py:25,34` |
| `payload` | object | 恒有 | 同上 |
| `payload.post_type` | `"message"` \| `"inputing"` | 恒有 | `qqbot/listener.py:26,36` |
| `payload.user_id` | int（QQ 号，OneBot 原值） | 恒有 | `qqbot/listener.py:28,37` |
| `payload.group_id` | int \| `0` \| null | **仅 `message` 事件有**；`inputing` 分支不设该键 | `qqbot/listener.py:38` vs `:26-29` |
| `payload.raw_message` | str | 仅 `message` | `qqbot/listener.py:39` |
| `payload.message` | list[object]（OneBot 消息段） | 仅 `message` | `qqbot/listener.py:40` |
| `created_at` | tz-aware UTC `datetime` | 恒有（消费端追加） | `history_repository.py:31` |

**未落库的字段**：`self_id`、`time`、`message_id`、`message_seq`、`real_id`、`real_seq`、`sender`、`font`、`message_type`、`sub_type`、`target_id`、`status_text` —— 均在 `parse_event` 构造 payload 时被丢弃（`qqbot/listener.py:33-42`）。

### 6.2.2 筛选与转换逻辑

`handle_event()`（`qqbot_consumer/queue_consumer.py:19-31`）是四道串联判定：

1. `event.get("event_type") == "qq"`（`:24`）——非 `qq` 事件仅存档；
2. `payload.get("post_type") == "message"`（`:25`）——`inputing` 落到 `else: pass`（`:30-31`）被静默丢弃；
3. `not payload.get("group_id")`（`:26`）——用**假值判断**同时覆盖 `None` 与 OneBot 私聊实际下发的 `0`；
4. `str(payload.get("user_id")) == str(env("QQ_TARGET_USER_ID", ""))`（`:27`）——双侧转字符串，兼容 int/str；`QQ_TARGET_USER_ID` 未配置时默认 `""`，任何真实 QQ 号都不匹配（**默认拒绝**）。

全部条件成立 → `publish_to_queue(MAIN_AGENT_QUEUE_NAME, event)`（`:28`）。

**关键事实：本适配器不做任何信封转换**——它把 `event`（`event_type: "qq"` 的原信封）**原样**转发到主队列。`qq → workflow` 的转换由 `agent/task_worker.py:46-52` 通过 `event_bindings` 路由完成。因此：

- 本适配器只负责「存档 + 授权私聊透传」；
- 「目标用户判定」唯一实现在 `queue_consumer.py:27`，与 `qqbot/listener.py` 完全无关。

### 6.2.3 消息内容如何投影

**当前代码中不存在任何内容投影。** 具体说明：

- `raw_message` / `message` 原样随 payload 进入主队列，不拼接、不包装、不改名（`queue_consumer.py:28`）。
- **`<Command>` 这类包装标记在当前代码里已完全消失**。全仓检索显示其只存在于 `docs/废弃旧文档/06-格式规范.md:163`、`07-事件双重身份与信息回调.md:108,118`、`08-终端设计.md:18,43,126,190` 与历史审查日志中；`agent/prompt/`、`agent/settings.json` 已不存在，`agent/task_worker.py` 也没有 `active`/`qq()` 处理器（`docs/审查日志/架构问题汇总.md:24` 登记为 A-03 死链）。
- 当前的内容投影机制是**画布 + 端口名字符串匹配**：
  `agent/task_worker.py:82-87` 遍历 `input_node['workflowPorts']`，用 `e['payload'].get(port['name'])` 取同名字段写入端口槽。
  即：想让 QQ 消息进入 Workflow，只需在工作流 Input 节点声明一个 `name == "raw_message"` 的端口（`docs/20-Event协议与流转.md:176`）。
- 端口不存在同名 payload 键时取到 `None`，运行期把 `None` 视为「没有值」（`docs/20:176`）。

### 6.2.4 转发键名、方向、失败与重试、幂等性

| 项 | 值 | 依据 |
| --- | --- | --- |
| 转发键 | `MAIN_AGENT_QUEUE_NAME`，默认 `main_agent_queue` | `qqbot_consumer/queue_client.py:9` |
| 转发方向 | `LPUSH`（左入）；消费端 `agent` 用 `BRPOP`（右出）→ 主队列内为 **FIFO** | `qqbot_consumer/queue_client.py:19`、`agent/queue_client.py:65` |
| 净效果 | 单个事件在 `qq:events` 内是 LIFO 排序，进入主队列后转为 FIFO 排序 | 上两行 |
| 失败处理 | 无重试。`handle_event` 抛异常 → 外层 `except` → `logger.exception` + `time.sleep(2)` → 继续循环 | `queue_consumer.py:44-50` |
| 重试声明 | 日志文案 `"the event remains available to retry"`（`:49`）**与事实不符**：`BLPOP` 已把元素移出队列，异常路径不会重入队 | `queue_consumer.py:40`、`queue_client.py:23-26` |
| 实际投递语义 | **at-most-once**。`record_history` 失败 → 既不存档也不转发；`publish_to_queue` 失败 → 已存档但转发丢失 | `queue_consumer.py:21,28` |
| 幂等性 | **无**。无 `message_id`、无唯一索引（`history_repository.py:25-26` 两索引均非唯一），重放会产生第二条存档 + 第二次工作流执行 | 同上 |
| Worker 状态 | 每轮写 `QQ_WORKER_STATUS_KEY`（默认 `qq:worker:status`）：循环起点写 `idle`，取到事件写 `processing`，`finally` 写回 `idle` | `queue_consumer.py:39,43,47`、`queue_client.py:32-34` |

---

## 6.3 Event 协议对齐表

### 6.3.1 信封

主队列 Event 的**唯一结构约束**是 `handle_task` 的两处强索引（`agent/task_worker.py:45,51,55`）：必须含 `event_type`（str）与 `payload`（对象）；`workflow` 类型还必须在 `payload` 内含 `workflow_id`（str）。

- `terminal` 额外带顶层 `time`（`webui_py/events.py:389`），主 worker 不读。
- `agent/history_repository.py:50-55` 存档时复制整个 Event 并追加 `created_at`（tz-aware），MongoDB 生成 `_id`。
- 索引：`event_type_id` = `(event_type ASC, _id DESC)`；`tool_call_id_payload` = `(payload.id ASC)` sparse（`agent/history_repository.py:38-46`）。

### 6.3.2 全部事件类型与字段

| event_type | scope | 生产者 | payload 字段（名 : 类型） | 依据 |
| --- | --- | --- | --- | --- |
| `qq` | main_queue | `qqbot/listener.py`（经 `qqbot_consumer` 筛选） | `post_type`: `"message"`\|`"inputing"`；`user_id`: int；`group_id`: int\|0\|null；`raw_message`: str；`message`: array\<object\> | `qqbot/listener.py:24-42`、`manager_webui/event_catalog.py:8-35` |
| `terminal` | main_queue | `webui_py/events.py` | `content`: str（strip 后非空、≤4000 字符）；`files`: array（当前必须为空） | `webui_py/events.py:379-391`、`event_catalog.py:36-62` |
| `workflow` | main_queue | `agent/task_worker.py`（绑定路由） | 原事件 payload 全部字段 + `workflow_id`: str（必需、保留、覆盖原值） | `agent/task_worker.py:49-52`、`test_task_worker.py:45-51`、`event_catalog.py:63-89` |
| `response` | main_queue | `agent/task_worker.py` | `content`: any（`output.get("content", output)`） | `agent/task_worker.py:90-93`、`event_catalog.py:116-138` |
| `error` | main_queue | `agent/task_worker.py` | `workflow_id`: str；`message`: 常量 `"workflow not found"` | `agent/task_worker.py:61-64`、`event_catalog.py:90-115` |
| `async_result` | **callback_queue** | `tool_server` | `task_id`: str；`tool`: str；`status`: `working`\|`completed`\|`failed`；`result`: any；`error`: str\|null；`progress`: any；`message`: str\|null | `tool_server/main.py:56-70`、`event_catalog.py:139-169` |
| `raw` | **display_only** | `webui_py/events.py` | `raw`: str | `webui_py/events.py:64-69`、`event_catalog.py:170-192` |

> 除上表外，任何 `event_type` 都会被 `handle_task` 走同一条绑定路由（`agent/task_worker.py:46-53`），包括自定义类型 —— 这是扩展新事件源的协议基础。

### 6.3.3 与 Workflow 画布 Input 端口的对接契约

**契约唯一实现点**：`agent/task_worker.py:82-87`

```python
input_node = workflow_map[start]              # 第一个 type == "input" 的节点
workflow_ports = input_node.get('workflowPorts', [])
for port in workflow_ports:
    propagate_workflow_output(workflow_map, input_node, port['id'], e['payload'].get(port['name']))
```

因此对接规则是：**Input 端口 `name` == Event payload 的键名**（不是端口 `id`；端口 `id` 由 `parse_workflow` 置为 `workflow:<name>`，见 `agent/workflow_parser.py:48-49`、`manager_webui/workflows.py:277-278`）。

| 事件源 | payload 键 | 是否可直接作为 Input 端口名 | 备注 |
| --- | --- | --- | --- |
| QQ 输入 | `raw_message` | ✅ 是（文本内容，`content` 类型端口） | `docs/20:176` 明确点名 |
| QQ 输入 | `post_type` | ✅ 是（`content`） | 值为 `"message"`/`"inputing"` |
| QQ 输入 | `user_id` | ⚠️ 名字可以，类型不行 | payload 是 int，端口类型表（`agent/workflow_contract.py:8-16`）**没有整数类型**，下游会以类型错误形式爆在远处 |
| QQ 输入 | `group_id` | ⚠️ 同上 | 私聊下发 `0` 而非 `null` |
| QQ 输入 | `message` | ❌ 否 | 是 OneBot 消息段数组，不是 LLM `message` 对象（`{role, content}`） |
| 终端输入 | `content` | ✅ 是 | `content` 类型 |
| 终端输入 | `files` | ⚠️ 目前恒为空数组 | `webui_py/events.py:384-385` 拒绝非空 |
| 绑定路由附加 | `workflow_id` | ✅ 是（可选） | `test_task_worker.py:89-101` 断言 `workflow_id` 会被暴露给同名端口 |
| 任意 | 未声明的 payload 键 | — | 被忽略；声明的端口若 payload 中无同名键则传 `None` |

补充约束：

- 每个 `event_type` 在 `event_bindings` 中**至多一条**：`webui_py/main.py:80` 建 `event_type` 唯一索引 `unique_event_binding_type`（启动时还会 `drop_index("unique_event_binding_route")` 清理旧索引，`webui_py/main.py:78-79`）。
- `event_type` 命名被 WebUI 限制为 `^[a-z][a-z0-9_.-]*$`、长度 ≤80（`webui_py/event_bindings.py:13-14,59-61`）。
- 绑定文档字段：`event_type`、`workflow_id`(ObjectId)、`workflow_name`(快照)、`enabled`、`created_at`、`updated_at`（`webui_py/event_bindings.py:25-34,69-74`）。
- 绑定查询只按 `{"event_type": X, "enabled": True}`，查询失败抛 `RuntimeError("failed to read event binding")`，不被当作「未绑定」（`agent/task_worker.py:36-41`、`test_task_worker.py:75-80`）。

### 6.3.4 队列取序语义（三套并存）

| 队列 | 入 | 出 | 效果 | 依据 |
| --- | --- | --- | --- | --- |
| `qq:events` | `LPUSH` | `BLPOP` | **LIFO**（后到先处理） | `qqbot/queue_client.py:19`、`qqbot_consumer/queue_client.py:25` |
| `main_agent_queue`（agent 生产者 / QQ 适配器） | `LPUSH` | `BRPOP` | **FIFO** | `agent/queue_client.py:33,65`、`qqbot_consumer/queue_client.py:19` |
| `main_agent_queue`（WebUI 终端） | `RPUSH` | `BRPOP` | **插队**：终端事件排在消费端一侧，当前任务结束后优先被取走 | `webui_py/events.py:393`、`agent/queue_client.py:65` |
| 专用回调队列（Tool Server → 消费者） | `LPUSH` | 由消费者自定 | 协议未规定 | `tool_server/main.py:141` |

WebUI 对 pending 列表的删除/编辑按 `LINDEX -position` + `LSET` + `LREM` 实现（`webui_py/events.py:229-243`），与 `BRPOP`（右端出队）方向一致 —— position 1 = 下一个被消费的元素。

---

## 6.4 Dockerfile 与服务镜像事实

| 服务 | 基础镜像 | apt 额外包 | CMD（镜像内） | 依赖锁定 | 依据 |
| --- | --- | --- | --- | --- | --- |
| `agent` | `python:3.11-slim-bookworm` | `ffmpeg` | 无（compose 给 `python task_worker.py`） | **全部无版本号**：pymongo / requests / redis / ffmpeg-python / pydub | `agent/Dockerfile:1-12`、`agent/requirements.txt:1-5` |
| `qqbot` | `python:3.11-slim-bookworm` | — | 无（compose 给 `python listener.py`） | **全部无版本号**：redis / websockets / pymongo | `qqbot/Dockerfile:1-8`、`qqbot/requirements.txt:1-3` |
| `qqbot_consumer` | `python:3.11-slim-bookworm` | — | 无（compose 给 `python queue_consumer.py`） | **全部无版本号**：redis / pymongo | `qqbot_consumer/Dockerfile:1-8`、`qqbot_consumer/requirements.txt:1-2` |
| `webui_py` | `python:3.12-slim` | — | 无（compose 给 uvicorn） | 精确 pin：fastapi 0.116.1 / pymongo 4.13.2 / redis 6.2.0 / uvicorn[standard] 0.35.0 | `webui_py/Dockerfile:1-8`、`webui_py/requirements.txt:1-4` |
| `manager_webui` | `python:3.12-slim` | — | 无（compose 给 uvicorn） | 同 webui_py | `manager_webui/Dockerfile`、`manager_webui/requirements.txt` |
| `workflow_editor` | `python:3.12-slim` | — | `uvicorn main:app --host 0.0.0.0 --port 8082` | 同 webui_py | `workflow_editor/Dockerfile:10` |
| `tool_server` | `python:3.12-slim` | — | `uvicorn main:app --host 0.0.0.0 --port 8083` | pin + `jsonschema==4.25.1` | `tool_server/Dockerfile:10`、`tool_server/requirements.txt:1-5` |
| `tool_provider` | `python:3.12-slim` | `ffmpeg` | `python main.py` | 混用：jsonschema 4.25.1 / websocket-client 1.8.0 pin，requests / pydub / pymongo 无版本 | `tool_provider/Dockerfile:14`、`tool_provider/requirements.txt:1-5` |

`.dockerignore` 覆盖情况（内容 6 行一致：`__pycache__/`、`*.py[cod]`、`*$py.class`、`.env`、`.git/`、`.gitignore`）：

| 服务 | 有 `.dockerignore` |
| --- | --- |
| `agent` / `qqbot` / `webui_py` / `manager_webui` | ✅ `agent/.dockerignore:1-6` 等 |
| `qqbot_consumer` / `workflow_editor` / `tool_server` / `tool_provider` | ❌ 缺失 |

---

## 服务拓扑全表

共 **10 个服务**（8 个应用 + `redis` + `mongodb`），全部接入自定义 bridge 网络 `aagent_net`（`docker-compose.yml:251-253`）。

| 服务 | 端口（宿主:容器） | 入口 / 启动命令 | 依赖（depends_on） | 环境来源 | 重启策略 | 健康检查 | 挂载（prod） | 依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `agent` | — | `python task_worker.py` | `redis` healthy、`mongodb` healthy | `env_file: .env` + 5 个 `environment` 覆盖 | `unless-stopped` | ❌ 无 | 无 | `docker-compose.yml:2-21` |
| `qqbot` | — | `python listener.py` | `redis` healthy | `env_file: .env` + `QQ_QUEUE_NAME` | `unless-stopped` | ❌ 无 | 无 | `:23-36` |
| `qqbot_consumer` | — | `python queue_consumer.py` | `redis` healthy、`mongodb` healthy | `env_file: .env` + 12 个 `environment`（含 `REDIS_HOST/PORT`、`MONGO_*`） | `unless-stopped` | ❌ 无 | 无 | `:38-63` |
| `webui_py` | `8081:8081` | `uvicorn main:app --host 0.0.0.0 --port 8081` | `redis` healthy、`mongodb` healthy | 仅 `environment`（**无 `env_file`**） | `unless-stopped` | ✅ `GET /api/health`（`python -c urllib`），10s/3s/5 次 | 无 | `:65-94` |
| `manager_webui` | `8084:8084` | `uvicorn main:app --host 0.0.0.0 --port 8084` | `redis` healthy、`mongodb` healthy | 仅 `environment` | `unless-stopped` | ✅ `GET 8084/api/health`，10s/3s/5 次 | 无 | `:96-129` |
| `workflow_editor` | `8082:8082` | 镜像 `CMD`（compose 未覆盖） | `redis` healthy、`mongodb` healthy | 仅 `environment` | `unless-stopped` | ✅ `8082/api/health`，10s/3s/5 次 | 无 | `:131-159` |
| `tool_server` | `8083:8083` | 镜像 `CMD`（compose 未覆盖） | `redis` healthy、`mongodb` healthy | 仅 `environment`（**唯一注入 `REDIS_PASSWORD`/`REDIS_DB` 的应用服务**） | `unless-stopped` | ✅ `8083/api/health`（同时 ping Redis + Mongo），10s/3s/5 次 | 无 | `:161-190` |
| `tool_provider` | — | 镜像 `CMD`（`python main.py`） | `tool_server` healthy | `env_file: .env` + 12 个 `environment` | `unless-stopped` | ❌ 无 | 无 | `:192-216` |
| `redis` | — (prod) / `6379:6379` (dev) | `redis-server --appendonly yes` | — | — | `unless-stopped` | ✅ `redis-cli ping`，3s/3s/10 次 | `./data/redis:/data` | `:218-231` |
| `mongodb` | — (prod) / `27015:27017` (dev) | 官方镜像默认 | — | `MONGO_INITDB_ROOT_USERNAME/PASSWORD` | ❌ **无 `restart`** | ✅ `mongosh` 带账号密码 `ping`，`start_interval 2s` / `start_period 60s` / `interval 30s` / `timeout 5s` / `retries 10` | `./data/mongo:/data/db` | `:233-249` |

补充事实：

- 所有应用服务 `container_name` 带 `_aagent` 后缀：`agent_aagent`、`qqbot_aagent`、`qqbot_consumer_aagent`、`webui_py_aagent`、`manager_webui_aagent`、`workflow_editor_aagent`、`tool_server_aagent`、`tool_provider_aagent`、`redis_aagent`、`mongo_aagent`。
- 服务间寻址依赖 Compose 默认 DNS（服务名），例如 `TOOL_SERVER_URL=http://tool_server:8083`、`TOOL_SERVER_WS_URL=ws://tool_server:8083/ws/providers`、`ws://host.docker.internal:3001`（QQ 上游在宿主机）。
- 无 `expose`、无 `internal: true`、无网络别名；`aagent_net` 与 `default` 网络无关联。
- 除 `mongodb` 外所有长驻服务均 `restart: unless-stopped`。

---

## 环境变量全表

汇总方式：对全仓 `*.py` 检索 `os.environ` / `os.getenv` / `getenv(`，再与 `.env.example`、`docker-compose*.yml` 逐条对账。
**总计 63 个条目**：代码实际读取 59 个，另 4 个仅在 `.env.example` 中声明且全仓无读取方（死配置：`DEEPSEEK_MODEL`、`ASR_URL`、`MODEL_ID`、`QQ_BOT_ID`）。分组计数：LLM/密钥 13 + QQ 9 + Redis/队列 10 + Tool 平台 16 + Mongo 12 + Workflow 状态 3 = 63。

「必填」= 缺失即崩溃（`os.environ[...]` 强读或显式校验）。

### 6.E.1 LLM 与第三方密钥（13）

| 变量 | 代码默认 | 必填 | 作用 | 读取方 | `.env.example` | compose 注入 |
| --- | --- | --- | --- | --- | --- | --- |
| `DEEPSEEK_BASE_URL` | 无 | ✅ | DeepSeek 余额查询基址 | `agent/tools/tool.py:10` | `:1` | 经 `env_file` 给 agent |
| `DEEPSEEK_API_KEY` | 无 | ✅ | 同上鉴权 | `agent/tools/tool.py:11` | `:2` | 经 `env_file` 给 agent |
| `DEEPSEEK_MODEL` | 无 | ❌ **死配置** | 无任何读取方；模型名实际取自 Mongo `models` 文档 | 无 | `:3` | — |
| `KIMI_BASE_URL` | 无 | ✅ | Kimi 余额查询基址 | `agent/tools/tool.py:13` | `:5` | 经 `env_file` |
| `KIMI_API_KEY` | 无 | ✅ | 同上鉴权 | `agent/tools/tool.py:14` | `:6` | 经 `env_file` |
| `ZAI_API_KEY` | 无 | ✅ | **导入期强读但无任何工具使用**（历史遗留，缺 Key 直接启动失败） | `agent/tools/tool.py:16` | `:7` | 经 `env_file` |
| `TAVILY_API_KEYS` | 无 | ✅（且非空） | 逗号分隔多 Key，轮转使用 | `agent/tools/tool.py:17-29` | `:8` | 经 `env_file` |
| `BOCHA_BASE_URL` | 无 | ✅ | 博查搜索基址（`bocha_search` 未注册为 tool） | `agent/tools/tool.py:23` | `:9` | 经 `env_file` |
| `BOCHA_API_KEY` | 无 | ✅ | 同上 | `agent/tools/tool.py:24` | `:10` | 经 `env_file` |
| `BILIBILI_COOKIE` | `""` | ❌ | B 站请求 Cookie | `tool_provider/tools/bilibili.py:14` | `:54` | 经 `env_file` 给 tool_provider |
| `BILIBILI_DOWNLOAD_DIR` | `/tmp/aagent-downloads` | ❌ | B 站下载目录 | `tool_provider/tools/bilibili.py:83` | ❌ 未声明 | 未注入 |
| `ASR_URL` | 无 | ❌ **死配置** | 无读取方 | 无 | `:55` | — |
| `MODEL_ID` | 无 | ❌ **死配置** | 无读取方 | 无 | `:56` | — |

### 6.E.2 QQ 事件源（9）

| 变量 | 代码默认 | 必填 | 作用 | 读取方 | `.env.example` | compose 注入 |
| --- | --- | --- | --- | --- | --- | --- |
| `QQ_API_BASE_URL` | 无 | ✅（用 QQ 工具时） | OneBot HTTP API 基址（发消息） | `tool_provider/tools/qqapi.py:7`；死文件 `agent/tools/qqapi.py:6` | `:12` | 经 `env_file` 给 tool_provider |
| `QQ_API_TOKEN` | 无 | ✅（同上） | OneBot HTTP `Bearer` | `tool_provider/tools/qqapi.py:9`；死文件 `agent/tools/qqapi.py:8` | `:13` | 同上 |
| `QQ_WS_URI` | 无 | ✅ | 事件 WS 地址 | `qqbot/listener.py:9` | `:14` | 经 `env_file` 给 qqbot |
| `QQ_WS_TOKEN` | 无 | ✅ | 事件 WS `Bearer` | `qqbot/listener.py:11` | `:15` | 同上 |
| `QQ_TARGET_USER_ID` | 消费端 `""`（默认拒绝） | ✅（listener 强读） | 唯一授权 QQ 号；listener 侧读入即弃，消费端才是实际判定 | `qqbot/listener.py:14`（死）、`qqbot_consumer/queue_consumer.py:27`（生效） | `:16` | 经 `env_file` 给两者 |
| `QQ_BOT_ID` | 无 | ❌ **死配置** | 无读取方；导致机器人自身消息无过滤 | 无 | `:17` | — |
| `QQ_QUEUE_NAME` | `qq:events` | ❌ | QQ 入队 Redis List | `qqbot/queue_client.py:10`、`qqbot_consumer/queue_client.py:8` | `:26` | 显式给 qqbot(`:34`) 与 consumer(`:53`) |
| `QQ_WORKER_STATUS_KEY` | `qq:worker:status` | ❌ | QQ 消费者状态 Key（**只写不读**） | `qqbot_consumer/queue_client.py:10,34` | `:28` | 显式给 consumer(`:55`) |
| `QQ_HISTORY_COLLECTION` | `qq_event_history` | ❌ | QQ 事件存档集合 | `qqbot_consumer/history_repository.py:11` | `:52` | 显式给 consumer(`:61`) |

### 6.E.3 Redis 与队列（10）

| 变量 | 代码默认 | 必填 | 作用 | 读取方 | `.env.example` | compose 注入 |
| --- | --- | --- | --- | --- | --- | --- |
| `REDIS_HOST` | `redis` | ❌ | Redis 主机 | `agent/queue_client.py:7`、`qqbot/queue_client.py:7`、`qqbot_consumer/queue_client.py:6`、`webui_py/main.py:33`、`manager_webui/main.py:38`、`workflow_editor/main.py:28`、`tool_server/settings.py:27` | `:19` | 显式给 `webui_py`/`manager_webui`/`workflow_editor`/`tool_server`/`qqbot_consumer`；`agent`/`qqbot`/`tool_provider` 靠 `env_file` |
| `REDIS_PORT` | `6379` | ❌ | 同上 | 同上一行 | `:20` | 同上 |
| `REDIS_PASSWORD` | 空 → `None` | ❌ | Redis 密码 | `webui_py/main.py:49`、`manager_webui/main.py:54`、`workflow_editor/main.py:31`、`tool_server/settings.py:30` | `:21` | **仅 `tool_server`(`:173`)**；`agent`/`qqbot`/`qqbot_consumer` 既不注入也不读取 |
| `REDIS_DB` | `0` | ❌ | 库号 | `webui_py/main.py:37`、`manager_webui/main.py:42`、`workflow_editor/main.py:30`、`tool_server/settings.py:29` | `:22` | 仅 `tool_server`(`:174`) |
| `REDIS_ADDR` | 未设 → `host:port` | ❌ | 覆盖 host:port 组合 | `webui_py/main.py:30`、`manager_webui/main.py:35`、`workflow_editor/main.py:28` | ❌ 未声明 | 未注入 |
| `REDIS_URL` | 未设 → 由 host/port/db/password 拼 | ❌ | 完整连接串（优先于上面 4 项） | `tool_server/settings.py:25` | ❌ 未声明 | 未注入 |
| `REDIS_SOCKET_TIMEOUT` | `30` | ❌ | socket 超时（**仅 agent 有**） | `agent/queue_client.py:9` | `:24` | 未注入（靠 `env_file`） |
| `MAIN_AGENT_QUEUE_NAME` | `main_agent_queue` | ❌ | 主队列 List | `agent/queue_client.py:11`、`qqbot_consumer/queue_client.py:9`、`webui_py/main.py:38` | `:27` | 显式给 `webui_py`(`:78`)、`qqbot_consumer`(`:54`) |
| `AGENT_WORKER_STATUS_KEY` | `aagent:worker:status` | ❌ | agent 运行状态 Key（8081 读取展示） | `agent/queue_client.py:12`、`webui_py/main.py:39` | `:25` | 显式给 `webui_py`(`:79`) |
| `AGENT_TOOLS_KEY` | `aagent:tools` | ❌ | 本地工具注册 Hash | `agent/queue_client.py:16`、`manager_webui/main.py:43`、`workflow_editor/main.py:50` | `:23` | 显式给 `manager_webui`(`:109`)、`workflow_editor`(`:143`)、`agent`(`:15`) |

### 6.E.4 Tool 平台（16）

| 变量 | 代码默认 | 必填 | 作用 | 读取方 | `.env.example` | compose 注入 |
| --- | --- | --- | --- | --- | --- | --- |
| `TOOL_SERVER_URL` | `http://tool_server:8083` | ❌ | Tool Server HTTP 基址 | `agent/tool_server_client.py:26`、`workflow_editor/main.py:51` | ❌ 未声明 | 显式给 `agent`(`:16`)、`workflow_editor`(`:144`) |
| `TOOL_SERVER_WS_URL` | `ws://tool_server:8083/ws/providers` | ❌ | Provider 注册 WS | `tool_provider/main.py:23` | ❌ 未声明 | 显式(`:202`) |
| `TOOL_CLIENT_DEFAULT_WAIT_MS` | `10000` | ❌ | `remote_sync_tool` 未填 `timeout_ms` 时 | `agent/workflow_nodes.py:412` | `:32` | 显式给 `agent`(`:17`) |
| `TOOL_CLIENT_MAX_WAIT_MS` | `10000` | ❌ | 管理页校验同步工具上限 | `manager_webui/workflows.py:858` | `:33` | 显式给 `agent`(`:18`)、`manager_webui`(`:110`) |
| `TOOL_CLIENT_DEFAULT_ASYNC_TIMEOUT_MS` | `600000` | ❌ | `remote_async_tool` 默认超时 | `agent/workflow_nodes.py:437` | ❌ **未声明** | 未注入 |
| `TOOL_CLIENT_MAX_ASYNC_TIMEOUT_MS` | `3600000` | ❌ | 管理页校验异步工具上限 | `manager_webui/workflows.py:859` | `:34` | 显式给 `manager_webui`(`:111`) |
| `TOOL_MAX_WAIT_MS` | `30000` | ❌ | 同步等待上限 | `tool_server/settings.py:47` | `:31` | 未注入 |
| `TOOL_TASK_TTL_SECONDS` | `86400` | ❌ | 任务 Key / 日志 TTL | `tool_server/settings.py:46` | `:30` | 未注入 |
| `TOOL_DISPATCH_TIMEOUT_SECONDS` | `5` | ❌ | 派发超时 | `tool_server/settings.py:48` | `:35` | 未注入 |
| `TOOL_CALLBACK_EVENT_TYPES` | `async_result` | ❌ | 允许的 callback `event_type` 白名单（逗号分隔） | `tool_server/settings.py:33-37` | `:29` | 显式给 `tool_server`(`:181`) |
| `TOOL_PROVIDER_ID` | `provider-default-01` | ❌ | Provider 注册 ID | `tool_provider/main.py:24` | `:36` | 显式(`:203`) |
| `TOOL_PROVIDER_REVISION` | **`3`** | ❌ | 工具/Provider 版本号（三处默认不一致） | `tool_provider/main.py:25` | `:37`（=2） | 显式(`:204`，=5) |
| `TOOL_PROVIDER_CONSUMERS` | `1` | ❌ | Provider 消费线程数 | `tool_provider/main.py:27` | `:38` | 显式(`:205`) |
| `TOOL_PROVIDER_QUEUE_SIZE` | `128` | ❌ | Provider 队列容量 | `tool_provider/main.py:28` | `:39` | 显式(`:206`) |
| `TOOL_PROVIDER_HEARTBEAT_SECONDS` | `20` | ❌ | 心跳间隔 | `tool_provider/main.py:29` | `:40` | 显式(`:207`) |
| `TOOL_MODULES` | `tools.system,tools.qq,tools.bilibili,tools.documents` | ❌ | 加载的工具模块 | `tool_provider/main.py:18` | `:41`（缺 `tools.system`） | 显式(`:208`) |

### 6.E.5 MongoDB 与集合（12）

| 变量 | 代码默认 | 必填 | 作用 | 读取方 | `.env.example` | compose 注入 |
| --- | --- | --- | --- | --- | --- | --- |
| `MONGO_HOST` | `mongodb` | ❌ | Mongo 主机 | `agent/history_repository.py:6`、`agent/llm.py:20`、`agent/task_worker.py:23`、`agent/workflow_parser.py:126`、`agent/workflow_session_repository.py:106`、`qqbot_consumer/history_repository.py:6`、`tool_provider/tools/documents.py:15`、`webui_py/main.py:40`、`manager_webui/main.py:44`、`workflow_editor/main.py:37` | `:43` | 显式给 5 个 Web 服务 + consumer + provider |
| `MONGO_PORT` | `27017` | ❌ | 同上 | 同上一行 | `:44` | 同上 |
| `MONGO_USER` | 未设 | ❌ | 账号；**同时是 Mongo root 初始化账号** | 上述全部 + `tool_server/settings.py:42` | `:45` | 显式给多个服务；`mongodb` 用它建 root(`:239`) |
| `MONGO_PASS` | `""` | ❌（`MONGO_USER` 存在时应给） | 密码 | 同上 | `:46` | 同上 |
| `MONGO_DATABASE` | `agent` | ❌ | 库名 | 上述全部 + `tool_server/settings.py:44` | `:47` | 显式给多个服务 |
| `MONGO_HISTORY_COLLECTION` | `event_history` | ❌ | 主事件历史集合 | `agent/history_repository.py:11`、`webui_py/main.py:43` | `:48` | 显式给 `webui_py`(`:85`)；agent 靠 `env_file` |
| `MONGO_DOCUMENT_COLLECTION` | `documents` | ❌ | 文档集合 | `manager_webui/main.py:47`、`tool_provider/tools/documents.py:30` | `:49` | 显式(`:117`、`:214`) |
| `MONGO_MODEL_COLLECTION` | `models` | ❌ | 模型注册表 | `agent/llm.py:32`、`manager_webui/main.py:48`、`workflow_editor/main.py:49` | `:50` | 显式给 `manager_webui`(`:118`)、`workflow_editor`(`:150`) |
| `MONGO_WORKFLOW_COLLECTION` | `workflows` | ❌ | Workflow 定义集合 | `agent/workflow_parser.py:138`、`webui_py/main.py:44`、`manager_webui/main.py:49` | `:51` | 显式给 `manager_webui`(`:119`)；**webui_py 未注入** |
| `MONGO_SESSION_COLLECTION` | `sessions` | ❌ | Session 集合 | `agent/workflow_session_repository.py:120`、`manager_webui/main.py:50` | ❌ 未声明 | 显式给 `agent`(`:19`)、`manager_webui`(`:120`) |
| `MONGO_EVENT_BINDING_COLLECTION` | `event_bindings` | ❌ | 事件绑定集合 | `agent/task_worker.py:36`、`webui_py/main.py:45` | ❌ 未声明 | **两者均未注入** |
| `MONGO_TOOL_TASK_LOG_COLLECTION` | `tool_task_logs` | ❌ | 工具任务日志 | `tool_server/settings.py:45` | ❌ 未声明 | 显式给 `tool_server`(`:180`) |

### 6.E.6 Workflow 状态（3）

| 变量 | 代码默认 | 必填 | 作用 | 读取方 | `.env.example` | compose 注入 |
| --- | --- | --- | --- | --- | --- | --- |
| `WORKFLOW_CONTEXT_TTL_SECONDS` | `86400` | ❌ | Context Redis Key TTL | `agent/workflow_context_repository.py:71` | ❌ 未声明 | 未注入 |
| `WORKFLOW_CONTEXT_MAX_VALUE_BYTES` | `1048576` | ❌ | 单值大小上限 | `agent/workflow_context_repository.py:75` | ❌ 未声明 | 未注入 |
| `WORKFLOW_SESSION_MAX_VALUE_BYTES` | `1048576` | ❌ | Session 单值大小上限 | `agent/workflow_session_repository.py:76` | ❌ 未声明 | 未注入 |

### 6.E.7 对账结论

| 结论 | 明细 |
| --- | --- |
| `.env.example` 声明但代码不读（死配置 4 个） | `DEEPSEEK_MODEL`、`ASR_URL`、`MODEL_ID`、`QQ_BOT_ID` |
| 代码读取但 `.env.example` 未声明（12 个） | `TOOL_SERVER_URL`、`TOOL_SERVER_WS_URL`、`TOOL_CLIENT_DEFAULT_ASYNC_TIMEOUT_MS`、`MONGO_SESSION_COLLECTION`、`MONGO_EVENT_BINDING_COLLECTION`、`MONGO_TOOL_TASK_LOG_COLLECTION`、`WORKFLOW_CONTEXT_TTL_SECONDS`、`WORKFLOW_CONTEXT_MAX_VALUE_BYTES`、`WORKFLOW_SESSION_MAX_VALUE_BYTES`、`BILIBILI_DOWNLOAD_DIR`、`REDIS_ADDR`、`REDIS_URL` |
| 三处默认值不一致 | `TOOL_PROVIDER_REVISION`：`.env.example:37`=2 / `docker-compose.yml:204`=5 / `tool_provider/main.py:25`=3 |
| 默认值语义不一致 | `TOOL_MODULES`：示例 2 个模块，compose 与代码 4 个模块 |
| 注入不对称 | `webui_py`/`manager_webui`/`workflow_editor`/`tool_server` 无 `env_file`，只能拿到 `environment` 块里列出的变量 |
| 历史上已登记的环境缺口 | `docs/审查日志/2026-10-11-全项目-审查报告.md:63` |

---

## 存储键与集合全表

### 6.S.1 Redis 键

| 键 | 类型 | 写入方 | 读取方 | TTL | 语义 | 依据 |
| --- | --- | --- | --- | --- | --- | --- |
| `qq:events` | List | `qqbot`（`LPUSH`） | `qqbot_consumer`（`BLPOP`） | 无 | QQ 事件缓冲，LIFO | `qqbot/queue_client.py:19`、`qqbot_consumer/queue_client.py:25` |
| `main_agent_queue` | List | `agent`（`LPUSH`）、`qqbot_consumer`（`LPUSH`）、`webui_py` 终端（`RPUSH`） | `agent`（`BRPOP`） | 无 | 统一主队列；agent 侧 FIFO，终端可插队 | `agent/queue_client.py:33,38,65`、`webui_py/events.py:393` |
| `qq:worker:status` | String | `qqbot_consumer` | **无读取方** | 无 | QQ 消费者状态快照 JSON（`state`/`event`/`started_at`/`updated_at`） | `qqbot_consumer/queue_client.py:34`、`queue_consumer.py:39,43,47` |
| `aagent:worker:status` | String | `agent` | `webui_py`（8081 事件流页） | 无 | agent 状态快照（`idle`/`processing` + 当前 `event`） | `agent/queue_client.py:43-46`、`webui_py/main.py:39,82-119` |
| `aagent:tools` | Hash | `agent`（field=tool 名，value=OpenAI function schema） | `manager_webui`（校验 local_tool 引用）、`workflow_editor`（渲染本地工具目录） | 无（每次 agent 启动 `DEL` 重建） | 本地工具注册表 | `agent/queue_client.py:49-61`、`manager_webui/workflows.py:869-878`、`workflow_editor/main.py:109` |
| `workflow-context:{ctx_<hex32>}` | String(JSON) | `agent/workflow_context_repository.py` | 同 | `WORKFLOW_CONTEXT_TTL_SECONDS`（默认 86400） | Workflow 内可变 Context 值 | `agent/workflow_context_repository.py:78-79`、`docs/21-Workflow Context节点设计.md` |
| `tool:task:{task_id}` | String(JSON) | `tool_server` | `tool_server` | `TOOL_TASK_TTL_SECONDS`（默认 86400） | 工具任务状态机 | `tool_server/task_store.py:70-71,79-84` |
| `tool:task:{task_id}:updates` | List | `tool_server`（Lua `LPUSH` + `LTRIM 0 0`） | `tool_server`（`BLPOP` 等待终态） | 同任务 TTL | 单元素变更通知，用于 `wait_for_terminal` 阻塞 | `tool_server/task_store.py:44-46,155` |
| `tool:tasks:recent` | ZSet | `tool_server` | `tool_server` | 无（按 score 定期 `ZREMRANGEBYSCORE`） | 最近任务索引（score = created_at 时间戳） | `tool_server/task_store.py:88-89,101` |
| `tool:callback:outbox` | List | `tool_server`（Lua 内 `LPUSH`） | `tool_server` 的 `callback_worker`（`BRPOPLPUSH`） | 无 | 回调投递 outbox | `tool_server/task_store.py:123`、`main.py:125,136` |
| `tool:callback:processing` | List | `tool_server`（`BRPOPLPUSH` 目标） | `tool_server`（启动时回灌 outbox） | 无 | 投递中回调，进程重启后恢复 | `tool_server/main.py:126-133,146-147` |
| `tool:providers` | Hash | `tool_server`（field=provider_id） | `tool_server` | 无（断连时 `HDEL`） | 在线 Provider 注册快照 | `tool_server/main.py:311-315,326` |

### 6.S.2 MongoDB 集合

| 集合 | 默认名（env） | 写入方 | 读取方 | 索引 | 依据 |
| --- | --- | --- | --- | --- | --- |
| 主事件历史 | `event_history`（`MONGO_HISTORY_COLLECTION`） | `agent/history_repository.py:50-55` | `webui_py` 事件流与终端历史、`agent` 的 `history` 节点 | `event_type_id`、`tool_call_id_payload`(sparse) | `agent/history_repository.py:38-46`、`webui_py/events.py:151-184,355-375`、`agent/workflow_nodes.py:342-351` |
| QQ 事件存档 | `qq_event_history`（`QQ_HISTORY_COLLECTION`） | `qqbot_consumer/history_repository.py:30-32` | **无读取方**（仅人工排查） | `created_at_desc`、`event_type_created_at` | `qqbot_consumer/history_repository.py:25-26` |
| Workflow 定义 | `workflows`（`MONGO_WORKFLOW_COLLECTION`） | `manager_webui/workflows.py` | `agent/workflow_parser.py:124-153`、`webui_py/event_bindings.py:40-54`、`manager_webui` | `name` 唯一（`unique_workflow_name`） | `manager_webui/main.py:85-88` |
| 事件绑定 | `event_bindings`（`MONGO_EVENT_BINDING_COLLECTION`） | `webui_py/event_bindings.py:84-131` | `agent/task_worker.py:21-41` | `event_type` 唯一（`unique_event_binding_type`） | `webui_py/main.py:76-82` |
| 文档 | `documents`（`MONGO_DOCUMENT_COLLECTION`） | `manager_webui/documents.py` | `manager_webui`、`tool_provider/tools/documents.py:29-30` | 见 `manager_webui/documents.py` | `manager_webui/main.py:47,73` |
| 模型注册表 | `models`（`MONGO_MODEL_COLLECTION`） | `manager_webui/models.py` | `agent/llm.py:30-36`、`workflow_editor/main.py:86-104` | `name` 唯一（`unique_model_name`） | `manager_webui/main.py:84` |
| Session | `sessions`（`MONGO_SESSION_COLLECTION`） | `agent/workflow_session_repository.py:118-122`、`manager_webui/sessions.py` | 同上 | `updated_at`（`session_updated_at`） | `manager_webui/main.py:89` |
| 工具任务日志 | `tool_task_logs`（`MONGO_TOOL_TASK_LOG_COLLECTION`） | `tool_server/task_log_repository.py:27-45` | `tool_server/main.py:194-217,283-288` | `task_id_logged_at`、`logged_at_desc` | `tool_server/task_log_repository.py:17-25` |

### 6.S.3 持久化目录

| 宿主路径 | 容器内路径 | 服务 | 内容证据 |
| --- | --- | --- | --- |
| `./data/redis` | `/data` | `redis` | `data/redis/appendonlydir/appendonly.aof.manifest`（AOF 开启） |
| `./data/mongo` | `/data/db` | `mongodb` | `data/mongo/WiredTiger*`、`collection-*.wt`、`diagnostic.data/metrics.*` |

`data/` 被 `.gitignore:5` 忽略；`docker-compose.dev.yml:9` 的注释也说明它仅用于本机排查。

### 6.S.4 生产 / dev 配置差异

| 维度 | `docker-compose.yml`（生产） | `docker-compose.dev.yml`（覆盖） |
| --- | --- | --- |
| 源码挂载 | 无（代码在镜像内） | 8 个应用服务全部挂 `./<svc>:/app`（`:15,26,34,44,53,62,71,80`） |
| 入口进程 | 各自真实入口 | `agent`/`qqbot`/`qqbot_consumer` 改为 `sleep infinity`（`:17,27,35`）；其余 5 个仍跑原命令 |
| depends_on 条件 | `service_healthy`（受健康检查门控） | 全部降级为 `service_started`（`:18-83`）→ 启动不再等健康检查 |
| 宿主端口 | 仅 8081/8082/8083/8084 | 额外发布 `6379:6379`（Redis，无鉴权）与 `27015:27017`（Mongo，非标准宿主端口） |
| 镜像构建 | 同 | 建议叠加 `--build`（`:4` 注释） |

---

## 6.5 开发调试流程

1. 启动（`docker-compose.dev.yml:4`、`README.md:147`）：
   `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build`
2. 手动跑入口（以 agent 为例，`README.md:148`）：`docker compose exec agent python task_worker.py`
   —— `agent`/`qqbot`/`qqbot_consumer` 被 `sleep infinity` 占位，因此**必须**手动 exec 才会真正消费队列。
3. 改代码如何生效：

| 服务 | dev 下改代码 | 是否需要重建 |
| --- | --- | --- |
| `agent` / `qqbot` / `qqbot_consumer` | 挂载生效；进程本来就是手动 exec 的，重跑即可 | 否（除非改了 `requirements.txt`） |
| `webui_py` / `manager_webui` / `workflow_editor` / `tool_server` / `tool_provider` | 挂载生效，但进程由镜像 `CMD`/compose `command` 启动，**uvicorn 未带 `--reload`**（`docker-compose.yml:68,99`、`workflow_editor/Dockerfile:10`、`tool_server/Dockerfile:10`）→ 需 `docker compose restart <svc>` | 否，但需重启进程 |
| 生产配置下的任何服务 | 代码在镜像内 | 是：`docker compose up -d --build <服务>`（`README.md:153`） |

4. 静态资源版本键 `?v=N` 的缓存约束（`README.md:153`）：

| 页面 | 版本键 | 依据 |
| --- | --- | --- |
| `webui_py/static/bindings.html` | `/css/bindings.css?v=2`、`/bindings.js?v=2` | `:9,107` |
| `manager_webui/static/sessions.html` | `/css/sessions.css?v=6`、`/sessions.js?v=7` | `:9,41` |
| `manager_webui/static/document.html` | `/document.js?v=documents-4`（非纯数字） | `:75` |
| `workflow_editor/static/workflow_edit.html` | `/css/workflow.css?v=16`、`/workflow.js?v=23` | `:9,578` |
| `webui_py/static/index.html`、`terminal.html`、`manager_webui/static/{workflows,events,model}.html`、`tool_server/static/index.html` | **无版本键** | `index.html:93`、`terminal.html:73`、`workflows.html:151`、`events.html:74`、`model.html:47`、`tool_server/static/index.html:113` |

   服务端缓存策略：`webui_py` 与 `manager_webui` 的 `RevalidatingStaticFiles` 对 `.html` 下发 `Cache-Control: no-store`，其余 `no-cache`（`webui_py/main.py:143-147`、`manager_webui/main.py:169-173`）；`workflow_editor` 与 `tool_server` 对所有响应下发 `no-store[, no-cache, must-revalidate, max-age=0]`（`workflow_editor/main.py:58`、`tool_server/main.py:173`）。因此 `?v=N` 实际只在 `no-cache`（允许缓存 + 需校验）语义下起显式破缓存作用，且并非所有页面都遵循该约定。

---

## 6.6 安全与密钥管理

| 主题 | 现状 | 依据 |
| --- | --- | --- |
| 密钥存储约定 | 全部凭据放根目录 `.env`，模板为 `.env.example`（`replace-me` 占位）；`.gitignore` 忽略 `.env` 与 `.env.*`，仅保留 `.env.example` | `.gitignore:1-3`、`.env.example:2` |
| 数据不提交 | `.gitignore:5` 忽略 `data/`；`data/` 下确有 Redis AOF 与 Mongo WiredTiger 实际数据 | `.gitignore:5`、`data/mongo/WiredTiger`、`data/redis/appendonlydir/appendonly.aof.manifest` |
| 运行时个人配置 | `agent/settings.json` 被忽略（含个人 QQ 号），但该文件与相关读取代码当前已不存在 | `.gitignore:7-8` |
| 应用直连 Mongo root | `mongodb` 用 `MONGO_USER`/`MONGO_PASS` 建 root（`MONGO_INITDB_ROOT_*`），全部应用用**同一账号** + `authSource=admin` 连接 → 无最小权限账号 | `docker-compose.yml:239-240`、`agent/history_repository.py:29-34`、`tool_server/main.py:37-42` |
| Redis 无鉴权 | `redis` 命令未启用 `requirepass`；`REDIS_PASSWORD` 只注入 `tool_server`，`agent`/`qqbot`/`qqbot_consumer` 客户端根本不读密码 | `docker-compose.yml:224,173`、`agent/queue_client.py:22-28`、`qqbot/queue_client.py:14` |
| HTTP 接口无鉴权 | 4 个 Web 服务均无认证依赖、无 CORS、无限流，仅有安全响应头（CSP / `X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy`）；8081/8082/8083/8084 发布到宿主机所有网卡 | `webui_py/main.py:85-92`、`manager_webui/main.py:94-101`、`workflow_editor/main.py:54-64`、`tool_server/main.py:169-177` |
| 队列 token 明文 | `QQ_WS_TOKEN` / `QQ_API_TOKEN` 以 `Bearer` 走明文 `ws://` / `http://`（上游为宿主机 `host.docker.internal`） | `qqbot/listener.py:11`、`tool_provider/tools/qqapi.py:7-11`、`.env.example:12,14` |
| 容器网络隔离 | 单一自定义 bridge `aagent_net`（`driver: bridge`），无 `internal: true`、无子网划分；所有服务同网段可互访 | `docker-compose.yml:251-253` |
| 生产端口暴露面 | 仅 8081-8084 映射宿主；Redis/Mongo 不发布 | `docker-compose.yml:86-87,121-122,151-152,182-183` |
| dev 暴露面 | Redis 6379 + Mongo 27015 映射宿主，均无 TLS；Redis 无密码 | `docker-compose.dev.yml:85-91` |
| 已登记风险 | 「WebUI 完全无鉴权」（`docs/审查日志/2026-08-06-全项目review-审计报告.md:39` N2）、「应用直连 MongoDB root 账号」（同文 `:67` N19）、「全部 HTTP 接口无任何鉴权,且端口对外发布」（`docs/审查日志/2026-09-14-全项目-问题报告.md:191` H-02）、「Redis 连接参数不统一」（`docs/审查日志/架构问题汇总.md:36` A-10） | 同上 |

---

## 扩展槽

### 扩展槽 1：新增一个事件源适配器（推荐路径：复用绑定路由）

对接契约（唯一硬约束）：Event 信封 `{event_type: str, payload: object}`；`event_type` 命名 `^[a-z][a-z0-9_.-]*$` 且 ≤80 字符（`webui_py/event_bindings.py:13-14`）；`payload` 的键名要与目标 Workflow 的 Input 端口 `name` 一致（`agent/task_worker.py:83-87`）。

最小实现清单：

| 步骤 | 动作 | 是否必须 | 依据/模板 |
| --- | --- | --- | --- |
| 1 | 选定 `event_type`（例如 `webhook`、`cron`） | 必须 | `webui_py/event_bindings.py:13-14` |
| 2 | 写一个采集进程，构造信封并 `LPUSH MAIN_AGENT_QUEUE_NAME` | 必须 | 模板：`qqbot_consumer/queue_client.py:17-20`（20 行以内） |
| 3 | 在目标 Workflow 的 Input 节点声明与 payload 键同名的端口 | 必须 | `agent/task_worker.py:82-87`、`manager_webui/workflows.py:665-672` |
| 4 | 建一条 `event_bindings` 文档（`event_type` / `workflow_id` / `workflow_name` / `enabled`） | 必须（走绑定路径时） | 推荐直接用 8081 `POST /api/event-bindings`（`webui_py/event_bindings.py:84-95`）；每类型至多一条（`webui_py/main.py:80`） |
| 5 | 把类型加进 `manager_webui/event_catalog.py` 的 `EVENT_CATALOG` | 建议 | `manager_webui/event_catalog.py:6-193`；**必须同步改** `manager_webui/test_event_catalog.py:13` 的集合断言 |
| 6 | 加 compose 服务块 + `Dockerfile` + `requirements.txt` + `.dockerignore` | 仅容器化时 | 模板：`docker-compose.yml:23-36`（qqbot 块最简） |
| 7 | 若需要两段式（缓冲 + 筛选），照抄 `qqbot` + `qqbot_consumer` 双服务模式 | 可选 | `docs/20-Event协议与流转.md:303-312` 的修改检查表 |

**更短的旁路路径**：跳过绑定层，直接产出 `{"event_type": "workflow", "payload": {..., "workflow_id": "<ObjectId>"}}` 写入主队列。此路径**不需要**改 compose、不需要 binding 文档、agent 侧零改动（`agent/task_worker.py:46,55`；`README.md:93`；`docs/24:40`）。代价是 `workflow_id` 被硬编码进适配器，无法在 WebUI 上切换。

### 扩展槽 2：新增一个服务

| 要改的文件 | 具体内容 |
| --- | --- |
| `docker-compose.yml` | 新服务块：`build`、`container_name`、`command`、`restart: unless-stopped`、`depends_on`（用 `condition: service_healthy` 并确保被依赖方有 healthcheck）、`environment`（**注意：若不加 `env_file: .env`，必须把每个变量逐条列进 `environment`**）、`ports`（仅浏览器直连才需要）、`healthcheck`、`networks: [aagent_net]` |
| `docker-compose.dev.yml` | 加 `./<svc>:/app` 挂载（可写代码）；把 `depends_on` 降级为 `condition: service_started`；若要手动跑入口再加 `command: ["sleep","infinity"]` |
| 新目录 | `Dockerfile`（`FROM python:3.12-slim` 与多数服务一致）、`requirements.txt`（**精确 pin**，与 webui 系对齐）、`.dockerignore`（照抄 `agent/.dockerignore:1-6`） |
| 本文档 | 把服务登记进「服务拓扑全表」，把新增 env 登记进「环境变量全表」，把新增集合/键登记进「存储键与集合全表」 |
| `README.md:100-111` | 服务与端口表 |
| 注意 | 仓库**没有共享代码层**（`docs/审查日志/架构问题汇总.md:31` A-05），队列客户端/历史仓储只能复制；服务间通过 Compose DNS 用服务名互访，无需发布端口 |

### 扩展槽 3：环境变量如何扩展

1. 在 `.env.example` 按现有分组（LLM / QQ / 队列 / Tool / 存储）追加一行，写清默认值，避免出现第三处默认值。
2. 在 `docker-compose.yml` 的**每一个需要读该变量的服务**的 `environment` 加 `${VAR:-default}`；没有 `env_file: .env` 的 4 个服务（`webui_py`/`manager_webui`/`workflow_editor`/`tool_server`）**必须**显式列出，否则代码只会拿到自己的 `os.getenv` 默认值。
3. 三处默认值必须一致：`.env.example`、compose 的 `${VAR:-...}`、代码的 `os.getenv(..., "...")`。反例：`TOOL_PROVIDER_REVISION` 的 2/5/3。
4. 强读变量（`os.environ[...]`）必须无条件出现在 `.env.example`，否则容器启动即失败（当前 13 个强读变量里 `QQ_WS_URI`/`QQ_WS_TOKEN`/`QQ_TARGET_USER_ID`/8 个 LLM Key 都在示例里）。
5. 新增变量后同步登记进本文档「环境变量全表」，并声明读取方 `文件:行号`。

### 扩展槽 4：回调消费者如何扩展

现状：**仓库内不存在任何专用的 `async_result` 消费者**；但**主 worker 本身就能消费它**——给它建一条启用绑定即可（下方路线 A）。生产端在 `tool_server`：

1. 节点参数 `arguments.callback = {type: "redis", queue: "<队列名>", event_type: "async_result", on: ["working","completed","failed"]}`（`tool_server/models.py:28,44`；前端默认值 `tool_server/static/console.js:320-324`）。**`queue` 可以是 `main_agent_queue`。**
2. `event_type` 被 `TOOL_CALLBACK_EVENT_TYPES` 白名单校验，不在白名单直接 400（`tool_server/main.py:233-234`、`settings.py:33-37`）。
3. 状态转移的 Lua 脚本原子地把回调 JSON 写入 `tool:callback:outbox`（`tool_server/task_store.py:47-49,118-133`）。
4. `callback_worker()` 用 `BRPOPLPUSH outbox → processing`，成功后 `LPUSH record["queue"]` 投递（`tool_server/main.py:136-142`），失败回灌 outbox 并 sleep 1s（`:143-149`）；进程重启时把 `processing` 残留回灌 outbox（`:127-133`）。
5. 回调信封：`{event_type, payload: {task_id, tool, status, result, error, progress, message}}`（`tool_server/main.py:56-70`）。

扩展步骤（**两条路线，先选路线再决定队列**）：

| | 路线 A：交给 Agent（推荐，无需新容器） | 路线 B：自建消费者 |
| --- | --- | --- |
| 适用 | 回调要唤醒 / 续跑某个 Workflow | 回调只做审计落库、通知外部系统，或需要独立处理节奏 |
| `callback.queue` | `main_agent_queue` | 自定义专用队列名 |
| 谁消费 | `agent` 的 `BRPOP`（`agent/queue_client.py:65`） | 你的消费者 `BLPOP` 专用队列 |
| 必备动作 | 在绑定页给 `async_result` 建**一条启用绑定**（`POST /api/event-bindings`，`webui_py/event_bindings.py:84-95`） | 无需绑定；落库可仿 `qqbot_consumer/history_repository.py:30-32` |
| 结果 | 主 worker 走通用绑定路由，把回调 payload + `workflow_id` 发布成 `workflow` 事件（`agent/task_worker.py:46-53`） | 自行重发布 `{"event_type": "workflow", "payload": {..., "workflow_id": "..."}}` 到主队列 |

共同前置：把目标 `event_type` 加进 `TOOL_CALLBACK_EVENT_TYPES`（逗号分隔）并重启 `tool_server`。幂等由消费方自负：投递是 at-least-once（失败回灌 outbox）。

**路线 A 为什么成立（本节原稿在此处有误，已修正）**：`docs/20-Event协议与流转.md:247`、`README.md:98` 称"主 worker 没有 `async_result` handler，故不能写主队列"。该结论出自**旧的按类型白名单分发**架构；现行 `agent/task_worker.py:46` 的条件是 `event_type != "workflow"`，对**任意**类型开放绑定路由，因此 `async_result` 有一条绑定即可被主 worker 消费，**不需要专用消费者**。`docs/19:150` 的 `main_agent_queue` 示例本来就是对的。

**什么时候才必须用专用队列**：只在你确实要另起消费者时。`agent` 用 `BRPOP` 占着 `main_agent_queue`（`agent/queue_client.py:65`），对**同一** List 再加 `BLPOP/BRPOP` 会与它抢事件——路线 B 必须换队列，路线 A 不新增消费者，不受此限。

### 扩展槽 5：把 Workflow 输出回送 QQ

现状：`response` 事件只落 `event_history`（`agent/task_worker.py:90-93`），并由 8081 终端历史页展示（`webui_py/events.py:355-375`）。**没有任何代码读取 `response` 去调 QQ**。出站能力只以「工具」形式存在：

- `qq.send_private_msg(user_id, message)` / `qq.send_group_msg(group_id, message)`（`tool_provider/tools/qq.py:7-64`）
- 底层 `POST {QQ_API_BASE_URL}/send_private_msg`，头 `Authorization: Bearer ${QQ_API_TOKEN}`（`tool_provider/tools/qqapi.py:6-36`）

推荐扩展方式（无需新基础设施）：在画布上用 `remote_sync_tool` 节点调用上述工具，输入端口 `user_id` + `message` 分别接 `user_id` 与 LLM 输出端口；`qq.send_*` 工具已在 `TOOL_MODULES` 默认值内（`tool_provider/main.py:18`）。

若要新增推送消费者，必须走专用队列（不能挂 `main_agent_queue`），并注意：`response`/`error` 同样会经过绑定路由（`agent/task_worker.py:46-52`），因此可以给 `response` 建一条绑定，但要注意这会让「输出 → 新工作流 → 新输出」形成环，且 `workflow_validator` 不做环检测（`docs/审查日志/架构问题汇总.md:25` A-04）。

---

## 已知缺陷与不一致

按严重度排列。前 6 条为功能性缺陷，其余为配置/文档漂移。

| # | 级别 | 摘要 | 证据 |
| --- | --- | --- | --- |
| D-01 | **高** | `qqbot_consumer` 声称可重试，实际 at-most-once，异常时静默丢事件 | `queue_consumer.py:49` vs `:40`、`queue_client.py:23-26` |
| D-02 | **高** | 未授权用户私聊消息被投递并**无条件存档**（授权判定在存档之后） | `queue_consumer.py:21` 先于 `:27`；`qqbot/listener.py:31-42` 无用户过滤 |
| D-03 | **高** | `response` / `error` 实际参与绑定路由，与文档「不参与」冲突，可构成事件回环 | `agent/task_worker.py:46-52`、`test_task_worker.py:63-73` vs `docs/20:78`、`docs/24:14` |
| D-04 | **中** | `QQ_TARGET_USER_ID` 在 listener 中被读入即弃（死变量），但被 `os.environ[]` 强读 → 缺变量时监听器崩溃，配置了也无过滤作用 | `qqbot/listener.py:14`（全文件唯一引用） |
| D-05 | **中** | 无幂等：`message_id` 等字段被丢弃且无唯一索引，重放会二次存档 + 二次执行 | `qqbot/listener.py:33-42`、`qqbot_consumer/history_repository.py:25-26` |
| D-06 | **中** | `inputing` 噪音永久落库，集合无 TTL 索引 | `qqbot/listener.py:23-30`、`queue_consumer.py:21,30-31`、`history_repository.py:25-26` |
| D-07 | 中 | 绑定集合名在 agent 与 webui_py 之间可能不同步：`MONGO_EVENT_BINDING_COLLECTION`/`MONGO_WORKFLOW_COLLECTION` 被 `webui_py` 读取但 compose 未注入，而 agent 经 `env_file .env` 能拿到 → 在 `.env` 里改集合名会让两者读不同集合 | `webui_py/main.py:44-45`、`docker-compose.yml:75-85`、`agent/task_worker.py:36` |
| D-08 | 中 | 启用 `REDIS_PASSWORD` 会打断整条事件链：只有 `tool_server` 注入且只有 4 个服务读该变量，agent/qqbot/qqbot_consumer 客户端不读 | `docker-compose.yml:173`、`agent/queue_client.py:22-28`、`qqbot/queue_client.py:14`、`qqbot_consumer/queue_client.py:14` |
| D-09 | 中 | `?v=N` 破缓存约定只覆盖 4 个页面；README 表述为通用做法 | `bindings.html:9,107`、`sessions.html:9,41`、`document.html:75`、`workflow_edit.html:9,578` vs `index.html:93`、`terminal.html:73`、`workflows.html:151`、`events.html:74`、`model.html:47` |
| D-10 | 中 | dev 覆盖把所有 `depends_on` 降级为 `service_started`，健康检查门控在开发态完全失效（启动竞态被掩盖） | `docker-compose.dev.yml:18-83` |
| D-11 | 中 | `TOOL_PROVIDER_REVISION` 三处默认值不一致（2 / 5 / 3） | `.env.example:37`、`docker-compose.yml:204`、`tool_provider/main.py:25` |
| D-12 | 低 | `TOOL_MODULES` 示例值缺 `tools.system`，照抄示例会丢掉 system 工具模块 | `.env.example:41` vs `docker-compose.yml:208`、`tool_provider/main.py:18` |
| D-13 | 低 | `QQ_BOT_ID`、`DEEPSEEK_MODEL`、`ASR_URL`、`MODEL_ID` 为死配置（`.env.example` 声明、无读取方）；同时**没有任何机器人自身消息过滤** | `.env.example:17,3,55,56`；全仓检索无读取方；`qqbot/listener.py` 从不读 `self_id` |
| D-14 | 低 | 12 个代码实际读取的变量未进 `.env.example`（含 `TOOL_CLIENT_DEFAULT_ASYNC_TIMEOUT_MS`、`MONGO_EVENT_BINDING_COLLECTION`、`WORKFLOW_*`、`REDIS_ADDR`/`REDIS_URL` 等） | 见 §6.E.7 |
| D-15 | 低 | `qq:worker:status` 只写不读，QQ 消费者无任何可视化状态 | `qqbot_consumer/queue_client.py:34` vs 全仓无读取方；`webui_py/main.py:39` 读的是 `aagent:worker:status` |
| D-16 | 低 | `qqbot`/`qqbot_consumer` 的 Redis 客户端无 `socket_timeout`（agent 有）→ Redis 挂起时可能无限阻塞 | `qqbot/queue_client.py:13-14`、`qqbot_consumer/queue_client.py:13-14` vs `agent/queue_client.py:9` |
| D-17 | 低 | 缺 `.dockerignore` 的服务会把 `__pycache__` 打进镜像；残留缓存文件证明曾有已删除模块（`qqbot/mq.py`、`qqbot/qqapi.py`、`qqbot_consumer/llm.py`） | `qqbot/__pycache__/mq.cpython-311.pyc`、`qqapi.cpython-311.pyc`、`qqbot_consumer/__pycache__/llm.cpython-311.pyc` |
| D-18 | 低 | `mongodb` 服务唯一没有 `restart` 策略 | `docker-compose.yml:233-249` |
| D-19 | 低 | 基础镜像与依赖锁定策略分裂：3 服务 3.11 + 全无版本号，5 服务 3.12 + 精确 pin；`qqbot` 的未锁 `websockets` 与 `additional_headers`（≥12）耦合 | `agent/Dockerfile:1`、`qqbot/requirements.txt:2`、`qqbot/listener.py:51`、`webui_py/requirements.txt:1-4` |
| D-20 | 低 | `CMD` 位置不一致：5 个 Dockerfile 无 `CMD`（靠 compose），3 个有 `CMD` | `webui_py/Dockerfile:1-8` vs `tool_server/Dockerfile:10` |
| D-21 | 低 | QQ 私聊 `group_id` 上游下发 `0` 而非 `null`，与 `docs/20:95` 示例不符；消费端用假值判断侥幸兼容 | `qqbot/listener.py:22,38` vs `docs/20-Event协议与流转.md:95` |
| D-22 | 低 | 文档漂移：「QQ consumer 用 `RPUSH` 投递 `workflow` Event」在两个位置错误（实际 `LPUSH` + 原 `qq` 信封）；`README:96` 又说 handler 把 `qq`/`terminal` 转成 `workflow`（实际由绑定路由完成） | `docs/功能全景/_sections/00-概述与能力矩阵.md:72`、`README.md:96` vs `qqbot_consumer/queue_consumer.py:28`、`agent/task_worker.py:49-52` |
| D-23 | 低 | `event_catalog` 漂移：`async_result.status` 枚举缺 `working`（实际会推送）；`terminal.payload.additionalProperties: false` 与绑定路由注入 `workflow_id` 的事实相抵（目录描述的是绑定前信封） | `manager_webui/event_catalog.py:57,158` vs `tool_server/main.py:56-70,110-111`、`agent/task_worker.py:51` |
| D-24 | 低 | 历史审查日志中的变量名/集合名已失效（`QQ_AGENT_QUEUE_NAME`、`subagent_qq_history`、`QQ_AGENT_SETTINGS_KEY`、`MONGO_SETTINGS_COLLECTION`、`AGENT_SYSTEM_PROMPT_KEY`、`DASHSCOPE_API_KEY`），按日志排查当前配置会被误导 | `docs/审查日志/2026-09-14-全项目-问题报告.md:109,177-178,589,615-623`（全仓已无对应代码） |
| D-25 | 低 | `tool:callback:processing` 用 `lrem(..., 1, item)` 按值删除，重复负载时会删错条目 | `tool_server/main.py:142`（已在 `docs/审查日志/2026-10-11-全项目-审查报告.md:73` 登记） |

### 与 `docs/` 已登记项的对照

| 本节编号 | `docs/` 已登记项 | 关系 |
| --- | --- | --- |
| D-04 / D-13 | `docs/审查日志/2026-10-11-全项目-审查报告.md:110` B7、`docs/审查日志/架构问题汇总.md:37` A-11 | 部分重叠（`.env.example` 缺口与依赖锁定）；「listener 不校验发送者」在 `docs/审查日志/2026-09-14-全项目-问题报告.md:587-593` 已登记，但该文引用的 `QQ_AGENT_QUEUE_NAME`、`subagent_qq_history` 已失效 |
| D-08 | `docs/审查日志/架构问题汇总.md:36` A-10、`docs/审查日志/2026-09-14-全项目-问题报告.md:627-637` M-21 | 一致，本轮复核仍成立 |
| D-11 / D-12 | `docs/审查日志/2026-10-11-全项目-审查报告.md:110` B7、`:63` | 一致，本轮复核仍成立 |
| D-17 / D-19 / D-20 | `docs/审查日志/2026-09-14-全项目-问题报告.md:575-585` M-16/M-17、`docs/审查日志/架构问题汇总.md:37` A-11 | 一致，且 `.dockerignore` 现状比历史记录（3 个）多 1 个（`manager_webui`），仍缺 4 个 |
| D-25 | `docs/审查日志/2026-10-11-全项目-审查报告.md:73` | 完全一致 |
| D-03 | 无 | **新发现**：文档与代码 + 单元测试三方冲突 |
| D-07 | 无 | **新发现**：集合名注入不对称导致 agent / webui_py 集合分叉 |
| D-09 / D-10 | 无（README:153 只泛泛提示 `?v=N`） | **新发现**：破缓存约定覆盖不全；dev 覆盖关闭健康检查门控 |
