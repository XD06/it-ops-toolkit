import tempfile
import unittest
from pathlib import Path

from it_ops_toolkit.models import TaskStatus
from it_ops_toolkit.storage import SQLiteStore, TaskRecordNotFound
from it_ops_toolkit.tasks import new_task_run


class StorageTests(unittest.TestCase):
    def test_save_list_and_get_task_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            task = new_task_run(task_type="health_check", status=TaskStatus.success)

            store.save_task_run(task)

            tasks = store.list_task_runs()
            loaded = store.get_task_run(task.id)

            self.assertEqual(len(tasks), 1)
            self.assertEqual(loaded.id, task.id)
            self.assertEqual(loaded.task_type, "health_check")
            self.assertEqual(loaded.status, TaskStatus.success)

    def test_missing_task_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")

            with self.assertRaises(TaskRecordNotFound):
                store.get_task_run("task-missing")


if __name__ == "__main__":
    unittest.main()

