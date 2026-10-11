# 02 Agent WebUI（webui_py，:8081）

> 审计对象：`webui_py/`（FastAPI 单体 + 3 张静态页 + 6 个前端模块）。全部结论来自源码逐行阅读，无不存在的接口推断。
> 重要事实：`docs/功能全景/_sections/00-目录说明.md:9` 把本节范围写成"事件流 / 终端 / 绑定 / **设置**"，但当前源码内**不存在任何 settings/文档页路由**（`webui_py` 全目录 grep `api/settings`、`document.html`、`system-prompt` 均无匹配）。本节按实际代码清点，只含 事件流 / 终端 / 绑定 三页。

## 2.1 代码地图与运行形态

| 层 | 文件 | 行数 | 职责 |
| --- | --- | --- | --- |
| 入口/装配 | `webui_py/main.py` | 150 | FastAPI 实例、3 个中间件、`/api/health`、两个路由工厂挂载、静态目录挂载（`webui_py/main.py:72-150`） |
| 事件流 API | `webui_py/events.py` | 398 | 快照聚合（Worker/Redis/Mongo 三段）、事件删改、终端历史与投递、Lua CAS 脚本（`webui_py/events.py:246-398`） |
| 绑定 API | `webui_py/event_bindings.py` | 134 | 事件类型 → Workflow 绑定的 CRUD 与 Workflow 选项（`webui_py/event_bindings.py:37-134`） |
| 共享校验 | `webui_py/common.py` | 7 | 唯一函数 `limit_error()`，limit 必须 1..300（`webui_py/common.py:4-7`） |
| 页面 | `static/index.html`(95) `static/terminal.html`(75) `static/bindings.html`(109) | — | 三张独立 HTML，无前端框架、无 SPA 路由 |
| 前端 JS | `static/app.js`(247) `render.js`(274) `api.js`(79) `terminal.js`(164) `bindings.js`(234) `auto-refresh.js`(24) `scroll-anchor.js`(59) | — | 原生 ES Module（`type="module"`），无构建步骤 |
| 样式 | `static/css/base.css`(40) `event-stream.css`(106) `terminal.css`(38) `bindings.css`(113) | — | 手写 CSS，CSS 变量主题，3 组断点 |

运行形态（`docker-compose.yml`）：

| 事实 | 位置 |
| --- | --- |
| 启动命令 `uvicorn main:app --host 0.0.0.0 --port 8081`，容器名 `webui_py_aagent` | `docker-compose.yml:65-68` |
| 端口**直接发布到宿主** `"8081:8081"`（未绑回环） | `docker-compose.yml:87` |
| 健康检查命中 `GET /api/health`，10s 间隔 / 3s 超时 / 5 次重试 | `docker-compose.yml:88-92` |
| 依赖 redis、mongodb 均 `service_healthy` 才启动 | `docker-compose.yml:70-74` |
| webui_py 服务块**没有 `env_file`**（与 `qqbot_consumer` 不同） | `docker-compose.yml:75-85` vs `:48-49` |
| 依赖固定版本 fastapi 0.116.1 / pymongo 4.13.2 / redis 6.2.0 / uvicorn 0.35.0 | `webui_py/requirements.txt:1-4` |
| Dockerfile 为 python:3.12-slim，`COPY . .`，无 CMD（由 compose 给命令） | `webui_py/Dockerfile:1-8` |

## 2.2 页面与导航

| 页面 | URL | 标题 | 导航高亮 | 数据源 | 自动刷新 |
| --- | --- | --- | --- | --- | --- |
| 事件流 | `/`（`StaticFiles(html=True)` 目录索引） | AAgent 事件流 | 事件流 | `GET /api/events` | 有，默认 2s |
| 终端 | `/terminal.html` | AAgent 终端 | 终端（`aria-current="page"`） | `GET /api/terminal/history` + `POST /api/terminal` | 有，默认 2s |
| 绑定 | `/bindings.html` | AAgent 事件绑定 | 绑定（`aria-current="page"`） | `GET /api/event-bindings` + `/workflow-options` | **无**（进页面加载一次，手动保存/删除后才刷新） |

导航结构：三页共享同一 `header.topbar`，其中 `.brand` 恒指向 `/`，`.page-nav` 三个 `<a>` 互链，当前页加 `.active`：

- `webui_py/static/index.html:13-22`（事件流页，`/` 为 active）
- `webui_py/static/terminal.html:13-22`（终端页）
- `webui_py/static/bindings.html:13-22`（绑定页）

跳转方式：**整页跳转（普通 `<a href>`）**，无 History API、无客户端路由、无跨页状态传递（`webui_py/static/*.js` 内无 `history.pushState` / `location.hash` 处理）。三页各自独立执行一次初始化：`app.js:247`、`terminal.js:164`、`bindings.js:234`。

DOM 装配：JS 一律通过 `document.querySelector('#id')` 在模块顶层取节点（`app.js:7-20`、`terminal.js:5-20`、`bindings.js:9-26`），**无 DOMContentLoaded 包裹**——因 `type="module"` 默认 defer，脚本执行时 DOM 已解析完毕。

## API 路由全表

共 **11 条 API 路由**（另有 1 个根静态挂载）。错误响应统一为 `{"error": "<中文文案>"}`；FastAPI 自身校验失败走 422 `{"detail":[{loc,msg,...}]}`。

| # | 方法 + 路径 | 请求参数 / 体 | 成功响应 | 失败响应 | 用途 | 代码位置 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `GET /api/health` | 无 | `200 {"status":"ok"}` | `503 {"status":"unavailable","error":str}` | 存活探针，Redis ping；compose healthcheck 使用 | `webui_py/main.py:128-134` |
| 2 | `GET /api/events` | query `limit`（默认 150，必须 1..300） | 快照对象：`queue`,`fetched_at`,`worker`,`summary{pending,running,history}`,`sources{mongodb,redis,worker}`,`items[]`,可选 `warnings{}` | `400 {"error":"limit must be between 1 and 300"}`（`common.py:4-7`） | 事件流页唯一数据源，一次聚合 Worker/Redis/Mongo 三层 | `webui_py/events.py:254-259`；聚合 `events.py:187-226` |
| 3 | `DELETE /api/events` | body `{status*:"done"\|"pending", doc_id?, position?, fingerprint?}`（`extra="forbid"`） | `done`→`{"deleted":true,"status":"done"}`；`pending`→`{"deleted":true,"status":"pending"}` | `400` 缺参数/ID 无效/不支持的 status；`404` 记录不存在；`409` 队列已变化；`503` Mongo/Redis 不可用 | 删除历史事件（Mongo `delete_one`）或从等待队列摘除（Lua + 指纹 CAS） | `webui_py/events.py:261-300` |
| 4 | `PUT /api/events` | body `{status*, event*:object, doc_id?, position?, fingerprint?}`（`extra="forbid"`） | `done`→`{"updated":true,"status":"done","doc_id","fingerprint"}`；`pending`→`{"updated":true,"status":"pending","position","fingerprint"}` | `400`（空事件/无 event_type/超 256 KB/缺 ID/缺指纹）；`404`；`409` 队列已变化；`503` | 就地编辑事件 JSON：历史整体 `replace_one`（保留 `created_at`），队列项 `LSET` 覆盖 | `webui_py/events.py:302-353` |
| 5 | `GET /api/terminal/history` | query `limit`（默认 150，1..300） | `{"fetched_at":ISO, "items":[{"id":str(_id), "created_at":ISO, "event":{...}}]}`，按 `_id` 升序（时间正序） | `400` limit 越界；`503 {"error":"终端历史暂时不可用"}` | 终端页消息列表；过滤 `event_type ∈ {terminal,response}` | `webui_py/events.py:355-375` |
| 6 | `POST /api/terminal` | body `{content*, files:[]}`（`extra="forbid"`；`Content-Length` ≤ 16 KB 由中间件拦） | `201 {"event":{event_type:"terminal",time:ISO Z,payload:{content,files:[]}}, "queue":"<队列名>"}` | `400`（空/超 4000 字符/`files` 非空）；`400` 体积超限（中间件）；`503 {"error":"消息队列暂时不可用"}` | 向 Agent 队列 `RPUSH` 一条 `terminal` 事件 | `webui_py/events.py:377-396` |
| 7 | `GET /api/event-bindings/workflow-options` | 无 | `{"items":[{"id","name","input_ports","output_ports"}]}`，按 name 升序 | `503 {"error":"Workflow 选项暂时不可用"}` | 绑定页下拉与端口契约预览 | `webui_py/event_bindings.py:40-56` |
| 8 | `GET /api/event-bindings` | 无 | `{"items":[{id,event_type,workflow_id,workflow_name,enabled,created_at,updated_at}]}`，按 `event_type` 升序 | `503 {"error":"事件绑定暂时不可用"}` | 绑定列表 | `webui_py/event_bindings.py:76-82`；字段映射 `:25-34` |
| 9 | `POST /api/event-bindings` | body `{event_type*:1..80, workflow_id*:min1, enabled:bool=true}`（`extra="forbid"`） | `200` 单条绑定对象（**注意是 200 而非 201**） | `400` 类型正则不合法 / Workflow id 无效；`404` Workflow 不存在；`409 {"error":"该 Event 已经绑定 Workflow"}`（唯一索引）；`503` | 新建绑定；服务端补 `workflow_name` | `webui_py/event_bindings.py:84-95`；校验 `:58-74` |
| 10 | `PUT /api/event-bindings/{binding_id}` | path `binding_id`；body 同 #9 | `200` 更新后的绑定对象 | `400` 绑定 id 无效 / 校验失败；`404 {"error":"事件绑定不存在"}`；`409`；`503` | 全量覆盖式更新（`$set`，`ReturnDocument.AFTER`） | `webui_py/event_bindings.py:97-118` |
| 11 | `DELETE /api/event-bindings/{binding_id}` | path `binding_id` | `{"deleted":true}` | `400` id 无效；`404 {"error":"事件绑定不存在"}`；`503 {"error":"事件绑定删除失败"}` | 删除绑定 | `webui_py/event_bindings.py:120-132` |
| — | `GET /`（挂载） | 静态目录 `static/`，`html=True` | 三张 HTML + `/css/*.css` + `/*.js` | 未匹配路径返回 StaticFiles 的纯文本 `Not Found`（非 JSON） | 页面与静态资源 | `webui_py/main.py:140-150` |

中间件（3 个，均为 `@app.middleware("http")`）：

