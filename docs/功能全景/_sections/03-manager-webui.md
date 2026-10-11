# 03 管理 WebUI（manager_webui，:8084）

> 类型:审计报告（分节草稿）。
> 性质:现行文档。
> 归属:`manager_webui/`。
> 适用版本:平台 `0.1.0+`。

`manager_webui/` 是一个 FastAPI 单进程服务（`docker-compose.yml:96-129`，`uvicorn main:app --port 8084`），同时承担三类职责：

1. **管理 API 后端**：Workflow 元数据/画布、文档、模型注册表、Session 存储、事件目录、健康检查（`manager_webui/main.py:145-159`）。
2. **静态管理台**：5 个页面 + 8 个 JS 模块 + 6 个 CSS 文件，全部由 `StaticFiles(html=True)` 挂在根路径（`manager_webui/main.py:161-176`）。
3. **契约守门人**：在写入 Workflow 前对节点类型、端口、连接类型、Tool 注册表（Redis）、模型注册表（MongoDB）做全量交叉校验（`manager_webui/workflows.py:785-953`）。

> 注意区分三个 WebUI：`webui_py/`（8081 运行态事件流）、`workflow_editor/`（8082 画布编辑器，写入同一 `workflows` 集合）、`manager_webui/`（8084 只读管理台）。本节只覆盖 `manager_webui/`。

---

## 3.1 进程装配、中间件与静态服务

### 3.1.1 配置与环境变量

| 变量 | 默认值 | 代码位置 |
| --- | --- | --- |
| `REDIS_ADDR`（优先）/ `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` / `REDIS_PASSWORD` | —/`redis`/`6379`/`0`/空 | `main.py:34-42,54` |
| `AGENT_TOOLS_KEY` | `aagent:tools` | `main.py:43` |
| `MONGO_HOST` / `MONGO_PORT` / `MONGO_DATABASE` / `MONGO_USER` / `MONGO_PASS` | `mongodb`/`27017`/`agent`/空/空 | `main.py:44-46,65-70` |
| `MONGO_DOCUMENT_COLLECTION` | `documents` | `main.py:47` |
| `MONGO_MODEL_COLLECTION` | `models` | `main.py:48` |
| `MONGO_WORKFLOW_COLLECTION` | `workflows` | `main.py:49` |
| `MONGO_SESSION_COLLECTION` | `sessions` | `main.py:50` |
| `TOOL_CLIENT_MAX_WAIT_MS` / `TOOL_CLIENT_MAX_ASYNC_TIMEOUT_MS` | `10000` / `3600000` | `workflows.py:858-859` |

Redis 客户端 `decode_responses=True`，连接/读写超时均 5s（`main.py:52-58`）；Mongo 客户端 `serverSelectionTimeoutMS=5000`、`tz_aware=True`（`main.py:59-64`），全库统一 UTC（`documents.py:61`、`models.py:64`、`workflows.py:562`、`sessions.py:82-84`）。

### 3.1.2 启动钩子与索引

`@app.on_event("startup") create_config_indexes()`（`main.py:81-91`）执行 4 件事：

1. `model_configs.create_index("name", unique=True, name="unique_model_name")`（`main.py:84`）
2. 若存在历史 `unique_workflow_key` 索引则 drop，并 `update_many` 清除所有 `key` 字段（`main.py:85-87`，Workflow 主键从 `key` 迁移到 `name`）
3. `workflows.create_index("name", unique=True, name="unique_workflow_name")`（`main.py:88`）
4. `sessions.create_index("updated_at", name="session_updated_at")`（`main.py:89`，非唯一、无 TTL）

失败仅记 `logger.error`，不阻断启动（`main.py:90-91`）。

### 3.1.3 三个 HTTP 中间件（顺序为注册逆序执行）

| 中间件 | 代码位置 | 行为 |
| --- | --- | --- |
| `request_body_guard` | `main.py:118-142` | 按路径前缀检查 `Content-Length`，超限直接 400 |
| `request_logger` | `main.py:104-115` | 仅对 `/api/*` 记 method/path/耗时 |
| `security_headers` | `main.py:94-101` | 注入 4 个安全响应头 |

请求体上限常量（`main.py:24-27`）：

| 路径匹配 | 上限 | 错误文案 |
| --- | --- | --- |
| `POST/PUT /api/documents[/...]` | 1 MB | 文档请求体不能超过 1 MB |
| `POST/PUT /api/models[/...]` | 16 KB | 模型配置请求体不能超过 16 KB |
| `PUT /api/workflows/{id}` | 512 KB | Workflow 请求体不能超过 512 KB |
| `POST/PUT /api/sessions*` | 1 MB + 4096 | Session 请求体不能超过 1 MB |

注意：`PUT /api/workflows/{id}/metadata` **不**受 `MAX_WORKFLOW_BODY_BYTES` 保护（`main.py:129` 要求路径以 `/api/workflows/` 开头且方法为 PUT，实际会命中——因 `/metadata` 也在该前缀下；但 `POST /api/workflows` 建表请求无体积限制）。

安全响应头（`main.py:97-100`）：

```
Content-Security-Policy: default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
```

CSP 说明：`script-src 'self'` 禁内联脚本，因此所有页面逻辑必须在外部 JS 模块中；`img-src 'self' data:` 允许内联 SVG `data:` URI。

### 3.1.4 静态资源与缓存策略

`RevalidatingStaticFiles`（`main.py:169-173`）覆写 `get_response`：`*.html` 用 `Cache-Control: no-store`（`main.py:172`），其他资源（js/css/svg/字体）用 `no-cache`（强制条件请求，可 304）。

挂载点 `/`、`html=True`（`main.py:176`），因此 5 个 `.html` 都直接由静态目录提供，**没有单独的路由函数**；根路径 `/` 显式返回 `workflows.html`（`main.py:164-166`，`include_in_schema=False`）。

前端手写版本键（唯一的缓存破坏手段）：

| 资源 | 版本键 | 代码位置 |
| --- | --- | --- |
| `document.js` | `?v=documents-4` | `static/document.html:75` |
| `api.js`（被 document.js 导入） | `?v=documents-4` | `static/document.js:1` |
| `sessions.css` | `?v=6` | `static/sessions.html:9` |
| `sessions.js` | `?v=7` | `static/sessions.html:41` |

`workflows.js`、`model.js`、`events.js`、`workflow_canvas.mjs` 与其余 CSS **无版本键**，依赖 `no-cache` 条件请求生效。

---

## 3.2 API 路由全表

### 3.2.1 页面与基础设施路由

| 方法 | 路径 | 参数 | 响应 | 用途 | 位置 |
| --- | --- | --- | --- | --- | --- |
| GET | `/` | — | `workflows.html`（FileResponse） | 管理台首页重定向到 Workflow 页 | `main.py:164-166` |
| GET | `/{任意静态路径}` | — | 文件或 404 | `StaticFiles(html=True)`，提供 5 个 HTML、8 个 JS、6 个 CSS | `main.py:176` |
| GET | `/api/health` | — | `{"status":"ok"}` / 503 `{"status":"unavailable","error":...}` | Redis `ping` + Mongo `admin.command("ping")` 双探活；compose healthcheck 调它 | `main.py:145-152` |

### 3.2.2 Workflow（`workflows.py`）

| 方法 | 路径 | 参数 | 成功响应 | 失败响应 | 用途 | 位置 |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/api/workflows` | — | `{items:[{id,name,description,version,node_count,connection_count,input_ports,output_ports,workflow_nodes,remote_tools,created_at,updated_at}]}`，按 `updated_at` 倒序 | 503 `Workflow 列表暂时不可用` | 列表页数据源；`node_count`/`connection_count` 为服务端 `len()` 计算，不返回完整画布 | `workflows.py:528-555` |
| POST | `/api/workflows` | body `{name}`（`WorkflowCreateRequest`，extra=forbid） | 201 完整 `workflow_response` | 400 名称空 / 409 名称已存在（预查 + `DuplicateKeyError` 双保险）/ 503 | 新建空 Workflow，自动生成 Input+Output 两节点与一条 control 连接 | `workflows.py:557-597` |
| GET | `/api/workflows/{workflow_id}` | path ObjectId | `workflow_response`（含完整 nodes/connections） | 400 `Workflow id 无效` / 404 / 503 | 详情 + 画布渲染数据源 | `workflows.py:605-616` |
| PATCH | `/api/workflows/{workflow_id}` | body `{name}` | `workflow_response` | 400 / 404 / 409 / 503 | 仅重命名；成功后级联更新其他 Workflow 里引用旧名的 `workflow_nodes[].name` 与 `nodes[].arguments.workflow_name`（array_filters 双路径） | `workflows.py:618-662` |
| PUT | `/api/workflows/{workflow_id}/metadata` | body `{input_ports[],output_ports[],workflow_nodes[],remote_tools[]}`（`WorkflowMetadataRequest`） | `workflow_response` | 400（端口重名/Remote Tool 重名或重名端口/引入自身/引入不存在）/ 404 / 503 | 只改边界契约，并自动**同步**节点 `workflowPorts`、重写 `workflow` 节点端口快照、删除失效连接 | `workflows.py:664-770` |
| PUT | `/api/workflows/{workflow_id}` | body `WorkflowRequest`（name/description/version/input_ports/output_ports/nodes/connections，全部 extra=forbid） | `workflow_response` | 400（十余种校验）/ 404 / 409 / 503 | 保存完整画布；先做契约一致性校验，再同步端口、过滤非法连接后落库 | `workflows.py:785-953` |
| DELETE | `/api/workflows/{workflow_id}` | path ObjectId | `{deleted:true,id}` | 400 / 404 / 503 | 删除 Workflow（不级联清理引用它的其他 Workflow） | `workflows.py:772-783` |

`workflow_response` 字段契约（`workflows.py:503-517`）：`id`(str)、`name`、`description`、`version`、`nodes`、`connections`、`input_ports`、`output_ports`、`workflow_nodes`、`remote_tools`、`created_at`、`updated_at`。**不含 `key` 字段**（已迁移废弃）。

### 3.2.3 文档（`documents.py`，`prefix="/api/documents"`）

| 方法 | 路径 | 参数 | 成功响应 | 失败响应 | 用途 | 位置 |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/api/documents` | — | `{items:[document_response(include_content=false)]}`，按 `updated_at` 倒序 | 503 | 列表，投影排除 `content` 省流量 | `documents.py:46-54` |
| POST | `/api/documents` | body `{title,content}` | 201 含 content | 400 标题空 / 503 | 新建，`pinned` 强制 false | `documents.py:56-68` |
| GET | `/api/documents/{id}` | path ObjectId | 含 content | 400 `文档 ID 无效` / 404 / 503 | 详情 | `documents.py:70-81` |
| PUT | `/api/documents/{id}` | body `{title,content}` | 含 content | 400 / 404 / 503 | 全量覆盖，**不修改 `pinned`** | `documents.py:83-102` |
| PATCH | `/api/documents/{id}/pin` | body `{pinned: bool}` | 含 content | 400 / 404 / 503 | 切换钉住；注意**不更新 `updated_at`** | `documents.py:104-119` |
| DELETE | `/api/documents/{id}` | path ObjectId | `{deleted:true,id}` | 400 / 404 / 503 | 删除 | `documents.py:121-132` |

`document_response`（`documents.py:30-40`）：`id`、`title`、`pinned`(bool 强转)、`created_at`、`updated_at`，可选 `content`。

### 3.2.4 模型注册表（`models.py`，`prefix="/api/models"`）

| 方法 | 路径 | 参数 | 成功响应 | 失败响应 | 用途 | 位置 |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/api/models` | — | `{items:[model_response]}`，按 `updated_at` 倒序 | 503 | 列表（返回完整 `api_key`，见 §3.10.3 S2） | `models.py:51-57` |
| POST | `/api/models` | body `ModelRequest` | 201 `model_response` | 400（四字段非空校验）/ 409 名称已存在 / 503 | 新建；`base_url` 自动 `rstrip("/")` | `models.py:59-75` |
| PUT | `/api/models/{id}` | body `ModelRequest` | `model_response` | 400 / 404 / 409 / 503 | 全量覆盖（含 api_key 与 enabled） | `models.py:77-100` |
| DELETE | `/api/models/{id}` | path ObjectId | `{deleted:true,id}` | 400 / 404 / 503 | 删除；**不检查是否被 Workflow 的 LLM 节点引用** | `models.py:102-113` |

字段约束（`models.py:14-22`、`39-45`）：`name`≤120、`provider`≤120、`model`≤200、`base_url`≤500、`api_key`≤1000（可空）、`enabled` 默认 true。空值校验文案统一为「模型名称、厂商、模型标识和 Base URL 不能为空」（`models.py:62-63`）。

> 注意 `update_model` 复用 `parse_object_id(..., "文档 ID 无效")`（`models.py:79`），错误文案沿用了「文档」字样。

### 3.2.5 Session（`sessions.py`，`prefix="/api/sessions"`）

| 方法 | 路径 | 参数 | 成功响应 | 失败响应 | 用途 | 位置 |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/api/sessions` | `limit`(1-100，默认 50)、`cursor`(base64)、`q`(≤100) | `{items:[{id,value_type,created_at,updated_at}],next_cursor}` | 400 `Session 游标无效` / 503 | 键集分页（`updated_at` DESC, `_id` DESC 复合排序）；`q` 走 `_id` 前缀正则（`re.escape` 转义） | `sessions.py:90-127` |
| GET | `/api/sessions/{session_id}` | path 字符串 | `{id,value_type,value,created_at,updated_at}` | 404 / 503 | 详情（含 value） | `sessions.py:129-137` |
| POST | `/api/sessions` | body `{value_type,value,updated_at?}` | 201 含 value | 400 `Session Value 无效`/`Session Value 过大` / 503 | 新建，`_id` 服务端生成 `ses_{uuid4().hex}` | `sessions.py:139-156` |
| PUT | `/api/sessions/{session_id}` | body `{value_type,value,updated_at}` | 含 value | 400（值无效/过大/`updated_at 不能为空`）/ 404 / 409 乐观锁冲突 / 503 | 乐观并发：`filter={_id,value_type,updated_at}` 精确匹配，`updated_at` 单调递增（`max(now, 传入+1ms)`） | `sessions.py:158-178` |
| DELETE | `/api/sessions/{session_id}` | path 字符串 | `{deleted:true,id}` | 404 / 503 | 删除 | `sessions.py:180-188` |

