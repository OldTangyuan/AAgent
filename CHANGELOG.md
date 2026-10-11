# 更新日志

AAgent 平台的发布历史。格式遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/)，版本号为 `MAJOR.MINOR.PATCH`（`MAJOR`=架构/引擎代数，`MINOR`=功能代数，`PATCH`=修 bug/改文档代数），**不是 SemVer**；协议版本为 `MAJOR.MINOR`。编号原理见 [docs/版本控制.md](docs/版本控制.md)，落地规则见 [docs/版本与归属规范.md](docs/版本与归属规范.md)。

每个已发布版本必须写出 `协议版本` 段（不变也写明），否则无法回答"哪个平台版本能跟哪个服务版本通信"。

## [Unreleased]

## [4.0.0] - 2026-10-11

首个纳入版本体系的版本，同时把版本口径从 SemVer 换成本仓库自己的三代编号（`MAJOR`=引擎代数 / `MINOR`=功能代数 / `PATCH`=修补代数）。此前的 154 个提交（2026-07-30 ~ 2026-10-11）不逐个回填编号，其内容归纳在下面的「主线回填」小节。

### 协议版本

- `event` 1.0 —— 主队列 / 回调队列的事件信封格式
- `workflow` 1.0 —— Workflow JSON 契约（顶层字段、节点、端口）

### 新增

- 三层版本体系：`version.json`（权威清单）、8 个服务目录的 `version.json`（服务级副本：`platform` + `protocol`，随镜像进容器）、`scripts/check_version.py`（一致性校验）
- `docs/版本控制.md` —— 三代编号（引擎/功能/修补）的原理与字段定义
- `docs/版本与归属规范.md` —— 版本号与文档归属的唯一可执行规则来源
- 文档元信息头规范：`类型` / `性质` / `归属` / `适用版本`（协议类文档另加 `协议版本`）
- `docs/README.md` 重写为全库文档总索引

### 变更

- 版本号口径由 SemVer 改为三代编号：`MAJOR`=引擎代数（当前第 4 代，分 task 同步 FIFO 调度）、`MINOR`=功能代数、`PATCH`=修补代数；协议保持 `MAJOR.MINOR`
- 文档归属规则明确化：`归属` 定义为「该文档描述的代码责任域」，用于契约变更时反查需要同步的文档
- `CHANGELOG.md` 建立，主线历史以归纳形式回填

---

## 主线回填（2026-07-30 ~ 2026-10-11，不逐个提交编号）

以下按阶段归纳这 154 个提交的主线变化。**每段给出提交区间**（`起始短哈希 → 结束短哈希`），可用 `git log --oneline 起始..结束` 展开细节；也可用 `git log --oneline v2..v3` 等旧锚点（见末尾「历史锚点」）。它不构成逐版本的发布记录，只回答"这个项目是怎么走到 4.0.0 的"。

### 1. 初始化与事件驱动转向 — `217e83d` → `9f3238c`（2026-07-30 ~ 08-01）

- 项目初始化，agent 业务代码与 WebUI 上线。
- Agent 取消 QQ 单一入口，改为**完全事件驱动 + history callback**。
- WebUI 固定视口高度布局、时间轴内部滚动、"回到正在执行" 控件、chat UI。
- 后端由 Go 迁移为 **Python FastAPI**。

### 2. WebUI、终端与设置 — `3f79ac1` → `6805fd6`（2026-08-02 ~ 08-06）

- 前端事件流重构与 CSS 按职责拆分；终端页落地。
- 设置页与 System Prompt 持久化（`prompt/system.txt` → `settings.json` → Redis 单键 JSON）。
- 文档页：MongoDB `documents` 集合 + CRUD + 上传/下载/批量导入 + 钉住。
- tool 动态注册。

### 3. 外部工具与路线转向 — `d48f689` → `d40e762`（2026-08-09 ~ 08-19）

- bilibili 解析工具。
- 放弃"中央 agent + subagent/RPC"路线，确立 **workflow + agent 组织 + 文档系统** 方向。
- Workflow 画布、解析器与执行器落地；动态 `tool_calls` 编译。
- 新增 `list-content`、构造 content、foreach 复杂控制流、Output 节点、事件 source。
- `webui_py` 后端拆分。

### 4. Workflow 管理与编辑器独立 — `84ce33a` → `3361a44`（2026-08-20 ~ 09-14）

- Workflow 管理页；Workflow 调用 Workflow。
- 移除旧的 agent setting 业务逻辑与选择 Workflow 的旧字段。
- `workflow_editor` 拆为独立服务，Workflow 以文本 JSON 交换。
- 编辑器前端目录重构（domain / editor / inspector 分层）；管理页改为只读 + 上传写入。

### 5. 工具平台拆分 — `14ff0a7` → `10214ce`（2026-09-15 ~ 09-18）

- 新增 `tool_server` 与 `tool_provider`，工具执行从 agent 内拆出。
- 区分本地 / 远程工具，**删除独立的 `tool_call` 执行节点**。
- `remote_tool` 改为 Workflow 顶层元数据约定；Tool 输出 Schema 严格化。
- 删除 subagent 相关业务；事件绑定落库；`manager_webui` 独立成服务。

### 6. Workflow 数据能力 — `776b7c7` → `5886074`（2026-09-19 ~ 09-28）

- `tool_server` 任务与日志落 MongoDB 持久化。
- 引入 Context、history 召回、list 追加、event 拆分、JSON 反序列化、message 构造/映射节点。
- 画布预览与 SVG 导出；事件契约可视化。

### 7. 模型、Session 与修复 — `6823447` → `e28e83d`（2026-10-04 ~ 10-11）

- LLM 节点改为按 MongoDB 模型配置调用（`chat_with_model`，取代 `DEEPSEEK_*` 直连）。
- 引入 Session 节点与管理页双模式编辑（JSON / 可视化）。
- `list-event` 命名修正；新增 `map-content` 数据类型与 `map_content_get` / `construct_map_content` 节点。
- 修复 provider 输出不符合 output Schema 时打断 WebSocket 连接的问题。

### 同期移除

- 旧事件驱动链（`active` / `tool_excute` / `rpc_apply` / `rpc_review` / `tool_return`）。
- 设置与 System Prompt 链路（`GET/POST /api/settings`、`aagent:settings`、`agent/settings.json`）。
- subagent / RPC 相关业务；独立 `tool_call` 执行节点。

---

## 历史锚点

版本体系（`v4.0.0`）之前存在过几次"自封版本"，**全部保留以便追溯**，不做编号回填、不改写任何历史：

| 锚点 | 形态 | 指向提交 | 日期 | 说明 |
|---|---|---|---|---|
| `chore: release v1.0.0` | 仅提交信息 | `d246dc6` | 2026-08-01 | 信息里写了 release，但**没打标签**，不构成版本 |
| `stable v1` | 仅提交信息 | `f0ef10c` | 2026-08-01 | 同上 |
| `v2` | **附注标签**（tag 对象 `60ab1a7`） | `f39e242` | 2026-08-02 | 标签 message 为 `stable v2` |
| `v3` | **轻量标签**（无 tag 对象） | `bcce929` | 2026-08-22 | 标签名 `v3`，无 message |

这些锚点**不表示任何兼容性承诺**，只是"当时停在这里"的痕迹。规则与完整登记见 [docs/版本与归属规范.md §6.1](docs/版本与归属规范.md)。
