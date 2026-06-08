from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlparse

from .models import ProbeResult, ProbeStatus, TaskRun
from .probes import check_http_url, check_tcp_port, ping_host, resolve_hostname
from .storage import SQLiteStore


DEFAULT_EXTERNAL_IP = "223.5.5.5"
DEFAULT_DNS_NAME = "www.baidu.com"
DEFAULT_HTTP_URL = "https://www.baidu.com"
DEFAULT_RDP_PORT = 3389


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


def run_intranet_diagnosis(
    *,
    task: TaskRun,
    store: SQLiteStore,
    url: str,
    timeout_ms: int = 1000,
    retries: int = 1,
) -> tuple[list[ProbeResult], DiagnosisSummary]:
    target = parse_service_url(url)
    results: list[ProbeResult] = []

    if not _is_ip_address(target["host"]):
        results.append(
            resolve_hostname(
                task_id=task.id,
                hostname=target["host"],
                timeout_ms=timeout_ms,
            )
        )

    results.extend(
        [
            ping_host(
                task_id=task.id,
                target=target["host"],
                timeout_ms=timeout_ms,
                retries=retries,
            ),
            check_tcp_port(
                task_id=task.id,
                target=target["host"],
                port=target["port"],
                timeout_ms=timeout_ms,
            ),
            check_http_url(
                task_id=task.id,
                url=target["url"],
                timeout_ms=timeout_ms,
            ),
        ]
    )

    for result in results:
        store.save_probe_result(result)
    return results, classify_intranet_diagnosis(results)


def classify_intranet_diagnosis(results: list[ProbeResult]) -> DiagnosisSummary:
    dns_result = _first_result(results, "dns")
    ping_result = _first_result(results, "ping")
    tcp_result = _first_result(results, "tcp")
    http_result = _first_result(results, "http")

    dns_ok = dns_result is None or _is_success(dns_result)
    ping_ok = _is_success(ping_result)
    tcp_ok = _is_success(tcp_result)
    http_ok = _is_success(http_result)

    if not dns_ok:
        return DiagnosisSummary(
            title="内网系统域名解析异常",
            likely_area="内网 DNS、主机名配置、搜索域或 DNS 转发",
            recommendation="先确认域名是否正确，再检查本机 DNS、内网 DNS 服务和解析记录。",
        )
    if not ping_ok and not tcp_ok:
        return DiagnosisSummary(
            title="目标主机或网络路径不可达",
            likely_area="目标服务器、路由、ACL、防火墙、网段隔离",
            recommendation="检查目标服务器是否在线、网关路由是否正确，以及防火墙/ACL 是否阻断。",
        )
    if not tcp_ok:
        return DiagnosisSummary(
            title="目标主机可达，但业务端口不可达",
            likely_area="服务未启动、本机或服务器防火墙、端口策略、负载均衡",
            recommendation="检查目标服务端口、应用服务状态、防火墙策略和反向代理/负载均衡。",
        )
    if not http_ok:
        return DiagnosisSummary(
            title="端口可达，但 HTTP/HTTPS 访问异常",
            likely_area="Web 应用、证书、认证、反向代理、应用错误",
            recommendation="查看浏览器错误、HTTP 状态、证书、应用日志和反向代理配置。",
        )
    return DiagnosisSummary(
        title="内网系统基础访问链路正常",
        likely_area="未发现 DNS、网络路径、端口或 HTTP 基础异常",
        recommendation="如果用户仍然打不开，继续检查账号权限、浏览器缓存、代理、应用业务状态或用户终端环境。",
    )


