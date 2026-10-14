import json
import os
from datetime import datetime, timezone
from typing import Any, Literal

import redis
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pymongo import DESCENDING
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError, PyMongoError

from workflow_contract import filter_connections
from workflow_validator import WorkflowValidationError, validate_workflow

MAX_WORKFLOW_NODES = 200
MAX_WORKFLOW_CONNECTIONS = 1000
MAX_WORKFLOW_METADATA_PORTS = 50
MAX_WORKFLOW_NODE_REFERENCES = 50
MAX_REMOTE_TOOL_REFERENCES = 100
MAX_WORKFLOW_DESCRIPTION_LENGTH = 2000
WORKFLOW_SCHEMA_VERSION = "1.1"
DATA_TYPES = {"content", "message", "event", "map-content", "list-content", "list-message", "list-event"}

NODE_BASE_FIELDS = {"id", "type", "name", "x", "y", "arguments"}
NODE_SHARED_FIELDS = {"workflowPorts", "dataInputPorts", "input_ports", "output_ports"}
NODE_ARGUMENT_FIELDS_BY_TYPE = {
    "input": set(),
    "output": set(),
    "router": {"branches"},
    "construct_message": {"role", "role_source"},
    "construct_content": {"append_items"},
    "construct_map_content": {"mappings"},
    "map_content_get": set(),
    "deserialize_json": {"outputs"},
    "split_event": set(),
    "construct_list": {"item_type", "initial_value_count"},
    "list_append": {"item_type", "position"},
    "foreach": {"item_type"},
    "history": {"event_types", "limit"},
    "llm": {"model", "think", "tool_calls", "tools"},
    "local_tool": {"tool", "parameters"},
    "remote_sync_tool": {"tool", "parameters", "outputs", "timeout_ms"},
    "remote_async_tool": {"tool", "parameters", "timeout_ms", "callback"},
    "context_create": {"value_type"},
    "context_read": {"value_type"},
    "context_write": {"value_type"},
    "session_create": {"value_type"},
    "session_read": {"value_type"},
    "session_write": {"value_type"},
    "workflow": {"workflow_name"},
}
NODE_ARGUMENT_FIELDS = set().union(*NODE_ARGUMENT_FIELDS_BY_TYPE.values())


def node_arguments(node: dict[str, Any]) -> dict[str, Any]:
    arguments = node.get("arguments")
    return arguments if isinstance(arguments, dict) else {}


def list_type_for_item(item_type: Any) -> str:
    return f"list-{item_type}"


def tool_node_error(node: dict[str, Any], max_wait_ms: int, max_async_timeout_ms: int) -> str | None:
    arguments = node_arguments(node)
    tool_name = arguments.get("tool")
    parameters = arguments.get("parameters", [])
    if not isinstance(tool_name, str) or not tool_name:
        return "Tool 节点必须填写工具名称"
    if node.get("type") == "local_tool":
        if (
            not isinstance(parameters, list)
            or any(not isinstance(parameter, str) or not parameter or parameter == "control-in" for parameter in parameters)
            or len(parameters) != len(set(parameters))
        ):
            return "Local Tool 参数必须是非空、不重复且不能为 control-in 的字符串"
    else:
        if not isinstance(parameters, list) or any(
            not isinstance(parameter, dict)
            or set(parameter) != {"name", "type"}
            or not isinstance(parameter.get("name"), str)
            or not parameter["name"]
            or parameter["name"] == "control-in"
            or parameter.get("type") not in DATA_TYPES
            for parameter in parameters
        ):
            return "Remote Tool 参数必须包含有效的 name 和 type"
        parameter_names = [parameter["name"] for parameter in parameters]
        if len(parameter_names) != len(set(parameter_names)):
            return "Remote Tool 参数名称不能重复"
        if node.get("type") == "remote_sync_tool":
            outputs = arguments.get("outputs", [])
            if not isinstance(outputs, list) or any(
                not isinstance(output, dict)
                or set(output) != {"name", "type"}
                or not isinstance(output.get("name"), str)
                or not output["name"]
                or output["name"] == "control-out"
                or output.get("type") not in DATA_TYPES
                for output in outputs
            ):
                return "Remote Sync Tool 输出必须包含有效的 name 和 type"
            output_names = [output["name"] for output in outputs]
            if len(output_names) != len(set(output_names)):
                return "Remote Sync Tool 输出名称不能重复"
        timeout_ms = arguments.get("timeout_ms")
        maximum_ms = max_wait_ms if node.get("type") == "remote_sync_tool" else max_async_timeout_ms
        if timeout_ms is not None and (
            not isinstance(timeout_ms, int)
            or isinstance(timeout_ms, bool)
            or timeout_ms <= 0
            or timeout_ms > maximum_ms
        ):
            return f"Remote Tool timeout_ms 必须是 1 到 {maximum_ms} 的整数"
        if node.get("type") == "remote_async_tool":
            callback = arguments.get("callback")
            if callback is not None and (
                not isinstance(callback, dict)
                or set(callback) != {"type", "queue", "event_type", "on"}
                or callback.get("type") != "redis"
                or not isinstance(callback.get("queue"), str)
                or not callback["queue"]
                or len(callback["queue"]) > 256
                or not isinstance(callback.get("event_type"), str)
                or not callback["event_type"]
                or len(callback["event_type"]) > 128
                or not isinstance(callback.get("on"), list)
                or not callback["on"]
                or any(status not in {"working", "completed", "failed"} for status in callback["on"])
                or len(callback["on"]) != len(set(callback["on"]))
            ):
                return "Remote Async Tool callback 必须是有效的 Redis 回调配置"
    return None