游标编解码（`sessions.py:101-108`、`126`）：`base64.urlsafe_b64encode(json.dumps([updated_at.isoformat(), last_id]))`；解码时校验 `ses_[0-9a-f]{32}` 正则（`sessions.py:19`）并强制 `tzinfo` 非空。

### 3.2.6 事件目录（`event_catalog.py`）

| 方法 | 路径 | 参数 | 响应 | 用途 | 位置 |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/event-catalog` | — | `{"items":[...7 项...],"count":7}`（`deepcopy` 保护源数据） | 返回硬编码事件目录，无数据库依赖 | `event_catalog.py:196-206` |

---

## 3.3 Workflow 管理页（`workflows.html` / `workflows.js`，路由 `/` 与 `/workflows.html`）

### 3.3.1 用途与布局

只读管理台：**不含画布编辑能力**，只做列表浏览、契约检视、依赖改名、导入导出、重命名与删除。三行布局：

| 区域 | DOM | 说明 |
| --- | --- | --- |
| 顶栏 | `header.topbar` | 品牌链接 + `.page-nav` 五页导航 + `#workflowState` 状态徽标（`aria-live=polite`） |
| 左列表 | `aside.workflow-management-sidebar` | `#workflowList`，卡片按钮动态生成 |
| 右配置区 | `section.workflow-configuration` | `#workflowEmpty` 空态 + `#metadataPanel` 详情面板 |

详情面板内部区块顺序（`workflows.html:65-105`）：描述 → 完整画布预览 → 数据端口（Input/Output 双列）→ Workflows 依赖与契约 → Remote Tool 依赖与契约。

### 3.3.2 数据加载链路

1. 页面加载末尾直接调用 `loadWorkflows()`（`workflows.js:799`）。
2. `GET /api/workflows` → `state.workflows`，若当前选中项已消失则自动选中第一项（`workflows.js:404-408`）。
3. `renderList()` 生成卡片按钮，文案 `"{name}"` + `"{node_count} 节点 / {connection_count} 连接"`（`workflows.js:381-394`）。
4. `renderConfiguration()` 渲染右侧；`renderCanvasPreview(workflow.id)` 额外发 `GET /api/workflows/{id}`，结果缓存在 `state.workflowDetails` Map（`workflows.js:331-339`），重命名/覆盖/删除时 `delete` 失效（`workflows.js:279`、`607`、`635`、`755`）。
5. 状态徽标文案集合：`读取中` → `共 N 个` / `读取超时` / `不可用`（`workflows.js:400-413`）。

### 3.3.3 只读画布 `workflow_canvas.mjs`

`workflowCanvasSvg(workflow)` 是**纯函数式 SVG 生成器**，返回字符串（`workflow_canvas.mjs:138-189`）：

| 步骤 | 实现 | 位置 |
| --- | --- | --- |
| 坐标归一 | `renderX = x - minX + 56`，`renderY = y - minY + 56 + 54`（预留 54px 标题带） | `workflow_canvas.mjs:141-147` |
| 画布尺寸 | `width=max(720, max(renderX+190+56))`，`height=max(360, max(renderY+nodeHeight+56))` | `workflow_canvas.mjs:149-150` |
| 端口推导 | `contractPortIds(node, direction, workflow)` 为 **21 种**节点类型静态推导输入/输出端口集合（覆盖 24 种节点中除 `construct_map_content`、`map_content_get`、`session_*` 外的全部类型） | `workflow_canvas.mjs:54-101` |
| 端口行号 | `endpointRows` 取"实际有连接"的端口，按契约顺序排序；未在契约中的端口排最后 | `workflow_canvas.mjs:103-115` |
| 端口坐标 | `x = renderX + (output?190:0)`，`y = renderY + 52 + row*18` | `workflow_canvas.mjs:117-124` |
| 连线路径 | 三次贝塞尔，控制点偏移 `max(42, |Δx|*0.45)`；control 实线，数据线 `stroke-dasharray="6 5"` | `workflow_canvas.mjs:126-129,159-160` |
| 节点高度 | `max(86, 64 + max(入端口数,出端口数)*18)` | `workflow_canvas.mjs:131-136` |
| 转义 | `escapeXml` 转 `& < > " '`；`safeCoordinate` 把非有限数归 0 | `workflow_canvas.mjs:36-44` |
| 配色 | `TYPE_COLORS` 18 种节点色 + `CONNECTION_COLORS` 7 种连接色 | `workflow_canvas.mjs:5-34` |

交互约束：生成物是**死 SVG**——无 `pointer-events`、无 JS 事件绑定、无缩放/平移/选中逻辑。`workflows.js:322-329` 用 `DOMParser` 解析后**主动移除 `<style>` 节点**、设 `preserveAspectRatio="xMidYMid meet"`；`workflows.js:351-356` 裁剪顶部 54px 标题带并计算预览比例：`ratio = viewBox.width / max(1, viewBox.height - 54)`，`viewBox` 上移 54，`--preview-width = min(760, 420*ratio)`。CSS 侧 `.workflow-canvas-preview-stage` 用 `aspect-ratio: var(--preview-ratio)` + `overflow:hidden` + `max-height:420px`（`css/workflows.css:58`），并隐藏标题带与端口文字（`css/workflows.css:64-65`）。空态文本「正在生成完整画布...」/「画布读取超时」/「画布读取失败」（`workflows.js:345,361`）。

### 3.3.4 依赖与契约快照展示

`renderDependencies(references)`（`workflows.js:123-165`）为每个 `workflow_nodes` 条目渲染：

| 元素 | 内容 | 位置 |
| --- | --- | --- |
| 徽标 | `<span>WF</span>`（`metadata-port-mark workflow`） | `workflows.js:139-141` |
| 名称 | `reference.name \|\| reference.workflow_name`，空则「未命名 Workflows」 | `workflows.js:143-144` |
| 「修改」按钮 | `dependency-edit-button`，`title="修改依赖 Workflows"` | `workflows.js:146-152` |
| 契约双列 | Input/Output 两个 `dependency-contract`，各含端口行 | `workflows.js:153-158,87-100` |
| 契约告警 | `samePortContract` 比较快照与当前 Workflow 的 `{name,type}` 序列；不一致时插入红色告警「契约错误：Input、Output 端口与对应 Workflows 不一致」 | `workflows.js:102-121` |

`renderRemoteTools(references)`（`workflows.js:167-199`）：徽标 `RT`、名称、Input/Output 契约；**没有「修改」按钮**，依赖项为只读。计数徽标 `{N} 项` 或空态「无 Workflows 依赖」/「无 Remote Tool 依赖」（`workflows.js:126-131,170-175`）。

### 3.3.5 依赖改名内联编辑器

点击「修改」调用 `editDependency`（`workflows.js:201-246`）：就地替换 header 为 `<input class="dependency-name-input" maxlength=120>` + 「保存/取消」；`input` 事件实时校验 `!name || !exists || duplicate`（目标 Workflow 不存在，或与同列表其他依赖重名）→ 保存禁用、输入框加 `.invalid`；「取消」整块重渲染；「保存」名称未变则重渲染，否则走 `saveDependency`；自动 `focus()`+`select()`。

`saveDependency(references, previousName, nextName)`（`workflows.js:248-289`）：

1. 本地查目标 Workflow 存在性 → 不存在则状态栏「依赖 Workflows 不存在，无法保存」，不发请求。
2. 构造新 `nextReferences`：改名项带 `previous_name`（对应 `WorkflowNodeReference.previous_name`，`workflows.py:244`，供后端做节点级联改名），端口快照原样带过去。
3. 本地查重：重名 → 「依赖 Workflows 不能重复」。
4. `PUT /api/workflows/{id}/metadata`，`input_ports`/`output_ports` 必须回传原值（后端校验逐字段相等，见下）。
5. 成功：合并返回值、`workflowDetails.delete`、状态「依赖已更新」、重渲染；失败展示 `error.message`，`AbortError` 时「保存依赖超时」。

**契约一致性陷阱**：后端在两条写入路径都要求提交的 `input_ports`/`output_ports` 与库中值**逐字段相等**（`workflows.py:704-705,826-830`），所以前端必须回传当前值而不能重算。

### 3.3.6 导入（文件 / 文本）

两条入口共用 `prepareWorkflowUpload(imported)`（`workflows.js:485-493`）：写入 `state.pendingUpload`、预填名称、`validateUploadName()`、打开 `#uploadDialog`、聚焦并全选名称。

- **文件导入**：`#uploadButton` → `#uploadFileInput.click()`（`workflows.js:769`）→ `change` → `chooseWorkflowFile()`（`workflows.js:495-505`）。`accept="application/json,.json"`（`workflows.html:35`）。读 `file.text()` 后由 `parseWorkflowText`（`workflows.js:477-483`）校验：非数组对象、`name` 非空字符串、`nodes`/`connections` 为数组。成功后**立即清空** `value`（`workflows.js:497`）允许重复选同一文件；失败则状态栏显示消息并清 `pendingUpload`。
- **文本导入**：`#textImportButton` → `openTextImportDialog()`（`workflows.js:507-521`）清空输入与错误后 `showModal()`，再尝试 `navigator.clipboard.readText()` 预填，但**必须先通过 `parseWorkflowText` 校验**才填入（`workflows.js:511-515`），并跳过 `NotAllowedError`/`SyntaxError`（`workflows.js:516-518`）。`submitTextImport`（`workflows.js:523-533`）解析成功则关窗并 `prepareWorkflowUpload`，失败写入 `#textImportError`。
- **引用解析** `resolveWorkflowReferences`（`workflows.js:454-475`）：把 `workflow_id` 或 `name` 解析为库中**唯一匹配**的 Workflow；无匹配抛「找不到被调用 Workflows“X”」、多匹配抛「名称不唯一」、节点映射缺失抛「节点“X”引用的 Workflows 不存在」；最终**剥离 `workflow_id`** 只留 `workflow_name`（后端只认名字，`workflows.py:463,473-475`）。
- **上传确认** `confirmWorkflowUpload`（`workflows.js:535-580`）三步串行：`POST /api/workflows {name}` 建空壳 → `PUT .../metadata` 写契约 → `PUT .../{id}` 写完整 `description`/`version`/`nodes`/`connections`（`version` 非 ≥1 整数则兜底为 1）；任一步失败且已创建 → 尝试 `DELETE` 回滚（失败仅 `console.warn`）。
- **覆盖** `overwriteWorkflow`（`workflows.js:582-621`）：同名已存在时「覆盖」可用；流程为 `metadata` + 完整 `PUT`，**不创建**，失败不回滚。

### 3.3.7 导出三态与剪贴板降级

| 功能 | 函数 | 实现 | 文件名规则 |
| --- | --- | --- | --- |
| 导出到剪贴板 | `copySelectedWorkflow`（`workflows.js:679-695`） | `GET /api/workflows/{id}` → `exportableWorkflow()` → `writeClipboardText(JSON.stringify(...))` | 无 |
| 导出 JSON 文件 | `exportSelectedWorkflow`（`workflows.js:697-721`） | `Blob(JSON.stringify(exported,null,2)+"\n", application/json)` → 临时 `<a download>` → `click()` → `revokeObjectURL` | `{name}-{YYYY-MM-DD}.json`，`name` 中 `[<>:"/\|?*]+`→`-`、空白→`-`（`workflows.js:709-711`） |
| 导出画布 SVG | `exportSelectedCanvas`（`workflows.js:723-745`） | 复用缓存详情 → `workflowCanvasSvg` → `Blob(image/svg+xml)` | `{safeName}-{YYYY-MM-DD}-canvas.svg`（`workflow_canvas.mjs:191-194`） |

