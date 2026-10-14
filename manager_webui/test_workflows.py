import unittest

from pydantic import ValidationError

from workflows import (
    WORKFLOW_SCHEMA_VERSION,
    WorkflowMetadataPatchRequest,
    WorkflowNodeReference,
    WorkflowRequest,
    filter_invalid_connections,
    node_format_error,
    remap_workflow_node_names,
    synchronize_workflow_nodes,
)


class WorkflowSchemaVersionTest(unittest.TestCase):
    def test_workflow_names_reject_empty_but_preserve_whitespace(self):
        with self.assertRaises(ValidationError):
            WorkflowRequest.model_validate({"name": "", "schema_version": WORKFLOW_SCHEMA_VERSION})

        payload = {
            "name": "   ",
            "schema_version": WORKFLOW_SCHEMA_VERSION,
            "input_ports": [],
            "output_ports": [],
            "nodes": [{"id": "output", "type": "output", "workflowPorts": []}],
        }
        self.assertEqual(WorkflowRequest.model_validate(payload).name, "   ")
        self.assertEqual(WorkflowMetadataPatchRequest(name="  ").name, "  ")

    def test_accepts_current_version_and_rejects_past_and_future_versions(self):
        payload = {
            "name": "echo",
            "schema_version": WORKFLOW_SCHEMA_VERSION,
            "input_ports": [],
            "output_ports": [],
            "nodes": [{"id": "output", "type": "output", "workflowPorts": []}],
        }
        self.assertEqual(
            WorkflowRequest.model_validate(payload).schema_version,
            WORKFLOW_SCHEMA_VERSION,
        )

        without_version = {key: value for key, value in payload.items() if key != "schema_version"}
        with self.assertRaises(ValidationError) as raised:
            WorkflowRequest.model_validate(without_version)
        self.assertEqual(raised.exception.errors()[0]["loc"], ("schema_version",))

        # 升级 Workflow 协议时，更新两侧样例，确保它们都不是当前版本。
        for version in ("1.0", "1.2"):
            with self.subTest(version=version):
                with self.assertRaises(ValidationError) as raised:
                    WorkflowRequest.model_validate({**payload, "schema_version": version})
                self.assertEqual(raised.exception.errors()[0]["loc"], ("schema_version",))


