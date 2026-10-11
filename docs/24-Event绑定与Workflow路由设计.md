# 24 Event 绑定与 Workflow 路由设计

> 类型:设计文档。
> 性质:现行文档。
> 归属:`webui_py/` + `agent/`。
> 适用版本:平台 `4.0.0+`。

本文记录已实现的绑定路由行为。当前运行路径见 [20-Event 协议与流转](20-Event协议与流转.md)；全局激活 Workflow 回退不再参与事件路由。

## 1. 核心规则

`handle_task` 收到一个带 `event_type` 和 `payload` 的 Event 后，先记录原事件，再按原事件的 `event_type` 查询启用的绑定。每个事件类型至多绑定一个 Workflow（现有 `event_bindings.event_type` 唯一索引）。

- 查到启用绑定：生成一个 `workflow` Event，`payload.workflow_id` 为绑定中的 Workflow ID，其他 payload 字段沿用原事件的 payload，发布到主队列。
- 没查到绑定或绑定已禁用：处理到此结束，不发布 `workflow` 或其他后续 Event；原事件仍留在历史中。
- 绑定查询失败：作为处理错误报告，不等同于“没有绑定”，也不能回退到别的 Workflow。
- 删除 `_id = "agent"` 的全局 `workflow_id` 在事件路由中的读取和回退逻辑。路由只由事件绑定决定。

绑定只决定要运行哪个 Workflow，不规定原事件必须叫 `qq` 或 `terminal`，也不规定 payload 必须有 `content`、`source`。上游适配器负责输入筛选和构造事件，`handle_task` 不应为每种外部 Event 手写一份固定的 Workflow 转换逻辑。`workflow`、`response`、`error` 是内部事件，不走上述绑定路由，分别负责执行、记录结果、记录错误，避免内部事件再次触发自身。

## 2. Workflow Event 与输入元数据

例如收到：

```json
{
  "event_type": "terminal",
  "payload": {"content": "执行任务", "files": []}
}
```

若 `terminal` 绑定到 ID 为 `66aabbccddeeff0011223344` 的 Workflow，则发布：

```json
{
  "event_type": "workflow",
  "payload": {
    "content": "执行任务",
    "files": [],
    "workflow_id": "66aabbccddeeff0011223344"
  }
}
```

`workflow_id` 是 `workflow` Event payload 的必填、保留字段，由路由写入绑定的 ID，不信任或沿用原事件同名字段。执行器只从 `payload.workflow_id` 选择 Workflow，不再通过 `source` 重新查询绑定，也不读取全局设置。发布时固定目标 ID，因此绑定在 Event 入队后发生变化，不影响这次执行。

选中 Workflow 后，仍按 Input 节点元数据的端口名称从整个 `workflow` Event payload 取同名字段：声明 `workflow_id` 输入端口便能读取该 ID；不声明也照常执行。`content`、`source` 等其他字段同理，是否成为输入由 Workflow 自己决定。`workflow_id` 不属于 Workflow 定义内部的依赖标识，仅用于这次顶层执行的选择和可选输入。

## 3. 目标不存在与 Error Event

执行 `workflow` Event 时，如果 `payload.workflow_id` 对应的 Workflow 不存在（例如绑定创建后目标被删除），不运行其他 Workflow，也不发布 `response`；改为发布一次终态 `error` Event：

```json
{
  "event_type": "error",
  "payload": {
    "workflow_id": "66aabbccddeeff0011223344",
    "message": "workflow not found"
  }
}
```

`error` 通过主队列记录进 Event 历史，供事件流查看；其 handler 不执行 Workflow，也不重新查绑定。这里只规定“目标 Workflow 不存在”的错误事件；MongoDB 查询失败、Workflow 校验失败及节点执行失败等其他错误的处理不在本文范围内，不将它们伪装成“未绑定”或“目标不存在”。

## 4. 实施边界与验收

- Agent：把绑定查找前移至原事件路由；`workflow` handler 根据 payload ID 加载 Workflow；移除全局设置回退；增加 `error` handler。保留原事件和新事件各自的历史记录。
- Event 目录：`workflow` schema 将 `workflow_id` 设为必填，不强制 `content` / `source`；新增 `error` 类型及上述 payload 格式；同步更新当前协议文档。
- 检查用例：启用绑定生成携带绑定 ID 的 `workflow` Event；无绑定或禁用绑定不产生后续 Event；原 payload 的同名 ID 不能覆盖绑定 ID；执行事件的 ID 决定目标，Input 可选读取 ID；目标不存在恰好发布一个 `error` Event、不发布 `response`、不回退全局设置。

上述事件路由、目录协议和定向测试已实现。