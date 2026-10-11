# 07 设计目标态、扩展槽与未来项

> 类型:审计报告（分节草稿）。
> 性质:现行文档。
> 归属:跨服务。
> 适用版本:平台 `4.0.0+`。

> 分节稿（合并前草稿），对应 `00-目录说明.md` 的 07 行。
> 依据：`README.md`、`todo.md`、`docs/审计.md`、`docs/17` – `docs/26`、`docs/审查日志/` 权威清单与三份全项目报告、`docs/废弃旧文档/`（仅用于追溯规划项）。
> 方法：只读文档 + 关键源码交叉核对（`agent/`、`tool_server/`、`manager_webui/`、`webui_py/`、`workflow_editor/`）。
> 本会话沙箱禁用 PowerShell，全部结论来自 `read` / `grep` / `glob` 静态证据。

## 7.1 阅读范围、方法与状态判定口径

| 状态 | 判定口径 |
| --- | --- |
| **已落地** | 源码中存在完整实现路径（处理函数 / API / 页面），且设计与实现无实质冲突 |
| **部分实现** | 主路径已实现，但存在文档自述的缺口、契约不一致、或审查报告已登记且经本轮复核仍成立的问题 |
| **纯目标态** | 只在文档中以"未来 / 后续 / 规划中 / 首期不实现"出现，源码中无对应实现，或仅有占位 |

判定时的两个硬性依据：

1. `README.md:20` 与 `docs/README.md:35` 都声明"设计与实现冲突时以源码为准"，因此凡文档写方案而源码无实现者一律降级为纯目标态；
2. `docs/审查日志/README.md:3` 明确审查日志"不定义当前 Agent 架构"，因此日志中的方案描述同样不构成实现证据，只有其中的**代码级证据链**被采信。

