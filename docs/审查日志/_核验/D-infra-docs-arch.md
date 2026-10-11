# D 组核验：部署与配置 / 架构决策清单 / 文档漂移

> 类型:核验记录。
> 性质:现行文档。
> 归属:`基础设施` + `文档自身`。
> 适用版本:平台 `0.1.0+`。

> 日期:本次会话。
> 性质:核验记录（不是新审查报告）。
> 基准:**当前工作区源码**（compose、Dockerfile、requirements.txt、.dockerignore、.env.example、.gitattributes、docs/、各服务 main.py）。报告中引用的行号一律为本次实际读到的行号;历史报告行号已失效,不引用。
> 特别说明:原 `docs/00`~`docs/16` 编号文档**已全部移入 `docs/废弃旧文档/`**（`docs/` 根目录现存编号文档只有 17~26）。按口径,移入 `废弃旧文档/` 的文档视为 `GONE`。
> 未修改任何非 `_核验/` 下的文件;未启动容器。

---

## 组 1：部署与配置（来自 2026-09-14 报告）

- `1 (A-09 / M-08)` | GONE | `agent/` 下已无 `initialize_settings()` / `set_settings()` / `read_settings_file()`（全仓 `*.py` 零命中），`agent/settings.json` 与 `agent/settings.example.json` 均不存在，入口 `main()` 现在只在 `agent/task_worker.py:96-122`（事件循环，无任何设置初始化） | 整条「本地文件无条件覆盖 Redis 设置」链路随 System Prompt/设置功能一起被移除,权威来源之争自动失效
- `2 (A-10 / M-21 / M-22 / A18)` | STILL | `agent/queue_client.py:22-28` `get_connection()` 只传 host/port/decode_responses/socket_timeout,**不读 `REDIS_PASSWORD`**;`qqbot/queue_client.py:13-14` 与 `qqbot_consumer/queue_client.py:13-14` 只传 host/port/decode_responses,**连 `socket_timeout` 都没有**;`docker-compose.yml:170-174` 只有 `tool_server` 的 `environment` 注入 `REDIS_PASSWORD`/`REDIS_DB` | 三服务连客户端都不读密码,一旦给 Redis 加 `requirepass`（现 `docker-compose.yml:224` 的 `redis-server --appendonly yes` 无 `requirepass`）就整链断开,而 4 个 WebUI/Tool 服务正常;详见下方 Redis 参数表
- `3 (A-11 / M-16 / M-17 / N20 / A33 / B7)` | STILL | 基镜像 `agent`/`qqbot`/`qqbot_consumer` = `python:3.11-slim-bookworm`（各自 Dockerfile:1）vs 其余 5 个 = `python:3.12-slim`;`agent/requirements.txt:1-5` 与 `qqbot/requirements.txt:1-3`、`qqbot_consumer/requirements.txt:1-2` 全部无版本号;`.dockerignore` 只有 4 份（`agent/`、`qqbot/`、`webui_py/`、`manager_webui/`），`qqbot_consumer`/`workflow_editor`/`tool_server`/`tool_provider` 仍缺;`TOOL_PROVIDER_REVISION` 三处不一致：`.env.example:37`=2 / `docker-compose.yml:204` 默认 5 / `tool_provider/main.py:25` 默认 3;`.env.example:41` `TOOL_MODULES=tools.qq,tools.bilibili` 确实**不含 `tools.system`**（compose:208 与代码 `tool_provider/main.py:18` 默认含） | 逐服务明细见下方构建/依赖表
- `4 (M-15 / D1 / B8)` | STILL | `agent/.dockerignore:1-6` 只有 `__pycache__/`、`*.py[cod]`、`*$py.class`、`.env`、`.git/`、`.gitignore`——**未排除 `downloaded/`、`test_*.py`**;`agent/Dockerfile:12` 仍是 `COPY . .`;`agent/downloaded/` 仍存在（glob 实测 **174 个文件**,`*.m4s`/`*.mp3`）;`agent/requirements.txt:4-5` 仍带 `ffmpeg-python`/`pydub`、`agent/Dockerfile:5-7` 仍装 `ffmpeg`,而全仓 `ffmpeg`/`pydub` 的**代码使用点只有 `tool_provider/tools/bilibili.py:7,90`**,`agent/` 零使用 | `settings.json` 与 `agent/2.py`、`agent/3.py` 已不存在,该子项自动失效;但 `agent/` 下仍有 4 个 `test_*.py` 会被打进镜像。**`downloaded/` 的字节总量无法核实**：本次会话 Windows 沙箱的 pwsh 一律以 `SetNamedSecurityInfoW failed (Win32 5): grantWrite(D:\AAgent)` 失败,取不到 `Measure-Object` 结果（见「核验边界」）
- `5 (M-19)` | STILL | `tool_provider/tools/bilibili.py:94-103` 的 `_asr()` 仍把端点写死为 `"https://frp-dry.com:63030/"`（:97）,全仓无 `ASR_URL` 读取方（`.env.example:55` 的 `ASR_URL` 是死配置,与代码无任何连接） | 子项「`.env.example` 未定义 `DASHSCOPE_API_KEY`」事实成立（`.env.example` 全文 56 行无该键）,但**该子项已失效**：全仓 `*.py` 零处读取 `DASHSCOPE_API_KEY`,`qwen3asr`/占位符 Bearer 的旧代码已不存在。端点仍未移入环境变量,故整条判 STILL
- `6 (M-20 / M-4 / N7)` | STILL | 实测对账：代码读取但 `.env.example`（56 行）未声明的键 **12 个**——`REDIS_ADDR`、`REDIS_URL`、`MONGO_EVENT_BINDING_COLLECTION`、`MONGO_SESSION_COLLECTION`、`MONGO_TOOL_TASK_LOG_COLLECTION`、`TOOL_SERVER_URL`、`TOOL_SERVER_WS_URL`、`TOOL_CLIENT_DEFAULT_ASYNC_TIMEOUT_MS`、`WORKFLOW_CONTEXT_TTL_SECONDS`、`WORKFLOW_CONTEXT_MAX_VALUE_BYTES`、`WORKFLOW_SESSION_MAX_VALUE_BYTES`、`BILIBILI_DOWNLOAD_DIR`;`.env.example` 中已无读取方的**死配置 4 个**：`DEEPSEEK_MODEL`（:3）、`QQ_BOT_ID`（:17）、`ASR_URL`（:55）、`MODEL_ID`（:56） | 读取位置见下方环境变量对账表。另注:`agent/tools/tool.py:10-24` 用 `os.environ[...]` 硬取 `DEEPSEEK_BASE_URL/API_KEY`、`KIMI_BASE_URL/API_KEY`、`ZAI_API_KEY`、`TAVILY_API_KEYS`、`BOCHA_BASE_URL/API_KEY`,该模块经 `agent/llm.py:8` 被导入,缺任一键会在启动期直接 `KeyError`（这些键都在 `.env.example` 内,故不计入缺口）
- `7 (N19)` | STILL | `docker-compose.yml:239-240` 以 `MONGO_INITDB_ROOT_USERNAME/PASSWORD: ${MONGO_USER}/${MONGO_PASS}` 建 **root**;所有消费方一律用同一 `MONGO_USER`+`authSource=admin` 直连：`webui_py/main.py:60-65`、`manager_webui/main.py:65-69`、`workflow_editor/main.py:42-46`、`agent/history_repository.py:29-34`、`agent/task_worker.py:27-32`、`agent/llm.py:24-29`、`agent/workflow_session_repository.py:111-115`、`agent/workflow_parser.py:130-134`、`qqbot_consumer/history_repository.py:21-22`、`tool_provider/tools/documents.py:20-24` | 全仓检索 `createUser` / `docker-entrypoint-initdb.d` / `initdb`：**零命中**,即没有任何最小权限应用账号的实现;`.env.example:45` 也只是 `MONGO_USER=agent`
- `8 (N21)` | STILL | `.gitattributes:9-10` 仍写 `webui/static/app.js  linguist-vendored` 与 `webui/sync-test.js  linguist-vendored`;`webui/` 目录在仓库中**不存在**（glob `webui/**` 零命中）,glob `**/sync-test.js` 零命中;实际前端在 `webui_py/static/app.js` | 两条 linguist 规则是空指向,不生效
- `9 (D2)` | GONE | 仓库根与全仓 glob `**/*.patch`、`**/backup-before-rollback.patch`：**零命中**,该 110 KB 历史补丁文件已不在工作区 | 问题对象（被 git 跟踪的补丁文件）已不存在
- `10 (L-04 / W5)` | STILL | `workflow_editor/main.py:81-83` 的 `GET /api/health` 仍是 `return {"status": "ok"}` 无条件返回;作为对照,`webui_py/main.py:128-134` 探 Redis、`manager_webui/main.py:145-152` 探 Redis+Mongo、`tool_server/main.py:180-186` 探 Redis+Mongo | `workflow_editor` 是 4 个 HTTP 服务里唯一完全不探依赖的
- `11 (N16)` | GONE | glob `docs/Harness*` 与 `docs/**/*` 全量列举：`docs/HarnessEngeneering/` 目录**不存在**（拼写错误的目录已移除） | —
- `12 (compose 编排核验, 9-13 §2.1 第 7 条)` | STILL | 该条是「已核验结论」不是缺陷,本轮复核**结论仍成立**：正式 compose 的 `redis`（:218-231）与 `mongodb`（:233-249）均**无 `ports`**;8 个应用服务 + 2 个基础设施服务（共 10 个服务）的 `depends_on` 全部为 `condition: service_healthy`（:8-11、:29-30、:44-47、:71-74、:102-105、:136-139、:166-169、:196-198）,4 个 HTTP 服务各有 healthcheck（:88-92、:123-127、:153-157、:184-188）,`redis`（:225-229）与 `mongodb`（:241-247）有 healthcheck;`docker-compose.dev.yml:85-91` 仍暴露 `6379:6379` 与 `27015:27017` | 附注:`agent`/`qqbot`/`qqbot_consumer`/`tool_provider` 自身无 healthcheck,但没有任何服务 `depends_on` 它们,门控链无缺口;`mongodb`（:233-249）没有 `restart:` 键

