# SNMP 模块设计

## 模块定位

SNMP 探针模块用于通过 SNMP v2c 协议采集网络设备的基础信息，包括系统描述、主机名、接口列表等。

## 设计决策

### 纯 Python 实现

不依赖 `pysnmp` 或系统 `snmpget` 命令，使用 Python 标准库（`socket` + 手写 BER 编码）实现 SNMP v2c 通信。

原因：
- 中小企业环境不一定安装了 net-snmp 工具。
- `pysnmp` 是可选依赖，增加安装复杂度。
- SNMP v2c 协议本身简单（UDP + BER 编码），手写实现可控且无外部依赖。

### 只读探针

只实现 GET / GETNEXT / WALK，不实现 SET 操作。符合第一阶段安全策略：所有探针都是只读的。

## 架构

```
probes/snmp.py
├── BER 编码/解码
│   ├── _encode_length / _decode_length
│   ├── _encode_integer / _decode_integer
│   ├── _encode_octet_string / _decode_octet_string
│   ├── _encode_oid / _decode_oid
│   └── _encode_sequence / _encode_null
├── SNMP 消息构建
│   └── _build_get_request (GET / GETNEXT)
├── SNMP 响应解析
│   ├── _parse_response
│   ├── _get_raw_value
│   └── _decode_value
├── 公开 API
│   ├── snmp_get (单个 OID GET)
│   ├── snmp_getnext (GETNEXT)
│   ├── snmp_walk (子树遍历)
│   └── collect_snmp_info (高级接口：设备信息采集)
```

## 常用 OID

| 名称 | OID | 说明 |
|---|---|---|
| sysDescr | 1.3.6.1.2.1.1.1.0 | 系统描述 |
| sysObjectID | 1.3.6.1.2.1.1.2.0 | 系统对象 ID |
| sysUpTime | 1.3.6.1.2.1.1.3.0 | 系统运行时间 |
| sysContact | 1.3.6.1.2.1.1.4.0 | 联系人 |
| sysName | 1.3.6.1.2.1.1.5.0 | 主机名 |
| sysLocation | 1.3.6.1.2.1.1.6.0 | 位置 |
| sysServices | 1.3.6.1.2.1.1.7.0 | 服务 |
| ifNumber | 1.3.6.1.2.1.2.1.0 | 接口数量 |
| ifDescr | 1.3.6.1.2.1.2.2.1.2 | 接口描述（WALK） |
| ifOperStatus | 1.3.6.1.2.1.2.2.1.8 | 接口操作状态（WALK） |

## CLI 命令

```bash
# 采集设备基础信息
ops probe snmp 192.168.1.1 --community public

# 查询单个 OID
ops probe snmp 192.168.1.1 --oid 1.3.6.1.2.1.1.1.0

# 自定义端口和超时
ops probe snmp 192.168.1.1 --port 1161 --timeout 5000
```

## Web API

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/snmp/{target}` | GET | 采集设备基础信息 |
| `/api/snmp/{target}/get` | GET | 查询单个 OID |

## 不支持的能力

- SNMP v3（需要认证框架，暂不实现）
- SET 操作（只读探针）
- SNMP Trap 接收（需要常驻监听服务）
- 趋势分析（SNMP 观察值以字符串为主，无数值型时序指标）
- 告警规则（`AlertCondition.probe_type` 的 Literal 已包含 `"snmp"`，但无内置 SNMP 告警规则实现）

## 状态

已完成（2026-06-28）。
