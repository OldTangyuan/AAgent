# 01 Agent 运行时（agent/）

> 范围：`agent/` 目录下的运行时进程、Workflow 执行引擎、节点契约与校验、LLM/远程工具接入、持久化与调试入口。
> 依据：只读源码与测试交叉印证，所有结论附 `文件:行号`。测试通过即视为该行为已被契约固化，测试失败/矛盾处单独标注。

## 1.1 文件清单与角色

| 文件 | 行数 | 角色 | 是否被运行进程加载 |
| --- | --- | --- | --- |
| `agent/task_worker.py` | 126 | 进程入口、队列主循环、事件分流、Workflow 启动 | 是（`command: ["python","task_worker.py"]`，`docker-compose.yml:5`） |
| `agent/workflow_parser.py` | 160 | 画布文档 → 索引链表结构的编译 | 是（`task_worker.py:8`） |
| `agent/workflow_nodes.py` | 602 | 节点处理器实现 + `nodes_map` 分发表 + 执行主循环 | 是（`task_worker.py:10`） |
| `agent/workflow_contract.py` | 368 | 节点类型/参数/端口/连线类型表（唯一权威来源） | 是（`workflow_parser.py:13`） |
| `agent/workflow_validator.py` | 711 | 保存/执行期不变量校验 | 是（`task_worker.py:9`） |
| `agent/llm.py` | 78 | 模型配置读取 + OpenAI 兼容 chat completion | 是（懒加载，`workflow_nodes.py:121`） |
| `agent/tool_server_client.py` | 60 | 远程工具 HTTP 客户端（wait / async） | 是（懒加载，`workflow_nodes.py:393`） |
| `agent/queue_client.py` | 69 | Redis 队列、worker 状态键、工具注册表 | 是 |
| `agent/history_repository.py` | 75 | 事件历史 MongoDB 仓库（含两处索引） | 是 |
| `agent/workflow_context_repository.py` | 193 | Workflow Context（Redis，运行期可变单元） | 是（懒加载，`workflow_nodes.py:60`） |
| `agent/workflow_session_repository.py` | 186 | Workflow Session（MongoDB，跨运行全局值） | 是（懒加载，`workflow_nodes.py:495`） |
| `agent/utils.py` | 3 | `env(name, fallback)` 一行封装 | **否**（仅被 `tools/documents.py:1` 引用） |
| `agent/debug_workflow.py` | 56 | 拉取并打印解析后的 workflow map（离线 CLI） | 否（人工执行） |
| `agent/tools/tool.py` | 180 | 本地工具注册表 + `execute_tool` 分发 | 是（`llm.py:8`、`workflow_nodes.py:122`） |
| `agent/tools/documents.py` | 212 | 文档 CRUD 工具（第二套实现） | **否**（agent 内零 import） |
| `agent/tools/qqapi.py` | 82 | QQ HTTP API 封装 | 否（仅被 `tool_provider/tools/qq.py:4` import） |
| `agent/tools/1.py` | 269 | B 站搜索页 `window.__pinia` 解析实验脚本 | 否（有 `__main__`，会联网并写 `1.txt`） |
| `agent/test_*.py`（5 个） | 1822 | 契约测试（事件路由/节点/工具/仓库） | 否 |
| `agent/downloaded/` | 226 个文件 | `.m4s`/`.mp3` 音视频产物（含一批 `.m4s` 与对应 mp3） | 否 |

依赖仅 5 项且未锁版本：`pymongo / requests / redis / ffmpeg-python / pydub`（`agent/requirements.txt:1-5`）；基镜像 `python:3.11-slim-bookworm`（`agent/Dockerfile:1`）。

## 1.2 进程入口与主循环

| 维度 | 事实 | 位置 |
| --- | --- | --- |
| 启动方式 | 容器 `command: ["python","task_worker.py"]`，容器名 `agent_aagent`，`restart: unless-stopped` | `docker-compose.yml:2-6` |
| 启动参数 | `main()` 无参数、无 argparse；仅 `if __name__ == "__main__"` | `task_worker.py:96-126` |
| 消费方式 | `BRPOP main_agent_queue timeout=5`（阻塞 5s，超时返回 `None` 后 `continue`） | `queue_client.py:63-69`、`task_worker.py:104-106` |
| 生产方式 | 一律 `LPUSH`（同一队列），与 `BRPOP` 组成 FIFO | `queue_client.py:31-39` |
| 并发模型 | 单进程单线程串行：一次只处理一个事件，无线程池/无 prefetch/无并行 | `task_worker.py:98-118` |
| 心跳/状态 | 每轮循环先写 `state=idle`；取到任务写 `state=processing` + `event` 原文 + `started_at`；`finally` 再写 `idle` | `task_worker.py:100-118` |
| 状态键 | `AGENT_WORKER_STATUS_KEY`，默认 `aagent:worker:status`，值为 JSON 字符串，**无 TTL** | `queue_client.py:12-15`、`:41-47` |
| 错误处理 | 最外层 `except Exception`：`print("agent处理失败:", e)` + `traceback.print_exc()` + `time.sleep(2)`，**不重试、不发事件** | `task_worker.py:119-122` |
| 优雅退出 | **无**：无信号处理、无 drain、无 in-flight 记录；进程被杀时已 `BRPOP` 出队的事件永久丢失 | 全文无 `signal`/`atexit` |
| 重试 | 无任何队列级重试/死信；唯一"重试"是 Mongo 读绑定失败时抛 `RuntimeError` 后由主循环 sleep 2s 重来（事件已丢） | `task_worker.py:39-40`、`:119-122` |
| 退出条件 | 无（`while True`） | `task_worker.py:98` |

环境变量（agent 实际读取）：

| 变量 | 默认 | 位置 |
| --- | --- | --- |
| `MONGO_HOST` / `MONGO_PORT` / `MONGO_USER` / `MONGO_PASS` / `MONGO_DATABASE` | `mongodb` / `27017` / 空 / `""` / `agent` | `task_worker.py:22-35` 等 5 处同构 |
| `MONGO_HISTORY_COLLECTION` | `event_history` | `history_repository.py:11-14` |
| `MONGO_EVENT_BINDING_COLLECTION` | `event_bindings` | `task_worker.py:36`（`.env.example` 未列） |
| `MONGO_WORKFLOW_COLLECTION` | `workflows` | `workflow_parser.py:138` |
| `MONGO_MODEL_COLLECTION` | `models` | `llm.py:32` |
| `MONGO_SESSION_COLLECTION` | `sessions` | `workflow_session_repository.py:120` |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_SOCKET_TIMEOUT` | `redis` / `6379` / `30` | `queue_client.py:7-9` |
| `MAIN_AGENT_QUEUE_NAME` | `main_agent_queue` | `queue_client.py:11` |
| `AGENT_WORKER_STATUS_KEY` / `AGENT_TOOLS_KEY` | `aagent:worker:status` / `aagent:tools` | `queue_client.py:12-19` |
| `TOOL_SERVER_URL` | `http://tool_server:8083` | `tool_server_client.py:26` |
| `TOOL_CLIENT_DEFAULT_WAIT_MS` / `TOOL_CLIENT_DEFAULT_ASYNC_TIMEOUT_MS` | `10000` / `600000` | `workflow_nodes.py:412`、`:437` |
| `TOOL_CLIENT_MAX_WAIT_MS` / `TOOL_CLIENT_MAX_ASYNC_TIMEOUT_MS` | `10000` / `3600000` | `workflow_validator.py:364-370` |
| `WORKFLOW_CONTEXT_TTL_SECONDS` / `WORKFLOW_CONTEXT_MAX_VALUE_BYTES` | `86400` / `1048576` | `workflow_context_repository.py:70-75` |
| `WORKFLOW_SESSION_MAX_VALUE_BYTES` | `1048576` | `workflow_session_repository.py:75-76` |
| `DEEPSEEK_*` / `KIMI_*` / `ZAI_API_KEY` / `TAVILY_API_KEYS` / `BOCHA_*` | 无默认，`os.environ[...]` 强读 | `tools/tool.py:10-27` |