---

## 组 2：架构决策清单（`docs/审查日志/架构问题汇总.md` A-01 ~ A-11）

- `A-01` | STILL | 队列方向现状：主队列 `agent/queue_client.py:33` `lpush` 入 + `:65` `brpop` 出（FIFO）;QQ 子队列 `qqbot/queue_client.py:19` `lpush` 入 + `:25` `blpop` 出（**LIFO**）;WebUI 终端 `webui_py/events.py:393` `redis_client.rpush(queue_name, ...)` **直写** + 主队列 `brpop`（插队）。`queue_client.py` 仍 **3 份**（`agent/`、`qqbot/`、`qqbot_consumer/`） | 另新增 4 处各自新建 Redis 客户端、同样不在 `queue_client` 内：`webui_py/main.py:47-53`、`manager_webui/main.py:53-55`、`workflow_editor/main.py:28-32`、`tool_server/settings.py:25-32`。`submit_terminal` 仍是 RPUSH 直写（见 `webui_py/events.py:378-396`）
- `A-02` | STILL | 4 个 HTTP 服务全部无鉴权：全仓 `*.py` 检索 `Depends(` / `HTTPBearer` / `Authorization`（作为服务端校验）/ `CORSMiddleware` / `add_middleware` 均**无服务端鉴权命中**（命中的三处 `Authorization` 是出站请求：`agent/llm.py:49`、`agent/tools/tool.py:62,75,107,160`、`tool_provider/tools/qqapi.py:9`、`qqbot/listener.py:11`）;`webui_py/main.py:85/95/109` 只有安全头/日志/请求体上限三个中间件,`manager_webui/main.py:94/104/118` 同构,`workflow_editor/main.py:54/67` 与 `tool_server/main.py:169` 只有安全头/日志;compose 发布 **4 个端口**：8081（:86-87）、8082（:151-152）、8083（:182-183）、8084（:121-122） | 相比 9-14 报告,发布面从 8081/8082 扩到 8081-8084,信任边界问题更大
- `A-03` | MOVED | 死链**已被整体删除**：`agent/*.py` 检索 `active` / `tool_excute` / `handle_map` / `max_context_count` / `<Command>` / `initialize_system_prompt` 全部**零命中**,`agent/task_worker.py:43-93` 只有 `record_history → 读绑定 → 发 workflow → 读 workflow → run_workflow_map → 发 response`;`agent/prompt/` 目录不存在。残留两处：① `webui_py/static/render.js:45-47` 仍保留 `if (item.event?.event_type === 'active') return '请求 LLM 处理'` 特判;② 承载能力的 `system_documents_prompt()` 仍在 `agent/tools/documents.py:166-173`,但全仓无任何模块 import `tools.documents`（`from tools.documents` / `import documents` 零命中）→ 该能力**现在不生效**,与「历史投影」「system_prompt 占位符替换」「`max_context_count`」一样已随 `active` 消失 | 决策点形态已变：原「保留还是删除死链」的选项已被一次性删除解决,剩下的是「render.js 死分支是否清掉」「文档索引进上下文能力是否在 LLM 节点重建」,不再需要二选一决策 → 见文末「不再需要决策」列表
- `A-04` | STILL | `agent/workflow_validator.py` 全文检索 `环`/`cycle`/`循环`/`loop`/`visited`/`SCC`：**零命中**,无环检测;`agent/workflow_nodes.py:56-88` 的 `run_workflow_map` 仍是 `while current_id != WORKFLOW_END:`（:70）,循环体内无迭代计数、无总超时、无轮次上限,`finally` 只做 Context 清理 | 无限环会一直触发 LLM/工具节点
- `A-05` | MOVED | 实测副本数：`queue_client.py` **3 份**（未变）;`llm.py` **1 份**（`agent/llm.py`,原 2 份中的 `qqbot_consumer/llm.py` 已删,只剩 `qqbot_consumer/__pycache__/llm.cpython-311.pyc` 残留）;`history_repository.py` **2 份**（`agent/history_repository.py`、`qqbot_consumer/history_repository.py`）;工具注册表 **2 份**（`agent/tools/tool.py` 的 `tool` 装饰器 + `registered_tools`、`tool_provider/tool.py` 的 `Tool` 抽象基类 + `discover`——两者性质不同） | 另新增第 5 处 Redis 连接封装 `tool_server/settings.py`。分歧仍在（取序相反、`socket_timeout` 有无、密码读取有无）,但「LLM 客户端复制」这一条已消失,故判 MOVED 而非原样 STILL
- `A-06` | STILL | **两套实现都还在**,只是保存侧换了文件：执行侧 `agent/workflow_contract.py:231` `is_valid_connection`（同文件 `:367` 的 `filter_connections` 复用）;保存侧 `manager_webui/workflows.py:308` `filter_invalid_connections`（调用点 `:305`、`:752`、`:910`）。文档/报告写的 `webui_py/workflows.py` **已不存在**（`webui_py/` 下只有 `main.py`/`events.py`/`event_bindings.py`/`common.py`） | **详见 B 组 H-05,本组不重复论证「判定是否相反」**
- `A-07` | STILL | 仍是 **4 份合同副本**,其中一份换文件：① `agent/workflow_contract.py`（`SUPPORTED_NODE_TYPES:17`、`NODE_BASE_FIELDS:44`、`NODE_SHARED_FIELDS:45`、`NODE_ARGUMENT_FIELDS_BY_TYPE:51`）② `manager_webui/workflows.py`（`NODE_BASE_FIELDS:24`、`NODE_SHARED_FIELDS:25`、`NODE_ARGUMENT_FIELDS_BY_TYPE:26`,类型集由 `:803` `set(NODE_ARGUMENT_FIELDS_BY_TYPE)` 充当）③ `workflow_editor/static/workflow/domain/node-contract.js`（`NODE_TYPES:3`）④ 同目录 `serialization.js`（`NODE_BASE_FIELDS:12`、`NODE_SHARED_FIELDS:13`、`NODE_ARGUMENT_FIELDS_BY_TYPE:14`） | `manager_webui/static/workflow_canvas.mjs` 经检索**不是**合同副本（只有 `NODE_WIDTH:1`/`NODE_HEIGHT:2` 等几何常量与 `TYPE_COLORS`）,无需计入第五份
- `A-08` | MOVED | 「业务字段放事件顶层」这一条**已消除**：`rpc_review`/`rpc_apply`/`tool_excute`/`application` 在 `*.py` 中仅剩测试与 `response` 相关命中,`agent/` 侧发布者全不存在;当前主队列事件信封统一为 `{event_type, payload}`（`agent/task_worker.py:49-52,61-64,90-93`、`webui_py/events.py:387-391`、`qqbot/listener.py:24-35`）。**新增**了只读的统一 schema 清单 `manager_webui/event_catalog.py`（7 类：`qq:8`、`terminal:37`、`workflow:64`、`error:91`、`response:117`、`async_result:140`、`raw:171`）,经 `main.py:158` 暴露为 `GET /api/event-catalog`。但它是**描述性清单,不是构造器也不是校验器**：全仓除 `manager_webui/test_event_catalog.py` 外无任何读取方,没有运行时 schema 校验,也没有统一构造器。`time` 字段仍只有 `terminal` 带（`event_catalog.py:49` 声明、`webui_py/events.py:389` 生成）,`workflow`/`error`/`response`/`qq` 都不带 | 决策点形态已变：不再是「格式不统一」而是「有清单无强制」,是否引入统一构造/校验入口仍需决策
- `A-09` | GONE | 同组 1 第 1 条：`initialize_settings`/`set_settings`/`read_settings_file`/`aagent:settings` 在 `*.py` 与 `.env.example`/`docker-compose.yml` 中**全无**;`agent/settings.json` 不存在;`agent/task_worker.py:96-122` 的 `main()` 无任何设置读写 | 「Redis 还是文件为权威」这一取舍的前提（存在文件种子 + 启动覆盖）整体消失,决策不再需要
- `A-10` | STILL | 同组 1 第 2 条 | 见 Redis 参数表
- `A-11` | STILL | 同组 1 第 3 条 | 见构建/依赖表