def node_format_error(node: dict[str, Any], index: int) -> str | None:
    node_type = node.get("type")
    arguments = node.get("arguments", {})
    if node_type not in NODE_ARGUMENT_FIELDS_BY_TYPE:
        return f"nodes[{index}].type 不受支持: {node_type}"
    if not isinstance(arguments, dict):
        return f"nodes[{index}].arguments 必须是对象"
    misplaced_arguments = NODE_ARGUMENT_FIELDS.intersection(node)
    if misplaced_arguments:
        return f"nodes[{index}] 的可配置字段必须放入 arguments: {', '.join(sorted(misplaced_arguments))}"
    misplaced_shared = NODE_SHARED_FIELDS.intersection(arguments)
    if misplaced_shared:
        return f"nodes[{index}] 的公共字段必须位于一级: {', '.join(sorted(misplaced_shared))}"
    unsupported_arguments = set(arguments) - NODE_ARGUMENT_FIELDS_BY_TYPE.get(node_type, set())
    if unsupported_arguments:
        return f"nodes[{index}].arguments 包含该节点不支持的字段: {', '.join(sorted(unsupported_arguments))}"
    unsupported_fields = set(node) - NODE_BASE_FIELDS - NODE_SHARED_FIELDS
    if unsupported_fields:
        return f"nodes[{index}] 包含不支持的一级字段: {', '.join(sorted(unsupported_fields))}"
    if node_type == "history":
        event_types = arguments.get("event_types")
        limit = arguments.get("limit")
        if (
            not isinstance(event_types, list)
            or not event_types
            or any(event_type not in {"terminal", "response"} for event_type in event_types)
            or len(event_types) != len(set(event_types))
        ):
            return f"nodes[{index}].arguments.event_types 只能包含不重复的 terminal 或 response"
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
            return f"nodes[{index}].arguments.limit 必须是 1 到 1000 的整数"
    if node_type == "list_append":
        if arguments.get("item_type") not in {"content", "message", "event"}:
            return f"nodes[{index}].arguments.item_type 必须是 content、message 或 event"
        if arguments.get("position") not in {"start", "end"}:
            return f"nodes[{index}].arguments.position 必须是 start 或 end"
    if node_type == "deserialize_json":
        outputs = arguments.get("outputs")
        if not isinstance(outputs, list) or not outputs or any(
            not isinstance(output, dict)
            or set(output) != {"key", "type"}
            or not isinstance(output.get("key"), str)
            or not output["key"]
            or output["key"] == "control-out"
            or output.get("type") not in DATA_TYPES
            for output in outputs
        ):
            return f"nodes[{index}].arguments.outputs 必须包含有效的 key 和 type"
        output_keys = [output["key"] for output in outputs]
        if len(output_keys) != len(set(output_keys)):
            return f"nodes[{index}].arguments.outputs 的 key 不能重复"
    if node_type == "construct_map_content":
        mappings = arguments.get("mappings")
        if not isinstance(mappings, list) or not mappings or any(
            not isinstance(item, dict)
            or set(item) != {"key", "value"}
            or not isinstance(item.get("key"), str)
            or not item["key"]
            or not isinstance(item.get("value"), str)
            for item in mappings
        ):
            return f"nodes[{index}].arguments.mappings 必须包含非空字符串 key 和字符串 value"
        keys = [item["key"] for item in mappings]
        if len(keys) != len(set(keys)):
            return f"nodes[{index}].arguments.mappings 的 key 不能重复"
    if node_type in {"context_create", "context_read", "context_write", "session_create", "session_read", "session_write"}:
        if arguments.get("value_type") not in DATA_TYPES:
            return f"nodes[{index}].arguments.value_type 必须是受支持的数据类型"
    return None


class WorkflowPortMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    type: Literal["content", "message", "event", "map-content", "list-content", "list-message", "list-event"]


class WorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=MAX_WORKFLOW_DESCRIPTION_LENGTH)
    schema_version: Literal["1.1"]  # 只接受version=1.1的workflow
    input_ports: list[WorkflowPortMetadata] = Field(max_length=MAX_WORKFLOW_METADATA_PORTS)
    output_ports: list[WorkflowPortMetadata] = Field(max_length=MAX_WORKFLOW_METADATA_PORTS)
    nodes: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_WORKFLOW_NODES)
    connections: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_WORKFLOW_CONNECTIONS)
    workflow_nodes: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_WORKFLOW_NODE_REFERENCES)
    remote_tools: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_REMOTE_TOOL_REFERENCES)


class WorkflowCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class WorkflowRenameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class WorkflowNodeReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    input_ports: list[WorkflowPortMetadata] | None = None
    output_ports: list[WorkflowPortMetadata] | None = None
    previous_name: str | None = Field(default=None, max_length=120)


class WorkflowMetadataPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    workflow_nodes: list[WorkflowNodeReference] | None = None


class RemoteToolReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    input_ports: list[WorkflowPortMetadata] = Field(default_factory=list, max_length=MAX_WORKFLOW_METADATA_PORTS)
    output_ports: list[WorkflowPortMetadata] = Field(default_factory=list, max_length=MAX_WORKFLOW_METADATA_PORTS)


def duplicate_port_name(ports: list[WorkflowPortMetadata]) -> bool:
    names = [port.name.strip().casefold() for port in ports]
    return any(not name for name in names) or len(names) != len(set(names))


