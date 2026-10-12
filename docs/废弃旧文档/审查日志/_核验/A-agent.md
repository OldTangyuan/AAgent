# A-agent 历史问题对当前源码核验

> 类型:核验记录。
> 性质:历史快照。
> 归属:`agent/`。
> 适用版本:平台 `4.0.0+`。

> 工作区 D:\AAgent；只读源码取证，未修改 `_核验/` 以外的任何文件。
> 报告行号一律作废，下列行号均为本次实际读到的行号。

## 组 1

- 1 | A1 | **FIXED** | ~~`agent/workflow_contract.py:24` SUPPORTED_NODE_TYPES 有 `"map_content_get"`、`:177` data_ports_for_node 也有分支，但 `:51-75` NODE_ARGUMENT_FIELDS_BY_TYPE 无该键~~ | **已修复**：`agent/workflow_contract.py:58` 已补 `"map_content_get": set(),`。`agent/workflow_validator.py:178` 仍是裸下标但已无缺项可撞；`agent/test_workflow_node.py:263` 与 `agent/test_tool_nodes.py:240` 两例应转绿（未复跑）。本组条目计数 9 → 8
- 2 | A2 | STILL | `agent/workflow_validator.py:389-390` `any(status not in {"working","completed","failed"} ...)` 与 `len(...)!=len(set(callback["on"]))`；`manager_webui/workflows.py:129-130` 同构 | `on=[{"status":"completed"}]` → dict 不可哈希 → TypeError（不是 WorkflowValidationError）；两份同构代码都还在
- 3 | A3 | STILL | `tool_server/main.py:118` `Draft202012Validator(tool.outputSchema).validate(event.output)`；`:319` except 只捕获 `(PydanticValidationError, SchemaError, ValueError)` | jsonschema==4.25.1 的 `ValidationError` 继承 `_Error(Exception)`（已核上游 v4.25.1 exceptions.py），不是 ValueError → 不被捕获，WebSocket 处理器内异常逃逸
- 4 | A4 | STILL | `tool_server/main.py:258-259` `next(item["provider_id"] for item in tools if item["name"] == tool_name)` 无 default，与 `:230` registry.get_tool 之间存在窗口 | provider 掉线 → StopIteration（协程内 PEP479 转 RuntimeError）→ 500
- 5 | 第3节-1 | STILL | `manager_webui/workflows.py:136-204` node_format_error 只覆盖 history/list_append/deserialize_json/construct_map_content/context_*；对照 `agent/workflow_validator.py:195-296` 缺 router 分支、construct_message role(_source)、construct_content append_items、construct_list、foreach；`:812-817` 对 input/output 只查 `isinstance(workflowPorts, list)`，agent `:474-506` 还查 id 命名空间/名称一致/类型/重复 | llm 参数校验两面都缺
- 6 | 第3节-2 | STILL | `manager_webui/workflows.py:904-915` update_workflow 仍走 `synchronize_metadata_ports`（`:269-305`，其中 `:300-303` continue 丢弃错型连接）+ `filter_invalid_connections`（`:308-451`，`:451` 静默过滤）| 保存时静默丢连接
- 7 | 第3节-5 | STILL | `agent/task_worker.py:84-87` `propagate_workflow_output(..., e['payload'].get(port['name']))`；`agent/workflow_nodes.py:34-44` 只做 dict 浅拷贝写槽位 | 入口无端口类型强校验，缺键 → None
- 8 | 第3节-6 | STILL | `agent/workflow_nodes.py:31` `return input_slot[2] is not None`；`:130-142` content 与 reasoning 原样传播；`agent/llm.py:59-63` content 可能为 None、reasoning 缺失时为 `""` | 只回 tool_calls 时 output=None 被判"未到达"，reasoning="" 被判"有值"，同节点两类输出语义不一致
- 9 | 第4节-1 | STILL | `agent/tools/documents.py`、`agent/tools/qqapi.py`、`agent/tools/1.py`、`agent/utils.py`、`agent/downloaded/` 全部存在；全仓 grep `tools.documents`/`import qqapi`/`from utils import` 只命中文档自身（`agent/tools/documents.py:1`） | utils.py 唯一引用者是死代码 documents.py；四者仍无人 import
- 10 | 第4节-2 | STILL | `webui_py/main.py:78-79` `drop_index("unique_event_binding_route")`；`manager_webui/main.py:85-87` `drop_index("unique_workflow_key")` + `update_many({"key":{"$exists":True}},{"$unset":{"key":""}})` | 启动期迁移代码仍在
- 11 | 第4节-3 | STILL | `agent/llm.py:58` `print(resp.json())`；`:30` `with MongoClient(**mongo_kwargs)` 每次新建；`:56` `return 402,None,None` 混型（`:75` 用 `content==402` 判） | 三条都成立
- 12 | 第4节-4 | STILL | `agent/llm.py:8` `from tools.tool import registered_tools` → `agent/tools/tool.py:33` import 期 `redis_reset_tools()`；`:10-24` 硬索引 DEEPSEEK_*/KIMI_*/ZAI_API_KEY/TAVILY_API_KEYS/BOCHA_* 共 8 个 env | 缺任一键即阻断启动
- 13 | 第4节-5 | STILL | `tool_server/main.py:142` `await redis.lrem(processing, 1, item)`、`:146` 同 | 按值删除处理中条目，重复负载会删错
- 14 | B1 | STILL | `manager_webui/static/workflow_canvas.mjs:54-101` contractPortIds 无 map_content_get/construct_map_content/deserialize_json 分支（落到 `:100 return []`）；`:61` construct_message 缺 `role-in`；`:26-34` CONNECTION_COLORS 缺 map-content；`:5-24` TYPE_COLORS 缺 construct_map_content/map_content_get/deserialize_json 三色 | 与 agent contract 对照仍过期
- 15 | B3 | STILL | `agent/Dockerfile:6` 装 ffmpeg；`agent/requirements.txt:4-5` ffmpeg-python/pydub；agent/ 下 grep `ffmpeg|pydub|AudioSegment` 零命中 | 真正使用方是 tool_provider（`tool_provider/Dockerfile:6`、`tool_provider/tools/bilibili.py:7,90`）
- 16 | B5 | STILL | `workflow_editor/static/workflow/inspector/structure.js:190` deserialize_json 输出类型 `<select>` 的 option 只有 content/message/event/list-content/list-message/list-event | 缺 map-content
- 17 | B7 | STILL | `.env.example:37`=2 / `docker-compose.yml:204`=5 / `tool_provider/main.py:25`=3；`.env.example:41` `TOOL_MODULES=tools.qq,tools.bilibili`（缺 tools.system，compose:208 与 main.py:18 有）；`agent/Dockerfile:1`、`qqbot/Dockerfile:1`、`qqbot_consumer/Dockerfile:1` = python:3.11-slim-bookworm，其余 5 个服务 = python:3.12-slim；agent/qqbot/qqbot_consumer/tool_provider 的 requirements 未锁版本 | 与报告不同处：qqbot、qqbot_consumer 也是 3.11（不是"仅 agent"）
- 18 | B8 | STILL | `agent/tools/1.py` 存在（269 行 B 站搜索草稿，无 `@tool`、全仓零引用）；`agent/downloaded/` 存在（glob 计数 174 个 .m4s/.mp3） | 体积无法统计：pwsh 被沙箱阻断
- 19 | 第5节 | NEEDCHECK | 夹具已改：`agent/test_tool_nodes.py:19-23` local_tool 输出端口为 `"output"`、`:69/84/95/117/128/139` 用例名已改为 local_tool/remote_*；`agent/test_workflow_node.py:263` 已有 `test_validator_and_parser_accept_map_content_nodes`，其 `:299` 调 validate_workflow | "当前红绿"必须实跑：本次无法运行测试（pwsh 被阻断）；静态可证 `test_workflow_node.py:263`（A1 KeyError）与 `test_tool_nodes.py:240` `assertEqual(SUPPORTED_NODE_TYPES, set(NODE_ARGUMENT_FIELDS_BY_TYPE))` 必失败，其余用例状态未知
- 20 | 第6节 | FIXED | 六个文件全部存在：`agent/test_workflow_node.py`、`agent/test_task_worker.py`、`agent/test_tool_nodes.py`、`agent/test_workflow_context_repository.py`、`agent/test_workflow_session_repository.py`、`agent/test_history_repository.py` | 存在性满足