---

## 组 3：文档漂移

- `13 (A40)` | GONE | `docs/02`、`docs/03` 已移入 `docs/废弃旧文档/`：漂移文字确实还在——`废弃旧文档/02-事件与队列.md:39`「当前 `llm.py` 将 `qq`、`terminal`、`response` 和 `tool_return` 映射到 prompt」、`废弃旧文档/03-模块详解.md:66-68`「## 4. LLM 对话(`llm.py`)」——但该文档已废 | 附带事实：当前 `agent/llm.py:11-36,65-78` 只做「按 model_id 从 Mongo 读模型配置并调用」,**不再做任何事件→消息投影**,投影能力已整体消失
- `14 (A41)` | GONE | `docs/废弃旧文档/00-设计哲学.md:45`「1. 同一时刻最多存在一个 LLM 调用;」文字仍在,但文档已废 | 同类表述在 `废弃旧文档/09-同步架构加速.md:9` 已自行限缩为「同一时刻只能有一个推进权威上下文的决策点」
- `15 (A42)` | GONE | 所述代码不存在：`agent/task_worker.py` 无 `terminal` 分支（全文 126 行只有 `read_bound_workflow_id`/`handle_task`/`main`）,`agent/*.py` 检索 `active` 零命中;`webui_py/events.py:387-391` 现在的 terminal payload 为 `{"content": content, "files": []}`（**非空**） | 「`{"event_type":"active","payload":{}}`」在当前仓库无任何生产者
- `16 (L-06)` | GONE | 全仓 glob `**/settings*.json`：**零命中**（`agent/settings.example.json` 与 `agent/settings.json` 都不存在） | 示例值与实际值不一致的问题随两个文件一起消失
- `17 (M-5 / N5 / N16, 8-06)` | FIXED | 全仓 `*.py` 检索 `limit=16`：**零命中**;`agent/history_repository.py:57-61` 默认 `limit: int = 10`,`agent/task_worker.py` 全文不调用 `get_recent_history`;现有唯一业务调用点 `agent/workflow_nodes.py:343-349` 从节点参数取 `limit` | 被指出的 `docs/03`/`docs/06`（`废弃旧文档/06-格式规范.md:173` 仍写 `get_recent_history(limit=10)`）已移入 `废弃旧文档/`;代码侧的不一致已消失,故判 FIXED
- `18 (N8)` | GONE | 全仓 `*.py` 检索 `user_interface`：**零命中**（已内联进新链路后彻底删除）;仍引用它的 `废弃旧文档/01-系统架构.md:41`、`废弃旧文档/02-事件与队列.md:14,17,79,103`、`废弃旧文档/03-模块详解.md:42,52,64`、`废弃旧文档/06-格式规范.md:33,36,64` 全部已废 | —
- `19 (N9)` | GONE | 工具已在 `tool_provider/tools/`（`system.py`、`qq.py`、`qqapi.py`、`bilibili.py`、`documents.py`）;仍写 `agent/tool.py`/`agent/qqapi.py` 的文档均为废档（`废弃旧文档/03-模块详解.md:10-11`、`05-路线图与创新.md:335`、`06-格式规范.md:9,217`）;当前文档（`docs/17`~`docs/26`、`docs/README.md`、根 `README.md`、`docs/功能全景/`）检索无该路径 | 附带事实：`agent/tools/` 目录**仍残留** `tool.py`/`qqapi.py`/`documents.py`/`1.py`,其中 `documents.py`、`qqapi.py`、`1.py` 在 agent 进程内无 import（`agent/tools/tool.py` 仍被 `agent/llm.py:8` 导入,不是死代码）
- `20 (N10)` | GONE | `docs/废弃旧文档/02-事件与队列.md:51`「`setting --> [*]: 非空 system_prompt 覆盖 prompt 文件`」文字仍在,但文档已废,且 `agent/prompt/` 目录与 `setting` 事件在代码中均不存在 | —
- `21 (N15)` | STILL | `docs/审查日志/2026-08-05-agent-问题汇总.md:12` 仍写「文档索引经 `{{DOCUMENTS_INDEX}}` 接入 system prompt」（活文档、仍在根目录）;而当前 `*.py` 检索 `{{DOCUMENTS_INDEX}}` 与 `{{SYSTEM_DOCUMENTS_PROMPT}}` **两边都是零命中** | 该条实际比原描述更糟：「代码实际为 `{{SYSTEM_DOCUMENTS_PROMPT}}`」这一半也已失效——占位符链路整体不存在,`agent/tools/documents.py:166-173` 的 `system_documents_prompt()` 返回裸字符串、不做任何占位符替换,且无调用方
- `22 (N17)` | FIXED | 根 `README.md` 已整体重写：全文无 `2026-08-02-审查核验汇总` 字样,`:172` 只指向 `docs/README.md`,文档表 `:174-181` 指向 `docs/17`~`docs/21` | 死链已不存在（被指向的 `docs/审查日志/历史/2026-08-02-审查核验汇总.md` 本身仍在归档目录,但已无入口引用）
- `23 (N22 / N23)` | GONE | `docs/01-系统架构.md` 已移入 `docs/废弃旧文档/`（`docs/` 根目录现无 01 号文档）;其 §5 `created_at_desc` 主排序说法、Redis Key 表缺 `aagent:settings`、§2 旧工具路径三条随之失效 | 代码侧事实：`agent/history_repository.py:38-46` 现在只建 `event_type_id` 与 `tool_call_id_payload` 两个索引,**不含 `created_at_desc`**;`aagent:settings` 在代码中不存在。`created_at_desc` 索引仅存于另一集合：`qqbot_consumer/history_repository.py:25`
- `24 (M1)` | GONE | `docs/00`~`docs/08` **全部**在 `docs/废弃旧文档/`（`00-设计哲学.md`、`01-系统架构.md`、`02-事件与队列.md`、`03-模块详解.md`、`04-配置与部署.md`、`05-路线图与创新.md`、`06-格式规范.md`、`07-事件双重身份与信息回调.md`、`08-终端设计.md`）;`docs/` 根目录现存编号文档只有 `17`~`26` | 结论：核验对象已整体归档,「与运行时脱节」自动失效。当前描述 `workflow` 事件的文档为 `docs/20-Event协议与流转.md`、`docs/24-Event绑定与Workflow路由设计.md` 与根 `README.md:93-98`
- `25 (M2)` | GONE | `docs/13-Workflow解析器.md` 已移入 `docs/废弃旧文档/13-Workflow解析器.md`,其 `:14` 仍写「查询条件:   {"key": workflow_key}」,但文档已废 | 运行时代码事实（供参考）：`agent/task_worker.py:57` 用 `_read_workflow(workflow_id, by_id=True)`,即按 `_id` 取
- `26 (M3)` | GONE | `docs/01` 与 `docs/04` 均在 `docs/废弃旧文档/`（`01-系统架构.md:30`、`04-配置与部署.md:63` 仍写 `rainbow_net`,全仓 compose 为 `aagent_net`：`docker-compose.yml:252`） | 当前生效的清单已正确：根 `README.md:102-111` 列出 8081/8082/8083/8084 与 agent/qqbot/qqbot_consumer/tool_provider/redis/mongodb,`:157-168` 目录树列出全部 8 个应用目录 + `docs/`、`data/`。`rainbow_net` 全仓仅存于上列两份废档
- `27 (审查日志/README.md 与 索引.md)` | STILL | 只做存在性核对,**不一致清单**：① `docs/审查日志/索引.md` 通篇未登记 `2026-09-14-全项目-问题报告.md`（该文件在根目录存在,且被 `README.md:11` 指为唯一证据来源）与 `架构问题汇总.md`（根目录存在,被 `README.md:11` 列为权威清单成员）;② `索引.md:3` 元信息「日期:2026-08-06」但正文已登记到 `2026-10-11` 的报告,日期过时;③ `索引.md:9` 章节标题写作「审查/审计快照(历史/)」,而 `:13`~`:21` 登记的 9 份报告实际都在 `审查日志/` 根目录（与其 `:5` 自述「现行于根目录、归档于 `历史/`」自相矛盾）;④ `README.md:15` 与 `:61` 反复称「[权威清单] 三份(问题)汇总」,但 `README.md:7-11` 的权威清单实际列了 **4 份活文档**（3 份领域汇总 + 架构问题汇总） | 已核对**存在**的：`索引.md:22-36` 的 15 条 `历史/` 链接全部命中 `docs/审查日志/历史/` 实际文件;`索引.md:40-48` 的 10 条 `../日志/` 链接全部命中 `docs/日志/` 实际文件;`索引.md:13-21` 的 9 条根目录链接全部命中。另发现相邻死链（`README.md:11` 引用的活文档内）：`架构问题汇总.md:48` 指向 `docs/09-同步架构加速.md`,该文件现位于 `docs/废弃旧文档/09-同步架构加速.md`

