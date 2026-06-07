from __future__ import annotations

from dataclasses import dataclass

from .models import ProbeResult, ProbeStatus, TaskRun
from .probes import check_http_url, ping_host, resolve_hostname
from .storage import SQLiteStore


DEFAULT_EXTERNAL_IP = "223.5.5.5"
DEFAULT_DNS_NAME = "www.baidu.com"
DEFAULT_HTTP_URL = "https://www.baidu.com"


@dataclass(frozen=True)
class DiagnosisSummary:
    title: str
    likely_area: str
    recommendation: str


def run_internet_diagnosis(
    *,
    task: TaskRun,
    store: SQLiteStore,
    external_ip: str = DEFAULT_EXTERNAL_IP,
    dns_name: str = DEFAULT_DNS_NAME,
    http_url: str = DEFAULT_HTTP_URL,
    timeout_ms: int = 1000,
    retries: int = 1,
) -> tuple[list[ProbeResult], DiagnosisSummary]:
    results = [
        ping_host(
            task_id=task.id,
            target=external_ip,
            timeout_ms=timeout_ms,
            retries=retries,
        ),
        resolve_hostname(
            task_id=task.id,
            hostname=dns_name,
            timeout_ms=timeout_ms,
        ),
        check_http_url(
            task_id=task.id,
            url=http_url,
            timeout_ms=timeout_ms,
        ),
    ]
    for result in results:
        store.save_probe_result(result)
    return results, classify_internet_diagnosis(results)


def classify_internet_diagnosis(results: list[ProbeResult]) -> DiagnosisSummary:
    ping_result = _first_result(results, "ping")
    dns_result = _first_result(results, "dns")
    http_result = _first_result(results, "http")

    ping_ok = _is_success(ping_result)
    dns_ok = _is_success(dns_result)
    http_ok = _is_success(http_result)

    if not ping_ok:
        return DiagnosisSummary(
            title="外部 IP 不可达",
            likely_area="本机网络、网关、出口、防火墙或运营商链路",
            recommendation="先检查本机 IP、网关、网线/无线、默认路由和出口设备状态。",
        )
    if not dns_ok:
        return DiagnosisSummary(
            title="外部 IP 可达，但 DNS 解析异常",
            likely_area="DNS 配置、DNS 服务或上游解析",
            recommendation="检查本机 DNS 配置、内网 DNS 服务、DNS 转发和安全设备策略。",
        )
    if not http_ok:
        return DiagnosisSummary(
            title="IP 和 DNS 基本正常，但 HTTP 访问异常",
            likely_area="代理、浏览器、证书、目标网站、出口 HTTP/HTTPS 策略",
            recommendation="检查代理配置、浏览器错误、证书状态和出口安全设备策略。",
        )
    return DiagnosisSummary(
        title="基础互联网连通性正常",
        likely_area="未发现基础连通性异常",
        recommendation="如果用户仍然反馈异常，继续检查具体应用、账号、代理、DNS 缓存或业务系统状态。",
    )


def _first_result(results: list[ProbeResult], probe_type: str) -> ProbeResult | None:
    return next((result for result in results if result.probe_type == probe_type), None)


def _is_success(result: ProbeResult | None) -> bool:
    return result is not None and result.status == ProbeStatus.success

