"""Web Console API 单元测试。

使用 FastAPI TestClient 和内存 SQLite 数据库测试所有 API 端点。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from it_ops_toolkit.config import OpsConfig
from it_ops_toolkit.models import (
    Asset,
    ErrorInfo,
    Finding,
    ProbeResult,
    ProbeStatus,
    Report,
    RiskLevel,
    Severity,
    Target,
    TaskRun,
    TaskStatus,
)
from it_ops_toolkit.storage import SQLiteStore
from it_ops_toolkit.web.app import app, set_config, set_store


# ---------------------------------------------------------------------------
# 测试夹具
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStore:
    db_path = tmp_path / "test_web.sqlite"
    s = SQLiteStore(db_path)
    s.ensure_schema()
    return s


@pytest.fixture
def client(store: SQLiteStore) -> TestClient:
    set_store(store)
    set_config(None)  # 默认不注入配置
    return TestClient(app)


@pytest.fixture
def config() -> OpsConfig:
    return OpsConfig.model_validate({
        "app": {"name": "Test", "environment": "test"},
        "scan_profiles": {
            "test_scan": {
                "description": "测试扫描",
                "subnets": ["192.168.1.0/30"],
                "ping": {"enabled": True, "timeout_ms": 200, "retries": 0},
                "tcp_ports": [80],
            }
        },
        "health_profiles": {
            "test_health": {
                "description": "测试巡检",
                "targets": [
                    {"name": "网关", "type": "ip", "value": "192.168.1.1", "checks": ["ping"]},
                ],
            }
        },
        "probe_defaults": {"timeout_ms": 200, "retries": 0, "concurrency": 4},
        "reports": {"output_dir": "./reports", "formats": ["markdown"]},
        "storage": {"type": "sqlite", "path": "./data/test.sqlite"},
        "security": {"risky_ports": [22, 3389]},
    })


@pytest.fixture
def client_with_config(store: SQLiteStore, config: OpsConfig) -> TestClient:
    set_store(store)
    set_config(config)
    return TestClient(app)


def _make_task(
    *,
    task_type: str = "health_check",
    status: TaskStatus = TaskStatus.success,
    risk_level: RiskLevel = RiskLevel.read_only,
    summary: dict | None = None,
) -> TaskRun:
    return TaskRun(
        id=f"task-{uuid4().hex[:12]}",
        task_type=task_type,
        requested_by="tester",
        source="cli",
        status=status,
        risk_level=risk_level,
        started_at=datetime.now(UTC),
        ended_at=datetime.now(UTC) if status in (TaskStatus.success, TaskStatus.failed) else None,
        summary=summary or {},
    )


def _make_asset(
    *,
    ip: str = "192.168.1.100",
    hostname: str | None = "host-100",
    mac: str | None = "aa:bb:cc:dd:ee:ff",
    open_ports: list[int] | None = None,
    status: str = "active",
) -> Asset:
    now = datetime.now(UTC)
    return Asset(
        id=f"asset-{uuid4().hex[:12]}",
        ip=ip,
        hostname=hostname,
        mac=mac,
        vendor="TestVendor",
        os_hint="Linux",
        asset_type="server",
        open_ports=open_ports or [22, 80],
        first_seen=now,
        last_seen=now,
        status=status,
        source="asset_scan",
    )


def _make_probe_result(
    *,
    task_id: str,
    probe_type: str = "ping",
    target_value: str = "192.168.1.1",
    status: ProbeStatus = ProbeStatus.success,
    duration_ms: int = 50,
    observations: dict | None = None,
) -> ProbeResult:
    return ProbeResult(
        id=f"probe-{uuid4().hex[:12]}",
        task_id=task_id,
        probe_type=probe_type,
        target=Target(type="ip", value=target_value),
        status=status,
        started_at=datetime.now(UTC),
        ended_at=datetime.now(UTC),
        duration_ms=duration_ms,
        observations=observations or {"avg_rtt_ms": 5},
    )


def _make_finding(
    *,
    task_id: str,
    severity: Severity = Severity.high,
    title: str = "测试发现项",
    category: str = "availability",
) -> Finding:
    return Finding(
        id=f"finding-{uuid4().hex[:12]}",
        task_id=task_id,
        category=category,
        severity=severity,
        title=title,
        description="这是一个测试发现项的描述。",
        evidence_refs=["probe-abc"],
        recommendation="建议处理此问题。",
        requires_human_review=True,
    )


def _make_report(
    *,
    source_task_id: str,
    report_type: str = "health",
    title: str = "巡检报告",
    fmt: str = "markdown",
    path: str = "/tmp/report.md",
    summary: str = "巡检完成",
) -> Report:
    return Report(
        id=f"report-{uuid4().hex[:12]}",
        source_task_id=source_task_id,
        report_type=report_type,
        title=title,
        format=fmt,
        path=path,
        summary=summary,
        generated_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health(self, client: TestClient) -> None:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


# ---------------------------------------------------------------------------
# 概览
# ---------------------------------------------------------------------------


class TestOverviewEndpoint:
    def test_empty_overview(self, client: TestClient) -> None:
        resp = client.get("/api/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["assets_count"] == 0
        assert data["tasks_count"] == 0
        assert data["reports_count"] == 0
        assert data["findings_count"] == 0
        assert data["task_type_counts"] == {}
        assert data["severity_counts"] == {}

    def test_overview_with_data(self, client: TestClient, store: SQLiteStore) -> None:
        task = _make_task(task_type="health_check")
        store.save_task_run(task)
        store.save_asset(_make_asset())
        store.save_finding(_make_finding(task_id=task.id, severity=Severity.high))
        store.save_report(_make_report(source_task_id=task.id))

        resp = client.get("/api/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["assets_count"] == 1
        assert data["tasks_count"] == 1
        assert data["reports_count"] == 1
        assert data["findings_count"] == 1
        assert data["task_type_counts"]["health_check"] == 1
        assert data["severity_counts"]["high"] == 1


# ---------------------------------------------------------------------------
# 资产
# ---------------------------------------------------------------------------


class TestAssetsEndpoints:
    def test_list_empty(self, client: TestClient) -> None:
        resp = client.get("/api/assets")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_data(self, client: TestClient, store: SQLiteStore) -> None:
        asset = _make_asset(ip="10.0.0.1", hostname="server-01")
        store.save_asset(asset)

        resp = client.get("/api/assets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["ip"] == "10.0.0.1"
        assert data[0]["hostname"] == "server-01"
        assert data[0]["open_ports"] == [22, 80]
        assert data[0]["status"] == "active"

    def test_get_by_ip(self, client: TestClient, store: SQLiteStore) -> None:
        asset = _make_asset(ip="10.0.0.2", hostname="server-02", mac="11:22:33:44:55:66")
        store.save_asset(asset)

        resp = client.get("/api/assets/10.0.0.2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ip"] == "10.0.0.2"
        assert data["hostname"] == "server-02"
        assert data["mac"] == "11:22:33:44:55:66"

    def test_get_by_ip_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/assets/10.99.99.99")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 任务
# ---------------------------------------------------------------------------


class TestTasksEndpoints:
    def test_list_empty(self, client: TestClient) -> None:
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_data(self, client: TestClient, store: SQLiteStore) -> None:
        task1 = _make_task(task_type="health_check")
        task2 = _make_task(task_type="asset_scan")
        store.save_task_run(task1)
        store.save_task_run(task2)

        resp = client.get("/api/tasks?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_get_task(self, client: TestClient, store: SQLiteStore) -> None:
        task = _make_task(
            task_type="diagnosis",
            summary={"scenario": "dns", "title": "DNS 诊断"},
        )
        store.save_task_run(task)

        resp = client.get(f"/api/tasks/{task.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == task.id
        assert data["task_type"] == "diagnosis"
        assert data["status"] == "success"
        assert data["summary"]["scenario"] == "dns"

    def test_get_task_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/tasks/nonexistent")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_get_task_results(self, client: TestClient, store: SQLiteStore) -> None:
        task = _make_task()
        store.save_task_run(task)
        store.save_probe_result(_make_probe_result(task_id=task.id, probe_type="ping"))
        store.save_probe_result(_make_probe_result(task_id=task.id, probe_type="dns"))

        resp = client.get(f"/api/tasks/{task.id}/results")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        probe_types = {r["probe_type"] for r in data}
        assert probe_types == {"ping", "dns"}

    def test_get_task_results_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/tasks/nonexistent/results")
        assert resp.status_code == 404

    def test_get_task_findings(self, client: TestClient, store: SQLiteStore) -> None:
        task = _make_task()
        store.save_task_run(task)
        store.save_finding(_make_finding(task_id=task.id, severity=Severity.critical))
        store.save_finding(_make_finding(task_id=task.id, severity=Severity.info, title="信息项"))

        resp = client.get(f"/api/tasks/{task.id}/findings")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_get_task_findings_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/tasks/nonexistent/findings")
        assert resp.status_code == 404

    def test_get_task_snapshots_empty(self, client: TestClient, store: SQLiteStore) -> None:
        task = _make_task()
        store.save_task_run(task)

        resp = client.get(f"/api/tasks/{task.id}/snapshots")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------


class TestReportsEndpoints:
    def test_list_empty(self, client: TestClient) -> None:
        resp = client.get("/api/reports")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_data(self, client: TestClient, store: SQLiteStore) -> None:
        task = _make_task()
        store.save_task_run(task)
        report = _make_report(source_task_id=task.id, title="测试报告")
        store.save_report(report)

        resp = client.get("/api/reports")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "测试报告"

    def test_get_report(self, client: TestClient, store: SQLiteStore) -> None:
        task = _make_task()
        store.save_task_run(task)
        report = _make_report(source_task_id=task.id, title="详情报告")
        store.save_report(report)

        resp = client.get(f"/api/reports/{report.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "详情报告"
        assert data["source_task_id"] == task.id

    def test_get_report_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/reports/nonexistent")
        assert resp.status_code == 404

    def test_get_report_content(
        self, client: TestClient, store: SQLiteStore, tmp_path: Path
    ) -> None:
        report_file = tmp_path / "test_report.md"
        report_file.write_text("# 巡检报告\n\n一切正常。", encoding="utf-8")

        task = _make_task()
        store.save_task_run(task)
        report = _make_report(
            source_task_id=task.id,
            title="文件报告",
            fmt="markdown",
            path=str(report_file),
        )
        store.save_report(report)

        resp = client.get(f"/api/reports/{report.id}/content")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "文件报告"
        assert "一切正常" in data["content"]

    def test_get_report_content_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/reports/nonexistent/content")
        assert resp.status_code == 404

    def test_get_report_content_file_missing(
        self, client: TestClient, store: SQLiteStore, tmp_path: Path
    ) -> None:
        task = _make_task()
        store.save_task_run(task)
        missing_file = tmp_path / "deleted_report.md"
        report = _make_report(
            source_task_id=task.id,
            path=str(missing_file),
        )
        store.save_report(report)

        resp = client.get(f"/api/reports/{report.id}/content")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 仪表盘页面
# ---------------------------------------------------------------------------


class TestDashboardPage:
    def test_dashboard_html(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        body = resp.text
        assert "IT Ops Toolkit" in body
        assert "Web Console" in body

    def test_dashboard_with_data(self, client: TestClient, store: SQLiteStore) -> None:
        store.save_asset(_make_asset())
        store.save_task_run(_make_task())

        resp = client.get("/")
        assert resp.status_code == 200
        assert "IT Ops Toolkit" in resp.text


# ---------------------------------------------------------------------------
# 任务筛选
# ---------------------------------------------------------------------------


class TestTaskFiltering:
    def test_filter_by_task_type(self, client: TestClient, store: SQLiteStore) -> None:
        task1 = _make_task(task_type="health_check")
        task2 = _make_task(task_type="asset_scan")
        store.save_task_run(task1)
        store.save_task_run(task2)

        resp = client.get("/api/tasks?task_type=health_check")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["task_type"] == "health_check"

    def test_filter_by_status(self, client: TestClient, store: SQLiteStore) -> None:
        task1 = _make_task(status=TaskStatus.success)
        task2 = _make_task(status=TaskStatus.failed)
        store.save_task_run(task1)
        store.save_task_run(task2)

        resp = client.get("/api/tasks?status=failed")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "failed"

    def test_filter_by_type_and_status(self, client: TestClient, store: SQLiteStore) -> None:
        task1 = _make_task(task_type="health_check", status=TaskStatus.success)
        task2 = _make_task(task_type="health_check", status=TaskStatus.failed)
        task3 = _make_task(task_type="asset_scan", status=TaskStatus.success)
        store.save_task_run(task1)
        store.save_task_run(task2)
        store.save_task_run(task3)

        resp = client.get("/api/tasks?task_type=health_check&status=success")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["task_type"] == "health_check"
        assert data[0]["status"] == "success"

    def test_filter_no_match(self, client: TestClient, store: SQLiteStore) -> None:
        task1 = _make_task(task_type="health_check")
        store.save_task_run(task1)

        resp = client.get("/api/tasks?task_type=asset_scan")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# 配置查看
# ---------------------------------------------------------------------------


class TestConfigEndpoints:
    def test_config_not_available(self, client: TestClient) -> None:
        resp = client.get("/api/config")
        assert resp.status_code == 503

    def test_get_config(self, client_with_config: TestClient) -> None:
        resp = client_with_config.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["app"]["name"] == "Test"
        assert "test_scan" in data["scan_profiles"]
        assert "test_health" in data["health_profiles"]
        assert data["probe_defaults"]["timeout_ms"] == 200
        assert data["security"]["risky_ports"] == [22, 3389]

    def test_get_health_profiles(self, client_with_config: TestClient) -> None:
        resp = client_with_config.get("/api/config/health-profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "test_health"
        assert len(data[0]["targets"]) == 1
        assert data[0]["targets"][0]["name"] == "网关"
        assert data[0]["targets"][0]["checks"] == ["ping"]

    def test_get_scan_profiles(self, client_with_config: TestClient) -> None:
        resp = client_with_config.get("/api/config/scan-profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "test_scan"
        assert "192.168.1.0/30" in data[0]["subnets"]
        assert 80 in data[0]["tcp_ports"]

    def test_health_profiles_not_available(self, client: TestClient) -> None:
        resp = client.get("/api/config/health-profiles")
        assert resp.status_code == 503

    def test_scan_profiles_not_available(self, client: TestClient) -> None:
        resp = client.get("/api/config/scan-profiles")
        assert resp.status_code == 503

    def test_overview_config_available_flag(
        self, client_with_config: TestClient
    ) -> None:
        resp = client_with_config.get("/api/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["config_available"] is True

    def test_overview_config_not_available(self, client: TestClient) -> None:
        resp = client.get("/api/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["config_available"] is False


# ---------------------------------------------------------------------------
# 任务触发
# ---------------------------------------------------------------------------


class TestTaskTrigger:
    def test_trigger_health_check_no_config(self, client: TestClient) -> None:
        resp = client.post(
            "/api/tasks/trigger/health-check",
            json={"profile_name": "test_health"},
        )
        assert resp.status_code == 503

    def test_trigger_health_check_invalid_profile(
        self, client_with_config: TestClient
    ) -> None:
        resp = client_with_config.post(
            "/api/tasks/trigger/health-check",
            json={"profile_name": "nonexistent"},
        )
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]

    def test_trigger_health_check_success(
        self, client_with_config: TestClient, store: SQLiteStore
    ) -> None:
        from unittest.mock import patch

        mock_results = [
            ProbeResult(
                id="probe-mock-1",
                task_id="mock-task",
                probe_type="ping",
                target=Target(type="ip", value="192.168.1.1"),
                status=ProbeStatus.success,
                started_at=datetime.now(UTC),
                ended_at=datetime.now(UTC),
                duration_ms=5,
                observations={"reachable": True, "avg_rtt_ms": 2},
            ),
        ]

        with patch(
            "it_ops_toolkit.web.app.run_health_check", return_value=mock_results
        ):
            resp = client_with_config.post(
                "/api/tasks/trigger/health-check",
                json={"profile_name": "test_health"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["source"] == "web"
        assert data["requested_by"] == "web"
        assert data["task_type"] == "health_check"
        assert len(data["result_refs"]) == 1

        # 验证任务已保存
        saved_task = store.get_task_run(data["id"])
        assert saved_task.status.value == "success"

    def test_trigger_health_check_failure(
        self, client_with_config: TestClient, store: SQLiteStore
    ) -> None:
        from unittest.mock import patch

        from it_ops_toolkit.health import HealthCheckError

        with patch(
            "it_ops_toolkit.web.app.run_health_check",
            side_effect=HealthCheckError("probe failed"),
        ):
            resp = client_with_config.post(
                "/api/tasks/trigger/health-check",
                json={"profile_name": "test_health"},
            )

        assert resp.status_code == 500
        assert "probe failed" in resp.json()["detail"]

    def test_trigger_asset_scan_no_config(self, client: TestClient) -> None:
        resp = client.post(
            "/api/tasks/trigger/asset-scan",
            json={"profile_name": "test_scan"},
        )
        assert resp.status_code == 503

    def test_trigger_asset_scan_invalid_profile(
        self, client_with_config: TestClient
    ) -> None:
        resp = client_with_config.post(
            "/api/tasks/trigger/asset-scan",
            json={"profile_name": "nonexistent"},
        )
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]

    def test_trigger_asset_scan_success(
        self, client_with_config: TestClient, store: SQLiteStore
    ) -> None:
        from unittest.mock import patch

        mock_assets = [
            Asset(
                id="asset-192-168-1-1",
                ip="192.168.1.1",
                hostname="router",
                first_seen=datetime.now(UTC),
                last_seen=datetime.now(UTC),
                status="active",
                source="scan_profile:test_scan",
            ),
        ]
        mock_results = [
            ProbeResult(
                id="probe-mock-scan-1",
                task_id="mock-task",
                probe_type="ping",
                target=Target(type="ip", value="192.168.1.1"),
                status=ProbeStatus.success,
                started_at=datetime.now(UTC),
                ended_at=datetime.now(UTC),
                duration_ms=3,
                observations={"reachable": True},
            ),
        ]

        with patch(
            "it_ops_toolkit.web.app.run_asset_scan",
            return_value=(mock_assets, mock_results),
        ):
            resp = client_with_config.post(
                "/api/tasks/trigger/asset-scan",
                json={"profile_name": "test_scan"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["source"] == "web"
        assert data["task_type"] == "asset_scan"
        assert "192.168.1.1" in data["target_refs"]

    def test_trigger_asset_scan_failure(
        self, client_with_config: TestClient, store: SQLiteStore
    ) -> None:
        from unittest.mock import patch

        from it_ops_toolkit.assets import AssetScanError

        with patch(
            "it_ops_toolkit.web.app.run_asset_scan",
            side_effect=AssetScanError("scan failed"),
        ):
            resp = client_with_config.post(
                "/api/tasks/trigger/asset-scan",
                json={"profile_name": "test_scan"},
            )

        assert resp.status_code == 500
        assert "scan failed" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 配置页面
# ---------------------------------------------------------------------------


class TestConfigPage:
    def test_config_page_without_config(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "IT Ops Toolkit" in resp.text

    def test_config_page_with_config(self, client_with_config: TestClient) -> None:
        resp = client_with_config.get("/")
        assert resp.status_code == 200
        assert "IT Ops Toolkit" in resp.text
