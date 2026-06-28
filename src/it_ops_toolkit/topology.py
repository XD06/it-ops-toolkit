"""拓扑分析服务。

基于本机视角构建基础网络拓扑：
- 采集 ARP 表（IP → MAC → 厂商映射）。
- 采集本机网络接口和默认网关。
- 可选执行 traceroute 到外部目标。
- 将 ARP 表与资产库对比，发现未知设备和离线设备。

不追求完整网络拓扑发现（需要 SNMP/LLDP/CDP），只做本机视角的基础拓扑。
"""

from __future__ import annotations

import socket
from typing import Any

from .models import (
    ArpEntry,
    Asset,
    AssetReconciliation,
    TopologyView,
    TraceRouteResult,
)
from .probes.arp import collect_arp_table
from .probes.traceroute import run_traceroute
from .storage import SQLiteStore


class TopologyError(RuntimeError):
    pass


def get_topology(
    *,
    store: SQLiteStore | None = None,
    traceroute_target: str | None = None,
    max_hops: int = 15,
) -> TopologyView:
    """采集并构建本机视角的网络拓扑。

    Args:
        store: 数据存储实例（可选，提供时做资产对比）。
        traceroute_target: 可选，traceroute 目标。
        max_hops: traceroute 最大跳数。

    Returns:
        TopologyView 包含接口、网关、ARP 表和可选的 traceroute。
    """
    # 采集本机网络信息
    interfaces = _get_local_interfaces()
    gateway = _get_default_gateway()
    source = _get_local_ip()

    # 采集 ARP 表
    arp_entries = collect_arp_table()

    # 可选 traceroute
    traceroute_result: TraceRouteResult | None = None
    if traceroute_target:
        try:
            traceroute_result = run_traceroute(
                target=traceroute_target,
                max_hops=max_hops,
            )
        except Exception as exc:
            traceroute_result = TraceRouteResult(
                target=traceroute_target,
                source=source,
                reached=False,
                raw_output=f"traceroute failed: {exc}",
            )

    # 资产对比
    reconciliation: AssetReconciliation | None = None
    if store is not None:
        reconciliation = reconcile_arp_with_assets(
            arp_entries=arp_entries,
            store=store,
        )

    return TopologyView(
        source=source,
        interfaces=interfaces,
        gateway=gateway,
        arp_entries=arp_entries,
        traceroute=traceroute_result,
        reconciliation=reconciliation,
    )


def reconcile_arp_with_assets(
    *,
    arp_entries: list[ArpEntry],
    store: SQLiteStore,
) -> AssetReconciliation:
    """将 ARP 表与资产库对比。

    - ARP 表中有但资产库中没有 → 标记为"新设备"。
    - 资产库中有但 ARP 表中没有 → 标记为"离线设备"。
    - 两者都有 → 匹配，更新资产 MAC/厂商。
    - 厂商为 None → 标记为"未知厂商"。
    """
    # 获取所有已知资产
    assets = store.list_assets()
    asset_ips = {a.ip: a for a in assets}
    arp_ips = {e.ip for e in arp_entries}

    new_devices: list[ArpEntry] = []
    offline_devices: list[Asset] = []
    matched: list[dict[str, Any]] = []
    unknown_vendors: list[ArpEntry] = []

    for entry in arp_entries:
        if entry.ip in asset_ips:
            asset = asset_ips[entry.ip]
            matched.append(
                {
                    "asset_id": asset.id,
                    "ip": entry.ip,
                    "mac": entry.mac,
                    "vendor": entry.vendor,
                    "hostname": asset.hostname,
                    "open_ports": asset.open_ports,
                    "device_type": entry.device_type,
                }
            )
        else:
            new_devices.append(entry)

        if entry.vendor is None:
            unknown_vendors.append(entry)

    for asset in assets:
        if asset.ip not in arp_ips:
            offline_devices.append(asset)

    return AssetReconciliation(
        new_devices=new_devices,
        offline_devices=offline_devices,
        matched=matched,
        unknown_vendors=unknown_vendors,
    )