def run_rdp_diagnosis(
    *,
    task: TaskRun,
    store: SQLiteStore,
    target: str,
    port: int = DEFAULT_RDP_PORT,
    timeout_ms: int = 1000,
    retries: int = 1,
) -> tuple[list[ProbeResult], DiagnosisSummary]:
    parsed = parse_host_port_target(target, default_port=port)
    host = parsed["host"]
    target_port = parsed["port"]
    results: list[ProbeResult] = []

    if not _is_ip_address(host):
        results.append(
            resolve_hostname(
                task_id=task.id,
                hostname=host,
                timeout_ms=timeout_ms,
            )
        )

    results.extend(
        [
            ping_host(
                task_id=task.id,
                target=host,
                timeout_ms=timeout_ms,
                retries=retries,
            ),
            check_tcp_port(
                task_id=task.id,
                target=host,
                port=target_port,
                timeout_ms=timeout_ms,
            ),
        ]
    )

    for result in results:
        store.save_probe_result(result)
    return results, classify_rdp_diagnosis(results)


def classify_rdp_diagnosis(results: list[ProbeResult]) -> DiagnosisSummary:
    dns_result = _first_result(results, "dns")
    ping_result = _first_result(results, "ping")
    tcp_result = _first_result(results, "tcp")

    dns_ok = dns_result is None or _is_success(dns_result)
    ping_ok = _is_success(ping_result)
    tcp_ok = _is_success(tcp_result)

    if not dns_ok:
        return DiagnosisSummary(
            title="远程桌面目标解析异常",
            likely_area="DNS、主机名、搜索域或资产命名",
            recommendation="先确认目标名称是否正确，再检查本机 DNS、内网 DNS 记录和搜索域配置。",
        )
    if tcp_ok and not ping_ok:
        return DiagnosisSummary(
            title="RDP 端口可达，但 Ping 不通",
            likely_area="目标主机禁 ICMP、终端防火墙、网络设备阻断 Ping",
            recommendation="RDP 基础端口已可达，继续检查账号权限、NLA、远程桌面服务策略和客户端错误信息。",
        )
    if not ping_ok and not tcp_ok:
        return DiagnosisSummary(
            title="目标主机或网络路径不可达",
            likely_area="目标主机离线、路由、ACL、防火墙、跨网段策略",
            recommendation="确认目标主机在线、电源和网卡状态正常，再检查网关路由、防火墙和网络隔离策略。",
        )
    if not tcp_ok:
        return DiagnosisSummary(
            title="目标主机可达，但 RDP 端口不可达",
            likely_area="远程桌面服务未启用、防火墙阻断、端口变更、主机安全策略",
            recommendation="检查目标主机是否启用远程桌面、TCP 端口、防火墙入站规则和安全基线策略。",
        )
    return DiagnosisSummary(
        title="RDP 基础端口可达",
        likely_area="网络路径和端口基础检查正常",
        recommendation="如果仍无法登录，继续检查账号权限、NLA、远程桌面服务状态、授权、并发会话和客户端版本。",
    )


def parse_service_url(url: str) -> dict[str, object]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must include http:// or https:// and a hostname")
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return {
        "url": url,
        "host": parsed.hostname,
        "port": port,
    }


def parse_host_port_target(target: str, *, default_port: int) -> dict[str, object]:
    if default_port < 1 or default_port > 65535:
        raise ValueError(f"invalid TCP port: {default_port}")

    value = target.strip()
    if not value:
        raise ValueError("target is required")

    if value.startswith("rdp://"):
        parsed = urlparse(value)
        if not parsed.hostname:
            raise ValueError("RDP target must include a hostname")
        port = parsed.port or default_port
        return {"host": parsed.hostname, "port": _validate_port(port)}

    if value.count(":") == 1:
        host, raw_port = value.rsplit(":", 1)
        if host and raw_port.isdigit():
            return {"host": host, "port": _validate_port(int(raw_port))}

    return {"host": value, "port": default_port}


def _first_result(results: list[ProbeResult], probe_type: str) -> ProbeResult | None:
    return next((result for result in results if result.probe_type == probe_type), None)


def _is_success(result: ProbeResult | None) -> bool:
    return result is not None and result.status == ProbeStatus.success


def _is_ip_address(value: str) -> bool:
    try:
        ip_address(value)
    except ValueError:
        return False
    return True


def _validate_port(port: int) -> int:
    if port < 1 or port > 65535:
        raise ValueError(f"invalid TCP port: {port}")
    return port