---

## 表 1：HTTP 服务（服务名 / 端口 / compose 是否发布 / 有无鉴权 / health 是否探依赖）

| 服务 | 端口 | compose 是否发布 | 有无鉴权 | health 是否探依赖 |
|---|---|---|---|---|
| `webui_py` | 8081 | ✅ `docker-compose.yml:86-87` | 无（`main.py:85/95/109` 仅安全头/日志/体积上限） | 部分：仅 `redis_client.ping()`（`main.py:128-134`）,**不探 Mongo** |
| `workflow_editor` | 8082 | ✅ `docker-compose.yml:151-152` | 无（`main.py:54/67` 仅安全头/日志） | ❌ 无条件 `{"status": "ok"}`（`main.py:81-83`） |
| `tool_server` | 8083 | ✅ `docker-compose.yml:182-183` | 无（`main.py:169` 仅安全头） | ✅ Redis + Mongo（`main.py:180-186`） |
| `manager_webui` | 8084 | ✅ `docker-compose.yml:121-122` | 无（`main.py:94/104/118` 仅安全头/日志/体积上限） | ✅ Redis + Mongo（`main.py:145-152`） |

> 说明：4 个服务均为 FastAPI,均挂载 `StaticFiles`,均无 CORS、无限流、无 Token/依赖注入式校验。