def detect_unknown_devices(
    *,
    arp_entries: list[ArpEntry],
    store: SQLiteStore,
) -> list[ArpEntry]:
    """检测 ARP 表中不在资产库的未知设备。

    这是安全相关功能：未知设备可能是未授权接入。
    """
    assets = store.list_assets()
    asset_ips = {a.ip for a in assets}

    unknown: list[ArpEntry] = []
    for entry in arp_entries:
        if entry.ip not in asset_ips:
            unknown.append(entry)

    return unknown


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _get_local_ip() -> str:
    """获取本机 IP。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _get_default_gateway() -> str | None:
    """获取默认网关。

    Windows: `route print` 或 `netsh` 输出解析。
    Linux: `ip route` 输出解析。
    """
    import platform
    import subprocess

    system = platform.system().lower()

    if system == "windows":
        try:
            completed = subprocess.run(
                ["route", "print", "0.0.0.0"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return _parse_windows_gateway(completed.stdout)
        except Exception:
            return None
    else:
        try:
            completed = subprocess.run(
                ["ip", "route"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return _parse_linux_gateway(completed.stdout)
        except Exception:
            return None


def _parse_windows_gateway(output: str) -> str | None:
    """从 Windows route print 输出中解析默认网关。"""
    import re

    # 查找 "0.0.0.0  0.0.0.0  <gateway>  <interface>" 行
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("0.0.0.0"):
            parts = line.split()
            if len(parts) >= 3:
                gw = parts[2]
                if _is_valid_ip(gw):
                    return gw

    # 也尝试 netsh 的输出格式
    for line in output.splitlines():
        match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", line)
        if match and "0.0.0.0" in line:
            ip = match.group(1)
            if ip != "0.0.0.0" and _is_valid_ip(ip):
                return ip

    return None


def _parse_linux_gateway(output: str) -> str | None:
    """从 Linux ip route 输出中解析默认网关。"""
    import re

    for line in output.splitlines():
        line = line.strip()
        if line.startswith("default"):
            # 格式: default via 192.168.1.1 dev eth0
            match = re.search(r"via\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", line)
            if match:
                return match.group(1)

    return None


def _is_valid_ip(ip: str) -> bool:
    """简单验证 IP 地址格式。"""
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


def _get_local_interfaces() -> list[dict[str, Any]]:
    """获取本机网络接口信息。

    使用 socket 和平台特定方法获取简化信息。
    """
    hostname = socket.gethostname()

    try:
        local_ip = _get_local_ip()
    except Exception:
        local_ip = "127.0.0.1"

    interfaces: list[dict[str, Any]] = []

    # 尝试获取所有接口信息
    import platform
    import subprocess

    system = platform.system().lower()

    if system == "windows":
        try:
            # Windows ipconfig 输出使用系统活动代码页（中文系统为 GBK/CP936）。
            # 用 bytes 模式捕获，再按正确编码解码，避免乱码。
            completed = subprocess.run(
                ["ipconfig"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            stdout = completed.stdout
            # 优先尝试系统默认编码（locale.getpreferredencoding），
            # 中文 Windows 上通常是 cp936(gbk)。
            import locale
            preferred = locale.getpreferredencoding()
            try:
                text_output = stdout.decode(preferred)
            except (UnicodeDecodeError, LookupError):
                # 兜底：尝试常见 Windows 中文编码
                for enc in ("gbk", "cp936", "utf-8"):
                    try:
                        text_output = stdout.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    text_output = stdout.decode("utf-8", errors="replace")
            interfaces = _parse_windows_ipconfig(text_output)
        except Exception:
            interfaces = [
                {
                    "name": "unknown",
                    "ip": local_ip,
                    "hostname": hostname,
                }
            ]
    else:
        try:
            completed = subprocess.run(
                ["ip", "addr"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            interfaces = _parse_linux_ip_addr(completed.stdout)
        except Exception:
            interfaces = [
                {
                    "name": "unknown",
                    "ip": local_ip,
                    "hostname": hostname,
                }
            ]

    return interfaces


# ipconfig 输出中不应作为接口名的行前缀
_IPCONFIG_SKIP_PREFIXES = (
    "Connection-specific",
    "Windows IP",
)


def _parse_windows_ipconfig(output: str) -> list[dict[str, Any]]:
    """解析 Windows ipconfig 输出。"""
    import re

    interfaces: list[dict[str, Any]] = []
    current_name = ""
    current_ip = ""

    for raw_line in output.splitlines():
        stripped = raw_line.strip()

        # 跳过空行
        if not stripped:
            continue

        # 缩进行是接口的属性行（IPv4、MAC、DNS 等）
        if raw_line[0].isspace():
            if "IPv4" in stripped or "IP Address" in stripped:
                match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", stripped)
                if match:
                    current_ip = match.group(1)
            continue

        # 非缩进行且以冒号结尾 → 接口名
        if stripped.endswith(":"):
            name = stripped[:-1].strip()
            # 跳过非接口名行
            if name.startswith(_IPCONFIG_SKIP_PREFIXES):
                continue
            # 保存上一个接口
            if current_name:
                interfaces.append(
                    {"name": current_name, "ip": current_ip, "hostname": ""}
                )
            current_name = name
            current_ip = ""

    if current_name:
        interfaces.append(
            {"name": current_name, "ip": current_ip, "hostname": ""}
        )

    return interfaces


def _parse_linux_ip_addr(output: str) -> list[dict[str, Any]]:
    """解析 Linux ip addr 输出。"""
    import re

    interfaces: list[dict[str, Any]] = []
    current_name = ""
    current_ip = ""

    for line in output.splitlines():
        line = line.strip()

        # 接口行: "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 ..."
        match = re.match(r"^\d+:\s+([^:]+):", line)
        if match:
            if current_name:
                interfaces.append(
                    {"name": current_name, "ip": current_ip, "hostname": ""}
                )
            current_name = match.group(1)
            current_ip = ""
        elif "inet " in line:
            match = re.search(r"inet\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", line)
            if match:
                current_ip = match.group(1)

    if current_name:
        interfaces.append(
            {"name": current_name, "ip": current_ip, "hostname": ""}
        )

    return interfaces
