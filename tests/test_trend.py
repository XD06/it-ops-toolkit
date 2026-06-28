import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from it_ops_toolkit.models import ProbeResult, ProbeStatus, Target
from it_ops_toolkit.storage import SQLiteStore
from it_ops_toolkit.tasks import new_task_run
from it_ops_toolkit.trend import (
    PROBE_METRICS,
    TrendError,
    get_trend,
    get_trend_summary,
    list_available_targets,
)


def _make_probe_result(
    *,
    task_id: str,
    probe_type: str = "ping",
    target_value: str = "192.168.1.1",
    status: ProbeStatus = ProbeStatus.success,
    observations: dict | None = None,
    started_at: datetime | None = None,
    seq: int = 0,
) -> ProbeResult:
    return ProbeResult(
        id=f"result-{probe_type}-{target_value}-{seq}-{started_at.isoformat() if started_at else 'now'}",
        task_id=task_id,
        probe_type=probe_type,
        target=Target(type="ip", value=target_value),
        status=status,
        started_at=started_at or datetime.now(UTC),
        ended_at=started_at or datetime.now(UTC),
        observations=observations or {},
    )


class TrendSetup:
    """共享的测试数据准备。"""

    def _setup_store_with_data(self) -> SQLiteStore:
        tmp = tempfile.TemporaryDirectory()
        self._tmp = tmp  # keep alive
        store = SQLiteStore(Path(tmp.name) / "ops.sqlite")
        store.ensure_schema()

        task = new_task_run(task_type="health_check")
        store.save_task_run(task)

        now = datetime.now(UTC)
        # 3 天的数据，每天 2 条 ping 结果
        seq = 0
        for days_ago in range(3):
            day = now - timedelta(days=days_ago)
            for i in range(2):
                rtt = 5.0 + i * 2 + days_ago * 1.5
                result = _make_probe_result(
                    task_id=task.id,
                    probe_type="ping",
                    target_value="192.168.1.1",
                    status=ProbeStatus.success,
                    observations={
                        "avg_rtt_ms": rtt,
                        "min_rtt_ms": rtt - 1,
                        "max_rtt_ms": rtt + 2,
                        "packet_loss_percent": 0.0 if i == 0 else 5.0,
                    },
                    started_at=day,
                    seq=seq,
                )
                store.save_probe_result(result)
                seq += 1

            # 1 条失败结果
            failed_result = _make_probe_result(
                task_id=task.id,
                probe_type="ping",
                target_value="192.168.1.1",
                status=ProbeStatus.failed,
                observations={"avg_rtt_ms": 0, "min_rtt_ms": 0, "max_rtt_ms": 0, "packet_loss_percent": 100.0},
                started_at=day,
                seq=seq,
            )
            store.save_probe_result(failed_result)
            seq += 1

        # 添加一些 TCP 数据
        for days_ago in range(2):
            day = now - timedelta(days=days_ago)
            result = _make_probe_result(
                task_id=task.id,
                probe_type="tcp",
                target_value="192.168.1.2",
                status=ProbeStatus.success,
                observations={"duration_ms": 10.0 + days_ago * 2, "port": 80, "open": True},
                started_at=day,
                seq=seq,
            )
            store.save_probe_result(result)
            seq += 1

        return store


class GetTrendTests(TrendSetup, unittest.TestCase):
    def test_get_trend_basic(self) -> None:
        store = self._setup_store_with_data()
        trend = get_trend(store=store, probe_type="ping", days=7, granularity="daily")

        self.assertEqual(trend["probe_type"], "ping")
        self.assertEqual(trend["days"], 7)
        self.assertEqual(trend["granularity"], "daily")
        self.assertIsNotNone(trend["status_distribution"])
        self.assertGreater(trend["status_distribution"]["total"], 0)

    def test_get_trend_with_target(self) -> None:
        store = self._setup_store_with_data()
        trend = get_trend(
            store=store,
            probe_type="ping",
            target="192.168.1.1",
            days=7,
        )
        self.assertEqual(trend["target"], "192.168.1.1")
        self.assertGreater(trend["status_distribution"]["total"], 0)

    def test_get_trend_with_metric(self) -> None:
        store = self._setup_store_with_data()
        trend = get_trend(
            store=store,
            probe_type="ping",
            metric="avg_rtt_ms",
            days=7,
        )
        self.assertIn("avg_rtt_ms", trend["metric_stats"])
        stats = trend["metric_stats"]["avg_rtt_ms"]
        self.assertGreater(len(stats), 0)
        # Check that stats have required fields
        for s in stats:
            self.assertIn("time_bucket", s)
            self.assertIn("count", s)
            self.assertIn("avg", s)
            self.assertIn("min", s)
            self.assertIn("max", s)
            self.assertIn("p95", s)

    def test_get_trend_all_metrics(self) -> None:
        store = self._setup_store_with_data()
        trend = get_trend(store=store, probe_type="ping", days=7)
        # Should have all ping metrics that have data
        self.assertIn("avg_rtt_ms", trend["metric_stats"])
        self.assertIn("packet_loss_percent", trend["metric_stats"])

    def test_get_trend_invalid_probe_type(self) -> None:
        store = self._setup_store_with_data()
        with self.assertRaises(TrendError):
            get_trend(store=store, probe_type="invalid", days=7)

    def test_get_trend_invalid_granularity(self) -> None:
        store = self._setup_store_with_data()
        with self.assertRaises(TrendError):
            get_trend(store=store, probe_type="ping", days=7, granularity="weekly")

    def test_get_trend_invalid_days(self) -> None:
        store = self._setup_store_with_data()
        with self.assertRaises(TrendError):
            get_trend(store=store, probe_type="ping", days=0)
        with self.assertRaises(TrendError):
            get_trend(store=store, probe_type="ping", days=400)

    def test_get_trend_hourly(self) -> None:
        store = self._setup_store_with_data()
        trend = get_trend(
            store=store,
            probe_type="ping",
            metric="avg_rtt_ms",
            days=1,
            granularity="hourly",
        )
        self.assertEqual(trend["granularity"], "hourly")

    def test_status_distribution(self) -> None:
        store = self._setup_store_with_data()
        trend = get_trend(store=store, probe_type="ping", days=7)
        dist = trend["status_distribution"]

        self.assertGreater(dist["total"], 0)
        self.assertGreater(dist["success_count"], 0)
        self.assertGreater(dist["failed_count"], 0)
        self.assertGreaterEqual(dist["success_rate"], 0)
        self.assertLessEqual(dist["success_rate"], 100)


