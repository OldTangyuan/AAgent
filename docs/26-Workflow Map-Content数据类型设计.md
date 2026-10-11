# 26 Workflow `map-content` 数据类型设计

> 类型:设计文档。
> 性质:现行文档。
> 归属:跨服务（`agent/` + `workflow_editor/` + `manager_webui/`）。
> 适用版本:平台 `4.0.0+`。

## 1. 目标与边界

现有 `content_map` 节点把面板中配置的 `mappings: [{key, value}]` 用作静态查表：输入 `content-in`，输出匹配的 `content-out`。这份映射不能作为数据传给其他节点，也不能保存到 Context / Session 或作为 Workflow 的输入输出。

本方案新增唯一一种 Map 数据类型：`map-content`。`map` 只表示类型族，不是合法的端口类型或 `value_type`；未来若支持其他值类型，另行设计，不预先开放 `map-message` 等名称。Map 的键是字符串，值的 Workflow 数据类型只能是 `content`（运行时对应 Python `str`），因此整体运行时表示为 `dict[str, str]`，例如 `{"draft":"草稿","done":"完成"}`。它不是承载 JSON 字符串的 `content`，也不是 `list-content`。

将现有 `content_map` 更名为 `construct_map_content`，只用配置项构造 Map；运行时按键取值由新的 `map_content_get` 节点负责。旧 `content_map` 类型及其 `content-in` / `content-out` 端口不保留，已有 Workflow 需重建相关节点和连线，不提供迁移或兼容层。首期不做嵌套 Map、动态写入/删除键、Map 遍历、默认值或隐式类型转换。

## 2. 数据契约

| 项目 | 规则 |
|------|------|
| 类型标识 | 仅 `map-content`；裸 `map` 非法 |
| 运行时值 | `dict[str, str]`；键为字符串，值为 `content`（Python `str`）；允许空字典 |
| 键 | 非空字符串，大小写敏感；重复键在构造配置中拒绝，不允许静默覆盖 |
| 值 | 只能是 `content`（Python `str`），允许空字符串；数字、布尔、`null`、对象和数组不能隐式转换为 `content` |
| 连线 | 仅可连接同类型端口；不自动拆分成 `content` |
| 序列化 | JSON 对象；边界及存储反序列化后恢复为字典，而非 JSON 文本 |

`content` 中即使装着 `{"a":"b"}`，也不能直接连到 `map-content` 端口。必须经过显式解析。Map 是值，不是共享引用：节点向外传播后，消费者不能通过原地修改影响另一条连接上的值；当前设计没有 Map 原地修改节点。

## 3. 节点设计

### 3.1 `construct_map_content`：构造 Map

把原 `content_map` 更名为 `construct_map_content`，沿用面板的 `arguments.mappings` 配置。节点没有数据输入，只有一个 `map-content` 数据输出；控制端口按现有节点约定保留。

```json
{
  "id": "construct-map-content-1",
  "type": "construct_map_content",
  "name": "构造 Map-Content",
  "x": 320,
  "y": 200,
  "arguments": {
    "mappings": [
      { "key": "draft", "value": "草稿" },
      { "key": "done", "value": "完成" }
    ]
  }
}
```

| 方向 | 端口 | 类型 | 行为 |
|------|------|------|------|
| 输入 | `control-in` | `control` | 触发节点 |
| 输出 | `map-out` | `map-content` | 每次执行都输出本节点配置的整张 Map |
| 输出 | `control-out` | `control` | 构造成功后继续 |

保留 `mappings` 非空、键非空且唯一、值为 `content`（Python `str`）的配置校验。执行时将配置转为独立的字典，传播 `map-out` 后再进入 `control-out`；不读取键，也不输出查表结果。

### 3.2 `map_content_get`：按键映射

新增 `map_content_get` 节点，对运行时传入的 Map 按键取值：

| 方向 | 端口 | 类型 | 行为 |
|------|------|------|------|
| 输入 | `control-in` | `control` | 触发查找 |
| 输入 | `map-in` | `map-content` | 必填 |
| 输入 | `key-in` | `content` | 必填 |
| 输出 | `content-out` | `content` | 命中的字符串值 |
| 输出 | `control-out` | `control` | 命中后继续 |