**未被 agent 读取但存在于 `.env.example` 的 Redis 项**：`REDIS_PASSWORD`、`REDIS_DB`（`queue_client.py:22-28` 只传 host/port/decode_responses/socket_timeout）。`.env.example` 亦缺 `MONGO_EVENT_BINDING_COLLECTION`、`TOOL_CLIENT_DEFAULT_ASYNC_TIMEOUT_MS`、`WORKFLOW_CONTEXT_*`、`WORKFLOW_SESSION_*`（`.env.example` 全文 56 行）。

## 1.3 Event 协议与分发

`handle_task(e)` 是**唯一**事件入口，没有 dict 注册表，只有两个分支（`task_worker.py:43-93`）：

| 事件类型 | 判定 | 副作用（按执行顺序） | 位置 |
| --- | --- | --- | --- |
| 任意 | 无条件 | `record_history(e)`：整条事件 + `created_at` 落 `event_history` | `task_worker.py:44`、`history_repository.py:50-55` |
| `workflow`（等于） | `if event_type != "workflow"` 取反分支 | 见下"Workflow 启动链" | `task_worker.py:46`、`:55-93` |
| 其它任意类型 | 兜底分支 | `read_bound_workflow_id(event_type)` 查 `event_bindings{event_type, enabled:true}`；命中则 `LPUSH` 一条 `{event_type:"workflow", payload:{**e["payload"], workflow_id}}`，否则**静默丢弃** | `task_worker.py:46-53`、`:21-41` |

关键事实：

* **没有事件类型白名单**：未绑定的事件（含拼写错误、`raw`、未知类型）只写历史，不报错、不告警、无返回值。
* **payload 是唯一数据通道**：`payload` 键名必须与目标 workflow 的 `input_ports[].name` 一致才会被注入（`task_worker.py:83-87`）；缺少 `payload` 键本身则在绑定命中时抛 `KeyError`（`task_worker.py:51`）。
* **`workflow` 事件必须带 `payload.workflow_id`**，缺失即 `KeyError` → 冒泡到主循环 → 静默失败（`task_worker.py:55`）。
* **自产事件回流**：`response`/`error`/`workflow` 都被 `LPUSH` 回同一队列（`task_worker.py:49-52`、`:61-64`、`:90-93`），会在后续循环中再次被 `handle_task` 记录历史。若 `event_bindings` 里为 `response` 或 `error` 建了绑定，就会形成"workflow→response→workflow"的**无界事件回环**；测试明确固化了这一可实现性（`test_task_worker.py:63-73`）。
* 已知生产者（跨模块，仅作协议上下文）：`qqbot/listener.py:25,34`（`qq`）、`webui_py/events.py:388`（`terminal`）、`agent/tools/tool.py:130`（`response`，工具 `output_to_terminal` 直接往队列推）。
* 绑定文档结构（保存侧）：`{event_type, workflow_id(ObjectId), workflow_name, enabled}`，`event_type` 有唯一索引（`webui_py/event_bindings.py:17-23`、`webui_py/main.py:80`）；agent 侧只读 `event_type/enabled/workflow_id` 三个字段，完全不校验 `workflow_name`（`task_worker.py:36-38`）。

### Workflow 启动链（`event_type == "workflow"`）

| 步 | 动作 | 失败表现 | 位置 |
| --- | --- | --- | --- |
| 1 | `_read_workflow(workflow_id, by_id=True)`，`ObjectId` 非法 → `WorkflowParseError("workflow id invalid")`；查询无果 → `"workflow not found:"` | 仅 `not found` 前缀被识别为"已删除"，回推 `{event_type:"error", payload:{workflow_id, message:"workflow not found"}}`；**其它异常继续上抛** | `task_worker.py:56-65`、`workflow_parser.py:140-152` |
| 2 | `validate_workflow(workflow_document)` | `WorkflowValidationError`/`KeyError`/`TypeError` 全部上抛 → 静默失败 | `task_worker.py:66` |
| 3 | `parse_workflow(...)` 编译为索引链表 | 上抛 | `task_worker.py:67` |
| 4 | 给每个节点写 `_workflow_call_stack = [workflow_document['name']]` | 文档无 `name` 字段 → `KeyError`（校验器不校验 `name`） | `task_worker.py:68-69` |
| 5 | 取第一个 `type=="input"` 节点为起点；无 → `ValueError("workflow has no input node")` | 上抛 | `task_worker.py:71-80` |
| 6 | 对 input 节点每个 `workflowPorts` 用 `payload[port['name']]` 注入下游槽位 | 缺值即注入 `None`，下游视作"未连接" | `task_worker.py:82-87` |
| 7 | `run_workflow_map(map, start)` | 上抛 | `task_worker.py:89` |
| 8 | 结果回推 `{event_type:"response", payload:{content: output.get("content", output)}}` | 无 output 内容时 `content` 直接是端口名→值的 dict（**非字符串**） | `task_worker.py:90-93` |

## 1.4 Workflow 执行引擎

### 图解析（`workflow_parser.py`）

* 输入是 MongoDB `workflows` 文档，必须有 `nodes`、`connections`、`input_ports`、`output_ports`（`workflow_parser.py:33-41`）。
* `filter_connections(...)` 先丢掉全部不满足连接契约的边（**静默过滤，无日志**，`workflow_contract.py:357-368`）。
* 输出为等长 `list[dict]`，索引即节点位置；每个节点携带：
  * `predecessors: {key: [index,...]}`、`successors: {key: index}`（`workflow_parser.py:55-65`）；
  * `data_inputs: {port_id: [源节点索引, 源端口, 值槽]}`（三元可变槽）；
  * `data_outputs: {port_id: [[目标节点索引, 目标端口], ...]}`（可多目标）；
  * `x`/`y` 被 `pop`（`workflow_parser.py:46-47`）。
* 控制流键的推导（`workflow_parser.py:97-113`）：

| 源节点/端口 | successor 键 | 目标节点/端口 | predecessor 键 |
| --- | --- | --- | --- |
| 一般节点 `control-out` | `next` | 一般节点 `control-in` | `last` |
| `router` 的分支端口 | `branch-{branch.name}`（按 **name** 而非 id） | — | — |
| `foreach` 的 `loop-out` | `item` | `foreach` 的 `loop-in` | `continue` |

### 调度主循环（`workflow_nodes.py:56-88`）

```text
current = start
while current != -1:
    node = map[current]; handler = nodes_map[node.type]   # 未知类型 → ValueError
    current = handler(current, map)                        # 由 handler 决定下一步
    if node.pop("_workflow_result") is dict: result = 它    # 仅 output 节点写入
return result or {}
```