## 组 2

- 21 | F-01 | FIXED | `agent/workflow_nodes.py:131` `chat_with_model(messages, node_argument(node,"model"), tools=tools)`；`agent/llm.py:11-36` `_model_config(model_id)` 从 `MONGO_MODEL_COLLECTION`（默认 models）取 `config["model"]/base_url/api_key` 再调 `openai_llm_api` | 已按节点 model 解析，不再走 `chat_with_deepseek` 进程级 env
- 22 | F-02/R1 | **FIXED** | ~~`agent/task_worker.py:89` `output = run_workflow_map(...)` 无 try/except（唯一 error 事件在 `:61-64` 的 workflow not found）；`agent/workflow_nodes.py:67-87` 只有 try/finally（finally 仅清 Context）~~ | **2026-10-12 已修复**：`agent/task_worker.py:114-124` 在单任务边界捕获异常并发布 `error`（payload `{message}` + 存在时的 `workflow_id`）后再上抛；外层 print + `sleep(2)` 仅作日志兜底；处理 `error` 事件自身失败时不重复发布
- 23 | F-04/第3节-6 | STILL | 同第 8 条：`agent/workflow_nodes.py:31` 用 `is not None`；`agent/llm.py:59-61` 不归一化 None/""；`agent/workflow_nodes.py:130-142` 两类输出空值语义不一致 | 未修
- 24 | F-03/R2 | GONE | 全仓 .py grep `rpc_apply|rpc_review` 零命中；`agent/task_worker.py:43-93` 只有 workflow 分支，无这两个处理器；`qqbot_consumer/llm.py` 不存在（该目录只剩 queue_consumer.py/history_repository.py/queue_client.py）| 回发链整体消失
- 25 | H-01/A-01 | STILL | `qqbot/queue_client.py:19` publish=lpush、`qqbot_consumer/queue_client.py:25` pop=blpop（栈序，与先入先出相反）；`agent/queue_client.py:33` lpush + `:65` brpop（FIFO）| 子队列方向仍错配
- 26 | H-02 | STILL | `webui_py/main.py:72-125`、`workflow_editor/main.py:21-83` 无鉴权依赖、无 CORSMiddleware、无限流中间件（只有安全响应头/日志/长度守卫）；`docker-compose.yml:86-87` `8081:8081`、`:151-152` `8082:8082` 仍发布 | 三处均无变化
- 27 | H-03 | STILL | `manager_webui/models.py:32` `"api_key": document.get("api_key","")`，`:51-55` GET /api/models 直接返回该结构 | 明文回显；对照 `workflow_editor/main.py:89` 的 /api/models 只投影 name/model/provider
- 28 | H-04/W1 | STILL | 见第 5 条：`manager_webui/workflows.py:793-817` 的保存面规则集合仍小于 `agent/workflow_validator.py:154-398`
- 29 | H-05/A-06 | STILL | 两套独立实现：`agent/workflow_contract.py:231-354` is_valid_connection vs `manager_webui/workflows.py:308-451` filter_invalid_connections（`:451` 静默过滤）
- 30 | H-06/A-03/R5 | MOVED | agent 侧死链已消失：全仓 .py 无 `active`/`tool_excute` 事件分支、无 active()、无 max_context_count 引用；`system_documents_prompt` 只剩定义 `agent/tools/documents.py:166` 零调用；但前端特判仍在 `webui_py/static/render.js:45-47` `if (item.event?.event_type === 'active') return '请求 LLM 处理'`
- 31 | H-07/R6 | STILL | `agent/task_worker.py:45` `event_type = e["event_type"]` 无条件取（缺键即 KeyError）；`:46-53` 非 workflow 事件查绑定，无绑定直接 return | 未知类型现在静默丢弃不报错（不再是 TypeError），但仍无诊断
- 32 | H-08 | STILL | `webui_py/events.py:393` `redis_client.rpush(queue_name, ...)` 直写队列，未复用 queue_client（agent 侧 `lpush`+`brpop`，rpush 会径直落到消费端）| 仍插队
- 33 | M-01/R4 | STILL | `agent/task_worker.py:34` `with MongoClient(**mongo_kwargs) as client` 每次建连；`agent/workflow_parser.py:139` `with MongoClient(...)` + `:150` find_one 全量读 | 两处都无进程内 client 复用/缓存
- 34 | M-02/R3 | MOVED | 事件仍全量落库无体积控制：`agent/task_worker.py:44` 与 `qqbot_consumer/queue_consumer.py:21` `record_history`，`agent/history_repository.py:50-55` 整条 insert；但"逐节点事件携带完整 workflow_map"已不存在——`agent/task_worker.py:49-52` 只发 `{"event_type":"workflow","payload":{...payload,workflow_id}}`，全仓无发布 workflow_map 的代码
- 35 | M-03/M-04 | MOVED | 节点表已无 `tool_call`/`workflow_tool_call`（`agent/workflow_contract.py:17-42`、`agent/workflow_nodes.py:577-602`），"workflow_tool_call 外层 JSON 解析"对象不存在；但失败语义仍不对称：local_tool → `agent/tools/tool.py:169-171`（未知工具返回字符串、不抛）vs remote_* → `agent/workflow_nodes.py:399-407` 捕获 ToolServerError 后抛 ValueError(JSON)
- 36 | M-05 | STILL | `agent/workflow_nodes.py:354-359` `next_successor(node, f"branch-{key}")`（`:47-53` 无后继即 ValueError）；`agent/workflow_parser.py:97-107` 生成 `branch-{name}`；`agent/workflow_validator.py:195-223` 只查 branches 非空/唯一，不要求兜底分支
- 37 | M-06/R7 | STILL | `agent/task_worker.py:86` `e['payload'].get(port['name'])` 端口名不匹配仍静默传 None，入口无校验 | 但 workflow_llm 已明确报错：`agent/workflow_nodes.py:107-111`（缺 messages-in / 空列表 / 非法消息均 raise）
- 38 | M-07 | STILL | `agent/tools/tool.py:33` 模块顶层 `redis_reset_tools()`（import 即 delete `aagent:tools`），`:52` 再逐个 hset
- 39 | M-08 | GONE | 全仓 .py grep `initialize_settings|set_settings|read_settings_file` 零命中；`agent/queue_client.py:1-69` 已无任何设置覆盖逻辑
- 40 | M-09 | MOVED | 缺陷只剩在死代码 `agent/tools/documents.py`（无人 import）；活代码 `tool_provider/tools/documents.py` 已重写：`:40-44` `_find_document` 有 None 检查、`:179/209/240` `ReturnDocument.AFTER`、`:97-98` 结构化返回、无 list_documents、无 MAX_DOCUMENT_BODY_BYTES
- 41 | M-10/R8 | FIXED | `agent/history_repository.py:57-61` `get_recent_history(limit=10, query: dict | None = None, event_types=None)`，`:65` `dict(query or {})`；`qqbot_consumer/history_repository.py` 已无该函数
- 42 | M-11/W3 | STILL | `webui_py/main.py:117-124` 与 `manager_webui/main.py:134-141` 均只读 `content-length` 头，无头即放行 | 分块传输可绕过
- 43 | M-12 | FIXED | `workflow_editor/static/workflow/domain/serialization.js:230-233` construct_list 端口按 `${item_type}-in-${index}` 生成，全仓静态资源 grep `message-in-` 零命中 | content-in→message-in 静默改写已不存在
- 44 | M-13/A-07 | STILL | 至少 6 份副本：`agent/workflow_contract.py:17-75`、`manager_webui/workflows.py:22-51`、`workflow_editor/static/workflow/domain/node-contract.js:3-28`+`:48-244`、同目录 `serialization.js:12-40`、`connection-rules.js:13`、`manager_webui/static/workflow_canvas.mjs:5-101`（另有 `inspector/structure.js:190` 类型枚举）
- 45 | M-14 | STILL | `workflow_editor/static/workflow.js:569-572` `new URLSearchParams(window.location.search).get('workflow')` 后直接 `importWorkflowText(workflowParameter, '已从 URL 导入')` | 整份 Workflow JSON 仍走查询串
- 46 | M-15/D1 | STILL | `agent/.dockerignore:1-6` 仅 __pycache__/*.py[cod]/.env/.git*，未排除 `downloaded/`、`test_*.py` | `settings.json` 已不存在（glob `**/settings*.json` 零命中），该子项自动失效
- 47 | M-16/A-11/N20/A33/B7 | STILL | 基镜像两组：agent/qqbot/qqbot_consumer = python:3.11-slim-bookworm（各自 Dockerfile:1），webui_py/manager_webui/workflow_editor/tool_server/tool_provider = python:3.12-slim；未锁版本：`agent/requirements.txt:1-5`、`qqbot/requirements.txt:1-3`、`qqbot_consumer/requirements.txt:1-2`、`tool_provider/requirements.txt:3-5`（requests/pydub/pymongo），其余 4 个服务全 `==`
- 48 | M-17 | STILL | 全仓只有 4 个 .dockerignore（`agent/`、`qqbot/`、`webui_py/`、`manager_webui/`）；缺 `workflow_editor/`、`tool_server/`、`tool_provider/`、`qqbot_consumer/`
- 49 | M-18/A14 | STILL | `qqbot/listener.py:17-43` parse_event 只按 `user_id` 是否存在投递、不校验发送者；`:23-30` 仍把 input_status 转成 `post_type="inputing"` 投递；`qqbot_consumer/queue_consumer.py:21` `record_history(event)` 对所有事件无条件落库
- 50 | M-19 | MOVED | `tool_provider/tools/bilibili.py:94-103` `_asr` 仍硬编码 `https://frp-dry.com:63030/`（`:97`）；`DASHSCOPE_API_KEY` 占位符默认值已不存在（全仓 grep 只命中文档，`.env.example` 亦无该键）
- 51 | M-20/M-21/M-22/A18/A-10 | STILL | 三个 get_connection 都不读 REDIS_PASSWORD：`agent/queue_client.py:22-28`（有 socket_timeout=30）、`qqbot/queue_client.py:13-14`、`qqbot_consumer/queue_client.py:13-14`（后两者连 socket_timeout 都没有）| compose 只在 `docker-compose.yml:173` 给 tool_server 显式注入；三者靠 `env_file: .env`（`:12-13`/`:31-32`/`:48-49`）拿到该变量但客户端不读
- 52 | L-01/A2 | GONE | `agent/command.py` 不存在（glob agent/** 无此文件，全仓 grep 无源码命中）
- 53 | L-02/R9 | MOVED | `agent/2.py`、`agent/3.py` 已不存在；`agent/tools/1.py` 仍在（269 行）
- 54 | L-03/A17 | MOVED | print 仍在 `agent/llm.py:58`；`qqbot_consumer/llm.py` 与 `agent/tools/bilibili.py` 均已不存在（后者逻辑迁至 `tool_provider/tools/bilibili.py`，无 print）
- 55 | L-04/W5 | STILL | `workflow_editor/main.py:81-83` `def health(): return {"status":"ok"}` 不探测依赖（对比 `webui_py/main.py:128-134` ping Redis、`tool_server/main.py:180-186` ping Redis+Mongo）
- 56 | L-05/N6a/N6b | MOVED | `chat_with_llama_cpp` 已不存在（全仓 .py 零命中）；`agent/task_worker.py` 已无 tool_return/response/rpc_review 处理器；`bocha_search` 死代码仍在 `agent/tools/tool.py:150`（无 `@tool`、零调用）
- 57 | L-06 | GONE | `agent/settings.example.json` 不存在（glob `**/settings*` 只命中 `tool_server/settings.py`）| `system_prompt` 投影本身也已从代码消失（全仓 .py grep `system_prompt` 零命中）
- 58 | L-07 | STILL | `webui_py/events.py:48-61` 自实现 FNV-1a 变体（offset basis 1469598103934665603、prime 1099511628211、base36 输出）
- 59 | L-08/L-09/W2 | STILL | `manager_webui/workflows.py:638-655`（PATCH）与 `:930-948`（PUT）：级联 `$set` 内含 `updated_at`（`:649`/`:942`）刷新引用方；一条 update_many 同时带 `workflow_nodes.$[reference].name` 与 `nodes.$[node].arguments.workflow_name` 两个 arrayFilters（`:651-654`/`:944-947`）；主 `find_one_and_update` 与级联 `update_many` 分两次、无事务
- 60 | L-10 | STILL | `manager_webui/workflows.py:793-817` 只校验节点 id 唯一、类型合法、至少一个 output（`:810`），无"恰好一个 input"（agent 侧 `agent/workflow_validator.py:72-76` 有）
- 61 | L-11 | STILL | `agent/llm.py:38` `def openai_llm_api(messages,model,url,key,tools=registered_tools,extra={})` 仍可变默认参
- 62 | N1 | FIXED | `qqbot_consumer/queue_consumer.py:24-29` 仅当 `post_type=='message'`、无 group_id 且 `user_id == QQ_TARGET_USER_ID` 才 publish 到主队列；未授权消息只落 `qq_event_history`（`:21`），不再进入 LLM 上下文（旧 active 投影整体删除）
- 63 | N3 | GONE | `response→tool→tool_return→active` 链不存在（全仓 .py 无 tool_return/active），迭代上限保护无对象
- 64 | N11 | STILL | `agent/tools/tool.py:168-171` `handler is None → return f"未知工具: {tool}"`（返回字符串而非抛错），`:173-180` 一律 `str(result)` 成"成功结果"
- 65 | N12/A1 | STILL | 请求异常在 `agent/llm.py:46-57` 直接上抛 → `agent/workflow_nodes.py:130` 无捕获 → `agent/task_worker.py:119-122` 只 print + sleep(2) | 事件已 `record_history`；**2026-10-12 起不再“无 error 事件”**（`agent/task_worker.py:114-124` 会发 `error`），但仍不重试、不重新入队
- 66 | N13 | MOVED | `agent/llm.py:55-56` 402 返回 `(402,None,None)`，`:75-76` 归一成 content 字符串 `"[-]余额不足"` 走正常 response 路径 | 无独立 error 事件、无 QQ/终端定向回推，只是不再静默丢
- 67 | N14 | GONE | 全仓 .py 无 `setting` 事件类型/handler（agent 侧 grep `setting` 零命中，webui_py 无 settings 路由）| 待校验对象不存在
- 68 | N4 | GONE | `agent/prompt/` 目录不存在；仓库根 `skills/` 存在（.txt/.md），但全仓 .py/.js/.yml grep `skills` 零命中 | 无消费者
- 69 | A3 | STILL | `agent/tools/qqapi.py` 六个函数全是裸 `res.raise_for_status()`（`:19,29,48,57,67,81`）；`agent/tools/tool.py:66-69` deepseekBalance、`:79-82` kimiBalance 无 try/except | 该模块在 agent 内无 import（tool_provider 有自己的 tools/qqapi.py）
- 70 | A4 | STILL | `agent/task_worker.py:107-111` processing 只写 state/event/started_at；updated_at 只在 idle 时写（`:100-103`、`:115-118`）| 处理期间不刷心跳
- 71 | A5 | STILL | `agent/queue_client.py:32,37,43,50,55,64` 每次 `get_connection()` 新建 client；`qqbot/queue_client.py:18,24`、`qqbot_consumer/queue_client.py:18,24,33` 同 | 无模块级复用
- 72 | A6 | STILL | `agent/tools/tool.py:16` `os.environ["ZAI_API_KEY"]`、`:23` `os.environ["BOCHA_BASE_URL"]`、`:24` `os.environ["BOCHA_API_KEY"]` import 期强读；`agent/llm.py:8` 导入即触发 | 缺键 KeyError 阻断启动
- 73 | A7 | STILL | `agent/task_worker.py:96-122`、`qqbot_consumer/queue_consumer.py:35-50` 无 Redis 锁/租约/worker 标识，只写状态键
- 74 | A8 | STILL | 事件无唯一 ID/幂等：`webui_py/events.py:387-391` terminal 事件只有 event_type/time/payload；`agent/history_repository.py:50-55` 逐条 insert 无去重键；`event_fingerprint` 仅前端展示用
- 75 | A9 | STILL | 无"LLM 回复自动发 QQ"路径：回复经 `agent/task_worker.py:90-93` 落 response 事件回主队列，只有 workflow 绑定 + `tool_provider/tools/qq.py:8,38`（qq.send_*）才会真正发出
- 76 | A10 | STILL | `agent/tools/qqapi.py` 6 个函数共用同一 requests 模板（`:13-20/:23-30/:34-49/:52-58/:61-68/:71-82`）；模块外零调用点，其中 send_private_img/get_group_list/get_group_member_info/get_group_msg_history 全为未使用函数
- 77 | A11 | STILL | `qqbot/queue_client.py:23-29` pop_from_queue（blpop）在 qqbot/ 内零调用（`qqbot/listener.py:7` 只 import publish_to_queue），且与 publish 的 lpush 方向相反
- 78 | A12/A13 | FIXED | schema 与 handler 在同一装饰器内注册：`agent/tools/tool.py:36-55`（registered_tools 与 tool_handlers 同时写）；执行是字典查表 `:169`，非长 if-elif；命令分发文件 `agent/command.py` 已删除
- 79 | A15 | GONE | 全仓 .py grep `"context"`/`'context'` 在事件载荷零命中；两处发布 response 只带 content：`agent/task_worker.py:90-93`、`agent/tools/tool.py:129-135`
- 80 | A16 | STILL | `agent/tools/tool.py:68` 返回 `response.json()['balance_infos'][0]['total_balance']`（原值）vs `:81` `str(response.json()['data']['available_balance'])`
- 81 | A19-A26 | STILL | 全部在 `agent/tools/documents.py`（死代码）：`:108/:134` `return_document=return_final`（布尔）；`:186-192` rename 未取 AFTER → 返回旧标题；`:111/:137` `return str(res)`（None 或更新前 dict）；`:67-73` 与 `:76-84` 无 None 检查；`:47` 未命中返回 ""；`:161` `find()` 无投影全表扫；`:12` MAX_DOCUMENT_BODY_BYTES 零引用；`:76-84` document_wrapper 与 `:65-74` query_document_by_id 重复 | 活代码 `tool_provider/tools/documents.py` 已逐项修正
- 82 | A27/A28 | MOVED | A27 的 `import tools.qq` 副作用注册已不存在（agent 无 tools/qq.py、全仓 .py 无该 import；改为 `tool_provider/main.py:15-21` 按 TOOL_MODULES 显式加载）；A28 仍成立：`agent/tools/` 无 `__init__.py`（全仓 glob `**/__init__.py` 零命中）
- 83 | A30 | STILL | `agent/tools/tool.py:168` `def execute_tool(id,tool,args)`，函数体 `:169-180` 未引用 id（调用方 `agent/workflow_nodes.py:381` 传 `node["id"]`）
- 84 | A31 | STILL | `agent/llm.py:61` `reasoning=res.get('reasoning_content') if res.get('reasoning_content') else ""`（`:60` tool_calls 同构）| 仍可简化
- 85 | A32 | STILL | `qqbot_consumer/history_repository.py:25` 创建 `created_at_desc` 索引，模块内只有 record_history（`:30-32`），全仓无按 created_at 查询/排序的调用
- 86 | A34 | FIXED | agent/ 下 grep ` +$` 未命中 `agent/task_worker.py`（只命中 `agent/llm.py:77`、`agent/tools/documents.py:161,163,170`）
- 87 | A35 | STILL | `webui_py/events.py:389` 写入信封 `"time": ...Z`，但前端只消费 created_at（`webui_py/static/render.js:53-59` eventTime 用 started_at/created_at）| 全仓无读取事件 time 字段的代码
- 88 | A36 | GONE | `agent/settings.json` 与 settings.example.json 均不存在（glob `**/settings*` 只命中 `tool_server/settings.py`）
- 89/A40 | GONE | 目标 `docs/02-事件与队列.md`、`docs/03-模块详解.md` 已移入 `docs/废弃旧文档/`；且"投影在 active 分支"的代码对象已删除
- 89/N5 | GONE | docs/03、06、07 均在 `docs/废弃旧文档/`；代码侧 `get_recent_history(limit=16)` 已不存在（`agent/workflow_nodes.py:346-349` 用节点参数）
- 89/N8 | GONE | docs/01、02、03、06 已移入 `docs/废弃旧文档/`（`01-系统架构.md`、`02-事件与队列.md`、`03-模块详解.md`、`06-格式规范.md`）
- 89/N9 | GONE | docs/03、05、06 已移入 `docs/废弃旧文档/`
- 89/N10 | GONE | docs/02 已移入 `docs/废弃旧文档/`
- 89/N22 | GONE | docs/01 已移入 `docs/废弃旧文档/`
- 89/N23 | GONE | docs/01 已移入 `docs/废弃旧文档/`
- 89/M1 | GONE | docs/00-08 全部在 `docs/废弃旧文档/`（glob 确认 00,01,02,03,04,05,06,07,08 均在）
- 89/M2 | GONE | `docs/13-Workflow解析器.md` 已移入 `docs/废弃旧文档/`
- 89/M3 | GONE | docs/01、docs/04 均已移入 `docs/废弃旧文档/`
- 89/M4 | GONE | docs/04 已移入 `docs/废弃旧文档/`；且 `.env.example` 不再需要 `QQ_AGENT_SETTINGS_KEY`（全仓无该变量）
- 89/N15 | STILL | `docs/审查日志/2026-08-05-agent-问题汇总.md:12` 仍写"文档索引经 `{{DOCUMENTS_INDEX}}` 接入 system prompt"；该文件仍是活文档（未归档），而代码里两个占位符都已不存在
- 89/N16 | GONE | `docs/HarnessEngeneering/` 已不存在（docs/** glob 无该目录）
- 89/N17 | FIXED | `README.md` 全文已无指向 `docs/审查日志/2026-08-02-审查核验汇总.md` 的链接（grep `审查核验汇总|2026-08-02|docs/审查日志` 零命中）
- 89/N21 | STILL | `.gitattributes:9-10` 仍写 `webui/static/app.js`、`webui/sync-test.js`（实际前端在 `webui_py/static/`，后者文件不存在）

## 核验边界

- **pwsh 完全不可用**：本会话每次 shell 调用都在沙箱配权限阶段失败（`SetNamedSecurityInfoW failed (Win32 5): grantWrite(D:\AAgent)`），因此 (a) 无法统计 `agent/downloaded/` 体积（第 18 条只能给 glob 文件数 174）；(b) 无法运行任何测试；(c) `NeedCheck` 只能靠静态推断。
- **判了 NEEDCHECK 的条目**：仅第 19 条。理由：夹具与用例名已静态确认改到位，但"`test_validator_and_parser_accept_map_content_nodes` 当前是红是绿"是运行期事实，必须实跑 `python -m unittest`；静态可证 `agent/test_workflow_node.py:263`（经 A1 的 KeyError）与 `agent/test_tool_nodes.py:240`（`SUPPORTED_NODE_TYPES != set(NODE_ARGUMENT_FIELDS_BY_TYPE)`）必然失败，其余用例状态未知。
- **其他"需要实测但已按静态判定"的点**（未判 NEEDCHECK，仅提示）：第 3 条中 ValidationError 逃逸后 WebSocket 的具体关闭码由 Starlette 版本决定（"jsonschema.ValidationError 不是 ValueError"这一点已按上游 jsonschema==4.25.1 的 exceptions.py 源码核实）；第 4 条 StopIteration 竞态需要真实并发时序才触发；第 59 条 arrayFilters 双路径的实际写入行为需要真实 MongoDB。
- **本次没有读到的文件/对象（glob/grep 确认其不存在，而非未查）**：`agent/command.py`、`agent/2.py`、`agent/3.py`、`agent/prompt/`（含 skills/)、`agent/tools/qq.py`、`agent/tools/bilibili.py`、`agent/settings.json`/`settings.example.json`、`qqbot_consumer/llm.py`、`docs/HarnessEngeneering/`、全仓任何 `__init__.py`、`**/settings*.json`。
- **文档类条目（第 89 条）的取证方式**：待核验清单只给了编号，未给原文，因此先读了 `docs/审查日志/2026-08-06-全项目review-审计报告.md`（N5、N8~N23 定义，行 45/52-61/67-73）与 `docs/审查日志/2026-09-13-全项目-审查报告.md`（M1~M4 定义，行 33/44/45/59）确定各编号含义，再打开目标文档本身判定；判定依据是目标文档的当前位置与内容，未用报告的描述当结论。
