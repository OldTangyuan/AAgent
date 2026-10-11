# 04 Workflow 编辑器（workflow_editor，:8082）

> 类型:审计报告（分节草稿）。
> 性质:现行文档。
> 归属:`workflow_editor/`。
> 适用版本:平台 `0.1.0+`。

> 范围：`workflow_editor/` 全量源码（后端 1 份、HTML 1 份、JS 9 份、CSS 4 份），交叉核对 `agent/workflow_contract.py`、`agent/workflow_validator.py`、`manager_webui/static/workflow_canvas.mjs`。全部结论均带 `文件:行号`。
> 一句话定位：这是一个**纯前端、零持久化的 Workflow 画布编辑器**——后端只提供 3 个只读资源接口与静态文件服务，所有编辑（节点/连线/元数据）只存在于浏览器内存，产出物是导出的 JSON 文件或剪贴板文本。

## 4.1 服务定位与部署

| 项 | 事实 | 出处 |
| --- | --- | --- |
| 服务名 / 容器 | `workflow_editor` / `workflow_editor_aagent` | [docker-compose.yml](../../../docker-compose.yml#L131-L133) |
| 端口 | `8082:8082`（宿主全接口绑定，未绑回环） | [docker-compose.yml](../../../docker-compose.yml#L152) |
| 启动方式 | `uvicorn main:app --host 0.0.0.0 --port 8082` | [Dockerfile](../../../workflow_editor/Dockerfile#L10) |
| 健康检查 | `GET /api/health` | [main.py](../../../workflow_editor/main.py#L81-L83)、[docker-compose.yml](../../../docker-compose.yml#L154) |
| 依赖服务 | redis、mongodb（`depends_on` + `service_healthy`） | [docker-compose.yml](../../../docker-compose.yml#L135-L139) |
| 环境变量 | `REDIS_HOST/PORT/DB/PASSWORD`、`AGENT_TOOLS_KEY`、`TOOL_SERVER_URL`、`MONGO_HOST/PORT/USER/PASS/DATABASE/MODEL_COLLECTION` | [main.py](../../../workflow_editor/main.py#L24-L51) |
| 鉴权 | **无**。三个中间件全部是响应头/日志，无认证依赖、无 CORS、无限流 | [main.py](../../../workflow_editor/main.py#L54-L78) |
| 定位说明 | README 记为「Workflow 可视化编辑器（独立服务，只导出 JSON）」 | [README.md](../../../README.md#L105) |

## 4.2 后端（`workflow_editor/main.py`，160 行）

### 4.2.1 路由全表

| 方法 | 路径 | 行为 | 数据源 | 失败行为 | 行号 |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/health` | 固定返回 `{"status":"ok"}` | 无 | 无 | [main.py:81](../../../workflow_editor/main.py#L81-L83) |
| GET | `/api/models` | 列出可用模型；投影 `name/model/provider`，过滤 `enabled != False`，按 `updated_at` 倒序 | MongoDB `models` 集合 | `PyMongoError` → 503 `{"error":"模型配置暂时不可用"}` | [main.py:86](../../../workflow_editor/main.py#L86-L103) |
| GET | `/api/tools/local` | 列出 Agent 进程内工具；读 Redis Hash，逐条 `json.loads`，跳过解析失败与 `function.name != key` 的不一致项，按名排序 | Redis Hash `AGENT_TOOLS_KEY`（默认 `aagent:tools`） | `redis.RedisError` → 503 `{"error":"Tool 注册表暂时不可用"}` | [main.py:106](../../../workflow_editor/main.py#L106-L133) |
| GET | `/api/tools/remote` | 代理 Tool Server 的 `GET {TOOL_SERVER_URL}/api/tools`（超时 5s），映射为 `{name,description,inputSchema,outputSchema}` | `tool_server:8083` | `URLError/TimeoutError/ValueError` → 503 `{"error":"Remote Tool 目录暂时不可用"}` | [main.py:136](../../../workflow_editor/main.py#L136-L156) |
| — | `/`（mount） | `StaticFiles(directory=static, html=True)`，兜底静态服务并支持目录索引 | `workflow_editor/static/` | 404 | [main.py:159](../../../workflow_editor/main.py#L159-L160) |

**关键结论：没有任何写路由。** 无 POST/PUT/PATCH/DELETE，无 Workflow 保存接口，编辑器确实不落库。这与 [README.md](../../../README.md#L105) 的「只导出 JSON」一致。

### 4.2.2 中间件与缓存策略

`security_headers`（对所有响应，含静态文件，[main.py:54](../../../workflow_editor/main.py#L54-L64)）：

| 响应头 | 值 |
| --- | --- |
| `Content-Security-Policy` | `default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:` |
| `Cache-Control` | `no-store, no-cache, must-revalidate, max-age=0` |
| `Pragma` | `no-cache` |
| `Expires` | `0` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |

**缓存策略判定：`Cache-Control` 已在服务端全局禁用缓存，因此前端 `?v=N` 查询串是冗余的「双保险」，而非必要机制。**

`request_logger`（[main.py:67](../../../workflow_editor/main.py#L67-L78)）：仅对 `path.startswith("/api/")` 记录 `method/path/duration`，静态资源不记日志。

### 4.2.3 静态资源与 `?v=N` 版本串

| 资源 | 引用 | 版本串 |
| --- | --- | --- |
| `/css/base.css` | `<link rel="stylesheet">` | 无 | 
| `/css/workflow.css` | `<link rel="stylesheet">` | `?v=16` |
| `/workflow.js` | `<script type="module">` | `?v=23` |

出处：[workflow_edit.html:8-L9](../../../workflow_editor/static/workflow_edit.html#L8-L9)、[workflow_edit.html:578](../../../workflow_editor/static/workflow_edit.html#L578)。

- `workflow.css` 只是 3 行 `@import`，把 `workflow/layout.css`、`canvas.css`、`inspector.css` 串起来（[workflow.css:1-L3](../../../workflow_editor/static/css/workflow.css#L1-L3)）；子样式表**不带版本串**，其缓存仅靠后端 `no-store` 保证。
- 无外部 CDN、无字体文件、无构建产物；CSP `script-src 'self'` 与纯本地资源一致。
- 无 `favicon.ico`（`img-src` 含 `data:`，但页面未引用任何图标资源）。

### 4.2.4 前端 API 客户端（`static/api.js`，95 行）

| 项 | 事实 | 行号 |
| --- | --- | --- |
| 超时 | `FETCH_TIMEOUT_MS = 5000`，`AbortController` 强制中断 | [api.js:1](../../../workflow_editor/static/api.js#L1)、[api.js:5-L13](../../../workflow_editor/static/api.js#L5-L13) |
| 缓存 | `fetch(..., {cache:'no-store'})` | [api.js:7](../../../workflow_editor/static/api.js#L7) |
| 错误模型 | 非 2xx 抛 `Error(body.error || "HTTP <status>")`；JSON 解析失败降级为 `{}` | [api.js:8-L9](../../../workflow_editor/static/api.js#L8-L9) |
| 编辑器实际使用 | 仅 `fetchModels` / `fetchLocalTools` / `fetchRemoteTools` | [workflow.js:1](../../../workflow_editor/static/workflow.js#L1) |
| 死代码（编辑器未调用） | `fetchEvents`、`deleteEvent`、`updateEvent`、`fetchTerminalHistory`、`submitTerminal`、`fetchDocuments`、`fetchDocument`、`createDocument`、`updateDocument`、`updateDocumentPin`、`deleteDocument` | [api.js:16-L95](../../../workflow_editor/static/api.js#L16-L95) |

这 11 个函数全部指向 WebUI(:8081) 的接口，在本服务不存在对应路由——它们是目录重构时整份拷贝 `api.js` 带过来的遗留，若被调用必然 404。

### 4.2.5 资源加载与失败降级

`workflow.js` 顶部并行发起 3 个请求，各自 `then/catch`（[workflow.js:140-L175](../../../workflow_editor/static/workflow.js#L140-L175)）：

| 请求 | 成功回调 | 失败降级 |
| --- | --- | --- |
| `fetchModels()` | `inspector.setModels(items)` → 过滤 `enabled === true`；计数写入 `resourceState` | `resourceErrors.models = "Models: <msg>"`，编辑器继续可用（模型下拉禁用） |
| `fetchLocalTools()` | `inspector.setLocalTools(items)` → 过滤有名字的项 | `resourceErrors.localTools` |
| `fetchRemoteTools()` | 存 `remoteToolSchemas`，重绘所有 Remote Tool 行的建议列表 | `resourceErrors.remoteTools` |

`renderResourceState()` 把计数与错误拼成 `·` 分隔的一行（[workflow.js:130-L138](../../../workflow_editor/static/workflow.js#L130-L138)），这条文本同时被复用为**元数据表单的校验错误提示位**（[workflow.js:435-L457](../../../workflow_editor/static/workflow.js#L435-L457)）。这是把「资源状态」与「表单错误」混用同一个 DOM 槽位的设计缺陷。

## 4.3 页面骨架与布局结构

`workflow_edit.html` 三段式布局（只说明结构，不逐条列样式）：

| 区域 | 元素 | 内容 | 行号 |
| --- | --- | --- | --- |
| 顶栏 `.topbar` | 品牌 + `.top-actions` | 导入组（从文件导入 / 从文本导入） + 导出组（导出文件 / 导出到剪贴板） | [workflow_edit.html:12-L40](../../../workflow_editor/static/workflow_edit.html#L12-L40) |
| 左栏 `.node-library` | 节点库 | 1 个固定 Input 说明卡 + 22 个 `[data-add-node]` 按钮 + 动态 `#workflowNodeLibrary`（hidden 占位） + footer 计数 | [workflow_edit.html:43-L166](../../../workflow_editor/static/workflow_edit.html#L43-L166) |
| 中栏 `.workflow-canvas-panel` | 画布 | `.canvas-toolbar`（选中的 Workflow 名 / 连接数 / 状态 + 清空 + 元数据）+ `.workflow-canvas`（grid / svg / nodeLayer / legend） | [workflow_edit.html:168-L185](../../../workflow_editor/static/workflow_edit.html#L168-L185) |
| 右栏 `.node-inspector` | 属性面板 | `#inspectorTitle` / `#inspectorType` / `#inspectorContent` | [workflow_edit.html:187-L193](../../../workflow_editor/static/workflow_edit.html#L187-L193) |
| 对话框 | `<dialog>` ×2 | `#textImportDialog`（文本导入）、`#metadataDialog`（元数据与接口） | [workflow_edit.html:197-L255](../../../workflow_editor/static/workflow_edit.html#L197-L255) |
| `<template>` | ×22 | 5 个元数据模板 + 17 个 Inspector 模板族（共 17 个 `*InspectorTemplate`） | [workflow_edit.html:257-L576](../../../workflow_editor/static/workflow_edit.html#L257-L576) |

CSS 结构（`layout.css` / `canvas.css` / `inspector.css`）：

| 结构点 | 事实 | 行号 |
| --- | --- | --- |
| 三栏栅格 | `grid-template-columns:238px minmax(520px,1fr) 300px`；≤1180px → `210/480/270`；≤900px → `190/420/240` 且 `min-width:800px` | [layout.css:20](../../../workflow_editor/static/css/workflow/layout.css#L20)、[layout.css:141-L142](../../../workflow_editor/static/css/workflow/layout.css#L141-L142) |
| ≤560px 响应式 | 顶栏按钮收成 38px 图标（文字 `sr-only` 化），元数据双栏塌成单栏 | [layout.css:143](../../../workflow_editor/static/css/workflow/layout.css#L143) |
| 画布滚动 | `.workflow-canvas { overflow:auto; cursor:grab; touch-action:none }`，滚动条隐藏 | [canvas.css:1-L2](../../../workflow_editor/static/css/workflow/canvas.css#L1-L2) |
| 网格 | `.canvas-grid` 24×24px 双线性渐变，最小 1800×1200 | [canvas.css:4](../../../workflow_editor/static/css/workflow/canvas.css#L4) |
| 连接层 | `z-index:1; pointer-events:none` | [canvas.css:5](../../../workflow_editor/static/css/workflow/canvas.css#L5) |
| 节点层 | `z-index:2; min-width:1800px; height:1200px` | [canvas.css:14](../../../workflow_editor/static/css/workflow/canvas.css#L14) |
| 图例 | `.canvas-legend` `position:sticky` 左下角，8 种颜色点 | [canvas.css:64-L74](../../../workflow_editor/static/css/workflow/canvas.css#L64-L74) |
| 节点卡 | `width:190px; min-height:116px`；头部 45px + 体部 `max(70, 8+行数*28)` | [canvas.css:15](../../../workflow_editor/static/css/workflow/canvas.css#L15)、[editor.js:221](../../../workflow_editor/static/workflow/editor.js#L221) |
| 端口点 | 12×12 圆点，输入 `left:-7px` / 输出 `right:-7px`，`::after` 用 `data-port-label` 显示标签 | [canvas.css:48-L53](../../../workflow_editor/static/css/workflow/canvas.css#L48-L53) |
| 端口间距 | 行距 28px（`top = 8 + row*28`） | [editor.js:226](../../../workflow_editor/static/workflow/editor.js#L226) |
| 死样式 | `.draft-badge` 在 layout.css 定义但 HTML/JS 中**零引用** | [layout.css:74](../../../workflow_editor/static/css/workflow/layout.css#L74) |

## 4.4 画布交互（逐个动作）

### 4.4.1 动作总表

| # | 动作 | 触发方式 | 实现函数 | 关键边界行为 |
| --- | --- | --- | --- | --- |
| 1 | 新增节点 | 左栏 `[data-add-node]` 按钮 click | `workflow.js:487-495` → `addNode()` [serialization.js:86](../../../workflow_editor/static/workflow/domain/serialization.js#L86-L91) → `createNode()` [node-contract.js:259](../../../workflow_editor/static/workflow/domain/node-contract.js#L259) | 自动选位（4×3 网格，溢出后按 `(n%6, ⌊n/6⌋+4)` 排布）；新增后自动选中并打开 Inspector；`markChanged()` |
| 2 | 新增 Workflow 调用节点 | 动态库 `[data-add-workflow-node]` click | [workflow.js:476-485](../../../workflow_editor/static/workflow.js#L476-L485) | 仅当 `workflow_nodes` 非空时该区可见（否则 `hidden`）；按 name 查引用，找不到直接 return |
| 3 | 删除节点 | Inspector 底部「删除节点」按钮 | [inspector.js:57-63](../../../workflow_editor/static/workflow/inspector/inspector.js#L57-L63) → `deleteNode()` [serialization.js:93](../../../workflow_editor/static/workflow/domain/serialization.js#L93-L98) | 连带删除 `fromId`/`toId` 命中的全部连接；**`id === 'input'` 时直接返回 false，Input 节点不可删**；Input 的 Inspector 模板根本没有删除按钮 |
| 4 | 复制节点 | **不支持** | — | 无独立复制；仅「导出到剪贴板」复制整份 Workflow JSON |
| 5 | 粘贴 | `document` 级 `paste` 事件 | [workflow.js:556-566](../../../workflow_editor/static/workflow.js#L556-L566) | **不是粘贴节点，而是导入整份 Workflow**；仅 `isPristineEditor()` 为真时生效；焦点在 `input/textarea/[contenteditable]` 内时忽略；成功才 `preventDefault` |
| 5b | 「纯净编辑器」判定 | — | [workflow.js:77-87](../../../workflow_editor/static/workflow.js#L77-L87) | 需同时满足：无未保存改动、名称为 `workflow`、描述空、无输入/输出/可调用/远程工具声明、恰好 2 个节点、恰好 1 条连接 |
| 6 | 拖拽移动节点 | 节点体 pointerdown + move | `bindNodeDrag` [editor.js:171-201](../../../workflow_editor/static/workflow/editor.js#L171-L201) | 3px 阈值（`Math.hypot < 3` 不算移动）；钳制 `x,y ∈ [12, layer.scrollWidth/Height - 尺寸 - 12]`；移动中实时 `renderConnections()`；移动**不触发** `markChanged()`（见 4.4.4 缺陷 D1） |
| 7 | 框选 | **不支持** | — | 无 marquee、无多选 |
| 8 | 多选 | **不支持** | — | `editorState.selectedId` 是**单值字符串**（[editor.js:5](../../../workflow_editor/static/workflow/editor.js#L5)） |
| 9 | 缩放（滚轮） | **不支持** | — | 无 `wheel` 监听，无 `scale` 变换 |
| 10 | 缩放（按钮） | **不支持** | — | 工具栏无缩放控件 |
| 11 | 缩放（快捷键） | **不支持** | — | 无键盘绑定 |
| 12 | 平移画布 | 空白处（非 `.flow-node`）左键按下拖动 | `bindCanvasPan` [editor.js:305-326](../../../workflow_editor/static/workflow/editor.js#L305-L326) | 采用 `scrollLeft/scrollTop` 反向位移；`event.target.closest('.flow-node')` 时不平移；加/移除 `.panning` 类切换 `cursor:grabbing` |
| 13 | 网格 | 纯 CSS 背景 | [canvas.css:4](../../../workflow_editor/static/css/workflow/canvas.css#L4) | 24px 网格；**不参与对齐与吸附** |
| 14 | 对齐 / 吸附 | **不支持** | — | 拖拽为自由像素定位，无网格吸附、无辅助线 |
| 15 | 自动布局 | **不支持** | — | 唯一的位置计算是新增节点的 `nextNodePosition()` [node-contract.js:246-257](../../../workflow_editor/static/workflow/domain/node-contract.js#L246-L257) |
| 16 | 撤销 / 重做 | **不支持** | — | 无历史栈、无快照回滚 |
| 17 | 节点右键菜单 | **不支持** | — | 无 `contextmenu` 监听 |
| 18 | 画布右键菜单 | **不支持** | — | 同上（浏览器原生菜单） |
| 19 | 双击节点 | **不支持** | — | 无 `dblclick` 监听 |
| 20 | 单击节点 | 节点卡 click | [editor.js:239](../../../workflow_editor/static/workflow/editor.js#L239) → `selectNode` [editor.js:294-298](../../../workflow_editor/static/workflow/editor.js#L294-L298) | 全量 `renderNodes()` + `renderInspector()`；产生 `.selected` 描边 |
| 21 | 单击空白 | 无处理 | — | 只有 pointerdown 启动平移；**不取消选中**（选中态保持不变） |
| 22 | 删除连接 | 见 4.5.5 | — | 无「选中连接 + Delete」路径 |
| 23 | 窗口 resize | `resize` 事件 | [workflow.js:615](../../../workflow_editor/static/workflow.js#L615) | 仅重算 SVG `viewBox` 与尺寸 |
| 24 | 选中态兜底 | 每次 `renderWorkflow` / `renderInspector` | `ensureSelection` [editor.js:300-303](../../../workflow_editor/static/workflow/editor.js#L300-L303) | 选中节点被删后回落到 `state.nodes[0]`（初始渲染时即 Input） |
| 25 | 布局膨胀 | 每次 `renderNodes` | [editor.js:248-253](../../../workflow_editor/static/workflow/editor.js#L248-L253) | 节点层/连接层尺寸 = `max(1800, 最右节点+20) × max(1200, 最下节点+20)`；**缩小窗口不会回收**，因为基于 `offsetLeft+offsetWidth` 而非视口 |

### 4.4.2 新增节点的选位算法

```
候选格 (row 0..3) × (col 0..2):  x = 52 + col*258,  y = 72 + row*150
占用判定: 与任一现有节点满足 |Δx| ≥ 210 或 |Δy| ≥ 125 即视为该格可用
溢出(12 格用尽): x = 52 + (overflowIndex % 6)*258,  y = 72 + (⌊overflowIndex/6⌋ + 4)*150
  overflowIndex = nodes.length - 12
```
出处 [node-contract.js:246](../../../workflow_editor/static/workflow/domain/node-contract.js#L246-L257)。溢出分支可能导致**与既有节点重叠**（未做占用校验，仅线性排布）。

初始状态固定为 2 节点 / 1 连接（[serialization.js:4-10](../../../workflow_editor/static/workflow/domain/serialization.js#L4-L10)）：`input`@(52,238) → `output`@(310,238)，控制流 `control-out → control-in` 预连。

### 4.4.3 平移与节点拖拽的互斥

- 画布 `pointerdown` 要求 `event.button === 0` 且 `!event.target.closest('.flow-node')`（[editor.js:308](../../../workflow_editor/static/workflow/editor.js#L308)）；
- 节点自身的 pointerdown 未 `stopPropagation`，但画布已用 `closest` 排除，等效互斥；
- 端口 pointerdown 显式 `stopPropagation`（[editor.js:122](../../../workflow_editor/static/workflow/editor.js#L122)）并 `preventDefault`，避免落到节点拖拽；
- 三套 pointer 捕获互相独立：`elements.canvas` / `element(节点)` / `port`，各自保存 `pointerId` 做归属校验，均检查 `hasPointerCapture` 后释放。

### 4.4.4 已确认的交互缺陷

| 编号 | 缺陷 | 证据 |
| --- | --- | --- |
| D1 | **拖动节点不置「未保存」**：`bindNodeDrag` 的 pointermove 只改 `node.x/y` 与 DOM 样式，从不调用 `markChanged()`，`finishDrag` 也不调用。位置变更后直接关页不会触发 `beforeunload` 提示 | [editor.js:179-201](../../../workflow_editor/static/workflow/editor.js#L179-L201)、[workflow.js:609-613](../../../workflow_editor/static/workflow.js#L609-L613) |
| D2 | **`compatible` 端口高亮在拖拽结束时移除、拖拽中不更新**：`setCompatiblePorts()` 只在 pointerdown 调用一次；端口位置随节点拖拽变化时不重算（拖拽期间通常也不改节点位置，影响有限） | [editor.js:54-58](../../../workflow_editor/static/workflow/editor.js#L54-L58)、[editor.js:159](../../../workflow_editor/static/workflow/editor.js#L159) |
| D3 | **删连接 + 取消/失败时状态可能不标脏**：拖输入端把边取走后，若 `markChanged()` 未被执行的分支（不兼容落点、空白落点且无 `connectionId`）不标记改动，UI 上「未保存」不亮 | [editor.js:60-108](../../../workflow_editor/static/workflow/editor.js#L60-L108) |
| D4 | **`offsetWidth` 参与左侧钳制，但宽度未随缩放变化**：左侧硬下限 12px，右侧按 `scrollWidth - offsetWidth - 12`；节点被拖到最右后再拉宽窗口会留在旧钳制位置 | [editor.js:185-188](../../../workflow_editor/static/workflow/editor.js#L185-L188) |
| D5 | **`0` 值字段显示为空**：通用 `[data-field]` 绑定用 `node[field] || ''`，`initial_value_count = 0`、`limit = 0` 等会渲染成空串 | [inspector.js:27](../../../workflow_editor/static/workflow/inspector/inspector.js#L27) |
| D6 | **数字字段先落字符串后落数字**：`[data-field]` 的 `input` 事件把 `field.value`（string）直接写进 `node`；只有 `structure.js` 里单独绑定的字段才 `change` 时转 `int` | [inspector.js:28-33](../../../workflow_editor/static/workflow/inspector/inspector.js#L28-L33) vs [structure.js:128-132](../../../workflow_editor/static/workflow/inspector/structure.js#L128-L132) |
| D7 | **拖拽到节点 body 视为「空白」→ 删除原连接**：`elementFromPoint(...).closest('.node-port')` 为 null 即走空白分支 | [editor.js:68](../../../workflow_editor/static/workflow/editor.js#L68)、[editor.js:101-106](../../../workflow_editor/static/workflow/editor.js#L101-L106) |

## 4.5 连接交互全规则

### 4.5.1 端口 DOM 契约

每个端口是 `<span class="node-port">`，携带 5 个 dataset（[editor.js:227-233](../../../workflow_editor/static/workflow/editor.js#L227-L233)）：

| dataset | 语义 | 用途 |
| --- | --- | --- |
| `portId` | 端口 id（节点内作用域） | 连接端点、`portCenter` 查找 |
| `portDirection` | `input` / `output` | 兼容性判定、锚点方向 |
| `portType` | `control` \| 7 种数据类型 | 强类型匹配 |
| `portMultiple` | `"true"` / `"false"` 字符串 | 单连接约束（控制流输出、控制流输入） |
| `portLabel` | 显示标签（CSS `::after`） | 视觉 |

另有 `aria-label`（方向 + 标签 + 类型）与 `title`（端口语义说明）。`portCenter()` 全部用 dataset 精确相等比较查找，**不把数据拼进 `querySelector`**（[editor.js:18-35](../../../workflow_editor/static/workflow/editor.js#L18-L35)），这是 2026-08-16 审查修复过的注入风险点。

### 4.5.2 连接对象与合法性

连接对象固定 6 字段：`{id, fromId, fromPortId, toId, toPortId, type}`。

合法性判定（`isValidConnection`，[connection-rules.js:11-21](../../../workflow_editor/static/workflow/domain/connection-rules.js#L11-L21)）需**同时满足**：

1. `connection.id` 是非空字符串；
2. `type ∈ {control, content, message, event, map-content, list-content, list-message, list-event}`（共 8 种，7 种数据 + control）；
3. `fromId` 与 `toId` 都能在 `state.nodes` 中找到节点；
4. `portsForNode(source)` 中存在 `id == fromPortId && direction == 'output' && type == connection.type`；
5. `portsForNode(target)` 中存在 `id == toPortId && direction == 'input' && type == connection.type`。

> **强类型语义**：端口类型必须与连接 `type` 严格相等（`endpointPort` 三条件与比较，[connection-rules.js:3-9](../../../workflow_editor/static/workflow/domain/connection-rules.js#L3-L9)）。因此「content 输出 → message 输入」在编辑器里**不可能建立**，也不会被保留。

`filterValidConnections()` 批量过滤（[connection-rules.js:23-25](../../../workflow_editor/static/workflow/domain/connection-rules.js#L23-L25)）；`reconcileConnections(state)` 就地重写 `state.connections`（[connection-rules.js:27-29](../../../workflow_editor/static/workflow/domain/connection-rules.js#L27-L29)）。`reconcileConnections` 在 8 处被调用：切换 role_source、分支增删、内容项增删/改类型、列表类型与数量、foreach 类型、context/session value_type、local tool 换工具、remote tool 换工具、LLM think/tool_calls 开关（[inspector.js:49](../../../workflow_editor/static/workflow/inspector/inspector.js#L49)、[structure.js:18](../../../workflow_editor/static/workflow/inspector/structure.js#L18) 等）。

### 4.5.3 拖拽起点行为（六种状态）

端口 pointerdown 时先把「该端口已存在的边」从 `state.connections` 取出，再按状态决定锚点（[editor.js:120-161](../../../workflow_editor/static/workflow/editor.js#L120-L161)）：

| 起点 | 有无已存边 | 取边逻辑 | 锚点 = 哪一端 | `targetDirection` | 语义 |
| --- | --- | --- | --- | --- | --- |
| 数据**输入端** | 有 | `incoming`（`toId+toPortId+type`） | 上游 `fromId/fromPortId`（output） | `input` | 改接：拖的是上游输出端，落点须是另一个**输入**端 |
| 数据**输入端** | 无 | — | 本节点本端口（input） | `null` | 新建：落点须是**输出**端 |
| 数据**输出端** | 有（任意条） | `outgoing[0]`（仅当恰好 1 条） | 本节点本端口（output） | `null` | 扇出/新建：落点须是**输入**端 |
| 数据**输出端** | 多条 | `connectionId = null`（`outgoing.length === 1` 才取） | 本节点本端口（output） | `null` | 扇出新边，不动已有边 |
| 控制**输入端** | 有 | `incoming` | 上游 `fromId/fromPortId`（output） | `input` | 改接上游 |
| 控制**输出端** | 有（恰好 1 条） | `outgoing[0]` | 下游 `toId/toPortId`（input） | `output` | **反拖**：拖的是下游输入端，落点须是**输出**端 |
| 控制**输出端** | 多条 | 不会发生（`multiple:false` 保证） | 本节点本端口 | `null` | — |

控制流的 `connectionId` 解析式（[editor.js:132](../../../workflow_editor/static/workflow/editor.js#L132)）：

```js
const connectionId = type === 'control'
  ? incoming?.id || (outgoing.length === 1 ? outgoing[0].id : null)
  : incoming?.id || null;
```

> **数据流只认输入端为「已连接」**：从输出端拖拽时 `outgoing` 仅用于控制流，数据流一律新建（扇出）。

### 4.5.4 落点判定与提交（`finishConnectionDrag`）

落点目标用 `document.elementFromPoint(clientX, clientY).closest('.node-port')` 求得（[editor.js:68](../../../workflow_editor/static/workflow/editor.js#L68)）——即**以真实命中测试为准**，与拖拽过程中悬停的 DOM 无关。

`compatiblePort(port, drag)`（[editor.js:44-52](../../../workflow_editor/static/workflow/editor.js#L44-L52)）三条件：

```js
port.dataset.portType === drag.type
&& port.dataset.portDirection === targetDirection      // targetDirection 缺省 = drag.direction 的反向
&& port.dataset.nodeId !== drag.anchorNodeId           // 禁止自环（同一节点）
```

命中兼容端口后，先做**占位清理**，再分三支提交：

**清理（无论哪支都先执行，[editor.js:71-77](../../../workflow_editor/static/workflow/editor.js#L71-L77)）**

```
targetIsInput        = target.dataset.portDirection === 'input'
targetIsSingleOutput = direction === 'output' && dataset.portMultiple !== 'true'
删除条件: item.type === drag.type && (
            (targetIsInput && item.toId === target.nodeId && item.toPortId === target.portId)
         || (targetIsSingleOutput && item.fromId === target.nodeId && item.fromPortId === target.portId))
```

**提交三分支**

| 条件 | 行为 | 结果 | 行号 |
| --- | --- | --- | --- |
| `type !== 'control' && drag.direction === 'input' && connection` | 改接：改写 `connection.toId/toPortId` 后 push | 上游不变，落点改指 | [editor.js:78-81](../../../workflow_editor/static/workflow/editor.js#L78-L81) |
| `type === 'control' && connection` | 按 `drag.direction` 改写 `from*`（output 起点）或 `to*`（input 起点），push | 控制流单端移动 | [editor.js:82-90](../../../workflow_editor/static/workflow/editor.js#L82-L90) |
| 其他 | 新建：按 `anchorDirection` 决定 from/to 归属，生成新 id | 数据流扇出/新建 | [editor.js:91-99](../../../workflow_editor/static/workflow/editor.js#L91-L99) |

新建分支的 from/to 推导（这是 2026-08-16 修复的 P1 缺陷核心，现为正确形态）：

```js
const from = anchorDirection === 'output' ? {anchorNode, anchorPort} : {targetNode, targetPort};
const to   = anchorDirection === 'output' ? {targetNode, targetPort} : {anchorNode, anchorPort};
```
连接 ID：`connection-<Date.now()>-<递增序列>`（[editor.js:13-16](../../../workflow_editor/static/workflow/editor.js#L13-L16)），避免同毫秒碰撞。

**未命中兼容端口的三种结局**

| 情形 | 行为 | 是否标脏 | 行号 |
| --- | --- | --- | --- |
| 落点是非端点元素（节点 body、网格） | `drag.connection` 存在 → 原边回填；不存在则**什么都不做** | 仅回填分支不标脏 | [editor.js:101-102](../../../workflow_editor/static/workflow/editor.js#L101-L102) |
| 落点是不兼容端口（类型/方向/自环不符） | `drag.connection` 存在 → 原边回填；否则**什么都不做** | 不标脏 | 同上 |
| 落点是空白且带 `connectionId`（即把边从端口拖走） | **删除该连接**并 `markChanged()` | 标脏 | [editor.js:103-106](../../../workflow_editor/static/workflow/editor.js#L103-L106) |
| `pointercancel`（系统取消） | `drag.connection` 存在且未被回填 → 塞回 `state.connections`；不提交、不删除 | 不标脏 | [editor.js:63-67](../../../workflow_editor/static/workflow/editor.js#L63-L67) |

> 注意 `target` 为 null 与 `target` 存在但不兼容走的是**同一个 `else if (drag.connection)`** 吗？不是：`else if (target) { if (drag.connection) push }` 与 `else if (drag.connectionId) { 删除 }` 是**互斥**的两支——**落点非空但不是端口** 且 `connectionId` 有值时，`target` 为 null 才走删除（[editor.js:101-106](../../../workflow_editor/static/workflow/editor.js#L101-L106)）；落点是「不兼容端口」时 `target` 非空，只回填、**不删除**。

### 4.5.5 删除连接的四种方式

| 方式 | 是否支持 | 说明 |
| --- | --- | --- |
| 点击连线 | ❌ | SVG 层 `pointer-events:none`（[canvas.css:5](../../../workflow_editor/static/css/workflow/canvas.css#L5)），`<path>` 上无任何监听 |
| 悬停显示删除按钮 | ❌ | 无 hover 交互 |
| 右键删除 | ❌ | 无 `contextmenu` |
| 选中连线 + Delete | ❌ | 无连接选中态、无键盘绑定 |
| **把边从输入端拖到空白** | ✅ | `connectionId` 分支删除（[editor.js:103-106](../../../workflow_editor/static/workflow/editor.js#L103-L106)） |
| **删除节点连带删除** | ✅ | `deleteNode` 按 `fromId`/`toId` 清理（[serialization.js:96](../../../workflow_editor/static/workflow/domain/serialization.js#L96)） |
| **改接时被占位清理** | ✅ | 目标 input 的旧边被同类型新边替换（[editor.js:73-77](../../../workflow_editor/static/workflow/editor.js#L73-L77)） |
| **结构性变更导致失效** | ✅ | `reconcileConnections` 按契约整体重校验，失效边静默消失 |

### 4.5.6 连线渲染与配色语义

路径生成 `connectionPath(start, end)`（[editor.js:37-42](../../../workflow_editor/static/workflow/editor.js#L37-L42)）：

```
curve = max(42, |Δx| * 0.45)
startDirection = (start.direction === 'input') ? -1 : +1
endDirection   = (end.direction === 'output') ? +1 : -1
d = M sx sy C (sx + curve*startDirection) sy, (ex + curve*endDirection) ey, ex ey
```

即三次贝塞尔，控制点水平外扩；**方向由端口 dataset 决定**，所以反向连线（端点角色互换）也能画出正确曲率。

渲染流程（`renderConnections`，[editor.js:258-292](../../../workflow_editor/static/workflow/editor.js#L258-L292)）：以 `max(nodeLayer.scrollWidth, canvas.clientWidth)` 设置 `viewBox/width/height` → 逐条 `state.connections` 用 `portCenter()` 取两端 → 任一端口找不到就 `continue`（**静默跳过，不渲染**）→ 生成 `<path class="connection-path <type>">` → 拖拽中额外追加一条 `preview` 路径 → `replaceChildren` 全量替换 → 更新 `#connectionCount` 文案。

拖拽预览（[editor.js:275-289](../../../workflow_editor/static/workflow/editor.js#L275-L289)）：终点 = 指针坐标（换算进 canvas 坐标系），方向取 `anchorDirection` 的反向；`anchorDirection === 'output'` 时 `connectionPath(anchor, cursor)`，否则 `connectionPath(cursor, anchor)`。

配色（[canvas.css:6-13](../../../workflow_editor/static/css/workflow/canvas.css#L6-L13)）：

| type | 描边色 | 线型 | 语义 |
| --- | --- | --- | --- |
| `control` | `#8b9991`（默认灰） | 实线 2px | 控制流（唯一不虚线） |
| `content` | `var(--blue)` = `#356e9b` | `5 5` 虚线 | Content |
| `message` | `#b75b18` | `2 4` 点线 | Message |
| `event` | `#147d78` | `2 4` 点线 | Event |
| `list-content` | `var(--workflow-list-content)` = `#d12f72`（洋红） | `7 3` 长虚 | List[Content] |
| `list-message` | `#7a3e88` | `7 3` 长虚 | List[Message] |
| `list-event` | `#147d78` | `7 3` 长虚 | List[Event]（与 event 同色，仅线型区分） |
| `map-content` | **未定义** | 回落默认灰实线 | Map-Content **与 control 视觉同色同线型**——图例里也没有 map-content 条目 |

预览路径 `.connection-path.preview`：`stroke-width:2.5; opacity:.7`（[canvas.css:13](../../../workflow_editor/static/css/workflow/canvas.css#L13)）。

端口点配色（[canvas.css:56-63](../../../workflow_editor/static/css/workflow/canvas.css#L56-L63)）：

| port type | 颜色 |
| --- | --- |
| control | `--green` `#13775a` |
| content | `--blue` `#356e9b` |
| message | `#b75b18` |
| event | `#147d78` |
| map-content | `#46713f` |
| list-content | `--workflow-list-content` `#d12f72` |
| list-message | `#7a3e88` |
| list-event | `#147d78` |

图例（`workflow_edit.html:183`）只列 8 项：CONTROL / CONTENT / MESSAGE / EVENT / MAP-CONTENT / LIST-CONTENT / LIST-MESSAGE / LIST-EVENT。

### 4.5.7 非法连接的反馈

| 反馈手段 | 实现 | 强度 |
| --- | --- | --- |
| 兼容端口放大 + 绿环 | `.node-port.compatible`（pointerdown 时一次性打标，[editor.js:54-58](../../../workflow_editor/static/workflow/editor.js#L54-L58)） | 弱（只在起始瞬间标一次） |
| 非法端口**无**任何否定样式 | 无 `.incompatible` 类 | — |
| 落点失败**无** toast / 抖动 / 文案 | 仅静默回填原边或删除 | 无 |
| 控制流重复连接受**静默归一化**而非报错 | 占位清理（[editor.js:73-77](../../../workflow_editor/static/workflow/editor.js#L73-L77)） | 无提示 |
| 导入时失效连接被**静默丢弃** | `filterValidConnections`（[serialization.js:377](../../../workflow_editor/static/workflow/domain/serialization.js#L377)） | 无提示（2026-09-12 报告 P3 已登记） |

## 4.6 连接规则全表

| # | 规则 | 编辑器实现 | 后端对应 | 一致性 |
| --- | --- | --- | --- | --- |
| R1 | 连接方向恒定 output → input | `endpointPort(source,'output') && endpointPort(target,'input')` | `data_ports_for_node` 输出/输入集合 | ✅ |
| R2 | 端口类型必须与连接 type 严格相等（7 种数据 + control，共 8） | `port.dataset.portType === drag.type`；`isValidConnection` 三重比较 | `DATA_CONNECTION_TYPES` + 逐节点 type 断言 | ✅（后端更细，见 R14） |
| R3 | 禁止自环（同一节点的输出→输入） | `port.dataset.nodeId !== drag.anchorNodeId` | **后端不查自环**（`is_valid_connection` 无此判断） | ⚠️ 编辑器更严 |
| R4 | 控制流单后继 | 目标 `multiple !== 'true'` 的输出端触发占位清理 | `control output has multiple successors` 异常 | ✅ |
| R5 | 数据输入单来源 | 目标输入端触发占位清理（同 type） | `data input has multiple sources` 异常 | ✅ |
| R6 | 数据输出可扇出 | 输出端口 `multiple: true`，不清理已有边 | 无约束 | ✅ |
| R7 | 控制流输入单来源 | `control-in` 端口 `multiple: false`；占位清理命中 input 侧 | `connected_control_inputs` 集合（后端只查输出侧唯一性） | ✅ 编辑器更严 |
| R8 | 重复连接归一化 = 替换占位（不报错） | `state.connections.filter(...)` 先删后 push | 后端会**直接报错**（重复即异常） | ⚠️ 语义不同 |
| R9 | 控制流反拖（从输出端拖走 = 移动下游端点） | `hasControlConnection && direction === 'output'` → 锚点取下端 | 无对应概念 | — |
| R10 | 数据流反拖（从输入端拖走 = 移动上游端点） | `hasDataInputConnection` → 锚点取上游，`targetDirection='input'` | 无对应概念 | — |
| R11 | 拖到空白/不兼容 → 回滚原连接 | 回填 `drag.connection` | — | — |
| R12 | 拖到空白且无原连接对象 → 删除该条边 | `else if (drag.connectionId)` 删除 | — | — |
| R13 | 结构性变更后**整体重校验**并丢弃失效边 | `reconcileConnections(state)` | `filter_connections` | ✅ 同构 |
| R14 | 后端额外语义（编辑器不校验） | — | ① `llm.messages-in` 必须 `list-message`；② `llm.tool_calls` 输出必须 `list-content`；③ tool 节点参数名/类型须与 `remote_tools` 声明**逐项相等**；④ 边界端口 `workflowPorts` 必须与顶层 `input_ports/output_ports` 完全相等；⑤ **所有必需控制端口必须已连接**（`control ports must be connected`）；⑥ `input` 节点恰好 1 个、至少有 1 个 `output` 节点 | ⚠️ 编辑器**不阻止**「画布合法但执行期被拒」的状态 |
| R15 | 编辑器更严之处 | 中间节点的数据端口类型也强制相等 | Python `filter_connections` 只查端口存在性 | ⚠️ 已知 P2（[审查报告 2026-09-12 §3](../../审查日志/2026-09-12-workflow编辑器-前端目录重构-审查报告.md)） |
| R16 | 循环控制流 | `foreach` 的 `loop-out → loop-in` 是一条普通控制流边，编辑器和后端都**不拒绝成环** | 后端环检测由执行器负责 | ✅ |

> R14⑤ 是最容易踩的坑：编辑器允许保存「未接控制流的节点」，但 `validate_workflow` 会因缺失控制端口而拒绝执行。编辑器侧**没有任何**「控制端口未连接」的提示 UI。

## 4.7 节点与端口全表

### 4.7.1 节点类型总表（24 类）

| # | type | 中文名 | 节点库按钮 | 符号 | 顶边色 | 默认参数 | 模板行号 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `input` | Input（固定，不可删） | 非按钮（`.library-item.fixed`） | IN | `--ink` | 无 | — |
| 2 | `output` | Output | `data-add-node="output"` | OUT | `#7a3e88` | `workflowPorts` 来自 `output_ports` | [334](../../../workflow_editor/static/workflow_edit.html#L328-L331) |
| 3 | `router` | Router | ✅ | R | `--amber` `#c18413` | `branches:[分支1,分支2]` | [333](../../../workflow_editor/static/workflow_edit.html#L333-L345) |
| 4 | `llm` | LLM | ✅ | L | `--blue` `#356e9b` | `model:'', tools:[], think:false, tool_calls:false` | [347](../../../workflow_editor/static/workflow_edit.html#L347-L360) |
| 5 | `construct_message` | 构造 Message | ✅ | M | `#b75b18` | `role_source:'fixed', role:'user'` | [362](../../../workflow_editor/static/workflow_edit.html#L362-L372) |
| 6 | `construct_content` | 构造 Content | ✅ | C | `#2f6f8f` | `append_items:[{type:'fixed',value:''}], dataInputPorts:[]` | [515](../../../workflow_editor/static/workflow_edit.html#L515-L520) |
| 7 | `construct_map_content` | 构造 Map-Content | ✅ | MAP | `#46713f` | `mappings:[{key:'key1',value:''}]` | [382](../../../workflow_editor/static/workflow_edit.html#L382-L393) |
| 8 | `map_content_get` | Map-Content 查找 | ✅ | GET | `#326b4b` | 无 | [395](../../../workflow_editor/static/workflow_edit.html#L395-L401) |
| 9 | `split_event` | 拆分 Event | ✅ | E/ | `#147d78` | 无 | [374](../../../workflow_editor/static/workflow_edit.html#L374-L380) |
| 10 | `deserialize_json` | 反序列化 JSON | ✅ | J/ | `#61568a` | `outputs:[{key:'value',type:'content'}]` | [403](../../../workflow_editor/static/workflow_edit.html#L403-L414) |
| 11 | `construct_list` | 构造列表 | ✅ | L | `#176f73` | `item_type:'content', initial_value_count:1, dataInputPorts:['content-in-0']` | [416](../../../workflow_editor/static/workflow_edit.html#L416-L424) |
| 12 | `list_append` | List 追加 | ✅ | L+ | `#27705b` | `item_type:'content', position:'end'` | [435](../../../workflow_editor/static/workflow_edit.html#L435-L443) |
| 13 | `foreach` | 遍历列表 | ✅ | FE | `#9a5a24` | `item_type:'content'` | [426](../../../workflow_editor/static/workflow_edit.html#L426-L433) |
| 14 | `history` | 召回 History | ✅ | H | `#396a87` | `event_types:['terminal','response'], limit:10` | [445](../../../workflow_editor/static/workflow_edit.html#L445-L459) |
| 15 | `context_create` | 创建 Context | ✅ | C+ | `#326b4b` | `value_type:'content'` | [461](../../../workflow_editor/static/workflow_edit.html#L461-L468) |
| 16 | `context_read` | 读取 Context | ✅ | CR | `#376c78` | `value_type:'content'` | [470](../../../workflow_editor/static/workflow_edit.html#L470-L477) |
| 17 | `context_write` | 修改 Context | ✅ | CW | `#8a5b2d` | `value_type:'content'` | [479](../../../workflow_editor/static/workflow_edit.html#L479-L486) |
| 18 | `session_create` | 创建 Session | ✅ | S+ | `#187b70` | `value_type:'content'` | [488](../../../workflow_editor/static/workflow_edit.html#L488-L495) |
| 19 | `session_read` | 读取 Session | ✅ | SR | `#28749c` | `value_type:'content'` | [497](../../../workflow_editor/static/workflow_edit.html#L497-L504) |
| 20 | `session_write` | 修改 Session | ✅ | SW | `#ab6740` | `value_type:'content'` | [506](../../../workflow_editor/static/workflow_edit.html#L506-L513) |
| 21 | `local_tool` | Local Tool | ✅ | LT | `--green` `#13775a` | `tool:'', parameters:[]` | [522](../../../workflow_editor/static/workflow_edit.html#L522-L529) |
| 22 | `remote_sync_tool` | Remote Sync Tool | ✅ | RS | `#a94f36` | `tool:'', parameters:[], outputs:[], timeout_ms:10000` | [531](../../../workflow_editor/static/workflow_edit.html#L531-L541) |
| 23 | `remote_async_tool` | Remote Async Tool | ✅ | RA | `#b47a22` | `tool:'', parameters:[], timeout_ms:600000, callback:null` | [543](../../../workflow_editor/static/workflow_edit.html#L543-L567) |
| 24 | `workflow` | 可调用 Workflow | 动态库 `data-add-workflow-node` | WF | `#785d9b` | `workflow_name, input_ports, output_ports` 来自声明 | [569](../../../workflow_editor/static/workflow_edit.html#L569-L576) |

类型枚举权威定义：[node-contract.js:3-28](../../../workflow_editor/static/workflow/domain/node-contract.js#L3-L28)（前端）与 [workflow_contract.py:17-42](../../../agent/workflow_contract.py#L17-L42)（后端），**两边 24 项逐字相同**。节点库按钮共 22 个 `[data-add-node]`（Input 不是按钮，`workflow` 是动态生成）。

节点卡符号映射见 [editor.js:208](../../../workflow_editor/static/workflow/editor.js#L208)；顶边色见 [canvas.css:15-41](../../../workflow_editor/static/css/workflow/canvas.css#L15-L41) 与 [layout.css:36-58](../../../workflow_editor/static/css/workflow/layout.css#L36-L58)。

### 4.7.2 端口契约全表

`multiple` 语义：`true` → 允许扇出（数据输出）；`false` → 单连接（控制端口 + 数据输入）。`contract` 字段用于 Inspector 契约区显示。

| 节点 | 输入端口（id : 类型, multiple） | 输出端口 | 动态来源 | 行号 |
| --- | --- | --- | --- | --- |
| `input` | — | `control-out` : control(false)；`workflow:<name>` : 边界类型(true) | `node.workflowPorts` ← 顶层 `input_ports` | [49](../../../workflow_editor/static/workflow/domain/node-contract.js#L49-L54) |
| `output` | `control-in` : control(false)；`workflow:<name>` : 边界类型(false) | — | `node.workflowPorts` ← 顶层 `output_ports` | [55](../../../workflow_editor/static/workflow/domain/node-contract.js#L55-L60) |
| `router` | `control-in` : control(false)；`content-in` : content(false) | `branches[i].id` : control(false)，label = 分支名 | `node.branches` | [61](../../../workflow_editor/static/workflow/domain/node-contract.js#L61-L67) |
| `construct_message` | `control-in`；`content-in` : content；`role-in` : content（**仅当** `role_source === 'port'`） | `control-out`；`message-out` : message(true) | `node.role_source` | [68](../../../workflow_editor/static/workflow/domain/node-contract.js#L68-L78) |
| `construct_content` | `control-in`；`append-in-N` : content(false)，label = `内容 N` | `control-out`；`content-out` : content(true) | `node.dataInputPorts` | [79](../../../workflow_editor/static/workflow/domain/node-contract.js#L79-L89) |
| `construct_map_content` | `control-in` | `control-out`；`map-out` : map-content(true) | 固定 | [90](../../../workflow_editor/static/workflow/domain/node-contract.js#L90-L96) |
| `map_content_get` | `control-in`；`map-in` : map-content；`key-in` : content | `control-out`；`content-out` : content(true) | 固定 | [97](../../../workflow_editor/static/workflow/domain/node-contract.js#L97-L105) |
| `split_event` | `control-in`；`event-in` : event | `control-out`；`type-out` : content(true)；`payload-out` : content(true) | 固定 | [106](../../../workflow_editor/static/workflow/domain/node-contract.js#L106-L114) |
| `deserialize_json` | `control-in`；`content-in` : content | `control-out`；`outputs[i].key` : `outputs[i].type`(true) | `node.outputs`（**动态输出**） | [115](../../../workflow_editor/static/workflow/domain/node-contract.js#L115-L122) |
| `construct_list` | `control-in`；`{item_type}-in-N` : `item_type`(false) | `control-out`；`list-out` : `list-{item_type}`(true) | `item_type` + `initial_value_count` + `dataInputPorts` | [123](../../../workflow_editor/static/workflow/domain/node-contract.js#L123-L138) |
| `list_append` | `control-in`；`list-in` : `list-{item_type}`；`item-in` : `{item_type}` | `control-out`；`list-out` : `list-{item_type}`(true) | `node.item_type` | [139](../../../workflow_editor/static/workflow/domain/node-contract.js#L139-L147) |
| `foreach` | `control-in`；`loop-in` : control（循环体结束）；`list-in` : `list-{item_type}` | `control-out`；`loop-out` : control（循环体开始）；`item-out` : `{item_type}`(true) | `node.item_type` | [148](../../../workflow_editor/static/workflow/domain/node-contract.js#L148-L157) |
| `history` | `control-in` | `control-out`；`events` : list-event(true) | 固定 | [158](../../../workflow_editor/static/workflow/domain/node-contract.js#L158-L164) |
| `context_create` / `session_create` | `control-in`；`initial-value` : `value_type` | `control-out`；`context-id`/`session-id` : content(true) | `node.value_type` | [165](../../../workflow_editor/static/workflow/domain/node-contract.js#L165-L175) |
| `context_read` / `session_read` | `control-in`；`context-id`/`session-id` : content | `control-out`；`value-out` : `value_type`(true) | `node.value_type` | [176](../../../workflow_editor/static/workflow/domain/node-contract.js#L176-L186) |
| `context_write` / `session_write` | `control-in`；`context-id`/`session-id` : content；`value-in` : `value_type` | `control-out`；`context-id`/`session-id` : content(true)；`value-out` : `value_type`(true) | `node.value_type` | [187](../../../workflow_editor/static/workflow/domain/node-contract.js#L187-L199) |
| `local_tool` | `control-in`；每个参数名 : content | `control-out`；`output` : content(true) | `node.parameters`（string[]） | [200](../../../workflow_editor/static/workflow/domain/node-contract.js#L200-L226) |
| `remote_sync_tool` | `control-in`；每个参数名 : 参数类型 | `control-out`；`outputs[i].name` : `outputs[i].type`(true) | `node.parameters`（对象数组）、`node.outputs` | 同上 |
| `remote_async_tool` | `control-in`；每个参数名 : 参数类型 | `control-out`；`task_id` : content(true) | `node.parameters` | 同上 |
| `workflow` | `control-in`；`workflow:<name>` : 声明类型 | `control-out`；`workflow:<name>` : 声明类型(true) | `node.input_ports` / `node.output_ports` | [227](../../../workflow_editor/static/workflow/domain/node-contract.js#L227-L234) |
| `llm`（兜底分支） | `control-in`；`messages-in` : list-message | `control-out`；`output` : content(true)；`reasoning` : content(true)（**仅当** `think === true`）；`tool_calls` : list-content(true)（**仅当** `tool_calls === true`） | `node.think` / `node.tool_calls` | [235](../../../workflow_editor/static/workflow/domain/node-contract.js#L235-L243) |

> `portsForNode()` 的 `llm` 分支是**函数末尾的兜底 `return`**：任何没被前面 if 命中的 type 都会落到这里。目前只有 `llm` 会到达该处（其余 23 类都有显式分支），但这是**隐式契约**——新增节点类型若漏写分支，会静默获得 LLM 的端口而不是报错。

### 4.7.3 边界端口（Input / Output / 可调用 Workflow）

| 项 | 事实 | 行号 |
| --- | --- | --- |
| 结构 | 顶层 `input_ports` / `output_ports` 元素为 `{name, type}` | [workflow_edit.html:257-263](../../../workflow_editor/static/workflow_edit.html#L257-L263) |
| 节点内结构 | `workflowPorts` 元素为 `{id, name, type}`，`id = "workflow:" + name` | [node-contract.js:37-42](../../../workflow_editor/static/workflow/domain/node-contract.js#L37-L42) |
| 类型白名单 | `DATA_TYPES` 7 种；非法 type 的端口被 `flatMap` 静默丢弃 | [node-contract.js:39](../../../workflow_editor/static/workflow/domain/node-contract.js#L39) |
| name 截断 | `name.slice(0, 80)` —— **id 用未截断名拼接**，>80 字符时 `id !== "workflow:"+name`，后端 `_validate_workflow_ports` 会拒（已登记 P1） | [node-contract.js:40](../../../workflow_editor/static/workflow/domain/node-contract.js#L40)、[报告 §3](../../审查日志/2026-09-12-workflow编辑器-前端目录重构-审查报告.md) |
| 名称长度约束 | HTML `maxlength="80"`（元数据端口行） | [workflow_edit.html:259](../../../workflow_editor/static/workflow_edit.html#L259) |
| Input 节点 | 不可新增第二个（库中非按钮）、不可删除（`deleteNode('input') === false`）、导入时强制要求恰好 1 个 | [serialization.js:94](../../../workflow_editor/static/workflow/domain/serialization.js#L94)、[serialization.js:364](../../../workflow_editor/static/workflow/domain/serialization.js#L364) |
| Output 节点 | 可多个；导入时若一个都没有则自动补建并带上当前 `workflowPorts` | [serialization.js:365-368](../../../workflow_editor/static/workflow/domain/serialization.js#L365-L368) |

### 4.7.4 节点配色规范汇总

| 语义层 | 端口点 | 连线 | 节点顶边 | 节点库符号 |
| --- | --- | --- | --- | --- |
| control | `#13775a` | `#8b9991` 实线 | —（input 用 `--ink`） | — |
| content | `#356e9b` | `#356e9b` `5 5` | `#2f6f8f`（构造 Content）/ `--blue`（LLM） | 同顶边 |
| message | `#b75b18` | `#b75b18` `2 4` | `#b75b18` | 同顶边 |
| event | `#147d78` | `#147d78` `2 4` | `#147d78` | 同顶边 |
| map-content | `#46713f` | **缺省灰实线**（未定义） | `#46713f` | 同顶边 |
| list-content | `#d12f72` | `#d12f72` `7 3` | `#176f73`（构造列表） | 同顶边 |
| list-message | `#7a3e88` | `#7a3e88` `7 3` | — | — |
| list-event | `#147d78` | `#147d78` `7 3` | — | — |

调色板来源 [base.css:1](../../../workflow_editor/static/css/base.css#L1)：`--green:#13775a` `--blue:#356e9b` `--amber:#c18413` `--workflow-list-content:#d12f72` `--red:#b8483d`。

## 4.8 属性面板（Inspector）

### 4.8.1 渲染调度

`renderInspector()`（[inspector.js:11-64](../../../workflow_editor/static/workflow/inspector/inspector.js#L11-L64)）流程：

1. `editor.ensureSelection()` → 取回选中 id；
2. `nodeById(selectedId) || state.nodes[0]` → 兜底第一个节点；
3. 写 `#inspectorTitle`（`node.name`）与 `#inspectorType`（`node.type.toUpperCase()`）；
4. `document.querySelector('#' + node.type + 'InspectorTemplate')` → `replaceChildren(cloneNode(true))`（**每次全量重建，不保留输入焦点**）；
5. `input` 类型 → 只渲染接口契约后 `return`（**Input 没有删除按钮、没有任何可编辑字段**）；
6. `integrations.prepare(node)` → 模型/工具下拉的数据准备；
7. `renderInterfaceContract(node)` → 由 `portsForNode()` 动态生成端口清单（**契约是派生的，不是静态 HTML**）；
8. 遍历 `[data-field]` 做**通用字段绑定**；
9. `bindStructureInspector(node, context)` → 结构编辑器；
10. `integrations.bind(node)` → 集成控件事件；
11. `construct_message` 特判：`role_source` 单选 + role 显隐；
12. 绑 `[data-delete-node]`。

`editor.setInspectorRenderer(renderInspector)` 在 [inspector.js:109](../../../workflow_editor/static/workflow/inspector/inspector.js#L109) 完成注入，保证 `selectNode()` 能触发面板重绘。

### 4.8.2 通用字段绑定（`[data-field]`）

```js
for (const field of elements.inspectorContent.querySelectorAll('[data-field]')) {
  field.value = node[field.dataset.field] || '';
  field.addEventListener('input', () => {
    node[field.dataset.field] = field.value;      // 原样写入（可能是 string）
    markChanged();
    editor.renderNodes();                          // 只重绘节点层，不动 Inspector
    elements.inspectorTitle.textContent = node.name; // 只有 name 需要即时同步
  });
}
```
出处 [inspector.js:26-34](../../../workflow_editor/static/workflow/inspector/inspector.js#L26-L34)。`renderNodes()` 而非 `renderInspector()` 是刻意的——避免重建 DOM 丢焦点；代价是**端口契约区不会随字段变化刷新**（只有显式调用 `renderInspector` 的字段才会）。

### 4.8.3 各节点可编辑项总表

| 节点 | 通用 `[data-field]` | 专用控件 | 结构编辑函数 | 提交时机 |
| --- | --- | --- | --- | --- |
| `input` | — | — | — | — |
| `output` | — | 删除节点 | — | — |
| `router` | `name`(30) | 分支名输入×N、删除分支×N、`+ 添加分支` | `bindBranches` [structure.js:24](../../../workflow_editor/static/workflow/inspector/structure.js#L24-L50) | 名 `input` 即时；增删立即 `renderInspector()` |
| `llm` | `name`(30)、`model`(select) | `data-think`、`data-tool-calls`、`data-tool` 复选框组 + `data-tool-count` | `bindLlm` [integrations.js:176](../../../workflow_editor/static/workflow/inspector/integrations.js#L176-L199) | change 即时；think/tool_calls 变更后 `renderInspector()` |
| `construct_message` | `name`、`role`(select 4 项) | `data-role-source` 单选（fixed/port） | `bindBranches` 之外的 [inspector.js:37-56](../../../workflow_editor/static/workflow/inspector/inspector.js#L37-L56) | radio `change` → `reconcileConnections` + 重绘 |
| `construct_content` | `name` | 每项：来源 select（port/fixed）、`data-append-port` code、固定值 textarea(100000)、删除×N、`+ 添加内容项` | `bindConstructContent` [structure.js:52](../../../workflow_editor/static/workflow/inspector/structure.js#L52-L116) | 文本 `input` 即时；类型/增删立即重绘 |
| `construct_map_content` | `name` | 每项：`data-map-key`(1000)、`data-map-value`(100000)、删除×N、`+ 添加映射` | `bindContentMap` [structure.js:224](../../../workflow_editor/static/workflow/inspector/structure.js#L224-L261) | key `change`（查重）、value `input` |
| `map_content_get` | `name` | — | — | — |
| `split_event` | `name` | — | — | — |
| `deserialize_json` | `name` | 每项：`data-output-key`(80)、`data-output-type`(7 项 select)、删除×N、`+ 添加输出` | `bindDeserializeJson` [structure.js:185](../../../workflow_editor/static/workflow/inspector/structure.js#L185-L222) | key `change`（查重 + 拒 `control-out`）、type `change` |
| `construct_list` | `name`、`item_type`(3 项)、`initial_value_count`(number 0–20) | — | `bindConstructList` [structure.js:118](../../../workflow_editor/static/workflow/inspector/structure.js#L118-L133) | `change`；重建 `dataInputPorts` |
| `list_append` | `name`、`item_type`、`position`(start/end) | — | `bindListAppend` [structure.js:167](../../../workflow_editor/static/workflow/inspector/structure.js#L167-L174) | `item_type` change |
| `foreach` | `name`、`item_type` | — | `bindForeach` [structure.js:135](../../../workflow_editor/static/workflow/inspector/structure.js#L135-L142) | `change` |
| `history` | `name`、`limit`(number 1–1000) | `data-history-event-type` 复选（terminal/response） | `bindHistory` [structure.js:144](../../../workflow_editor/static/workflow/inspector/structure.js#L144-L165) | 复选 `change`（**至少保留 1 项**：清空时强制回勾）；limit `change` 后回写数值 |
| `context_*` / `session_*` | `name`、`value_type`(7 项 select) | — | `bindContext` [structure.js:176](../../../workflow_editor/static/workflow/inspector/structure.js#L176-L183) | `change` |
| `local_tool` | `name`、`tool`(select) | — | `renderLocalToolSelect` [integrations.js:43](../../../workflow_editor/static/workflow/inspector/integrations.js#L43-L69) | `change` → 用 `inputSchema.properties` 的键重算 `parameters` |
| `remote_sync_tool` | `name`、`tool`(select)、`timeout_ms`(number 1–10000) | — | `bindRemoteTool` [integrations.js:102](../../../workflow_editor/static/workflow/inspector/integrations.js#L102-L119) | tool `change` 拉契约；timeout `input` 即写 `Number()`（**不做范围钳制**） |
| `remote_async_tool` | `name`、`tool`、`timeout_ms`(number 1–3600000) | `data-callback-enabled`、`data-callback-queue`(256)、`data-callback-event-type`(128)、`data-callback-status` 三复选 | `bindCallback` [integrations.js:121](../../../workflow_editor/static/workflow/inspector/integrations.js#L121-L141) | callback 四要素任一变更即重建整个 `node.callback` 对象 |
| `workflow` | `name` | `data-workflow-name`（`readonly`，只展示目标） | — | — |

### 4.8.4 校验与错误提示

| 校验点 | 行为 | 行号 |
| --- | --- | --- |
| `deserialize_json` 输出键 | 空 / 等于 `control-out` / 与其它项重复 → **回退输入框为旧值，静默拒绝** | [structure.js:198-201](../../../workflow_editor/static/workflow/inspector/structure.js#L198-L201) |
| `construct_map_content` 映射键 | 空 / 重复 → 回退旧值，静默拒绝 | [structure.js:237-240](../../../workflow_editor/static/workflow/inspector/structure.js#L237-L240) |
| 分支数量 | ≤ 1 时删除按钮无效果 | [structure.js:40](../../../workflow_editor/static/workflow/inspector/structure.js#L40) |
| 内容项数量 | ≤ 1 时删除按钮无效果 | [structure.js:98](../../../workflow_editor/static/workflow/inspector/structure.js#L98) |
| JSON 输出数量 | ≤ 1 时删除按钮无效果 | [structure.js:210](../../../workflow_editor/static/workflow/inspector/structure.js#L210) |
| 映射数量 | ≤ 1 时删除按钮无效果 | [structure.js:249](../../../workflow_editor/static/workflow/inspector/structure.js#L249) |
| 列表初始值数量 | `Math.min(20, Math.max(0, parseInt || 0))` 就地钳制并回写 | [structure.js:129](../../../workflow_editor/static/workflow/inspector/structure.js#L129) |
| history limit | `Math.min(1000, Math.max(1, parseInt || 1))` 就地钳制并回写 | [structure.js:161](../../../workflow_editor/static/workflow/inspector/structure.js#L161) |
| history 事件类型 | 不允许清空（清空时强制回勾当前项） | [structure.js:151-154](../../../workflow_editor/static/workflow/inspector/structure.js#L151-L154) |
| remote tool timeout | **无范围校验**（`Number(input.value)` 直接写，可在 UI 上超出后端 `timeout_ms <= 10000 / 3600000` 限制） | [integrations.js:115-117](../../../workflow_editor/static/workflow/inspector/integrations.js#L115-L117) |
| LLM 模型 | 语义回退：`node.model` 匹配 `model.model` 或 `model.name` 且唯一 → 迁移为 `id`；空 → 取第 1 个；不可用 → 插入「当前不可用 (x)」选项并保留原值 | [integrations.js:21-41](../../../workflow_editor/static/workflow/inspector/integrations.js#L21-L41) |
| LLM 工具 | 注册表中已消失的工具名会在渲染时被剔除并 `markChanged()` | [integrations.js:146-151](../../../workflow_editor/static/workflow/inspector/integrations.js#L146-L151) |
| local tool 工具 | 名字不在注册表 → 回落第一个工具并重算参数（**空注册表时写空串**） | [integrations.js:45-51](../../../workflow_editor/static/workflow/inspector/integrations.js#L45-L51) |
| remote tool 工具 | 不在元数据声明中 → 下拉首项为占位「选择已注册的 Remote Tool」 | [integrations.js:79-84](../../../workflow_editor/static/workflow/inspector/integrations.js#L79-L84) |
| 面板级错误区 | **Inspector 内部没有任何错误提示容器**（除结构项静默回退）；全局错误都写到画布工具栏的 `#workflowState` / `#resourceState` | — |

### 4.8.5 修改如何回写模型

| 路径 | 机制 |
| --- | --- |
| 直接字段 | `node[field] = field.value`（[inspector.js:29](../../../workflow_editor/static/workflow/inspector/inspector.js#L29)） |
| 结构数组 | `node.branches.splice/push`、`node.append_items.splice/push`、`node.outputs.splice/push`、`node.mappings.splice/push`（[structure.js](../../../workflow_editor/static/workflow/inspector/structure.js) 全文） |
| 联动端口 | `node.dataInputPorts` 在 4 处重建：`syncPorts()`（[structure.js:54-63](../../../workflow_editor/static/workflow/inspector/structure.js#L54-L63)）、`item_type`/`initial_value_count` change（[structure.js:125](../../../workflow_editor/static/workflow/inspector/structure.js#L125)、[structure.js:130](../../../workflow_editor/static/workflow/inspector/structure.js#L130)） |
| 联动工具契约 | `node.parameters` 与 `node.outputs` 从选中的 tool/remote tool 声明 `structuredClone` 覆盖（[integrations.js:49](../../../workflow_editor/static/workflow/inspector/integrations.js#L49)、[integrations.js:63](../../../workflow_editor/static/workflow/inspector/integrations.js#L63)、[integrations.js:107-108](../../../workflow_editor/static/workflow/inspector/integrations.js#L107-L108)） |
| 归一化 | 结构性提交统一走 `commitStructureChange()` = `reconcileConnections` → `markChanged` → `renderNodes` → `renderInspector`（[structure.js:17-22](../../../workflow_editor/static/workflow/inspector/structure.js#L17-L22)） |
| 全局重载 | 元数据对话框「应用」会 `workflowSnapshot()` + `loadSnapshot(snapshot)` 把内存态**整体过一遍归一化**（[workflow.js:466-467](../../../workflow_editor/static/workflow.js#L466-L467)） |

### 4.8.6 `integrations.js` 的职责边界

| 职责 | 内容 | 行号 |
| --- | --- | --- |
| 外部资源缓存 | `modelConfigs` / `localToolSchemas` / `remoteToolReferences` 三个模块级数组 | [integrations.js:5-7](../../../workflow_editor/static/workflow/inspector/integrations.js#L5-L7) |
| `prepare(node)` | 按类型预渲染：LLM 模型下拉、local tool 下拉、remote tool 下拉 + callback 区块回填、workflow 目标名回填 | [integrations.js:9-14](../../../workflow_editor/static/workflow/inspector/integrations.js#L9-L14) |
| `bind(node)` | 只绑 LLM 与 remote tool 的事件（local tool 的事件在 `prepare→renderLocalToolSelect` 内绑） | [integrations.js:16-19](../../../workflow_editor/static/workflow/inspector/integrations.js#L16-L19) |
| 资源注入 | `setModels` / `setLocalTools` / `setRemoteToolReferences`，三者在**当前选中节点类型匹配时**才触发 `renderInspector()`（避免无谓重绘） | [integrations.js:201-214](../../../workflow_editor/static/workflow/inspector/integrations.js#L201-L214) |
| 明确不属于它 | 不处理导入/导出、不处理剪贴板、不发网络请求——**网络请求全部在 `workflow.js` 顶层发起**，本模块只消费结果 | — |

> 命名注意：本文件叫 `integrations.js`，但**与外部系统的互通（导入/导出/文件/剪贴板）全部在 `workflow.js` 里**（[workflow.js:497-607](../../../workflow_editor/static/workflow.js#L497-L607)），本模块实际职责是「节点与外部资源目录（模型/Tool 注册表/Remote Tool 声明）的绑定」。

## 4.9 序列化（domain/serialization.js）

### 4.9.1 内存状态（`state`）

```js
{ name, description, nodes[], connections[], input_ports[], output_ports[], workflow_nodes[], remote_tools[] }
```
初值：[serialization.js:71-80](../../../workflow_editor/static/workflow/domain/serialization.js#L71-L80)。`nodes` 初值为 `input`+`output`，`connections` 初值为 1 条控制流。

### 4.9.2 导出 JSON 结构（`workflowSnapshot()`）

| 字段 | 类型 | 归一化规则 | 行号 |
| --- | --- | --- | --- |
| `name` | string | 导入时 `trim().slice(0,120)` | [serialization.js:369](../../../workflow_editor/static/workflow/domain/serialization.js#L369) |
| `description` | string | `trim().slice(0,2000)` | [serialization.js:371](../../../workflow_editor/static/workflow/domain/serialization.js#L371) |
| `input_ports` | `{name,type}[]` | 经 `boundaryPorts()` 过滤非法 type | [serialization.js:372](../../../workflow_editor/static/workflow/domain/serialization.js#L372) |
| `output_ports` | `{name,type}[]` | 同上 | [serialization.js:373](../../../workflow_editor/static/workflow/domain/serialization.js#L373) |
| `workflow_nodes` | `{name,input_ports,output_ports}[]` | 去重（小写比较）、名称 trim+slice(120)、端口经 `boundaryPorts` 后**剥掉 id** | [serialization.js:126-142](../../../workflow_editor/static/workflow/domain/serialization.js#L126-L142) |
| `remote_tools` | `{name,input_ports,output_ports}[]` | 同上，名称 slice(128) | [serialization.js:144-160](../../../workflow_editor/static/workflow/domain/serialization.js#L144-L160) |
| `nodes` | 见下 | 每个节点过 `compactNodeArguments` | [serialization.js:108](../../../workflow_editor/static/workflow/domain/serialization.js#L108) |
| `connections` | `{id,fromId,fromPortId,toId,toPortId,type}[]` | 原样 | [serialization.js:109](../../../workflow_editor/static/workflow/domain/serialization.js#L109) |

**导出节点字段布局（`compactNodeArguments`，[serialization.js:60-69](../../../workflow_editor/static/workflow/domain/serialization.js#L60-L69)）**：

| 层 | 字段 | 说明 |
| --- | --- | --- |
| 顶层 base | `id`, `type`, `name`, `x`, `y` | `NODE_BASE_FIELDS` 去掉 `arguments` |
| 顶层 shared | `workflowPorts`, `dataInputPorts`, `input_ports`, `output_ports` | `NODE_SHARED_FIELDS`，**留在顶层** |
| `arguments` | 每类型的可配置字段 | 见 4.9.3 |

**导出中不存在 `version` 字段**——尽管 [manager_webui/static/workflow_canvas.mjs:186](../../../manager_webui/static/workflow_canvas.mjs#L186) 会渲染 `VERSION ${workflow.version || 1}`，编辑器从不写出该字段。

### 4.9.3 `arguments` 字段白名单（前端 ↔ 后端逐字一致）

| 节点类型 | `arguments` 允许字段 | 前端 | 后端 |
| --- | --- | --- | --- |
| `input` / `output` / `map_content_get` / `split_event` | `∅` | [serialization.js:15-23](../../../workflow_editor/static/workflow/domain/serialization.js#L15-L23) | [workflow_contract.py:51-75](../../../agent/workflow_contract.py#L51-L75) |
| `router` | `branches` | ✅ | ✅ |
| `construct_message` | `role`, `role_source` | ✅ | ✅ |
| `construct_content` | `append_items` | ✅ | ✅ |
| `construct_map_content` | `mappings` | ✅ | ✅ |
| `deserialize_json` | `outputs` | ✅ | ✅ |
| `construct_list` | `item_type`, `initial_value_count` | ✅ | ✅ |
| `list_append` | `item_type`, `position` | ✅ | ✅ |
| `foreach` | `item_type` | ✅ | ✅ |
| `history` | `event_types`, `limit` | ✅ | ✅ |
| `llm` | `model`, `think`, `tool_calls`, `tools` | ✅ | ✅ |
| `local_tool` | `tool`, `parameters` | ✅ | ✅ |
| `remote_sync_tool` | `tool`, `parameters`, `outputs`, `timeout_ms` | ✅ | ✅ |
| `remote_async_tool` | `tool`, `parameters`, `timeout_ms`, `callback` | ✅ | ✅ |
| `context_*` / `session_*` | `value_type` | ✅ | ✅ |
| `workflow` | `workflow_name` | ✅ | ✅ |

后端可额外在节点顶层允许 `arguments` 键本身（`NODE_BASE_FIELDS` 含 `arguments`），前端 `compactNodeArguments` 会主动生成该键。

### 4.9.4 导入解析链路

```
文本/文件/URL/剪贴板
  └─ parseWorkflowText(text)                          [serialization.js:400]
       ├─ JSON.parse(text)                            → SyntaxError 抛出
       ├─ normalizeImportedWorkflow(imported)          [serialization.js:385]
       │    ├─ 若 imported.workflows 是对象 → 视为「多 Workflow 集合」
       │    │    ├─ main 取 imported.main（有效时）或 Object.entries() 第一项
       │    │    ├─ 空集合 → throw new Error('Workflow 集合为空')
       │    │    └─ 其余 workflow → workflow_nodes[{name,input_ports,output_ports}]
       │    │         main.remote_tools → remote_tools
       │    └─ 否则原样返回
       ├─ 非对象/数组 → throw '内容不是有效的 Workflow JSON'
       ├─ name 非非空字符串 → throw 'Workflow 名称不能为空'
       └─ nodes/connections 非数组 → throw 'Workflow 缺少节点或连接数据'
  └─ loadSnapshot(workflow)                            [serialization.js:343]
       ├─ nodes 数组校验 → false
       ├─ name 校验 → false
       ├─ 逐节点：id 非空字符串 / id 不重复 / type ∈ NODE_TYPES / hasStrictNodeFormat → false
       ├─ normalizeNode(...) 返回 null → false
       ├─ 无 input 节点 → false
       ├─ 无 output 节点 → 自动补建
       └─ connections 经 filterValidConnections（失效边静默丢弃）
```

导入失败**全部表现为返回 `false` 或抛异常，无错误码、无失败原因回显**（调用方只能给出一句通用文案）：

| 入口 | 失败文案 | 行号 |
| --- | --- | --- |
| 文件导入 | `error.message \|\| '导入失败'` → 写 `#workflowState` | [workflow.js:506-512](../../../workflow_editor/static/workflow.js#L506-L512) |
| 文本导入 | `error.message \|\| 'Workflow 文本无效'` → 写 `#textImportError` | [workflow.js:530-537](../../../workflow_editor/static/workflow.js#L530-L537) |
| 新页面打开 | 同上（先 `parseWorkflowText` 预检） | [workflow.js:539-551](../../../workflow_editor/static/workflow.js#L539-L551) |
| 剪贴板 paste | `error.message \|\| '剪贴板导入失败'` | [workflow.js:556-566](../../../workflow_editor/static/workflow.js#L556-L566) |
| URL `?workflow=` | `error.message \|\| 'URL Workflow 导入失败'` | [workflow.js:568-577](../../../workflow_editor/static/workflow.js#L568-L577) |
| 启动时剪贴板自动导入 | `console.warn`（非 NotAllowedError） | [workflow.js:578-585](../../../workflow_editor/static/workflow.js#L578-L585) |
| `loadSnapshot` 返回 false | 抛 `'内容不是有效的 Workflow JSON'`（**信息误导**，实际可能是端口/节点非法） | [workflow.js:67](../../../workflow_editor/static/workflow.js#L67) |

### 4.9.5 严格格式校验（`hasStrictNodeFormat`）

四个「必须同时成立」条件（[serialization.js:42-49](../../../workflow_editor/static/workflow/domain/serialization.js#L42-L49)）：

1. `node.arguments`（缺省 `{}`）必须是**非数组对象**；
2. 节点顶层**不得**出现任何 `NODE_ARGUMENT_FIELDS`（例如 `branches` 直接写在顶层 → 拒）；
3. `arguments` 内**不得**出现任何 `NODE_SHARED_FIELDS`（例如 `arguments.dataInputPorts` → 拒）；
4. `arguments` 内**不得**出现该类型白名单外的键；节点顶层**只能**是 base ∪ shared。

即：**「旧扁平格式」的 Workflow 无法导入**。前端没有扁平格式兼容层（`expandNodeArguments` 只在已经通过 `hasStrictNodeFormat` 之后调用，[serialization.js:51-58](../../../workflow_editor/static/workflow/domain/serialization.js#L51-L58)）。

### 4.9.6 导入归一化缺陷（逐条列证）

| 编号 | 缺陷 | 后果 | 证据 |
| --- | --- | --- | --- |
| N1 | `boundaryPorts` 用未截断名拼 id、`name` 截断 80 | 名 >80 字符时 `id !== "workflow:"+name`，执行期 `_validate_workflow_ports` 拒绝（已知 P1） | [node-contract.js:40](../../../workflow_editor/static/workflow/domain/node-contract.js#L40)、[workflow_validator.py:495](../../../agent/workflow_validator.py#L495-L498) |
| N2 | `normalizeNode` 对 `append_items` 的 `port` 项**不去重**，且全非法项时 `flatMap` 结果为空 | 可产出重复 `port_id` 或空 `append_items`，违反 `_validate_construct_content`（已知 P1） | [serialization.js:193-200](../../../workflow_editor/static/workflow/domain/serialization.js#L193-L200)、[workflow_validator.py:509-539](../../../agent/workflow_validator.py#L509-L539) |
| N3 | 元数据端口名不判空、不 trim | 单个空名可通过前端查重（`''` 只出现一次），后端 `min_length=1` 拒；带前后空格的名称与后端 `strip()` 后不一致 | [workflow.js:434-437](../../../workflow_editor/static/workflow.js#L434-L437) |
| N4 | 失效连接静默丢弃、无计数回显 | 排障困难（已知 P3） | [serialization.js:377](../../../workflow_editor/static/workflow/domain/serialization.js#L377) |
| N5 | workflow 节点缺 `workflow_name` → **整份文档导入失败**（`normalizeNode` 返回 null → `loadSnapshot` 返回 false），而非只删该节点 | 与 P3 描述的「节点被移除」在实现上是**整体失败** | [serialization.js:334](../../../workflow_editor/static/workflow/domain/serialization.js#L334)、[serialization.js:361](../../../workflow_editor/static/workflow/domain/serialization.js#L361) |
| N6 | 远程工具 `parameters` 与声明不一致时**不报错，而是被声明覆盖** | 导入静默改写用户数据；但后端 `validate_workflow` 要求逐项相等，因此覆盖方向是「向合法靠拢」 | [serialization.js:277](../../../workflow_editor/static/workflow/domain/serialization.js#L277)、[serialization.js:296](../../../workflow_editor/static/workflow/domain/serialization.js#L296) |
| N7 | `normalizeNode` 的 `catch` 只在 `loadSnapshot` 最外层（包住整个循环） | 任何节点触发异常 → **整份文档导入失败**（[serialization.js:379-382](../../../workflow_editor/static/workflow/domain/serialization.js#L379-L382)） |
| N8 | `deserialize_json` 的 `outputs` 要求 `Object.keys(output).length === 2`（严格 `{key,type}`） | 带额外字段（如 `name`）的导出无法导入 | [serialization.js:219](../../../workflow_editor/static/workflow/domain/serialization.js#L219) |
| N9 | `normalizeImportedWorkflow` 保留 `main` 之外的 workflow 为 `workflow_nodes`，但**不校验名称重复** | 后 `callableWorkflowMetadata` 会按首次出现去重（小写比较） | [serialization.js:393-395](../../../workflow_editor/static/workflow/domain/serialization.js#L393-L395)、[serialization.js:133-135](../../../workflow_editor/static/workflow/domain/serialization.js#L133-L135) |
| N10 | 导入**不读 `version`**，无版本兼容分支 | 只有「严格格式」一条通道；未来版本字段无意义 | 全文无 `version` 读取 |

## 4.10 导入 / 导出 / 元数据（`workflow.js` 入口层）

### 4.10.1 顶栏按钮

| 按钮 | id | 行为 | 行号 |
| --- | --- | --- | --- |
| 从文件导入 | `#importButton` | `hasUnsavedChanges` 时 `window.confirm('导入会覆盖当前未保存的 Workflow，确定继续吗？')`，确认后触发隐藏 `#importFileInput` 的 click | [workflow.js:497-500](../../../workflow_editor/static/workflow.js#L497-L500) |
| 文件选择 | `#importFileInput` | `accept="application/json,.json"` `hidden`；change 后**先清空 value** 再 `file.text()` → `importWorkflowText` | [workflow_edit.html:18](../../../workflow_editor/static/workflow_edit.html#L18)、[workflow.js:502-512](../../../workflow_editor/static/workflow.js#L502-L512) |
| 从文本导入 | `#textImportButton` | 打开 `#textImportDialog`，清空 textarea 与错误区，**尝试读剪贴板**：能 `parseWorkflowText` 通过才填充 textarea；`NotAllowedError`/`SyntaxError` 静默忽略；最后 `focus()` textarea | [workflow.js:514-528](../../../workflow_editor/static/workflow.js#L514-L528) |
| 导出文件 | `#exportButton` | `JSON.stringify(snapshot, null, 2) + "\n"` → Blob → `URL.createObjectURL` → `<a download>` click → `revokeObjectURL` | [workflow.js:597-607](../../../workflow_editor/static/workflow.js#L597-L607) |
| 导出文件名 | — | `${name.replace(/[<>:"/\\|?*]+/g,'-').replace(/\s+/g,'-')}-${YYYY-MM-DD}.json`（ISO 日期前 10 位） | [workflow.js:603-604](../../../workflow_editor/static/workflow.js#L603-L604) |
| 导出到剪贴板 | `#copyButton` | `navigator.clipboard.writeText`；不可用时降级到隐藏 textarea + `document.execCommand('copy')`，失败抛 `'浏览器不允许访问剪贴板'`；成功写 `#workflowState = '已复制到剪贴板'` | [workflow.js:89-104](../../../workflow_editor/static/workflow.js#L89-L104)、[workflow.js:587-595](../../../workflow_editor/static/workflow.js#L587-L595) |
| 清空 | `#clearButton` | 有未保存改动时 confirm → `resetWorkflow()`（恢复初始 2 节点 1 连接 + 清空全部元数据）→ 清空 Inspector 的 workflow/remote tool 引用 → 状态置「已清空」 | [workflow.js:389-399](../../../workflow_editor/static/workflow.js#L389-L399)、[serialization.js:113-124](../../../workflow_editor/static/workflow/domain/serialization.js#L113-L124) |
| 元数据 | `#metadataButton` | `renderMetadataDialog()` + `showModal()` | [workflow.js:384-387](../../../workflow_editor/static/workflow.js#L384-L387) |

### 4.10.2 文本导入对话框（`#textImportDialog`）

| 控件 | 行为 | 行号 |
| --- | --- | --- |
| textarea `#textImportValue` | `rows=16`、`required`、`spellcheck=false`、placeholder「粘贴 Workflow JSON」 | [workflow_edit.html:204](../../../workflow_editor/static/workflow_edit.html#L204) |
| 覆盖 `#overwriteTextImportButton` | `importWorkflowText(value, '已从文本导入')`；失败写 `#textImportError`，**不关对话框** | [workflow.js:530-537](../../../workflow_editor/static/workflow.js#L530-L537) |
| 在新页面打开 `#openTextImportButton` | 先 `parseWorkflowText` 预检 → `new URL('/workflow_edit.html', origin)` + `searchParams.set('workflow', 原文)` → `window.open('_blank')` → `editorWindow.opener = null`（防 opener 泄漏）→ 关对话框；被拦截抛 `'新窗口被浏览器拦截'` | [workflow.js:539-551](../../../workflow_editor/static/workflow.js#L539-L551) |
| 关闭 `#closeTextImportButton` / 取消 `#cancelTextImportButton` | `dialog.close()` | [workflow.js:553-554](../../../workflow_editor/static/workflow.js#L553-L554) |

**URL 导入的容量风险**：整份 Workflow JSON 作为 `?workflow=` 查询参数（未压缩、未编码上限处理），大工作流会超 URL 长度限制。

### 4.10.3 启动自动导入（`importInitialWorkflow`）

优先级（[workflow.js:568-585](../../../workflow_editor/static/workflow.js#L568-L585)）：

1. `?workflow=` 参数存在 → 导入，状态标「已从 URL 导入」，**直接 return**（不再尝试剪贴板）；
2. 否则若 `isPristineEditor()` 且 `navigator.clipboard.readText` 可用 → 读剪贴板，能解析就导入并标「已从剪贴板自动导入」；`NotAllowedError` 静默，其它 `console.warn`。

> 这是**静默导入**：用户打开页面时若剪贴板里有合法 Workflow，画布会被自动替换，且 `hasUnsavedChanges = true`（`importWorkflowText` 内设置），后续任何操作都会触发 `beforeunload` 拦截。见 4.11 风险表。

### 4.10.4 元数据对话框（`#metadataDialog`）

对话框分 4 个区块（[workflow_edit.html:217-255](../../../workflow_editor/static/workflow_edit.html#L217-L255)）：

| 区块 | 内容 | 添加方式 | 删除方式 |
| --- | --- | --- | --- |
| 基本信息 | Workflow 名称（`maxlength=120`，`required`）、描述（`maxlength=2000`） | — | — |
| 输入接口 | `[data-metadata-port-list="input_ports"]`，每行：名称(`maxlength=80`)+类型(7 项 select)+删除 | 头部 `+`（`[data-add-metadata-port]`） | 行内 `×` |
| 输出接口 | 同上 | 同上 | 同上 |
| 可调用 Workflow | 每行：名称(`maxlength=120`)+删除；双栏输入/输出契约各带 `+` | `#addCallableWorkflowButton` | 行内 `×` |
| Remote Tools | 每行：名称(`maxlength=128`) + `↻`（从 Tool Server 填充）+ `×`；双栏契约 | `#addRemoteToolButton` | 行内 `×` |

**Remote Tool 名称自动补全**（[workflow.js:315-334](../../../workflow_editor/static/workflow.js#L315-L334)）：

- `input` / `focus` 时按 `name + ' ' + description` 小写包含匹配，取前 **8** 条；
- 候选项用 `mousedown`（而非 click）配合 `preventDefault` 选中，避免 input 失焦先行隐藏；
- 仅当 `document.activeElement === input` 且匹配非空时显示。

**从 Tool Server 填充（`↻` 与候选选中共用的 `fillFromSchema`）**（[workflow.js:270-304](../../../workflow_editor/static/workflow.js#L270-L304)）：

```js
workflowType(v) = ['content','message','event','list-content','list-message','list-event']
                    .includes(v['x-workflow-port-type']) ? v['x-workflow-port-type']
                  : v?.type === 'array' ? 'list-content' : 'content'
inputSchema.properties  → 逐属性映射为 {name, type}
outputSchema.properties → 同上
outputSchema 无 properties → 退化为单端口 {name:'result', type:...}
```
未命中同名 schema 时写 `#resourceState = 'Tool Server 中没有同名 Remote Tool'`（[workflow.js:271-274](../../../workflow_editor/static/workflow.js#L271-L274)）。

**「应用」提交校验链（`#metadataForm` submit，[workflow.js:425-474](../../../workflow_editor/static/workflow.js#L425-L474)）**：

1. `event.submitter?.value === 'cancel'` → 直接返回（关闭按钮 `value="cancel"`）；
2. `preventDefault()` + `reportValidity()`（原生 required/maxlength 校验）；
3. 读 4 组数据：顶层 input/output 端口、可调用 Workflow 列表、Remote Tool 列表；
4. **同侧端口名不得重复**（小写比较，覆盖所有 port list）→ 提示「同一侧接口名称不能重复」；
5. **可调用 Workflow 名不得重复** → 「可调用 Workflow 名称不能重复」；
6. **Remote Tool 名不得重复** → 「Remote Tool 名称不能重复」；
7. **被画布节点引用的 Workflow 不得删除**（按 `previous_name || name` 集合判断）→ 「"X"仍被画布节点调用」；
8. **被画布节点引用的 Remote Tool 不得删除** → 同上；
9. `syncCallableWorkflowNodes()` / `syncRemoteToolNodes()` → 沿 `previous_name` 把重命名传播到画布节点的 `workflow_name` / `tool`，并用新契约覆盖 `input_ports/output_ports` / `parameters/outputs`；
10. 写回 `state.name/description/input_ports/output_ports/workflow_nodes/remote_tools`（剥掉 `previous_name` 临时字段）；
11. `loadSnapshot(workflowSnapshot())` 整体重新归一化；
12. 刷新 Inspector 引用、`markChanged()`、更新标题、`renderWorkflow()`、`close()`。

`previous_name` 通过 `row.dataset.previousName` 承载（[workflow.js:225](../../../workflow_editor/static/workflow.js#L225)、[workflow.js:263](../../../workflow_editor/static/workflow.js#L263)），提交时用 `row.dataset.previousName` 读取（[workflow.js:254](../../../workflow_editor/static/workflow.js#L254)），因为 `readCallableWorkflows` 返回对象后再解构。

### 4.10.5 未保存状态与离开拦截

| 机制 | 事实 | 行号 |
| --- | --- | --- |
| `hasUnsavedChanges` | 模块级布尔；`markChanged()` 置 true 并写状态文案「未保存」+ 去掉 `.saved` 类 | [workflow.js:49-55](../../../workflow_editor/static/workflow.js#L49-L55) |
| 状态文案 | `#workflowState`，取值：`未保存` / `已清空` / `已复制到剪贴板` / `已从文本导入` / `已从 URL 导入` / `已从剪贴板自动导入` / 各错误 message | 全文 |
| `.saved` 类 | CSS 存在（`color:var(--green)`，[layout.css:5](../../../workflow_editor/static/css/workflow/layout.css#L5)），但**代码中只有 `classList.remove('saved')`，从无 `add`** → 死类 | [workflow.js:54](../../../workflow_editor/static/workflow.js#L54) 等 5 处 |
| 离开拦截 | `beforeunload` 在 `hasUnsavedChanges` 时 `preventDefault()` + `returnValue=''` | [workflow.js:609-613](../../../workflow_editor/static/workflow.js#L609-L613) |
| **无「保存」** | 没有保存按钮、没有保存快捷键、没有自动保存到 localStorage | 全文 |

## 4.11 快捷键全表

> **结论：本编辑器只有 1 个键盘级绑定，没有任何用户可用的编辑快捷键。** 对 `keydown`/`keyup`/`keypress`/`ctrlKey`/`metaKey`/`shiftKey`/`altKey`/`Delete`/`Backspace` 的全目录检索为**零命中**。

| # | 按键 / 组合 | 行为 | 实现位置 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | `Ctrl+V` / `⌘V`（粘贴） | 若编辑器「纯净」且焦点不在输入控件内 → **导入剪贴板里的整份 Workflow**（不是粘贴节点）；解析失败则把错误写到 `#workflowState`，且**不** `preventDefault` | [workflow.js:556-566](../../../workflow_editor/static/workflow.js#L556-L566) | 唯一的全局键盘绑定；受 `isPristineEditor()` 严格限制 |
| 2 | `Tab` / `Shift+Tab` | 浏览器原生焦点遍历（节点卡是 `<button>`，端口是 `<span>`） | — | 非自定义 |
| 3 | `Enter` / `Space` | 触发焦点元素的 click（节点卡可键盘选中；`<dialog>` 内表单原生提交行为） | [editor.js:204](../../../workflow_editor/static/workflow/editor.js#L204) | 原生 |
| 4 | `Esc` | 关闭 `<dialog>`（`showModal()` 的原生行为） | [workflow_edit.html:197](../../../workflow_editor/static/workflow_edit.html#L197)、[workflow_edit.html:217](../../../workflow_editor/static/workflow_edit.html#L217) | 原生 |
| 5 | 数字/文本输入 | 只在 `<input>`/`<textarea>` 内生效 | — | 原生 |
| 6 | `Ctrl+C` | **未绑定**（浏览器复制选中文本；画布内容不可选中） | — | 硬性不存在的功能 |

**明确不存在**：`Delete`/`Backspace` 删节点、`Ctrl+Z`/`Ctrl+Shift+Z`/`Ctrl+Y` 撤销重做、`Ctrl+D` 复制、`Ctrl+A` 全选、`Ctrl+S` 保存、`Ctrl+滚轮` 缩放、`+`/`-`/`0` 缩放、`Space` 拖拽平移、方向键微调节点、`Ctrl+Shift+V` 粘贴节点。

## 4.12 与后端的接口契约与一致性

### 4.12.1 编辑器 ↔ `agent/workflow_contract.py` 的字段级一致性

| 契约项 | 前端 | 后端 | 一致性 |
| --- | --- | --- | --- |
| 节点类型集合（24） | `NODE_TYPES` [node-contract.js:3-28](../../../workflow_editor/static/workflow/domain/node-contract.js#L3-L28) | `SUPPORTED_NODE_TYPES` [workflow_contract.py:17-42](../../../agent/workflow_contract.py#L17-L42) | ✅ 逐字相同 |
| 数据连接类型（7） | `DATA_TYPES` [node-contract.js:1](../../../workflow_editor/static/workflow/domain/node-contract.js#L1) | `DATA_CONNECTION_TYPES` [workflow_contract.py:8-16](../../../agent/workflow_contract.py#L8-L16) | ✅ |
| 节点 base/shared/argument 字段划分 | `NODE_BASE_FIELDS` / `NODE_SHARED_FIELDS` / `NODE_ARGUMENT_FIELDS_BY_TYPE` [serialization.js:12-40](../../../workflow_editor/static/workflow/domain/serialization.js#L12-L40) | 同名常量 [workflow_contract.py:44-75](../../../agent/workflow_contract.py#L44-L75) | ✅ 逐字相同 |
| 边界端口 id 规则 | `workflow:${name}` [node-contract.js:40](../../../workflow_editor/static/workflow/domain/node-contract.js#L40) | `f"workflow:{port['name']}"` [workflow_contract.py:136](../../../agent/workflow_contract.py#L136) | ✅（超长名缺陷见 N1） |
| 端口集合（24 类逐节点） | `portsForNode()` [node-contract.js:48-244](../../../workflow_editor/static/workflow/domain/node-contract.js#L48-L244) | `control_ports_for_node` + `data_ports_for_node` [workflow_contract.py:144-228](../../../agent/workflow_contract.py#L144-L228) | ⚠️ 存在 3 处已知不等价，见下 |
| 连接合法性 | `isValidConnection`（类型 + 端口存在性 + 禁自环） | `is_valid_connection`（端口存在性 + 20 余条类型断言 + tool/边界/context 专项校验） | ⚠️ 见 4.12.2 |

### 4.12.2 已知契约不等价点（编辑器可制造出「画布合法、执行被拒」的文档）

| # | 不等价 | 前端 | 后端 | 影响 |
| --- | --- | --- | --- | --- |
| C1 | 中间节点的数据端口类型约束 | 强制 `type` 与端口类型严格相等 | Python `filter_connections` 只查端口存在性（部分场景），`_validate_data_connection` 另有专项断言 | 编辑器更严：外部文件里某些「后端可接受」的连接会被编辑器静默丢弃（P2） |
| C2 | `llm.messages-in` 必须 `list-message` | `portsForNode` 已把该端口类型固定为 `list-message`，天然满足 | 额外断言 `connection_type != 'list-message'` → 拒 | ✅ 实际一致 |
| C3 | `llm.tool_calls` 输出必须 `list-content` | 端口类型固定 `list-content` | 额外断言 | ✅ 实际一致 |
| C4 | tool 节点 `parameters` 必须与 `remote_tools` 声明**逐项相等** | 编辑器用声明覆盖节点（导入归一化 [serialization.js:277](../../../workflow_editor/static/workflow/domain/serialization.js#L277) + 下拉切换 [integrations.js:107](../../../workflow_editor/static/workflow/inspector/integrations.js#L107)） | `parameters != declaration["input_ports"]` → 拒 | ✅ 覆盖方向正确 |
| C5 | 边界节点 `workflowPorts` 必须等于顶层端口 | 导入时总是重算（[serialization.js:172](../../../workflow_editor/static/workflow/domain/serialization.js#L172)） | `node.get("workflowPorts") != expected_ports` → 拒 | ✅ 归一化保证 |
| C6 | **所有必需控制端口必须已连接** | **无任何校验、无任何提示** | `control ports must be connected: node X, ports input:control-in` → 拒 | ❌ 最大的一致性缺口：用户可自由保存未接控制流的节点 |
| C7 | 恰好 1 个 `input` 节点 | 不可新增、不可删除、导入强制 1 个 | `input_count != 1` → 拒 | ✅ |
| C8 | 至少 1 个 `output` 节点 | 导入时自动补建 | 无 `output` → 拒 | ✅ |
| C9 | `remote_async_tool.timeout_ms` 上限 | 无上限校验（HTML `max` 只是 UX，脚本可超） | `TOOL_CLIENT_MAX_ASYNC_TIMEOUT_MS`（默认 3600000）→ 拒 | ⚠️ 编辑器不阻止超限 |
| C10 | `construct_content.append_items` 的 `port_id` 唯一且与 `dataInputPorts` 等集 | Inspector 侧 `syncPorts()` 保证唯一；**导入归一化不保证**（N2） | `_validate_construct_content` → 拒 | ❌ 导入路径可产出非法文档 |
| C11 | 自环连接 | 编辑器禁止 | 后端不查（可能由执行器兜底） | ⚠️ 编辑器更严 |

### 4.12.3 与 `manager_webui` 只读画布的对比（编辑器独有能力）

`manager_webui/static/workflow_canvas.mjs` 把同一份 Workflow JSON 渲染成**静态 SVG**（[workflow_canvas.mjs:138](../../../manager_webui/static/workflow_canvas.mjs#L138)），用于管理页预览与下载。两者差异：

| 维度 | `workflow_canvas.mjs`（:8084 只读） | `workflow_editor`（:8082 编辑器） |
| --- | --- | --- |
| 输出形态 | 服务端拼字符串 → SVG 字符串 / Blob 下载 | 实时 DOM + SVG 交互层 |
| 端口行 | 只渲染**已连接**的端口（`endpointRows`），按契约表排序 | 渲染**全部**端口（`portsForNode`），未连接也显示 |
| 端口 y | `renderY + 52 + row*18`，行距 **18** | `8 + row*28`，行距 **28** |
| 节点尺寸 | `190 × max(86, 64 + rows*18)` | `190 × (45 + max(70, 8+rows*28))` |
| 连接配色 | `CONNECTION_COLORS`；map-content **缺失**（回落 control 灰） | CSS 类；map-content **也未定义**（同样回落默认灰）——**两处同源缺陷** |
| 交互 | 无（`workflow_canvas.mjs` 全文无事件监听） | 拖拽/平移/选择/连线 |
| 节点拖拽 | ❌ | ✅ |
| 端口连线 | ❌ | ✅ |
| 节点增删 | ❌ | ✅ |
| Inspector 编辑 | ❌ | ✅ 17 套模板 |
| 导入/导出 | ❌ | ✅ 文件/文本/URL/剪贴板 |
| 适配归一化 | 读原始 JSON 字段（`node.arguments`），不做类型校验 | 严格 `hasStrictNodeFormat` + `normalizeNode`，失败即整份拒绝 |
| `version` 显示 | 读 `workflow.version \|\| 1` | **从不写出 `version`** → 编辑器产出的文档在管理页恒显示 `VERSION 1` |

**编辑器独有（管理页完全没有）**：12 种 Inspector 结构编辑器、端口拖拽连线与扇出/改接/删除规则、节点拖动与位置钳制、画布平移、元数据对话框（含 Remote Tool 搜索补全）、三种导入通道 + 剪贴板自动导入、beforeunload 未保存拦截。

**管理页独有**：整图导出 SVG（含标题与 `NODES/CONNECTIONS/VERSION` 元信息行，[workflow_canvas.mjs:185-186](../../../manager_webui/static/workflow_canvas.mjs#L185-L186)）、自动排除未连接端口的紧凑布局、坐标归一化（`minX/minY` 偏移 + PADDING=56，[workflow_canvas.mjs:141-147](../../../manager_webui/static/workflow_canvas.mjs#L141-L147)）——编辑器**没有**坐标归一化，也没有整图导出。

## 4.13 扩展槽

### 4.13.1 分层边界与职责（改动前必须遵守）

| 层 | 文件 | 允许 | 禁止 |
| --- | --- | --- | --- |
| **domain** | `domain/node-contract.js`、`connection-rules.js`、`serialization.js` | 纯计算：类型/端口/默认值/ID/连接校验/快照/导入归一化 | **不得触碰 DOM、不得 import 上层**（当前 0 个 DOM 引用，`connection-rules.js` 仅依赖 `node-contract.js`） |
| **editor** | `editor.js` | 画布 DOM 渲染、pointer 交互、瞬态选择态 `editorState`；通过 `elements` 入参访问 DOM | 不得直接改 `state` 的语义字段（除连接增删这一既有例外）；不得 import inspector |
| **inspector** | `inspector/inspector.js`、`structure.js`、`integrations.js` | 面板渲染与事件绑定；通过 `context = {elements, editor, markChanged, renderInspector, renderInterfaceContract}`（[inspector.js:8](../../../workflow_editor/static/workflow/inspector/inspector.js#L8)）反向调用 | 不得自建 DOM 根、不得绕过 `context` 直接调 `editor` 之外的模块 |
| **entry** | `workflow.js`、`workflow_edit.html` | 页面组装、元素句柄、导入导出、元数据对话框、网络请求、`markChanged` 定义 | 不得包含节点/端口/连接规则 |

**`domain → editor → inspector → entry` 单向依赖**是这套代码的核心可维护性约束；`integrations.js` 是唯一「名称与职责不完全匹配」的模块（见 4.8.6）。

### 4.13.2 新增一种节点类型（完整清单，共 11 处）

| # | 文件 | 具体改动 | 必须性 |
| --- | --- | --- | --- |
| 1 | `domain/node-contract.js` | `NODE_TYPES` 加类型名（L3-28） | **必须**（否则 `createNode` 直接返回 null、导入被拒） |
| 2 | `domain/node-contract.js` | `portsForNode()` 加显式分支（**不要依赖末尾兜底**，否则会拿到 LLM 的端口） | **必须** |
| 3 | `domain/node-contract.js` | `createNode()` 加默认值分支（含 `id` 前缀、中文名模板 `${中文名} ${number}`） | **必须**（否则返回 null） |
| 4 | `domain/serialization.js` | `NODE_ARGUMENT_FIELDS_BY_TYPE` 加该类型的字段集合（空集也要显式写） | **必须**（否则 `hasStrictNodeFormat` 对任何 `arguments` 都判 false） |
| 5 | `domain/serialization.js` | `normalizeNode()` 加归一化分支（默认值、范围钳制、非法值 `return null`） | **必须** |
| 6 | `static/workflow_edit.html` | 节点库加 `<button class="library-item" data-add-node="类型名">`（含 `.node-symbol` 与文案） | **必须**（否则无法从 UI 新增） |
| 7 | `static/workflow_edit.html` | 新增 `<template id="类型名InspectorTemplate">`，首个子元素必须是 `<div data-interface-contract>` | **必须**（否则 `template.content` 为 null 抛错） |
| 8 | `static/workflow/editor.js` | `symbols` 映射加节点卡符号（L208），缺省回落 `'L'` | 建议 |
| 9 | `static/css/workflow/layout.css` + `canvas.css` | 加 `.<类型名>-symbol { background:… }` 与 `.flow-node.<类型名> { border-top-color:… }` | 建议（否则用默认色） |
| 10 | `agent/workflow_contract.py` | `SUPPORTED_NODE_TYPES` + `NODE_ARGUMENT_FIELDS_BY_TYPE` 同步；`data_ports_for_node` / `control_ports_for_node` 加分支 | **必须**（否则 `validate_workflow` 直接拒） |
| 11 | `agent/workflow_validator.py` | `_validate_node` 加该类型的专项校验；若涉及数据流还需在 `_validate_data_connection` 加断言 | **必须**（否则非法配置会漏到执行期） |

**模板与命名约定**：新增的 Inspector 模板中，通用字段一律用 `data-field="<arguments 键名>"`，`structure.js` / `integrations.js` 只处理「需要联动端口或复杂行编辑」的字段。

### 4.13.3 新增一种端口数据类型（完整清单，共 7 处）

| # | 文件 | 改动 | 必须性 |
| --- | --- | --- | --- |
| 1 | `domain/node-contract.js` | `DATA_TYPES` 加类型（L1） | **必须** |
| 2 | `domain/connection-rules.js` | `isValidConnection` 的类型白名单数组加类型（L13）——**这是硬编码数组，与 `DATA_TYPES` 不同源，容易漏改** | **必须** |
| 3 | `static/css/workflow/canvas.css` | `.connection-path.<类型>` 描边；`.node-port[data-port-type="<类型>"]` 背景；`.canvas-legend` 加点 | 建议 |
| 4 | `static/css/workflow/inspector.css` | `.port-swatch.<类型>` | 建议 |
| 5 | `static/workflow_edit.html` | 元数据端口 `<select data-metadata-port-type>` 加 `<option>`（[L260](../../../workflow_editor/static/workflow_edit.html#L260)）；各 Inspector 的端口类型下拉（context/session `value_type`、`deserialize_json` `data-output-type`） | 视需要 |
| 6 | `agent/workflow_contract.py` | `DATA_CONNECTION_TYPES` 加类型 | **必须** |
| 7 | `agent/workflow_validator.py` | 所有 `DATA_CONNECTION_TYPES` 引用自动生效；若该类型有专属约束，需在 `_validate_data_connection` 补断言 | 视需要 |

> 若新增类型是「列表型」，还需处理 `listTypeForItem()`（[node-contract.js:44-46](../../../workflow_editor/static/workflow/domain/node-contract.js#L44-L46)）与 `item_type` 白名单（`['content','message','event']` 在 [structure.js](../../../workflow_editor/static/workflow/inspector/structure.js) 与 [serialization.js:231](../../../workflow_editor/static/workflow/domain/serialization.js#L231) 多处硬编码）。

### 4.13.4 新增一个快捷键（当前基础设施为 0）

现状：**没有任何键盘绑定基础设施**（无 `keydown` 委托、无快捷键表、无修饰键判定）。

| # | 步骤 | 落点建议 |
| --- | --- | --- |
| 1 | 新增 `document.addEventListener('keydown', ...)`，位置应在 `workflow.js` 入口层（与 `paste` 同级，[workflow.js:556](../../../workflow_editor/static/workflow.js#L556)） | entry |
| 2 | 必须先做焦点守卫：`event.target.closest('input, textarea, select, [contenteditable="true"]')` 时 return（参考 [workflow.js:557](../../../workflow_editor/static/workflow.js#L557)） | entry |
| 3 | 语义动作要落到 domain 纯函数（如节点删除走 `deleteNode()`），不要写在事件回调里 | domain |
| 4 | 动作完成后依次调用 `markChanged()` + `editor.renderNodes()` + 必要时的 `renderInspector()`（参考 `commitStructureChange` 的四步，[structure.js:17-22](../../../workflow_editor/static/workflow/inspector/structure.js#L17-L22)） | entry/inspector |
| 5 | 若新增「撤销/重做」类全局历史，建议在 domain 层新增 `history.js`（快照栈 = `workflowSnapshot()` 的 `structuredClone`），避免污染 `serialization.js` | domain（新文件） |

### 4.13.5 新增一个 Inspector 字段

| 情形 | 唯一改动 |
| --- | --- |
| 普通文本/数字/下拉，写入 `node[field]` | 在对应 `<template id="…InspectorTemplate">` 加 `<label>…<input data-field="字段名"></label>`；**无需改 JS**（通用绑定覆盖，[inspector.js:26-34](../../../workflow_editor/static/workflow/inspector/inspector.js#L26-L34)） |
| 需要数值钳制 | 在 `structure.js` 加 `change` 绑定（参考 `bindHistory` 的 limit，[structure.js:159-164](../../../workflow_editor/static/workflow/inspector/structure.js#L159-L164)） |
| 需要影响端口 | 在 `structure.js` 加分支，并在改动后调用 `commitStructureChange()`（内含 `reconcileConnections`） |
| 需要外部资源下拉 | 在 `integrations.js` 的 `prepare()` 加渲染、`bind()` 加事件；同时**必须**在 `domain/serialization.js` 的 `NODE_ARGUMENT_FIELDS_BY_TYPE` 注册字段名，否则导出的 `arguments` 会被 `hasStrictNodeFormat` 拒 |
| 新增节点专属的端口类型下拉选项 | 同时改 HTML `<option>` 与 `agent/workflow_contract.py` 的白名单 |

**关键提醒**：任何新增的 `arguments` 字段**必须**同步进 `NODE_ARGUMENT_FIELDS_BY_TYPE`（前端 [serialization.js:14-39](../../../workflow_editor/static/workflow/domain/serialization.js#L14-L39) + 后端 [workflow_contract.py:51-75](../../../agent/workflow_contract.py#L51-L75)），三处少一处就会导致「编辑器能编辑但导出被拒」或「导出被后端拒」的不一致。

### 4.13.6 修改连接规则时的必改点

| 想改的语义 | 必改位置 |
| --- | --- |
| 端口类型 / multiple 标记 | `portsForNode()` + `agent/workflow_contract.py` 对应函数 |
| 兼容性判定（能否连） | `compatiblePort()` [editor.js:44](../../../workflow_editor/static/workflow/editor.js#L44-L52) **与** `isValidConnection()` [connection-rules.js:11](../../../workflow_editor/static/workflow/domain/connection-rules.js#L11-L21)（**两处都要改**，前者决定拖拽手感、后者决定数据合法性） |
| 单连接 / 扇出 | `portsForNode()` 的 `multiple` + `finishConnectionDrag` 的占位清理 [editor.js:71-77](../../../workflow_editor/static/workflow/editor.js#L71-L77) |
| 删除连接的触发方式 | `finishConnectionDrag` 末尾分支 [editor.js:101-106](../../../workflow_editor/static/workflow/editor.js#L101-L106)；若要加「点击连线删除」，必须先把 `.connection-layer` 的 `pointer-events:none`（[canvas.css:5](../../../workflow_editor/static/css/workflow/canvas.css#L5)）改为按需开启，并给 `<path>` 加 `data-connection-id`（当前渲染时未写入该 dataset，[editor.js:266-274](../../../workflow_editor/static/workflow/editor.js#L266-L274)） |
| 失效连接的清理时机 | `reconcileConnections()` 的调用点（当前 8 处） |

## 4.14 已知问题与风险登记

| 级别 | 问题 | 证据 / 出处 |
| --- | --- | --- |
| **P1（安全）** | 服务**无任何鉴权**，宿主全接口绑定 `8082:8082`；同网段任意客户端可读写其暴露的模型列表与 Tool 目录（编辑器 API 本身是只读的，但服务可与 redis/mongo 通信） | [main.py:54-78](../../../workflow_editor/main.py#L54-L78)、[docker-compose.yml:152](../../../docker-compose.yml#L152)、[架构问题汇总 A-02](../../审查日志/架构问题汇总.md) |
| **P1（契约）** | 边界端口 id/name 在名称 >80 字符时不符（N1） | [node-contract.js:40](../../../workflow_editor/static/workflow/domain/node-contract.js#L40) |
| **P1（契约）** | 导入归一化可产出重复/空 `append_items`（N2） | [serialization.js:193-200](../../../workflow_editor/static/workflow/domain/serialization.js#L193-L200) |
| **P2** | 编辑器比后端严格（R15/C1）：外部文件中的部分数据连接被静默丢弃 | [connection-rules.js:3-9](../../../workflow_editor/static/workflow/domain/connection-rules.js#L3-L9) |
| **P2** | 元数据空名/空白名未拦截（N3） | [workflow.js:434-437](../../../workflow_editor/static/workflow.js#L434-L437) |
| **P2** | `initial_value_count = 0` 显示为空 + 数字字段瞬态字符串（D5/D6） | [inspector.js:27-33](../../../workflow_editor/static/workflow/inspector/inspector.js#L27-L33) |
| **P2** | 拖动节点不标记「未保存」（D1）——数据丢失风险 | [editor.js:179-201](../../../workflow_editor/static/workflow/editor.js#L179-L201) |
| **P2** | 控制端口未连接的画布状态**无任何提示**，执行期才被拒（C6） | 编辑器全文无 `control ports` 校验 |
| **P2** | `remote_sync_tool` / `remote_async_tool` 的 `timeout_ms` 无上限校验（C9） | [integrations.js:115-117](../../../workflow_editor/static/workflow/inspector/integrations.js#L115-L117) |
| **P3** | 导入静默过滤无计数回显（N4） | [serialization.js:377](../../../workflow_editor/static/workflow/domain/serialization.js#L377) |
| **P3** | `connection-rules.js` 的类型白名单与 `node-contract.js` 的 `DATA_TYPES` 不同源（扩展点时易漏改） | [connection-rules.js:13](../../../workflow_editor/static/workflow/domain/connection-rules.js#L13) vs [node-contract.js:1](../../../workflow_editor/static/workflow/domain/node-contract.js#L1) |
| **P3** | `map-content` 连线无专属样式（与 control 视觉同色），图例也缺该条目 | [canvas.css:6-13](../../../workflow_editor/static/css/workflow/canvas.css#L6-L13)、[workflow_edit.html:183](../../../workflow_editor/static/workflow_edit.html#L183) |
| **P3** | `#resourceState` 一槽两用（资源计数 + 表单错误） | [workflow.js:130-138](../../../workflow_editor/static/workflow.js#L130-L138)、[workflow.js:435-457](../../../workflow_editor/static/workflow.js#L435-L457) |
| **P3** | `api.js` 中 11 个函数指向不存在的 WebUI 路由（死代码） | [api.js:16-95](../../../workflow_editor/static/api.js#L16-L95) |
| **P3** | `portsForNode()` 的 `llm` 是**兜底分支**，新增类型漏写分支会静默获得 LLM 端口 | [node-contract.js:235-243](../../../workflow_editor/static/workflow/domain/node-contract.js#L235-L243) |
| **P4** | `?v=N` 在 `Cache-Control: no-store` 下冗余；子 CSS 无版本串 | [main.py:58](../../../workflow_editor/main.py#L58)、[workflow.css:1-3](../../../workflow_editor/static/css/workflow.css#L1-L3) |
| **P4** | `.saved` 类只被 `remove`、从未 `add`；`.draft-badge` 零引用 | [workflow.js:54](../../../workflow_editor/static/workflow.js#L54)、[layout.css:74](../../../workflow_editor/static/css/workflow/layout.css#L74) |
| **P4** | 启动时剪贴板自动导入是**静默**的，且会置 `hasUnsavedChanges` | [workflow.js:578-585](../../../workflow_editor/static/workflow.js#L578-L585) |
| **P4** | URL `?workflow=` 承载整份 JSON，大文档可能超 URL 长度限制 | [workflow.js:543](../../../workflow_editor/static/workflow.js#L543) |
| **P4** | 导出不含 `version`，管理页恒显示 `VERSION 1` | [manager_webui/static/workflow_canvas.mjs:186](../../../manager_webui/static/workflow_canvas.mjs#L186) |
| **P4** | 溢出选位（第 13 个节点起）不做占用校验，可能与已有节点重叠 | [node-contract.js:255-256](../../../workflow_editor/static/workflow/domain/node-contract.js#L255-L256) |
| **P4** | Inspector 每次 `renderInspector()` 全量重建 DOM，输入焦点会丢（结构编辑处已用 `render()` 局部重绘规避） | [inspector.js:19](../../../workflow_editor/static/workflow/inspector/inspector.js#L19) |

---

### 统计摘要

| 指标 | 数值 |
| --- | --- |
| 节点类型总数 | **24**（前端 `NODE_TYPES` 与后端 `SUPPORTED_NODE_TYPES` 逐字一致） |
| 节点库可点按钮 | 22 个 `[data-add-node]` + 动态 `[data-add-workflow-node]` |
| 数据端口类型 | **7**（content / message / event / map-content / list-content / list-message / list-event）+ control |
| 连接类型 | **8**（上 7 种 + control） |
| Inspector 模板 | **17** 个 `*InspectorTemplate`（+ 5 个元数据/契约模板） |
| 键盘绑定 | **1**（`Ctrl/Cmd+V` 粘贴导入）；其余全部不存在 |
| 后端路由 | **4**（1 健康检查 + 3 只读资源）+ 1 静态挂载 |
| 持久化 | **无**（0 个写路由、0 个 localStorage） |
| 撤销/重做 | **无** |
| 缩放 / 框选 / 多选 / 右键菜单 / 自动布局 | **全部无** |
