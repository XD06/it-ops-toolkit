"""Traceroute Adapter。

跨平台支持：
- Windows: `tracert -d -h 15` 命令输出解析。
- Linux: `traceroute -n -m 15` 或 `tracepath -n` 命令输出解析。

输出 TraceRouteResult，包含每一跳的 IP、RTT 和超时信息。
"""

from __future__ import annotations

import platform
import re
import socket
import subprocess

from ..models import TraceRouteHop, TraceRouteResult


class TraceRouteError(RuntimeError):
    pass


def run_traceroute(
    *,
    target: str,
    max_hops: int = 15,
    timeout_seconds: int = 30,
) -> TraceRouteResult:
    """执行路由追踪。

    Args:
        target: 目标主机（IP 或主机名）。
        max_hops: 最大跳数。
        timeout_seconds: 总超时秒数。

    Returns:
        TraceRouteResult 包含每一跳信息。
    """
    source = _get_local_ip()

    system = platform.system().lower()
    if system == "windows":
        raw_output = _run_windows_tracert(target, max_hops, timeout_seconds)
        hops = _parse_windows_tracert(raw_output)
    else:
        raw_output = _run_linux_traceroute(target, max_hops, timeout_seconds)
        hops = _parse_linux_traceroute(raw_output)

    reached = _check_reached(hops, target)

    return TraceRouteResult(
        target=target,
        source=source,
        hops=hops,
        total_hops=len(hops),
        reached=reached,
        raw_output=raw_output,
    )


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


def _run_windows_tracert(target: str, max_hops: int, timeout: int) -> str:
    """Windows: tracert -d -h max_hops target"""
    try:
        completed = subprocess.run(
            ["tracert", "-d", "-h", str(max_hops), target],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        return completed.stdout or ""
    except subprocess.TimeoutExpired as exc:
        raise TraceRouteError(f"tracert timed out after {timeout}s") from exc
    except FileNotFoundError as exc:
        raise TraceRouteError("tracert command not found") from exc


def _run_linux_traceroute(target: str, max_hops: int, timeout: int) -> str:
    """Linux: traceroute -n -m max_hops target (或 tracepath)"""
    # 优先使用 traceroute
    try:
        completed = subprocess.run(
            ["traceroute", "-n", "-m", str(max_hops), target],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if completed.returncode == 0 or completed.stdout.strip():
            return completed.stdout or ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # 降级到 tracepath
    try:
        completed = subprocess.run(
            ["tracepath", "-n", target],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return completed.stdout or ""
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise TraceRouteError(f"traceroute/tracepath failed: {exc}") from exc


def _parse_windows_tracert(output: str) -> list[TraceRouteHop]:
    """解析 Windows tracert 输出。

    示例格式：
    Tracing route to 8.8.8.8 over a maximum of 15 hops

      1     1 ms     1 ms     1 ms  192.168.1.1
      2     5 ms     4 ms     5 ms  10.0.0.1
      3     *        *        *     Request timed out.
      4    12 ms    11 ms    12 ms  8.8.8.8

    Trace complete.
    """
    hops: list[TraceRouteHop] = []

    for line in output.splitlines():
        line = line.strip()

        # 匹配跳数行
        # 格式:  N  RTT1  RTT2  RTT3  IP  或  N  *  *  *  Request timed out.
        match = re.match(
            r"^\s*(\d+)\s+(.*)$",
            line,
        )
        if not match:
            continue

        hop_num = int(match.group(1))
        rest = match.group(2)

        # 检查是否超时
        if "*" in rest and "timed out" in rest.lower():
            hops.append(
                TraceRouteHop(
                    hop=hop_num,
                    ip=None,
                    rtt_ms=[],
                    timeout=True,
                )
            )
            continue

        # 提取 RTT 值（所有 ms 数值）和 IP
        rtts = re.findall(r"(\d+)\s*ms", rest)
        # 提取 IP 地址（最后一个 IP 格式字符串）
        ip_match = re.findall(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", rest)

        ip = ip_match[-1] if ip_match else None
        rtt_values = [float(r) for r in rtts] if rtts else []

        hops.append(
            TraceRouteHop(
                hop=hop_num,
                ip=ip,
                rtt_ms=rtt_values,
                timeout=ip is None,
            )
        )

    return hops


def _parse_linux_traceroute(output: str) -> list[TraceRouteHop]:
    """解析 Linux traceroute 输出。

    示例格式：
    traceroute to 8.8.8.8 (8.8.8.8), 15 hops max, 60 byte packets
     1  192.168.1.1 (192.168.1.1)  1.234 ms  1.456 ms  1.789 ms
     2  10.0.0.1 (10.0.0.1)  5.123 ms  5.456 ms  5.789 ms
     3  * * *
     4  8.8.8.8 (8.8.8.8)  12.345 ms  12.678 ms  12.901 ms
    """
    hops: list[TraceRouteHop] = []

    for line in output.splitlines():
        line = line.strip()

        # 跳过标题行
        if line.startswith("traceroute to") or line.startswith("tracepath to"):
            continue

        # 匹配跳数行
        match = re.match(r"^\s*(\d+)\s+(.*)$", line)
        if not match:
            continue

        hop_num = int(match.group(1))
        rest = match.group(2)

        # 检查是否超时
        if rest.strip() == "* * *" or rest.strip().startswith("*"):
            hops.append(
                TraceRouteHop(
                    hop=hop_num,
                    ip=None,
                    rtt_ms=[],
                    timeout=True,
                )
            )
            continue

        # 提取 IP（第一个括号前的 IP 或括号内的 IP）
        ip_match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", rest)
        ip = ip_match.group(1) if ip_match else None

        # 提取 RTT 值
        rtts = re.findall(r"([\d.]+)\s*ms", rest)
        rtt_values = [float(r) for r in rtts] if rtts else []

        hops.append(
            TraceRouteHop(
                hop=hop_num,
                ip=ip,
                rtt_ms=rtt_values,
                timeout=ip is None,
            )
        )

    return hops


def _check_reached(hops: list[TraceRouteHop], target: str) -> bool:
    """检查 traceroute 是否到达目标。

    如果最后一跳的 IP 等于目标 IP（或目标 IP 的解析结果），则认为到达。
    """
    if not hops:
        return False

    last_hop = hops[-1]
    if last_hop.timeout or last_hop.ip is None:
        return False

    # 直接比较 IP
    if last_hop.ip == target:
        return True

    # 尝试解析目标主机名
    try:
        resolved = socket.gethostbyname(target)
        if last_hop.ip == resolved:
            return True
    except socket.gaierror:
        pass

    # 如果最后一跳不是超时且 IP 不为空，也认为可能到达
    return False
