import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from it_ops_toolkit.config import OpsConfig, ScheduleItemConfig
from it_ops_toolkit.models import (
    AlertSeverity,
    ScheduledTask,
    ScheduledTaskStatus,
)
from it_ops_toolkit.scheduler import (
    CronExpression,
    SchedulerEngine,
    SchedulerError,
    create_scheduled_task,
)
from it_ops_toolkit.storage import SQLiteStore


class CronExpressionTests(unittest.TestCase):
    def test_basic_match(self) -> None:
        cron = CronExpression("0 8 * * *")
        # 8:00 every day
        dt = datetime(2026, 6, 27, 8, 0, tzinfo=UTC)
        self.assertTrue(cron.matches(dt))

    def test_no_match_wrong_hour(self) -> None:
        cron = CronExpression("0 8 * * *")
        dt = datetime(2026, 6, 27, 9, 0, tzinfo=UTC)
        self.assertFalse(cron.matches(dt))

    def test_wildcard_matches_all(self) -> None:
        cron = CronExpression("* * * * *")
        dt = datetime(2026, 6, 27, 14, 30, tzinfo=UTC)
        self.assertTrue(cron.matches(dt))

    def test_step_expression(self) -> None:
        cron = CronExpression("*/15 * * * *")
        self.assertTrue(cron.matches(datetime(2026, 6, 27, 10, 0, tzinfo=UTC)))
        self.assertTrue(cron.matches(datetime(2026, 6, 27, 10, 15, tzinfo=UTC)))
        self.assertTrue(cron.matches(datetime(2026, 6, 27, 10, 30, tzinfo=UTC)))
        self.assertFalse(cron.matches(datetime(2026, 6, 27, 10, 7, tzinfo=UTC)))

    def test_comma_list(self) -> None:
        cron = CronExpression("0 8,18 * * *")
        self.assertTrue(cron.matches(datetime(2026, 6, 27, 8, 0, tzinfo=UTC)))
        self.assertTrue(cron.matches(datetime(2026, 6, 27, 18, 0, tzinfo=UTC)))
        self.assertFalse(cron.matches(datetime(2026, 6, 27, 12, 0, tzinfo=UTC)))

    def test_weekday_match(self) -> None:
        # Monday (weekday=0 in Python)
        cron = CronExpression("0 9 * * 1")
        monday = datetime(2026, 6, 29, 9, 0, tzinfo=UTC)  # 2026-06-29 is Monday
        self.assertTrue(cron.matches(monday))
        tuesday = datetime(2026, 6, 30, 9, 0, tzinfo=UTC)
        self.assertFalse(cron.matches(tuesday))

    def test_invalid_expression_raises(self) -> None:
        with self.assertRaises(SchedulerError):
            CronExpression("invalid")
        with self.assertRaises(SchedulerError):
            CronExpression("0 8 * *")  # only 4 fields

    def test_next_run_after(self) -> None:
        cron = CronExpression("0 8 * * *")
        after = datetime(2026, 6, 27, 10, 0, tzinfo=UTC)
        next_run = cron.next_run_after(after)
        self.assertEqual(next_run.hour, 8)
        self.assertEqual(next_run.minute, 0)
        # Should be the next day
        self.assertEqual(next_run.day, 28)

    def test_range_expression(self) -> None:
        cron = CronExpression("0 9-17 * * *")
        self.assertTrue(cron.matches(datetime(2026, 6, 27, 9, 0, tzinfo=UTC)))
        self.assertTrue(cron.matches(datetime(2026, 6, 27, 17, 0, tzinfo=UTC)))
        self.assertFalse(cron.matches(datetime(2026, 6, 27, 8, 0, tzinfo=UTC)))
        self.assertFalse(cron.matches(datetime(2026, 6, 27, 18, 0, tzinfo=UTC)))


class CreateScheduledTaskTests(unittest.TestCase):
    def test_create_task(self) -> None:
        task = create_scheduled_task(
            name="test-task",
            task_type="health_check",
            profile="default",
            cron="0 8 * * *",
        )
        self.assertEqual(task.name, "test-task")
        self.assertEqual(task.task_type, "health_check")
        self.assertTrue(task.enabled)
        self.assertIsNotNone(task.next_run)
        self.assertIn(AlertSeverity.warning, task.alert_on)
        self.assertIn(AlertSeverity.critical, task.alert_on)

    def test_create_task_invalid_cron(self) -> None:
        with self.assertRaises(SchedulerError):
            create_scheduled_task(
                name="bad",
                task_type="health_check",
                profile="default",
                cron="invalid",
            )


class SchedulerEngineTests(unittest.TestCase):
    def _make_engine(self) -> tuple[SchedulerEngine, SQLiteStore, tempfile.TemporaryDirectory]:
        tmp = tempfile.TemporaryDirectory()
        store = SQLiteStore(Path(tmp.name) / "ops.sqlite")
        store.ensure_schema()
        config = OpsConfig()
        engine = SchedulerEngine(config=config, store=store)
        return engine, store, tmp

    def test_load_tasks_from_empty_config(self) -> None:
        engine, store, tmp = self._make_engine()
        tasks = engine.list_tasks()
        self.assertEqual(len(tasks), 0)
        tmp.cleanup()

    def test_load_tasks_from_config(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        store = SQLiteStore(Path(tmp.name) / "ops.sqlite")
        store.ensure_schema()
        config = OpsConfig(
            schedules=[
                ScheduleItemConfig(
                    name="每日巡检",
                    task_type="health_check",
                    profile="daily_basic",
                    cron="0 8 * * *",
                ),
            ]
        )
        engine = SchedulerEngine(config=config, store=store)
        tasks = engine.list_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].name, "每日巡检")
        self.assertIsNotNone(tasks[0].next_run)
        tmp.cleanup()

    def test_add_and_remove_task(self) -> None:
        engine, store, tmp = self._make_engine()
        task = create_scheduled_task(
            name="new-task",
            task_type="security_check",
            profile="default",
            cron="0 6 * * *",
        )
        engine.add_task(task)
        self.assertEqual(len(engine.list_tasks()), 1)

        removed = engine.remove_task(task.id)
        self.assertTrue(removed)
        self.assertEqual(len(engine.list_tasks()), 0)
        tmp.cleanup()

    def test_enable_disable_task(self) -> None:
        engine, store, tmp = self._make_engine()
        task = create_scheduled_task(
            name="toggle-task",
            task_type="health_check",
            profile="default",
            cron="0 8 * * *",
        )
        engine.add_task(task)

        disabled = engine.disable_task(task.id)
        self.assertIsNotNone(disabled)
        self.assertFalse(disabled.enabled)

        enabled = engine.enable_task(task.id)
        self.assertIsNotNone(enabled)
        self.assertTrue(enabled.enabled)
        tmp.cleanup()

    def test_persistence_after_restart(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        store_path = Path(tmp.name) / "ops.sqlite"
        store = SQLiteStore(store_path)
        store.ensure_schema()
        config = OpsConfig(
            schedules=[
                ScheduleItemConfig(
                    name="持久化测试",
                    task_type="health_check",
                    profile="default",
                    cron="0 8 * * *",
                ),
            ]
        )
        engine1 = SchedulerEngine(config=config, store=store)
        tasks1 = engine1.list_tasks()
        self.assertEqual(len(tasks1), 1)

        # 模拟重启：新引擎实例
        store2 = SQLiteStore(store_path)
        engine2 = SchedulerEngine(config=config, store=store2)
        tasks2 = engine2.list_tasks()
        self.assertEqual(len(tasks2), 1)
        self.assertEqual(tasks2[0].name, "持久化测试")
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
