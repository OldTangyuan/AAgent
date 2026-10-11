# 23 Workflow Session 节点与管理页设计

> 类型:设计文档。
> 性质:现行文档。
> 归属:`agent/` + `manager_webui/`。
> 适用版本:平台 `4.0.0+`。

## 1. 目标与边界

Session 是跨 Workflow、跨执行实例共享的带类型可变值。它不绑定 `invocation_id`，不设置 TTL，也不在 `run_workflow_map` 的 `finally` 中清理；只有管理页主动删除时才消失。重启 Agent / Manager 后仍应可读。它与 [Workflow Context](21-Workflow%20Context节点设计.md) 并存，不改变现有 Context 的执行实例隔离、TTL 和自动清理语义。

首期提供三种 Workflow 节点：创建、读取、覆盖；另在 `manager_webui` 提供 Session 列表、查看、创建、覆盖和删除。全局指同一部署内的 Workflow（包括父子 Workflow）只要拿到 Session ID 就能读写，不指跨部署共享或聊天会话隔离。暂不提供按名称查找、追加/合并、自动过期或历史版本。

## 2. 身份与节点契约

- 节点类型：`session_create`、`session_read`、`session_write`，节点面板参数均为 `arguments.value_type`；其可选类型与 Context 对齐：`content`、`message`、`event`、`list-content`、`list-message`、`list-event`。
- `session_create`：输入 `control-in`、`initial-value: value_type`；输出 `control-out`、`session-id: content`。值必填，后端生成 `ses_<uuid4 hex>`，不由调用方指定 ID。
- `session_read`：输入 `control-in`、`session-id: content`；输出 `control-out`、`value-out: value_type`。
- `session_write`：输入 `control-in`、`session-id: content`、`value-in: value_type`；输出 `control-out`、`session-id: content`、`value-out: value_type`。只允许覆盖已有 Session，不隐式创建，不允许改变其 `value_type`。
- 数据端口和控制端口的连接规则、值必填规则、节点失败即中止 Workflow 的规则沿用 Context；ID 仍是普通 `content`，可经 Workflow 输入输出端口在调用间传递。ID 缺失、记录不存在、类型不符或值无效均报错，不静默返回空值。

读写仅以 ID 定位，不检查创建者或 Workflow 名称。Session ID 本身是访问凭据；持有者能覆盖值。管理页删除后旧 ID 不再有效，再创建会得到新 ID。管理页应方便复制 ID，供 Workflow 的 `content` 输入使用；首期不允许节点通过名称检索已有 Session。

## 3. 存储与并发

使用现有 MongoDB 数据库中的独立 `sessions` 集合（可用 `MONGO_SESSION_COLLECTION` 配置）；不用 `workflow-context:*` Redis key。当前 Redis 虽启用了 AOF 和卷挂载，但 Context 的 TTL 与清理逻辑不适合作为永久存储边界。Session 集合**不建立 TTL 索引**，文档字段：

| 字段 | 含义 |
|------|------|
| `_id` | 生成的 `ses_...` 字符串，集合主键 |
| `value_type` | 创建时确定的静态数据类型 |
| `value` | 原生 BSON 可表示的 JSON 值（字符串、对象或数组） |
| `created_at` / `updated_at` | UTC 时间 |

建议 Agent 使用独立 `workflow_session_repository.py` 封装 Mongo 连接和 `create/read/write`；Manager 使用同一集合的管理 API。两侧遵守相同的类型与值校验规则，不在节点处理器里直写数据库。`value` 的 JSON UTF-8 序列化大小限制沿用 Context 默认 1 MiB（按已编码字节检查，而非字符数）；超过限制拒绝，MongoDB 16 MiB 文档上限不能替代业务限制。读出值也校验类型，损坏的记录直接报错。

覆盖使用 `updated_at` 条件更新并将时间版本至少递增 1 毫秒。节点写入遇到并发覆盖时重读版本并重试，因此节点间最后成功提交者生效；读-改-写不是原子操作，页面编辑期间节点也可能写入。管理页保存带上读取时的 `updated_at` 做条件更新，冲突时返回 409 并提示刷新，不自动覆盖编辑框内容。删除后节点的读写返回不存在；并发删除/覆盖以数据库提交顺序为准。

注意现有 `workflow_context_repository.py` 虽列出 `event` / `list-event`，其 `_valid_value` 目前并未处理这两类。实施时要为 Session 定义完整的六类型校验，并补测事件对象结构；如要复用校验器，须先解决这一差异，不能直接把当前 `_valid_value` 当作六类型校验器。Session 的值协议以现有 Workflow event 数据结构为准，管理页输入也按同一规则校验。

## 4. 管理页

新增 `/sessions.html` 页面及 `/api/sessions` API，沿用 manager_webui 当前的静态 HTML + JS + CSS、`api.js` 请求封装与顶部导航。导航入口同步加入现有 `workflows.html`、`events.html`、`document.html`、`model.html`。