| 中间件 | 行为 | 位置 |
| --- | --- | --- |
| `security_headers` | 所有响应加 `Content-Security-Policy: default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:`、`X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: no-referrer` | `webui_py/main.py:85-92` |
| `request_logger` | 仅当 path 以 `/api/` 开头，记录 method/path/duration（`%.3fs`）到 `aagent.webui` logger | `webui_py/main.py:95-106` |
| `request_body_guard` | 仅按 `(method,path)` 精确匹配 `("POST","/api/terminal")`→16 KB、`("PUT","/api/events")`→256 KB，读 `Content-Length` 头，超限直接 `400 {"error":"请求体不能超过 N KB"}` | `webui_py/main.py:109-125`；常量 `:21-22` |

> 顺序推断：Starlette 的 `add_middleware` 把后注册者插入用户栈首，构建时栈首为最外层。故 `request_body_guard`（最后注册）最外层，`security_headers` 最内层——**body_guard 直接返回的 400 不经过安全头与访问日志**。此结论依据库语义推导，本会话未运行验证。

启动钩子：`@app.on_event("startup")` 删除遗留索引 `unique_event_binding_route`，创建 `event_type` 唯一索引 `unique_event_binding_type`；异常只记 error 日志、不阻断启动（`webui_py/main.py:75-82`）。

## 控件与交互全表

计数口径：可交互控件（按钮 / 输入 / 下拉 / 文本域 / 表单 / 链接 / 开关），按"DOM 模板中出现的控件种类"计一行，动态生成的重复项合并为一行并标注 ×N。**合计 41 行**。展示型元素（计数、状态文本）另见 2.6。

| 控件 | 位置 | 触发条件 | 行为 | 调用的接口 | 代码位置 |
| --- | --- | --- | --- | --- | --- |
| `.brand` 品牌链接（事件流页） | 顶栏左侧 | 恒可见 | 跳 `/` | 无 | `static/index.html:13-16` |
| `.page-nav`「事件流」 | 顶栏中部导航 | 恒可见，本页 `.active` | 跳 `/` | 无 | `static/index.html:19` |
| `.page-nav`「终端」 | 顶栏中部导航 | 恒可见 | 跳 `/terminal.html` | 无 | `static/index.html:20` |
| `.page-nav`「绑定」 | 顶栏中部导航 | 恒可见 | 跳 `/bindings.html` | 无 | `static/index.html:21` |
| `#interval` 刷新间隔下拉 | 顶栏右侧 | 恒可见；选项 0.5/1/2(默认)/3/5/10 s | `change` → `schedule()` 仅重排下一次定时器，**不立即刷新** | 无（影响后续 `GET /api/events`） | `static/index.html:28`；`static/auto-refresh.js:10` |
| `#pauseButton` 暂停/继续 | 顶栏右侧图标按钮 | 恒可见 | 点击翻转 `paused`；加/去 `.active`；`.pause-icon` 切 `.play`（CSS 变三角）；`title`/`aria-label` 在"暂停自动刷新/继续自动刷新"间切换；`#refreshState` 文案切"自动刷新已暂停/已开启"；暂停时 `schedule()` 清定时器，恢复时因 `app.js` 未传 `onResume` 而调 `schedule()`（等一个间隔才刷新） | 无 | `static/index.html:29`；`static/auto-refresh.js:11-21`；装配 `static/app.js:240-245` |
| `#refreshButton` 立即刷新 | 顶栏右侧图标按钮 | 恒可见；请求进行中 `disabled`（CSS `cursor:wait; opacity:.55`） | 点击 → `refresh()` 拉快照并重渲染 | `GET /api/events?limit=150` | `static/index.html:30`；`static/app.js:239`、`:22-44` |
| `#runningButton` 回到正在执行 | 工具条右侧 | 恒可见；快照含 running 项时加 `.has-running`（绿底） | 点击 → 设 `anchorRestoreSuppressedUntil = now+1200ms`，`scrollTo({top: runningSection.offsetTop, behavior:'smooth'})`；1.2s 内抑制滚动锚点回写 | 无 | `static/index.html:45-48`；`static/app.js:136-139`、`:53` |
| `.type-filter-toggle` 类型筛选开关 | 工具条 | 恒可见；标签为"全部类型/单类型/已选 N 项" | 点击开合菜单，同步 `aria-expanded`；点菜单外任意处关闭；按 `Escape` 关闭 | 无（纯前端过滤） | `static/index.html:49-53`；`static/app.js:141-159` |
| `.type-filter-clear`「全部类型」 | 类型下拉菜单首项 | 每次 `populateTypes` 重建后恒存在 | 点击 → 清空 `selectedTypes`、反勾全部复选框、刷新标签、重渲染列表 | 无 | `static/render.js:68-72`；`static/app.js:160-166` |
| `.type-filter-option > input[checkbox]` ×N | 类型下拉菜单 | 选项集合 = 当前快照中所有 `event_type` 去重排序；仅当类型集合变化时才重建（增删同步勾选态，已消失的类型从选择集剔除） | `change` → 加入/移出 `selectedTypes`，刷新标签，重渲染 | 无 | `static/render.js:62-87`；`static/app.js:167-174`、`:31-32` |
| `#searchInput` 搜索框 | 工具条右端 | 恒可见（`type="search"`，浏览器自带清除 ✕） | `input` 事件 → `renderFilteredEvents()`；对 `JSON.stringify(item.event)` 小写做 `includes` 本地匹配；**不发请求**；有查询词时空态文案切"当前筛选没有匹配的…" | 无 | `static/index.html:54`；`static/app.js:135`、`:57-64` |
| `.details-button` 展开/收起 ×每行 | 事件行操作列 | 恒可见（running 行也显示）；`::before/::after` 画 +/−（展开时隐藏竖线） | 点击 `toggle('expanded')`，`title`/`aria-label` 在"展开事件详情/收起事件详情"切换，展开态记入 `expandedKeys`（按 `itemKey`） | 无 | `static/render.js:171`、`:173-183` |
| `.delete-button` 删除事件 ×每行 | 事件行操作列 | `item.status === 'running'` 时 `hidden`（`render.js:255`）；hover 变红 | 点击 → `confirm()`（pending 文案"确定从等待队列中删除该事件吗？"，done 文案"确定删除该历史事件吗？删除后不可恢复。"）→ 调用删除 → `finally` 无论成败都 `refresh()`；失败在警告条显示"删除失败：…" | `DELETE /api/events` | `static/render.js:171`、`:184-186`、`:255`；`static/app.js:177-193` |
| `.edit-button` 编辑/保存 ×每行 | 事件详情工具条 | `running` 行 `hidden`；非编辑态文案"编辑"，编辑态"保存"；保存中 `disabled` | 进编辑态：`JSON.stringify(event,null,2)` 填入编辑框、隐藏 `pre`、显示取消按钮、`focus({preventScroll:true})`；再点=保存：`JSON.parse` 校验 → 调 `PUT`；成功写回 `pre` 文本并提示"已保存"（或"内容未改动"）；失败加 `.edit-error` 并把错误文案写入 `.edit-status` | `PUT /api/events` | `static/render.js:172`、`:209-249`；`static/app.js:195-226` |
| `.cancel-edit-button` 取消 ×每行 | 事件详情工具条 | 默认 `hidden`，进入编辑态才显示 | 点击 → 退出编辑态：清空编辑框、隐藏它、显示 `pre`、按钮复位、清错误与状态文案；**不发请求** | 无 | `static/render.js:172`、`:196-207`、`:191` |
| `.event-editor` JSON 编辑文本域 ×每行 | 事件详情区 | 仅编辑态可见（CSS 用 `[hidden]` + `field-sizing:content` 自适应高度） | `input` → 移除 `.edit-error` 并清空 `.edit-status`（用户重新输入即清错） | 无 | `static/render.js:172`、`:187-190`；`static/css/event-stream.css:94-97` |
| `.brand` 品牌链接（终端页） | 顶栏左侧 | 恒可见 | 跳 `/` | 无 | `static/terminal.html:13-16` |
| `.page-nav`「事件流」 | 顶栏中部 | 恒可见 | 跳 `/` | 无 | `static/terminal.html:19` |
| `.page-nav`「终端」 | 顶栏中部 | 本页 `.active` + `aria-current="page"` | 跳 `/terminal.html` | 无 | `static/terminal.html:20` |
| `.page-nav`「绑定」 | 顶栏中部 | 恒可见 | 跳 `/bindings.html` | 无 | `static/terminal.html:21` |
| `#terminalInterval` 刷新间隔下拉 | 顶栏右侧 | 恒可见，6 档同事件流页 | `change` → `schedule()` | 无 | `static/terminal.html:28`；`static/auto-refresh.js:10` |
| `#terminalPauseButton` 暂停/继续 | 顶栏右侧 | 恒可见 | 同上；**恢复时走 `onResume` → 立即 `refreshStatus()` 一次**（与事件流页不同） | `GET /api/terminal/history` | `static/terminal.html:29`；`static/auto-refresh.js:11-21`；`static/terminal.js:154-160` |
| `#terminalRefreshButton` 立即刷新 | 顶栏右侧 | 请求中 `disabled` | 点击 → `refreshStatus()` | `GET /api/terminal/history?limit=150` | `static/terminal.html:30`；`static/terminal.js:135`、`:22-39` |
| `#terminalLatestButton`「跳到最新」 | 面板头部 | 恒可见；有新消息且用户不在底部时加 `.has-updates`（绿底） | 点击 → 去 `.has-updates` 并 `scrollTo({top:scrollHeight, behavior:'smooth'})`；列表滚动到距底 ≤24px 时也自动去该标记 | 无 | `static/terminal.html:42-45`；`static/terminal.js:136-142`、`:63`、`:68-71` |
| `#terminalForm` 消息表单 | 输入区 | 恒存在 | `submit` → `preventDefault()` + `sendMessage()`；输入框内 Enter 亦走此路径 | `POST /api/terminal` | `static/terminal.html:61-69`；`static/terminal.js:131-134`、`:147-152` |
| `#messageInput` 消息文本域 | 输入区 | `maxlength=4000`、`required`；发送中 `disabled`（CSS `opacity:.65`） | `input` → 自适应高度（`height=auto` 后取 `scrollHeight`，上限 180px）+ 更新 `#characterCount`（按码点 `[...value].length`）+ 若处于 error 态则清空状态文案；`Enter`（非 Shift、非 `isComposing`）→ 发送；`Shift+Enter` 换行；无上下键历史 | `POST /api/terminal`（Enter 路径） | `static/terminal.html:63`；`static/terminal.js:41-45`、`:143-152`、`:108`、`:125` |
| `#sendButton`「发送」 | 输入区右下 | `type="submit"`；内容为空或 `state.sending` 时点击**静默返回**（无提示）；请求中 `disabled` | 点击/提交 → 置"正在入队…"→ 成功后清空输入、`#queueName` 更新为返回队列名、状态"已优先入队，等待消费"（绿），并立即触发一次 `refreshStatus()`；失败置 `.error` 文案（超时→"请求超时，请重试"，否则服务端 `error`）；`finally` 恢复按钮与输入框、`resizeInput()`、回焦输入框 | `POST /api/terminal`，随后 `GET /api/terminal/history` | `static/terminal.html:67`；`static/terminal.js:102-129` |
| `.brand` 品牌链接（绑定页） | 顶栏左侧 | 恒可见 | 跳 `/` | 无 | `static/bindings.html:13-16` |
| `.page-nav`「事件流」 | 顶栏中部 | 恒可见 | 跳 `/` | 无 | `static/bindings.html:19` |
| `.page-nav`「终端」 | 顶栏中部 | 恒可见 | 跳 `/terminal.html` | 无 | `static/bindings.html:20` |
| `.page-nav`「绑定」 | 顶栏中部 | 本页 `.active` + `aria-current` | 跳 `/bindings.html` | 无 | `static/bindings.html:21` |
| `#newBinding`「+」 | 左栏标题右侧 | 恒可见 | 点击 → `resetForm()` → 打开表单（`.open`）、隐藏空态、`eventType.focus()` | 无 | `static/bindings.html:32`；`static/bindings.js:197-202` |
| `.binding-select` 整条选择按钮 ×每条 | 左栏列表项主体 | 列一项显示一条；当前编辑项加 `.selected`（绿底 + 左内阴影） | 点击 → `editBinding()`：回填 event_type/workflow_id/enabled、标题"编辑事件绑定"、`#formState`="编辑中"、启用取消按钮、清状态、重渲染列表以更新高亮 | 无（数据取自已加载的 `bindings`） | `static/bindings.js:98-101`、`:151-164`；样式 `static/css/bindings.css:16` |
| `.binding-item .delete-button`「删除」 ×每条 | 左栏列表项右侧 | 恒可见（文案按钮，hover 下划线，红色） | 点击 → `confirm('删除 <event_type> 的事件绑定？')` → 删除；成功则本地过滤数组、若删的正是当前编辑项则 `resetForm()`、重渲染、状态"已删除"；失败显示 `error.message` | `DELETE /api/event-bindings/{id}` | `static/bindings.js:121-125`、`:166-178` |
| `#eventType` 事件类型输入 | 表单路由区左 | 恒可见；`maxlength=80`、`pattern="[a-z][a-z0-9_.-]*"`、`required` | 提交时 `trim().toLowerCase()` 后作为 `event_type`；非法由浏览器原生校验拦截，服务端再以正则复核（400） | `POST`/`PUT /api/event-bindings` | `static/bindings.html:57`；`static/bindings.js:209`；`webui_py/event_bindings.py:59-61` |
| `#workflowId` 目标工作流下拉 | 表单路由区右 | 无 Workflow 时 `disabled` 且唯一选项文案"暂无 Workflow，请先创建"；有则"选择 Workflow"+列表 | `change` → `renderContractPreview()` 重绘端口契约；提交时取值 | `GET /api/event-bindings/workflow-options`（初始化） | `static/bindings.html:63-65`；`static/bindings.js:133-149`、`:204`、`:58-68` |
| `#enabled` 启用开关（隐藏 checkbox + `.toggle-track`） | 表单行为区右 | 恒可见；真实 `input` 绝对定位 `opacity:0`，由 `<label for="enabled">` 代理点击 | 切换勾选；提交时读 `checked`；编辑时按 `binding.enabled` 回填；`resetForm()` 强制回 `true` | `POST`/`PUT /api/event-bindings` | `static/bindings.html:96-100`；`static/bindings.js:211`、`:158`、`:76`；样式 `static/css/bindings.css:81-87` |
| `#cancelEdit`「取消」 | 表单标题右侧 | 初始 `disabled`；进入编辑或新建后启用；CSS 禁用态 `opacity:.48; cursor:not-allowed` | 点击 → `resetForm()`：清 `editingId`、关表单、显示空态、`form.reset()`、`enabled=true`、标题复位、`#formState`="未保存"、禁用自身、清状态、重绘契约 | 无 | `static/bindings.html:44`；`static/bindings.js:203`、`:70-82` |
| `#saveBinding`「保存绑定」 | 表单标题右侧 | `type="submit"`；无 Workflow 时初始 `disabled`；提交中 `disabled` | 提交 → 置"保存中"→ 有 `editingId` 走 `PUT` 否则 `POST`；成功用**服务端返回对象**替换本地项（新建则追加后按 `event_type` 排序）、重渲染、进入编辑态、状态"已保存"；失败显示 `error.message`；`finally` 无条件恢复 `disabled=false` | `POST` / `PUT /api/event-bindings` | `static/bindings.html:45`；`static/bindings.js:206-232` |
| `#bindingForm` 绑定表单 | 右栏配置区 | 默认 `display:none`，`.open` 才 `display:grid`；与 `#bindingEmpty` 空态互斥 | `submit` → 统一保存流程；输入框内按 Enter 触发原生隐式提交 | 同上 | `static/bindings.html:39`；`static/bindings.js:206`；样式 `static/css/bindings.css:34-35`、`:30-33` |

