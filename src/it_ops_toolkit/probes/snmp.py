"""SNMP v2c 探针：纯 Python 实现，不依赖外部库。

支持：
- SNMP v2c GET（单个 OID）
- SNMP v2c GETNEXT（用于 WALK）
- 高级接口 collect_snmp_info（一次采集常用设备信息）

不支持的：
- SNMP v3（需要认证框架，暂不实现）
- SET 操作（只读探针，符合第一阶段安全策略）
"""

from __future__ import annotations

import socket
import struct
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from it_ops_toolkit.models import ErrorInfo, ProbeResult, ProbeStatus, Target


class SnmpError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# 常用 OID 定义
# ---------------------------------------------------------------------------

SYSTEM_OIDS = {
    "sysDescr": "1.3.6.1.2.1.1.1.0",
    "sysObjectID": "1.3.6.1.2.1.1.2.0",
    "sysUpTime": "1.3.6.1.2.1.1.3.0",
    "sysContact": "1.3.6.1.2.1.1.4.0",
    "sysName": "1.3.6.1.2.1.1.5.0",
    "sysLocation": "1.3.6.1.2.1.1.6.0",
    "sysServices": "1.3.6.1.2.1.1.7.0",
    "ifNumber": "1.3.6.1.2.1.2.1.0",
}

# 用于 WALK 的子树根
IF_TABLE_OID = "1.3.6.1.2.1.2.2"
IF_DESCR_OID = "1.3.6.1.2.1.2.2.1.2"
IF_TYPE_OID = "1.3.6.1.2.1.2.2.1.3"
IF_OPER_STATUS_OID = "1.3.6.1.2.1.2.2.1.8"
IF_SPEED_OID = "1.3.6.1.2.1.2.2.1.5"


# ---------------------------------------------------------------------------
# BER 编码/解码（最小实现，仅覆盖 SNMP v2c 所需类型）
# ---------------------------------------------------------------------------

# BER 标签
_TAG_INTEGER = 0x02
_TAG_OCTET_STRING = 0x04
_TAG_NULL = 0x05
_TAG_OBJECT_IDENTIFIER = 0x06
_TAG_SEQUENCE = 0x30
_TAG_GET_REQUEST = 0xA0
_TAG_GET_NEXT_REQUEST = 0xA1
_TAG_GET_RESPONSE = 0xA2
_TAG_NO_SUCH_OBJECT = 0x80
_TAG_NO_SUCH_INSTANCE = 0x81
_TAG_END_OF_MIB_VIEW = 0x82


def _encode_length(length: int) -> bytes:
    """BER 编码长度字段。"""
    if length < 0x80:
        return bytes([length])
    # 长格式
    encoded = []
    while length > 0:
        encoded.insert(0, length & 0xFF)
        length >>= 8
    return bytes([0x80 | len(encoded), *encoded])


def _decode_length(data: bytes, offset: int) -> tuple[int, int]:
    """解码 BER 长度，返回 (length, new_offset)。"""
    if data[offset] < 0x80:
        return data[offset], offset + 1
    num_bytes = data[offset] & 0x7F
    offset += 1
    length = 0
    for _ in range(num_bytes):
        length = (length << 8) | data[offset]
        offset += 1
    return length, offset


def _encode_integer(value: int) -> bytes:
    """BER 编码整数。"""
    if value == 0:
        return bytes([_TAG_INTEGER, 0x01, 0x00])
    encoded = []
    val = value
    if value > 0:
        while val > 0:
            encoded.insert(0, val & 0xFF)
            val >>= 8
        if encoded[0] & 0x80:
            encoded.insert(0, 0)
    else:
        # 负数（SNMP 中很少用，但保持完整性）
        val = -value - 1
        while val >= 0:
            encoded.insert(0, (~val) & 0xFF)
            val = (val >> 8) - 1
            if val < 0:
                break
        if not (encoded[0] & 0x80):
            encoded.insert(0, 0xFF)
    content = bytes(encoded)
    return bytes([_TAG_INTEGER]) + _encode_length(len(content)) + content


def _decode_integer(data: bytes, offset: int) -> tuple[int, int]:
    """解码整数，返回 (value, new_offset)。"""
    # 跳过标签
    offset += 1
    length, offset = _decode_length(data, offset)
    value = 0
    for i in range(length):
        value = (value << 8) | data[offset + i]
    # 处理负数
    if data[offset] & 0x80:
        value -= 1 << (8 * length)
    offset += length
    return value, offset