| 维度 | 事实 | 位置 |
| --- | --- | --- |
| 控制流决定方式 | 每个 handler 返回下一个节点索引；`next_successor(node, key)` 未连接即 `ValueError("workflow successor is not connected: node X, key K")` | `workflow_nodes.py:47-53` |
| 终止 | `WORKFLOW_END = -1`，只有 `workflow_output` 返回它 | `workflow_nodes.py:16`、`:102` |
| 迭代上限 | **无**。无步数计数、无墙钟超时、无环检测 → 任意控制流环 = 永久挂死（单线程 worker 停止消费） | `workflow_nodes.py:70-79` |
| 深度 | 单层 `while`，无递归调度；子 workflow 通过嵌套调用 `run_workflow_map` 递归 | `workflow_nodes.py:569` |
| Context 生命周期 | 每次 `run_workflow_map` 生成 `invocation_id = uuid4().hex`，写入每个节点的 `_workflow_invocation_id` / `_workflow_context_ids`；`finally` 中 `delete_contexts(context_ids)`，并 `pop` 掉两个内部键 | `workflow_nodes.py:60-88` |
| 清理失败 | 只 `logger.exception(...)`，不覆盖原有返回值或异常（测试固化） | `workflow_nodes.py:80-84`、`test_workflow_node.py:890-918` |
| 子 workflow 作用域 | 子调用是独立 `run_workflow_map` → 独立 `invocation_id` 与独立 context 集合；测试断言父/子 invocation 不同、清理顺序 `[{子}, {父}]` | `test_workflow_node.py:920-1000` |
| 递归防护 | 仅按 **workflow 名**白名单：`_workflow_call_stack` 命中即 `ValueError("recursive workflow call detected: A -> B -> A")` | `workflow_nodes.py:530-535` |

### 失败处理矩阵

| 失败点 | 传播路径 | 用户可见结果 | 位置 |
| --- | --- | --- | --- |
| 节点处理器 `ValueError`（输入缺失/类型不符/键未映射/未知节点类型/后继未连接） | handler → `run_workflow_map` → `handle_task` → `main` 兜底 | **无任何事件**；仅容器 stdout `agent处理失败:` + traceback | `workflow_nodes.py:109` 等、`task_worker.py:119-122` |
| 工具超时（远程 sync） | `ToolServerError` → 转 `ValueError(json{node_id,tool,execution,message[,task_id]})` + `logger.error` | 同上（错误详情只进 stderr 日志与异常消息） | `workflow_nodes.py:399-407` |
| LLM 失败 | `requests` 异常/非 200（`raise_for_status`）/模型缺失 → 上抛 | 同上；402 特判返回字符串 `"[-]余额不足"` | `llm.py:55-57`、`:75-76` |
| Mongo/Redis 故障 | `WorkflowContextError`/`WorkflowSessionError`/`PyMongoError` → 上抛 | 同上 | `workflow_context_repository.py:103` 等 |
| 未知本地工具 | **不抛错**：`execute_tool` 返回 `"未知工具: {tool}"` 并被当作正常 content 下传 | workflow 继续跑，结果里出现中文提示字符串 | `tools/tool.py:169-171` |
| 事件落库时机 | 只有 `handle_task` 入队时写历史；引擎自身产生的 `response`/`error` 不直接落库，而是回队列后被**同一 worker 下一轮**记录 | 历史条数 = 被消费次数 | `task_worker.py:44`、`:90-93` |

## 1.5 全部节点类型

`nodes_map` 共 24 个键，与 `SUPPORTED_NODE_TYPES`、`NODE_ARGUMENT_FIELDS_BY_TYPE`（缺 1 项，见缺陷 D1）共同构成契约。

### 端口总表（权威来源：`workflow_contract.py:144-228`）

| 节点类型 | handler（`workflow_nodes.py`） | 数据输入端口 | 数据输出端口 | 控制输入 | 控制输出 | 运行期语义 / 失败模式 |
| --- | --- | --- | --- | --- | --- | --- |
| `input` | `workflow_input:90` | 无（由 payload 注入） | `workflow:<name>`×N（来自 `input_ports`，`boundary_ports` 强制 `id=workflow:<name>`） | 无 | `control-out` | 仅 `next_successor`；`workflowPorts` 被 parser 覆盖为 boundary 集合 |
| `output` | `workflow_output:94` | `workflow:<name>`×N | 无 | `control-in` | 无 | 收集所有"有值"端口为 dict 写入 `_workflow_result`，返回 `-1`；无值端口不进结果 |
| `router` | `workflow_router:354` | `content-in`（强制） | 无 | `control-in` | `branches[].id`（每个必须连） | 读 `content-in` 值 `k`，跳 `branch-{k}`——**必须精确等于某个 branch 的 `name`**；否则 `successor is not connected` 抛错。无 default/兜底分支（`workflow_validator.py:195-223` 不要求兜底） |
| `construct_message` | `workflow_construct_message:146` | `content-in` + `role-in`（仅 `role_source=="port"` 时） | `message-out` | `control-in` | `control-out` | 组 `{role, content}`；`role_source` 缺省 `"fixed"`；端口 role 缺失或 role 非 4 种标准角色 → 抛错 |
| `construct_content` | `workflow_construct_content:163` | `dataInputPorts`（须与 `append_items` 中 port 项完全一致，`workflow_validator.py:509-539`） | `content-out` | `control-in` | `control-out` | 按 `append_items` 顺序拼接，`fixed` 用字面值、`port` 取槽位值（非 str 走 `str()`）；缺值端口直接跳过（**静默丢段**） |
| `construct_map_content` | `workflow_construct_map_content:177` | 无 | `map-out` | `control-in` | `control-out` | 由 `mappings[{key,value}]` 组 dict，键值均强制 str 且键唯一（`workflow_validator.py:240-255`） |
| `map_content_get` | `workflow_map_content_get:184` | `map-in`（map-content）、`key-in`（content） | `content-out` | `control-in` | `control-out` | 校验 map 形状与 key 命中，未命中 → `key is not mapped` 抛错；**该类型在执行期必崩**（缺陷 D1） |
| `split_event` | `workflow_split_event:205` | `event-in` | `type-out`（content）、`payload-out`（content） | `control-in` | `control-out` | `payload` 用 `json.dumps(separators=(",",":"))` 压缩；str 原样返回（`_json_content:220-223`） |
| `deserialize_json` | `workflow_deserialize_json:262` | `content-in` | `outputs[].key` 动态端口 | `control-in` | `control-out` | 根必须是 object；逐 key 按声明类型转换（`content/list-content/message/event/list-message/list-event/map-content`）；任一 key 缺失或类型不符 → **整体抛错且不传播任何已转换值**（测试固化 `test_workflow_node.py:1160-1180`） |
| `construct_list` | `workflow_construct_list:293` | `{item_type}-in-{0..n-1}`（与 `initial_value_count` 一致） | `list-out` | `control-in` | `control-out` | 按索引顺序读槽位，只收"有值"的；`initial_value_count` 0..20 |
| `list_append` | `workflow_list_append:307` | `list-in`、`item-in` | `list-out` | `control-in` | `control-out` | 返回新列表（不改输入）；`position` 缺省非 `"start"` 即追加尾部 |
| `foreach` | `workflow_foreach:322` | `list-in` | `item-out` | `control-in`、`loop-in` | `control-out`（`next`）、`loop-out`（`item`） | 首轮 `list(input)` 存入节点私有键 `_foreach_items`；每次 `pop(0)` 发 `item-out` 并走 `item`；列表耗尽后清键走 `next`。迭代状态挂在**图节点 dict 上**，非并发安全 |
| `history` | `workflow_history:342` | 无 | `events`（仅允许 `list-event`） | `control-in` | `control-out` | 调 `get_recent_history(limit, event_types)`；`event_types` 只允许 `terminal`/`response`，`limit` 1..1000；返回文档含 `created_at`、不含 `_id` |
| `llm` | `workflow_llm:105` | `messages-in`（仅 `list-message`，`workflow_validator.py:704-707` 强制；运行时二次校验角色与 content 为 str） | `output`；`reasoning`（`think=true` 时）；`tool_calls`（`tool_calls=true` 时，元素为 JSON 字符串 → `list-content`） | `control-in` | `control-out` | 见 §1.7；`tools` 由 `registered_tools` 按名称交集过滤 |
| `local_tool` | `workflow_local_tool:377` | `parameters`（字符串名列表，`content` 类型） | `output`（content） | `control-in` | `control-out` | `execute_tool(node_id, tool, args)`；dict/list 结果 `json.dumps`，`None` → `"执行失败，未获取到数据"`；**未知工具不报错** |
| `remote_sync_tool` | `workflow_remote_sync_tool:410` | `parameters[{name,type}]` | `outputs[{name,type}]` | `control-in` | `control-out` | `mode="wait"`；单 `result` 输出直传；多输出要求返回 dict 且字段齐备，缺字段抛错；`map-content` 输出会二次校验形状 |
| `remote_async_tool` | `workflow_remote_async_tool:432` | `parameters[{name,type}]` | `task_id`（content） | `control-in` | `control-out` | `mode="async"`，返回服务端 `task_id`；可选 `callback{type:"redis",queue,event_type,on[]}` 原样透传 |
| `context_create` | `workflow_context_create:452` | `initial-value` | `context-id`（content） | `control-in` | `control-out` | 生成 `ctx_<uuid4hex>`，写 Redis Hash + TTL，把 id 记入本次调用的清理集合 |
| `context_read` | `workflow_context_read:465` | `context-id` | `value-out`（`arguments.value_type` 声明类型） | `control-in` | `control-out` | 校验 invocation 归属与 `value_type`，命中即刷新 TTL |
| `context_write` | `workflow_context_write:477` | `context-id`、`value-in` | `context-id`、`value-out` | `control-in` | `control-out` | 同 read 的归属/类型校验后覆盖 `value` 与 `updated_at` |
| `session_create` | `workflow_session_create:494` | `initial-value` | `session-id`（content） | `control-in` | `control-out` | 写 MongoDB `sessions`，`_id = ses_<uuid4hex>`，**无 TTL、不参与清理** |
| `session_read` | `workflow_session_read:504` | `session-id` | `value-out` | `control-in` | `control-out` | 按 `_id + value_type` 查询；ID 需匹配 `^ses_[0-9a-f]{32}$` |
| `session_write` | `workflow_session_write:514` | `session-id`、`value-in` | `session-id`、`value-out` | `control-in` | `control-out` | CAS 循环：`find_one(updated_at)` → `update_one` 带旧 `updated_at` 条件 → `matched_count==0` 重试（无次数上限） |
| `workflow` | `workflow_workflow:526` | `workflow:<name>`×N（来自节点 `input_ports`） | `workflow:<name>`×N（来自节点 `output_ports`） | `control-in` | `control-out` | 见下 |