展示型元素（非交互，但有其可见条件与状态语义，逐个列全）：

| 元素 | 页面/位置 | 可见条件与内容 | 代码位置 |
| --- | --- | --- | --- |
| `#lastRefresh`「最后同步」 | 事件流 / 顶栏 | 成功时写 `fetched_at` 的 24h `toLocaleTimeString`；失败时文案改"同步失败"并加 `.sync-error`（红、非等宽字体） | `index.html:25`；`app.js:50`、`:125-128` |
| `#refreshState` | 事件流 / 顶栏 | "自动刷新已开启" / "自动刷新已暂停" | `index.html:26`；`auto-refresh.js:17` |
| `#doneCount` | 事件流 / 概览条 | `summary.history`；Mongo source 非 `ok` 时显示 `--` | `index.html:36`；`app.js:49`、`:115-117` |
| `#pendingCount` | 事件流 / 概览条 | `summary.pending`（`LLEN` 全量，非窗口）；Redis 非 `ok` 时 `--` | `index.html:37`；`app.js:48` |
| `#workerCard` + `#workerState` + `#workerDetail` | 事件流 / 概览条右侧 | 7 种状态文案（不可用/状态无效/疑似卡死/正在执行/疑似离线/等待任务/尚未上报）+ 类 `unknown\|processing\|idle\|stale` 决定左描边色 | `index.html:38`；`app.js:80-113`；`css/event-stream.css:6-9` |
| `#resultCount` | 事件流 / 工具条 | `${三段过滤后之和} 条事件` | `index.html:43`；`app.js:67` |
| `#historyVisibleCount` / `#runningVisibleCount` / `#pendingVisibleCount` | 事件流 / 各段标题右 | 各段**过滤后**条数（与概览条口径不同） | `index.html:65`、`:75`、`:84`；`render.js:109` |
| `#warningBanner`（`role="alert"`） | 事件流 / 工具条下方 | 默认 `hidden`；快照 `warnings` 非空、接口异常、删除/保存失败时显示，多处共用同一区域（后者会覆盖前者） | `index.html:58`；`app.js:119-123`、`:37-38`、`:188-189`、`:222-223` |
| `.list-head` 表头 | 事件流 / 历史段「阶段·事件·时间/来源」、队列段「队列位置·事件·顺序/来源」 | 静态文案；≤900px 时 `display:none` | `index.html:67`、`:86`；`css/event-stream.css:104` |
| `.status-dot` / `.section-marker` | 事件流 / 每行左侧、每段标题左侧 | 纯颜色语义：灰=历史、蓝=等待、琥珀=正在执行（marker 带脉冲动画） | `render.js:168`；`css/event-stream.css:39-49`、`:59-61` |
| `.empty-state` | 事件流 / 各段空态 | 三段 × (空/被筛选/数据源异常) 三套文案 | `render.js:141-159` |
| `.type-filter-label` | 事件流 / 类型筛选按钮内 | "全部类型" / 单个类型名 / "已选 N 项" | `render.js:89-94` |
| `.edit-status` | 事件流 / 详情工具条左 | "保存中…"、"已保存"、"内容未改动"、或错误消息；`.edit-error` 时加粗变红 | `render.js:230`、`:242`、`:245`；`css/event-stream.css:88-89` |
| `#terminalLastRefresh` / `#terminalRefreshState` | 终端 / 顶栏 | 同事件流页；超时文案为"同步超时" | `terminal.html:25-26`；`terminal.js:29-33` |
| `#queueName` | 终端 / 面板头部 | 初始静态 `main_agent_queue`，发送成功后被服务端返回的 `queue` 覆盖 | `terminal.html:48`；`terminal.js:114` |
| `#terminalEmpty` | 终端 / 消息区 | 空态占位；首条消息渲染时 `.remove()` 且不再恢复 | `terminal.html:53-58`；`terminal.js:77` |
| `#sendStatus`（`role="status"`） | 终端 / 输入区左下 | 空 → "正在入队…" → `.success`"已优先入队，等待消费" 或 `.error` 错误/超时文案 | `terminal.html:65`；`terminal.js:109-121` |
| `#characterCount` | 终端 / 输入区 | `N / 4000`，随输入实时更新 | `terminal.html:66`；`terminal.js:44` |
| `#bindingCount` | 绑定 / 顶栏右 | `${bindings.length} 条`；加载失败显示"不可用" | `bindings.html:23`；`bindings.js:86`、`:191` |
| `#formTitle` / `#formState` | 绑定 / 表单标题 | "新建事件绑定 / 编辑事件绑定" + "未保存 / 编辑中" | `bindings.html:41`；`bindings.js:77-78`、`:159-160` |
| `#formStatus`（`aria-live="polite"`） | 绑定 / 表单标题右 | 空 / "删除中" / "保存中" / `.success`"已保存""已删除" / `.error` 错误文案 | `bindings.html:43`；`bindings.js:32-35`、`:168`、`:174`、`:214`、`:226` |
| `#bindingEmpty` | 绑定 / 右栏 | 与表单互斥的引导空态（"选择一个事件绑定 / 或从左侧新建绑定"） | `bindings.html:38`；`bindings.js:74`、`:199` |
| `#contractWorkflowName` / `#contractInputCount` / `#contractOutputCount` | 绑定 / 契约预览 | Workflow 名或"未选择 Workflow"；`N 个端口` | `bindings.html:74`、`:80`、`:87`；`bindings.js:62-64` |
| `.contract-port-row` | 绑定 / 契约预览 | 每端口一行：名称 + 类型 `<code>`（缺省 `content`）；空则"暂无字段"或"选择 Workflow 后预览" | `bindings.js:37-56` |
| `.status-enabled` / `.status-disabled` | 绑定 / 列表项 | "已启用"（绿）/ "已停用"（琥珀） | `bindings.js:119-120`；`css/bindings.css:23-25` |