## 表 2：Redis 连接参数（三份 `queue_client` 与 compose 注入）

| 文件 / 服务 | 读 `REDIS_PASSWORD` | 有 `socket_timeout` | 支持 `REDIS_ADDR` | 支持 `REDIS_DB` |
|---|---|---|---|---|
| `agent/queue_client.py` | ❌（`:22-28` 只传 host/port/decode_responses/socket_timeout） | ✅ `:9` 默认 30s,用于 `:27` | ❌ | ❌ |
| `qqbot/queue_client.py` | ❌（`:13-14`） | ❌ | ❌ | ❌ |
| `qqbot_consumer/queue_client.py` | ❌（`:13-14`） | ❌ | ❌ | ❌ |
| `webui_py/main.py` | ✅ `:49` | ✅ `:51-52`（connect 5s / socket 5s） | ✅ `:30-33` | ✅ `:37` |
| `manager_webui/main.py` | ✅ `:54` | —（未读该文件其余行） | ✅ `:35` | ✅ `:42` |
| `workflow_editor/main.py` | ✅ `:31` | — | ✅ `:28` | ✅ `:30` |
| `tool_server/settings.py` | ✅ `:30-31`（还支持 `REDIS_URL:25`） | — | ❌（用 `REDIS_URL` 代替） | ✅ `:29` |
| `tool_provider` | 无 Redis 客户端（只用 `tool_server` WebSocket + Mongo） | — | — | — |
| compose 注入 `REDIS_PASSWORD` | **仅 `tool_server`**（`docker-compose.yml:173`）;`REDIS_DB` 同样仅 `:174` | — | 全 compose 无 `REDIS_ADDR` | — |
| compose `env_file: .env` 透传 | `agent`（`:12-13`）、`qqbot`（`:31-32`）、`qqbot_consumer`（`:48-49`）、`tool_provider`（`:199-200`）——**变量会进容器,但代码不读** | — | — | — |

