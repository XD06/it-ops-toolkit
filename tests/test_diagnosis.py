import unittest
from datetime import UTC, datetime

from it_ops_toolkit.diagnosis import classify_internet_diagnosis
from it_ops_toolkit.models import ProbeResult, ProbeStatus, Target


class DiagnosisTests(unittest.TestCase):
    def test_classifies_dns_issue_when_ping_ok_but_dns_fails(self) -> None:
        results = [
            _result("ping", "223.5.5.5", ProbeStatus.success),
            _result("dns", "www.baidu.com", ProbeStatus.failed),
            _result("http", "https://www.baidu.com", ProbeStatus.failed),
        ]

        summary = classify_internet_diagnosis(results)

        self.assertEqual(summary.title, "外部 IP 可达，但 DNS 解析异常")

    def test_classifies_success_when_all_checks_pass(self) -> None:
        results = [
            _result("ping", "223.5.5.5", ProbeStatus.success),
            _result("dns", "www.baidu.com", ProbeStatus.success),
            _result("http", "https://www.baidu.com", ProbeStatus.success),
        ]

        summary = classify_internet_diagnosis(results)

        self.assertEqual(summary.title, "基础互联网连通性正常")


def _result(probe_type: str, target: str, status: ProbeStatus) -> ProbeResult:
    now = datetime.now(UTC)
    target_type = "url" if target.startswith("http") else "hostname"
    return ProbeResult(
        id=f"probe-{probe_type}-{target}",
        task_id="task-test",
        probe_type=probe_type,
        target=Target(type=target_type, value=target),
        status=status,
        started_at=now,
        ended_at=now,
    )


if __name__ == "__main__":
    unittest.main()