## 2.3 交互细节：键盘 / 鼠标 / 焦点 / 滚动

键盘事件（全量，仅 4 处）：

| 事件 | 作用域 | 行为 | 代码位置 |
| --- | --- | --- | --- |
| `Escape` | `document`（事件流页） | 无条件 `closeMenu()` 关闭类型筛选菜单（`menu.hidden=true` + `aria-expanded=false`），即使菜单已关也执行 | `static/app.js:157-159` |
| `Enter` | `#messageInput`（终端页） | `!shiftKey && !isComposing` 时 `preventDefault()` 并发送；`Shift+Enter` 保留换行；输入法组合中不发送 | `static/terminal.js:147-152` |
| `Enter`（隐式提交） | 绑定表单文本/下拉 | 浏览器原生表单隐式提交，等价点击"保存绑定" | `static/bindings.html:39-47`、`static/bindings.js:206` |
| 无 | 事件流页 | **无** `Enter` 发送、**无** 上下键历史、**无** 全局快捷键、**无** `Ctrl/Cmd+*` 组合键 | `static/app.js` 全文仅 `:157` 一个 keydown |

鼠标交互：

| 交互 | 目标 | 行为 | 代码位置 |
| --- | --- | --- | --- |
| 点击外部关闭 | `document` 点击 | `!container.contains(event.target)` → 关闭类型菜单 | `static/app.js:154-156` |
| 展开/折叠 | `.details-button` | 切换行 `.expanded`，`pre` 从 `display:none` 变 `block`，+/− 图标切换 | `static/render.js:173-183`；`static/css/event-stream.css:77`、`:84-85` |
| 编辑/只读切换 | `.edit-button` / `.cancel-edit-button` | 只读态显示 `<pre>`（深色背景等宽），编辑态 `pre` 隐藏、`.event-editor` 显示（同配色、`field-sizing:content` 自增高），退出时清空编辑框 | `static/render.js:196-249`；`static/css/event-stream.css:86`、`:94-97` |
| hover 反馈 | 行、按钮 | `.event-row:hover` 淡底；`.delete-button:hover` 变红；`.details-button`/`.edit-button` hover 变绿；绑定项 hover `#f0f5f1` | `static/css/event-stream.css:56`、`:83`、`:91`；`static/css/bindings.css:15` |
| 确认对话框 | 删除事件、删除绑定 | 均用原生 `window.confirm`，非自定义弹层；取消则直接 `return`，不发请求 | `static/app.js:181`；`static/bindings.js:167` |
| 双击 | 无 | 全站无 `dblclick` 监听 | — |
| 拖拽 / 右键 / 长按 | 无 | 无 `dragstart`/`contextmenu`/`pointer*` 监听，无右键菜单 | — |
| 焦点管理 | 三处显式 | 进编辑态 `editor.focus({preventScroll:true})`（避免滚动跳动）；新建绑定时 `eventType.focus()`；发送完成后回焦输入框 | `static/render.js:225`；`static/bindings.js:201`；`static/terminal.js:127` |
| 可见焦点环 | 全局 | `:focus-visible` → `2px solid var(--green)` + `outline-offset:2px` | `static/css/base.css:5` |

滚动行为：

| 机制 | 规则 | 代码位置 |
| --- | --- | --- |
| 首屏定位 | 第一次渲染后 `timeline.scrollTop = runningSection.offsetTop`（瞬间，无动画），之后置 `initialPositioned=true`，永不再自动定位 | `static/app.js:68-70` |
| 滚动锚定（`scroll-anchor.js`） | 刷新前 `captureAnchorState(timeline, '.event-row')`：在全部行中取 `abs(row.top - container.top)` **最小者**为锚点，记录 `{anchorId: dataset.id, anchorOffset, scrollTop}`；渲染后在 `requestAnimationFrame` 中 `restoreAnchorState`：用 `[data-id="…"]`（`CSS.escape`）找回锚点，`scrollTop = 旧scrollTop + (新anchorOffset - 旧anchorOffset)`；锚点行已消失则回退为旧 `scrollTop`；锚点集合为空则返回 null 不做处理 | `static/scroll-anchor.js:1-59`；调用 `static/app.js:65-77` |
| 锚定抑制 | `#runningButton` 点击后 1.2s 内跳过恢复（`anchorRestoreSuppressedUntil`），且在 rAF 回调里**二次检查**时间戳，防止点击滚动动画与锚点回写互相打架 | `static/app.js:6`、`:136-139`、`:71-76` |
| 详情内容防重写 | `if (details.textContent !== content)` 才写入 `pre`，避免每 2s 轮询都重写 DOM（保护内部滚动/选择状态） | `static/render.js:271-273` |
| 终端贴底跟随 | `isNearBottom()`：`scrollHeight - scrollTop - clientHeight <= 24`；首屏加载无动画贴底，之后新增消息时若贴底则 `smooth` 滚底，否则加 `has-updates` 标记；`scroll` 监听里一旦回到底部即清除标记 | `static/terminal.js:47-71`、`:140-142` |
| 滚动容器 | 事件流滚动发生在 `.timeline`（`overflow-y:auto`，`overscroll-behavior:contain`，细滚动条 8px）；`<pre>` 为 `overflow:visible` 不独立滚动 | `static/css/event-stream.css:30-32`、`:86` |

展开状态保持（`render.js` 模块级 `expandedKeys: Set`，`static/render.js:12`）：

- key 规则：`done:<doc_id>` / `pending:<fingerprint>:<position>` / `running:<id>`（`static/render.js:22-26`）。
- 行 DOM 复用后由 `updateEventRow` 用 `expandedKeys.has(itemKey)` 重新套用 `.expanded`（`static/render.js:264-268`）。
- 队列项编辑成功后 `remapExpandedKey` 把旧 key 迁到新 `fingerprint`/`position`（`static/app.js:214-218`、`static/render.js:28-33`）。
- **失效时机**：等待队列整体前移会使 `position` 变化 → key 不再命中 → 展开态自动折叠；历史事件被删除或 key 不在快照中即自然失效（集合**只增不减**，长会话下 Set 会缓慢膨胀）。

## 2.4 实时性机制

| 项 | 事实 | 代码位置 |
| --- | --- | --- |
| 传输方式 | **仅 HTTP 轮询**。无 SSE、无 WebSocket、无 `EventSource`、无 `setInterval`（全目录 grep 无匹配） | `static/auto-refresh.js` 全文；`static/api.js` |
| 定时器 | 递归 `setTimeout`（不是周期 `setInterval`），每次刷新 `finally` 里重新 `schedule()`，因此**实际周期 = 请求耗时 + 间隔值**，天然不重叠 | `static/auto-refresh.js:5-8`；`static/app.js:42`；`static/terminal.js:37` |
| 间隔档位 | 500 / 1000 / **2000（默认 `selected`）** / 3000 / 5000 / 10000 ms | `static/index.html:28`；`static/terminal.html:28` |
| 暂停 | 有。暂停=清定时器且不再调度；事件流页恢复仅重排定时器（等一个间隔），终端页恢复立即刷新一次（`onResume`） | `static/auto-refresh.js:2-21`；`static/app.js:240-245`；`static/terminal.js:154-160` |
| 手动刷新 | 两个页面顶栏按钮；刷新期间按钮 `disabled`，形成最小并发保护 | `static/app.js:25`、`:41`；`static/terminal.js:25`、`:36` |
| 单请求超时 | 5s `AbortController`；超时抛 `AbortError`。事件流页把 `error.message` 直接拼进警告条；终端页特判 `AbortError` 显示"同步超时" | `static/api.js:1`、`:4-5`、`:16-18`；`static/app.js:38`；`static/terminal.js:33`、`:121` |
| 缓存策略 | fetch 一律 `cache:'no-store'`；服务端 HTML `Cache-Control: no-store`、其余静态资源 `no-cache`（每次校验 ETag/Last-Modified 后可能 304） | `static/api.js:7`；`webui_py/main.py:143-147` |
| 绑定页 | **不轮询**，仅在 `load()` 时并发拉取两个接口 | `static/bindings.js:180-195` |
| 服务端快照新鲜度 | 每次请求**实时**读 Redis 队列/状态与 Mongo（无缓存层），`fetched_at` 为服务端当前 UTC 时间 | `webui_py/events.py:126-128`、`:155`、`:84`、`:202` |

增量渲染与"避免重建 DOM"指纹机制（`static/render.js:108-139`）：

1. 快照被按 `status` 分组为 `done/running/pending` 三段（`render.js:96-106`）。
2. 每段用 `section.list.querySelectorAll('.event-row')` 建 `Map<dataset.id, node>`（`render.js:115`）。
3. 遍历目标项：`existing.get(item.id)` 命中则复用节点，否则新建（带 `.enter` 动画，`animationend` 后移除，`render.js:165-166`）；用 `insertBefore` 就地移动、`existing.delete` 标记已用。
4. 遍历结束后统一 `node.remove()` 删除多余节点（`render.js:132`、`:133-137`）。
5. **running 特殊分支**：`reusableRunningNode`——当 running 段恰有 1 项、且旧节点也恰有 1 个时，直接复用旧节点以消化 `id` 变化（`id = running-<fingerprint>` 随任务切换而变），避免重建导致的动画闪烁与滚动跳动（`render.js:116-124`）。
6. 行内各字段全部 `textContent` 赋值（`render.js:251-274`），只有 `pre` 文本做了"内容相同则不写"的指纹判断（`render.js:271-273`）。
7. **编辑中的行跳过刷新**：`updateEventRow` 先更新 `row._item` 与基础字段，再 `if (row.classList.contains('editing')) return;`——编辑态下不覆盖用户输入、不改展开态（`render.js:252`、`:263`）。这同时意味着保存时用的是**最新快照**的 `position`/`fingerprint`/`doc_id`，用户只提交 event 内容。

