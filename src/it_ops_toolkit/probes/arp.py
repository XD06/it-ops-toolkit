"""ARP 表采集 Adapter。

跨平台支持：
- Windows: `arp -a` 命令输出解析。
- Linux: `ip neigh` 或 `arp -n` 命令输出解析。

输出 ArpEntry 列表，包含 IP、MAC、接口、状态和厂商信息。
"""

from __future__ import annotations

import platform
import re
import subprocess

from ..models import ArpEntry

# 精简 OUI 数据库（常见厂商前缀）
# 完整 OUI 数据库约 3 万条，这里只内置最常见的厂商前缀
_OUI_PREFIXES: dict[str, str] = {
    # Cisco
    "00:1b:54": "Cisco Systems",
    "00:1d:70": "Cisco Systems",
    "00:25:84": "Cisco Systems",
    "00:50:56": "VMware (Cisco)",
    "f4:cf:e2": "Cisco Systems",
    "00:14:2d": "Cisco Systems",
    # HP / Hewlett Packard
    "00:1e:0b": "Hewlett-Packard",
    "00:24:a8": "Hewlett-Packard",
    "00:25:61": "Hewlett-Packard",
    "3c:52:82": "Hewlett Packard",
    "f0:1d:bc": "Hewlett Packard",
    # Dell
    "00:15:c5": "Dell Inc.",
    "00:14:22": "Dell Inc.",
    "f8:db:88": "Dell Inc.",
    "14:18:77": "Dell Inc.",
    # Apple
    "00:1d:4f": "Apple Inc.",
    "00:25:00": "Apple Inc.",
    "ac:de:48": "Apple Inc.",
    "b8:e8:56": "Apple Inc.",
    # Intel
    "00:13:02": "Intel Corporate",
    "00:15:00": "Intel Corporate",
    "f0:98:9d": "Intel Corporate",
    # Realtek
    "00:30:18": "Realtek Semiconductor",
    "52:54:00": "Realtek Semiconductor (QEMU)",
    # Raspberry Pi
    "b8:27:eb": "Raspberry Pi Foundation",
    "dc:a6:32": "Raspberry Pi Foundation",
    # Huawei
    "00:25:9e": "Huawei Technologies",
    "00:18:82": "Huawei Technologies",
    "48:46:fb": "Huawei Technologies",
    # TP-Link
    "50:c7:bf": "TP-Link Technologies",
    "f4:f2:6d": "TP-Link Technologies",
    # Ubiquiti
    "00:27:22": "Ubiquiti Networks",
    "04:18:d6": "Ubiquiti Networks",
    # MikroTik
    "00:0c:42": "MikroTik",
    "d4:ca:6d": "MikroTik",
    # Synology
    "00:11:32": "Synology Incorporated",
    # QNAP
    "00:08:9b": "QNAP Systems",
    # Brother (printers)
    "00:80:77": "Brother Industries",
    "c4:ca:d9": "Brother Industries",
    # Canon
    "00:1e:8f": "Canon Inc.",
    "ac:5f:3e": "Canon Inc.",
    # Xerox
    "00:00:aa": "Xerox Corporation",
    "00:80:5f": "Xerox Corporation",
    # Samsung
    "00:15:99": "Samsung Electronics",
    # Lenovo
    "00:24:e4": "Lenovo Mobile",
    "60:45:bd": "Lenovo",
    # Microsoft (Surface)
    "00:15:5d": "Microsoft Corporation",
    # Google
    "f4:f5:e8": "Google Inc.",
    # Generic
    "00:00:00": "Invalid MAC",
    "ff:ff:ff": "Broadcast",
}


def lookup_vendor(mac: str) -> str | None:
    """根据 MAC 地址前缀查询厂商。

    使用内置精简 OUI 数据库，离线可用。
    """
    if not mac:
        return None

    mac_clean = mac.lower().strip()
    # 尝试 3 字节前缀匹配
    prefix = mac_clean[:8]  # XX:XX:XX
    return _OUI_PREFIXES.get(prefix)


def infer_device_type(vendor: str | None, mac: str) -> str | None:
    """根据厂商和 MAC 推断设备类型。"""
    if not vendor:
        return "unknown"

    vendor_lower = vendor.lower()

    if "cisco" in vendor_lower or "mikrotik" in vendor_lower or "ubiquiti" in vendor_lower:
        return "network_device"
    if "hp" in vendor_lower or "hewlett" in vendor_lower or "brother" in vendor_lower or "canon" in vendor_lower or "xerox" in vendor_lower:
        return "printer"
    if "raspberry" in vendor_lower:
        return "iot"
    if "dell" in vendor_lower or "lenovo" in vendor_lower:
        return "server"
    if "apple" in vendor_lower:
        return "workstation"
    if "vmware" in vendor_lower or "qemu" in vendor_lower:
        return "virtual"
    if "synology" in vendor_lower or "qnap" in vendor_lower:
        return "nas"

    return "unknown"