该节点不需要面板参数。执行时验证 Map 与键的类型，缺键直接失败，不返回空字符串或 `None`；成功时传播 `content-out` 后进入 `control-out`。它是构造节点之外唯一承担查表职责的节点。

## 4. 进入和离开数据边界

1. **Workflow 输入/输出及子 Workflow：** 元数据端口可声明 `map-content`；调用节点据此生成同类型端口。传递实际字典，不传 JSON 字符串。输入/输出端口和依赖快照的类型校验需同步。
2. **反序列化 JSON：** `deserialize_json.outputs[*].type` 可选 `map-content`。字段必须是 JSON 对象，且每个键为非空字符串、值为 JSON 字符串（转换后是 `content` / Python `str`）；`null` 等其他值直接报错。不把对象先重新序列化为 `content`。
3. **Context / Session：** `value_type` 可选 `map-content`；创建、读取、覆盖均验证 `dict[str, str]`，使用现有 JSON 存储机制和各自生命周期/大小限制。`context-id`、`session-id` 仍是 `content`。
4. **远程 Tool：** 若端口元数据声明 `map-content`，同步 Tool 返回必须经类型校验后传为字典，不能把 JSON 对象当字符串直通；不改变现有 Tool Server 的 Schema 语义。
5. **不提供自动转换：** 本期不新增 Map 转 JSON、Map 转条目列表或从 `content` 隐式解析 Map。需要外部 JSON 输入时使用 `deserialize_json` 明确取字段；直接解析根对象可留待后续专门节点讨论。

## 5. 改动位置与实施顺序

| 层 | 必须同步的事项 |
|----|----------------|
| Agent 契约 | 在数据类型集合加入 `map-content`；用 `construct_map_content` 替换 `content_map`，并为其 `map-out` 和 `map_content_get` 声明数据/控制端口及严格连线校验；继续拒绝裸 `map` |
| Agent 校验和执行 | 校验节点参数与动态端口；构造独立 Map，按运行时 Map 查键；JSON 反序列化加入 `map-content` 转换 |
| Context / Session 仓储 | 类型白名单和存储值校验加入 Map；对现有未覆盖的类型校验缺口单独核对，不把旧行为当 Map 的先例 |
| 管理页 | Workflow 元数据、节点类型、连线规则、上传/导出/依赖快照均识别新类型；上传不能静默丢连接 |
| 编辑器 | 端口类型、连线颜色/标签、`construct_map_content` 的配置面板与单一数据输出、`map_content_get` 节点、导入导出、元数据/Context/Session/JSON 类型下拉同步 |

建议依次实现契约与执行器、仓储和 JSON 转换、管理页保存、编辑器，最后跑跨层用例。不要只改通用类型集合：现有 `content_map` 的输出端口与连接类型在 Agent 和管理页都有按节点类型写死的判断，替换节点类型时都要同步移除。

## 6. 验收场景

- `construct_map_content` 配置 `draft -> 草稿`，只输出 `{"draft":"草稿"}`；不提供 `content-in` 或 `content-out` 数据端口。
- 将其 `map-out` 接到 `map_content_get.map-in`，`key-in` 输入 `draft` 后从 `content-out` 得到 `草稿`；未知键使查表节点失败且不执行后继控制节点。
- JSON 字段 `{"labels":{"draft":"草稿"}}` 可声明 `labels: map-content`，并原样通过 Workflow 边界、Context 和 Session 读写；值为数字或 `null` 时拒绝。
- `map`、`map-message`、`content` 到 `map-content`、`map-content` 到 `content` 的声明/连线均拒绝；空 Map 可经 JSON 解析和边界传递，但无法由当前非空 `mappings` 面板配置构造。
- 保存、导出、重新导入、上传包含 `map-content` 的 Workflow 后，端口与连线不丢失；子 Workflow 调用也保留类型。

## 7. 设计结论

`construct_map_content` 只构造 `map-content`；`map_content_get` 只消费 Map 并按键输出 `content`。两个节点同批落地，旧 `content_map` 不保留。