## 2.5 前端状态管理

| 页面 | 状态 | 类型 | 生命周期与失效时机 | 代码位置 |
| --- | --- | --- | --- | --- |
| 事件流 | `state.snapshot` | 最近一次成功快照 | 每次成功 `fetchEvents` 覆盖；失败时保留旧值并在警告条提示"页面展示最后一次成功快照" | `static/app.js:6`、`:30`、`:38` |
| 事件流 | `state.loading` | 互斥锁 | 进入 `refresh` 置 true（此时再调直接 return），`finally` 置 false | `static/app.js:23-24`、`:40` |
| 事件流 | `state.selectedTypes` | `Set<string>` | 勾选/清空时改；`populateTypes` 在类型集合变化时剔除已不存在的类型；**跨页面不持久化**（无 localStorage/sessionStorage） | `static/app.js:6`、`:163`、`:170-171`；`static/render.js:63-66` |
| 事件流 | `state.initialPositioned` | 布尔 | 首帧定位后置 true，本页生命周期内不再自动定位 | `static/app.js:6`、`:68-70` |
| 事件流 | `state.anchorRestoreSuppressedUntil` | 时间戳(ms) | `#runningButton` 点击时设为 now+1200 | `static/app.js:6`、`:137` |
| 事件流 | `expandedKeys` | `Set<string>`（模块私有） | 展开即加、收起即删、编辑成功迁移；删除/队列前移后成为悬垂 key（不清理） | `static/render.js:12`、`:28-33`、`:180-182` |
| 事件流 | `deleteHandler`/`editHandler` | 函数引用 | 模块加载时由 `app.js:237-238` 注入，解耦 `render.js` 与 `api.js` | `static/render.js:10-20` |
| 事件流 | 滚动位置 | DOM 属性 + 锚点快照 | 每帧渲染前捕获、`rAF` 后恢复（见 2.3）；不持久化到存储 | `static/app.js:65`、`:71-77` |
| 终端 | `state.seen` | `Set<item.id>` | 已渲染消息 id 指纹，用于**只追加**去重；**只增不减、无上限**，长会话内存单调增长 | `static/terminal.js:4`、`:51-52` |
| 终端 | `state.historyLoaded` | 布尔 | 首帧后置 true，决定滚底用 `auto` 还是 `smooth` | `static/terminal.js:4`、`:57-65` |
| 终端 | `state.loading` / `state.sending` | 互斥锁 | 分别守卫轮询与发送；发送期间输入框+按钮 `disabled` | `static/terminal.js:4`、`:23`、`:104-108`、`:123-125` |
| 终端 | `#queueName` 文本 | DOM 状态 | 初始硬编码 `main_agent_queue`（HTML 静态文本），仅在**发送成功后**被服务端返回的 `queue` 覆盖 | `static/terminal.html:48`；`static/terminal.js:114` |
| 绑定 | `bindings` 数组 | 内存模型 | `load()` 全量替换；新建追加并按 `event_type` 前缀排序；更新用服务端对象原位替换；删除本地过滤 | `static/bindings.js:28`、`:186`、`:219-223`、`:171` |
| 绑定 | `workflows` 数组 | 内存模型 | 仅 `load()` 时由 `renderWorkflows` 写入；决定下拉选项、`saveButton.disabled`、契约预览 | `static/bindings.js:29`、`:133-149` |
| 绑定 | `editingId` | string\|null | 点击列表项/新建/取消/删除时改写；决定 `.selected` 高亮与走 POST 还是 PUT | `static/bindings.js:30`、`:152`、`:71`、`:216` |
| 全局 | 无跨页共享状态 | — | 无 localStorage / sessionStorage / IndexedDB / cookie 读写（三页 JS 均无相关 API） | — |

分页/游标：**不存在**。事件流与终端历史均由 `limit=150` 截断（`static/api.js:21`、`:41`），服务端上限 300，无 offset/cursor/翻页控件。历史段的 `summary.history` 因此是"当前窗口条数"而非全量，UI 文案已注明"MongoDB 当前窗口"（`static/index.html:36`）；而 `summary.pending` 取 `LLEN` 全量（`webui_py/events.py:126`、`:148`）。

## 2.6 数据渲染

### 事件流：一条事件的渲染字段

行 DOM 结构由静态模板一次性生成（唯一的 `innerHTML` 用法，且无任何插值，`static/render.js:167-172`），4 列 grid：`112px | 1fr | 180px | 70px`（`static/css/event-stream.css:50`）。

| 位置 | 内容来源 | 规则 | 代码位置 |
| --- | --- | --- | --- |
| 列1 `.state-cell > strong` | 状态文案 | `running`→"正在执行"、`pending`→"等待执行"、`done`→"执行历史"，未知则回显原 status | `static/render.js:1`、`:257` |
| 列1 `.state-cell > small` | 副标签 | pending → `QUEUE <position>`；其余 → status 大写 | `static/render.js:258` |
| 列1 `.status-dot` | 颜色语义 | 灰=历史、蓝=`pending`、琥珀=`running`（并带 5px 光晕） | `static/css/event-stream.css:59-61` |
| 列2 `.event-type` | `event.event_type`，缺省 `'未分类'` | 等宽小标签，最长 180px 省略号；pending 蓝底、running 琥珀底 | `static/render.js:35-37`、`:259`；`css/event-stream.css:67-69` |
| 列2 `.event-preview` | 单行预览，优先级：`event.render`(非空字符串) → `event_type==='active'` 时固定"请求 LLM 处理" → `payload.raw_message/content/result/message/tool/raw` 首个非空字符串 → 否则 `JSON.stringify(payload ?? event)`；一律截断 260 字符 | 单行省略号，等宽字体 | `static/render.js:39-51`、`:260` |
| 列3 `.source-cell > strong` | 来源 | `worker`→Worker、`redis`→Redis、`mongodb`→MongoDB，未知回显原值 | `static/render.js:2`、`:261` |
| 列3 `.source-cell > small` | 时间/顺序标签 | pending：`position===1`→"下一项"，否则"等待 #N"；running/done：`started_at \|\| created_at` → `toLocaleString('zh-CN',{hour12:false})`，无效→"时间未知" | `static/render.js:53-60`、`:262` |
| 详情 `pre` | `JSON.stringify(item.event, null, 2)` | **纯文本、无 JSON 语法高亮**（深色底 `#1c2824` + 浅字 `#dce9e4`，`white-space:pre-wrap`、`overflow-wrap:anywhere`）；内容相同则不重写 | `static/render.js:270-273`；`css/event-stream.css:86` |
| 行级强调 | `[data-status="running"]` | 行更高（88px）、上下琥珀边、半透明琥珀底、状态点脉冲动画 | `css/event-stream.css:57`、`:61`、`:48` |

- **耗时**：事件行**不渲染任何耗时字段**。唯一耗时展示在状态条 WORKER 卡片："已运行 Xs / Xm Ys"（`formatDuration`，`<60` 显示 `${s}s`，否则 `${m}m ${s}s`）——`static/app.js:100-102`、`:130-133`。
- **空态**：三段各有两套文案——"数据源为空"与"筛选无匹配"；数据源异常时用第三套（MongoDB 历史不可用 / Worker 尚未上报 / Worker 状态不可用 / Worker 状态无效 / Redis 队列不可用），并按 `sources` 状态择一（`static/render.js:141-159`）。
- **警告条**：`snapshot.warnings` 的 `{source: message}` 以 ` · ` 连接写入 `#warningBanner`（`role="alert"`），无警告则 `hidden`；接口异常时复用同一区域显示"事件接口不可用：…"或"删除失败/保存失败：…" | `static/app.js:119-123`、`:37-38`、`:188-189`、`:222-223`。
- **概览条**：`#doneCount`（Mongo 窗口条数）、`#pendingCount`（Redis 队列总数）在对应 source 非 `ok` 时显示 `--`（`static/app.js:48-49`、`:115-117`）；WORKER 卡片有 7 种状态文案与 4 种配色类 `unknown/processing/idle/stale`：不可用、状态无效、疑似卡死（processing 且 started 超 10 分钟）、正在执行（显示已运行时长）、疑似离线（idle 且 `updated_at` 缺失或超 15 秒）、等待任务（idle，显示更新时刻，缺 `updated_at` 时显示"阻塞于 Redis 队列"）、尚未上报（`static/app.js:80-113`；CSS `css/event-stream.css:6-9`）。
- **区块计数**：`#historyVisibleCount`/`#runningVisibleCount`/`#pendingVisibleCount` 为**过滤后**条数（`render.js:109`）；工具条 `#resultCount` 为三段之和（`app.js:67`）。

### 终端：消息与角色渲染

每条历史事件 `appendMessage` 生成一个 `.terminal-message`（只追加，绝不清空列表，`static/terminal.js:73-100`）：

| 字段 | 规则 | 代码位置 |
| --- | --- | --- |
| 角色判定 | `event.event_type === 'response'` → 类名 `response-message` + 作者 `AGENT`（蓝）；否则 `command-message` + 作者 `TERMINAL`（绿） | `terminal.js:79`、`:85` |
| 对齐与配色 | 命令靠右、绿底 `#e5f2eb`、右侧 4px 绿边；响应靠左、蓝底 `#e7f0f7`、左侧 4px 蓝边；宽度 `min(78%,720px)` | `css/terminal.css:16`、`:19-23` |
| 时间 | `new Date(item.created_at)` → `toLocaleTimeString('zh-CN',{hour12:false,hour:'2-digit',minute:'2-digit'})`；无效→"时间未知"；同时写 `<time datetime>` | `terminal.js:87-91` |
| 正文 | response：`payload.content \|\| (payload.tool_calls?.length ? '[工具调用]' : '[空响应]')`；其余：`payload.content \|\| '[空命令]'`；`textContent` + `white-space:pre-wrap` | `terminal.js:94-97`；`css/terminal.css:19` |
| 去重 | `state.seen` 按 `item.id`（Mongo `_id` 字符串）跳过重复 | `terminal.js:51-52` |
| 入退场动画 | `.terminal-message` 有 220ms `message-in`；`prefers-reduced-motion` 下关闭 | `css/terminal.css:16`、`:38` |
| 空态 | 容器内静态 `#terminalEmpty`（大 "A" 方块 + "已消费的终端命令与 Agent 响应将在这里追加"），**首条消息到达时用 `elements.empty?.remove()` 移除，且不再恢复** | `terminal.html:53-59`；`terminal.js:77` |

