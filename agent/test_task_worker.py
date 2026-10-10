import unittest
from unittest.mock import patch

from bson import ObjectId
from pymongo.errors import PyMongoError

import task_worker
from workflow_parser import WorkflowParseError


class WorkerRoutingTest(unittest.TestCase):
    @patch("task_worker.MongoClient")
    def test_binding_lookup_only_queries_enabled_event_type(self, mongo_client):
        bound_id = ObjectId()
        database = mongo_client.return_value.__enter__.return_value.__getitem__.return_value
        database.__getitem__.return_value.find_one.return_value = {"workflow_id": bound_id}

        self.assertEqual(task_worker.read_bound_workflow_id("terminal"), str(bound_id))
        database.__getitem__.return_value.find_one.assert_called_once_with(
            {"event_type": "terminal", "enabled": True}, {"workflow_id": 1}
        )
        database.__getitem__.assert_called_once_with("event_bindings")

    @patch("task_worker.MongoClient")
    def test_unbound_or_disabled_event_does_not_fall_back(self, mongo_client):
        database = mongo_client.return_value.__enter__.return_value.__getitem__.return_value
        database.__getitem__.return_value.find_one.return_value = None

        self.assertIsNone(task_worker.read_bound_workflow_id("terminal"))
        database.__getitem__.assert_called_once_with("event_bindings")

    @patch("task_worker.read_bound_workflow_id", return_value=None)
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.record_history")
    def test_unbound_event_only_records_history(self, record_history, publish, read_bound):
        event = {"event_type": "custom.event", "payload": {"value": 1}}
        task_worker.handle_task(event)
        record_history.assert_called_once_with(event)
        read_bound.assert_called_once_with("custom.event")
        publish.assert_not_called()

    @patch("task_worker.read_bound_workflow_id", return_value="bound-id")
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.record_history")
    def test_bound_event_preserves_payload_but_overwrites_id(self, record_history, publish, read_bound):
        event = {"event_type": "custom.event", "payload": {"value": 1, "workflow_id": "untrusted"}}
        task_worker.handle_task(event)
        publish.assert_called_once_with(task_worker.MAIN_AGENT_QUEUE_NAME, {
            "event_type": "workflow", "payload": {"value": 1, "workflow_id": "bound-id"},
        })
        self.assertEqual(event["payload"]["workflow_id"], "untrusted")

    @patch("task_worker.read_bound_workflow_id")
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.record_history")
    def test_internal_events_are_terminal(self, record_history, publish, read_bound):
        for event_type in ("response", "error"):
            task_worker.handle_task({"event_type": event_type, "payload": {}})
        self.assertEqual(record_history.call_count, 2)
        read_bound.assert_not_called()
        publish.assert_not_called()

    @patch("task_worker.MongoClient")
    def test_binding_lookup_failure_is_not_treated_as_unbound(self, mongo_client):
        database = mongo_client.return_value.__enter__.return_value.__getitem__.return_value
        database.__getitem__.return_value.find_one.side_effect = PyMongoError("unavailable")
        with self.assertRaisesRegex(RuntimeError, "failed to read event binding"):
            task_worker.read_bound_workflow_id("terminal")

    @patch("task_worker._read_workflow")
    @patch("task_worker.validate_workflow")
    @patch("task_worker.parse_workflow")
    @patch("task_worker.propagate_workflow_output")
    @patch("task_worker.run_workflow_map", return_value={"content": "done"})
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.record_history")
    def test_workflow_event_uses_id_and_optionally_exposes_it_as_input(
        self, record_history, publish, run, propagate, parse, validate, read_workflow
    ):
        read_workflow.return_value = {"name": "new workflow"}
        parse.return_value = [{"type": "input", "workflowPorts": [
            {"id": "id-in", "name": "workflow_id"}, {"id": "value-in", "name": "value"},
        ]}]
        task_worker.handle_task({"event_type": "workflow", "payload": {"workflow_id": "selected", "value": 42}})
        read_workflow.assert_called_once_with("selected", by_id=True)
        self.assertEqual(propagate.call_count, 2)
        self.assertEqual(propagate.call_args_list[0].args[3], "selected")
        self.assertEqual(propagate.call_args_list[1].args[3], 42)
        self.assertEqual(publish.call_args.args[1]["event_type"], "response")

    @patch("task_worker._read_workflow", return_value={"name": "workflow"})
    @patch("task_worker.validate_workflow")
    @patch("task_worker.parse_workflow", return_value=[{"type": "input", "workflowPorts": []}])
    @patch("task_worker.propagate_workflow_output")
    @patch("task_worker.run_workflow_map", return_value={"content": "done"})
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.record_history")
    def test_workflow_id_does_not_require_input_port(
        self, record_history, publish, run, propagate, parse, validate, read_workflow
    ):
        task_worker.handle_task({"event_type": "workflow", "payload": {"workflow_id": "selected"}})
        read_workflow.assert_called_once_with("selected", by_id=True)
        propagate.assert_not_called()
        self.assertEqual(publish.call_args.args[1]["event_type"], "response")

    @patch("task_worker._read_workflow", side_effect=WorkflowParseError("workflow not found: deleted"))
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.record_history")
    def test_missing_workflow_publishes_error_once(self, record_history, publish, read_workflow):
        task_worker.handle_task({"event_type": "workflow", "payload": {"workflow_id": "deleted"}})
        publish.assert_called_once_with(task_worker.MAIN_AGENT_QUEUE_NAME, {
            "event_type": "error", "payload": {"workflow_id": "deleted", "message": "workflow not found"},
        })

    @patch("task_worker._read_workflow", side_effect=WorkflowParseError("workflow id invalid: bad"))
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.record_history")
    def test_invalid_workflow_id_is_not_missing_workflow(self, record_history, publish, read_workflow):
        with self.assertRaisesRegex(WorkflowParseError, "workflow id invalid"):
            task_worker.handle_task({"event_type": "workflow", "payload": {"workflow_id": "bad"}})
        publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()