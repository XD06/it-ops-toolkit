import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from it_ops_toolkit.ai_copilot import (
    AIAdapterError,
    OpenAIAdapter,
    OllamaAdapter,
    TemplateAdapter,
    create_adapter,
    explain_anomaly,
    sanitize_ai_input,
    summarize_recent,
    summarize_task,
)
from it_ops_toolkit.config import AIConfig, OpsConfig, load_config
from it_ops_toolkit.models import (
    AIInput,
    AIOutput,
    Finding,
    ProbeResult,
    ProbeStatus,
    Severity,
    Target,
    TaskRun,
    TaskStatus,
)
from it_ops_toolkit.storage import SQLiteStore
from it_ops_toolkit.tasks import new_task_run


def _make_task(store: SQLiteStore, *, task_type: str = "health_check") -> TaskRun:
    task = new_task_run(task_type=task_type)
    store.save_task_run(task)
    return task


def _make_probe_result(
    *,
    task_id: str,
    probe_type: str = "ping",
    target_value: str = "192.168.1.1",
    status: ProbeStatus = ProbeStatus.success,
    observations: dict | None = None,
    seq: int = 0,
) -> ProbeResult:
    return ProbeResult(
        id=f"result-{task_id}-{probe_type}-{seq}",
        task_id=task_id,
        probe_type=probe_type,
        target=Target(type="ip", value=target_value),
        status=status,
        started_at=datetime.now(UTC),
        ended_at=datetime.now(UTC),
        observations=observations or {},
    )


def _make_finding(
    *,
    task_id: str,
    severity: Severity = Severity.high,
    title: str = "高风险端口开放",
    description: str = "检测到 445 端口开放",
    recommendation: str = "建议在防火墙限制 445 端口访问来源",
    seq: int = 0,
) -> Finding:
    return Finding(
        id=f"finding-{task_id}-{seq}",
        task_id=task_id,
        category="security",
        severity=severity,
        title=title,
        description=description,
        recommendation=recommendation,
        evidence_refs=[f"result-{task_id}-tcp-{seq}"],
    )