### 绑定页：渲染

| 区域 | 渲染方式 | 代码位置 |
| --- | --- | --- |
| 顶部计数 | `#bindingCount` = `${bindings.length} 条`；加载失败时显示"不可用" | `bindings.js:86`、`:191` |
| 列表项 | `.binding-item` = `.binding-select`（`event_type` 等宽加粗 + `→` + `workflow_name \|\| workflow_id \|\| '未知 Workflow'`）+ `.binding-meta`（"已启用"绿 / "已停用"琥珀 + "删除"按钮）；当前编辑项加 `.selected` | `bindings.js:94-130`、`:119-120`、`:112` |
| 列表空态 | 单段 `<p class="empty-state">还没有事件绑定。</p>` | `bindings.js:87-93` |
| 配置区空态 | `#bindingEmpty`（"选择一个事件绑定 / 或从左侧新建绑定"）与表单互斥：`emptyState.hidden` + `form.classList.toggle('open')` | `bindings.html:38`；`bindings.js:70-82`、`:197-202` |
| 端口契约预览 | 逗号："`N 个端口`"；逐端口一行（名称 + `<code>` 类型，缺省 `content`）；无端口且已选 Workflow → "暂无字段"，未选 → "选择 Workflow 后预览"；标题显示 Workflow 名或 `未选择 Workflow` | `bindings.js:37-68`；`css/bindings.css:69-77` |
| 端口配色 | `IN` 蓝 `#277da1`，`OUT` 橙 `#d26938` | `css/bindings.css:70-71` |
| 表单状态 | `#formStatus` 文案 + 类 `success`（绿）/`error`（红）/空；`#formState` 显示"未保存 / 编辑中" | `bindings.js:32-35`、`:78`、`:160` |

### 布局与主题

| 项 | 事实 | 代码位置 |
| --- | --- | --- |
| 主题 | 单一浅色主题，`:root` CSS 变量（canvas/surface/ink/muted/line/green/amber/blue/red/shadow）；每页 `<meta name="color-scheme" content="light">`，**无深色模式、无 `prefers-color-scheme` 分支** | `css/base.css:1`；`index.html:6`、`terminal.html:6`、`bindings.html:6` |
| 字体 | `"Bahnschrift","Microsoft YaHei"`（正文）、`Georgia`（标题/数字）、`Consolas`（等宽/标签） | `css/base.css:4`、`:11`、`:31` |
| 骨架 | `body` 为 `100dvh` 纵向 flex + `overflow:hidden`（整页不滚动）；顶栏 68px；`main` 居中且宽 `min(1360px, 100% - 48px)` | `css/base.css:4`、`:7`、`:27` |
| 事件流布局 | 状态条 3 列 grid → 流面板 flex 列 → `.timeline` 独立纵向滚动；时间轴用 `.event-section::before` 画竖线，`.section-heading` `position:sticky; top:0` 吸顶 | `css/event-stream.css:1`、`:10`、`:30`、`:33-37` |
| 终端布局 | 3 行 grid：头部 / 消息滚动区 / 输入区；消息区带 28px 网格背景；输入区居中宽度 `min(...860px)` | `css/terminal.css:2`、`:11`、`:24` |
| 绑定布局 | 2 列 grid（`minmax(250px,330px)` 列表 + 自适应配置区），各自独立滚动；右栏带 28px 横线背景 | `css/bindings.css:5`、`:6`、`:13`、`:29` |
| 断点 | `base.css`: 1000px（顶栏改 112px 高、导航绝对定位右上）、560px（隐藏品牌文字/间隔标签、缩小内边距）；`event-stream.css`: 900px（状态条 3 列、WORKER 独占整行、工具条竖排、隐藏 `list-head`、行改 3 列）、560px（工具条竖排、类型筛选全宽、行改 2 列并把 event-main/source/详情改为跨列分行）；`bindings.css`: 700px（单列、列表限高 230–300px、表单状态绝对定位到标题下方）；`terminal.css`: 560px | 各 `css/*.css` 末段 `@media` |
| 动效降级 | `@media (prefers-reduced-motion:reduce)` 关闭行入场与脉冲动画、关闭消息入场动画 | `css/event-stream.css:106`；`css/terminal.css:38` |
| 可访问性 | `.sr-only` 隐藏标签、`aria-label`/`aria-expanded`/`aria-haspopup`/`aria-current`/`aria-live`/`role="alert"`/`role="status"` 齐备；图标按钮均有 title | `css/base.css:6`；三个 HTML 与 JS 内 `setAttribute` 调用 |

## 2.7 写入与变更操作

| 操作 | 入口 | 前端校验 | 服务端校验 | 乐观更新 | 失败处理 / 回滚 | 并发保护 |
| --- | --- | --- | --- | --- | --- | --- |
| 终端发消息 | `#sendButton` / Enter | 内容 `trim()` 非空（空则静默 return）；`maxlength=4000`；发送中自锁 | `content.strip()` 非空（400"消息不能为空"）、`len>4000`→400、`files` 非空→400"暂不支持文件附件"、`Content-Length>16KB`→中间件 400、`extra="forbid"` | 无 | 无本地改动可回滚；保留输入框内容，`sendStatus` 显示 `.error` 文案；`finally` 恢复可交互并聚焦 | `state.sending` 自锁 + 按钮/输入框 `disabled`；无幂等键（重复提交会产生多条队列项） |
| 事件编辑保存（历史项） | `.edit-button`（编辑态） | `JSON.parse` 失败→"JSON 格式无效，请修正后再保存"；非对象/数组→"事件内容必须是 JSON 对象"；`canonicalJson` 与当前值完全一致→**不发请求**，提示"内容未改动" | 去掉 `_id`/`created_at` 后非空、`event_type` 必须为非空字符串、序列化后 ≤256 KB、`doc_id` 必需且为合法 ObjectId | 无（先请求、成功后写回 `pre`） | 失败：行加 `.edit-error`（编辑框描边变红、状态文字加粗变红），保持编辑态、保留用户输入，警告条同时显示"保存失败：…"；无回滚需要 | Mongo `replace_one` **无版本号/ETag**，后写覆盖先写；服务端先 `find_one` 确认存在（404）再替换，保留 `created_at` |
| 事件编辑保存（队列项） | 同上 | 同上 | 同上 + `position≥1` 与 `fingerprint` 必需 | 无 | 同上 | 双层 CAS：先 `LINDEX -position` 比对指纹（`events.py:336-342`），再用 Lua `UPDATE_PENDING_SCRIPT` 在原子内 `LINDEX` 复检后 `LSET`（`events.py:237-243`、`:344`）；不符返回 409"队列已发生变化，请刷新后重试" |
| 删除历史事件 | `.delete-button` | `confirm()` 二次确认 | `status="done"` + `doc_id` 合法 ObjectId；`delete_one` 命中 0 条→404 | 无 | 失败显示"删除失败：…"；`finally` 无条件 `refresh()`（成功也刷新，以保证快照一致） | 无（删除幂等性由 404 表达） |
| 删除队列事件 | `.delete-button` | `confirm()` 文案不同 | `status="pending"` + `position≥1` + `fingerprint`；`LINDEX` 比对→`eval(DELETE_PENDING_SCRIPT)`：`LSET` 写入唯一 marker（`__aagent_deleted__<uuid4>`）再 `LREM 1 marker`，保证只移除被校验的那一个元素 | 无 | 同上 | 同一套 CAS：脚本内 `if current ~= ARGV[2] then return -1`；返回 -1→409、0→404（`events.py:229-235`、`:287-297`） |
| 新建绑定 | `#newBinding` → `#saveBinding` | `required` + `maxlength=80` + `pattern`；提交前 `trim().toLowerCase()`；无 Workflow 时按钮 `disabled` | 正则 `^[a-z][a-z0-9_.-]*$`（400）、`workflow_id` 必须为合法 ObjectId（400）、Workflow 必须存在（404）、`event_type` 唯一索引冲突（409） | 无 | 失败仅显示 `#formStatus` error 文案，表单内容保留；`finally` 恢复按钮可用（注意：无 Workflow 时也会被恢复为可点击） | 服务端唯一索引 `unique_event_binding_type`（启动时创建，`main.py:76-82`）；前端按钮 `disabled` |
| 更新绑定 | 列表项 → 改字段 → 保存 | 同上 | 同上 + 绑定 id 合法（400）+ 存在性（404） | 无（用 `PUT` 返回的对象替换本地项） | 同上 | 唯一索引 + `find_one_and_update` 原子更新 |
| 删除绑定 | 列表项"删除" | `confirm()` | 绑定 id 合法（400）、存在（404） | 无 | 失败显示 error 文案，本地数组不变 | 无 |
| 启用/停用 | `#enabled` 开关 | 无（提交时才生效） | `enabled: bool` 由 Pydantic 强类型校验 | 无 | 同保存流程 | 同更新绑定 |

共性事实：**全站没有任何乐观更新**（无 temp id、无 pending 样式），一律"请求成功后刷新/写回"；也没有撤销（undo）入口。

## 2.8 后端契约：Redis / MongoDB

### 配置项与环境变量（全部来自环境，无配置文件解析、无 python-dotenv）

| 变量 | 默认值 | 用途 | 位置 |
| --- | --- | --- | --- |
| `REDIS_ADDR` | 空 | 显式地址（给定时优先） | `main.py:30-33` |
| `REDIS_HOST` / `REDIS_PORT` | `redis` / `6379` | 拼接地址 | `main.py:33` |
| `REDIS_DB` | `0` | 库号 | `main.py:37` |
| `REDIS_PASSWORD` | 空 | 密码（空则不启用） | `main.py:49` |
| `MAIN_AGENT_QUEUE_NAME` | `main_agent_queue` | Agent 主队列键 | `main.py:38` |
| `AGENT_WORKER_STATUS_KEY` | `aagent:worker:status` | Worker 状态键 | `main.py:39` |
| `MONGO_HOST` / `MONGO_PORT` | `mongodb` / `27017` | Mongo 连接 | `main.py:40-41` |
| `MONGO_DATABASE` | `agent` | 库名 | `main.py:42` |
| `MONGO_HISTORY_COLLECTION` | `event_history` | 历史事件集合 | `main.py:43` |
| `MONGO_WORKFLOW_COLLECTION` | `workflows` | Workflow 集合（只读，取 name/端口） | `main.py:44` |
| `MONGO_EVENT_BINDING_COLLECTION` | `event_bindings` | 绑定集合 | `main.py:45` |
| `MONGO_USER` / `MONGO_PASS` | 空 | 有 USER 才启用认证，`authSource="admin"` | `main.py:60-65` |