def synchronize_metadata_ports(
    nodes: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    input_ports: list[dict[str, Any]],
    output_ports: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    input_node_ports = [{**port, "id": f"workflow:{port['name']}"} for port in input_ports]
    output_node_ports = [{**port, "id": f"workflow:{port['name']}"} for port in output_ports]
    synchronized_nodes = [
        {
            **node,
            **(
                {"workflowPorts": input_node_ports}
                if node.get("type") == "input"
                else {"workflowPorts": output_node_ports}
                if node.get("type") == "output"
                else {}
            ),
        }
        for node in nodes
    ]
    return synchronized_nodes, filter_connections(connections, synchronized_nodes, input_ports, output_ports)


def filter_invalid_connections(
    nodes: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    input_ports: list[dict[str, Any]],
    output_ports: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop links whose endpoints no longer exist after metadata changes."""
    return nodes, filter_connections(connections, nodes, input_ports, output_ports)


def synchronize_workflow_nodes(
    nodes: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    workflow_nodes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    references = {reference["name"]: reference for reference in workflow_nodes}
    removed_node_ids = {
        node.get("id")
        for node in nodes
        if node.get("type") == "workflow" and node_arguments(node).get("workflow_name") not in references
    }
    synchronized_nodes = []
    workflow_node_by_id = {}
    for node in nodes:
        if node.get("id") in removed_node_ids:
            continue
        if node.get("type") == "workflow":
            arguments = node_arguments(node)
            reference = references[arguments["workflow_name"]]
            node = {
                **node,
                "arguments": {**arguments, "workflow_name": reference["name"]},
                "input_ports": reference["input_ports"],
                "output_ports": reference["output_ports"],
            }
            workflow_node_by_id[node["id"]] = node
        synchronized_nodes.append(node)

    def valid_workflow_endpoint(node: dict[str, Any], port_id: Any, connection_type: Any, field: str) -> bool:
        return any(
            port_id == f"workflow:{port['name']}" and connection_type == port["type"]
            for port in node[field]
        )

    synchronized_connections = []
    for connection in connections:
        if connection.get("fromId") in removed_node_ids or connection.get("toId") in removed_node_ids:
            continue
        if connection.get("type") != "control":
            source = workflow_node_by_id.get(connection.get("fromId"))
            target = workflow_node_by_id.get(connection.get("toId"))
            if source and not valid_workflow_endpoint(source, connection.get("fromPortId"), connection.get("type"), "output_ports"):
                continue
            if target and not valid_workflow_endpoint(target, connection.get("toPortId"), connection.get("type"), "input_ports"):
                continue
        synchronized_connections.append(connection)
    return synchronized_nodes, synchronized_connections


def remap_workflow_node_names(
    nodes: list[dict[str, Any]],
    references: list[WorkflowNodeReference],
) -> list[dict[str, Any]]:
    replacements = {
        reference.previous_name: reference.name.strip()
        for reference in references
        if reference.previous_name and reference.previous_name != reference.name.strip()
    }
    remapped = []
    for node in nodes:
        if node.get("type") != "workflow":
            remapped.append(node)
            continue
        arguments = node_arguments(node)
        previous_name = arguments.get("workflow_name")
        next_name = replacements.get(previous_name)
        remapped.append(
            {
                **node,
                "arguments": {**arguments, **({"workflow_name": next_name} if next_name else {})},
            }
        )
    return remapped


def synchronize_workflow_node_snapshots(
    nodes: list[dict[str, Any]],
    references: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    references_by_name = {reference["name"]: reference for reference in references}
    synchronized = []
    for node in nodes:
        if node.get("type") != "workflow":
            synchronized.append(node)
            continue
        arguments = node_arguments(node)
        reference = references_by_name.get(arguments.get("workflow_name"))
        if reference is None:
            synchronized.append(node)
            continue
        synchronized.append({
            **node,
            "input_ports": reference["input_ports"],
            "output_ports": reference["output_ports"],
        })
    return synchronized


def workflow_response(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": document.get("name", ""),
        "description": document.get("description", ""),
        "schema_version": document.get("schema_version"),
        "nodes": document.get("nodes", []),
        "connections": document.get("connections", []),
        "input_ports": document.get("input_ports", []),
        "output_ports": document.get("output_ports", []),
        "workflow_nodes": document.get("workflow_nodes", []),
        "remote_tools": document.get("remote_tools", []),
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
    }


def create_workflows_router(
    redis_client: redis.Redis,
    tools_key: str,
    model_configs: Collection,
    workflows: Collection,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/workflows")
    def list_workflows():
        try:
            items = workflows.find(
                {},
                {"name": 1, "description": 1, "schema_version": 1, "nodes": 1, "connections": 1, "input_ports": 1, "output_ports": 1, "workflow_nodes": 1, "remote_tools": 1, "created_at": 1, "updated_at": 1},
            ).sort("updated_at", DESCENDING)
            return {
                "items": [
                    {
                        "name": item.get("name", ""),
                        "description": item.get("description", ""),
                        "schema_version": item.get("schema_version"),
                        "node_count": len(item.get("nodes", [])),
                        "connection_count": len(item.get("connections", [])),
                        "input_ports": item.get("input_ports", []),
                        "output_ports": item.get("output_ports", []),
                        "workflow_nodes": item.get("workflow_nodes", []),
                        "remote_tools": item.get("remote_tools", []),
                        "created_at": item.get("created_at"),
                        "updated_at": item.get("updated_at"),
                    }
                    for item in items
                ]
            }
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "Workflow 列表暂时不可用"})

    @router.get("/api/workflow/{name}")
    def get_workflow(name: str):
        try:
            document = workflows.find_one({"name": name})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "Workflow 暂时不可用"})
        if document is None:
            return JSONResponse(status_code=404, content={"error": "Workflow 不存在或已被删除"})
        return workflow_response(document)

    @router.post("/api/workflow/{name}", status_code=201)
    def create_workflow(name: str, payload: WorkflowRequest):
        return save_workflow(name, payload, overwrite=False)

    @router.put("/api/workflow/{name}")
    def overwrite_workflow(name: str, payload: WorkflowRequest):
        return save_workflow(name, payload, overwrite=True)

    def save_workflow(name: str, payload: WorkflowRequest, overwrite: bool):
        if not name:
            return JSONResponse(status_code=400, content={"error": "Workflow 名称不能为空"})
        if payload.name != name:
            return JSONResponse(status_code=400, content={"error": "请求路径名称必须与 Workflow JSON 的 name 一致"})
        try:
            existing = workflows.find_one({"name": name})
            if overwrite and existing is None:
                return JSONResponse(status_code=404, content={"error": "Workflow 不存在或已被删除"})
            if not overwrite and existing is not None:
                return JSONResponse(status_code=409, content={"error": "Workflow 名称已存在"})
            if duplicate_port_name(payload.input_ports) or duplicate_port_name(payload.output_ports):
                return JSONResponse(status_code=400, content={"error": "Workflow 边界端口名称不能为空或重名"})
            input_ports = [port.model_dump() | {"name": port.name.strip()} for port in payload.input_ports]
            output_ports = [port.model_dump() | {"name": port.name.strip()} for port in payload.output_ports]
            references = payload.workflow_nodes
            reference_names = [item.get("name", "").strip() for item in references]
            if any(not reference_name for reference_name in reference_names) or len(reference_names) != len(set(reference_names)):
                return JSONResponse(status_code=400, content={"error": "Workflow 依赖名称不能为空或重复"})
            if name in reference_names:
                return JSONResponse(status_code=400, content={"error": "Workflow 不能引入自身"})
            referenced = list(workflows.find({"name": {"$in": reference_names}})) if reference_names else []
            by_name = {item.get("name"): item for item in referenced}
            if len(by_name) != len(reference_names):
                return JSONResponse(status_code=400, content={"error": "引入的 Workflow 不存在或已被删除"})
            canonical_references = []
            for reference in references:
                actual = by_name[reference["name"].strip()]
                input_contract = [port.model_dump() for port in reference.get("input_ports", [])]
                output_contract = [port.model_dump() for port in reference.get("output_ports", [])]
                if input_contract != actual.get("input_ports", []) or output_contract != actual.get("output_ports", []):
                    return JSONResponse(status_code=400, content={"error": f"Workflow 依赖 {actual['name']} 的端口契约不一致"})
                canonical_references.append({"name": actual["name"], "input_ports": input_contract, "output_ports": output_contract})
            values = payload.model_dump()
            values["nodes"] = synchronize_workflow_node_snapshots(values["nodes"], canonical_references)
            values.update({"name": name, "input_ports": input_ports, "output_ports": output_ports, "workflow_nodes": canonical_references})
            try:
                validate_workflow(values)
            except WorkflowValidationError as error:
                return JSONResponse(status_code=400, content={"error": str(error)})
            max_wait_ms = int(os.getenv("TOOL_CLIENT_MAX_WAIT_MS", "10000"))
            max_async_timeout_ms = int(os.getenv("TOOL_CLIENT_MAX_ASYNC_TIMEOUT_MS", "3600000"))
            for node in values["nodes"]:
                if node.get("type") in {"local_tool", "remote_sync_tool", "remote_async_tool"}:
                    error = tool_node_error(node, max_wait_ms, max_async_timeout_ms)
                    if error:
                        return JSONResponse(status_code=400, content={"error": error})
            local_tools = [node for node in values["nodes"] if node.get("type") == "local_tool"]
            if local_tools:
                registered = {value.decode() if isinstance(value, bytes) else value for value in redis_client.hkeys(tools_key)}
                if any(node_arguments(node).get("tool") not in registered for node in local_tools):
                    return JSONResponse(status_code=400, content={"error": "Tool 节点引用了未注册的工具"})
            model_nodes = [node for node in values["nodes"] if node.get("type") == "llm"]
            model_ids = [ObjectId(node_arguments(node).get("model", "")) for node in model_nodes]
            available = {item["_id"] for item in model_configs.find({"_id": {"$in": model_ids}, "enabled": True}, {"_id": 1})} if model_ids else set()
            if any(model_id not in available for model_id in model_ids):
                return JSONResponse(status_code=400, content={"error": "LLM 节点引用了不存在或已停用的模型配置"})
        except (InvalidId, TypeError, ValueError, KeyError) as error:
            return JSONResponse(status_code=400, content={"error": f"Workflow 契约无效: {error}"})
        except redis.RedisError:
            return JSONResponse(status_code=503, content={"error": "暂时无法校验 Tool 注册表"})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法校验或保存 Workflow"})

        now = datetime.now(timezone.utc)
        values["description"] = values["description"].strip()
        values["updated_at"] = now
        try:
            if overwrite:
                values["created_at"] = existing.get("created_at", now)
                workflows.replace_one({"_id": existing["_id"]}, values)
                document = workflows.find_one({"_id": existing["_id"]})
            else:
                values["created_at"] = now
                result = workflows.insert_one(values)
                values["_id"] = result.inserted_id
                document = values
        except DuplicateKeyError:
            return JSONResponse(status_code=409, content={"error": "Workflow 名称已存在"})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法保存 Workflow"})
        return workflow_response(document)

    @router.patch("/api/workflow/{name}/metadata")
    def update_workflow_metadata(name: str, payload: WorkflowMetadataPatchRequest):
        # 改名和删除只作用于目标 Workflow，不级联改写其他引用处；全量同步代价大且没有功能收益。
        next_name = payload.name
        try:
            existing = workflows.find_one({"name": name})
            if existing is None:
                return JSONResponse(status_code=404, content={"error": "Workflow 不存在或已被删除"})
            if workflows.find_one({"name": next_name, "_id": {"$ne": existing["_id"]}}):
                return JSONResponse(status_code=409, content={"error": "Workflow 名称已存在"})
            updates = {"name": next_name, "updated_at": datetime.now(timezone.utc)}
            if payload.workflow_nodes is not None:
                references = [reference.model_dump(exclude_none=True) for reference in payload.workflow_nodes]
                names = [reference["name"].strip() for reference in references]
                targets = list(workflows.find({"name": {"$in": names}})) if names else []
                by_name = {target["name"]: target for target in targets}
                if len(names) != len(set(names)) or any(target not in by_name for target in names):
                    return JSONResponse(status_code=400, content={"error": "Workflow 依赖名称重复或不存在"})
                remapped_nodes = remap_workflow_node_names(existing.get("nodes", []), references)
                canonical_references = [
                    {
                        "name": value,
                        "input_ports": by_name[value].get("input_ports", []),
                        "output_ports": by_name[value].get("output_ports", []),
                    }
                    for value in names
                ]
                nodes, connections = synchronize_workflow_nodes(
                    remapped_nodes,
                    existing.get("connections", []),
                    canonical_references,
                )
                updates.update({
                    "workflow_nodes": canonical_references,
                    "nodes": nodes,
                    "connections": connections,
                })
            workflows.update_one({"_id": existing["_id"]}, {"$set": updates})
            document = workflows.find_one({"_id": existing["_id"]})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法更新 Workflow 元数据"})
        return workflow_response(document)

    @router.delete("/api/workflow/{name}")
    def delete_workflow(name: str):
        # 删除只移除目标 Workflow，不扫描或修改其他 Workflow 中的引用。
        try:
            result = workflows.delete_one({"name": name})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法删除 Workflow"})
        if result.deleted_count == 0:
            return JSONResponse(status_code=404, content={"error": "Workflow 不存在或已被删除"})
        return {"deleted": True, "name": name}

    return router