> 结论：启用 `REDIS_PASSWORD` 时,`agent`/`qqbot`/`qqbot_consumer` 三个服务的客户端**根本不传密码**（与是否注入无关）;当前 `redis` 服务未开 `requirepass`（`docker-compose.yml:224`）,所以是潜伏陷阱。

## 表 3：构建与依赖（服务 / 基镜像 / requirements 是否 pin / 有无 .dockerignore / 是否注入 REDIS_PASSWORD / 是否读 REDIS_PASSWORD）

| 服务 | 基镜像 | requirements 是否 pin | 有无 `.dockerignore` | compose 注入 `REDIS_PASSWORD` | 代码读 `REDIS_PASSWORD` |
|---|---|---|---|---|---|
| `agent` | `python:3.11-slim-bookworm`（`agent/Dockerfile:1`） | ❌ 5 项全部无版本（`requirements.txt:1-5`：pymongo/requests/redis/ffmpeg-python/pydub） | ✅ `agent/.dockerignore:1-6` | ❌ `environment` 无（但 `env_file: .env`） | ❌ |
| `qqbot` | `python:3.11-slim-bookworm`（`qqbot/Dockerfile:1`） | ❌ 3 项无版本（`redis`/`websockets`/`pymongo`） | ✅ `qqbot/.dockerignore:1-6` | ❌（但 `env_file: .env`） | ❌ |
| `qqbot_consumer` | `python:3.11-slim-bookworm`（`qqbot_consumer/Dockerfile:1`） | ❌ 2 项无版本（`redis`/`pymongo`） | ❌ **无** | ❌（但 `env_file: .env`） | ❌ |
| `webui_py` | `python:3.12-slim`（`webui_py/Dockerfile:1`） | ✅ 4 项全 `==`（`fastapi==0.116.1`/`pymongo==4.13.2`/`redis==6.2.0`/`uvicorn[standard]==0.35.0`） | ✅ `webui_py/.dockerignore:1-6` | ❌（无 `env_file`） | ✅ `main.py:49` |
| `manager_webui` | `python:3.12-slim`（`manager_webui/Dockerfile:1`） | ✅ 4 项全 `==`（同上） | ✅ `manager_webui/.dockerignore:1-6` | ❌ | ✅ `main.py:54` |
| `workflow_editor` | `python:3.12-slim`（`workflow_editor/Dockerfile:1`） | ✅ 4 项全 `==`（同上） | ❌ **无** | ❌ | ✅ `main.py:31` |
| `tool_server` | `python:3.12-slim`（`tool_server/Dockerfile:1`） | ✅ 5 项全 `==`（+ `jsonschema==4.25.1`） | ❌ **无** | ✅ `docker-compose.yml:173`（全 compose 唯一） | ✅ `settings.py:30` |
| `tool_provider` | `python:3.12-slim` + `ffmpeg`（`Dockerfile:1,5-7`） | ⚠️ 混用：`jsonschema==4.25.1`、`websocket-client==1.8.0` 有 pin;`requests`/`pydub`/`pymongo` 无（`requirements.txt:1-5`） | ❌ **无** | ❌（但 `env_file: .env`） | 无 Redis 客户端 |
| `redis`（镜像） | `redis:7-alpine`（`docker-compose.yml:219`） | 固定 tag,非 digest | — | —（服务端未设 `requirepass`） | — |
| `mongodb`（镜像） | `mongo:8`（`docker-compose.yml:234`） | 固定 tag,非 digest | — | — | — |