约定细节：`env()` 用 `os.getenv(name) or fallback`，**空字符串等同未设置**（`main.py:25-26`）；`decode_responses=True`（`main.py:50`）；Redis socket 连接/读写超时各 5s（`main.py:51-52`）；Mongo `serverSelectionTimeoutMS=5000`、`tz_aware=True`（`main.py:54-59`，后者是 `created_at` 带时区序列化的前提）。

### Redis

| 键 | 结构 | 读 | 写 | 语义 | 代码位置 |
| --- | --- | --- | --- | --- | --- |
| `<MAIN_AGENT_QUEUE_NAME>`（默认 `main_agent_queue`） | List，元素为单行紧凑 JSON（`separators=(",",":")`、`ensure_ascii=False`） | `LLEN` 取总数；`LRANGE (len-limit) .. -1` 取**尾部窗口**；`LINDEX -position` 按"从右数第 N 个"定位；`Lua: LINDEX/LSET/LREM` | `RPUSH`（尾插） | **方向要点**：WebUI 用 `RPUSH`（右端入队），而 Agent Worker 用 `BRPOP`（`agent/queue_client.py:65`）从右端弹出 ⇒ 二者构成 **LIFO（栈）语义：最后提交的最先被消费**。这也解释了 UI 文案"已优先入队"。列表**头部是老消息**，尾部是新消息；`position=1` = 队尾 = 下一个被消费的项。对照 `agent/queue_client.py`：`publish_to_queue` 用 `LPUSH`（与 BRPOP 组成 FIFO），`insert_to_queue` 用 `RPUSH`（与 BRPOP 组成 LIFO）——WebUI 采用后者 | `webui_py/events.py:393`（RPUSH）、`:126-128`（LLEN/LRANGE）、`:282`、`:336`；`agent/queue_client.py:31-39`、`:63-69` |
| `<AGENT_WORKER_STATUS_KEY>`（默认 `aagent:worker:status`） | String，JSON 对象 | `GET` → `json.loads` | 由 Agent 侧 `SET` 写入（无 TTL） | 合法形态仅两类：`{"state":"idle","updated_at":ISO}` 与 `{"state":"processing","event":{...},"started_at":ISO}`（`agent/task_worker.py:100-118`）。WebUI 校验：非 JSON→`invalid`；非对象→`invalid`；`state` 不在 `{idle,processing}`→`invalid`；`processing` 缺 `event` 对象→`invalid`；键不存在→`unknown`；读失败→`unavailable`（`events.py:82-99`、`:72-79`）。注意 `processing` 状态**不写 `updated_at`**，这正是前端"idle 超 15s 视为离线"和"processing 超 10 分钟视为卡死"判定的依据（`static/app.js:86-88`） | `webui_py/events.py:82-99`；`agent/task_worker.py:100-118` |

队列项的**指纹**：`event_fingerprint(event)` = FNV-1a 64 位（offset basis `1469598103934665603`、prime `1099511628211`、`&0xFFFFFFFFFFFFFFFF`）作用于 `json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",",":"))`，输出 base36 字符串，`0` 特判为 `"0"`（`events.py:48-61`）。用途有三：pending 项 id、历史与 running 的重复消除、以及 CAS 比对值。64 位空间存在碰撞可能（概率极低）。

### MongoDB

| 集合 | 本服务操作 | 文档形态 | 代码位置 |
| --- | --- | --- | --- |
| `event_history` | `find({}).sort("_id",-1).limit(limit)`（事件流）；`find({"event_type":{"$in":["terminal","response"]}}).sort("_id",-1).limit(limit)`（终端）；`delete_one`；`find_one({"_id"},{"created_at":1})` + `replace_one` | 任意事件 JSON + `created_at`（tz-aware datetime）。对外时**剥离 `_id` 与 `created_at`** 后再作为 `event` 暴露；编辑保存时 `_id` 不变、`created_at` 从旧文档回填、其余字段整体替换 ⇒ 服务端附加字段会被丢弃 | `events.py:155`、`:162`、`:172`、`:361-365`、`:271`、`:321-327` |
| `workflows` | 只读：`find({},{"name":1,"input_ports":1,"output_ports":1}).sort("name",1)`；`find_one({"_id"},{"name":1})` | 取 `name`、`input_ports`、`output_ports`（端口项形如 `{name,type}`，前端缺省类型 `content`） | `event_bindings.py:43`、`:66`；`bindings.js:50-52` |
| `event_bindings` | `find({}).sort("event_type",1)`；`insert_one`；`find_one_and_update($set, AFTER)`；`delete_one`；启动时 `create_index("event_type", unique=True, name="unique_event_binding_type")` 并 drop 遗留索引 `unique_event_binding_route` | `{_id, event_type, workflow_id(ObjectId), workflow_name(str 冗余快照), enabled(bool), created_at, updated_at}`；响应时 `workflow_id` 转字符串、非 ObjectId 则返回 `null` | `event_bindings.py:79`、`:90`、`:107-111`、`:127`、`:25-34`；`main.py:75-82` |

历史排序与重复消除：`history_stage` 按 `_id` 倒序取窗口，用 running 事件的指纹在窗口内查找并**跳过**该条，避免"正在执行"的事件同时出现在历史段；随后整段 `reversed()` 变成时间正序（`events.py:155-184`、`:210`）。终态 items 顺序 = 历史（正序）→ running（0/1 条）→ pending（`position` 1 起、即最新在前）（`events.py:210`、`:223-225`）。

上传/下载接口：**不存在**。`post /api/terminal` 显式拒绝 `files`（`events.py:384-385`），前端固定发送 `files: []`（`api.js:49`）——附件功能是"预留但未实现"。

## 2.9 安全与边界

| 维度 | 事实 | 位置 |
| --- | --- | --- |
| 鉴权 | **完全没有**。无认证依赖、无 Token、无 Session、无 Cookie 校验、无限流；三个中间件分别只做安全头、日志、体积限制 | `main.py:85-125` 全文；`docker-compose.yml:87` 直接发布 8081 |
| CORS | 未配置（无 `CORSMiddleware`）⇒ 仅同源可读；`connect-src 'self'` 进一步限制 | `main.py:88` |
| CSRF | 无显式防护（无 Token、无 SameSite Cookie、无 Origin 校验）。写接口均为 JSON 且 `Content-Type: application/json` 会触发预检，浏览器同源策略+无 CORS 头构成事实上的屏障；但**代码层没有任何主动校验** | `api.js:27-30`、`:47-50`、`:63-66`；`main.py:88` |
| CSP 与安全头 | `default-src/style-src/script-src/connect-src 'self'`、`img-src 'self' data:`、`nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: no-referrer` | `main.py:88-91` |
| XSS 防护 | 全前端仅 **1 处 `innerHTML`**，且是完全静态、无插值的模板字符串（`render.js:167-172`）；其余所有动态文本均走 `textContent`（事件字段、预览、JSON 详情、终端消息、绑定列表、端口名、错误文案）。无 `eval`/`new Function`/`insertAdjacentHTML`/`document.write` | `render.js:85`、`:259-262`、`:270-273`；`terminal.js:85-97`；`bindings.js:50-52`、`:104-124` |
| 注入面 | 无 SQL；Mongo 查询全部使用字面量 dict，无 `$where`；`payload.event` 作为文档体整体写入，服务端只剥离 `_id`/`created_at`，对键名**不做任何前缀/字符校验**（未禁止 `$` 开头或含 `.` 的键），属于潜在脏数据入口 | `events.py:304-311`、`:324-327` |
| 输入长度 | 终端正文 ≤4000 字符；`POST /api/terminal` 体 ≤16 KB；`PUT /api/events` 体 ≤256 KB（中间件按 `Content-Length`，路由内再按序列化后字节数复核）；`limit` 1..300；`event_type` 长度 ≤80 且匹配 `^[a-z][a-z0-9_.-]*$`；`workflow_id` 必须为合法 ObjectId | `events.py:18`、`:382-383`、`:309-311`；`main.py:21-22`、`:109-125`；`common.py:4-7`；`event_bindings.py:13-21`、`:59-65` |
| 体积限制的缺口 | 中间件只看 `Content-Length` **请求头**：分块传输或缺失该头时直接放行到路由（FastAPI 仍会读完整个 body 交给 Pydantic 解析），因此超大 body 的内存消耗只受路由内的业务校验（4000 字符 / 事件 256 KB）间接约束 | `main.py:117-124`；`events.py:309-311`、`:382-383` |
| Pydantic 严格性 | 所有请求体 `model_config = ConfigDict(extra="forbid")` ⇒ 多余字段一律 422；`status` 只接受 `"done"`/`"pending"`，其余返回 400"不支持删除/修改该状态的事件"；删除模型 `DeleteEventRequest` 没有 `event` 字段，若误传 `event` 会因 `extra="forbid"` 被 422 拒绝；更新与删除**共用同一路径** `/api/events`，仅靠方法（PUT/DELETE）区分 | `events.py:22-45`、`:299-300`、`:353`；`event_bindings.py:17-22` |
| 错误处理 | Redis/Mongo 异常一律捕获转 503，附中文文案；队列元素 JSON 解析失败降级为 `{"event_type":"raw","payload":{"raw":<原文>}}` 而非 500（`events.py:64-69`）；worker 状态损坏降级为 `invalid` 而非报错；启动建索引失败只记日志（`main.py:81-82`）。前端 `request()` 统一把 `body.error`、FastAPI `detail[].loc+msg`、`HTTP <status>` 三级降级为 `Error.message` | `api.js:9-14`；`events.py:64-99`、`:129-130`、`:156-157`、`:272-273`、`:328-329`、`:366-367`、`:394-395`；`event_bindings.py:55-56`、`:81-82`、`:94-95`、`:117-118`、`:128-129` |
| 静态资源缓存与版本键 | 服务端对 `.html` 返回 `Cache-Control: no-store`，对 JS/CSS 返回 `no-cache`（每次带 ETag/Last-Modified 校验）。`?v=N` 是**手工维护**的查询串版本键，仅绑定页使用：`bindings.css?v=2`、`bindings.js?v=2`（`bindings.html:9`、`:107`）；事件流页与终端页**没有版本键**，靠 HTML 的 no-store + 资源 no-cache 生效。项目其他子系统同机制自行编号（如 `manager_webui/static/sessions.html:9` 用 `?v=6/7`、`workflow_editor` 用 `?v=16/23`），无统一构建工具注入 | `main.py:143-147`；`bindings.html:9`、`:107` |
| 会话/密钥 | 前端不接触任何密钥、不写 localStorage；Redis 密码只在服务端读取 | `main.py:49` |