class WorkflowConnectionFilterTest(unittest.TestCase):
    def test_dependency_rename_remaps_only_matching_canvas_nodes_and_refreshes_ports(self):
        nodes = [
            {
                "id": "call-child",
                "type": "workflow",
                "arguments": {"workflow_name": "Old child"},
                "input_ports": [{"name": "old", "type": "content"}],
                "output_ports": [],
            },
            {"id": "call-other", "type": "workflow", "arguments": {"workflow_name": "Other"}},
        ]
        references = [
            WorkflowNodeReference(name="New child", previous_name="Old child"),
            WorkflowNodeReference(name="Other"),
        ]

        remapped = remap_workflow_node_names(nodes, references)
        synchronized, _ = synchronize_workflow_nodes(
            remapped,
            [],
            [
                {"name": "New child", "input_ports": [{"name": "value", "type": "content"}], "output_ports": []},
                {"name": "Other", "input_ports": [], "output_ports": []},
            ],
        )

        self.assertEqual(synchronized[0]["arguments"]["workflow_name"], "New child")
        self.assertEqual(synchronized[0]["input_ports"], [{"name": "value", "type": "content"}])
        self.assertEqual(synchronized[1]["arguments"]["workflow_name"], "Other")

    def test_preserves_session_id_and_value_connections(self):
        nodes = [
            {"id": "input", "type": "input", "workflowPorts": [{"id": "workflow:value", "name": "value", "type": "content"}]},
            {"id": "create", "type": "session_create", "arguments": {"value_type": "content"}},
            {"id": "write", "type": "session_write", "arguments": {"value_type": "content"}},
            {"id": "read", "type": "session_read", "arguments": {"value_type": "content"}},
            {"id": "output", "type": "output", "workflowPorts": [{"id": "workflow:result", "name": "result", "type": "content"}]},
        ]
        connections = [
            {"fromId": "input", "fromPortId": "workflow:value", "toId": "create", "toPortId": "initial-value", "type": "content"},
            {"fromId": "create", "fromPortId": "session-id", "toId": "write", "toPortId": "session-id", "type": "content"},
            {"fromId": "input", "fromPortId": "workflow:value", "toId": "write", "toPortId": "value-in", "type": "content"},
            {"fromId": "write", "fromPortId": "session-id", "toId": "read", "toPortId": "session-id", "type": "content"},
            {"fromId": "read", "fromPortId": "value-out", "toId": "output", "toPortId": "workflow:result", "type": "content"},
        ]

        _, filtered = filter_invalid_connections(
            nodes, connections, [{"name": "value", "type": "content"}], [{"name": "result", "type": "content"}],
        )

        self.assertEqual(filtered, connections)

    def test_preserves_map_content_connections(self):
        nodes = [
            {
                "id": "input",
                "type": "input",
                "workflowPorts": [
                    {"id": "workflow:value", "name": "value", "type": "content"}
                ],
            },
            {
                "id": "map",
                "type": "construct_map_content",
                "arguments": {"mappings": [{"key": "a", "value": "b"}]},
            },
            {"id": "get", "type": "map_content_get"},
            {
                "id": "output",
                "type": "output",
                "workflowPorts": [
                    {"id": "workflow:result", "name": "result", "type": "content"}
                ],
            },
        ]
        connections = [
            {"id": "map-get", "fromId": "map", "fromPortId": "map-out", "toId": "get", "toPortId": "map-in", "type": "map-content"},
            {"id": "input-key", "fromId": "input", "fromPortId": "workflow:value", "toId": "get", "toPortId": "key-in", "type": "content"},
            {"id": "get-output", "fromId": "get", "fromPortId": "content-out", "toId": "output", "toPortId": "workflow:result", "type": "content"},
        ]

        _, filtered = filter_invalid_connections(
            nodes,
            connections,
            [{"name": "value", "type": "content"}],
            [{"name": "result", "type": "content"}],
        )

        self.assertEqual(filtered, connections)

    def test_preserves_construct_message_role_port_connection(self):
        nodes = [
            {
                "id": "input",
                "type": "input",
                "workflowPorts": [
                    {"id": "workflow:role", "name": "role", "type": "content"}
                ],
            },
            {
                "id": "message",
                "type": "construct_message",
                "arguments": {"role_source": "port", "role": "user"},
            },
        ]
        connection = {
            "id": "role-to-message",
            "fromId": "input",
            "fromPortId": "workflow:role",
            "toId": "message",
            "toPortId": "role-in",
            "type": "content",
        }

        _, connections = filter_invalid_connections(
            nodes,
            [connection],
            [{"name": "role", "type": "content"}],
            [],
        )

        self.assertEqual(connections, [connection])

    def test_preserves_history_to_event_foreach_connection(self):
        nodes = [
            {
                "id": "history",
                "type": "history",
                "arguments": {"event_types": ["response"], "limit": 10},
            },
            {
                "id": "foreach",
                "type": "foreach",
                "arguments": {"item_type": "event"},
            },
        ]
        connection = {
            "id": "history-to-foreach",
            "fromId": "history",
            "fromPortId": "events",
            "toId": "foreach",
            "toPortId": "list-in",
            "type": "list-event",
        }

        _, connections = filter_invalid_connections(nodes, [connection], [], [])

        self.assertEqual(connections, [connection])

    def test_preserves_split_event_connections(self):
        nodes = [
            {
                "id": "input",
                "type": "input",
                "workflowPorts": [
                    {"id": "workflow:event", "name": "event", "type": "event"}
                ],
            },
            {"id": "split", "type": "split_event", "arguments": {}},
            {
                "id": "output",
                "type": "output",
                "workflowPorts": [
                    {"id": "workflow:type", "name": "type", "type": "content"},
                    {"id": "workflow:payload", "name": "payload", "type": "content"},
                ],
            },
        ]
        connections = [
            {"fromId": "input", "fromPortId": "workflow:event", "toId": "split", "toPortId": "event-in", "type": "event"},
            {"fromId": "split", "fromPortId": "type-out", "toId": "output", "toPortId": "workflow:type", "type": "content"},
            {"fromId": "split", "fromPortId": "payload-out", "toId": "output", "toPortId": "workflow:payload", "type": "content"},
        ]

        _, filtered = filter_invalid_connections(
            nodes,
            connections,
            [{"name": "event", "type": "event"}],
            [
                {"name": "type", "type": "content"},
                {"name": "payload", "type": "content"},
            ],
        )

        self.assertEqual(filtered, connections)

    def test_deserialize_json_filters_changed_output_type_but_preserves_control(self):
        nodes = [
            {"id": "input", "type": "input", "workflowPorts": []},
            {
                "id": "deserialize",
                "type": "deserialize_json",
                "arguments": {"outputs": [{"key": "payload", "type": "message"}]},
            },
            {
                "id": "output",
                "type": "output",
                "workflowPorts": [{"id": "workflow:payload", "name": "payload", "type": "content"}],
            },
        ]
        control = {
            "fromId": "deserialize", "fromPortId": "control-out",
            "toId": "output", "toPortId": "control-in", "type": "control",
        }
        stale_data = {
            "fromId": "deserialize", "fromPortId": "payload",
            "toId": "output", "toPortId": "workflow:payload", "type": "content",
        }

        _, filtered = filter_invalid_connections(
            nodes,
            [control, stale_data],
            [],
            [{"name": "payload", "type": "content"}],
        )

        self.assertEqual(filtered, [control])

    def test_rejects_invalid_deserialize_json_outputs(self):
        error = node_format_error(
            {
                "id": "deserialize",
                "type": "deserialize_json",
                "arguments": {"outputs": [{"key": "value", "type": "content"}, {"key": "value", "type": "event"}]},
            },
            0,
        )

        self.assertEqual(error, "nodes[0].arguments.outputs 的 key 不能重复")

    def test_rejects_invalid_context_value_type(self):
        error = node_format_error(
            {
                "id": "context",
                "type": "context_create",
                "arguments": {"value_type": "number"},
            },
            0,
        )

        self.assertEqual(
            error,
            "nodes[0].arguments.value_type 必须是受支持的数据类型",
        )

    def test_preserves_construct_list_to_llm_messages_connection(self):
        nodes = [
            {
                "id": "messages",
                "type": "construct_list",
                "arguments": {
                    "item_type": "message",
                    "initial_value_count": 2,
                },
                "dataInputPorts": ["message-in-0", "message-in-1"],
            },
            {
                "id": "llm",
                "type": "llm",
                "arguments": {
                    "model": "model-id",
                    "think": False,
                    "tool_calls": False,
                    "tools": [],
                },
            },
        ]
        connection = {
            "id": "messages-to-llm",
            "fromId": "messages",
            "fromPortId": "list-out",
            "toId": "llm",
            "toPortId": "messages-in",
            "type": "list-message",
        }

        _, connections = filter_invalid_connections(nodes, [connection], [], [])

        self.assertEqual(connections, [connection])

    def test_preserves_context_connections_for_matching_value_type(self):
        for value_type in ("content", "message", "event", "map-content", "list-content", "list-message", "list-event"):
            with self.subTest(value_type=value_type):
                nodes = [
                    {
                        "id": "create",
                        "type": "context_create",
                        "arguments": {"value_type": value_type},
                    },
                    {
                        "id": "write",
                        "type": "context_write",
                        "arguments": {"value_type": value_type},
                    },
                    {
                        "id": "read",
                        "type": "context_read",
                        "arguments": {"value_type": value_type},
                    },
                    {
                        "id": "output",
                        "type": "output",
                        "workflowPorts": [
                            {"id": "workflow:value", "name": "value", "type": value_type}
                        ],
                    },
                ]
                connections = [
                    {"fromId": "create", "fromPortId": "context-id", "toId": "write", "toPortId": "context-id", "type": "content"},
                    {"fromId": "write", "fromPortId": "context-id", "toId": "read", "toPortId": "context-id", "type": "content"},
                    {"fromId": "write", "fromPortId": "value-out", "toId": "output", "toPortId": "workflow:value", "type": value_type},
                ]

                _, filtered = filter_invalid_connections(
                    nodes,
                    connections,
                    [],
                    [{"name": "value", "type": value_type}],
                )

                self.assertEqual(filtered, connections)

    def test_drops_context_value_connection_after_type_change(self):
        nodes = [
            {
                "id": "write",
                "type": "context_write",
                "arguments": {"value_type": "message"},
            },
            {
                "id": "output",
                "type": "output",
                "workflowPorts": [
                    {"id": "workflow:value", "name": "value", "type": "content"}
                ],
            },
        ]
        connection = {
            "fromId": "write",
            "fromPortId": "value-out",
            "toId": "output",
            "toPortId": "workflow:value",
            "type": "content",
        }

        _, connections = filter_invalid_connections(
            nodes,
            [connection],
            [],
            [{"name": "value", "type": "content"}],
        )

        self.assertEqual(connections, [])


if __name__ == "__main__":
    unittest.main()