`exportableWorkflow(detail)`（`workflows.js:648-660`）字段顺序固定为 `name, description, version, input_ports, output_ports, workflow_nodes, remote_tools, nodes, connections`——与导入端 `parseWorkflowText` 期望对齐，构成可往返格式。`writeClipboardText`（`workflows.js:662-677`）降级链：`navigator.clipboard.writeText` → 屏幕外只读 `<textarea>` + `document.execCommand('copy')` → 抛「浏览器不允许访问剪贴板」。

### 3.3.8 键盘与对话框行为

- 对话框统一用原生 `<dialog>` + `showModal()`，**Esc 关闭**由浏览器原生提供（无显式 `keydown` 监听）。
- 三个对话框的关闭按钮都带 `data-close-dialog`，统一循环绑定（`workflows.js:789-798`）：关闭 `#uploadDialog` 且非保存中时清 `pendingUpload` 并重置 `uploadMode`；`#uploadDialog` 另有 `close` 事件兜底（`workflows.js:777-782`）。
- 校验时机：`#uploadName`/`#renameName` 均为 `input` 实时校验（`workflows.js:773-774`）；提交时再调 `reportValidity()`（仅 rename，`workflows.js:626`）。
- **注意**：Workflow 页无 `localStorage` 草稿逻辑；`removeSelectedWorkflow` 里的 `localStorage.removeItem('aagent.workflow.draft.v1.'+id)`（`workflows.js:756`）实际是清理 `workflow_editor/`（8082）遗留的草稿键。

---

## 3.4 文档页（`document.html` / `document.js`，`/document.html`）

### 3.4.1 用途与布局

Markdown / 纯文本的轻量笔记库，三行结构（`document.html:29-73`）：

| 区域 | 内容 |
| --- | --- |
| 左栏 `aside.document-sidebar` | 标题「文档库」+「上传」+「+」+ 隐藏 file input + `#documentList` |
| 右侧 `section.document-editor` | `#documentTitle`（禁用态标题输入）+ `#documentId` + `#updatedAt` + 钉住/下载/删除 + 编辑区 + 底部状态栏 |
| 底部 `footer.editor-actions` | `#saveStatus`（`role=status`）+ `#characterCount` + `#cancelButton` + `#editButton` |

数据来源：`GET /api/documents`（列表，无 content）与 `GET /api/documents/{id}`（详情，有 content）。

### 3.4.2 双模式与脏状态

`state.mode` 只有两个取值（`document.js:3`）：`preview` 显示 `#documentPreview`（`<pre>` + `textContent`，`white-space:pre-wrap`）；`edit` 显示 `#documentContent` 且 `#documentTitle` 可编辑。进入 `edit` 的入口是「编辑」按钮、新建文档、导入单文件；回到 `preview` 是选中文档、保存成功、取消编辑。

脏状态：`state.saved` 存"进入编辑时的 `{title:trim, content}`"快照（`document.js:166`），`isChanged()` 逐字段比较（`document.js:40-43`）。三个动作前有确认弹窗：切换文档 `document.js:215`、新建文档 `document.js:233`、上传并打开新文档（仅单文件 `selectImported=true`）`document.js:82`，文案统一为「当前修改尚未保存，仍要…吗？」。

- **没有 `beforeunload` 监听**（与 sessions.js 不同），关闭标签页不会提示。
- **保存可用性**（`document.js:58-60`）：编辑模式下「保存」按钮仅在 `isChanged() && title.trim()` 时可用。

### 3.4.3 CRLF / 编码处理

- 前端不做任何换行规范化：`file.text()` 原样读入（`document.js:92`），`textarea.value` 原样提交（`document.js:37`）；服务端只限制 `content` 长度 1,000,000 字符（`documents.py:21`），不转换换行。
- **结论**：CRLF 完全由浏览器/编辑器行为决定，全链路无 `\r\n`→`\n` 归一化。
- 相关细节：`#documentContent` 带 `spellcheck="false"`（`document.html:61`）；文本域 CSS 用重复线性渐变模拟行线（`css/document.css:47`，`background-size:100% 28px` + `background-attachment:local`），行高与行线严格对齐 28px；`PATCH /pin` 不改 `updated_at`（`documents.py:110-114`），钉住不打乱排序。

### 3.4.4 批量导入

`importMarkdownFiles(fileList, selectImported)`（`document.js:79-116`）：

- 入口 `#uploadInput`（`accept=".md,.txt,text/markdown,text/plain"`、`multiple`、`class="sr-only"`，`document.html:38`）；`selectImported` = 文件数恰为 1（`document.js:330`），单文件导入后自动切 `preview` 并打开，多文件只刷新列表。
- 逐文件流程：`validateMarkdownFile` 校验扩展名（`/\.(md|txt)$/i`，`document.js:76`）→ `file.text()` → 前端校验 `[...content].length > 1_000_000` 抛「正文超过 100 万字符」→ `createDocument(markdownTitle(file.name), content)`。
- `markdownTitle`：去 `.md`/`.txt` 后缀 → `trim()` → 空则「未命名文档」→ 按码点截断到 200（`document.js:70-73`，与后端 `MAX_DOCUMENT_TITLE_CHARS=200` 对齐）。
- **逐文件容错**：单文件失败记入 `failures`，其余继续（`document.js:95-97`）。进度文案 `正在上传…` / `正在导入 i/N…`；结束汇总「上传完成」/「已导入 N 个文档」（success）或「已导入 N 个，失败 M 个：…」（error），状态徽标降级「部分同步」（`document.js:109-114`）。
- 列表插入 `state.documents.unshift(...imported.reverse())`（`document.js:101`）保持倒序一致；导入完清空 `uploadInput.value`（`document.js:331`）。

### 3.4.5 下载、列表标记与元信息

- **下载** `downloadCurrentDocument()`（`document.js:118-131`）：内容取编辑态 `#documentContent.value` 或 `state.current.content`；文件名净化两步——`[<>:"/\\|?*\u0000-\u001f]`→`_`，再去掉结尾的 `.` 与空格（`document.js:121-123`）；固定 `.md`，`Blob(text/markdown;charset=utf-8)` 触发下载，状态「下载已开始」。
- **列表标记** `renderList()`（`document.js:133-160`）：每项 `<button class="document-item">`，选中项加 `.active`（CSS 左侧 `inset 3px 0` 绿条）。`pinned` 为真时标题后插 `<span class="document-pin">钉住</span>`（`document.js:148-153`）。次行显示 `更新于 {zh-CN 本地时间}`。空态「还没有文档」。
- **元信息历史遗留**：`#updatedAt` 显示的是 `formatDate(created_at, '创建于')`（`document.js:169`）——**实际展示创建时间而非更新时间**。

---

## 3.5 模型注册表（`model.html` / `model.js`，`/model.html`）

### 3.5.1 用途与布局

单页双列：左 `#modelForm`（新建/编辑共用表单），右 `#modelItems`（`auto-fill minmax(240px,1fr)` 网格卡片）。顶部 `#modelState` 显示「N 个模型」。

### 3.5.2 字段与约束

| 字段 | 控件 | 前端约束 | 后端约束 | 备注 |
| --- | --- | --- | --- | --- |
| `name` | `<input id=modelName>` | `maxlength=120`、`required` | `min_length=1,max_length=120` | 唯一索引（`main.py:84`）；重复 → 409「模型名称已存在」 |
| `provider` | `<input id=modelProvider>` | `maxlength=120`、`required` | 同上 | 仅展示用，不参与调用 |
| `model` | `<input id=modelModel>` | `maxlength=200`、`required` | 同上 | 直接作为 OpenAI 请求的 `model` 字段（`agent/llm.py:69`） |
| `base_url` | `<input id=modelBaseUrl type=url>` | `maxlength=500`、`required`、浏览器 URL 校验 | `min_length=1,max_length=500` | 落库前 `strip().rstrip("/")`（`models.py:44`） |
| `api_key` | `<input id=modelApiKey type=password autocomplete=new-password>` | `maxlength=1000` | `default=""`，可空 | 明文存储、明文回传（§3.10.3 S2） |
| `enabled` | `<input id=modelEnabled type=checkbox checked>` | 默认勾选 | `bool`，默认 true | 停用后 LLM 节点校验会失败（`workflows.py:896`） |
| `id` | `<input id=modelId type=hidden>` | — | — | 空 = 新建，非空 = 编辑 |

### 3.5.3 交互细节

- `resetForm()`（`model.js:13`）：`form.reset()` + 清空隐藏 id + 强制 `enabled.checked = true` + 标题回「新建模型」+ 清状态。**「新建模型」按钮就是 resetForm**（`model.js:32`），因此它不做任何服务端交互。
- `editModel(model)`（`model.js:15`）：回填全部字段（含 `api_key` 明文）、标题改「编辑模型」、`name.focus()`。
- 提交（`model.js:31`）：`state.saving` 防重入 → `id` 有值走 `PUT /api/models/{id}`，否则 `POST /api/models` → `resetForm()` → `load()` 全量重拉 → 状态「已保存」；异常 → `setStatus(error.message, true)`（红色）。
- 删除（`model.js:30`）：`window.confirm("确认删除“{name}”？")` → `DELETE` → 若被删的正是表单当前编辑项则 `resetForm()` → `load()`。**前后端都不检查 Workflow 引用**。
- 卡片渲染（`model.js:21-26`）：`innerHTML` 拼骨架 + 三处 `textContent` 赋值（`strong`=name、`p`=`provider · model`、`code`=base_url），`enabled=false` 加 `.disabled`（CSS `opacity:.6`），底部 `<small>` 显示「API Key 已配置」/「未配置 API Key」；页脚两个按钮「编辑」「删除」逐项绑定。**名称/URL 经 `textContent` 注入，无 XSS**。

### 3.5.4 与 agent 侧 LLM 配置的连接方式

数据流：`model.html` 表单 → `POST/PUT /api/models` → MongoDB `{MONGO_DATABASE}.models`（`name` 唯一索引）→ `_id` 被写入 Workflow 的 LLM 节点 `arguments.model`（字符串）→ 保存画布时 `workflows.py:889-901` 校验（ObjectId 合法 + 存在 + `enabled=true`）→ 运行时 `agent/llm.py:11-36` 再查一次 → `agent/llm.py:65-73` 调 `openai_llm_api(url=base_url, model=model, key=api_key)`。

一致性要求：

- 模型 `_id` 在管理页以字符串暴露（`models.py:27`），节点里存字符串，运行时由 `agent/llm.py:15` 转 `ObjectId`。
- **双层校验**：保存 Workflow 时查 `enabled`（`workflows.py:896`），运行时再查一次（`agent/llm.py:33`）。因此停用模型会让已保存的 Workflow **在下一次保存时被 400 拒绝**（「LLM 节点引用了不存在或已停用的模型配置」），但不会使运行中的 Workflow 立即失效——运行时才抛 `ValueError`。
- 删除模型不级联处理引用它的 Workflow，形成悬空引用，直到该 Workflow 下次保存才暴露。

---

## 3.6 Session 管理页（`sessions.html` / `sessions.js`，`/sessions.html`）

### 3.6.1 用途与布局

`agent/workflow_session_repository.py` 的全局状态存储的管理前端，比文档页复杂得多（双模式结构化编辑器）。布局：`aside.sidebar`（列表 + 搜索 + 分页）| `section.detail`（详情头 + 表单 + 空态）。

### 3.6.2 列表：加载、分页、搜索

- **首页加载**：页面末尾 `loadList()`（默认 `append=false`、`cursor=''`，`sessions.js:424`）；每页大小前端硬编码 `limit=50`（`api.js:26`，后端上限 100）。
- **加载更多**：`#moreButton` → `loadList(true)` 用 `nextCursor`（`sessions.js:309,247-280`）；按钮仅在 `nextCursor` 非空时显示（`sessions.js:271`）。
- **竞态保护**：`listGeneration` 递增计数，响应回来 generation 不匹配即丢弃（`sessions.js:248,255`）。
- **搜索**：`#searchInput` + `#searchButton`，Enter 等价点按钮（`sessions.js:301-308`）；`q` 是 `_id` 的**前缀**正则匹配（后端 `re.escape`，`sessions.py:97-98`），非全文检索。
- **状态栏**：`读取中` → `{N} 条`（追加时补 `（更多可加载）`）或错误文案（`sessions.js:251,272,276`）。
- **列表项**：`<button class="session-item">`，主行 session id，次行 `{value_type} · {本地时间}`（`sessions.js:258-268`）；选中态由 `updateSelection()` 按 `data-id` 批量切 `.selected`，`creating` 时不选中（`sessions.js:231-235`）。

### 3.6.3 详情加载与乐观锁

`openSession(id)`（`sessions.js:281-299`）：`busy` 或 `!mayDiscard()` 直接返回 → `detailGeneration` 递增 → `GET /api/sessions/{id}` → `valueType.value = value_type`（因 `current` 非空而 `disabled`）→ `setDraft(type, value)`。

保存（`sessions.js:401-421`）：

