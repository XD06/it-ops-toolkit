from __future__ import annotations

import getpass
import json
import os
import platform as platform_module
import shutil
import socket
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from .models import LocalInterface, LocalSnapshot, TaskRun
from .storage import SQLiteStore


CommandRunner = Callable[[list[str], int], "CommandOutput"]

PROXY_ENV_NAMES = [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
]


@dataclass(frozen=True)
class CommandOutput:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class NetworkCollection:
    interfaces: list[LocalInterface]
    default_routes: list[dict[str, object]]
    dns_servers: list[str]
    observations: dict[str, object]
    raw: dict[str, object]


def collect_local_snapshot(
    *,
    task: TaskRun,
    store: SQLiteStore,
    command_runner: CommandRunner | None = None,
) -> LocalSnapshot:
    runner = command_runner or _run_command
    system_name = platform_module.system()
    network = _collect_network(system_name=system_name, runner=runner)
    interfaces = network.interfaces or _fallback_interfaces()
    dns_servers = _unique(
        [
            *network.dns_servers,
            *[
                server
                for interface in interfaces
                for server in interface.dns_servers
            ],
        ]
    )

    snapshot = LocalSnapshot(
        id=f"local-{uuid4().hex[:12]}",
        task_id=task.id,
        collected_at=datetime.now(UTC),
        hostname=socket.gethostname(),
        fqdn=_safe_fqdn(),
        username=_safe_username(),
        os_name=platform_module.platform(),
        platform=system_name,
        interfaces=interfaces,
        default_routes=network.default_routes,
        dns_servers=dns_servers,
        proxy=_collect_proxy_settings(system_name=system_name, runner=runner),
        observations={
            **network.observations,
            "interface_count": len(interfaces),
            "dns_server_count": len(dns_servers),
            "default_route_count": len(network.default_routes),
        },
        raw=network.raw,
    )
    store.save_local_snapshot(snapshot)
    return snapshot


def _collect_network(*, system_name: str, runner: CommandRunner) -> NetworkCollection:
    if system_name.lower() == "windows":
        collected = _collect_windows_network(runner)
        if collected.interfaces or collected.default_routes or collected.dns_servers:
            return collected

    return _collect_generic_network(runner)


def _collect_windows_network(runner: CommandRunner) -> NetworkCollection:
    executable = _powershell_executable()
    script = r"""
$ErrorActionPreference = 'SilentlyContinue'
$ipConfigs = @(Get-NetIPConfiguration | ForEach-Object {
    [pscustomobject]@{
        interface_alias = $_.InterfaceAlias
        interface_description = $_.InterfaceDescription
        interface_index = $_.InterfaceIndex
        net_adapter_status = if ($_.NetAdapter) { $_.NetAdapter.Status } else { $null }
        net_profile_name = if ($_.NetProfile) { $_.NetProfile.Name } else { $null }
        ipv4_addresses = @($_.IPv4Address | ForEach-Object { $_.IPAddress })
        ipv6_addresses = @($_.IPv6Address | ForEach-Object { $_.IPAddress })
        ipv4_default_gateways = @($_.IPv4DefaultGateway | ForEach-Object { $_.NextHop })
        dns_servers = @($_.DNSServer.ServerAddresses)
    }
})
$routes = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | ForEach-Object {
    [pscustomobject]@{
        interface_alias = $_.InterfaceAlias
        destination_prefix = $_.DestinationPrefix
        next_hop = $_.NextHop
        route_metric = $_.RouteMetric
        interface_index = $_.ifIndex
    }
})
$dns = @(Get-DnsClientServerAddress | ForEach-Object {
    [pscustomobject]@{
        interface_alias = $_.InterfaceAlias
        address_family = $_.AddressFamily
        server_addresses = @($_.ServerAddresses)
    }
})
[pscustomobject]@{
    ip_configurations = $ipConfigs
    default_routes = $routes
    dns_client_servers = $dns
} | ConvertTo-Json -Depth 8
"""
    output = runner(
        [
            executable,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        15,
    )
    raw: dict[str, object] = {
        "windows_network_command": {
            "returncode": output.returncode,
            "stderr": output.stderr.strip(),
        }
    }
    observations: dict[str, object] = {}
    if output.returncode != 0:
        observations["windows_network_command_failed"] = True
        return NetworkCollection([], [], [], observations, raw)

    raw["windows_network"] = _json_or_text(output.stdout)
    try:
        interfaces, routes, dns_servers = _parse_windows_network_json(output.stdout)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        observations["windows_network_parse_error"] = str(exc)
        return NetworkCollection([], [], [], observations, raw)

    return NetworkCollection(
        interfaces=interfaces,
        default_routes=routes,
        dns_servers=dns_servers,
        observations=observations,
        raw=raw,
    )


def _parse_windows_network_json(
    payload: str,
) -> tuple[list[LocalInterface], list[dict[str, object]], list[str]]:
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("PowerShell network payload must be an object")

    interfaces: list[LocalInterface] = []
    for item in _as_list(data.get("ip_configurations")):
        if not isinstance(item, dict):
            continue
        name = _string_or_none(item.get("interface_alias"))
        if not name:
            index = _string_or_none(item.get("interface_index")) or "unknown"
            name = f"interface-{index}"
        interfaces.append(
            LocalInterface(
                name=name,
                description=_string_or_none(item.get("interface_description")),
                status=_string_or_none(item.get("net_adapter_status")),
                ipv4_addresses=_strings(item.get("ipv4_addresses")),
                ipv6_addresses=_strings(item.get("ipv6_addresses")),
                default_gateways=_strings(item.get("ipv4_default_gateways")),
                dns_servers=_strings(item.get("dns_servers")),
            )
        )

    routes: list[dict[str, object]] = []
    for item in _as_list(data.get("default_routes")):
        if not isinstance(item, dict):
            continue
        routes.append(
            {
                "interface_alias": _string_or_none(item.get("interface_alias")),
                "destination_prefix": _string_or_none(item.get("destination_prefix")),
                "next_hop": _string_or_none(item.get("next_hop")),
                "route_metric": item.get("route_metric"),
                "interface_index": item.get("interface_index"),
            }
        )

    dns_servers = _unique(
        [
            server
            for item in _as_list(data.get("dns_client_servers"))
            if isinstance(item, dict)
            for server in _strings(item.get("server_addresses"))
        ]
    )
    if not dns_servers:
        dns_servers = _unique(
            [server for interface in interfaces for server in interface.dns_servers]
        )
    return interfaces, routes, dns_servers


def _collect_generic_network(runner: CommandRunner) -> NetworkCollection:
    observations: dict[str, object] = {"generic_network_fallback": True}
    raw: dict[str, object] = {}
    routes: list[dict[str, object]] = []
    dns_servers = _read_resolv_conf()

    ip_executable = shutil.which("ip")
    if ip_executable:
        route_output = runner([ip_executable, "route"], 5)
        raw["ip_route"] = {
            "returncode": route_output.returncode,
            "stdout": route_output.stdout,
            "stderr": route_output.stderr,
        }
        routes.extend(_parse_ip_route(route_output.stdout))

    return NetworkCollection(
        interfaces=_fallback_interfaces(),
        default_routes=routes,
        dns_servers=dns_servers,
        observations=observations,
        raw=raw,
    )


def _collect_proxy_settings(*, system_name: str, runner: CommandRunner) -> dict[str, object]:
    proxy: dict[str, object] = {
        "environment": {
            name: _redact_proxy_value(value)
            for name in PROXY_ENV_NAMES
            if (value := os.environ.get(name))
        }
    }
    if system_name.lower() != "windows":
        return proxy

    proxy["windows_internet_settings"] = _read_windows_internet_settings()
    winhttp = runner(["netsh", "winhttp", "show", "proxy"], 5)
    proxy["windows_winhttp"] = {
        "returncode": winhttp.returncode,
        "summary": _redact_proxy_text(winhttp.stdout.strip()),
        "stderr": winhttp.stderr.strip(),
    }
    return proxy


def _read_windows_internet_settings() -> dict[str, object]:
    try:
        import winreg
    except ImportError:
        return {}

    values: dict[str, object] = {}
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        ) as key:
            for name in ("ProxyEnable", "ProxyServer", "AutoConfigURL"):
                try:
                    value, _ = winreg.QueryValueEx(key, name)
                except OSError:
                    continue
                values[name] = _redact_proxy_value(str(value))
    except OSError:
        return {}
    return values


