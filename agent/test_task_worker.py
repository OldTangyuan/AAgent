import os
import unittest
from unittest.mock import patch

from bson import ObjectId

os.environ.setdefault("QQ_TARGET_USER_ID", "test-user")
os.environ.setdefault("QQ_BOT_ID", "test-bot")

import task_worker


class WorkerRoutingTest(unittest.TestCase):
    @patch("task_worker.MongoClient")
    def test_terminal_binding_takes_precedence_over_active_workflow(self, mongo_client):
        bound_id = ObjectId()
        database = mongo_client.return_value.__enter__.return_value.__getitem__.return_value
        database.__getitem__.return_value.find_one.side_effect = [
            {"workflow_id": bound_id},
        ]

        self.assertEqual(task_worker.read_active_workflow_id("terminal"), str(bound_id))
        database.__getitem__.return_value.find_one.assert_called_once_with(
            {"event_type": "terminal", "enabled": True}, {"workflow_id": 1}
        )

    @patch("task_worker.MongoClient")
    def test_unbound_event_uses_active_workflow(self, mongo_client):
        active_id = ObjectId()
        database = mongo_client.return_value.__enter__.return_value.__getitem__.return_value
        database.__getitem__.return_value.find_one.side_effect = [
            None,
            {"workflow_id": active_id},
        ]

        self.assertEqual(task_worker.read_active_workflow_id("terminal"), str(active_id))

    @patch("task_worker.MongoClient")
    @patch("task_worker._read_workflow")
    @patch("task_worker.validate_workflow")
    @patch("task_worker.parse_workflow")
    @patch("task_worker.propagate_workflow_output")
    @patch("task_worker.run_workflow_map", return_value={"content": "done"})
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.record_history")
    def test_terminal_message_executes_its_bound_workflow(
        self, record_history, publish, run, propagate, parse, validate, read_workflow, mongo_client
    ):
        bound_id = ObjectId()
        database = mongo_client.return_value.__enter__.return_value.__getitem__.return_value
        database.__getitem__.return_value.find_one.return_value = {"workflow_id": bound_id}
        read_workflow.return_value = {"name": "new workflow"}
        parse.return_value = [{"type": "input", "workflowPorts": [{"id": "in", "name": "content"}]}]
        task_worker.handle_task({"event_type": "terminal", "payload": {"content": "hello"}})
        workflow_event = publish.call_args.args[1]
        self.assertEqual(workflow_event["payload"]["source"], "terminal")
        task_worker.handle_task(workflow_event)
        database.__getitem__.return_value.find_one.assert_called_once_with(
            {"event_type": "terminal", "enabled": True}, {"workflow_id": 1}
        )
        read_workflow.assert_called_once_with(str(bound_id), by_id=True)


if __name__ == "__main__":
    unittest.main()