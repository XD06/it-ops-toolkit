import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from it_ops_toolkit.alert_engine import (
    AlertEngineError,
    _compare,
    _extract_metric_value,
    acknowledge_alert,
    evaluate_results,
    load_rules_from_config,
)
from it_ops_toolkit.config import (
    AlertRuleConditionConfig,
    AlertRuleItemConfig,
)
from it_ops_toolkit.models import (
    AlertCondition,
    AlertEvent,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    ProbeResult,
    ProbeStatus,
    Target,
)
from it_ops_toolkit.storage import SQLiteStore
from it_ops_toolkit.tasks import new_task_run


def _make_probe_result(
    *,
    task_id: str,
    probe_type: str = "ping",
    target_value: str = "192.168.1.1",
    status: ProbeStatus = ProbeStatus.success,
    observations: dict | None = None,
) -> ProbeResult:
    return ProbeResult(
        id=f"result-{probe_type}-{target_value}",
        task_id=task_id,
        probe_type=probe_type,
        target=Target(type="ip", value=target_value),
        status=status,
        started_at=datetime.now(UTC),
        ended_at=datetime.now(UTC),
        observations=observations or {},
    )


class CompareTests(unittest.TestCase):
    def test_gt_numeric(self) -> None:
        self.assertTrue(_compare(15, "gt", 10))
        self.assertFalse(_compare(5, "gt", 10))

    def test_lt_numeric(self) -> None:
        self.assertTrue(_compare(5, "lt", 10))
        self.assertFalse(_compare(15, "lt", 10))

    def test_eq_numeric(self) -> None:
        self.assertTrue(_compare(10, "eq", 10))
        self.assertFalse(_compare(11, "eq", 10))

    def test_eq_string(self) -> None:
        self.assertTrue(_compare("failed", "eq", "failed"))
        self.assertFalse(_compare("success", "eq", "failed"))

    def test_ne_string(self) -> None:
        self.assertTrue(_compare("success", "ne", "failed"))
        self.assertFalse(_compare("failed", "ne", "failed"))

    def test_gte_numeric(self) -> None:
        self.assertTrue(_compare(10, "gte", 10))
        self.assertTrue(_compare(11, "gte", 10))
        self.assertFalse(_compare(9, "gte", 10))


class ExtractMetricTests(unittest.TestCase):
    def test_extract_numeric(self) -> None:
        result = _make_probe_result(
            task_id="t1",
            observations={"packet_loss_percent": 15.0},
        )
        self.assertEqual(_extract_metric_value(result, "packet_loss_percent"), 15.0)

    def test_extract_status(self) -> None:
        result = _make_probe_result(
            task_id="t1",
            probe_type="tcp",
            status=ProbeStatus.failed,
        )
        self.assertEqual(_extract_metric_value(result, "status"), "failed")

    def test_extract_missing(self) -> None:
        result = _make_probe_result(task_id="t1", observations={})
        self.assertIsNone(_extract_metric_value(result, "avg_rtt_ms"))


class LoadRulesTests(unittest.TestCase):
    def test_load_rules(self) -> None:
        configs = [
            AlertRuleItemConfig(
                id="ping-loss",
                name="Ping 丢包",
                condition=AlertRuleConditionConfig(
                    probe_type="ping",
                    metric="packet_loss_percent",
                    operator="gt",
                    threshold=10,
                ),
                severity="warning",
                cooldown_minutes=60,
            ),
        ]
        rules = load_rules_from_config(configs)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].id, "ping-loss")
        self.assertEqual(rules[0].severity, AlertSeverity.warning)
        self.assertEqual(rules[0].condition.probe_type, "ping")