- 新建：`POST /api/sessions {value_type, value}`，`value_type` 取 `#valueType.value`。
- 更新：`PUT /api/sessions/{current.id} {value_type: current.value_type, value, updated_at: current.updated_at}`——**`value_type` 与 `updated_at` 都取 `current` 而非当前草稿**，以匹配后端乐观锁 filter（`sessions.py:168`）。
- 冲突返回 409「Session 已被其他操作更新，请刷新后重试」，在 `#formStatus` 展示；`#refreshButton` 是手动恢复手段。
- 成功则 `setDraft(document.value_type, document.value)` 重置 baseline，再 `loadList()` 刷新时间戳。

### 3.6.4 值类型与初始值

`SESSION_VALUE_TYPES`（后端 `sessions.py:20`）与 `initialValue()`（前端 `sessions.js:23-29`）对照：

| 类型 | 后端合法性校验 | 前端初始值 | 可视化控件 |
| --- | --- | --- | --- |
| `content` | `isinstance(str)` | `''` | 纯文本 textarea，**无模式切换** |
| `message` | dict 且键恰为 `{role,content}`、`role∈{system,user,assistant,tool}`、`content` 为 str | `{role:'user',content:''}` | 角色 `<select>` + 内容 textarea |
| `event` | dict 且有非空 str `event_type` 且含 `payload` 键 | `{event_type:'',payload:{}}` | 事件类型 input + Payload JSON textarea + 扩展字段 JSON textarea |
| `map-content` | dict 且所有 key 非空 str、所有 value 为 str | `{}` | 键/内容行列表 + `+ 添加一项`（键非空、不重复校验） |
| `list-content` | 数组且全为 str | `[]` | 列表，每项单条内容 textarea |
| `list-message` | 数组且每项 message 合法 | `[]` | 列表，每项角色 select + 内容 |
| `list-event` | 数组且每项 event 合法 | `[]` | 列表，每项事件类型 + payload + 扩展字段 |

前端 `checkValue`/`checkItem`（`sessions.js:31-59`）与后端 `valid_value`（`sessions.py:23-47`）是**逐条镜像实现**——改动任一侧必须同步另一侧。前端额外规则：event 的扩展字段必须是对象且**不能含 `event_type`/`payload` 键**（`sessions.js:106-109`）。

值大小上限：序列化后 UTF-8 ≤ 1 MiB（后端 `_validate_value`，`sessions.py:58-67`；`MAX_VALUE_BYTES = 1024*1024`）。

### 3.6.5 双模式编辑（可视化 / JSON）细节

模式状态：`mode ∈ {'visual','json'}`，`setDraft()` 每次重置为 `'visual'`（`sessions.js:220-226`）。

切换矩阵（`renderEditor()`，`sessions.js:144-206`）：

| 类型 | `#editModes` 显隐 | 可视化编辑器 | 文本框 |
| --- | --- | --- | --- |
| `content` | 隐藏（`hidden = type==='content'`） | 始终 `hidden` | 始终显示，标签「文本」 |
| 非 content + `visual` | 显示 | 显示 | 隐藏 |
| 非 content + `json` | 显示 | 隐藏 | 显示，标签「JSON」，内容 `JSON.stringify(draft, null, 2)` |

模式切换按钮（互斥 `aria-pressed`）：

- `#jsonButton`（`sessions.js:336-343`）：先 `readVisual()` 把可视化 DOM 读回 `draft`；读失败（如显式输入的 JSON 非法）→ 留在可视化模式并在 `#formStatus` 报错。
- `#visualButton`（`sessions.js:344-351`）：先 `readDraft()`（此时走 JSON 解析路径）验证合法性；失败则留在 JSON 模式报错。

列表项操作按钮（`sessions.js:185-196`，事件委托在 `sessions.js:352-378`）：

| 按钮 | 文案 | 禁用条件 | 行为 |
| --- | --- | --- | --- |
| 上移 | `↑` | `index === 0` | 与 `index-1` 交换后 `renderEditor()` 全量重渲染 |
| 下移 | `↓` | `index === draft.length-1` | 与 `index+1` 交换 |
| 删除 | `删除` | — | `row.remove()` 后 `readVisual()` 重读再重渲染 |
| 添加 | `+ 添加一项` | — | `draft.push(initialValue(draftType.slice(5)))`；`map-content` 走 `mapRow('','')` 并聚焦新键输入框 |

行标题生成（`sessions.js:183`）：`#i  ` + `content` 项取前 45 字符 / `message` 取 `role` / `event` 取 `event_type`。每项按钮的 `title`/`aria-label` 为 `{符号}第 i 项`。

### 3.6.6 脏状态与丢弃确认

`dirty()`（`sessions.js:135-142`）：把当前 DOM 值解析出来与 `baseline`（`JSON.stringify` 快照）比较；**解析抛异常即视为脏**（`catch { return true }`）。`mayDiscard()`（`sessions.js:143`）在脏时弹 `有未保存的修改，确定丢弃吗？`。

`dirty()` 的拦截点：切换 Session（`openSession`）、新建（`createButton`）、取消（`cancelButton`）、删除（`deleteButton`）、切换值类型（`valueType change`，另有专用文案「切换类型会丢弃当前的值，确定继续吗？」，拒绝时回滚 `select.value = draftType`，`sessions.js:321-329`）。

**`beforeunload` 保护**（`sessions.js:381`）：`if (dirty()) event.preventDefault();`——这是五个页面中唯一注册卸载保护的页面。

`cancelButton`（`sessions.js:330-335`）：新建态 → 取消创建、回空态；编辑态 → `setDraft(current.value_type, current.value)` 用服务端值覆盖草稿。

### 3.6.7 值类型下拉的禁用逻辑

`#valueType` 在打开已有 Session 时被 `disabled = Boolean(current)`（`sessions.js:244`）——**已有 Session 的类型不可改**（后端 `PUT` 的 filter 也含 `value_type`，改类型必然 409）；新建态可自由选择。

---

## 3.7 事件目录页（`events.html` / `events.js`，`/events.html`）

### 3.7.1 用途与布局

纯展示页，无写操作。数据源为硬编码目录（`event_catalog.py:6-193`，7 个事件类型）。布局：`aside.event-sidebar`（搜索 + 分组列表）| `section.schema-panel`（摘要 + 字段树/JSON 双视图）。

### 3.7.2 数据与分组

| 分组 `scope` | 中文标签 | 事件类型 | 代码位置 |
| --- | --- | --- | --- |
| `main_queue` | 主队列协议 | `qq`、`terminal`、`workflow`、`error`、`response` | `events.js:4`、`event_catalog.py:8,38,65,92,118` |
| `callback_queue` | Tool 回调 | `async_result` | `events.js:5`、`event_catalog.py:141` |
| `display_only` | 仅 WebUI 展示 | `raw` | `events.js:6`、`event_catalog.py:172` |

每个条目的元数据字段：`event_type`、`scope`、`title`、`description`、`producer`、`consumer`、`schema`（JSON Schema draft 2020-12）。分组渲染严格按 `scopeLabels` 的键顺序（`events.js:121`），空组不渲染（`events.js:123`）。

契约测试断言（`test_event_catalog.py:11-19`）：恰好这 7 个类型、`count==7`、`main_queue` 恰好 5 个。

### 3.7.3 搜索（纯前端过滤）

`renderList()`（`events.js:115-150`）：把 `event_type + title + description + scope 中文标签` 拼成小写字符串做 `includes(query)` 子串匹配，**无正则、无防抖**，`input` 事件即时触发（`events.js:163`）。无结果 → 「没有匹配的事件类型」。

### 3.7.4 字段树视图

`createField(name, schema, required, depth)`（`events.js:45-98`）递归构建：

| 元素 | 生成规则 | 位置 |
| --- | --- | --- |
| 折叠按钮 `.field-toggle` | 有 `properties` 时文案 `−`、`aria-expanded=true`、`aria-label="折叠 {name}"`；无子字段时文案 `·`、`disabled`、`aria-label="{name} 没有子字段"` | `events.js:52-59` |
| 缩进 | `row.style.setProperty('--depth', depth)`，CSS `padding-left: calc(10px + var(--depth)*26px)` | `events.js:50`、`css/events.css:45` |
| 必填标记 | 父级 `required` 数组包含该字段时插入 `<span class="required-marker">必填</span>` | `events.js:66-71` |
| 类型描述 | `describeSchema`：`const` → `固定值 X`；`enum` → `用 \| 连接`；数组 `type` → `用 \| 连接`；否则原样 | `events.js:27-33` |
| 约束描述 | `constraintText`：`format`、`最少 N 字符`、`最多 N 字符`、`最多 N 项`、`不允许额外字段`（`additionalProperties===false`） | `events.js:35-43` |

折叠切换（`events.js:89-94`）翻转 `aria-expanded`，文案在 `−`/`+` 间切换，`children.hidden` 同步；树根固定 `createField('event', item.schema, true)`（`events.js:107`）。

### 3.7.5 JSON 视图、复制与初始状态

- 视图切换 `setView(view)`（`events.js:152-161`）：`#schemaTree.hidden` / `#schemaJson.hidden` 互斥，所有 `[data-view]` 按钮同步 `.active` 与 `aria-pressed`。
- `#schemaJson` 内容在 `renderSchema` 时一次性写入 `<code>`：`JSON.stringify(item.schema, null, 2)`（`events.js:108`）。
- `#copySchema`（`events.js:167-172`）：`navigator.clipboard.writeText(同一 JSON)` → 加 `.copied` 类 → 900ms 后移除。**没有 try/catch**，剪贴板被拒时产生未处理的 Promise rejection。
- **初始状态**：模块级 TLA（`events.js:174-187`）读取成功 → `#catalogState` 显示 `count`、渲染列表、**自动选中第一项**（`qq`）；失败 → `#catalogState` 变「读取失败」+ `.error`（红色），`#schemaEmpty` 替换为错误消息，`#schemaActions` 保持 `hidden`。`#schemaEmpty` 初始文案「正在读取事件目录」（`events.html:59`）。

---

## 控件与交互全表

### 页头与导航（5 个页面共有）

| 控件 | 页面 | 触发条件 | 行为 | 调用的接口 | 代码位置 |
| --- | --- | --- | --- | --- | --- |
| `a.brand`（A + AAgent） | 全部 5 页 | 始终可点 | 跳转 `/`（渲染 `workflows.html`） | GET `/` | `workflows.html:13`、`document.html:13`、`model.html:13`、`sessions.html:13`、`events.html:13` |
| `.page-nav a` Workflows | 全部 | 始终 | 跳 `/workflows.html` | — | `workflows.html:19` 等 |
| `.page-nav a` 事件 | 全部 | 始终 | 跳 `/events.html` | — | `workflows.html:20` 等 |
| `.page-nav a` Sessions | 全部 | 始终 | 跳 `/sessions.html` | — | `workflows.html:21` 等 |
| `.page-nav a` 文档 | 全部 | 始终 | 跳 `/document.html` | — | `workflows.html:22` 等 |
| `.page-nav a` 模型 | 全部 | 始终 | 跳 `/model.html` | — | `workflows.html:23` 等 |
| 顶部状态徽标 | Workflows | 只读 | `#workflowState` 文案随状态变化（`aria-live`） | — | `workflows.html:25`、`workflows.js:400-413` |
| 顶部状态徽标 | 文档 | 只读 | `#documentState`：读取中/已同步/部分同步/不可用 | — | `document.html:25`、`document.js:109,197,203,205` |
| 顶部状态徽标 | 模型 | 只读 | `#modelState`：`{N} 个模型` / `不可用` | — | `model.html:21`、`model.js:18,29` |
| 顶部状态徽标 | 事件 | 只读 | `#catalogState`：`count` / `读取失败`（+`.error`） | — | `events.html:25`、`events.js:177,181-182` |
| 顶部状态徽标 | Sessions | **不存在**（该页顶栏只有导航） | — | — | `sessions.html:12-17` |

### Workflows 管理页控件