本轮额外核对了 `docs/审查日志/2026-10-11-全项目-审查报告.md` 登记的四项生产缺陷是否已修复，结论见 [已知问题摘要](#已知问题摘要) 与 [文档与实现漂移](#文档与实现漂移)。

## 7.2 设计目标态总览

`README.md:2` 是本项目唯一的目标态总纲：事件驱动架构启发的长程 ReAct 与瞬时任务调度、Workflow 可塑性支持 Agent 自演进、以及"从数学角度探索 MCTS 规划、上下文压缩、马尔可夫链决策与 LLM 的结合"。

| 目标态 | 出处 | 当前状态 | 判定依据 |
| --- | --- | --- | --- |
| 事件驱动 + 长程 ReAct 与瞬时任务调度 | `README.md:2`、`README.md:38` | **部分实现** | 绑定路由与 `workflow` 事件链已落地（`agent/task_worker.py:43-93`）；ReAct 靠"Workflow 发布事件调用自身 + history 召回"表达（`README.md:38`），但仍是单 worker 串行时间线（`README.md:15`），且 QQ 输入队列是 LIFO（`qqbot_consumer/queue_client.py:19,25`，README 亦把它写成"当前值"）。 |
| Workflow 可塑性（节点 / 端口 / 状态显式可见） | `README.md:16`、`README.md:34` | **已落地** | 24 类节点寄存器 `agent/workflow_contract.py:17-42`；动态端口（router branches、deserialize_json outputs、remote tool parameters/outputs）均有契约与校验。 |
| Workflow 支持 Agent 自演进 | `README.md:2`、`todo.md:7-8` | **纯目标态** | 只有 `todo.md` 的"交互方向 / ADAS 方向"与 `docs/论文survey/ADAS.md`（调研笔记），无实现与设计稿。 |
| Event 源可扩展（Webhook / 定时 / 其他平台） | `README.md:10`、`README.md:14`、`README.md:79` | **部分实现** | 机制已通：任意 `event_type` 只要存在启用绑定即生成 `workflow` 事件（`agent/task_worker.py:46-53`）；但除 QQ / Terminal 外无生产者。callback 亦走同一机制，可直接进主队列（见成稿 §8.15）。 |
| 异步回调唤醒 Agent / 长任务续跑 | `README.md:97-98`、`docs/17-Tool Server设计.md:214`、`docs/19:150` | **已可用（差一条绑定）** | Tool Server 侧 callback outbox 已实现（`tool_server/main.py:124-149`），投递队列取自节点 `callback.queue`（`:57,141`）。设为 `main_agent_queue` + 给 `async_result` 建一条启用绑定，主 worker 即经通用绑定路由唤醒 Workflow（`agent/task_worker.py:46-53`），**无需专用消费者**。`README.md:98` / `docs/20:247` 的"不能回主队列"是旧架构残留，见成稿 §8.15。 |
| 分布式 Tool Provider / 工具注册与调用 | `docs/17` 全篇、`docs/19` | **已落地** | Provider WS 注册（`tool_server/main.py:300-326`）、任务状态机、wait/async/202 分支、每任务通知 List（`tool_server/task_store.py:71-75,122,155`）。 |
| 三类 Tool 节点（local / remote_sync / remote_async） | `docs/19` | **已落地** | `agent/workflow_contract.py:32-34,193-199`、`agent/workflow_nodes.py:377-450`、`agent/tool_server_client.py`。 |
| Workflow 内可变 Context | `docs/21` | **已落地** | 三节点 + Redis 仓储 + 每次执行 `invocation_id` 与 `finally` 清理（`agent/workflow_nodes.py:56-87,452-492`、`agent/workflow_context_repository.py`）。 |
| 跨执行持久 Session（含管理页） | `docs/23`、`docs/25` | **已落地** | `agent/workflow_session_repository.py`、`manager_webui/sessions.py`、`manager_webui/static/sessions.html/js/css`；双模式编辑在 `sessions.js:19,131-152,336-348`。 |
| JSON 反序列化为强类型多输出 | `docs/22` | **已落地** | `agent/workflow_nodes.py:244-290`（含 `map-content` 分支）。 |
| `map-content` 一等数据类型 | `docs/26` | **部分实现** | 端口、连接、执行、Context / Session 均支持；但 agent 侧 `NODE_ARGUMENT_FIELDS_BY_TYPE` 缺 `map_content_get` 条目（`agent/workflow_contract.py:51-75`），任何含该节点的工作流在校验期抛 `KeyError`（`agent/workflow_validator.py:178`）。 |
| 全局 Context（跨 Workflow 执行长期共享） | `docs/21-Workflow Context节点设计.md:14,247-257` | **纯目标态** | 文档明确"首期不实现全局 Context"；源码只有 Workflow 内 Context + Session（Session 是它的替代落地形态，但语义不同）。 |
| Context 并发读改写原子性 / CAS | `docs/21:339-358` | **纯目标态** | 文档"首期不提供 append / merge / increment"；`docs/21:446-454` 的"首期不实现"清单未被后续文档撤销。 |
| MCP 兼容（标准 MCP Client 适配层） | `docs/17-Tool Server设计.md:11,266-278` | **纯目标态** | `tool_server/` 全目录无 MCP 相关实现；文档自称"未来可增加独立 MCP Adapter"。 |
| MCTS 规划 | `README.md:2`、`README.md:184` | **纯目标态** | 仅在 README/路线图中以一句 TODO 出现；`docs/废弃旧文档/05-路线图与创新.md:125-131` 标注"保留方向，尚未实现"（该文件已归档，不代表当前行为）。 |
| 上下文压缩 | `README.md:2` | **纯目标态** | 全仓仅 README 一句愿景，无设计文档、无实现。 |
| 马尔可夫链决策 | `README.md:2` | **纯目标态** | 同上，无任何细化文档。 |
| 交叉验证 | `README.md:185` | **纯目标态** | 仅 TODO 一行。 |
| ReAct multi-Agent 编排（上下文=任务状态+todo） | `README.md:41`、`README.md:186` | **纯目标态** | README 用"未来可以把不同角色建模为可复用的 Agent Workflow"表述；且子 Agent 回发链路（`rpc_apply` / `rpc_review`）在当前源码中已**整体删除**（全 `*.py` 检索无匹配），协作链路目前只有 Workflow 调用节点这一种形态。 |
| 事件 / 节点全量落库与可调试 | `README.md:18` | **已落地** | `agent/task_worker.py:44` 先落历史；`docs/20:288-301` 描述 WebUI 三来源合并。 |
| 弹性：服务独立进程 / 容器 | `README.md:15` | **已落地** | `docker-compose.yml` 七服务；`README.md:100-111` 端口表与服务一致。 |

## 7.3 专题文档提炼（17–26）

### 7.3.1 17-Tool Server 设计

| 维度 | 内容 |
| --- | --- |
| 核心命题 | 独立的 `tool_server` 统一管理分布式工具的注册、发现、调用与任务状态（`docs/17:5`）。 |
| 关键设计决定 | Tool Server 是**单实例调度内核**，不靠多实例分发（`docs/17:17,59`）；执行并发由 Provider 的 Consumer 数决定（`docs/17:25`）；三种调用方式共享同一任务记录（`docs/17:26,30`）；callback 可投递到调用方指定的任意 Redis List，但只做受控 JSON 投递（`docs/17:177,263`）。 |
| 实现程度 | **已落地**：Provider WS 注册 / 心跳 / 派发（`tool_server/main.py:300-326`）、`wait` / `async` 与 200/202 分支（`tool_server/main.py:259-280`）、任务状态与终态不可变、`TOOL_CALLBACK_EVENT_TYPES` 白名单（`tool_server/main.py:233-234`）。 |
| 与源码差异 | 无实质差异；`docs/17:280-286` 的建议实施顺序 1–4 已完成，第 5 项（MCP Adapter）无实现。 |
| 开放扩展点 | MCP Adapter 映射表（`docs/17:270-278`）；按工具配置调用权限（`docs/17:259`，属安全目标态）；`revision` 递增的 Schema 版本语义（`docs/17:87`）。 |

### 7.3.2 18-Tool Server 内核实现

| 维度 | 内容 |
| --- | --- |
| 核心命题 | 描述 Provider 连接所有权、执行并发、任务持久化、阻塞唤醒与 callback 可靠投递的实现（`docs/18:5`）。 |
| 关键设计决定 | WS Manager 是连接唯一读写者，Consumer 不接触 WebSocket（`docs/18:37`）；内部任务队列有界，入队即 `accepted`、队满即 `rejected`（`docs/18:41`）；每 Task 一条独立 TTL 通知 List，仅传"状态可能已变化"信号（`docs/18:65-67`）；状态更新与通知写入用事务 / Lua，先状态后通知（`docs/18:102`）；callback 先写 Outbox 再由独立循环投递，至少一次（`docs/18:110`）。 |
| 实现程度 | **已落地**：通知 List key `tool:task:{task_id}:updates`（`tool_server/task_store.py:74-75`）、`BLPOP` 等待循环（`tool_server/task_store.py:155`）、Outbox + `tool:callback:processing` 滞留回收（`tool_server/main.py:124-149`）、大结果外置与 TTL 语义。 |
| 与源码差异 | Outbox 用 `lrem(processing, 1, item)` **按值**删除处理中条目（`tool_server/main.py:142,146`），重复负载会删错一条——`2026-10-11-全项目-审查报告.md:73` 已登记，本轮复核仍成立。 |
| 开放扩展点 | Provider 租约与超时策略（`docs/18:46`）、断线 / 重复消息测试矩阵（`docs/18:132`）、Tool Server 高可用不破坏单调度权的实现方式（`docs/17:59`）。 |

### 7.3.3 19-Workflow 本地与远程 Tool 节点拆分

| 维度 | 内容 |
| --- | --- |
| 核心命题 | 把旧 `tool` 节点拆成 `local_tool` / `remote_sync_tool` / `remote_async_tool`，让执行位置与等待语义在画布上显式（`docs/19:5-11,35-43`）。 |
| 关键设计决定 | 不得用 `mode` 字段切换语义（`docs/19:11`）；本地与远程目录不合并、不自动降级、不跨目录查找（`docs/19:68-76`）；两种远程节点只保存契约快照，路由由 Tool Server 决定（`docs/19:76,236`）；同步收到 `202` 时节点失败并记录 `task_id`，不轮询（`docs/19:310-314`）；旧 `tool` 节点不迁移直接拒绝（`docs/19:366`）。 |
| 实现程度 | **已落地**：三类节点契约与端口（`agent/workflow_contract.py:32-34,193-199`）、运行时（`agent/workflow_nodes.py:377-450`）、契约一致性测试（`agent/test_tool_nodes.py`）。 |
| 与源码差异 | `docs/19:275` 的保存校验写"不允许出现 `mode` 或 `callback` arguments"，与同文档 `docs/19:163-165`（`callback` 为可选字段）及源码（`agent/workflow_contract.py:67` 含 `callback`、`agent/workflow_validator.py:375-392` 校验 callback 结构）**互相矛盾**；以源码为准，`callback` 受支持。 |
| 开放扩展点 | `docs/19:368-375` 的非目标清单全部未实现：`remote_tool_call` 动态名称节点、LLM 远程工具挂载、本地找不到自动转发远程、已发布异步任务的等待/跟踪/取消、工具参数类型系统扩展；`docs/19:63` 明确当前**无 cancel API**。 |

### 7.3.4 20-Event 协议与流转

| 维度 | 内容 |
| --- | --- |
| 核心命题 | 定义当前 Workflow + Tool Server 架构下 Event 的类型、JSON 格式、队列方向与完整运行路径（`docs/20:3-9`）。 |
| 关键设计决定 | 主队列 `LPUSH` + `BRPOP`（FIFO），终端 `RPUSH` 插队（`docs/20:50-52`）；QQ 队列 `LPUSH` + `BLPOP`（LIFO，`docs/20:38-39`）；`workflow` / `response` / `error` 为内部事件（`docs/20:25`）；未绑定事件只落历史（`docs/20:27`）；payload 中不存在的字段以 `None` 传播并被运行时判为"没有值"（`docs/20:176`）。 |
| 实现程度 | **已落地**：`workflow` / `response` / `error` 三条链（`agent/task_worker.py:43-93`）、终端 4000 字符与 `files` 为空约束、入口按端口名取 payload 字段（`agent/task_worker.py:83-87`）。 |
| 与源码差异 | `docs/20:78` 写"`response` / `error` 不参与绑定路由"，但 `agent/task_worker.py:46-53` 对除 `workflow` 外的**所有** `event_type` 都做绑定查询，`agent/test_task_worker.py:66-74` 明确断言 `response` / `error` 有绑定时会触发 Workflow。 |
| 开放扩展点 | 新增事件类型的六项检查表（`docs/20:305-312`）；`async_result` 回调接入（**推荐路线 A：主队列 + 一条绑定**，见成稿 §8.15；`docs/20:247` 的"必须专用消费者"要求已过时）；事件格式统一入口（见 `架构问题汇总` A-08）。 |

### 7.3.5 21-Workflow Context 节点设计

| 维度 | 内容 |
| --- | --- |
| 核心命题 | 给 pipeline 模型补一个带类型的可变状态空间，使 `foreach` 能做累积、跨轮传值与 reduce（`docs/21:5-22`）。 |
| 关键设计决定 | `value_type` 是面板配置而非数据端口（`docs/21:26`）；Context ID 是不透明 `content`，不新增数据类型（`docs/21:28,46`）；每个 Workflow 执行实例独立 `invocation_id`，`finally` 全量清理，TTL 仅兜底（`docs/21:31-33,204-208`）；父子 Workflow 作用域完全隔离（`docs/21:210-218`）；首期只做完整覆盖，不做复合操作（`docs/21:30`）。 |
| 实现程度 | **已落地**：三节点（`agent/workflow_nodes.py:452-492`）、`invocation_id` + `context_ids` + `finally` 清理（`agent/workflow_nodes.py:56-87`）、仓储与大小 / TTL 限制（`agent/workflow_context_repository.py:71-75`）。 |
| 与源码差异 | 无。`docs/21:402-403` 要求"新增 `agent/workflow_context_repository.py`"，该文件已存在。 |
| 开放扩展点 | 全局 Context 及其授权 / 生命周期 / 删除机制（`docs/21:247-257,454`）；`context_delete`、append / merge / increment 原子节点、并行读改写事务、用户自定义 Redis Key、节点级 TTL、永不过期 Context、自动类型转换、Value 历史版本（`docs/21:446-454`）；并发下的版本号 CAS 或 `WATCH/MULTI/EXEC`（`docs/21:349-358`）。 |

### 7.3.6 22-Workflow 反序列化 JSON 节点设计

| 维度 | 内容 |
| --- | --- |
| 核心命题 | 把 `content` 中的一整个 JSON 文本按顶层键拆成多个强类型输出，避免为每种响应结构写专用 Tool（`docs/22:5-13`）。 |
| 关键设计决定 | 只支持顶层键，不做 JSONPath / 下标 / 默认值（`docs/22:14`）；`content` 类型下 `null` 必须转成字符串 `"null"`，否则 `read_workflow_input` 会判为无输入（`docs/22:80`）；转换原子化，任一字段失败则不传播任何输出（`docs/22:151`）；不提供跳过失败字段或默认值（`docs/22:162`）。 |
| 实现程度 | **已落地**：`agent/workflow_nodes.py:262-290` 的读取—解析—根对象校验—逐字段转换—统一传播顺序与文档一致；`agent/workflow_nodes.py:27-31` 仍是 `is not None` 判定，故 `null → "null"` 的约定是必需的。 |
| 与源码差异 | `docs/22:52-61` 的类型清单未包含 `map-content`，而源码已支持（`agent/workflow_nodes.py:257-258`）、`docs/26:71` 亦已把它纳入——属**文档滞后**而非实现缺口。 |
| 开放扩展点 | `docs/22:230-239` 的首期排除项全部未实现：JSONPath / 点号路径 / 数组下标、嵌套字符串递归解析、默认值与可选键、数字与布尔等新的 Workflow 一等类型、JSON Schema 推断、输出配置拖动排序。 |

### 7.3.7 23-Workflow Session 节点与管理页设计

| 维度 | 内容 |
| --- | --- |
| 核心命题 | 提供跨 Workflow、跨执行实例、重启后仍可读的带类型可变值，并在管理页做 CRUD（`docs/23:5-7`）。 |
| 关键设计决定 | 用 MongoDB 独立 `sessions` 集合、不建 TTL 索引，明确不用 Redis Context Key（`docs/23:21`）；ID 由后端生成 `ses_<uuid4 hex>`，ID 本身即访问凭据（`docs/23:12,17`）；`value_type` 创建后固定、只允许覆盖（`docs/23:14`）；覆盖用 `updated_at` 乐观锁，管理页冲突返回 409（`docs/23:32`）；值上限 1 MiB 按已编码字节（`docs/23:30`）。 |
| 实现程度 | **已落地**：仓储（`agent/workflow_session_repository.py:25,54,75-76,102-120,139-169`）、三节点（`agent/workflow_nodes.py:494-514`）、`manager_webui/sessions.py` + `sessions.html/js/css` + `test_sessions.py`。 |
| 与源码差异 | `docs/23:34` 警告"现有 `workflow_context_repository.py` 的 `_valid_value` 并未处理 `event` / `list-event`"，该缺口**已修复**（`agent/workflow_context_repository.py:49-52`）；`docs/23:74` 自称"当前仅完成语法和编辑器静态诊断，运行时测试仍需执行"，实际已有 `agent/test_workflow_session_repository.py`、`manager_webui/test_sessions.py`，且 `2026-10-11` 报告在容器内跑通 90+17 用例。 |
| 开放扩展点 | 按名称查找 Session、追加 / 合并、自动过期、历史版本（`docs/23:7`）；所有者 / 授权规则（`docs/23:70`）；列表查询需 `(updated_at, _id)` 复合索引（`2026-10-11-全项目-审查报告.md:64`，目前只有 `updated_at` 单列索引）。 |

### 7.3.8 24-Event 绑定与 Workflow 路由设计

| 维度 | 内容 |
| --- | --- |
| 核心命题 | 记录已实现的绑定路由行为：每个事件类型至多绑定一个 Workflow，`workflow_id` 由路由写入且不可被原 payload 覆盖（`docs/24:3,7-14,40`）。 |
| 关键设计决定 | 删除 `_id = "agent"` 全局 `workflow_id` 回退，路由只由绑定决定（`docs/24:12`）；绑定查询失败 ≠ 未绑定（`docs/24:11`）；目标不存在时恰好发布一个 `error`、不发布 `response`（`docs/24:44-58`）；`workflow_id` 可作为输入端口被读取，也可不声明（`docs/24:42`）。 |
| 实现程度 | **已落地**，与源码逐条一致：`agent/task_worker.py:21-41`（按 event_type 查启用绑定）、`agent/task_worker.py:49-52`（覆盖 `workflow_id`）、`agent/task_worker.py:58-65`（目标不存在发 `error`）、`agent/test_task_worker.py:13-130`。 |
| 与源码差异 | 唯一显著偏差：`docs/24:14` 写"`workflow`、`response`、`error` 是内部事件，不走上述绑定路由"，与源码（只排除 `workflow`）和既有测试相反。 |
| 开放扩展点 | 该文档自我定位为"已实现行为记录"（`docs/24:3`），未声明后续扩展；绑定与 Workflow 改名 / 删除的一致性仍是开放问题（`2026-10-11-全项目-审查报告.md:60`）。 |

### 7.3.9 25-Session 管理页双模式编辑设计

| 维度 | 内容 |
| --- | --- |
| 核心命题 | 在 `/sessions.html` 值区域提供「可视化 / JSON」双模式，六种 `value_type` 都可可视化编辑（`docs/25:5-7`）。 |
| 关键设计决定 | 两模式保存同一个 `value`，不加存储字段、不加 API（`docs/25:5`）；`content` 不参与模式切换（`docs/25:11`）；event 的 `payload` 可为任意合法 JSON，扩展字段不得覆盖 `event_type` / `payload`（`docs/25:22`）；JSON 模式无效时禁止切回与保存，但允许确认丢弃后离开（`docs/25:30`）；编辑器切换本身不调 API（`docs/25:30`）。 |
| 实现程度 | **已落地**：`manager_webui/static/sessions.js` 的 `mode` 状态机与切换（`sessions.js:19,336-352`）、可视化容器与文本容器的显隐（`sessions.js:148-156`）、列表项增删排序（`sessions.js:167-205,352-379`）、按类型读取草稿（`sessions.js:131-139`）。 |
| 与源码差异 | 无实质差异；`docs/25:37` 要求"不修改 `manager_webui/sessions.py`、Agent 存储或接口协议"，与现状一致。 |
| 开放扩展点 | `docs/25:20` 的"新建 event 默认 `{event_type: "", payload: {}}`，填写类型后才可保存"依赖后端校验；移动端与长 JSON 滚动属验收项而非新能力（`docs/25:45`）。 |

### 7.3.10 26-Workflow `map-content` 数据类型设计

| 维度 | 内容 |
| --- | --- |
| 核心命题 | 新增唯一一种 Map 类型 `map-content`（`dict[str, str]`），把 `content_map` 更名为 `construct_map_content` 并新增 `map_content_get`，旧节点不保留（`docs/26:5-9,98`）。 |
| 关键设计决定 | 裸 `map` 非法、不预先开放 `map-message`（`docs/26:7`）；`content` 里的 JSON 文本不能直接连到 `map-content`，必须显式解析（`docs/26:22`）；Map 是值不是共享引用（`docs/26:22`）；六个数据边界（Workflow 输入输出 / 子 Workflow、deserialize_json、Context / Session、远程 Tool）都要支持 `map-content` 并做类型校验（`docs/26:70-73`）。 |
| 实现程度 | **部分实现**：数据类型集合（`agent/workflow_contract.py:8-16`）、节点与端口（`agent/workflow_contract.py:175-178`）、运行时构造与查键（`agent/workflow_nodes.py:177-199`）、JSON 转换（`agent/workflow_nodes.py:257-258`）、Context / Session 校验、编辑器契约与配色（`workflow_editor/static/workflow/domain/node-contract.js:1,94-100`）均已到位。 |
| 与源码差异 | **agent 侧契约漏注册**：`NODE_ARGUMENT_FIELDS_BY_TYPE` 无 `map_content_get`（`agent/workflow_contract.py:51-75` 逐项核对），而 `SUPPORTED_NODE_TYPES`（`:24`）与 `data_ports_for_node`（`:177`）都有；`agent/workflow_validator.py:178` 因此对任何 `map_content_get` 节点抛 `KeyError`。manager 侧同名表有该项（`manager_webui/workflows.py:33`），故保存与导入全部放行，只有运行时崩。 |
| 开放扩展点 | 嵌套 Map、动态写入 / 删除键、Map 遍历、默认值、隐式类型转换、Map↔JSON 自动转换（`docs/26:9,74`）；`map-message` 等其它值类型"另行设计"（`docs/26:7`）。 |

## 显式扩展槽清单

分类汇总全部"预留接口 / 可插拔边界 / 未来可接入点"。`性质`列区分：**已开放**（源码中存在真实接缝，新增实现即可接入）、**预留未用**（接缝存在但无实现者）、**目标态**（文档声明、源码无接缝）。

### 输入侧事件源

| 编号 | 扩展槽 | 出处 | 性质 | 现状 |
| --- | --- | --- | --- | --- |
| E-01 | 任意 `event_type` + 启用绑定 → `workflow` 事件 | `docs/24:7-14`；`docs/20:78` | 已开放 | 路由对除 `workflow` 外全部类型生效（`agent/task_worker.py:46-53`） |
| E-02 | 新适配器直接构造标准 `workflow` Event 写主队列 | `README.md:10,93` | 已开放 | 无需改执行器；payload 字段与 Input 端口同名即可 |
| E-03 | 新事件源适配器（Webhook / 定时 / 业务系统） | `README.md:10,74` | 预留未用 | 图中标为 `Future`，无实现 |
| E-04 | QQ / Terminal 适配器作为可替换实现 | `README.md:14,94-95` | 已开放 | 两个实现并存，语义不同（LIFO 排队 vs RPUSH 插队） |
| E-05 | callback 事件 → 队列 → 经绑定适配为 `workflow` Event | `README.md:88,98`；`docs/20:242-247`；`docs/19:150` | **已可用**（路线 A） | 队列取节点 `callback.queue`（`tool_server/main.py:57,141`）；设为 `main_agent_queue` + 建一条 `async_result` 启用绑定，主 worker 即走通用绑定路由消费（`agent/task_worker.py:46-53`），**不需要自建消费者**（成稿 §8.15） |
| E-06 | callback 触发状态可选 `working` / `completed` / `failed` | `docs/17:179`；`docs/18:110` | 已开放 | `callback_event()` 按 `on` 过滤（`tool_server/main.py:52-59`） |
| E-07 | callback `event_type` 白名单 `TOOL_CALLBACK_EVENT_TYPES` | `docs/17:178`；`docs/20:245` | 已开放 | `tool_server/main.py:233-234` |
| E-08 | 空闲时钟事件 / 主动行为 | `docs/废弃旧文档/05-路线图与创新.md:96-98` | 目标态 | 已归档文档标注"规划中"，源码无生产者 |
| E-09 | 事件格式统一构造器 / 类型枚举 / schema 校验入口 | `docs/审查日志/架构问题汇总.md:34` | 目标态 | 未决决策 A-08；当前靠各服务手写 dict |

### 编排侧节点

| 编号 | 扩展槽 | 出处 | 性质 | 现状 |
| --- | --- | --- | --- | --- |
| E-10 | 节点类型注册表（24 类） | `agent/workflow_contract.py:17-42` | 已开放 | 新增类型需同步 5 处副本（见 E-11） |
| E-11 | 节点契约单一来源（跨 Python / JS） | `架构问题汇总.md:33` | 目标态 | 未决决策 A-07；现有 5 份：agent、manager、`node-contract.js`、`serialization.js`、`workflow_canvas.mjs` |
| E-12 | 动态端口（router branches / deserialize outputs / remote tool ports） | `docs/22:45-51`；`docs/19:184-198` | 已开放 | 编辑器按 `arguments` 重建端口并回收失效连接 |
| E-13 | 未在 17–26 中成文的既有节点：`split_event`、`history`、`list_append`、`construct_list` | `agent/workflow_contract.py:25-29,185-192` | 已开放但**无设计文档** | 存在于契约与画布，`docs/` 无对应专题 |
| E-14 | 控制流成环（ReAct 自调用） | `README.md:38`；`agent/test_task_worker.py` | 已开放 | `run_workflow_map` 为 `while` 循环；有 `_workflow_call_stack` 递归防护 |
| E-15 | 环的迭代上限 / 超时保护 | `架构问题汇总.md:25` | 目标态 | 未决决策 A-04；`workflow_validator.py` 不做环检测 |
| E-16 | 子 Workflow 作为可复用能力单元 | `README.md:40`；`docs/19:236` | 已开放 | `workflow` 节点 + 元数据 `workflow_nodes` 契约快照 |
| E-17 | 全局 Context（跨执行共享状态） | `docs/21:247-257` | 目标态 | 首期明确不实现，且不许用节点参数切换 |
| E-18 | `context_delete` / append / merge / increment 原子节点 | `docs/21:446-454` | 目标态 | 首期"不实现"清单 |
| E-19 | 并行分支下 Context 的 CAS / 事务 | `docs/21:349-358` | 目标态 | 需要时再引入版本号或 `WATCH/MULTI/EXEC` |
| E-20 | 节点级 TTL / 永不过期 Context / Value 历史版本 | `docs/21:450-453` | 目标态 | 明确排除 |
| E-21 | Session 按名称检索、追加合并、自动过期、历史版本 | `docs/23:7` | 目标态 | 首期不做 |
| E-22 | `remote_tool_call` 等动态名称执行节点 | `docs/19:370` | 目标态 | 明确"本次不实现" |
| E-23 | LLM 远程工具挂载 / 动态工具调用 | `docs/19:65,371` | 目标态 | `llm.arguments.tools` 只挂本地工具（`agent/workflow_nodes.py:124-129`） |
| E-24 | 本地找不到工具时自动转发远程 | `docs/19:372` | 目标态 | 明确禁止"自动降级或跨目录查找"（`docs/19:68`） |
| E-25 | 工具参数类型系统扩展 | `docs/19:374` | 目标态 | 端口类型仍是四/七种固定集合 |
| E-26 | JSONPath / 数组下标 / 默认值 / 部分成功模式 | `docs/22:230-238` | 目标态 | 需真实需求后再独立设计 |
| E-27 | 数字 / 布尔 / 对象等新的 Workflow 一等数据类型 | `docs/22:235`；`docs/26:7` | 目标态 | 当前类型集合见 `agent/workflow_contract.py:8-16` |
| E-28 | deserialize_json 输出配置拖动排序 | `docs/22:237` | 目标态 | 首期靠删除后重加调整顺序 |
| E-29 | 嵌套 Map / Map 遍历 / Map 写入删除键 | `docs/26:9` | 目标态 | 首期不做 |
| E-30 | Map ↔ JSON / 条目列表的自动转换节点 | `docs/26:74` | 目标态 | 明确"本期不新增" |
| E-31 | 从 `content` 直接解析根对象的专用节点 | `docs/26:74` | 目标态 | "留待后续专门节点讨论" |

### 能力侧工具

| 编号 | 扩展槽 | 出处 | 性质 | 现状 |
| --- | --- | --- | --- | --- |
| E-32 | Provider WebSocket 动态注册工具 Schema | `docs/17:21,89-102` | 已开放 | `tool_server/main.py:300-315` |
| E-33 | Tool Schema 兼容 MCP 字段（`inputSchema` / `outputSchema` / `annotations`） | `docs/17:63-87` | 已开放 | 用 JSON Schema 2020-12，校验器为 `Draft202012Validator` |
| E-34 | 独立 MCP Adapter（tools/list、tools/call、Tasks 扩展） | `docs/17:266-278` | 目标态 | 源码零实现 |
| E-35 | Provider 侧 Consumer 并发横向扩展 | `docs/17:25`；`docs/18:39` | 已开放 | `tool_provider/runtime.py:26,38,83-88`；`TOOL_PROVIDER_CONSUMERS` |
| E-36 | `x-workflow-port-type` Schema 扩展字段（辅助端口类型选择） | `docs/19:178,244-246` | 已开放 | 只影响编辑器建议，不参与 Tool Server 校验 |
| E-37 | 工具 `revision` 递增式 Schema 版本 | `docs/17:87` | 已开放 | `TOOL_PROVIDER_REVISION`（三处默认不一致，见漂移 D-12） |
| E-38 | 远程同步 / 异步两种调用语义（同一工具可两种用法） | `docs/19:11,249` | 已开放 | 异步节点忽略元数据输出契约 |
| E-39 | 已发布异步任务的等待 / 跟踪 / 取消 API | `docs/19:63,373` | 目标态 | 明确非目标；节点发布完即不再管理 |
| E-40 | 按工具配置调用权限、Provider 与 HTTP 调用方分别认证 | `docs/17:258-259` | 目标态 | 当前接口无鉴权（`webui_py/main.py:85-109` 仅三个中间件） |

### 存储侧

| 编号 | 扩展槽 | 出处 | 性质 | 现状 |
| --- | --- | --- | --- | --- |
| E-41 | Context 仓储层（Key 构造 / 序列化 / 类型校验 / TTL / 大小） | `docs/21:200,394-403` | 已开放 | `agent/workflow_context_repository.py` |
| E-42 | Context Redis Hash 字段集（`version` 支持格式演进） | `docs/21:176-198` | 已开放 | 首版 `version=1` |
| E-43 | Session 集合与 `updated_at` 条件更新（乐观锁） | `docs/23:21-32` | 已开放 | `agent/workflow_session_repository.py:169`；页面 409 冲突 |
| E-44 | 每 Task 独立 TTL 通知 List | `docs/18:65` | 已开放 | `tool_server/task_store.py:74-75` |
| E-45 | callback Outbox + 滞留回收 + 退避重试 | `docs/18:57,110` | 已开放 | `tool_server/main.py:124-149` |
| E-46 | 大结果外置存储、任务记录只存引用 | `docs/18:121` | 目标态 | 文档列为原子性与清理要求，实现未覆盖 |
| E-47 | 事件入库体积控制 / 摘要化 | `2026-09-14-全项目-问题报告.md:387-391` | 目标态 | `record_history` 无条件全量展开 |
| E-48 | document callback（全局事件池按相关性召回） | `docs/废弃旧文档/05-路线图与创新.md:76-78` | 目标态 | 已归档文档标注"规划中"；现由 `history` 节点承担固定窗口召回 |
| E-49 | History / Event 的稳定唯一 ID（用于去重与观测合并） | `docs/webUI/前端事件流设计.md:36` | 目标态 | 当前靠内容指纹启发式合并 |
| E-50 | 全局 Context 的独立存储边界 | `docs/21:249-255` | 目标态 | 授权 / 命名空间 / TTL 策略均待设计 |

### 调度侧

| 编号 | 扩展槽 | 出处 | 性质 | 现状 |
| --- | --- | --- | --- | --- |
| E-51 | 队列语义显式 API（普通入队 vs 紧急入队） | `架构问题汇总.md:22` | 目标态 | 未决决策 A-01；现靠 `lpush/rpush/blpop/brpop` 方向配对 |
| E-52 | 终端插队优先级参数化 | `README.md:95`；`2026-09-14-全项目-问题报告.md:369-371` | 已开放但隐式 | `webui_py` 直接 `RPUSH`，行为未显式表达 |
| E-53 | Tool Server 单实例调度内核 + 故障重启恢复 | `docs/17:17,59`；`docs/18:9` | 已开放 | 明确**不允许**多实例并行调度 |
| E-54 | Tool Server 多实例 / 跨实例转发 | `docs/17:17` | 目标态（被否决方向） | 文档列为"与本系统职责划分不符" |
| E-55 | 单 worker 时间线（吞吐靠 Provider 而非 Agent） | `README.md:15`；`docs/18:48` | 已开放 | Consumer 数只改吞吐，不改 Agent 时间线 |
| E-56 | 入口鉴权边界（部署层 / 代码层 / 两者） | `架构问题汇总.md:23` | 目标态 | 未决决策 A-02 |
| E-57 | 循环上限与超限事件 | `架构问题汇总.md:25` | 目标态 | 未决决策 A-04 |

### 数学与规划侧

| 编号 | 扩展槽 | 出处 | 性质 | 现状 |
| --- | --- | --- | --- | --- |
| E-58 | MCTS reward 通过 Workflow 实现 | `README.md:184` | 目标态 | 仅一行 TODO；无设计稿 |
| E-59 | 交叉验证（多路径稳定性比较） | `README.md:185` | 目标态 | 仅一行 TODO |
| E-60 | ReAct multi-Agent 编排（上下文=任务状态+todo） | `README.md:186` | 目标态 | README 标注"长任务核心"，无实现 |
| E-61 | 上下文压缩 | `README.md:2` | 目标态 | 全仓仅愿景一句 |
| E-62 | 马尔可夫链决策与 LLM 结合 | `README.md:2` | 目标态 | 无细化文档 |
| E-63 | Workflow 可塑性驱动的 Agent 自演进 / ADAS 方向 | `README.md:2`；`todo.md:8` | 目标态 | 仅调研笔记 `docs/论文survey/ADAS.md` |
| E-64 | 小模型 draft-review 与主线采纳协议 | `docs/废弃旧文档/05-路线图与创新.md:271` | 目标态 | 已归档文档标注"规划中，尚未实现" |
| E-65 | 思考分支与语义合并 | `docs/废弃旧文档/05-路线图与创新.md:232` | 目标态 | 同上 |
| E-66 | Skill-Tool / Workflow-Tool / Skill-Tool 遗传算法寻优 | `docs/废弃旧文档/05-路线图与创新.md:14-25` | 目标态 | 同上；`docs/废弃旧文档/` 不代表当前行为 |
| E-67 | Pre-Tool（自然语言工具组）与 Content Package（无损内容包句柄） | `docs/废弃旧文档/05-路线图与创新.md:24-25,397` | 目标态 | 同上 |

## 未实现与路线图全表

去重规则：同一事项在多份报告出现时取**最早提出**者为主来源，其余记为"同项"，不重复计行。`类型`取值 功能 / 缺陷 / 重构；`纯设想`指只有愿景而无任何设计或代码接缝。

| 编号 | 事项 | 来源 | 类型 | 优先级 | 纯设想 |
| --- | --- | --- | --- | --- | --- |
| R-01 | MCTS reward 通过 workflow 实现 | `README.md:184` | 功能 | — | 是 |
| R-02 | 交叉验证 | `README.md:185` | 功能 | — | 是 |
| R-03 | ReAct multiAgent 编排（上下文代表任务状态 + todo） | `README.md:186` | 功能 | 长任务核心 | 是 |
| R-04 | 上下文压缩 | `README.md:2` | 功能 | — | 是 |
| R-05 | 马尔可夫链决策 | `README.md:2` | 功能 | — | 是 |
| R-06 | ADAS / 交互方向探索 | `todo.md:7-8` | 功能 | — | 是 |
| R-07 | 强类型检查（全链路类型收紧） | `todo.md:2` | 重构 | — | 否 |
| R-08 | 代码结构 / 目录与命名优化 | `todo.md:3` | 重构 | — | 否 |
| R-09 | wf 类型问题及其边界 | `todo.md:4` | 缺陷 | — | 否 |
| R-10 | json 问题 | `todo.md:5` | 缺陷 | — | 否 |
| R-11 | review（流程项，见 `docs/审计.md`） | `todo.md:1`；`docs/审计.md:1-10` | 重构 | — | 否 |
| R-12 | agent 契约漏注册 `map_content_get`，含该节点的工作流无法执行 | `2026-10-11:27-33`（本轮复核仍在） | 缺陷 | 高 | 否 |
| R-13 | async 回调 `on` 含非字符串元素时校验器崩溃（agent + manager 两份同构代码） | `2026-10-11:35-40`（本轮复核仍在） | 缺陷 | 中 | 否 |
| R-14 | Provider 输出不符合 `outputSchema` 时打断 WebSocket 连接 | `2026-10-11:42-47`（本轮复核仍在） | 缺陷 | 中 | 否 |
| R-15 | `call_tool` 派发前 `next(...)` 竞态 → 500 而非 503 | `2026-10-11:49-53`（本轮复核仍在） | 缺陷 | 低 | 否 |
| R-16 | 双校验器分叉：manager 保存校验是 agent `validate_workflow` 的子集 | `2026-10-11:57`；同项 `2026-09-13` W1、`2026-09-14` H-04/L-10 | 重构 | 长期 | 否 |
| R-17 | 保存时静默丢弃类型不匹配的连接，且不回告前端 | `2026-10-11:58`；同项 `2026-09-14` H-05 | 缺陷 | 中 | 否 |
| R-18 | `event_catalog` 的 `async_result` schema 缺 `working` 状态 | `2026-10-11:59` | 缺陷 | 低 | 否 |
| R-19 | `rename_workflow` 不更新 `event_bindings.workflow_name`；`delete_workflow` 不清理 binding | `2026-10-11:60` | 缺陷 | 中 | 否 |
| R-20 | 入口 payload 不做端口类型强校验 | `2026-10-11:61`；同项 `2026-09-13` R7、`2026-09-14` M-06 | 缺陷 | 中 | 否 |
| R-21 | LLM 空值语义不一致（`output=None` 视为未到达，`reasoning=""` 视为已到达） | `2026-10-11:62`；同源 `2026-09-14` F-04 | 缺陷 | 中 | 否 |
| R-22 | env 矩阵缺口（`TOOL_CLIENT_DEFAULT_ASYNC_TIMEOUT_MS`、`MONGO_EVENT_BINDING_COLLECTION`、`WORKFLOW_CONTEXT_*`、`WORKFLOW_SESSION_MAX_VALUE_BYTES`、`BILIBILI_DOWNLOAD_DIR` 未入示例；`ASR_URL`/`MODEL_ID`/`DEEPSEEK_MODEL` 死配置） | `2026-10-11:63`（本轮复核 `.env.example` 仍缺） | 重构 | 中 | 否 |
| R-23 | sessions 列表缺 `(updated_at, _id)` 复合索引 | `2026-10-11:64` | 缺陷 | 低 | 否 |
| R-24 | 模型 API 明文回传 `api_key` | `2026-10-11:65`；同项 `2026-09-14` H-03、`2026-09-13` W4 | 缺陷 | 低（外网前必修） | 否 |
| R-25 | `workflow_canvas.mjs` 是第 5 份契约副本且过期（缺 map/deserialize/session 节点与 `map-content` 配色） | `2026-10-11:104`（本轮复核仍在） | 缺陷 | 中 | 否 |
| R-26 | `workflow_editor/static/api.js` 12 个死导出 | `2026-10-11:105` | 重构 | 低 | 否 |
| R-27 | agent 镜像依赖死重量（ffmpeg / ffmpeg-python / pydub 零使用） | `2026-10-11:106` | 重构 | 低 | 否 |
| R-28 | `manager_webui/static/workflows.js` 清理无写入方的 localStorage 键 | `2026-10-11:107` | 重构 | 低 | 否 |
| R-29 | `structure.js` 的 deserialize_json 输出类型下拉缺 `map-content` | `2026-10-11:108`（本轮复核 `structure.js:190` 仍缺） | 缺陷 | 低 | 否 |
| R-30 | 导入格式两侧不对称（编辑器识别旧集合格式，管理页不识别） | `2026-10-11:109` | 缺陷 | 低 | 否 |
| R-31 | 构建 / 配置漂移（`TOOL_PROVIDER_REVISION` 2/5/3；示例 `TOOL_MODULES` 缺 `tools.system`；agent 基镜像 3.11 与其余 3.12 不一致；依赖未锁版） | `2026-10-11:110`（本轮复核 `.env.example:37`=2、`docker-compose.yml:204`=5、`tool_provider/main.py:25`=3） | 重构 | 低 | 否 |
| R-32 | 残留实验文件与死代码（`agent/tools/1.py`、`agent/tools/documents.py`、`agent/tools/qqapi.py`、`agent/utils.py`） | `2026-10-11:111`；同项 `2026-09-14` L-01/L-02（`agent/2.py`、`agent/3.py` 已删除） | 重构 | 低 | 否 |
| R-33 | 静态资源 `?v=` 版本号覆盖不全（部分页面无版本号） | `2026-10-11:112` | 重构 | 低 | 否 |
| R-34 | 遗留迁移代码（`webui_py/main.py:78-79`、`manager_webui/main.py:85-86` 启动时 drop_index） | `2026-10-11:70`（本轮复核仍在） | 重构 | 低 | 否 |
| R-35 | `agent/llm.py` 全量打印模型响应、每次新建 `MongoClient`、混型返回 `(402, None, None)` | `2026-10-11:71`；同项 `2026-09-14` L-03/M-01 | 重构 | 低 | 否 |
| R-36 | `llm.py` → `tools.tool` 导入链副作用（import 时 `redis_reset_tools()`） | `2026-10-11:72`；同项 `2026-09-14` M-07（本轮复核 `agent/tools/tool.py:33`、`agent/llm.py:8` 仍在） | 缺陷 | 中 | 否 |
| R-37 | callback outbox 按值 `lrem` 去重不稳 | `2026-10-11:73`（本轮复核 `tool_server/main.py:142,146`） | 缺陷 | 低 | 否 |
| R-38 | `render.js` 的 `event_type === 'active'` 特判为死分支 | `2026-10-11:74`；同项 `2026-09-14` H-06 的残留面 | 重构 | 低 | 否 |
| R-39 | 队列语义集中定义（A-01） | `架构问题汇总.md:22`；同项 `2026-09-14` H-01/H-08/X-01 | 重构 | P0 | 否 |
| R-40 | 入口鉴权边界（A-02） | `架构问题汇总.md:23`；同项 `2026-09-14` H-02 | 缺陷 | P0 | 否 |
| R-41 | 死链 `active` / `tool_excute` 与附带上下文能力处置（A-03） | `架构问题汇总.md:24`；同项 `2026-09-14` H-06 | 重构 | P0 | 否 |
| R-42 | 控制流环是否需要迭代上限（A-04） | `架构问题汇总.md:25` | 缺陷 | P0 | 否 |
| R-43 | 是否建立共享代码层（A-05） | `架构问题汇总.md:31` | 重构 | P1 | 否 |
| R-44 | 连接校验以哪一侧为准（A-06） | `架构问题汇总.md:32` | 缺陷 | P1 | 否 |
| R-45 | 节点契约单一来源（A-07） | `架构问题汇总.md:33` | 重构 | P1 | 否 |
| R-46 | 事件格式统一构造与校验入口（A-08） | `架构问题汇总.md:34` | 重构 | P1 | 否 |
| R-47 | 配置权威来源（Redis vs 文件，`SET NX`）（A-09） | `架构问题汇总.md:35`；同项 `2026-09-14` M-08 | 缺陷 | P1 | 否 |
| R-48 | Redis 连接参数统一（密码与 `socket_timeout`）（A-10） | `架构问题汇总.md:36`；同项 `2026-09-14` M-21/M-22 | 缺陷 | P1 | 否 |
| R-49 | Python 版本与依赖锁定策略（A-11） | `架构问题汇总.md:37` | 重构 | P1 | 否 |
| R-50 | 主 worker 缺少失败反馈（节点失败静默中断） | `2026-09-14:60-95`（F-02，本轮复核 `agent/task_worker.py:96-122` 仍在） | 缺陷 | 高 | 否 |
| R-51 | 未知 `event_type` 的可诊断处理（缺 `payload` 时 `KeyError`） | `2026-09-14:327-350`（H-07；`handle_map` 已删除，改为绑定查询，仍未判空） | 缺陷 | 中 | 否 |
| R-52 | 事件与队列写入路径无体积限制 | `2026-09-14:387-391`；同项 `2026-09-13` R3 | 缺陷 | 中 | 否 |
| R-53 | `request_body_guard` 只信 `content-length` | `2026-09-14:509-513`；同项 `2026-09-13` W3 | 缺陷 | 中 | 否 |
| R-54 | 编辑器把 LLM 输入端口静默改写（文档描述与现行 `messages-in` 单端口不符） | `2026-09-14:515-530`（M-12；源码已改为 `messages-in`，问题描述过期） | 缺陷 | 中 | 否 |
| R-55 | 编辑器用 URL 查询串传递整份 Workflow JSON | `2026-09-14:545-559` | 缺陷 | 中 | 否 |
| R-56 | `agent/.dockerignore` 未排除 `downloaded/`、`settings.json`、测试文件 | `2026-09-14:561-569`；同项 `2026-09-13` D1 | 缺陷 | 中 | 否 |
| R-57 | `qqbot_consumer/` 与 `workflow_editor/` 缺 `.dockerignore` | `2026-09-14:583-585`（本轮复核仅 `agent/.dockerignore` 存在） | 重构 | 低 | 否 |
| R-58 | `qqbot/listener.py` 不校验发送者，未授权私聊仍入库 | `2026-09-14:587-593` | 缺陷 | 中 | 否 |
| R-59 | `bilibili.asr` 硬编码第三方端点与占位 API Key | `2026-09-14:595-607` | 缺陷 | 中 | 否 |
| R-60 | `workflow_editor` 健康检查不探测依赖 | `2026-09-14:673-681`；同项 `2026-09-13` W5 | 缺陷 | 低 | 否 |
| R-61 | 前端事件指纹存在碰撞可能 | `2026-09-14:695-701` | 缺陷 | 低 | 否 |
| R-62 | `rename_workflow` 级联刷新引用方 `updated_at`；单条 `update_many` 承载两个 arrayFilters 且无事务 | `2026-09-14:703-729`；同项 `2026-09-13` W2 | 缺陷 | 低 | 否 |
| R-63 | `openai_llm_api` 的 `extra={}` 可变默认参数 | `2026-09-14:735-737` | 缺陷 | 低 | 否 |
| R-64 | 测试覆盖不足（保存面与运行时执行器缺自动化测试） | `2026-09-13:46`（T1） | 重构 | 中 | 否 |
| R-65 | `workflow_editor` 公共组件抽取（状态按钮 / 页脚操作区） | `2026-08-05-webui-前端-问题汇总.md:41` | 重构 | 低 | 否 |
| R-66 | 文档列表无分页上限、`documents.updated_at` 无索引 | `2026-08-05-webui文档页-实现记录.md:69,85` | 缺陷 | 低 | 否 |
| R-67 | 文档中心 Markdown 预览（需本地打包解析器，不能用 CDN） | `2026-08-05-webui文档页-实现记录.md:85` | 功能 | 低 | 否 |
| R-68 | 设置页多字段扩展（向 `aagent:settings` 追加字段） | `2026-08-06-settings-redis-审计报告.md:49` | 功能 | 低 | 否 |
| R-69 | `GET /api/settings` 用 503 表达"尚未初始化"语义混淆 | `2026-08-05-webui-后端-问题汇总.md:46` | 重构 | 低 | 否 |
| R-70 | 全局 Context（含授权 / 命名空间 / TTL / 泄漏边界） | `docs/21:247-257` | 功能 | — | 否（有设计约束，无实现） |
| R-71 | Session 按名称检索 / 追加合并 / 自动过期 / 历史版本 | `docs/23:7` | 功能 | — | 否（明确首期不做） |
| R-72 | MCP Adapter | `docs/17:266-278` | 功能 | 最后 | 是（有映射表，无代码） |
| R-73 | 异步任务 cancel API | `docs/19:63` | 功能 | — | 否（明确当前缺失） |
| R-74 | 空闲时钟事件 / 主动行为 | `docs/废弃旧文档/05-路线图与创新.md:96-98` | 功能 | — | 是 |
| R-75 | document callback 相关性召回 | `docs/废弃旧文档/05-路线图与创新.md:76-78` | 功能 | — | 是 |
| R-76 | Skill-Tool / Workflow-Tool / 遗传算法寻优 | `docs/废弃旧文档/05-路线图与创新.md:14-25` | 功能 | — | 是 |
| R-77 | 小模型 draft-review 与主线采纳协议 | `docs/废弃旧文档/05-路线图与创新.md:271` | 功能 | — | 是 |
| R-78 | 思考分支与语义合并 | `docs/废弃旧文档/05-路线图与创新.md:232` | 功能 | — | 是 |
| R-79 | Pre-Tool 工具分组与 Content Package 内容包 | `docs/废弃旧文档/05-路线图与创新.md:24-25,397` | 功能 | — | 是 |
| R-80 | Chat 页面回显 Agent 最终 `response` 与工具调用过程 | `docs/废弃旧文档/05-路线图与创新.md:104-106` | 功能 | — | 否（标注"部分实现，尚未完成"） |
| R-81 | 全局/激活 Workflow 回退（已被绑定路由取代） | `docs/24:12`；`docs/20:78` | 重构 | 已关闭 | 否 |
| R-82 | `_id="agent"` 全局设置读取逻辑删除 | `docs/24:12` | 重构 | 已关闭 | 否 |

> 计数：上表 **82** 项，其中已关闭 2 项（R-81/R-82 保留在表内以标记"曾经的路线图项已被绑定路由取代"），**纯设想 12** 项。

## 已知问题摘要

仅列**结论与编号**，不复述证据；"仍成立"指本轮静态复核在源码中仍能定位到对应实现。

### 2026-10-11 全项目审查报告（最新，四项生产缺陷均未修复）

| 编号 | 结论 | 本轮复核 |
| --- | --- | --- |
| A1 [高] | agent 契约漏注册 `map_content_get`，含该节点的工作流无法执行 | **仍成立**：`agent/workflow_contract.py:51-75` 无该项，`agent/workflow_validator.py:178` 会 `KeyError`；manager 侧有（`manager_webui/workflows.py:33`） |
| A2 [中] | async 回调 `on` 含非字符串元素时校验器崩溃 | **仍成立**：`agent/workflow_validator.py:389` 与 `manager_webui/workflows.py:129` 均在类型判断前做集合成员测试 |
| A3 [中] | Provider 输出不符合 `outputSchema` 时打断 WebSocket 连接 | **仍成立**：`tool_server/main.py:118` 抛出的 `jsonschema.ValidationError` 不在 `:319` 的 except 元组内 |
| A4 [低] | `call_tool` 派发前 `next(...)` 存在竞态 | **仍成立**：`tool_server/main.py:259` 无默认值 |
| 3.1–3.9 | 双校验器分叉、保存静默丢连接、`event_catalog` 状态枚举、改名/删除引用面、入口 payload 无强校验、LLM 空值语义、env 矩阵缺口、sessions 索引、`api_key` 明文 | 逐条与源码一致，未发现修复痕迹；见路线图 R-16 至 R-24 |
| B1 | `workflow_canvas.mjs` 过期副本 | **仍成立且更明显**：`TYPE_COLORS`(`:5-24`) 缺 map/deserialize/session，`CONNECTION_COLORS`(`:26-34`) 缺 `map-content`，`contractPortIds`(`:54-101`) 对这些节点返回 `[]` |
| B5 | deserialize_json 输出类型下拉缺 `map-content` | **仍成立**：`workflow_editor/static/workflow/inspector/structure.js:190` |
| B7 | 构建/配置漂移（`TOOL_PROVIDER_REVISION` 三处不一致） | **仍成立**：`.env.example:37`=2、`docker-compose.yml:204`=5、`tool_provider/main.py:25`=3 |
| B3/B4/B6/B8/B9 | 镜像死重量、死 localStorage 键、导入格式不对称、残留文件、`?v=` 覆盖不全 | 未逐条复核，登记为待核 |

### 2026-09-14 全项目问题报告（45 项 + 3 项跨领域；已部分失效）

| 编号 | 结论 | 状态 |
| --- | --- | --- |
| F-01 | LLM 节点 `model` 参数运行时被完全忽略 | **已修复**：`agent/workflow_nodes.py:130-132` 传入 `node_argument(node, "model")`，`agent/llm.py:11-36,65-78` 按 `_id` 读 Mongo 模型集合 |
| F-02 | 节点执行异常静默中断，无失败反馈 | **仍成立**：`agent/task_worker.py:56-93` 无节点级 try/except，异常仍冒泡至 `:119-122` 只打印（R-50） |
| F-03 | 子 Agent 回发链路不闭环，群消息发不出 | **已移除**：全仓 `*.py` 检索 `rpc_apply`/`rpc_review` 零匹配，链路整体删除 |
| F-04 | LLM 无文本输出时 `output → tool_call` 主链路必失败 | **已失效**：`tool_call` 节点已删除（`docs/19:65`、`agent/workflow_contract.py:17-42` 无该类型），`tool_calls` 改为 list-content 输出（`agent/workflow_nodes.py:136-142`）；但 `None` 语义问题转入 R-21 |
| H-01 | QQ 子 Agent 队列 LIFO | **仍成立**：`qqbot_consumer/queue_client.py:19,25` 为 `lpush` + `blpop`（README 把它写成"当前值"） |
| H-02 | 全部 HTTP 接口无鉴权 | **仍成立**：`webui_py/main.py:85-109` 仅三个中间件，无鉴权依赖 |
| H-03 | `GET /api/models` 明文返回 `api_key` | **仍成立**（10-11 §3.9 复述，本地单用户被接受） |
| H-04 | 保存面校验弱于执行面 | **仍成立**：agent 要求恰好一个 `input`（`agent/workflow_validator.py:75`）与控制端口连通（`:150`），manager 无对应规则 |
| H-05 | 两套连接校验分叉且保存时静默丢连接 | **仍成立**：`manager_webui/workflows.py:488-500` |
| H-06 | `active` / `tool_excute` 死代码与附带能力失效 | **已通过删除关闭**：`agent/task_worker.py` 只剩绑定路由与 `workflow` 分支，无 `handle_map`；但 `架构问题汇总` A-03 仍登记为未决，且 `render.js` 的 `active` 特判未清（R-38） |
| H-07 | 未知 `event_type` 触发 `TypeError` | **已关闭**：无 `handle_map.get()` 调用；残留风险是缺 `payload` 时的 `KeyError`（R-51） |
| H-08 | 终端 `RPUSH` 插队 | **仍成立**且被 README 承认为设计（`README.md:95`、`docs/20:52`）；决策未定（R-39） |
| M-01 | 每个 Workflow 事件新建 Mongo 连接并全量读定义 | **仍成立并扩大**：`agent/task_worker.py:34`、`agent/llm.py:30` 均按调用新建 `MongoClient` |
| M-07 | `tools/tool.py` import 时清空工具注册表 | **仍成立**：`agent/tools/tool.py:33` `redis_reset_tools()`，且被 `agent/llm.py:8` 导入链带出 |
| M-10 | `get_recent_history` 可变默认参 | **已修复**：`agent/history_repository.py:57-67` 改为 `query: dict | None` 并在内部拷贝 |
| M-13 | 节点契约常量四处副本 | **仍成立且增至五处**（新增 `manager_webui/static/workflow_canvas.mjs`） |
| M-15/M-16/M-17/M-21/M-22 | 镜像上下文、依赖与基础镜像、`.dockerignore`、Redis 密码未注入、缺 socket 超时 | **仍成立**（R-56/R-57/R-31/R-48） |
| L-02 | 仓库混入草稿（`agent/2.py`、`agent/3.py`、`agent/tools/1.py`） | **部分修复**：`2.py`/`3.py` 已删除，`agent/tools/1.py`、`qqapi.py`、`documents.py` 仍在 |
| L-03 | 库函数打印完整 HTTP 响应 | **仍成立**：`agent/llm.py:58` `print(resp.json())` |
| X-01/X-02/X-03 | 复制粘贴的服务副本、事件格式不统一、控制流环无限制 | **均仍成立** |

### 2026-09-13 全项目审查报告（P1 三项）

| 编号 | 结论 | 状态 |
| --- | --- | --- |
| R1 | Workflow 节点失败静默中断 | **仍成立**（同 F-02） |
| R2 | 子 Agent 回发链路不闭环 | **已移除**（同 F-03） |
| M1 | 核心文档 00-08 与运行时脱节（`active` 旧链） | **已用归档处理**：00-08 全部移入 `docs/废弃旧文档/`；`docs/24:3` 亦已改为"绑定路由已实现"的表述 |
| W1 | 保存面校验弱于执行面 | **仍成立**（同 H-04） |
| W2 | 重命名级联的 arrayFilters 双路径 + 无事务 | **仍成立**（R-62） |
| W3 | 请求体守卫只信 `content-length` | **仍成立**（R-53） |
| W4 | 模型接口明文返回 `api_key` | **仍成立**（R-24） |
| T1 | 测试覆盖集中于解析层 | **部分改善**：已新增 `test_task_worker.py`、`test_tool_nodes.py`、`test_history_repository.py`、`test_workflow_context_repository.py`、`test_workflow_session_repository.py`、`test_sessions.py`；保存面接口测试仍薄（R-64） |
| D2 | 仓库跟踪历史补丁文件 | **已关闭**：`backup-before-rollback.patch` 已不在工作区 |
| R5/R6/R8/R9 | `active` 死分支、未知 event_type、可变默认参、未引用草稿 | 前三项已关闭（见上），R9 部分关闭 |
| M2/M3/M4 | 解析器契约过期、服务拓扑与端口不一致、`.env.example` 缺口 | **M2 已随文档归档失效**；M3 部分改善（README 服务表已含 `qqbot_consumer`、`workflow_editor`、8082）；M4 仍有缺口（R-22） |

## 文档与实现漂移

按"读者会被误导的程度"排序。每条给出**文档主张 → 源码事实 → 影响**。

| 编号 | 文档主张 | 源码事实 | 影响 |
| --- | --- | --- | --- |
| D-01 | `docs/24:14`：`workflow`、`response`、`error` 是内部事件，不走绑定路由，避免内部事件再次触发自身；`docs/20:78`：`response` / `error` 不参与绑定路由 | `agent/task_worker.py:46` 只排除 `workflow`，`response` / `error` 同样查绑定；`agent/test_task_worker.py:66-74` 断言二者有绑定时会触发 Workflow | **严重**。按文档理解事件安全边界会得出相反结论；若为 `response` 建绑定会形成自触发链 |
| D-02 | `docs/19:275`：`remote_async_tool` 保存时"不允许出现 `mode` 或 `callback` arguments" | `agent/workflow_contract.py:67` 允许 `callback`；`agent/workflow_validator.py:375-392` 完整校验 callback 结构；`docs/19:163-165` 与 `docs/20:214-222` 亦描述 callback 能力 | **严重**。文档自相矛盾，实施者若按 §5.2 删掉校验会破坏已落地的回调配置 |
| D-03 | `docs/23:34`：`workflow_context_repository.py` 的 `_valid_value` 未处理 `event` / `list-event`，须先解决该差异才能复用为六类型校验器 | `agent/workflow_context_repository.py:49-52` 已处理 `event` 与 `list-event` | **高**。会诱导实现者重复修补已完成的类型校验 |
| D-04 | `docs/22:52-61`：`deserialize_json` 的 `type` 支持六种类型（不含 `map-content`） | `agent/workflow_nodes.py:257-258` 支持 `map-content`；`docs/26:71` 亦要求支持 | **高**。按 22 号文档实现会漏掉 `map-content` 分支 |
| D-05 | `docs/23:74`：Session"当前仅完成语法和编辑器静态诊断；运行时测试及浏览器交互仍需执行" | 已有 `agent/test_workflow_session_repository.py`、`manager_webui/test_sessions.py`；`2026-10-11` 报告在容器内跑通 agent 90 例、manager 17 例 | **高**。会低估 Session 的落地程度并重复投入验证 |
| D-06 | `docs/21:453` 与 `docs/21:247` 把全局 Context 记为"后续/首期不实现"；同时 `docs/21:14` 把它列为 Context 的两大类之一 | 全局 Context 无任何实现；跨执行持久化的实际落地形态是 Session（MongoDB），与 Context 语义、节点类型、存储都不同 | **高**。读者容易把 Session 当"全局 Context 已实现"，从而按 21 号文档的作用域规则去理解 Session |
| D-07 | `docs/审查日志/架构问题汇总.md:36` 指向 `docs/09-同步架构加速.md`；`2026-09-14:841` 同样指向该路径 | 该文件实际位于 `docs/废弃旧文档/09-同步架构加速.md`，`docs/` 根目录下不存在 | **中**。活文档的关联链接失效，待度量项 O-01…O-05 无处可查 |
| D-08 | `架构问题汇总.md:14,24`、`2026-09-14` H-06 把 `active` / `tool_excute` 死链列为"未决决策 A-03"，并称 `render.js` 为 `active` 保留特判 | `agent/task_worker.py` 已无 `handle_map`、无 `active` / `tool_excute` / `rpc_*` 分支；死链已通过删除关闭，仅 `render.js` 残留 | **中**。A-03 部分已成为"已决策/已关闭"却仍留在待决策区，与 `架构问题汇总.md:43`"暂无已决策项"冲突 |
| D-09 | `docs/20:25,78` 的事件类型表只列 `qq` / `terminal` / `workflow` / `response` / `error`，并称"其他 Event 按 event_type 查询启用的绑定" | 源码对任意 `event_type`（除 `workflow`）都查绑定；表未体现 `async_result`（Tool Server 回调，`docs/20:227-247` 正文有、表中无） | **中**。事件类型总表不完整，新增事件时容易漏改 |
| D-10 | `2026-09-14:515-530`（M-12）称编辑器把 LLM 的 `content-in-N` 静默改写为 `message-in-N`，并称 LLM 输入端口为 `message-in-*` | LLM 节点的数据输入端口已收敛为单一 `messages-in`（`agent/workflow_contract.py:167`）；`manager_webui/static/workflow_canvas.mjs:96-98` 亦如此 | **中**。M-12 描述的端口名在当前契约中不存在，按该条排查会找不到位置 |
| D-11 | `2026-10-11:57`（§3.1）称"双校验器分叉"仍缺 `router` / `construct_message` / `construct_content` / `construct_list` / `foreach` / `llm` 等类型的参数校验 | `manager_webui/workflows.py:26-52` 的 `NODE_ARGUMENT_FIELDS_BY_TYPE` 已含上述全部类型，`node_format_error` 亦按该表校验（`:139,149`） | **中**。分叉的实际形态已从"缺类型"变为"缺结构规则"（恰好一个 `input`、控制端口连通性），文档未同步 |
| D-12 | `2026-10-11:110`（B7）登记 `TOOL_PROVIDER_REVISION` 三处不一致 | 复核仍为 2 / 5 / 3（`.env.example:37`、`docker-compose.yml:204`、`tool_provider/main.py:25`） | **低**（漂移本身成立，登记准确，未被修复） |
| D-13 | `README.md:98`、`docs/20:247` 称"当前主 worker 没有 `async_result` handler，所以原始回调不能直接写入 `main_agent_queue`" | **判定为错**：现行 worker 的条件是 `event_type != "workflow"`（`agent/task_worker.py:46`），对任意类型开放绑定路由，故 `async_result` 配一条绑定即可进主队列 | **高（本轮修正）**。原稿误判为"与源码一致"；实际 `docs/19:150` 把 `callback.queue` 写成 `main_agent_queue` 是**对的**，README / docs20 才是过时的一方。详见成稿 §8.15 |
| D-14 | `docs/20:38-39` 记录 QQ 队列为 LIFO"当前值" | 与源码一致（`qqbot_consumer/queue_client.py:19,25`） | **低**，但同一事实被 `2026-09-14:171-187`（H-01）判为缺陷，两处口径相反，需择一 |
| D-15 | `docs/17` – `docs/26` 未收录 `split_event`、`history`、`list_append`、`construct_list` 四类已注册节点 | `agent/workflow_contract.py:25-29,185-192` 与 `manager_webui/static/workflow_canvas.mjs:68-76` 均支持 | **中**。设计文档集合不完整，新接手者会误以为节点集合只有文档覆盖的部分 |
| D-16 | `docs/审查日志/README.md:7-9` 把三份 2026-08-05 领域汇总列为"权威清单（活文档）"，问题登记以它们为准 | `docs/审查日志/` 根目录只有这三份汇总，但其条目明显早于 2026-09-14 / 2026-10-11 报告；最新问题实际登记在两份全项目报告与 `架构问题汇总` | **中**。按 README 指引去查权威清单会漏掉最新问题 |

## 7.4 推荐阅读路径

给新接手者的一条**从运行态到目标态**的代码阅读顺序，每步都指向当前源码而非文档：

1. **先看事件入口与路由**：`agent/task_worker.py`（全 126 行）——这是当前唯一的执行入口，绑定路由、`workflow` 事件、`error` 事件、`response` 事件、worker 状态与失败兜底都在这里。
2. **再看队列与历史底座**：`agent/queue_client.py`（队列方向语义）→ `agent/history_repository.py`（含 `get_recent_history` 的召回窗口）。
3. **然后看契约与校验**：`agent/workflow_contract.py`（24 类节点、端口、连接规则）→ `agent/workflow_validator.py`（结构规则与各类型参数校验，注意 `:178` 的 A1 缺口）。
4. **接着看节点实现**：`agent/workflow_nodes.py`（`run_workflow_map` 的执行循环、`invocation_id` / `finally` 清理、各 `workflow_*` handler、LLM 与两类 Tool）。
5. **再看两个状态仓储**：`agent/workflow_context_repository.py`（Redis、TTL、作用域）→ `agent/workflow_session_repository.py`（MongoDB、乐观锁）。
6. **然后看能力侧**：`tool_server/main.py` + `tool_server/task_store.py`（任务状态机、通知 List、callback outbox、Provider socket）→ `agent/tool_server_client.py`（Workflow 侧调用与 200/202 映射）。
7. **再看编排的两端**：`manager_webui/workflows.py`（保存校验 + 静默连接过滤）与 `workflow_editor/static/workflow/`（`domain/node-contract.js` → `domain/serialization.js` → `inspector/` → `editor.js`）。
8. **最后看目标态**：本文档 7.2 与 `## 显式扩展槽清单`，再去 `README.md:2` 与 `README.md:182-186` 对照愿景与 TODO——凡本文标为"纯目标态"的项，源码中不存在接缝，不能按已实现使用。

> 与 `docs/README.md:21-33` 的官方阅读顺序的差别：官方入口按"主题"组织（Event → 绑定 → 远程 Tool → …），适合查证单个设计；上面的顺序按"运行链路"组织，适合在 17–26 与源码出现冲突时快速定位真相。
