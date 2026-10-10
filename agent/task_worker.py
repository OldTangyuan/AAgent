# agent/task_worker.py
import os
import time
import traceback
from datetime import datetime, timezone
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from workflow_parser import WorkflowParseError, _read_workflow, parse_workflow
from workflow_validator import validate_workflow
from workflow_nodes import propagate_workflow_output, run_workflow_map

from history_repository import record_history
from queue_client import (
    MAIN_AGENT_QUEUE_NAME,
    pop_from_queue,
    publish_to_queue,
    set_worker_status,
)


def read_bound_workflow_id(event_type: str) -> str | None:
    mongo_kwargs = {
        "host": os.getenv("MONGO_HOST", "mongodb"),
        "port": int(os.getenv("MONGO_PORT", "27017")),
        "serverSelectionTimeoutMS": 5000,
    }
    if os.getenv("MONGO_USER"):
        mongo_kwargs.update(
            username=os.environ["MONGO_USER"],
            password=os.getenv("MONGO_PASS", ""),
            authSource="admin",
        )
    try:
        with MongoClient(**mongo_kwargs) as client:
            database = client[os.getenv("MONGO_DATABASE", "agent")]
            binding = database[os.getenv("MONGO_EVENT_BINDING_COLLECTION", "event_bindings")].find_one(
                {"event_type": event_type, "enabled": True}, {"workflow_id": 1}
            )
    except PyMongoError as error:
        raise RuntimeError("failed to read event binding") from error
    return str(binding["workflow_id"]) if binding is not None else None

def handle_task(e: dict):
    record_history(e)
    event_type = e["event_type"]
    if event_type in ("response", "error"):
        return
    if event_type != "workflow":
        workflow_id = read_bound_workflow_id(event_type)
        if workflow_id is not None:
            publish_to_queue(MAIN_AGENT_QUEUE_NAME, {
                "event_type": "workflow",
                "payload": {**e["payload"], "workflow_id": workflow_id},
            })
        return

    workflow_id = e["payload"]["workflow_id"]
    try:
        workflow_document = _read_workflow(workflow_id, by_id=True)
    except WorkflowParseError as error:
        if not str(error).startswith("workflow not found:"):
            raise
        publish_to_queue(MAIN_AGENT_QUEUE_NAME, {
            "event_type": "error",
            "payload": {"workflow_id": workflow_id, "message": "workflow not found"},
        })
        return
    validate_workflow(workflow_document)
    workflow_map = parse_workflow(workflow_document)
    for node in workflow_map:
        node['_workflow_call_stack'] = [workflow_document['name']]

    start = next(
        (
            index
            for index, node in enumerate(workflow_map)
            if node["type"] == "input"
        ),
        None,
    )
    if start is None:
        raise ValueError("workflow has no input node")

    input_node = workflow_map[start]
    workflow_ports = input_node.get('workflowPorts', [])
    for port in workflow_ports:
        propagate_workflow_output(
            workflow_map, input_node, port['id'], e['payload'].get(port['name'])
        )

    output = run_workflow_map(workflow_map, start)
    publish_to_queue(MAIN_AGENT_QUEUE_NAME, {
        "event_type": "response",
        "payload": {"content": output.get("content", output)},
    })
    

def main():
    print("Agent worker started...")
    while True:
        try:
            set_worker_status({
                "state": "idle",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            task = pop_from_queue(MAIN_AGENT_QUEUE_NAME, timeout=5)
            if task is None:
                continue
            set_worker_status({
                "state": "processing",
                "event": task,
                "started_at": datetime.now(timezone.utc).isoformat(),
            })
            try:
                handle_task(task)
            finally:
                set_worker_status({
                    "state": "idle",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as e:
            print("agent处理失败:", e)
            traceback.print_exc()
            time.sleep(2)


if __name__ == "__main__":
    main()