def _setup_store_with_data() -> tuple[SQLiteStore, TaskRun, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    store = SQLiteStore(Path(tmp.name) / "ops.sqlite")
    store.ensure_schema()

    task = _make_task(store)

    # 正常 ping 结果
    r1 = _make_probe_result(
        task_id=task.id,
        probe_type="ping",
        target_value="192.168.1.1",
        status=ProbeStatus.success,
        observations={"avg_rtt_ms": 5.0, "min_rtt_ms": 4.0, "max_rtt_ms": 8.0, "packet_loss_percent": 0.0},
        seq=0,
    )
    store.save_probe_result(r1)

    # 失败 ping 结果
    r2 = _make_probe_result(
        task_id=task.id,
        probe_type="ping",
        target_value="10.0.0.99",
        status=ProbeStatus.failed,
        observations={"avg_rtt_ms": 0, "min_rtt_ms": 0, "max_rtt_ms": 0, "packet_loss_percent": 100.0},
        seq=1,
    )
    store.save_probe_result(r2)

    # TCP 结果
    r3 = _make_probe_result(
        task_id=task.id,
        probe_type="tcp",
        target_value="192.168.1.50",
        status=ProbeStatus.success,
        observations={"port": 445, "open": True},
        seq=2,
    )
    store.save_probe_result(r3)

    # Finding
    f1 = _make_finding(task_id=task.id, seq=0)
    store.save_finding(f1)

    return store, task, tmp


# ---------------------------------------------------------------------------
# 脱敏处理测试
# ---------------------------------------------------------------------------


class SanitizeAIInputTests(unittest.TestCase):
    def test_removes_password_fields(self) -> None:
        data = {"host": "192.168.1.1", "password": "secret123", "name": "server"}
        result = sanitize_ai_input(data)
        self.assertEqual(result["password"], "***")
        self.assertEqual(result["host"], "192.168.1.1")

    def test_removes_token_fields(self) -> None:
        data = {"api_key": "abc123", "token": "xyz", "data": "ok"}
        result = sanitize_ai_input(data)
        self.assertEqual(result["api_key"], "***")
        self.assertEqual(result["token"], "***")

    def test_recursive_sanitization(self) -> None:
        data = {"outer": {"inner": {"secret": "hidden", "ok": "visible"}}}
        result = sanitize_ai_input(data)
        self.assertEqual(result["outer"]["inner"]["secret"], "***")
        self.assertEqual(result["outer"]["inner"]["ok"], "visible")

    def test_sanitizes_list_items(self) -> None:
        data = [{"password": "a"}, {"name": "ok"}]
        result = sanitize_ai_input(data)
        self.assertEqual(result[0]["password"], "***")
        self.assertEqual(result[1]["name"], "ok")

    def test_sanitizes_url_credentials(self) -> None:
        data = {"url": "http://user:pass@proxy.local:8080"}
        result = sanitize_ai_input(data)
        self.assertNotIn("user:pass", result["url"])
        self.assertIn("***:***", result["url"])

    def test_sanitizes_proxy_dict(self) -> None:
        data = {"proxy": {"host": "proxy.local", "username": "admin", "password": "pass"}}
        result = sanitize_ai_input(data)
        self.assertEqual(result["proxy"]["username"], "***")
        self.assertEqual(result["proxy"]["password"], "***")
        self.assertEqual(result["proxy"]["host"], "proxy.local")

    def test_preserves_non_sensitive_data(self) -> None:
        data = {"host": "192.168.1.1", "port": 80, "timeout": 30}
        result = sanitize_ai_input(data)
        self.assertEqual(result, data)


# ---------------------------------------------------------------------------
# TemplateAdapter 测试
# ---------------------------------------------------------------------------


class TemplateAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = TemplateAdapter()
        store, task, tmp = _setup_store_with_data()
        self.store = store
        self.task = task
        self.tmp = tmp

        results = store.list_probe_results_for_task(task.id)
        findings = store.list_findings(task.id)
        self.ai_input = AIInput(task=task, results=results, findings=findings)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_generates_output(self) -> None:
        output = self.adapter.generate(self.ai_input)
        self.assertIsInstance(output, AIOutput)
        self.assertTrue(output.summary)
        self.assertEqual(output.backend, "template")

    def test_facts_from_results(self) -> None:
        output = self.adapter.generate(self.ai_input)
        self.assertGreater(len(output.facts), 0)
        # Facts should contain probe result info
        facts_text = " ".join(output.facts)
        self.assertIn("192.168.1.1", facts_text)

    def test_facts_from_findings(self) -> None:
        output = self.adapter.generate(self.ai_input)
        facts_text = " ".join(output.facts)
        self.assertIn("高风险端口开放", facts_text)

    def test_no_inferences(self) -> None:
        output = self.adapter.generate(self.ai_input)
        # Template adapter does not make inferences
        self.assertEqual(len(output.inferences), 0)

    def test_recommendations_from_findings(self) -> None:
        output = self.adapter.generate(self.ai_input)
        self.assertGreater(len(output.recommendations), 0)
        self.assertIn("445", output.recommendations[0])

    def test_needs_human_review_with_failures(self) -> None:
        output = self.adapter.generate(self.ai_input)
        self.assertTrue(output.needs_human_review)

    def test_needs_human_review_no_failures(self) -> None:
        # All success
        r = _make_probe_result(
            task_id=self.task.id,
            status=ProbeStatus.success,
            observations={"avg_rtt_ms": 5.0, "packet_loss_percent": 0.0},
            seq=99,
        )
        ai_input = AIInput(task=self.task, results=[r], findings=[])
        output = self.adapter.generate(ai_input)
        self.assertFalse(output.needs_human_review)

    def test_confidence_is_1(self) -> None:
        output = self.adapter.generate(self.ai_input)
        self.assertEqual(output.confidence, 1.0)

    def test_sources_contain_result_ids(self) -> None:
        output = self.adapter.generate(self.ai_input)
        self.assertGreater(len(output.sources), 0)

    def test_ping_fact_format(self) -> None:
        r = _make_probe_result(
            task_id=self.task.id,
            probe_type="ping",
            target_value="8.8.8.8",
            status=ProbeStatus.success,
            observations={"avg_rtt_ms": 12.5, "packet_loss_percent": 0.0},
            seq=100,
        )
        ai_input = AIInput(task=self.task, results=[r], findings=[])
        output = self.adapter.generate(ai_input)
        self.assertTrue(any("12.5" in f for f in output.facts))

    def test_dns_fact_format(self) -> None:
        r = _make_probe_result(
            task_id=self.task.id,
            probe_type="dns",
            target_value="www.example.com",
            status=ProbeStatus.success,
            observations={"duration_ms": 15, "resolved_addresses": ["93.184.216.34"]},
            seq=101,
        )
        ai_input = AIInput(task=self.task, results=[r], findings=[])
        output = self.adapter.generate(ai_input)
        self.assertTrue(any("DNS" in f and "www.example.com" in f for f in output.facts))

    def test_tcp_fact_format(self) -> None:
        r = _make_probe_result(
            task_id=self.task.id,
            probe_type="tcp",
            target_value="192.168.1.10",
            status=ProbeStatus.success,
            observations={"port": 443, "open": True},
            seq=102,
        )
        ai_input = AIInput(task=self.task, results=[r], findings=[])
        output = self.adapter.generate(ai_input)
        self.assertTrue(any("TCP" in f and "443" in f for f in output.facts))

    def test_empty_results(self) -> None:
        ai_input = AIInput(task=self.task, results=[], findings=[])
        output = self.adapter.generate(ai_input)
        self.assertIn("无探测结果", output.summary)


# ---------------------------------------------------------------------------
# 适配器工厂测试
# ---------------------------------------------------------------------------


class CreateAdapterTests(unittest.TestCase):
    def test_template_backend(self) -> None:
        config = AIConfig(backend="template")
        adapter = create_adapter(config)
        self.assertIsInstance(adapter, TemplateAdapter)

    def test_openai_backend_no_key_raises(self) -> None:
        from it_ops_toolkit.config import OpenAIConfig
        config = AIConfig(backend="openai", openai=OpenAIConfig(api_key=""))
        with self.assertRaises(AIAdapterError):
            create_adapter(config)

    def test_ollama_backend(self) -> None:
        config = AIConfig(backend="ollama")
        adapter = create_adapter(config)
        self.assertIsInstance(adapter, OllamaAdapter)


# ---------------------------------------------------------------------------
# 领域服务测试
# ---------------------------------------------------------------------------


class SummarizeTaskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store, self.task, self.tmp = _setup_store_with_data()
        self.config = OpsConfig()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_summarize_task(self) -> None:
        output = summarize_task(
            task_id=self.task.id,
            store=self.store,
            config=self.config,
        )
        self.assertIsInstance(output, AIOutput)
        self.assertTrue(output.summary)
        self.assertGreater(len(output.facts), 0)
        self.assertEqual(output.backend, "template")

    def test_summarize_task_not_found(self) -> None:
        with self.assertRaises(AIAdapterError):
            summarize_task(
                task_id="nonexistent",
                store=self.store,
                config=self.config,
            )

    def test_summarize_logs_audit(self) -> None:
        summarize_task(
            task_id=self.task.id,
            store=self.store,
            config=self.config,
        )
        logs = self.store.list_ai_call_logs(task_id=self.task.id)
        self.assertEqual(len(logs), 1)
        self.assertTrue(logs[0].success)
        self.assertEqual(logs[0].backend, "template")


class SummarizeRecentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store, self.task, self.tmp = _setup_store_with_data()
        self.config = OpsConfig()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_summarize_recent(self) -> None:
        output = summarize_recent(
            store=self.store,
            config=self.config,
            days=7,
        )
        self.assertIsInstance(output, AIOutput)
        self.assertTrue(output.summary)

    def test_summarize_recent_no_data(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        try:
            store = SQLiteStore(Path(tmp.name) / "empty.sqlite")
            store.ensure_schema()
            output = summarize_recent(
                store=store,
                config=self.config,
                days=7,
            )
            self.assertIsInstance(output, AIOutput)
            self.assertIn("无探测结果", output.summary)
        finally:
            tmp.cleanup()


class ExplainAnomalyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store, self.task, self.tmp = _setup_store_with_data()
        self.config = OpsConfig()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_explain_anomaly(self) -> None:
        output = explain_anomaly(
            task_id=self.task.id,
            store=self.store,
            config=self.config,
        )
        self.assertIsInstance(output, AIOutput)
        # Should only include non-success results
        facts_text = " ".join(output.facts)
        self.assertIn("10.0.0.99", facts_text)
        self.assertNotIn("192.168.1.1", facts_text)

    def test_explain_anomaly_with_question(self) -> None:
        output = explain_anomaly(
            task_id=self.task.id,
            store=self.store,
            config=self.config,
            question="为什么 10.0.0.99 连不上？",
        )
        self.assertIsInstance(output, AIOutput)

    def test_explain_anomaly_not_found(self) -> None:
        with self.assertRaises(AIAdapterError):
            explain_anomaly(
                task_id="nonexistent",
                store=self.store,
                config=self.config,
            )


# ---------------------------------------------------------------------------
# 存储层 AI 日志测试
# ---------------------------------------------------------------------------


class StorageAILogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SQLiteStore(Path(self.tmp.name) / "ops.sqlite")
        self.store.ensure_schema()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_save_and_list_ai_call_log(self) -> None:
        from datetime import datetime as dt
        from it_ops_toolkit.models import AICallLog

        log = AICallLog(
            id="ai-log-001",
            task_id="task-001",
            backend="template",
            success=True,
            duration_ms=15,
            called_at=dt.now(UTC),
        )
        self.store.save_ai_call_log(log)

        logs = self.store.list_ai_call_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].backend, "template")
        self.assertTrue(logs[0].success)

    def test_list_ai_call_logs_by_task(self) -> None:
        from datetime import datetime as dt
        from it_ops_toolkit.models import AICallLog

        for i in range(3):
            log = AICallLog(
                id=f"ai-log-{i}",
                task_id="task-001" if i < 2 else "task-002",
                backend="template",
                success=True,
                duration_ms=10 + i,
                called_at=dt.now(UTC),
            )
            self.store.save_ai_call_log(log)

        logs = self.store.list_ai_call_logs(task_id="task-001")
        self.assertEqual(len(logs), 2)

    def test_list_ai_call_logs_empty(self) -> None:
        logs = self.store.list_ai_call_logs()
        self.assertEqual(len(logs), 0)


if __name__ == "__main__":
    unittest.main()