def collect_arp_table() -> list[ArpEntry]:
    """采集本机 ARP 表。

    自动识别平台并使用对应命令。
    """
    system = platform.system().lower()

    if system == "windows":
        return _collect_windows()
    else:
        return _collect_linux()


def _collect_windows() -> list[ArpEntry]:
    """Windows: 解析 `arp -a` 输出。"""
    try:
        completed = subprocess.run(
            ["arp", "-a"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise ArpCollectError(f"arp -a failed: {exc}") from exc

    return _parse_windows_arp(completed.stdout)


def _collect_linux() -> list[ArpEntry]:
    """Linux: 解析 `ip neigh` 或 `arp -n` 输出。"""
    # 优先使用 ip neigh
    try:
        completed = subprocess.run(
            ["ip", "neigh"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            return _parse_linux_ip_neigh(completed.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # 降级到 arp -n
    try:
        completed = subprocess.run(
            ["arp", "-n"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return _parse_linux_arp(completed.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise ArpCollectError(f"arp/ip neigh failed: {exc}") from exc


def _parse_windows_arp(output: str) -> list[ArpEntry]:
    """解析 Windows arp -a 输出。

    示例格式：
    Interface: 192.168.1.100 --- 0xa
      Internet Address      Physical Address    Type
      192.168.1.1           aa-bb-cc-dd-ee-ff   dynamic
      192.168.1.10          11-22-33-44-55-66   static
    """
    entries: list[ArpEntry] = []
    current_interface = ""

    for line in output.splitlines():
        line = line.strip()

        # 检测接口行
        if_match = re.match(r"Interface:\s*([\d.]+).*", line, re.IGNORECASE)
        if if_match:
            current_interface = if_match.group(1)
            continue

        # 匹配 ARP 条目行
        # IP  MAC  Type
        # MAC 格式: aa-bb-cc-dd-ee-ff (Windows 用 - 分隔)
        entry_match = re.match(
            r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+"
            r"([0-9a-fA-F]{2}-[0-9a-fA-F]{2}-[0-9a-fA-F]{2}-[0-9a-fA-F]{2}-[0-9a-fA-F]{2}-[0-9a-fA-F]{2})\s+"
            r"(\w+)",
            line,
        )
        if entry_match:
            ip = entry_match.group(1)
            mac = entry_match.group(2).replace("-", ":").lower()
            state = entry_match.group(3).lower()

            vendor = lookup_vendor(mac)
            device_type = infer_device_type(vendor, mac)

            entries.append(
                ArpEntry(
                    ip=ip,
                    mac=mac,
                    interface=current_interface,
                    state=state,
                    vendor=vendor,
                    device_type=device_type,
                )
            )

    return entries


def _parse_linux_ip_neigh(output: str) -> list[ArpEntry]:
    """解析 Linux `ip neigh` 输出。

    示例格式：
    192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE
    192.168.1.10 dev eth0 lladdr 11:22:33:44:55:66 STALE
    192.168.1.20 dev eth0 FAILED
    """
    entries: list[ArpEntry] = []

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue

        # 格式: IP dev IFACE lladdr MAC STATE
        match = re.match(
            r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+"
            r"dev\s+(\S+)\s+"
            r"(?:lladdr\s+([0-9a-fA-F:]{17})\s+)?"
            r"(\w+)?",
            line,
        )
        if match:
            ip = match.group(1)
            interface = match.group(2)
            mac = match.group(3).lower() if match.group(3) else ""
            state = match.group(4).lower() if match.group(4) else "unknown"

            if not mac:
                continue  # 跳过没有 MAC 的条目

            vendor = lookup_vendor(mac)
            device_type = infer_device_type(vendor, mac)

            entries.append(
                ArpEntry(
                    ip=ip,
                    mac=mac,
                    interface=interface,
                    state=state,
                    vendor=vendor,
                    device_type=device_type,
                )
            )

    return entries


def _parse_linux_arp(output: str) -> list[ArpEntry]:
    """解析 Linux `arp -n` 输出。

    示例格式：
    Address                  HWtype  HWaddress           Flags Mask  Iface
    192.168.1.1              ether   aa:bb:cc:dd:ee:ff   C           eth0
    192.168.1.10             ether   11:22:33:44:55:66   C           eth0
    """
    entries: list[ArpEntry] = []

    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("Address"):
            continue

        parts = line.split()
        if len(parts) >= 4 and parts[1] == "ether":
            ip = parts[0]
            mac = parts[2].lower()
            interface = parts[-1]

            vendor = lookup_vendor(mac)
            device_type = infer_device_type(vendor, mac)

            entries.append(
                ArpEntry(
                    ip=ip,
                    mac=mac,
                    interface=interface,
                    state="dynamic",
                    vendor=vendor,
                    device_type=device_type,
                )
            )

    return entries


class ArpCollectError(RuntimeError):
    pass