### 子 Workflow 调用（`workflow_nodes.py:526-574`）

1. `workflow_name` 必须在 `_workflow_call_stack` 中不存在，否则报递归（`:533-535`）。
2. `_read_workflow(name)`（**按 name 查询**，非 id）→ `validate_workflow` → 再逐字比对父节点保存的 `input_ports`/`output_ports` 与子文档是否完全相等，不等即 `callable workflow contract changed; refresh the workflow node metadata`（`:537-548`）。
3. `parse_workflow` → 找子图 `input` 节点（无则抛错）→ 给子图所有节点写 `next_call_stack`（`:550-560`）。
4. 逐端口把父节点 `workflow:<name>` 槽位值注入子 input（只注入"有值"的，`:561-567`）。
5. `run_workflow_map(child_map, child_input_id)` 递归执行；结果逐端口回填父节点 `workflow:<name>` 输出槽（`:569-573`）。
6. 子调用失败 = 父调用失败，无 try/except、无降级。

### 数据传播细节

* 写槽：`target_slot[2] = value.copy() if isinstance(value, dict) else value` —— **只有 dict 做浅拷贝**，list/对象按引用传递；`list_append` 等节点自建新列表来避免别名问题（`workflow_nodes.py:34-44`，测试 `test_workflow_node.py:769-801`）。
* 读槽：`read_workflow_input` 以 `slot[2] is not None` 作为"有值"判据 → **显式写入 `None` 等价于未连接**（`workflow_nodes.py:27-31`）。
* 目标槽位不是三元 list 时抛 `workflow target input is not connected`（`workflow_nodes.py:39-43`）。

## 1.6 契约（`workflow_contract.py`）

| 注册项 | 内容 | 位置 |
| --- | --- | --- |
| `DATA_CONNECTION_TYPES` | `content, message, event, list-content, list-message, list-event, map-content`（7 种，既是数据边类型也是"值类型"枚举） | `:8-16` |
| `SUPPORTED_NODE_TYPES` | 24 种（§1.5 表） | `:17-42` |
| `NODE_BASE_FIELDS` | `id, type, name, x, y, arguments` | `:44` |
| `NODE_SHARED_FIELDS` | `workflowPorts, dataInputPorts, input_ports, output_ports`（必须顶层） | `:45-50` |
| `NODE_ARGUMENT_FIELDS_BY_TYPE` | 每类节点允许的 `arguments` 键集合（**缺 `map_content_get`**） | `:51-75` |
| `NODE_ARGUMENT_FIELDS` | 上述并集，用于识别"参数被平铺到节点顶层" | `:76` |
| `normalize_node_arguments` | 只保留 base+shared 字段（`arguments` 字典整体保留） | `:123-128` |
| `boundary_ports` | 把 `{name,type}` 映射成 `{id:"workflow:<name>", name, type}` | `:131-141` |
| `data_ports_for_node` | 每种节点的数据入/出端口集合（动态项：`llm` 三输出、`construct_list` 的 `{item_type}-in-i`、tool 参数/输出、`workflow` 的 `workflow:*`） | `:144-213` |
| `control_ports_for_node` | `input` 只有 `control-out`；`output` 只有 `control-in`；`router` 输出=分支 id；`foreach` 有 `control-in/loop-in` 与 `control-out/loop-out`；其余默认 `control-in/control-out` | `:216-228` |
| `is_valid_connection` | 单边合法性判定（端口存在 + 逐类型语义 + 工具参数/输出类型 + 边界/子 workflow 端口类型 + context/session 的 `value_type`） | `:231-354` |
| `filter_connections` | 用上者过滤，**丢弃而非报错** | `:357-368` |

注意：`data_ports_for_node` 对 `input`/`output` 用 boundary 端口；对 `llm`/`deserialize_json`/`context_*`/`session_*` **忽略用户声明的 `dataInputPorts`**（硬编码返回），因此多余声明端口上的连线会在过滤阶段被静默删除。

## 1.7 校验（`workflow_validator.py`）与保存期/执行期差异

`validate_workflow(workflow)` 的不变量（`workflow_validator.py:28-151`）：