class GetTrendSummaryTests(TrendSetup, unittest.TestCase):
    def test_summary_basic(self) -> None:
        store = self._setup_store_with_data()
        summary = get_trend_summary(
            store=store, probe_type="ping", target="192.168.1.1", days=7
        )

        self.assertEqual(summary["probe_type"], "ping")
        self.assertGreater(summary["total_checks"], 0)
        self.assertGreaterEqual(summary["success_rate"], 0)
        self.assertIn("avg_rtt_ms", summary["metrics"])
        self.assertGreater(summary["metrics"]["avg_rtt_ms"]["data_points"], 0)

    def test_summary_no_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            store.ensure_schema()

            summary = get_trend_summary(
                store=store, probe_type="ping", days=7
            )
            self.assertEqual(summary["total_checks"], 0)
            self.assertEqual(summary["success_rate"], 0)
            self.assertEqual(len(summary["metrics"]), 0)


class ListAvailableTargetsTests(TrendSetup, unittest.TestCase):
    def test_list_all_targets(self) -> None:
        store = self._setup_store_with_data()
        targets = list_available_targets(store=store)

        # Should have ping and tcp targets
        probe_types = {t["probe_type"] for t in targets}
        self.assertIn("ping", probe_types)
        self.assertIn("tcp", probe_types)

    def test_list_targets_filtered(self) -> None:
        store = self._setup_store_with_data()
        targets = list_available_targets(store=store, probe_type="tcp")

        for t in targets:
            self.assertEqual(t["probe_type"], "tcp")

    def test_list_targets_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            store.ensure_schema()

            targets = list_available_targets(store=store)
            self.assertEqual(len(targets), 0)


class StorageTrendMethodsTests(TrendSetup, unittest.TestCase):
    def test_list_probe_results_between(self) -> None:
        store = self._setup_store_with_data()
        now = datetime.now(UTC)
        start = (now - timedelta(days=7)).isoformat()
        end = now.isoformat()

        results = store.list_probe_results_between(
            start=start, end=end, probe_type="ping"
        )
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertEqual(r.probe_type, "ping")

    def test_list_probe_results_between_with_target(self) -> None:
        store = self._setup_store_with_data()
        now = datetime.now(UTC)
        start = (now - timedelta(days=7)).isoformat()
        end = now.isoformat()

        results = store.list_probe_results_between(
            start=start, end=end, probe_type="ping", target="192.168.1.1"
        )
        self.assertGreater(len(results), 0)

    def test_get_probe_stats(self) -> None:
        store = self._setup_store_with_data()
        now = datetime.now(UTC)
        start = (now - timedelta(days=7)).isoformat()
        end = now.isoformat()

        stats = store.get_probe_stats(
            probe_type="ping",
            target="192.168.1.1",
            metric="avg_rtt_ms",
            start=start,
            end=end,
            granularity="daily",
        )
        self.assertGreater(len(stats), 0)
        for s in stats:
            self.assertGreater(s["count"], 0)
            self.assertIsNotNone(s["avg"])

    def test_get_status_distribution(self) -> None:
        store = self._setup_store_with_data()
        now = datetime.now(UTC)
        start = (now - timedelta(days=7)).isoformat()
        end = now.isoformat()

        dist = store.get_status_distribution(
            probe_type="ping",
            target="192.168.1.1",
            start=start,
            end=end,
        )
        self.assertGreater(dist["total"], 0)
        self.assertGreater(dist["success_count"], 0)
        self.assertGreater(dist["failed_count"], 0)


if __name__ == "__main__":
    unittest.main()