页面左侧为可搜索的 Session 列表（显示 ID 缩写、类型、更新时间；按更新时间倒序，服务端分页/游标，避免永久数据无限加载），右侧为选中 Session 的完整 ID、创建/更新时间、类型与值。值按类型展示：`content` 用文本编辑，其他类型用 JSON 格式化预览和 JSON 编辑区；所有值在界面以文本呈现，不作为 HTML 注入。支持复制 ID、手动刷新、创建、覆盖保存和删除确认；空列表、加载中、请求失败、校验失败及并发冲突分别提示。创建表单先选类型再输入初始值；覆盖时类型只读。操作成功刷新列表与详情；列表预览不返回大 `value`，仅详情返回完整值。页面不自动轮询，避免把用户正在编辑的内容覆盖。

API 草案（响应时间统一用 ISO 8601）：

| 方法与路径 | 行为 |
|-----------|------|
| `GET /api/sessions?limit=50&cursor=...&q=...` | 返回分页元数据列表与 `next_cursor`；`q` 按 ID 前缀过滤 |
| `GET /api/sessions/{session_id}` | 返回完整值与元数据；无记录 404 |
| `POST /api/sessions` | 接收 `{value_type, value}`，生成 ID；201 |
| `PUT /api/sessions/{session_id}` | 接收 `{value_type, value, updated_at}`，按版本条件完整覆盖；冲突 409，不存在 404 |
| `DELETE /api/sessions/{session_id}` | 永久删除；不存在 404 |

`q` 限制长度并按字面前缀处理，避免用户输入参与正则拼接；列表采用稳定排序 `(updated_at desc, _id desc)`，游标包含两者以避免同一时间记录漏项。请求体在 `main.py` 的 guard 中单独限制，并在 API 层按字节再次验证值大小；无效类型/值返回 400，数据库不可用返回 503。沿用当前 manager_webui 的访问边界：项目目前没有单独的 Session 授权机制，因此部署时管理端口必须仅对可信用户开放；不把随机 ID 当成对外暴露接口的认证手段。

## 5. 实施位置

1. Agent：新增 Session repository 及测试；在 `workflow_nodes.py` 接入三节点，确保新 ID 不加入 `_workflow_context_ids`；在 `workflow_contract.py`、`workflow_validator.py` 加入节点类型、参数、端口和连线类型检查。
2. Manager：在 `workflows.py` 的保存校验中加入三种节点及端口类型；在 `main.py` 注入 Mongo Session 集合、请求体限制和 Session router；新增对应 API 测试。确保上传的 Workflow 不会因缺少白名单而丢弃节点/连线。
3. Editor：在 `workflow_editor/static/workflow/` 的节点契约、序列化、节点工具栏、Inspector、符号及样式加入 Session 三节点；切换 `value_type` 时仅清理不兼容的数据连接，保留控制连接。
4. 页面：新增 `manager_webui/static/sessions.html`、`sessions.js`、`css/sessions.css`，扩展 `api.js` 和四个现有页面的导航；JS 修改后递增对应 HTML 中带 `?v=` 的资源版本号。

## 6. 验收场景

- Workflow A 创建并输出 Session ID，执行结束后 Workflow B（或子 Workflow）用该 ID 读取与覆盖，重启 Agent/Manager 后仍可读取；Context 仍在原调用结束时删除。
- 页面创建、列表分页/搜索、查看大值、复制 ID、保存与删除均可用；页面保存后节点读到新值，节点写入后页面刷新看到新值。
- ID 不存在、类型不匹配、非法结构、超过 1 MiB、Mongo 不可用各有明确错误；页面编辑期间节点写入时页面保存返回 409 而不是覆盖节点新值。
- 六种类型分别有创建、读取、覆盖的测试；编辑器导出 -> Manager 上传 -> Agent 校验/执行三端契约一致，类型切换保留控制连接。

## 7. 待确认

本方案默认“全局”意味着同一部署内任何拿到 ID 的 Workflow 都能读写，没有单用户以外的权限隔离；若将来暴露给不可信调用者，需要在实现前补所有者/授权规则。永久指无应用层过期或结束清理，不代替 MongoDB 备份；手动删除和数据目录丢失仍会使 Session 消失。

## 8. 实现与验证

管理入口为 `/sessions.html`；Agent 与 Manager 使用同一个 MongoDB 数据库和 `MONGO_SESSION_COLLECTION`（默认 `sessions`），此集合无 TTL 索引。编辑器提供 Session 三节点，Manager 提供分页、搜索、详情、创建、覆盖和删除。对应测试位于 Agent 的 Session repository 测试和 Manager 的 Session API、Workflow 连接测试中。当前仅完成语法和编辑器静态诊断；运行时测试及浏览器交互仍需在依赖和服务可用的环境执行。