| # | 不变量 | 位置 |
| --- | --- | --- |
| 1 | `nodes`/`connections` 必须是 list | `:29-34` |
| 2 | `input_ports`/`output_ports`/`remote_tools` 必须是 list，端口名去空格小写后唯一、类型在 7 种枚举内 | `:35-37`、`:401-457` |
| 3 | 每个节点：id 非空 str、type 受支持、`arguments` 为 dict、可配置字段不得平铺在顶层、shared 字段不得塞进 `arguments`、`arguments` 无未知键、节点无未知顶层字段、`dataInputPorts` 为非空字符串且不重复 | `:154-190`、`:460-471` |
| 4 | `input`/`output` 必须有 `workflowPorts` 且与文档 boundary 元数据**逐字相等**（含顺序），id 必须 `workflow:<name>` 且与 name 一致 | `:59-66`、`:474-506` |
| 5 | 恰好 1 个 `input` 节点；至少 1 个 `output` 节点 | `:72-78` |
| 6 | 节点 id 唯一 | `:67-70` |
| 7 | 控制输出**单后继**、数据输入**单来源** | `:112-134` |
| 8 | 每类节点的 `control_ports_for_node` 端口必须全部连上（`foreach` 因此强制 `loop-in`/`loop-out` 成环） | `:140-151` |
| 9 | 逐类型参数形状：`router.branches` 非空且 id/name 各自唯一；`construct_message.role_source/role`；`construct_content.append_items` 与 `dataInputPorts` 集合一致；`construct_map_content.mappings` 键唯一；`deserialize_json.outputs` 非空/键唯一/类型合法/不得叫 `control-out`；`construct_list` 的 `item_type` 与 `initial_value_count(0..20)` 与 `dataInputPorts` 一致；`list_append`/`foreach` 的 `item_type∈{content,message,event}` 与 `position∈{start,end}`；context/session 的 `value_type` 合法；`history` 的 `event_types` 与 `limit`；`local_tool`/远程工具的 tool 名与参数表 | `:195-325` |
| 10 | 远程工具必须先在 `workflow.remote_tools` 声明，且 `parameters`/`outputs` 与声明**完全相等**；`timeout_ms` 为正整数且不超过 `TOOL_CLIENT_MAX_(ASYNC_)…`；`callback` 严格 4 字段（`type=redis`、queue≤256、event_type≤128、`on` 非空无重复且∈`{working,completed,failed}`） | `:42-58`、`:326-392`、`:411-440` |
| 11 | `workflow` 节点的 `workflow_name` 非空 + `input_ports`/`output_ports` 端口形状合法 | `:393-398` |

**保存在哪一侧校验**：agent 只在**执行期**校验（`task_worker.py:66`、子 workflow `workflow_nodes.py:538`、离线 `debug_workflow.py:45`）；保存侧由 `webui_py`/`manager_webui`/`workflow_editor` 各写一套规则，agent 不复用（全仓 grep 确认 `validate_workflow` 仅被 agent 自身与测试引用）。因此"画布能保存"不等于"执行期能过"。

**两套实现的分叉（同文件内部）**：

* `validate_workflow` 先 `filter_connections` 再遍历，因此 §7 的"未知节点/端口"分支只对**已通过** `is_valid_connection` 的边走；所有不合法的边在 `filter_connections` 阶段被静默丢弃（测试明确断言丢弃语义：`test_workflow_node.py:543-582`）。
* `_validate_control_connection`（`:576-593`）与 `_validate_data_connection`（`:595-711`）与 `is_valid_connection` 高度重复；唯一**只在 validator 中存在**的规则是 `target_type == "llm" → connection_type 必须为 list-message`（`:704-707`），`is_valid_connection` 里没有对应判据，因此单独用 `parse_workflow`（如 `debug_workflow.py --no-validate`）时该非法边会被接受。
* 校验器**不校验**：文档 `name` 字段存在性、控制流环存在性、`router` 是否存在兜底分支、`workflowPorts` 与节点 `arguments` 之外的一致性。

## 1.8 LLM 接入（`llm.py`）

| 维度 | 事实 | 位置 |
| --- | --- | --- |
| Provider 抽象 | **无 provider 枚举**。模型配置以文档形式存 MongoDB `models`，按 `_id`（ObjectId 字符串）查询且要求 `enabled: true` | `llm.py:11-36` |
| 配置字段（消费方） | `model`、`base_url`、`api_key`（可选，`config.get("api_key","")`） | `llm.py:67-73` |
| 协议 | 单一 OpenAI 兼容 `POST {base_url}/chat/completions`，Bearer 鉴权 | `llm.py:46-54` |
| 请求体 | `{model, messages, tools, **extra}`；`extra` 默认 `{}`（可变默认参数，未被调用方使用） | `llm.py:40-45` |
| 流式 | **不支持**：一次性 JSON 响应，无 `stream` 参数 | `llm.py:59` |
| 重试 | **无** | 全文 |
| 超时 | `timeout=(5, 90)` 秒（连接, 读取），硬编码 | `llm.py:53` |
| 特殊返回 | HTTP 402 → 返回 `(402, None, None)`，由 `chat_with_model` 转成 `("[-]余额不足","",[])`（用 `content == 402` 比较，字面量 402 的模型输出不会被误判为 int） | `llm.py:55-56`、`:75-77` |
| 日志副作用 | `print(resp.json())` 打印**完整响应体**（含推理与 tool_calls），生产环境会污染 stdout | `llm.py:58` |
| 消息组装 | 只来自 `messages-in` 端口；运行时校验每条 `{role∈4, content:str}` | `workflow_nodes.py:105-119` |
| 工具挂载 | `registered_tools`（本地注册表快照）按 `node.arguments.tools` 名称交集过滤；**空列表也会照发** `"tools": []` | `workflow_nodes.py:124-132`、`llm.py:43` |
| tool_calls | 仅作为 `list-content`（JSON 字符串数组）输出到端口，**引擎不执行、不回灌**；无 ReAct/多轮工具循环 | `workflow_nodes.py:136-142` |
| `think` 参数 | 只用于 `data_ports_for_node` 决定是否暴露 `reasoning` 端口，**不参与请求体**；`reasoning_content` 仅在端口存在时传播 | `workflow_contract.py:161-167`、`workflow_nodes.py:134-135` |
| history 召回 | **无自动召回**。历史只能经 `history` 节点显式取回，再用 `construct_list`/`list_append`/`construct_message` 拼成 `list-message` 喂给 `messages-in` | `workflow_nodes.py:342-351` |
| 上下文裁剪 | **无**。无 system prompt 注入、无 token 计数、无截断；`tools/documents.py:166` 的 `system_documents_prompt()` 是 agent 内唯一"文档索引进上下文"的实现，但该模块 agent 不 import（死链） | `tools/documents.py:159-173` |

## 1.9 远程工具客户端（`tool_server_client.py`）

| 维度 | 事实 | 位置 |
| --- | --- | --- |
| 端点 | `POST {TOOL_SERVER_URL}/api/tools/{tool}/calls` | `tool_server_client.py:26-34` |
| 请求体 | `{arguments, mode, timeout_ms}`，可选 `callback` | `:27-29` |
| HTTP 超时 | `(3, timeout_ms/1000 + 5)` 秒（读取超时随业务预算放大） | `:34` |
| `mode="wait"` | 期望 `200 + {status:"completed"}`，返回 `payload["result"]`；**202 视为失败**（`remote tool did not complete; task continues on server: {task_id}`），不轮询、不等待 | `:45-59` |
| `mode="async"` | `202 + task_id` → 返回 `task_id`（字符串）；非 202/200 一律异常 | `:45-56` |
| task_id 获取 | 仅从响应体 `payload["task_id"]` 取；不落库、不做关联表 | `:43` |
| 重试/轮询 | **均无**。所谓"task_id 轮询"在本实现中不存在 | 全文 |
| 失败路径 | 网络异常 → `ToolServerError("remote tool request failed: …")`；HTTP≠200 → 带状态码与 `detail`；`status != "completed"` → `remote tool failed: {error}` | `:36-59` |
| 回调语义 | 客户端只做透传；`callback` 的消费方是 tool_server（向指定 Redis 队列发 `event_type` 事件）。agent 侧无 task_id 关联逻辑；回调事件回到 `main_agent_queue` 后靠 `event_bindings` 决定是否起新 workflow | `workflow_nodes.py:432-442`、`workflow_validator.py:375-392` |
| 双层错误包装 | `ToolServerError` 在节点层被转成 `ValueError(json{node_id,tool,execution,message,task_id})` 并 `logger.error`，因此错误信息以结构化 JSON 出现在异常里，但**不会产生任何事件** | `workflow_nodes.py:399-407` |
| 默认/上限 | sync 默认 10s、上限 10s（compose 同值）；async 默认 600s、上限 3600s | `workflow_nodes.py:412,437`、`workflow_validator.py:364-370` |