合计：`.dockerignore` **4 份**（agent/qqbot/webui_py/manager_webui）,缺 4 份（qqbot_consumer/workflow_editor/tool_server/tool_provider）。

## 表 4：`.env.example` 对账（56 行）

| 分类 | 键 | 证据 |
|---|---|---|
| 代码读取但模板未声明（12） | `REDIS_ADDR` | `webui_py/main.py:30`、`manager_webui/main.py:35`、`workflow_editor/main.py:28` |
| | `REDIS_URL` | `tool_server/settings.py:25` |
| | `MONGO_EVENT_BINDING_COLLECTION` | `agent/task_worker.py:36`、`webui_py/main.py:45` |
| | `MONGO_SESSION_COLLECTION` | `agent/workflow_session_repository.py:120` |
| | `MONGO_TOOL_TASK_LOG_COLLECTION` | `tool_server/settings.py:45` |
| | `TOOL_SERVER_URL` | `agent/tool_server_client.py:26` |
| | `TOOL_SERVER_WS_URL` | `tool_provider/main.py:23` |
| | `TOOL_CLIENT_DEFAULT_ASYNC_TIMEOUT_MS` | `agent/workflow_nodes.py:437`（默认 600000） |
| | `WORKFLOW_CONTEXT_TTL_SECONDS` | `agent/workflow_context_repository.py:71` |
| | `WORKFLOW_CONTEXT_MAX_VALUE_BYTES` | `agent/workflow_context_repository.py:75` |
| | `WORKFLOW_SESSION_MAX_VALUE_BYTES` | `agent/workflow_session_repository.py:76` |
| | `BILIBILI_DOWNLOAD_DIR` | `tool_provider/tools/bilibili.py:83` |
| 模板声明但全仓无读取方（死配置 4） | `DEEPSEEK_MODEL`（`.env.example:3`）、`QQ_BOT_ID`（`:17`）、`ASR_URL`（`:55`）、`MODEL_ID`（`:56`） | 四个键在 `*.py` 中零命中;`MODEL_ID`/`ASR_URL` 原属已删除的 ASR 链路 |