| 控件 | 页面 | 触发条件 | 行为 | 调用的接口 | 代码位置 |
| --- | --- | --- | --- | --- | --- |
| `#uploadButton`（文件图标） | Workflows | `busy` 时 disabled | 触发 `#uploadFileInput.click()` | — | `workflows.html:36`、`workflows.js:61,769` |
| `#uploadFileInput`（`hidden`, `accept="application/json,.json"`） | Workflows | 仅由按钮触发 | 读取文件文本、解析、打开上传确认对话框；自身 `value` 立即清空 | 无（纯本地） | `workflows.html:35`、`workflows.js:497,770` |
| `#textImportButton`（剪贴板图标） | Workflows | `busy` 时 disabled | 打开文本导入对话框，尝试预填剪贴板 | 无 | `workflows.html:39`、`workflows.js:771,507-521` |
| `#copyButton`「导出到剪贴板」 | Workflows | `hidden` 无选中或未选；`disabled` 当 `busy` | 拉详情 → 写剪贴板 → 状态「已复制到剪贴板」 | GET `/api/workflows/{id}` | `workflows.html:54`、`workflows.js:63,295,784,679-695` |
| `#canvasExportButton`「导出画布」 | Workflows | 同上 | 生成 SVG 并下载 `{name}-{date}-canvas.svg` | GET `/api/workflows/{id}`（可缓存命中） | `workflows.html:55`、`workflows.js:64,296,785,723-745` |
| `#exportButton`「导出 JSON」 | Workflows | 同上 | 下载 `{name}-{date}.json` | GET `/api/workflows/{id}` | `workflows.html:56`、`workflows.js:65,297,786,697-721` |
| `#renameButton`「重命名」 | Workflows | 同上 | 打开重命名对话框并预填当前名 | 无（提交时才调 PATCH） | `workflows.html:57`、`workflows.js:66,298,783,422-430` |
| `#deleteButton`「删除」 | Workflows | 同上 | `window.confirm` 后删除，清草稿键、重选首项 | DELETE `/api/workflows/{id}` | `workflows.html:58`、`workflows.js:67,299,787,747-767` |
| 列表项 `.workflow-management-item` | Workflows | 每项一个；`loading/saving` 不阻止点击（但会立刻被状态覆盖） | 选中该 Workflow，重渲染列表与配置区 | 无（选中后触发 GET 详情缓存） | `workflows.js:381-394,392` |
| `.dependency-edit-button`「修改」 | Workflows 依赖区 | 每次渲染动态生成；`state.saving` 时点击直接 return | 就地变内联重命名编辑器 | — | `workflows.js:146-151,201-202` |
| `.dependency-save-button`「保存」 | Workflows 依赖区（内联） | `!name \|\| !exists \|\| duplicate` 时 disabled | 提交新名字 | PUT `/api/workflows/{id}/metadata` | `workflows.js:213-226,270-276` |
| `.dependency-cancel-button`「取消」 | Workflows 依赖区（内联） | 始终 | 放弃改动并重渲染 | 无 | `workflows.js:227-234` |
| `.dependency-name-input` | Workflows 依赖区（内联） | 始终可编辑，`maxlength=120` | `input` 事件实时校验存在性与重名 | 无 | `workflows.js:205-210,235` |
| `#textImportValue` textarea（`rows=14`, `required`） | 文本导入对话框 | 始终 | 粘贴 JSON；提交时解析 | 无 | `workflows.html:115`、`workflows.js:526` |
| `#textImportError`（`role=alert`） | 文本导入对话框 | 只读 | 显示解析错误 | — | `workflows.html:116`、`workflows.js:531` |
| `.dialog-close`「×」 | 三个对话框 | 始终 | 关闭对话框；上传对话框额外清 `pendingUpload` | 无 | `workflows.html:113,124,135`、`workflows.js:789-798` |
| `.dialog-cancel`「取消」 | 三个对话框 | 始终 | 同上 | 无 | `workflows.html:118,129,140` |
| 文本导入 `button[type=submit]`「继续」 | 文本导入对话框 | `required` 未满足时浏览器拦截 | 解析文本 → 关闭本弹窗 → 打开上传确认 | 无 | `workflows.html:118`、`workflows.js:772,523-533` |
| `#uploadName`（`maxlength=120`, `required`） | 上传对话框 | 始终 | `input` 实时校验：空/重名提示 | 无 | `workflows.html:126`、`workflows.js:773,440-448` |
| `#uploadError`（`role=alert`） | 上传对话框 | 只读 | 空名/重名文案 + 「可选择覆盖」 | — | `workflows.html:127`、`workflows.js:443` |
| `#uploadOverwrite`「覆盖」 | 上传对话框 | 仅当名称重名且非 saving 时可点 | 覆盖同名 Workflow（PUT metadata + PUT 完整） | PUT `/api/workflows/{id}/metadata`、PUT `/api/workflows/{id}` | `workflows.html:129`、`workflows.js:445,776,582-621` |
| `#uploadSubmit`「确认上传」 | 上传对话框 | 空名或重名时 disabled | 新建同名 Workflow 并写入（失败回滚删除） | POST `/api/workflows`、PUT metadata、PUT 完整、DELETE（回滚） | `workflows.html:129`、`workflows.js:444,775,535-580` |
| `#renameName`（`maxlength=120`, `required`） | 重命名对话框 | 始终 | `input` 实时校验（排除自身 id） | 无 | `workflows.html:137`、`workflows.js:774,450-452,432-438` |
| `#renameError`（`role=alert`） | 重命名对话框 | 只读 | 空名/重名文案 | — | `workflows.html:138`、`workflows.js:435` |
| `#renameSubmit`「保存」 | 重命名对话框 | 空名/重名时 disabled | 提交重命名 | PATCH `/api/workflows/{id}` | `workflows.html:140`、`workflows.js:788,623-646` |
| `#workflowCanvasPreview`（内含 SVG） | Workflows | **只读展示**，无任何事件绑定 | 静态渲染完整画布，缩放由 CSS `aspect-ratio` 决定 | GET `/api/workflows/{id}` | `workflows.html:75`、`workflows.js:341-364`、`workflow_canvas.mjs:138-189` |
| `#metadataPortTemplate` `<template>` | Workflows | 非交互 | 端口行的克隆源 | 无 | `workflows.html:144-149`、`workflows.js:70-75` |

### 文档页控件

| 控件 | 页面 | 触发条件 | 行为 | 调用的接口 | 代码位置 |
| --- | --- | --- | --- | --- | --- |
| `#createButton`「+」 | 文档 | `loading/saving` 时 disabled | 脏检查 → 新建「未命名文档」→ 进编辑态 → 聚焦标题并全选 | POST `/api/documents` | `document.html:36`、`document.js:51,325,231-256` |
| `#uploadButton`「上传」 | 文档 | `loading/saving` 时 disabled | 触发 `#uploadInput.click()` | — | `document.html:35`、`document.js:52,326` |
| `#uploadInput`（`sr-only`, `multiple`, `accept=".md,.txt,text/markdown,text/plain"`） | 文档 | 仅由按钮触发 | 批量导入 Markdown；单文件导入后自动打开 | POST `/api/documents`（逐文件） | `document.html:38`、`document.js:329-332,79-116` |
| `#documentTitle`（`maxlength=200`, 初始 `disabled`） | 文档 | 仅 `mode==='edit' && active && !busy` 可编辑 | `input` 时清状态文案并重算脏状态/按钮 | 无 | `document.html:47`、`document.js:49,339` |
| `#documentContent`（`maxlength=1000000`, `spellcheck=false`, 初始 `disabled`） | 文档 | 仅编辑态可编辑 | 输入即同步 `#documentPreview` 文本并更新字数 | 无 | `document.html:61`、`document.js:50,340,64` |
| `#documentPreview`（`<pre hidden>`） | 文档 | 只读 | 预览态展示正文（`textContent`，非 Markdown 渲染） | — | `document.html:62`、`document.js:167,66` |
| `#pinButton`「钉住 / 已钉住」 | 文档 | 无选中或 `busy` 时 disabled | 取反 `pinned`，更新本地状态与列表标记 | PATCH `/api/documents/{id}/pin` | `document.html:54`、`document.js:54-57,328,174-193` |
| `#downloadButton`「下载 .md」 | 文档 | 无选中或 `busy` 时 disabled | 本地生成 Blob 下载，文件名净化 | 无（用当前内存内容） | `document.html:55`、`document.js:53,327,118-131` |
| `#deleteButton`「删除」 | 文档 | 无选中或 `busy` 时 disabled | `window.confirm` → 删除 → 清空所有字段并回空态 | DELETE `/api/documents/{id}` | `document.html:56`、`document.js:63,338,298-323` |
| `#editButton`「编辑 / 保存」 | 文档 | 预览态恒可点；编辑态需 `isChanged() && title.trim()` | 预览态 → 进编辑；编辑态 → 保存并回预览态 | PUT `/api/documents/{id}` | `document.html:69`、`document.js:58-60,333-336,258-279` |
| `#cancelButton`「取消」 | 文档 | 编辑态才可见/可用 | 用 `state.saved` 回滚标题与正文，回预览态 | 无 | `document.html:68`、`document.js:61-62,337,288-296` |
| 列表项 `.document-item` | 文档 | 每项一个；已在当前文档时点击无效 | 脏检查 → 拉详情 → 回预览态打开 | GET `/api/documents/{id}` | `document.js:142-159,157,213-229` |
| `.document-pin`「钉住」标记 | 文档 | 只读（`pinned` 为真时渲染） | 列表内联标记 | — | `document.js:148-153` |
| `#saveStatus`（`role=status`） | 文档 | 只读 | `''`/`success`/`error` 三态文案 | — | `document.html:66`、`document.js:25-28` |
| `#characterCount` | 文档 | 只读 | `[...content].length` 按码点计数 + ` 字` | — | `document.html:67`、`document.js:64` |
| `#documentId` | 文档 | 只读 | `_id {24 位 hex}` | — | `document.html:49`、`document.js:168` |
| `#updatedAt` | 文档 | 只读 | **实际显示 `创建于 {时间}`** | — | `document.html:50`、`document.js:169` |
| `#documentEmpty` | 文档 | 无选中时可见 | 空态提示「选择一篇文档 / 或新建一篇开始记录」 | — | `document.html:63`、`document.js:65` |

### 模型页控件

| 控件 | 页面 | 触发条件 | 行为 | 调用的接口 | 代码位置 |
| --- | --- | --- | --- | --- | --- |
| `#newModelButton`「新建模型」 | 模型 | 始终可点（**不受 saving 保护**） | `resetForm()`：清空表单、`enabled=true`、标题回「新建模型」 | 无 | `model.html:29`、`model.js:32,13` |
| `#modelName`（`maxlength=120`, `required`） | 模型 | 始终 | 表单字段 | — | `model.html:35`、`model.js:14` |
| `#modelProvider`（`maxlength=120`, `required`） | 模型 | 始终 | 表单字段 | — | `model.html:36`、`model.js:14` |
| `#modelModel`（`maxlength=200`, `required`） | 模型 | 始终 | 表单字段（模型标识） | — | `model.html:37`、`model.js:14` |
| `#modelBaseUrl`（`type=url`, `maxlength=500`, `required`） | 模型 | 始终 | 表单字段，浏览器做 URL 格式校验 | — | `model.html:38`、`model.js:14` |
| `#modelApiKey`（`type=password`, `maxlength=1000`, `autocomplete=new-password`） | 模型 | 始终 | 表单字段；编辑时明文回填 | — | `model.html:39`、`model.js:15` |
| `#modelEnabled`（`type=checkbox`, 默认 `checked`） | 模型 | 始终 | 启用开关，`accent-color: var(--green)` | — | `model.html:40`、`model.js:14` |
| `#modelId`（`type=hidden`） | 模型 | — | 空=新建，非空=编辑（决定 POST/PUT） | — | `model.html:34`、`model.js:31` |
| `form#modelForm` submit「保存配置」 | 模型 | HTML5 `required` 校验通过才触发 | `id` 有值 → PUT；否则 POST；成功后重拉列表 | POST `/api/models` 或 PUT `/api/models/{id}`，随后 GET `/api/models` | `model.html:41`、`model.js:31` |
| 卡片 `.edit`「编辑」 | 模型 | 每卡一个 | 回填表单并聚焦名称 | 无 | `model.js:23,25,15` |
| 卡片 `.delete-button`「删除」 | 模型 | 每卡一个 | `window.confirm` 后删除；若删的是当前编辑项则 `resetForm()`，然后重拉 | DELETE `/api/models/{id}`、GET `/api/models` | `model.js:23,25,30` |
| `#formStatus`（`role=status`） | 模型 | 只读 | 表单级状态（未使用于大部分流程） | — | `model.html:33` |
| `#saveStatus`（`role=status`） | 模型 | 只读 | `保存中…`/`已保存`/错误（`.error` 红） | — | `model.html:41`、`model.js:12` |
| `#listCount` | 模型 | 只读 | `{N} 个配置` | — | `model.html:43`、`model.js:18` |

### Session 页控件