def _encode_octet_string(value: str | bytes) -> bytes:
    """BER 编码字节串。"""
    if isinstance(value, str):
        content = value.encode("utf-8")
    else:
        content = value
    return bytes([_TAG_OCTET_STRING]) + _encode_length(len(content)) + content


def _decode_octet_string(data: bytes, offset: int) -> tuple[bytes, int]:
    """解码字节串，返回 (value, new_offset)。"""
    offset += 1  # 跳过标签
    length, offset = _decode_length(data, offset)
    value = data[offset : offset + length]
    offset += length
    return value, offset


def _encode_oid(oid: str) -> bytes:
    """BER 编码 OID。"""
    parts = [int(p) for p in oid.split(".")]
    if len(parts) < 2:
        raise SnmpError(f"invalid OID: {oid}")
    # 第一部分 = 40 * part[0] + part[1]
    encoded = [40 * parts[0] + parts[1]]
    for part in parts[2:]:
        if part == 0:
            encoded.append(0)
            continue
        sub_encoded = []
        val = part
        while val > 0:
            sub_encoded.insert(0, val & 0x7F)
            val >>= 7
        for i in range(len(sub_encoded) - 1):
            sub_encoded[i] |= 0x80
        encoded.extend(sub_encoded if sub_encoded else [0])
    content = bytes(encoded)
    return bytes([_TAG_OBJECT_IDENTIFIER]) + _encode_length(len(content)) + content


