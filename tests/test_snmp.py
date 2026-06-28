"""SNMP 探针测试。

测试 BER 编码/解码、消息构建、以及 collect_snmp_info 的结构化输出。
不依赖真实网络设备。
"""

import socket
import threading
import unittest
from unittest.mock import patch

from it_ops_toolkit.models import ProbeStatus
from it_ops_toolkit.probes.snmp import (
    SnmpError,
    _build_get_request,
    _decode_integer,
    _decode_length,
    _decode_octet_string,
    _decode_oid,
    _decode_value,
    _encode_integer,
    _encode_length,
    _encode_null,
    _encode_octet_string,
    _encode_oid,
    _encode_sequence,
    _get_raw_value,
    _parse_response,
    _TAG_END_OF_MIB_VIEW,
    _TAG_GET_RESPONSE,
    _TAG_INTEGER,
    _TAG_NO_SUCH_INSTANCE,
    _TAG_NO_SUCH_OBJECT,
    _TAG_OCTET_STRING,
    _TAG_SEQUENCE,
    collect_snmp_info,
    snmp_get,
    snmp_getnext,
)


class BerEncodeTests(unittest.TestCase):
    """BER 编码测试。"""

    def test_encode_length_short(self) -> None:
        self.assertEqual(_encode_length(5), b"\x05")
        self.assertEqual(_encode_length(0), b"\x00")
        self.assertEqual(_encode_length(127), b"\x7f")

    def test_encode_length_long(self) -> None:
        self.assertEqual(_encode_length(128), b"\x81\x80")
        self.assertEqual(_encode_length(256), b"\x82\x01\x00")

    def test_decode_length_short(self) -> None:
        length, offset = _decode_length(b"\x05", 0)
        self.assertEqual(length, 5)
        self.assertEqual(offset, 1)

    def test_decode_length_long(self) -> None:
        length, offset = _decode_length(b"\x81\x80", 0)
        self.assertEqual(length, 128)
        self.assertEqual(offset, 2)

    def test_encode_integer_zero(self) -> None:
        result = _encode_integer(0)
        self.assertEqual(result[0], _TAG_INTEGER)
        self.assertEqual(result[1], 1)  # length
        self.assertEqual(result[2], 0)

    def test_encode_integer_positive(self) -> None:
        result = _encode_integer(42)
        self.assertEqual(result, b"\x02\x01\x2a")

    def test_encode_integer_large(self) -> None:
        result = _encode_integer(256)
        self.assertEqual(result, b"\x02\x02\x01\x00")

    def test_encode_integer_high_bit(self) -> None:
        # 200 = 0xC8, high bit set, needs leading zero
        result = _encode_integer(200)
        self.assertEqual(result, b"\x02\x02\x00\xc8")

    def test_decode_integer(self) -> None:
        value, offset = _decode_integer(b"\x02\x01\x2a", 0)
        self.assertEqual(value, 42)

    def test_decode_integer_negative(self) -> None:
        value, _ = _decode_integer(b"\x02\x01\xff", 0)
        self.assertEqual(value, -1)

    def test_encode_octet_string(self) -> None:
        result = _encode_octet_string("hello")
        self.assertEqual(result, b"\x04\x05hello")

    def test_decode_octet_string(self) -> None:
        value, _ = _decode_octet_string(b"\x04\x05hello", 0)
        self.assertEqual(value, b"hello")

    def test_encode_oid(self) -> None:
        # 1.3.6.1.2.1.1.1.0 -> sysDescr.0
        result = _encode_oid("1.3.6.1.2.1.1.1.0")
        # First byte = 40*1 + 3 = 43 = 0x2B
        self.assertEqual(result[0], 0x06)  # TAG
        self.assertEqual(result[2], 0x2B)  # 40*1+3

    def test_encode_oid_simple(self) -> None:
        result = _encode_oid("1.3.6.1")
        self.assertEqual(result[0], 0x06)
        self.assertEqual(result[2], 0x2B)  # 40*1+3
        self.assertEqual(result[3], 0x06)
        self.assertEqual(result[4], 0x01)

    def test_decode_oid(self) -> None:
        encoded = _encode_oid("1.3.6.1.2.1.1.1.0")
        oid, _ = _decode_oid(encoded, 0)
        self.assertEqual(oid, "1.3.6.1.2.1.1.1.0")

    def test_encode_null(self) -> None:
        self.assertEqual(_encode_null(), b"\x05\x00")

    def test_encode_sequence(self) -> None:
        result = _encode_sequence(b"\x01\x02")
        self.assertEqual(result[0], _TAG_SEQUENCE)
        self.assertEqual(result[1], 2)
        self.assertEqual(result[2:], b"\x01\x02")