| 控件 | 页面 | 触发条件 | 行为 | 调用的接口 | 代码位置 |
| --- | --- | --- | --- | --- | --- |
| `#createButton`「+」 | Sessions | `busy` 或 `mayDiscard()` 拒绝时不动 | 进入新建态：清 `current`、`creating=true`、类型 `content`、草稿 `''`、聚焦 `#valueInput` | 无 | `sessions.html:21`、`sessions.js:310-320` |
| `#searchInput`（`type=search`） | Sessions | 始终 | Enter 键等价于点 `#searchButton` | 无（按键触发搜索） | `sessions.html:22`、`sessions.js:306-308` |
| `#searchButton`「搜索」 | Sessions | 始终 | 以输入值做 `_id` 前缀查询，重置游标并重载列表 | GET `/api/sessions?limit=50&q=...` | `sessions.html:22`、`sessions.js:301-305` |
| `#moreButton`「加载更多」 | Sessions | 仅 `next_cursor` 非空时显示 | 追加下一页 | GET `/api/sessions?cursor=...` | `sessions.html:24`、`sessions.js:309,271` |
| 列表项 `.session-item` | Sessions | 每项一个 | 脏检查 → 拉详情 → `current=doc`、`creating=false`、切到详情 | GET `/api/sessions/{id}` | `sessions.js:258-268,267,281-299` |
| `#valueType` `<select>`（7 个 option） | Sessions | `current` 非空时 **disabled** | 切换类型：脏则确认「切换类型会丢弃当前的值」，拒绝时回滚 select | 无 | `sessions.html:29`、`sessions.js:244,321-329` |
| `#visualButton`「可视化」 | Sessions | `content` 类型时整个 `#editModes` 隐藏 | JSON → 可视化：先 `readDraft()` 校验，失败留在 JSON 并报错 | 无 | `sessions.html:31`、`sessions.js:344-351,147` |
| `#jsonButton`「JSON」 | Sessions | 同上 | 可视化 → JSON：先 `readVisual()` 校验，失败留在可视化并报错 | 无 | `sessions.html:31`、`sessions.js:336-343` |
| `#valueInput` textarea | Sessions | `content` 或 JSON 模式下可见 | 值输入；`input` 时清状态 | 无 | `sessions.html:33`、`sessions.js:380,150-154` |
| `#visualEditor`（动态容器） | Sessions | 非 `content` 且可视化模式 | 事件委托处理下列 4 类按钮；`input` 清状态 | 无 | `sessions.html:32`、`sessions.js:352-379` |
| 列表项 `↑` 上移 | Sessions 可视化 | `index===0` 时 disabled | 与前一项交换后整体重渲染 | 无 | `sessions.js:186-196,372-375` |
| 列表项 `↓` 下移 | Sessions 可视化 | 末项 disabled | 与后一项交换 | 无 | `sessions.js:186-196,372-375` |
| 列表项 `删除` | Sessions 可视化 | 始终 | 移除该行（列表项）或 map 行 | 无 | `sessions.js:186-196,358,367` |
| `+ 添加一项` | Sessions 可视化（list/map-content） | 始终 | 追加一个初始值行；map 聚焦新键 | 无 | `sessions.js:163-167,201-205,359-363,371` |
| map 行 `键` input | Sessions 可视化 `map-content` | 始终 | 键输入，保存前校验非空且不重复 | 无 | `sessions.js:207-219,114-120` |
| map 行 `内容` textarea | Sessions 可视化 `map-content` | 始终 | 值输入（必须文本） | 无 | `sessions.js:212` |
| list-item `角色` `<select>`（system/user/assistant/tool） | Sessions 可视化 message 类 | 始终 | 角色选择 | 无 | `sessions.js:78-91` |
| list-item `内容` textarea | Sessions 可视化 content/message 类 | 始终 | 文本输入 | 无 | `sessions.js:77,90` |
| `事件类型` input | Sessions 可视化 event 类 | 始终 | 非空校验 | 无 | `sessions.js:94` |
| `Payload (JSON)` textarea | Sessions 可视化 event 类 | 始终 | `JSON.parse` 校验 | 无 | `sessions.js:95,104` |
| `扩展字段 (JSON 对象)` textarea | Sessions 可视化 event 类 | 始终 | 必须是对象且不得含 `event_type`/`payload` | 无 | `sessions.js:96,105-109` |
| `#copyButton`「复制 ID」 | Sessions | 无 `current` 或 `creating` 时 disabled | 写剪贴板 `current.id` | 无 | `sessions.html:27`、`sessions.js:241,382-386` |
| `#refreshButton`「刷新」 | Sessions | 无 `current` 或 `creating` 时 disabled | 重新拉取当前 Session（丢弃草稿前先 `mayDiscard()`） | GET `/api/sessions/{id}` | `sessions.html:27`、`sessions.js:242,387` |
| `#deleteButton`「删除」 | Sessions | 同上 | `mayDiscard()` + `window.confirm` 双确认 → 删除 → 清空详情 → 重载列表 | DELETE `/api/sessions/{id}`、GET `/api/sessions` | `sessions.html:27`、`sessions.js:243,388-400` |
| `#cancelButton`「取消」 | Sessions | 仅在表单可见时可用 | 新建态退出创建；编辑态用服务端值覆盖草稿 | 无 | `sessions.html:35`、`sessions.js:330-335` |
| `form#sessionForm` submit「保存」 | Sessions | `busy` 时短路 | 新建 → POST；否则 PUT（带 `current.updated_at` 乐观锁） | POST `/api/sessions` 或 PUT `/api/sessions/{id}`，随后 GET `/api/sessions` | `sessions.html:35`、`sessions.js:401-421` |
| `#formStatus`（`role=status`） | Sessions | 只读 | 校验错误 / `保存中` / `已保存` / 冲突消息 | — | `sessions.html:35`、`sessions.js:228` |
| `#listStatus`（`role=status`） | Sessions | 只读 | `读取中` / `{N} 条` / 错误 | — | `sessions.html:24`、`sessions.js:251,272,276` |
| `#emptyDetail` | Sessions | 无 `current` 且非 `creating` 时可见 | 「选择左侧 Session 或新建记录」 | — | `sessions.html:37`、`sessions.js:238` |
| `#detailTitle` / `#timestamp` | Sessions | 只读 | `新建 Session` / `{id}`；`创建 X · 更新 Y` | — | `sessions.html:27`、`sessions.js:239-240` |

### 事件页控件

| 控件 | 页面 | 触发条件 | 行为 | 调用的接口 | 代码位置 |
| --- | --- | --- | --- | --- | --- |
| `#eventSearch`（`type=search`） | 事件 | 始终 | `input` 即时前端过滤（无防抖） | 无 | `events.html:37`、`events.js:163,115-150` |
| 事件项 `.event-item` | 事件 | 每组内每项一个 | 切换选中态并渲染 Schema | 无 | `events.js:129-140,139` |
| `[data-view=tree]`「字段」 | 事件 | `#schemaActions` 未选中时整体 `hidden` | 切到字段树视图 | 无 | `events.html:51`、`events.js:164-166,152-161` |
| `[data-view=json]`「JSON」 | 事件 | 同上 | 切到 JSON 视图 | 无 | `events.html:52`、`events.js:164-166,152-161` |
| `.field-toggle` `−`/`+` | 事件字段树 | 无子字段时 disabled | 折叠/展开子树，同步 `aria-expanded` | 无 | `events.js:53-59,89-94` |
| `#copySchema`（剪贴板图标） | 事件 | `state.selected` 为空时直接 return | 复制缩进 JSON Schema，`.copied` 900ms | 无 | `events.html:54`、`events.js:167-172` |

### 全局交互与快捷键

| 交互 | 页面 | 实现 | 位置 |
| --- | --- | --- | --- |
| Esc 关闭对话框 | Workflows | 原生 `<dialog>` 行为 | `workflows.html:111,122,133` |
| Enter 触发搜索 | Sessions | `keydown` 判 `event.key === 'Enter'` → `preventDefault` + `searchButton.click()` | `sessions.js:306-308` |
| Enter 提交表单 | 模型 / Sessions / 三个 Workflow 对话框 | 原生 form submit | `model.html:32`、`sessions.html:28` |
| `required` / `maxlength` 原生校验 | 模型表单、Workflow 三个对话框 | HTML5 约束校验 + `reportValidity()` | `workflows.js:626`、`model.html:35-40` |
| 挂起退出保护 | Sessions | `beforeunload` + `dirty()` | `sessions.js:381` |
| 剪贴板降级 | Workflows 导出 | `navigator.clipboard` → `execCommand('copy')` | `workflows.js:662-677` |
| 剪贴板读取 | Workflows 文本导入 | `navigator.clipboard.readText()` + 必须先解析成功 | `workflows.js:511-519` |
| 拖拽排序 | **无** | 列表项无语序调整（Session 列表项用 ↑↓ 按钮） | `sessions.js:186-196` |
| 双击交互 | **无** | 全项目无 `dblclick` 监听 | — |
| Ctrl+S / Ctrl+Enter | **无** | 全项目无 `ctrlKey`/`metaKey` 处理 | — |
| 列表排序（用户可控） | **无** | 全部列表固定按服务端返回顺序 | — |
| 轮询 / WebSocket | **无** | 无定时器刷新，无 WS/SSE；数据仅在用户动作后重拉 | — |
| 请求超时 | 全部页面 | `AbortController` + 5000ms；`AbortError` 统一映射为「XX超时」文案 | `api.js:1-19` |
| 请求缓存 | 全部页面 | `cache: 'no-store'` | `api.js:7` |
| 错误提取优先级 | 全部页面 | `body.error` → FastAPI `body.detail` 数组（拼 `loc.msg`）→ `HTTP {status}` | `api.js:9-14` |

---

## 3.8 数据契约（MongoDB / Redis / 跨服务一致性）

### 3.8.1 MongoDB 集合

库名：`MONGO_DATABASE`，默认 `agent`（`main.py:46`）。

| 集合 | 环境变量 | 文档字段 | 索引 | 代码位置 |
| --- | --- | --- | --- | --- |
| `workflows` | `MONGO_WORKFLOW_COLLECTION` | `_id`(ObjectId)、`name`(str,唯一)、`description`(str)、`version`(int≥1)、`nodes`(list)、`connections`(list)、`input_ports`(list)、`output_ports`(list)、`workflow_nodes`(list)、`remote_tools`(list)、`created_at`、`updated_at` | `unique_workflow_name` on `name`（`main.py:88`） | `workflows.py:503-517`, `main.py:88` |
| `documents` | `MONGO_DOCUMENT_COLLECTION` | `_id`(ObjectId)、`title`(str)、`content`(str)、`pinned`(bool)、`created_at`、`updated_at` | 无 | `documents.py:62` |
| `models` | `MONGO_MODEL_COLLECTION` | `_id`(ObjectId)、`name`(str,唯一)、`provider`、`model`、`base_url`、`api_key`、`enabled`(bool)、`created_at`、`updated_at` | `unique_model_name` on `name`（`main.py:84`） | `models.py:39-45`, `main.py:84` |
| `sessions` | `MONGO_SESSION_COLLECTION` | `_id`(str `ses_`+32hex)、`value_type`(7 枚举)、`value`(任意，按类型校验)、`created_at`、`updated_at` | `session_updated_at` on `updated_at`（非唯一、无 TTL） | `sessions.py:145-151`, `main.py:89` |

Session 文档结构细节：`_id` 是**字符串**而非 ObjectId（`sessions.py:146`），因此 `GET/DELETE /api/sessions/{id}` 不做 ObjectId 转换（其余三个资源都做）；`updated_at` 精度截断到毫秒（`sessions.py:82-84`），这是乐观锁精确匹配成立的前提；写入强制单调递增 `max(_now(), payload.updated_at + 1ms)`（`sessions.py:165`）；`agent/workflow_session_repository.py:121,139-153` 用同样的 `_id` 规则与文档形状创建/索引 Session，因此管理页能直接看到 workflow 运行时创建的记录。

### 3.8.2 Redis

| 键 | 环境变量 | 类型 | 用途 | 代码位置 |
| --- | --- | --- | --- | --- |
| `aagent:tools` | `AGENT_TOOLS_KEY` | hash | 本地 Tool 注册表：`field=工具名`，`value=OpenAI function schema JSON`。管理页保存 Workflow 时 `hkeys` 校验引用存在性、`hmget` 读 `function.parameters.properties` 校验端口集合一致性 | `main.py:43`、`workflows.py:869-887`；生产端 `agent/queue_client.py:16-57` |

manager_webui **只读** Redis（仅 `ping` + 上述两个读操作），从不写入。

### 3.8.3 跨服务一致性要求（同一契约的多份镜像）

| 共享点 | 副本 1 | 副本 2 / 3 | 一致性要求 |
| --- | --- | --- | --- |
| Workflow 文档 | `workflow_response` 12 字段（`workflows.py:503-517`） | `agent/workflow_parser.py:124-153` 按 `name`/`_id` 读取并编译为索引链表（剥离 `_id`/`x`/`y`） | 管理页写入的 `nodes`/`connections` 必须满足 parser 的字段假设 |
| 端口 id 规则 | `workflow:{name}`（`workflows.py:277-278`） | `agent/workflow_parser.py:48-51` `boundary_ports()`；前端 `workflow_canvas.mjs:51` | 命名规则是硬契约，三处一致 |
| 连接类型枚举 | `DATA_TYPES`（`workflows.py:22`） | `agent/workflow_contract.py` | 不同步会导致管理页**静默丢弃**连接（`filter_invalid_connections`） |
| Session 值类型 | `SESSION_VALUE_TYPES` + `valid_value`（`sessions.py:20-47`） | `agent/workflow_session_repository.py` 的 `valid_value`；前端 `sessions.js:31-59` | **三份逐条镜像**，任一不同步即"页面能填、运行时报错" |
| 模型配置 | `models` 集合唯一写入者（`models.py`） | `agent/llm.py:11-36` 运行时 `find_one({_id, enabled:True})` | `_id` 以字符串在节点中传递；`base_url` 双方都 `rstrip('/')`（`models.py:44` ↔ `agent/llm.py:47`） |
| Tool 注册表 | 只读校验（`workflows.py:869-887`） | `agent/queue_client.py:51-57` 负责写入/删除 | 管理页只读，从不写 Redis |
| 文档集合 | 管理页 CRUD（`documents.py`） | `agent/tools/documents.py`、`tool_provider/tools/documents.py` | 共用 `MONGO_DOCUMENT_COLLECTION`（`docker-compose.yml:117,214`） |
| 事件目录 | `event_catalog.py` 硬编码 7 项 | `webui_py/events.py`、`agent/task_worker.py` | 纯文档性元数据，不参与运行时校验；`producer`/`consumer` 是字符串路径，重命名文件不会自动更新 |