## 1.10 持久化

### MongoDB（库名默认 `agent`）

| 集合（env） | 读者/写者 | 文档结构 | 索引 | 位置 |
| --- | --- | --- | --- | --- |
| `event_history`（`MONGO_HISTORY_COLLECTION`） | agent 读+写 | 事件原文全量 + `created_at`（UTC aware）。`{event_type, payload, ...任意透传字段, created_at}`；tool 回调事件惯例带 `payload.id` | `(event_type ASC, _id DESC)`= `event_type_id`；`(payload.id ASC)` sparse = `tool_call_id_payload` | `history_repository.py:20-55` |
| `workflows`（`MONGO_WORKFLOW_COLLECTION`） | 只读 | 消费字段：`name`、`input_ports`、`output_ports`、`remote_tools`、`nodes[]`（`{id,type,name,arguments,x,y,dataInputPorts,workflowPorts,input_ports,output_ports}`）、`connections[]`（`{fromId,fromPortId,toId,toPortId,type}`）；查询用 `{"_id":ObjectId}` 或 `{"name":...}`，投影去掉 `_id` | agent 不建索引 | `workflow_parser.py:124-153`、`workflow_contract.py:231-236` |
| `models`（`MONGO_MODEL_COLLECTION`） | 只读 | 消费字段：`model`、`base_url`、`api_key`；过滤 `enabled:true` | 无 | `llm.py:30-36` |
| `sessions`（`MONGO_SESSION_COLLECTION`） | 读+写 | `{_id:"ses_<32hex>", value_type, value(原生 BSON), created_at, updated_at}`（毫秒截断） | `(updated_at)` = `session_updated_at` | `workflow_session_repository.py:97-122`、`:139-153` |
| `event_bindings`（`MONGO_EVENT_BINDING_COLLECTION`） | 只读 | 只取 `{event_type, enabled:true}` 的第一条 `workflow_id` | 写侧（webui_py）建 `event_type` 唯一索引 | `task_worker.py:34-41`、`webui_py/main.py:80` |
| `documents`（`MONGO_DOCUMENT_COLLECTION`） | **agent 不读写** | 仅存在于未被 import 的 `tools/documents.py` | 无 | `tools/documents.py:14-33` |

生命周期：`event_history` 无 TTL、无归档；`sessions` 无 TTL（仅 `updated_at` 单调递增，用于 CAS）。

### Redis

| 键 | 类型 | 结构/命令 | TTL | 位置 |
| --- | --- | --- | --- | --- |
| `main_agent_queue`（`MAIN_AGENT_QUEUE_NAME`） | List | `LPUSH` 生产 + `BRPOP timeout=5` 消费（FIFO）；元素为 `json.dumps(event, ensure_ascii=False)` | 无 | `queue_client.py:31-34`、`:63-69` |
| `aagent:worker:status`（`AGENT_WORKER_STATUS_KEY`） | String | `{state:"idle"/"processing", updated_at?, event?, started_at?}` | **无** | `task_worker.py:100-118`、`queue_client.py:41-47` |
| `aagent:tools`（`AGENT_TOOLS_KEY`） | Hash | field=工具名，value=OpenAI function schema JSON；`redis_reset_tools()` 是 `DEL`，`redis_register_tool()` 是 `HSET` | 无 | `queue_client.py:49-61` |
| `workflow-context:<ctx_id>` | Hash | `{version:"1", value_type, value(JSON 字符串), invocation_id, created_at, updated_at}`；`WATCH/MULTI` 事务，读/写都会刷新 TTL | `WORKFLOW_CONTEXT_TTL_SECONDS`（默认 86400s），并在 `run_workflow_map` 结束时由 `delete_contexts` 删除 | `workflow_context_repository.py:78-128`、`:131-193`、`workflow_nodes.py:80-84` |
| `aagent:settings` 等 | — | agent 不读写（属 webui/qqbot 侧） | — | — |

写入方约定：`get_connection()` 每次调用**新建** `redis.Redis`（无连接池复用、无 password/db 参数），业务代码在循环里反复调用（如每次 `publish_to_queue`）——`queue_client.py:22-28`。

## 1.11 可观测性与调试

| 手段 | 用法 | 位置 |
| --- | --- | --- |
| `debug_workflow.py` | `python debug_workflow.py [name] [--by-id] [--no-validate]`；无 name 时交互输入；从 Mongo 拉取 → 可选校验 → 打印缩进 JSON（`default=str` 处理非 JSON 类型）；失败打印 stderr 并返回 1/2 | `debug_workflow.py:13-56` |
| `workflow_parser.py` 的 `__main__` | `python workflow_parser.py <workflow_name>`，按 **name** 取图并逐行打印（无校验、无 argparse，尽管第 5 行 import 了 argparse） | `workflow_parser.py:5`、`:156-160` |
| 日志 | 仅 `logging.getLogger("aagent.workflow")`：`logger.error("remote tool failed: …")`、`logger.exception("failed to clean up Workflow Contexts")`。全仓**无 logging 配置**（无 basicConfig/DictConfig），默认 WARNING 级走 root handler；节点级信息全部靠 `print` | `workflow_nodes.py:17`、`:84`、`:406` |
| stdout 噪声 | `print("Agent worker started...")`、`print("agent处理失败:", e)` + traceback、`llm.py:58` 打印完整响应 JSON、`tools/tool.py:114` Tavily 换 key 提示、`tools/tool.py:166` Bocha 打印 | 各处 |
| 外部观测面 | `aagent:worker:status`（`webui_py/main.py:39` 消费）用于展示 worker 是否 idle/processing 与当前事件 | `queue_client.py:41-47` |
| 无 | 无指标、无 trace、无请求 ID 贯穿、无节点级耗时统计 | — |

## 1.12 测试固化的契约（交叉印证）