## 扩展槽

### 槽 1：新增一个页面（静态页 + 导航）
1. 在 `webui_py/static/` 放 `<name>.html`，复用 `header.topbar` 结构（照抄 `bindings.html:12-25`），CSS 引 `/css/base.css` + 自己的 CSS，并**给 CSS/JS 手工加 `?v=N`**（约定见 `bindings.html:9`、`:107`）。
2. 在**三个**已有页面的 `.page-nav` 各加一个 `<a href="/<name>.html">`（`index.html:19-21`、`terminal.html:19-21`、`bindings.html:19-21`），新页面自身标 `class="active"` + `aria-current="page"`。
3. 写 `<name>.js`，从 `./api.js` 导入接口、必要时 `./auto-refresh.js` 造轮询（照 `terminal.js:154-160` 传 `onResume`）。
4. 无需改后端即可访问（`html=True` 的静态挂载天然服务 `/<name>.html`，`main.py:150`）。
5. 若要整页不滚动 + 独立滚动区，复刻 `body{overflow:hidden}` + `main` flex 骨架（`css/base.css:4`、`:27`）。

### 槽 2：新增一个 API
1. 建 `webui_py/<feature>.py`，导出 `create_<feature>_router(redis_client, history, ...) -> APIRouter` 工厂（模板见 `event_bindings.py:37-38`），把依赖（redis 客户端、Collection）通过参数注入而非模块级 import，便于测试。
2. 请求体一律用 Pydantic + `ConfigDict(extra="forbid")`，字段用 `Field(min_length/max_length)`；错误统一 `JSONResponse(status_code=..., content={"error": "<中文>"})`。
3. 在 `main.py` import 并 `app.include_router(...)`（`main.py:15-16`、`:137-138`）；新集合/键名走 `env(...)` 常量（`main.py:36-45`）。
4. **若方法是 POST/PUT 且需要体积上限**，必须同时改两处：`main.py:21-22` 常量 + `main.py:111-114` 的 `body_limits` 精确匹配表（该表按 `(method, path)` 全字面匹配，带路径参数的 PUT 写不进去）。
5. 前端在 `api.js` 加一个薄包装（照 `api.js:53-79`，统一用 `request()` 以获得 5s 超时 + `no-store` + 错误解析）；不要另写 fetch。

### 槽 3：新增一种事件类型的渲染
事件类型是**自由字符串**，无需注册：
1. 类型筛选下拉会自动纳入新类型（`render.js:62-63` 从快照 `items` 去重排序），空态/计数自动适配。
2. 想要友好预览，只需在 `eventPreview()` 的候选链里加字段：现优先级为 `event.render` → `active` 特判 → `payload.raw_message/content/result/message/tool/raw` → JSON 头 260 字符（`render.js:39-51`）。`event.render` 是**服务端可注入的"预渲染文本"钩子**——事件写入方只要带 `render` 字段就能完全接管预览文案，前端零改动（这是最省事的扩展点）。
3. 若要独立视觉，在 `updateEventRow` 里按 `eventType(item)` 给行/标签加 `data-type` 或类，再在 `event-stream.css` 加选择器（现有依据是 `.event-type` 与 `[data-status=...]`，`css/event-stream.css:67-69`）。
4. 编辑保存对事件类型无白名单（仅要求 `event_type` 为非空字符串，`events.py:307-308`），所以新类型天然可编辑。
5. 终端页是**例外**：只把 `terminal` 当命令、其余一律当响应渲染（`terminal.js:79`、`:95`），且历史接口只取 `event_type ∈ {terminal,response}`（`events.py:362`）；新增终端类角色必须同时改这两处。

### 槽 4：新增一个控件
1. 在对应 HTML 插入元素并给稳定 `id`，在模块顶部的 `elements` 映射里登记（`app.js:7-20`、`terminal.js:5-20`、`bindings.js:9-26`）。
2. 事件监听统一挂在模块底部或初始化函数中（`app.js:135-139`、`terminal.js:131-152`、`bindings.js:197-232`）；需要触发完整刷新的，调 `refresh()`/`refreshStatus()` 而不是自己 fetch，以复用 `state.loading` 互斥与 `autoRefresh.schedule()`。
3. 若控件只影响本地视图（过滤/排序），只调 `renderFilteredEvents()`（`app.js:57`）；若引入新的前端状态，加进 `state` 并在 `renderSnapshot()` 后重放（模式见 `expandedKeys`，`render.js:12`、`:264`）。
4. 加样式时优先复用变量与既有类（`.running-button`、`.icon-button`、`.primary-button`/`.secondary-button`、`.delete-button`、`.empty-state`），并在 `@media (max-width:900px/700px/560px)` 补响应式规则。
5. 纯展示控件放 `.sr-only` 标签或 `aria-live` 区域以维持可访问性（用法见 `index.html:50`、`bindings.html:43`）。

### 槽 5：改后端数据源 / 队列语义 / 配置开关
- 队列名、Worker 状态键、Mongo 库与三个集合名**全部可由环境变量覆盖**，不必改代码（`main.py:29-45`；compose 已传 `MAIN_AGENT_QUEUE_NAME`、`AGENT_WORKER_STATUS_KEY`、`MONGO_*`，`docker-compose.yml:75-85`）。
- 若要改变入队优先级语义，改 **`events.py:393` 的 `RPUSH` 为 `LPUSH`** 即可把"后进先出"变回"先进先出"（与 Worker 的 `BRPOP` 配对）；同时需同步 `pending_stage` 的窗口取值（`LRANGE (len-limit)..-1` 与 `LINDEX -position` 假设"尾部=最新=最优先"）与 `events.py:127-143` 的位置语义，并改 UI 文案"已优先入队"（`terminal.js:117`）与提示"下一项"（`render.js:54`）。
- 提高默认窗口：前端硬编码 `150`（`api.js:21`、`:41`），服务端上限 300（`common.py:5`）——要放大必须同时改两处。
- 新增启动期索引/迁移：加在 `main.py:75-82` 的 startup 钩子内，并沿用"失败只记日志不阻断"的策略（或刻意改为阻断）。
- 事件历史的服务端附加字段（如 ETag/版本号）应加在 `event_history` 文档上，并在 `history_stage`（`events.py:162`、`:172`）的剥离集合与 `events.py:304` 的剥离集合中**同步登记**，否则会被编辑保存悄悄丢掉。

## 2.10 已知边界与风险清单（源码事实）

| # | 事实 | 影响 | 位置 |
| --- | --- | --- | --- |
| 1 | 队列为 `RPUSH` + `BRPOP` = LIFO；`pending` 列表按"距队尾距离"编号 | 大量快速提交时**最早的消息可能长期不被消费**；UI"优先入队"文案虽准确但语义反直觉 | `events.py:393`、`:126-143`；`agent/queue_client.py:65` |
| 2 | `pending` 的 `position`/`fingerprint` 是**读时快照** | 两次轮询之间队列变化会让删除/编辑撞 409；前端只提示"请刷新后重试"，不自动重试 | `events.py:287-288`、`:341-342`；`app.js:189`、`:223` |
| 3 | 历史事件编辑走 `replace_one`，无版本字段 | 并发编辑 = 后写覆盖；`event_history` 文档上除 `created_at` 外的服务端附加字段会在保存时丢失 | `events.py:324-327` |
| 4 | 全站无鉴权 + 8081 直接发布到宿主 | 同网段任意客户端可发终端指令、删改事件历史与绑定配置 | `main.py:85-125`；`docker-compose.yml:87` |
| 5 | 体积上限只校验 `Content-Length` 头 | 无该头/分块请求可绕过中间件（路由内仍会拒绝超长业务字段） | `main.py:117-124` |
| 6 | `expandedKeys` 与 `state.seen` 为只增 Set，无清理/上限 | 长会话（尤其常驻终端页）内存单调增长 | `render.js:12`；`terminal.js:4` |
| 7 | `#sendButton` 在内容为空或正在发送时**静默返回**，无任何提示 | 空内容提交时用户得不到反馈 | `terminal.js:104` |
| 8 | `#saveBinding` 的 `disabled` 由两处独立维护：`renderWorkflows` 按"有无 Workflow"设置，而表单提交的 `finally` 无条件置 `false` | 同一按钮存在两个状态源，"无 Workflow 不可保存"这一约束可能被 `finally` 清掉（能否真正提交还取决于浏览器对 disabled 默认提交按钮的隐式提交处理）；建议二选一收敛 | `bindings.js:147` vs `:229-231` |
| 9 | 绑定页不参与轮询 | 其他客户端/Workflow 侧改动不会反映，需手动刷新页面 | `bindings.js:180-195`（无 auto-refresh import） |
| 10 | 无 API 路由的 404 由静态挂载返回**纯文本** `Not Found` | 前端 `request()` 的 `response.json()` 失败后兜底为 `{}`，错误信息退化为 `HTTP 404` | `main.py:150`；`api.js:8`、`:13` |
| 11 | 事件流首屏定位与锚点恢复都以 `runningSection.offsetTop`/最近行为基准，`#runningButton` 用 1.2s 时间窗抑制回写 | 高频刷新 + 手动平滑滚动期间可能仍有轻微跳动；抑制窗外的用户滚动会被锚点恢复覆盖 | `app.js:68-77`、`:136-139` |
| 12 | `summary.history` 是窗口内条数而非全量历史条数 | 状态条"已加载历史"数值随 `limit` 变化，不能当作总量 | `events.py:207`、`:155` |
| 13 | 终端字符计数 `[...value].length`（码点）与 `maxlength`（UTF-16 码元）口径不同 | 含 emoji 时浏览器可能在未达 4000 显示值前截断输入 | `terminal.js:44`；`terminal.html:63` |
| 14 | 启动建索引失败只记日志 | 若 MongoDB 启动期不可用，`event_type` 唯一约束缺失，可产生重复绑定，直至下次重启 | `main.py:75-82` |