---

## 3.9 校验规则与错误处理矩阵

### 3.9.1 Workflow 节点校验（保存画布路径 `PUT /api/workflows/{id}`）

按执行顺序（`workflows.py:790-901`）：

| # | 校验 | 错误文案 | 位置 |
| --- | --- | --- | --- |
| 1 | `name.strip()` 非空 | Workflow 名称不能为空 | `workflows.py:790-791` |
| 2 | 每个 node 有非空 str `id` | 每个节点都必须包含有效的 id | `workflows.py:793-795` |
| 3 | node id 不重复 | Workflow 中存在重复的节点 id | `workflows.py:796-797` |
| 4 | 连接的 `fromId`/`toId` 都在节点集合内 | 连接引用了不存在的节点 | `workflows.py:799-801` |
| 5 | `type` ∈ **24 种**（`NODE_ARGUMENT_FIELDS_BY_TYPE` 键集） | Workflow 包含不支持的节点类型 | `workflows.py:803-805` |
| 6 | 逐节点 `node_format_error` | 见 §3.9.2 | `workflows.py:806-809` |
| 7 | 至少一个 `output` 节点 | Workflow 必须至少包含一个 Output 节点 | `workflows.py:810-811` |
| 8 | input/output 节点的 `workflowPorts` 是 list | Input 和 Output 节点必须声明 workflowPorts | `workflows.py:812-817` |
| 9 | 提交的 `input_ports`/`output_ports` 与库中**逐字段相等** | Workflow 边界端口与当前元数据不一致，请刷新后重试 | `workflows.py:826-830` |
| 10 | 每个 `workflow` 节点的 `workflow_name` 在元数据 `workflow_nodes` 中 | Workflow 节点未在元数据中引入 | `workflows.py:835-838` |
| 11 | `workflow` 节点端口快照与元数据契约一致 | Workflow 节点端口与元数据契约不一致 | `workflows.py:839-840` |
| 12 | Remote Tool 节点引用已注册 Remote Tool | Remote Tool 节点未在元数据中注册 | `workflows.py:846-852` |
| 13 | Remote Tool 节点 `parameters` 与注册 `input_ports` 一致 | Remote Tool 节点输入端口与元数据契约不一致 | `workflows.py:853-854` |
| 14 | `remote_sync_tool` 的 `outputs` 与注册 `output_ports` 一致 | Remote Sync Tool 节点输出端口与元数据契约不一致 | `workflows.py:855-856` |
| 15 | `tool_node_error`（工具名/参数/输出/timeout/callback） | 见 §3.9.3 | `workflows.py:860-864` |
| 16 | `local_tool` 的 `tool` 在 Redis 注册表 | Tool 节点引用了未注册的工具 | `workflows.py:866-873` |
| 17 | `local_tool` 的 `parameters` 集合与工具 schema 属性集合相等 | Tool 节点参数端口与工具定义不一致 | `workflows.py:874-887` |
| 18 | 每个 `llm` 节点 `model` 是合法 ObjectId | LLM 节点必须选择有效的模型配置 | `workflows.py:889-893` |
| 19 | 模型存在且 `enabled=true` | LLM 节点引用了不存在或已停用的模型配置 | `workflows.py:894-901` |
| 20 | 名称全局唯一（排除自身） | Workflow 名称已存在 | `workflows.py:923-924` |

写入时还有两步**静默变换**（不报错，直接改数据）：

- `synchronize_metadata_ports`（`workflows.py:904-909`）：把库中 `input_ports`/`output_ports` 以 `workflow:{name}` 为 id 写回 input/output 节点的 `workflowPorts`，并**丢弃**边界端口类型与连接 `type` 不匹配的连接（`workflows.py:300-303`）。
- `filter_invalid_connections`（`workflows.py:308-451`）：对每条非 control 连接做"源端口类型 == 连接类型 == 目标端口类型"三重判定，不满足即**静默删除**。control 连接单独按节点类型推导合法端口集合（`workflows.py:327-340`）。

### 3.9.2 `node_format_error` 逐条规则（`workflows.py:136-204`）

| 规则 | 文案模板 | 位置 |
| --- | --- | --- |
| 类型不支持 | `nodes[{i}].type 不受支持: {type}` | `workflows.py:139-140` |
| `arguments` 非对象 | `nodes[{i}].arguments 必须是对象` | `workflows.py:141-142` |
| 可配置字段放在一级 | `nodes[{i}] 的可配置字段必须放入 arguments: {fields}` | `workflows.py:143-145` |
| 公共字段放进 arguments | `nodes[{i}] 的公共字段必须位于一级: {fields}` | `workflows.py:146-148` |
| 该类型不支持的 arguments 字段 | `nodes[{i}].arguments 包含该节点不支持的字段: {fields}` | `workflows.py:149-151` |
| 一级多余字段 | `nodes[{i}] 包含不支持的一级字段: {fields}` | `workflows.py:152-154` |
| `history` 的 `event_types` | 只能含不重复的 `terminal`/`response` | `workflows.py:155-164` |
| `history` 的 `limit` | 1–1000 整数（bool 被排除） | `workflows.py:165-166` |
| `list_append.item_type` | ∈ `{content,message,event}` | `workflows.py:167-169` |
| `list_append.position` | ∈ `{start,end}` | `workflows.py:170-171` |
| `deserialize_json.outputs` | 每项恰含 `{key,type}`、key 非空且非 `control-out`、type ∈ DATA_TYPES、key 不重复 | `workflows.py:172-186` |
| `construct_map_content.mappings` | 每项恰含 `{key,value}` 均为字符串，key 不重复 | `workflows.py:187-200` |
| 6 个 context/session 节点 `value_type` | ∈ DATA_TYPES | `workflows.py:201-203` |

`NODE_ARGUMENT_FIELDS_BY_TYPE`（`workflows.py:26-51`）是**唯一权威的"节点类型 → 可配置参数"映射表**，21 个节点类型：`input`、`output`、`router`、`construct_message`、`construct_content`、`construct_map_content`、`map_content_get`、`deserialize_json`、`split_event`、`construct_list`、`list_append`、`foreach`、`history`、`llm`、`local_tool`、`remote_sync_tool`、`remote_async_tool`、`context_create`、`context_read`、`context_write`、`session_create`、`session_read`、`session_write`、`workflow`（实际 24 项，其中 `session_*` 3 项）。

### 3.9.3 `tool_node_error` 规则（`workflows.py:64-133`）

| 场景 | 文案 | 位置 |
| --- | --- | --- |
| 工具名为空 | Tool 节点必须填写工具名称 | `workflows.py:68-69` |
| Local Tool 参数非法（空/重复/`control-in`） | Local Tool 参数必须是非空、不重复且不能为 control-in 的字符串 | `workflows.py:70-76` |
| Remote Tool 参数非法 | Remote Tool 参数必须包含有效的 name 和 type | `workflows.py:77-87` |
| Remote Tool 参数重名 | Remote Tool 参数名称不能重复 | `workflows.py:88-90` |
| Remote Sync Tool 输出非法 | Remote Sync Tool 输出必须包含有效的 name 和 type | `workflows.py:91-102` |
| Remote Sync Tool 输出重名 | Remote Sync Tool 输出名称不能重复 | `workflows.py:103-105` |
| `timeout_ms` 越界 | Remote Tool timeout_ms 必须是 1 到 {max} 的整数 | `workflows.py:106-114` |
| callback 结构非法 | Remote Async Tool callback 必须是有效的 Redis 回调配置（type=redis、queue≤256、event_type≤128、on⊆{working,completed,failed} 且不重复） | `workflows.py:115-132` |

### 3.9.4 HTTP 状态码与 MongoDB 异常映射

| 状态 | 触发 | 统一文案模式 |
| --- | --- | --- |
| 400 | 参数/契约校验失败、ObjectId 非法 | 具体中文消息 |
| 404 | `find_one`/`delete_one` 未命中 | `{资源} 不存在或已被删除` |
| 409 | 唯一键冲突（Workflow/Model 名重复）、Session 乐观锁冲突 | `{资源} 名称已存在` / `Session 已被其他操作更新，请刷新后重试` |
| 422 | Pydantic 模型校验失败（`extra=forbid` 多余字段、`min_length`/`max_length` 越界、`ge` 越界） | FastAPI 默认 `{"detail":[{loc,msg,...}]}`；前端 `api.js:10-12` 会把它拼成可读字符串 |
| 503 | `PyMongoError` / `redis.RedisError` | `{资源} 暂时不可用` / `暂时无法{操作}` |

所有写操作的集合查询都包裹在 `try/except PyMongoError` 中并返回 503，**没有任何接口返回 500**（除未捕获的编程错误）。

---

## 3.10 安全与边界

### 3.10.1 鉴权：无

- **零认证、零授权、零 CSRF token**：无 `Depends`、无 `Authorization` 解析、无 session/cookie、无鉴权中间件（`main.py:94-142` 三个中间件均为日志/体积/响应头）。
- 任何能访问 8084 的人都能读写全部 Workflow、文档、模型配置（含明文 `api_key`）、Session 并删除任意对象；部署侧唯一缓解是 Docker 网络 `aagent_net` 与端口映射 `"8084:8084"`（`docker-compose.yml:121-128`），即**默认对宿主机全网暴露**。
- 无 CORS 中间件，浏览器同源策略阻止跨站读取；`PUT/POST` 要求 `Content-Type: application/json`，提供了基本的 CSRF 抵御（简单表单无法伪造该 content-type）。

### 3.10.2 输入限制与注入防护

| 类别 | 限制 / 做法 | 位置 |
| --- | --- | --- |
| 请求体 | 文档 1MB / 模型 16KB / Workflow 512KB / Session 1MB+4096（中间件按路径前缀判定） | `main.py:118-142` |
| Pydantic | 所有请求模型 `ConfigDict(extra="forbid")` 拒绝多余字段 | `workflows.py:208,215,227,233,239,248,256`、`documents.py:18,25`、`models.py:15`、`sessions.py:51` |
| 业务常量 | 节点 ≤200、连接 ≤1000、元数据端口 ≤50、Workflow 节点引用 ≤50、Remote Tool ≤100、描述 ≤2000 字符 | `workflows.py:16-21` |
| 业务常量 | 文档标题 ≤200、正文 ≤1,000,000 字符；Session 值序列化后 ≤1 MiB | `documents.py:13-14`、`sessions.py:18,65-66` |
| 前端 | `maxlength`：120/200/500/1000/1000000；字数按 `[...str].length` 码点计 | `document.html:47,61`、`model.html:35-39`、`workflows.html:126,137` |
| Session 查询 | `q` ≤100 字符 + `re.escape` 防正则注入 | `sessions.py:94,98` |
| 超时 | Redis / Mongo 均 5s，避免慢依赖挂死请求 | `main.py:56-57,62` |
| HTML 注入 | 全部动态文本 `textContent`；唯一 `innerHTML` 用于**静态骨架**（`model.js:23`），字段值随后 `textContent` 覆写 | `model.js:23-25`、`document.js:147,155`、`sessions.js:263,265`、`events.js:63-64,135-137`、`workflows.js:72-73,142-144,386-389` |
| SVG / 坐标注入 | `escapeXml` 转 `& < > " '`；`safeCoordinate` 把非有限数归 0 防 `NaN` 进入 `transform` | `workflow_canvas.mjs:36-44` |
| NoSQL 注入 | 用户输入经 Pydantic 强类型转换后再进查询 | `sessions.py:98` |
| 响应头 | CSP `script-src 'self'` 禁内联脚本（`main.py:97`）；`X-Frame-Options: DENY`（`:99`）；`X-Content-Type-Options: nosniff`（`:98`）；`Referrer-Policy: no-referrer`（`:100`） | `main.py:97-100` |

### 3.10.3 已识别的边界与风险