| 测试文件 | 被固化的行为（即"改代码时必须同步改测试"的红线） | 代表用例 |
| --- | --- | --- |
| `test_task_worker.py` | 绑定查询只认 `{event_type, enabled:true}` 并投影 `workflow_id`；未绑定事件**只写历史、不回落默认 workflow**；绑定命中时用 `{**payload, workflow_id}` 覆盖 payload 中的不可信 id 且不修改原事件；`response`/`error` 也可被绑定触发 workflow；Mongo 读失败必须抛 `RuntimeError` 而非"视作未绑定"；workflow 事件按 `_id` 查询；input 端口名恰好为 `workflow_id` 时才注入该值（不是隐式注入）；`workflow not found` 只发一条 `error` 事件；`workflow id invalid` 不得被当作"不存在" | `:13-30`、`:45-51`、`:63-73`、`:75-80`、`:89-116`、`:118-133` |
| `test_workflow_node.py` | 控制流键名（`next`/`branch-{name}`/`item`/`continue`/`last`）；`branches` 必须留在 `arguments` 内；子 workflow 端口 `workflow:*` 双向映射与 `input_ports/output_ports` 顶层存放；`deserialize_json` 失败**不得**传播部分输出；`list_append` 不得原地修改入参；Context 在成功/失败两条路径都要清理且清理失败不得覆盖结果；子 workflow 使用**独立** `invocation_id` 与清理顺序；`foreach` 单次调用内跑完整轮循环并清理 `_foreach_items` | `:417-464`、`:511-541`、`:1160-1180`、`:769-801`、`:834-888`、`:920-1000`、`:1002-1043` |
| `test_tool_nodes.py` | `SUPPORTED_NODE_TYPES == set(NODE_ARGUMENT_FIELDS_BY_TYPE) == set(nodes_map)`；已删除的 `tool`/`remote_tool`/`tool_call` 必须被拒；远程 `timeout_ms` 不得超上限且 async 不受 sync 上限约束；`callback.on` 必须拒绝空数组与非字符串元素；客户端的 URL、请求体、`timeout=(3, timeout_ms/1000+5)`、202/200 语义逐字节固化 | `:239-241`、`:229-236`、`:243-253`、`:355-393`、`:158-225` |
| `test_history_repository.py` | `event_types` 过滤不得跨调用泄漏（每次新建 query dict，`history_repository.py:65`） | `:9-23` |
| `test_workflow_context_repository.py` | `invocation_id` 归属校验、`value_type` 不匹配拒绝、读时刷新 TTL、`delete_contexts(set())` 不得触达 Redis | `:46-75`、`:77-94`、`:125-129` |
| `test_workflow_session_repository.py` | 7 种值类型 CRUD、**无 TTL**、文档字段集合恰为 `{_id,value_type,value,created_at,updated_at}`、`updated_at` 单调递增的 CAS 重试、非法值与超限值拒绝 | `:26-39`、`:42-53`、`:56-67` |

## 扩展槽

| # | 扩展点 | 契约/接入方式 | 必须改动的文件/位置 |
| --- | --- | --- | --- |
| 1 | **新增节点类型** | 一个节点 = 一组端口 + 一个 handler。运行时按 `node["type"]` 在 `nodes_map` 取 handler，签名固定 `(current_id: int, workflow_map: list) -> int`（返回下一个索引，`-1` 结束） | ① `workflow_nodes.py:577-602` 加 handler 与表项；② `workflow_contract.py:17-42` `SUPPORTED_NODE_TYPES`；③ 同文件 `:51-75` `NODE_ARGUMENT_FIELDS_BY_TYPE`（漏加即 `KeyError`，见 D1）；④ 同文件 `:144-213` `data_ports_for_node`；⑤ 同文件 `:216-228` `control_ports_for_node`（若控制端口非默认）；⑥ 同文件 `:231-354` `is_valid_connection` 的逐类型分支；⑦ `workflow_validator.py:154-398` `_validate_node` 加 `elif`；⑧ 前端两处副本（`manager_webui`、`workflow_editor/static/workflow/domain/*`）。测试会强制断言 `SUPPORTED_NODE_TYPES == set(NODE_ARGUMENT_FIELDS_BY_TYPE) == set(nodes_map)`（`test_tool_nodes.py:239-241`） |
| 2 | **新增本地工具** | `@tool(description, json_schema, name=...)` 装饰器（`tools/tool.py:36-55`）：同时写入 `registered_tools`（LLM 可见 schema 列表）、`tool_handlers`（`execute_tool` 按名分发）、`aagent:tools` Redis Hash（manager_webui / workflow_editor 的 `/api/tools` 读它）。重名直接 `ValueError` | 只需在**被 agent import 的模块**里写函数 + 装饰器。注意 agent 只 import `tools.tool`（`llm.py:8`、`workflow_nodes.py:122,378`），`tools.documents`/`tools.qqapi` 不在导入链上 → 写在那里不会被注册 |
| 3 | **新增事件源** | 生产者向 `MAIN_AGENT_QUEUE_NAME` `LPUSH` 一条 `{"event_type": "<type>", "payload": {...}}`；要触发 workflow 则在 `event_bindings` 插一条 `{event_type, workflow_id(ObjectId), workflow_name, enabled:true}`（`event_type` 唯一索引）。`payload` 的键必须与目标 workflow 的 `input_ports[].name` 同名才会被注入 | 生产侧代码 + 绑定文档；agent 侧**零改动**。约束：`event_type` 是普通字符串、无白名单（`task_worker.py:46-53`）；不要给 `response`/`error` 建绑定以免自环（D2） |
| 4 | **新增数据类型/值类型** | 五处并行枚举：数据边与值类型共用 `DATA_CONNECTION_TYPES`（`workflow_contract.py:8-16`）、JSON 反序列化分派 `_deserialize_json_value`（`workflow_nodes.py:244-259`）、Context 值校验 `CONTEXT_VALUE_TYPES`+`_valid_value`（`workflow_context_repository.py:16-58`）、Session 值校验 `SESSION_VALUE_TYPES`+`valid_value`（`workflow_session_repository.py:16-72`）、边界端口类型校验（`workflow_validator.py:443-457`） | 上述 5 处 + 工具参数/输出的 `type` 声明（`workflow_validator.py:326-392`） |
| 5 | **远程工具契约** | 端点固定 `POST /api/tools/{tool}/calls`，语义由 `mode` 决定（`wait` 走 200+completed，`async` 走 202+task_id）；workflow 文档必须在顶层 `remote_tools` 里声明 `{name, input_ports, output_ports}`，节点 `arguments.parameters/outputs` 必须与之**逐字相等**；`callback` 必须严格 `{type:"redis", queue, event_type, on[]}` 且 `on ⊆ {working,completed,failed}` | workflow 文档 + tool_server 实现；时间预算由 `TOOL_CLIENT_*`（节点层默认）与 `TOOL_CLIENT_MAX_*`（校验上限）两个命名族控制（`workflow_nodes.py:396-398`、`workflow_validator.py:359-374`） |
| 6 | **新增持久化集合/队列/键** | 全部走环境变量；Mongo 侧模式统一为 `os.getenv("MONGO_*_COLLECTION", <默认>)`，Redis 侧 key 在 `queue_client.py` 顶部常量 | `task_worker.py:36`、`workflow_parser.py:138`、`llm.py:32`、`history_repository.py:11-14`、`workflow_session_repository.py:120`、`queue_client.py:11-19` |
| 7 | **替换/扩展执行器行为** | 唯一注入点是 `nodes_map`（可被 monkeypatch 覆盖单点行为，`test_tool_nodes.py:72-77` 即用 `sys.modules` 替换 `tools.tool`）；`run_workflow_map` 无参数化钩子（无 before/after 节点回调、无中间件） | `workflow_nodes.py:56-88`、`:577-602` |

## 已知缺陷与占位代码

> 全目录 grep `TODO|FIXME|XXX|NotImplemented|raise NotImplementedError|pass  #` **零命中**：本模块没有显式标记的未完成代码，但存在以下等效占位/死代码与实现矛盾。其中 D1、D6 与同仓测试的期望**直接冲突**（按现有代码必然失败），D2/D3 为运行期硬缺陷。