class EvaluateResultsTests(unittest.TestCase):
    def _setup_store(self) -> SQLiteStore:
        tmp = tempfile.TemporaryDirectory()
        store = SQLiteStore(Path(tmp.name) / "ops.sqlite")
        store.ensure_schema()
        self._tmp = tmp  # keep alive
        return store

    def test_triggers_alert_when_condition_met(self) -> None:
        store = self._setup_store()
        task = new_task_run(task_type="health_check")
        store.save_task_run(task)

        results = [
            _make_probe_result(
                task_id=task.id,
                target_value="192.168.1.1",
                observations={"packet_loss_percent": 25.0},
            ),
        ]
        rules = [
            AlertRule(
                id="ping-loss",
                name="Ping 丢包率超 10%",
                condition=AlertCondition(
                    probe_type="ping",
                    metric="packet_loss_percent",
                    operator="gt",
                    threshold=10,
                ),
                severity=AlertSeverity.warning,
                cooldown_minutes=60,
            ),
        ]

        events = evaluate_results(
            results=results, rules=rules, task_id=task.id, store=store
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].rule_id, "ping-loss")
        self.assertEqual(events[0].target, "192.168.1.1")
        self.assertEqual(events[0].value, "25.0")
        self.assertEqual(events[0].status, AlertStatus.active)

    def test_no_alert_when_condition_not_met(self) -> None:
        store = self._setup_store()
        task = new_task_run(task_type="health_check")
        store.save_task_run(task)

        results = [
            _make_probe_result(
                task_id=task.id,
                observations={"packet_loss_percent": 5.0},
            ),
        ]
        rules = [
            AlertRule(
                id="ping-loss",
                name="Ping 丢包率超 10%",
                condition=AlertCondition(
                    probe_type="ping",
                    metric="packet_loss_percent",
                    operator="gt",
                    threshold=10,
                ),
                severity=AlertSeverity.warning,
                cooldown_minutes=60,
            ),
        ]

        events = evaluate_results(
            results=results, rules=rules, task_id=task.id, store=store
        )
        self.assertEqual(len(events), 0)

    def test_cooldown_suppresses_duplicate(self) -> None:
        store = self._setup_store()
        task = new_task_run(task_type="health_check")
        store.save_task_run(task)

        rules = [
            AlertRule(
                id="ping-loss",
                name="Ping 丢包率超 10%",
                condition=AlertCondition(
                    probe_type="ping",
                    metric="packet_loss_percent",
                    operator="gt",
                    threshold=10,
                ),
                severity=AlertSeverity.warning,
                cooldown_minutes=60,
            ),
        ]

        results = [
            _make_probe_result(
                task_id=task.id,
                target_value="192.168.1.1",
                observations={"packet_loss_percent": 25.0},
            ),
        ]

        # 第一次触发
        events1 = evaluate_results(
            results=results, rules=rules, task_id=task.id, store=store
        )
        self.assertEqual(len(events1), 1)

        # 第二次应被冷却抑制
        events2 = evaluate_results(
            results=results, rules=rules, task_id=task.id, store=store
        )
        self.assertEqual(len(events2), 0)

    def test_cooldown_expires_allows_new_alert(self) -> None:
        store = self._setup_store()
        task = new_task_run(task_type="health_check")
        store.save_task_run(task)

        rules = [
            AlertRule(
                id="ping-loss",
                name="Ping 丢包率超 10%",
                condition=AlertCondition(
                    probe_type="ping",
                    metric="packet_loss_percent",
                    operator="gt",
                    threshold=10,
                ),
                severity=AlertSeverity.warning,
                cooldown_minutes=60,
            ),
        ]

        results = [
            _make_probe_result(
                task_id=task.id,
                target_value="192.168.1.1",
                observations={"packet_loss_percent": 25.0},
            ),
        ]

        # 第一次触发
        events1 = evaluate_results(
            results=results, rules=rules, task_id=task.id, store=store
        )
        self.assertEqual(len(events1), 1)

        # 模拟冷却期过后
        past_time = datetime.now(UTC) - timedelta(hours=2)
        # 手动修改已有告警的触发时间
        existing = store.find_active_alert("ping-loss", "192.168.1.1")
        assert existing is not None
        old_event = existing.model_copy(update={"triggered_at": past_time})
        store.save_alert_event(old_event)

        # 第二次应该可以触发新告警
        events2 = evaluate_results(
            results=results, rules=rules, task_id=task.id, store=store
        )
        self.assertEqual(len(events2), 1)

    def test_resolution_when_condition_no_longer_met(self) -> None:
        store = self._setup_store()
        task = new_task_run(task_type="health_check")
        store.save_task_run(task)

        rules = [
            AlertRule(
                id="ping-loss",
                name="Ping 丢包率超 10%",
                condition=AlertCondition(
                    probe_type="ping",
                    metric="packet_loss_percent",
                    operator="gt",
                    threshold=10,
                ),
                severity=AlertSeverity.warning,
                cooldown_minutes=60,
            ),
        ]

        # 第一次：触发告警
        bad_results = [
            _make_probe_result(
                task_id=task.id,
                target_value="192.168.1.1",
                observations={"packet_loss_percent": 25.0},
            ),
        ]
        events1 = evaluate_results(
            results=bad_results, rules=rules, task_id=task.id, store=store
        )
        self.assertEqual(len(events1), 1)

        # 第二次：恢复正常
        good_results = [
            _make_probe_result(
                task_id=task.id,
                target_value="192.168.1.1",
                observations={"packet_loss_percent": 0.0},
            ),
        ]
        events2 = evaluate_results(
            results=good_results, rules=rules, task_id=task.id, store=store
        )
        self.assertEqual(len(events2), 0)

        # 检查原告警是否被标记为 resolved
        active = store.list_alert_events(status="active")
        self.assertEqual(len(active), 0)
        resolved = store.list_alert_events(status="resolved")
        self.assertEqual(len(resolved), 1)

    def test_disabled_rule_ignored(self) -> None:
        store = self._setup_store()
        task = new_task_run(task_type="health_check")
        store.save_task_run(task)

        results = [
            _make_probe_result(
                task_id=task.id,
                observations={"packet_loss_percent": 25.0},
            ),
        ]
        rules = [
            AlertRule(
                id="ping-loss",
                name="Ping 丢包率超 10%",
                enabled=False,
                condition=AlertCondition(
                    probe_type="ping",
                    metric="packet_loss_percent",
                    operator="gt",
                    threshold=10,
                ),
                severity=AlertSeverity.warning,
                cooldown_minutes=60,
            ),
        ]

        events = evaluate_results(
            results=results, rules=rules, task_id=task.id, store=store
        )
        self.assertEqual(len(events), 0)


class AcknowledgeTests(unittest.TestCase):
    def test_acknowledge_alert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            store.ensure_schema()

            event = AlertEvent(
                id="alert-test",
                rule_id="rule-1",
                rule_name="Test Rule",
                severity=AlertSeverity.warning,
                target="192.168.1.1",
                probe_type="ping",
                metric="packet_loss_percent",
                value="25",
                threshold="10",
                task_id="task-1",
                triggered_at=datetime.now(UTC),
            )
            store.save_alert_event(event)

            acknowledged = acknowledge_alert(event_id="alert-test", store=store)
            self.assertTrue(acknowledged.acknowledged)
            self.assertIsNotNone(acknowledged.acknowledged_at)

    def test_acknowledge_nonexistent_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            store.ensure_schema()

            with self.assertRaises(AlertEngineError):
                acknowledge_alert(event_id="nonexistent", store=store)


if __name__ == "__main__":
    unittest.main()