| # | 问题 | 事实依据 | 影响 |
| --- | --- | --- | --- |
| S1 | 无鉴权 | `main.py:94-142` 无认证中间件 | 8084 暴露即全量数据可读写 |
| S2 | `api_key` 明文存储与回传 | `models.py:32`（`model_response` 原样返回 `api_key`）、`models.py:39-45`（不加密）、`GET /api/models` 返回全字段 | 任何能访问 `/api/models` 的人可拿到所有提供商的密钥；页面 `type=password` 仅遮显示 |
| S3 | 模型删除无引用检查 | `models.py:102-113` 不查询 Workflow 引用 | 产生悬空 LLM 节点引用，运行时才暴露 `ValueError`（`agent/llm.py:35`） |
| S4 | Workflow 删除无引用检查 | `workflows.py:772-783` 不检查其他 Workflow 的 `workflow_nodes` 引用 | 被引用方消失后，引用方画布在下次保存时 400「引入的 Workflow 不存在或已被删除」 |
| S5 | 连接的静默丢弃 | `filter_invalid_connections`（`workflows.py:308-451`）、`synchronize_metadata_ports`（`workflows.py:300-303`） | 改端口类型会**静默删除**相关连接，前端只被告知保存成功 |
| S6 | 错误文案复用 | `models.py:79` 用「文档 ID 无效」 | 模型接口报错信息指向错误资源 |
| S7 | 事件页复制无异常处理 | `events.js:167-172` 无 try/catch | 剪贴板权限被拒时静默失败 |
| S8 | 模型页「新建模型」不受 saving 保护 | `model.js:32` 无 `state.saving` 判断 | 保存请求进行中重置表单可能造成状态混淆 |
| S9 | 文档页无 `beforeunload` | 对比 `sessions.js:381` | 编辑文档时误关标签页丢失内容 |
| S10 | `#updatedAt` 展示创建时间 | `document.js:169` 传 `created_at` | 元信息误导 |
| S11 | `POST /api/workflows` 无体积限制 | `main.py:129` 只覆盖 `PUT /api/workflows/` | 建表请求仅含 `name`，实际风险低，但守卫不完整 |
| S12 | 无并发编辑保护（除 Session） | Workflow/文档/模型都用无条件 `find_one_and_update` | 两个浏览器同时编辑会静默互相覆盖（last-write-wins） |

---

## 3.11 扩展槽

### 3.11.1 新增一个管理页面

必须改的四处：

| # | 文件 | 改动 | 参考 |
| --- | --- | --- | --- |
| 1 | `manager_webui/static/<name>.html` | 新建页面，复制顶栏结构（`.topbar` + `.brand` + `.page-nav`，`.page-nav` 里**五页都要加/改** `active` 与 `aria-current="page"`） | `static/events.html:12-27` |
| 2 | 5 个已有 HTML | 在各自的 `.page-nav` 中插入新 `<a>` | `static/workflows.html:19-23` |
| 3 | `manager_webui/static/<name>.js` + `static/css/<name>.css` | 新建，`<script type="module" src="/<name>.js">`；CSS 用 `base.css` 的变量（`--green`/`--line`/`--canvas`…）保持视觉一致 | `static/events.js:1`、`static/css/events.css:1-4` |
| 4 | 无需改 `main.py` | `StaticFiles(html=True)` 自动托管新 HTML；**无需注册路由** | `main.py:176` |

**注意**：Vite/打包器不参与，资源路径必须写绝对路径 `/css/x.css`（`StaticFiles` 挂在根）。

### 3.11.2 新增一种管理对象（新 MongoDB 集合 + CRUD）

| # | 文件 | 改动 |
| --- | --- | --- |
| 1 | `manager_webui/main.py` | 加 `MONGO_<X>_COLLECTION = env(...)`（`main.py:47-50` 旁）+ `collection: Collection = database[...]`（`main.py:73-76` 旁） |
| 2 | 新建 `manager_webui/<x>.py` | 仿 `documents.py`：Pydantic Request 模型（`extra="forbid"` + `Field(max_length=...)`）、`_response()` 转换器、`create_<x>_router(collection)` 返回 `APIRouter(prefix="/api/<x>")` |
| 3 | `manager_webui/main.py:19` | 加 `from <x> import create_<x>_router` |
| 4 | `manager_webui/main.py:159` 前 | 加 `app.include_router(create_<x>_router(<x>))` |
| 5 | `manager_webui/main.py:118-142` | 在 `request_body_guard` 中加该路径的体积上限分支 |
| 6 | `manager_webui/main.py:81-91` | 需要唯一约束时加 `create_index` |
| 7 | `manager_webui/static/api.js` | 加 `fetch<X>/create<X>/update<X>/delete<X>` 导出函数 |
| 8 | `docker-compose.yml:106-120` | 加 `MONGO_<X>_COLLECTION: ${...:-...}` 环境变量 |
| 9 | `manager_webui/test_<x>.py` | 仿 `test_sessions.py` 用 `MagicMock()` 集合注入 router，通过 `{(method, route.path): route.endpoint}` 直接调 endpoint |

**关键约定**：`create_<x>_router(...)` 工厂模式接收集合而非 import 全局，使单元测试可注入 mock（`test_sessions.py:12-16`）。

### 3.11.3 新增一个 API 路由到已有对象

- 在对应 `create_*_router` 函数体内加 `@router.<method>("...")` 装饰器即可，无需改 `main.py`。
- 路由前缀由 `APIRouter(prefix=...)` 声明（`documents.py:44`、`models.py:49`、`sessions.py:88`）或裸路径（`workflows.py:528`、`event_catalog.py:203`）。
- 若新路径需要体积限制，**必须**同步改 `main.py:118-142`（该守卫用硬编码路径前缀，不是声明式）。
- 路径冲突注意：`GET /api/sessions/{session_id}` 会吞掉任何 `/api/sessions/xxx` 形式的字面量路径，新增子资源应放在 `{session_id}` 之前或改用不同前缀。

### 3.11.4 新增一种编辑器控件（前端）

Session 可视化编辑器的扩展点（`sessions.js`）共 4 处，必须同步：

| # | 位置 | 内容 |
| --- | --- | --- |
| 1 | `initialValue(type)`（`sessions.js:23-29`） | 新类型的初始值 |
| 2 | `checkValue`/`checkItem`（`sessions.js:31-59`） | 前端校验；必须与 `sessions.py:23-47` 的 `valid_value` **逐条镜像** |
| 3 | `itemEditor(type, value)`（`sessions.js:74-99`） | 可视化 DOM 构建 |
| 4 | `readItem(type, editor, label)`（`sessions.js:100-111`） | DOM → 值 读取 |

另外三处需要同步：`renderEditor()` 的类型分支（`sessions.js:144-206`）、`#valueType` 的 `<option>` 列表（`sessions.html:29`）、后端 `SESSION_VALUE_TYPES`（`sessions.py:20`）。

事件目录的字段树扩展点：`createField`（`events.js:45-98`）已递归支持任意 JSON Schema，新增 schema 关键字需要在 `describeSchema`（`events.js:27-33`）或 `constraintText`（`events.js:35-43`）中加分支。

Workflow 节点类型扩展点（**跨 3 个服务**）：

| # | 位置 | 内容 |
| --- | --- | --- |
| 1 | `workflows.py:26-51` `NODE_ARGUMENT_FIELDS_BY_TYPE` | 新节点类型 + 可配置参数集 |
| 2 | `workflows.py:136-204` `node_format_error` | 该类型的参数校验分支 |
| 3 | `workflows.py:308-451` `filter_invalid_connections` 的 `source_type()`/`target_type()` | 该类型端口的数据类型推导 |
| 4 | `workflow_canvas.mjs:54-101` `contractPortIds` | 端口集合（画布渲染） |
| 5 | `workflow_canvas.mjs:5-24` `TYPE_COLORS` | 节点配色 |
| 6 | `agent/workflow_contract.py` | 运行时端口/连接契约 |
| 7 | `workflow_editor/`（8082） | 编辑器侧的节点定义 |

### 3.11.5 静态资源与版本键/缓存策略

| 场景 | 做法 |
| --- | --- |
| 改了 HTML | 无需版本键：`Cache-Control: no-store`（`main.py:172`） |
| 改了 JS/CSS | 若 JS 是**模块顶层导入**（`import ... from './api.js'`），必须在**导入方**和**被导入方**都改 `?v=` 查询串，或改动 `html` 里的 `script src` 版本键；`document.js`/`api.js` 的 `?v=documents-4`（`document.html:75`、`document.js:1`）是范式；`sessions.css?v=6`、`sessions.js?v=7`（`sessions.html:9,41`）是另一组 |
| 未加版本键的 JS | 依赖 `Cache-Control: no-cache` 的条件请求（ETag/Last-Modified 由 `StaticFiles` 提供），刷新即生效；偶发陈旧需要硬刷新 |
| 生产部署 | 无构建步骤、无 hash 文件名、无 CDN；`Dockerfile` 仅 `pip install` + `COPY . .`（`Dockerfile:1-8`），改静态文件需重建镜像或挂卷 |

**推荐做法**：新增页面/模块时统一使用 `?v=<feature>-<n>` 版本键，并在同一改动中递增所有相关引用点的版本号。

### 3.11.6 事件类型目录的扩展

`event_catalog.py:6-193` 是纯 Python 字面量列表。新增事件类型只需追加一个 dict，字段为 `event_type`/`scope`/`title`/`description`/`producer`/`consumer`/`schema`。`event_catalog()` 用 `deepcopy` 返回，`test_event_catalog.py:11-19` 会因数量变化而失败，**必须同步更新该测试的期望集合与 `count`**。

---

## 3.12 响应式与布局结构

只做结构判定，不逐条列样式。

| 断点 | Workflows | 文档 | 模型 | Sessions | 事件 |
| --- | --- | --- | --- | --- | --- |
| `>1100px` | 双列 `minmax(250px,330px) 1fr`，端口/契约双列 | 双列 `minmax(230px,310px) 1fr` | 双列 `minmax(280px,360px) 1fr` | 双列 `minmax(270px,310px) 1fr` | 双列 `310px 1fr` |
| `≤1100px` | 左栏 270px；端口区与契约区**降为单列** | — | — | — | — |
| `≤1000px` | 顶栏 68→112px，品牌绝对定位、导航挪右上 | 左栏 260px、侧栏标题竖排 | — | 左栏 260px、详情头允许换行 | — |
| `≤800px` | — | — | — | — | 单列 + 上下布局（`38vh` 列表 + 详情），事件组变横向滚动条 |
| `≤700px` | 单列、列表限高 240–310px、操作按钮换行 | 单列、列表限高 210–270px、操作按钮竖排拉伸 | 单列（`display:block`）、表单在上 | 单列 + 上下布局（`minmax(200px,32%)`）、导航铺满一行 | — |
| `≤560px` | — | — | — | — | 隐藏 `#catalogState`、摘要 dl 单列 |
| `≤440px` | 对话框页脚压缩内边距 | — | — | — | — |

共同结构：`body` 为 `height:100dvh` 纵向 flex + `overflow:hidden`，`main` 为 `flex:1; min-height:0`，**滚动发生在内部容器**（列表/配置区/编辑器）而非页面（`css/base.css:4,27`）；`main` 宽度 `min(1360px, calc(100% - 48px))` 居中；焦点可见性统一 `:focus-visible { outline:2px solid var(--green); outline-offset:2px }`（`css/base.css:5`）；主色板集中在 `:root`（`css/base.css:1`），而 Workflow 节点/连接配色独立硬编码在 `workflow_canvas.mjs:5-34`（**不在 CSS 变量体系内**）。

## 3.13 测试交叉印证

| 测试文件 | 覆盖 | 关键断言 |
| --- | --- | --- |
| `test_workflows.py`（333 行，11 用例） | `filter_invalid_connections`、`node_format_error` | session/context 连接保留（`:7-27,257-297`）、map-content（`:29-65`）、`construct_message` 的 `role_source=port`（`:67-98`）、history→foreach list-event（`:100-124`）、split_event 两路输出（`:126-161`）、deserialize_json 输出类型变化时**丢弃数据连接但保留 control**（`:163-193`）、`construct_list`→`llm` list-message（`:222-255`）、context 类型变化后丢弃 value 连接（`:299-329`）、重复 output key 报错（`:195-205`）、非法 `value_type` 报错（`:207-220`） |
| `test_sessions.py`（64 行，4 用例） | Session router（`MagicMock` 集合） | 非法值创建被拒且 `insert_one` 未调用（`:18-22`）、`map-content` 仅接受非空 str→str（`:24-35`）、并发写返回 409 且 filter 精确匹配 `{_id, value_type, updated_at}`（`:37-45`）、分页 `next_cursor` 与 `$or` 结构（`:47-60`） |
| `test_event_catalog.py`（37 行，2 用例） | `event_catalog()` | 恰好 7 类、`count==7`、`main_queue` 恰好 5 类（`:11-19`）、每个 schema 的 `event_type.const` 自洽且 `required` 含 `event_type`/`payload`（`:26-33`） |

**未覆盖**：`main.py`（中间件、体积守卫、健康检查）、`documents.py`、`models.py`、`workflows.py` 的 HTTP 层与 `WorkflowRequest` 校验链、全部前端 JS、`workflow_canvas.mjs`。

## 3.14 一句话总结

`manager_webui` 是**无鉴权、无构建步骤、契约极度严格**的五页管理台：它不编辑画布（画布编辑在 8082），只做只读检视 + 依赖改名 + 导入导出，并在每次 Workflow 写入前用 20 步校验链把节点类型、边界端口、Remote Tool 契约、Redis Tool 注册表、MongoDB 模型注册表全部对齐一次；代价是任一环节变动（改端口类型、停用或删除模型、删除被引用的 Workflow）要么被硬拒（400），要么被**静默改写数据**（连接被丢弃）。