class SnmpMessageTests(unittest.TestCase):
    """SNMP 消息构建与解析测试。"""

    def test_build_get_request_structure(self) -> None:
        msg = _build_get_request("public", 1, "1.3.6.1.2.1.1.1.0")
        # 消息应以 SEQUENCE 标签开头
        self.assertEqual(msg[0], _TAG_SEQUENCE)

    def test_build_getnext_request(self) -> None:
        msg = _build_get_request("public", 1, "1.3.6.1.2.1.1.1.0", is_next=True)
        self.assertEqual(msg[0], _TAG_SEQUENCE)

    def test_build_get_request_contains_community(self) -> None:
        msg = _build_get_request("private", 1, "1.3.6.1.2.1.1.1.0")
        self.assertIn(b"private", msg)

    def test_parse_response_with_integer_value(self) -> None:
        """构建一个模拟的 SNMP GET RESPONSE 并解析。"""
        # 手动构建响应消息
        # VarBind: OID + Integer value
        oid_encoded = _encode_oid("1.3.6.1.2.1.1.3.0")
        value_encoded = _encode_integer(12345)
        varbind = _encode_sequence(oid_encoded + value_encoded)
        varbind_list = _encode_sequence(varbind)

        # PDU: GetResponse
        pdu_content = (
            _encode_integer(1)  # request-id
            + _encode_integer(0)  # error-status
            + _encode_integer(0)  # error-index
            + varbind_list
        )
        pdu = bytes([_TAG_GET_RESPONSE]) + _encode_length(len(pdu_content)) + pdu_content

        # Message
        msg = _encode_sequence(
            _encode_integer(1)  # version v2c
            + _encode_octet_string("public")
            + pdu
        )

        oid, value_bytes, error_status = _parse_response(msg)
        self.assertEqual(oid, "1.3.6.1.2.1.1.3.0")
        self.assertEqual(error_status, 0)

    def test_parse_response_with_string_value(self) -> None:
        """构建包含字符串值的响应。"""
        oid_encoded = _encode_oid("1.3.6.1.2.1.1.1.0")
        value_encoded = _encode_octet_string("Linux Router 1.0")
        varbind = _encode_sequence(oid_encoded + value_encoded)
        varbind_list = _encode_sequence(varbind)

        pdu_content = (
            _encode_integer(1)
            + _encode_integer(0)
            + _encode_integer(0)
            + varbind_list
        )
        pdu = bytes([_TAG_GET_RESPONSE]) + _encode_length(len(pdu_content)) + pdu_content

        msg = _encode_sequence(
            _encode_integer(1)
            + _encode_octet_string("public")
            + pdu
        )

        oid, _, _ = _parse_response(msg)
        self.assertEqual(oid, "1.3.6.1.2.1.1.1.0")

    def test_get_raw_value_returns_tag(self) -> None:
        """测试 _get_raw_value 返回正确的 value_tag。"""
        oid_encoded = _encode_oid("1.3.6.1.2.1.1.3.0")
        value_encoded = _encode_integer(99)
        varbind = _encode_sequence(oid_encoded + value_encoded)
        varbind_list = _encode_sequence(varbind)

        pdu_content = (
            _encode_integer(1)
            + _encode_integer(0)
            + _encode_integer(0)
            + varbind_list
        )
        pdu = bytes([_TAG_GET_RESPONSE]) + _encode_length(len(pdu_content)) + pdu_content

        msg = _encode_sequence(
            _encode_integer(1)
            + _encode_octet_string("public")
            + pdu
        )

        oid, value_tag, value_bytes = _get_raw_value(msg)
        self.assertEqual(oid, "1.3.6.1.2.1.1.3.0")
        self.assertEqual(value_tag, _TAG_INTEGER)

    def test_decode_value_integer(self) -> None:
        result = _decode_value(_TAG_INTEGER, b"\x00\xc8")
        self.assertEqual(result, 200)

    def test_decode_value_string(self) -> None:
        result = _decode_value(_TAG_OCTET_STRING, b"hello")
        self.assertEqual(result, "hello")