---

## A-01 ~ A-11 中「因现状已变而不再需要决策」的条目

- **`A-09`（配置权威来源）—— 不再需要决策**：`initialize_settings()` 无条件覆盖 Redis、`agent/settings.json` 文件种子、`aagent:settings` 键、`setting` 事件四者全部不存在,「谁是权威」的取舍前提整体消失。
- **`A-03`（死链 `active` / `tool_excute` 保留还是删除）—— 原决策不再需要**：`active`/`tool_excute`/`rpc_*`/`application` 分支与 `handle_map` 已被一次性删除,运行时上下文已事实上「只由画布决定」,不需要再做「迁移能力后再删」还是「直接删」的二选一。残留的是清理项（`webui_py/static/render.js:45-47` 的死分支）与可选的重建项（`agent/tools/documents.py:166-173` 的文档注入能力是否在 LLM 节点重建),`架构问题汇总.md` 应把它从「待决策」移到「已决策/已关闭」(该文件 `:43` 目前仍写「(暂无)」)。

> 形态已变、但**仍然需要**决策的：`A-05`（副本数下降但仍在复制）、`A-08`（新增了只读清单,但仍无构造器/校验器）。其余 7 条（`A-01`/`A-02`/`A-04`/`A-06`/`A-07`/`A-10`/`A-11`）现状与原描述一致,决策仍然需要。

---

## 核验边界

1. **本次会话 Windows 沙箱的 pwsh 完全不可用**：任何 `pwsh` 调用都以 `Error: SetNamedSecurityInfoW failed (Win32 5): grantWrite(D:\AAgent)` 失败（含把 `workdir` 换到 `C:\Users\...\Temp` 的一次尝试）。因此**所有需要 shell 的只读统计都做不了**,包括 `agent/downloaded/` 的字节总量。替代手段：用 `glob` 数出 **174 个文件**;报告中「628.9 MB」这一具体数字**本次未能复核**,建议用 `Get-ChildItem -Recurse -File agent\downloaded | Measure-Object Length -Sum` 补测。按判定口径,这不改变 `4 (M-15)` 的结论（构建上下文是否包含该目录可由 `.dockerignore` + `Dockerfile` 静态确定）。
2. **未启动任何容器、未运行任何测试、未做浏览器实测。** 本组 38 条的判定全部是静态证据（源码、配置文件、文档原文）。
3. **明确让给 B 组的**：`A-06` 只给「两套实现是否都还在、在哪个文件」的事实,「同一条连接两侧判定是否仍相反 / 保存时是否静默丢弃」的论证**详见 B 组 H-05**（`docs/审查日志/_核验/B-backend.md`）,本文件不重复。
4. **未核验的相邻项**（不属于本组范围,仅记录以免误读）：代码内部缺陷（`workflow_contract.py` 的 `map_content_get` 缺项、`async_result` 回调 `on` 校验、tool_server 输出校验等）、`webui_py/static/*.js` 的接口契约、`agent/tools/*` 死代码与 `None` 判空的完整清单。
5. **判定口径的两处灰区,已在条目内注明**：① `4 (M-15)` 中 `settings.json` 进镜像、`agent/2.py`/`3.py` 草稿两个子项**已消失**,只有 `downloaded/` 与 `test_*.py` 子项仍成立,整条判 STILL 而非 GONE;② `5 (M-19)` 中 `DASHSCOPE_API_KEY` 子项因读取方消失而失效,只有「ASR 端点硬编码」子项仍成立,整条判 STILL。