def _decode_oid(data: bytes, offset: int) -> tuple[str, int]:
    """解码 OID，返回 (oid_str, new_offset)。"""
    offset += 1  # 跳过标签
    length, offset = _decode_length(data, offset)
    end = offset + length
    parts = []
    # 第一个字节包含前两个子 OID
    first = data[offset]
    parts.append(first // 40)
    parts.append(first % 40)
    offset += 1
    while offset < end:
        val = 0
        while True:
            b = data[offset]
            offset += 1
            val = (val << 7) | (b & 0x7F)
            if not (b & 0x80):
                break
        parts.append(val)
    return ".".join(str(p) for p in parts), offset


def _encode_sequence(content: bytes) -> bytes:
    """编码 SEQUENCE。"""
    return bytes([_TAG_SEQUENCE]) + _encode_length(len(content)) + content


def _encode_null() -> bytes:
    """编码 NULL。"""
    return bytes([_TAG_NULL, 0x00])


# ---------------------------------------------------------------------------
# SNMP 消息构建与解析
# ---------------------------------------------------------------------------


def _build_get_request(
    community: str,
    request_id: int,
    oid: str,
    is_next: bool = False,
) -> bytes:
    """构建 SNMP v2c GET/GETNEXT 请求消息。"""
    # VarBind: (oid, null)
    varbind = _encode_sequence(_encode_oid(oid) + _encode_null())

    # VarBindList
    varbind_list = _encode_sequence(varbind)

    # PDU (GetRequestPDU 或 GetNextRequestPDU)
    pdu_tag = _TAG_GET_NEXT_REQUEST if is_next else _TAG_GET_REQUEST
    pdu_content = (
        _encode_integer(request_id)
        + _encode_integer(0)  # error-status
        + _encode_integer(0)  # error-index
        + varbind_list
    )
    pdu = bytes([pdu_tag]) + _encode_length(len(pdu_content)) + pdu_content

    # SNMP Message: version (1=v2c) + community + pdu
    message = _encode_sequence(
        _encode_integer(1)  # version: SNMPv2c = 1
        + _encode_octet_string(community)
        + pdu
    )
    return message


def _parse_response(response: bytes) -> tuple[str, bytes, int]:
    """解析 SNMP 响应，返回 (oid, value_bytes, pdu_error_status)。

    返回的 value_bytes 可能需要进一步解码为具体类型。
    如果是 NoSuchObject/NoSuchInstance/EndOfMibView，返回特殊标记。
    """
    offset = 0

    # Message SEQUENCE
    assert response[offset] == _TAG_SEQUENCE
    offset += 1
    msg_len, offset = _decode_length(response, offset)

    # Version
    version, offset = _decode_integer(response, offset)
    if version != 1:
        raise SnmpError(f"unsupported SNMP version in response: {version}")

    # Community
    community_bytes, offset = _decode_octet_string(response, offset)

    # PDU
    pdu_tag = response[offset]
    if pdu_tag != _TAG_GET_RESPONSE:
        raise SnmpError(f"unexpected PDU tag: 0x{pdu_tag:02X}")
    offset += 1
    pdu_len, offset = _decode_length(response, offset)

    # request-id
    req_id, offset = _decode_integer(response, offset)
    # error-status
    error_status, offset = _decode_integer(response, offset)
    # error-index
    error_index, offset = _decode_integer(response, offset)

    # VarBindList
    assert response[offset] == _TAG_SEQUENCE
    offset += 1
    vbl_len, offset = _decode_length(response, offset)

    # VarBind
    assert response[offset] == _TAG_SEQUENCE
    offset += 1
    vb_len, offset = _decode_length(response, offset)

    # OID
    oid, offset = _decode_oid(response, offset)

    # Value
    value_tag = response[offset]
    if value_tag == _TAG_NO_SUCH_OBJECT:
        return oid, b"\x80", error_status
    if value_tag == _TAG_NO_SUCH_INSTANCE:
        return oid, b"\x81", error_status
    if value_tag == _TAG_END_OF_MIB_VIEW:
        return oid, b"\x82", error_status

    # 解码值
    value_len, value_offset = _decode_length(response, offset + 1)
    value_start = value_offset
    value_end = value_offset + value_len
    value_bytes = response[value_start:value_end]

    return oid, value_bytes, error_status


def _decode_value(tag: int, value_bytes: bytes) -> str | int:
    """根据标签解码值。"""
    if tag == _TAG_INTEGER:
        val = 0
        for b in value_bytes:
            val = (val << 8) | b
        if value_bytes and value_bytes[0] & 0x80:
            val -= 1 << (8 * len(value_bytes))
        return val
    if tag == _TAG_OCTET_STRING:
        try:
            return value_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return value_bytes.hex()
    if tag == _TAG_OBJECT_IDENTIFIER:
        # 重新解码 OID
        fake_data = bytes([_TAG_OBJECT_IDENTIFIER]) + _encode_length(len(value_bytes)) + value_bytes
        oid, _ = _decode_oid(fake_data, 0)
        return oid
    # 未知类型，返回十六进制
    return value_bytes.hex()


def _get_raw_value(response: bytes) -> tuple[str, int, bytes]:
    """解析响应，返回 (oid, value_tag, value_bytes)。"""
    oid, value_bytes, error_status = _parse_response(response)
    # 找到值的 tag
    offset = 0
    # 重新解析以获取 value tag
    # Message SEQUENCE
    offset += 1
    _, offset = _decode_length(response, offset)
    # Version
    _, offset = _decode_integer(response, offset)
    # Community
    _, offset = _decode_octet_string(response, offset)
    # PDU
    offset += 1
    _, offset = _decode_length(response, offset)
    # request-id, error-status, error-index
    _, offset = _decode_integer(response, offset)
    _, offset = _decode_integer(response, offset)
    _, offset = _decode_integer(response, offset)
    # VarBindList
    offset += 1
    _, offset = _decode_length(response, offset)
    # VarBind
    offset += 1
    _, offset = _decode_length(response, offset)
    # OID
    _, offset = _decode_oid(response, offset)
    # Value tag
    value_tag = response[offset]
    return oid, value_tag, value_bytes


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def snmp_get(
    *,
    target: str,
    oid: str,
    community: str = "public",
    port: int = 161,
    timeout_ms: int = 3000,
) -> tuple[str, str | int]:
    """执行 SNMP v2c GET 请求。

    返回 (oid, value)。
    如果 OID 不存在，抛出 SnmpError。
    """
    request_id = 1
    message = _build_get_request(community, request_id, oid, is_next=False)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(max(timeout_ms / 1000, 0.1))
    try:
        sock.sendto(message, (target, port))
        response, _ = sock.recvfrom(65535)
    except socket.timeout as exc:
        raise SnmpError(f"SNMP GET timeout: {target}:{port} OID={oid}") from exc
    except OSError as exc:
        raise SnmpError(f"SNMP GET error: {exc}") from exc
    finally:
        sock.close()

    oid_resp, value_tag, value_bytes = _get_raw_value(response)

    if value_tag in (_TAG_NO_SUCH_OBJECT, _TAG_NO_SUCH_INSTANCE):
        raise SnmpError(f"no such object: {oid}")
    if value_tag == _TAG_END_OF_MIB_VIEW:
        raise SnmpError(f"end of MIB view: {oid}")

    value = _decode_value(value_tag, value_bytes)
    return oid_resp, value


def snmp_getnext(
    *,
    target: str,
    oid: str,
    community: str = "public",
    port: int = 161,
    timeout_ms: int = 3000,
) -> tuple[str, str | int]:
    """执行 SNMP v2c GETNEXT 请求。

    返回 (next_oid, value)。
    如果到达 MIB 末尾，抛出 SnmpError。
    """
    request_id = 1
    message = _build_get_request(community, request_id, oid, is_next=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(max(timeout_ms / 1000, 0.1))
    try:
        sock.sendto(message, (target, port))
        response, _ = sock.recvfrom(65535)
    except socket.timeout as exc:
        raise SnmpError(f"SNMP GETNEXT timeout: {target}:{port} OID={oid}") from exc
    except OSError as exc:
        raise SnmpError(f"SNMP GETNEXT error: {exc}") from exc
    finally:
        sock.close()

    oid_resp, value_tag, value_bytes = _get_raw_value(response)

    if value_tag == _TAG_END_OF_MIB_VIEW:
        raise SnmpError(f"end of MIB view: {oid}")

    value = _decode_value(value_tag, value_bytes)
    return oid_resp, value


def snmp_walk(
    *,
    target: str,
    oid: str,
    community: str = "public",
    port: int = 161,
    timeout_ms: int = 3000,
    max_repetitions: int = 50,
) -> list[tuple[str, str | int]]:
    """执行 SNMP WALK（使用 GETNEXT 遍历子树）。

    返回 [(oid, value), ...]。
    当返回的 OID 不再以指定前缀开头时停止。
    """
    results: list[tuple[str, str | int]] = []
    current_oid = oid

    for _ in range(max_repetitions):
        try:
            next_oid, value = snmp_getnext(
                target=target,
                oid=current_oid,
                community=community,
                port=port,
                timeout_ms=timeout_ms,
            )
        except SnmpError:
            break

        # 检查是否还在子树内
        if not next_oid.startswith(oid + ".") and next_oid != oid:
            break

        results.append((next_oid, value))
        current_oid = next_oid

    return results


def collect_snmp_info(
    *,
    task_id: str,
    target: str,
    community: str = "public",
    port: int = 161,
    timeout_ms: int = 3000,
) -> ProbeResult:
    """采集 SNMP 设备基础信息。

    采集 sysDescr、sysObjectID、sysUpTime、sysContact、sysName、sysLocation、
    sysServices、ifNumber，以及接口表基础信息。
    """
    started = datetime.now(UTC)
    start = monotonic()

    observations: dict[str, object] = {
        "target": target,
        "community": community,
        "port": port,
    }
    error: ErrorInfo | None = None
    status = ProbeStatus.success

    # 采集系统信息
    for name, oid in SYSTEM_OIDS.items():
        try:
            _, value = snmp_get(
                target=target,
                oid=oid,
                community=community,
                port=port,
                timeout_ms=timeout_ms,
            )
            observations[name] = value
        except SnmpError:
            observations[name] = None

    # 如果连 sysDescr 都获取不到，说明设备不可达或不支持 SNMP
    if observations.get("sysDescr") is None and observations.get("sysName") is None:
        status = ProbeStatus.failed
        error = ErrorInfo(
            code="snmp_unreachable",
            message="SNMP device unreachable or not responding",
            detail=f"target={target}:{port}, community={community}",
            retryable=True,
        )

    # 采集接口表基础信息
    if status == ProbeStatus.success:
        try:
            if_descr_results = snmp_walk(
                target=target,
                oid=IF_DESCR_OID,
                community=community,
                port=port,
                timeout_ms=timeout_ms,
            )
            if_status_results = snmp_walk(
                target=target,
                oid=IF_OPER_STATUS_OID,
                community=community,
                port=port,
                timeout_ms=timeout_ms,
            )

            interfaces = []
            for i, (oid, name) in enumerate(if_descr_results):
                iface: dict[str, object] = {"index": i + 1, "descr": name}
                if i < len(if_status_results):
                    iface["oper_status"] = if_status_results[i][1]
                interfaces.append(iface)

            observations["interfaces"] = interfaces
            observations["interface_count"] = len(interfaces)
        except SnmpError:
            observations["interfaces"] = []
            observations["interface_count"] = 0

    duration_ms = int((monotonic() - start) * 1000)

    return ProbeResult(
        id=f"probe-snmp-{target}-{uuid4().hex[:8]}",
        task_id=task_id,
        probe_type="snmp",
        target=Target(type="ip", value=target),
        status=status,
        started_at=started,
        ended_at=datetime.now(UTC),
        duration_ms=duration_ms,
        observations=observations,
        error=error,
        evidence={
            "protocol": "SNMPv2c",
            "port": port,
        },
    )