| # | 级别 | 缺陷 | 证据 | 影响 |
| --- | --- | --- | --- | --- |
| D1 | P0 | `NODE_ARGUMENT_FIELDS_BY_TYPE` **漏了 `map_content_get`** | `workflow_contract.py:17-42` 含该类型，`:51-75` 不含；`workflow_validator.py:178` 用 `NODE_ARGUMENT_FIELDS_BY_TYPE[node_type]` 直接取键 | 任何含 `map_content_get` 的 workflow 在执行期抛 `KeyError`（非 `WorkflowValidationError`）→ 被主循环兜底吞掉、静默失败；同时 `test_tool_nodes.py:240`（集合相等断言）与 `test_workflow_node.py:263-303`（该节点验收用例）必然失败。执行层单测直接调用节点函数、绕过校验器，故此前未暴露 |
| D2 | P1 | **运行期失败全静默**：节点抛错、校验失败、工具超时、Mongo 抖动都只 `print` + `sleep(2)`，不产出任何事件、不留节点信息 | `task_worker.py:119-122`；`task_worker.py:55`（缺 `payload.workflow_id`→`KeyError`）、`task_worker.py:69`（文档缺 `name`→`KeyError`）同样落入该兜底 | 用户侧表现为"发了没反应"；事件已 `BRPOP` 出队且无重试/死信 → 消息永久丢失；唯一的 `error` 事件只覆盖"workflow not found"一种情形（`task_worker.py:61-64`） |
| D3 | P1 | **执行器无环检测、无迭代上限、无超时** | `workflow_nodes.py:70-79` 为裸 `while`，无步数/墙钟保护；`workflow_validator.py` 只校验控制端口连通性与单后继，不禁止环 | 画布上任一非 `foreach` 回边即造成无限循环，单线程 worker 停止消费整条队列；每轮可能伴随 LLM/远程工具调用（成本放大）。`foreach` 的 `loop-in/loop-out` 是唯一"正当环"，但无机制区分 |
| D4 | P1 | **工具注册表被 import 副作用清空**：`tools/tool.py:33` 模块级 `redis_reset_tools()` 直接 `DEL aagent:tools` | `tools/tool.py:26-33`；且 `tools/tool.py:10-24` 用 `os.environ[...]` 强读 `DEEPSEEK_*`/`KIMI_*`/`ZAI_API_KEY`/`TAVILY_API_KEYS`/`BOCHA_*` | 任何 import `tools.tool` 的进程（agent、测试、一次性脚本）都会清掉共享工具目录；agent 只注册 5 个工具（余额×2、Tavily、`output_to_terminal`、`get_recent_records`），而 `aagent:tools` 的读者是 manager_webui/`workflow_editor`；`ZAI_API_KEY`/`BOCHA_*` 被读出但**完全未使用**，缺任一 Key 即启动失败 |
| D5 | P1 | **`tools/documents.py`、`tools/qqapi.py` 在 agent 进程内是死代码**：全仓 grep 确认 agent 无任何 import（`documents.py:1-2` 反向 import `utils` 与 `tools.tool`，即依赖方向是"死文件依赖活模块"）；`qqapi.py` 仅被 `tool_provider/tools/qq.py:4` 引用；且 `execute_tool` 对未知工具**返回成功字符串**而非报错 | `tools/documents.py:1`、`tools/qqapi.py`、`tools/tool.py:169-171` | `local_tool` 节点引用文档/QQ 工具时，节点"成功"输出 `"未知工具: xxx"` 并继续流转 → 静默错误结果；同理 `llm` 节点的 `tools` 过滤后可能为空集。另：`tools/documents.py:67-74,76-84` 的 `find_one` 结果**未判空**，文档不存在即 `TypeError`；`system_documents_prompt()`（`:166-173`）与 `list_documents()`（`:159-164`）无调用方（除非先补 import） |
| D6 | P1 | **校验器内部两套规则分叉 + 非预期异常** | `workflow_contract.py:231-354` 缺 `llm` 目标规则，`workflow_validator.py:704-707` 独有该规则；`workflow_validator.py:389` 用 `status not in {…}` 判定 `on[]` 元素，元素为 dict 时抛 `TypeError: unhashable type` 而非 `WorkflowValidationError`（与 `test_tool_nodes.py:375-393` 的期望不符）；`filter_connections` 静默丢弃非法边（`workflow_contract.py:357-368`） | 同一张图"`debug_workflow.py --no-validate` 能解析、正式执行才报错"；手工 JSON 里的非法回调会把 `TypeError` 冒泡到主循环兜底（→ D2 静默）；用户画错的连线无声消失 |
| D7 | P2 | **契约/实现不一致：`think` 参数不参与请求** | `workflow_contract.py:161-167` 用 `think` 决定是否暴露 `reasoning` 端口；`workflow_nodes.py:130-132` 只传 `messages`、`model`、`tools` | `think=true` 不会让模型开启思考，只是把响应里本来就可能存在的 `reasoning_content` 暴露出来（`llm.py:61`）；同理 `tool_calls` 参数只控制端口，不控制是否请求工具 |
| D8 | P2 | **`llm.py` 打印完整响应体 + 恒发 `"tools": []`** | `llm.py:58`、`llm.py:43` | stdout 被模型响应污染（含推理内容与工具调用）；部分 OpenAI 兼容网关对空 `tools` 数组返回 400 |
| D9 | P2 | **`history_repository.get_recent_history` 的 `query` 参数无调用方** | 定义 `history_repository.py:57-61`；唯一调用点 `workflow_nodes.py:346-349` 只传 `limit`/`event_types` | 节点无法按 payload 过滤历史；该分支属预留 API 死参数 |
| D10 | P2 | **CAS 循环无上限** | `workflow_context_repository.py:135-157`（`while True` + `WatchError` 重试）、`workflow_session_repository.py:174-184`（`while True` + `matched_count` 重试） | 高并发/长事务下可无限重试；Redis 客户端超时 30s 只作用于单次命令 |
| D11 | P2 | **无优雅退出** | `task_worker.py:96-126` 无信号处理 | `docker compose restart`/滚动更新会中断在途 workflow：Context 已建的 Redis 键只能靠 TTL 过期（`workflow_context_repository.py:124`），`_workflow_*` 内部键随进程消失；无任务补偿 |
| D12 | P3 | **`publish_to_queue` 每次新建 Redis 连接，且忽略 `REDIS_PASSWORD`/`REDIS_DB`** | `queue_client.py:22-34` | 高频事件下连接建立开销；`.env.example:21-22` 的密码/DB 配置对 agent 无效 |
| D13 | P3 | **`get_connection()` 语义重复**：`workflow_context_repository.py:13` 复用 `queue_client.get_connection`，但 agent 侧无连接池与重连策略 | `queue_client.py:22-28` | 单点故障即整轮事件失败（→ D2） |
| D14 | P3 | **死代码/残留** | `utils.py`（3 行，仅被死文件引用）、`tools/tool.py:150-166` `bocha_search`（无 `@tool`、无 return、无 timeout，仅 `print`）、`tools/1.py`（269 行 B 站解析实验，`__main__` 联网并写 `1.txt`）、`workflow_parser.py:5` `import argparse` 未使用、`tools/tool.py:168` `execute_tool(id, …)` 的 `id` 形参未使用、`llm.py:38` `extra={}` 可变默认参数、`agent/downloaded/` 226 个音视频产物 | 细节同上 | 认知负担与误用风险；`tools/1.py` 若被误执行会向工作目录写文件并发起外网请求 |
| D15 | P3 | **协议健壮性缺口** | `task_worker.py:51`（`e["payload"]` 直接解包）、`:55`（`payload.workflow_id`）、`:69`（`workflow_document["name"]`）、`:92`（`output.get("content", output)` 可能返回非字符串） | 字段缺失/形状异常 → 静默失败或向终端推送 dict 形状的 `content`；`event_type` 无格式约束（webui 侧有 `^[a-z][a-z0-9_.-]*$`，`webui_py/event_bindings.py:13`），agent 侧不校验 |