class MockSnmpServer:
    """简单的模拟 SNMP 服务器，用于测试 snmp_get/snmp_getnext。"""

    def __init__(self, responses: list[bytes]) -> None:
        self.responses = list(responses)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self) -> None:
        for _ in range(len(self.responses)):
            try:
                self.sock.settimeout(2)
                _, addr = self.sock.recvfrom(65535)
                if self.responses:
                    resp = self.responses.pop(0)
                    self.sock.sendto(resp, addr)
            except (socket.timeout, OSError):
                break

    def __enter__(self) -> "MockSnmpServer":
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.sock.close()


class SnmpGetTests(unittest.TestCase):
    """snmp_get / snmp_getnext 测试（使用模拟服务器）。"""

    def _build_response(
        self,
        oid: str,
        value_tag: int,
        value_bytes: bytes,
        request_id: int = 1,
    ) -> bytes:
        """构建模拟 SNMP GET RESPONSE。"""
        oid_encoded = _encode_oid(oid)
        if value_tag == _TAG_INTEGER:
            value_encoded = _encode_integer(int.from_bytes(value_bytes, "big", signed=True) if value_bytes else 0)
        elif value_tag == _TAG_OCTET_STRING:
            value_encoded = _encode_octet_string(value_bytes)
        else:
            value_encoded = bytes([value_tag, len(value_bytes)]) + value_bytes

        varbind = _encode_sequence(oid_encoded + value_encoded)
        varbind_list = _encode_sequence(varbind)

        pdu_content = (
            _encode_integer(request_id)
            + _encode_integer(0)
            + _encode_integer(0)
            + varbind_list
        )
        pdu = bytes([_TAG_GET_RESPONSE]) + _encode_length(len(pdu_content)) + pdu_content

        return _encode_sequence(
            _encode_integer(1)
            + _encode_octet_string("public")
            + pdu
        )

    def test_snmp_get_integer(self) -> None:
        oid = "1.3.6.1.2.1.1.3.0"
        resp = self._build_response(oid, _TAG_INTEGER, b"\x00\x00\x30\x39")  # 12345

        with MockSnmpServer([resp]) as server:
            resp_oid, value = snmp_get(
                target="127.0.0.1",
                oid=oid,
                port=server.port,
                timeout_ms=2000,
            )

        self.assertEqual(resp_oid, oid)
        self.assertEqual(value, 12345)

    def test_snmp_get_string(self) -> None:
        oid = "1.3.6.1.2.1.1.1.0"
        resp = self._build_response(oid, _TAG_OCTET_STRING, b"My Device")

        with MockSnmpServer([resp]) as server:
            resp_oid, value = snmp_get(
                target="127.0.0.1",
                oid=oid,
                port=server.port,
                timeout_ms=2000,
            )

        self.assertEqual(resp_oid, oid)
        self.assertEqual(value, "My Device")

    def test_snmp_get_timeout(self) -> None:
        """没有服务器响应时应该超时。"""
        with self.assertRaises(SnmpError):
            snmp_get(
                target="127.0.0.1",
                oid="1.3.6.1.2.1.1.1.0",
                port=19999,  # 无人监听的端口
                timeout_ms=500,
            )

    def test_snmp_getnext(self) -> None:
        oid = "1.3.6.1.2.1.1.1"
        next_oid = "1.3.6.1.2.1.1.1.0"
        resp = self._build_response(next_oid, _TAG_OCTET_STRING, b"Next Value")

        with MockSnmpServer([resp]) as server:
            resp_oid, value = snmp_getnext(
                target="127.0.0.1",
                oid=oid,
                port=server.port,
                timeout_ms=2000,
            )

        self.assertEqual(resp_oid, next_oid)
        self.assertEqual(value, "Next Value")


class CollectSnmpInfoTests(unittest.TestCase):
    """collect_snmp_info 测试。"""

    def test_collect_snmp_info_unreachable(self) -> None:
        """设备不可达时应返回 failed 状态。"""
        result = collect_snmp_info(
            task_id="test-task",
            target="127.0.0.1",
            port=19999,  # 无人监听
            timeout_ms=500,
        )

        self.assertEqual(result.status, ProbeStatus.failed)
        self.assertEqual(result.probe_type, "snmp")
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "snmp_unreachable")

    def test_collect_snmp_info_structure(self) -> None:
        """即使失败，结构化输出也应包含所有字段。"""
        result = collect_snmp_info(
            task_id="test-task",
            target="192.168.255.255",
            timeout_ms=500,
        )

        self.assertEqual(result.probe_type, "snmp")
        self.assertIn("target", result.observations)
        self.assertIn("community", result.observations)
        self.assertIn("sysDescr", result.observations)
        self.assertIn("sysName", result.observations)


if __name__ == "__main__":
    unittest.main()