def _fallback_interfaces() -> list[LocalInterface]:
    ipv4: list[str] = []
    ipv6: list[str] = []
    try:
        for family, _, _, _, sockaddr in socket.getaddrinfo(socket.gethostname(), None):
            address = sockaddr[0]
            if family == socket.AF_INET:
                ipv4.append(address)
            elif family == socket.AF_INET6:
                ipv6.append(address)
    except OSError:
        return []

    ipv4 = _unique(ipv4)
    ipv6 = _unique(ipv6)
    if not ipv4 and not ipv6:
        return []
    return [
        LocalInterface(
            name="hostname_resolution",
            description="Addresses resolved from local hostname",
            ipv4_addresses=ipv4,
            ipv6_addresses=ipv6,
        )
    ]


def _parse_ip_route(output: str) -> list[dict[str, object]]:
    routes: list[dict[str, object]] = []
    for line in output.splitlines():
        parts = line.split()
        if not parts or parts[0] != "default":
            continue
        route: dict[str, object] = {"raw": line}
        if "via" in parts:
            route["next_hop"] = parts[parts.index("via") + 1]
        if "dev" in parts:
            route["interface_alias"] = parts[parts.index("dev") + 1]
        routes.append(route)
    return routes


def _read_resolv_conf() -> list[str]:
    path = Path("/etc/resolv.conf")
    if not path.exists():
        return []
    servers: list[str] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] == "nameserver":
                servers.append(parts[1])
    except OSError:
        return []
    return _unique(servers)


def _run_command(args: list[str], timeout_seconds: int) -> CommandOutput:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            creationflags=creationflags,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandOutput(
            args=args,
            returncode=-2,
            stdout=exc.stdout or "",
            stderr=f"command timed out after {timeout_seconds}s",
        )
    except OSError as exc:
        return CommandOutput(args=args, returncode=-1, stdout="", stderr=str(exc))

    return CommandOutput(
        args=args,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _powershell_executable() -> str:
    for command in ("powershell.exe", "powershell", "pwsh"):
        executable = shutil.which(command)
        if executable:
            return executable
    return "powershell.exe"


def _safe_fqdn() -> str | None:
    try:
        return socket.getfqdn()
    except OSError:
        return None


def _safe_username() -> str | None:
    try:
        return getpass.getuser()
    except (KeyError, OSError):
        return None


def _json_or_text(value: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value.strip()


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _strings(value: object) -> list[str]:
    return [
        item
        for item in (_string_or_none(item) for item in _as_list(value))
        if item
    ]


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _redact_proxy_text(text: str) -> str:
    words = text.split()
    redacted: list[str] = []
    for word in words:
        redacted.append(_redact_proxy_value(word) if "://" in word else word)
    return " ".join(redacted)


def _redact_proxy_value(value: str) -> str:
    if "://" not in value:
        return value

    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if not parsed.username and not parsed.password:
        return value

    hostname = parsed.hostname or ""
    netloc = hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
