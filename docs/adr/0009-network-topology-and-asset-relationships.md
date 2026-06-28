# ADR 0009：网络拓扑与资产关系采集策略

## 状态

已接受，作为 Phase 8（网络拓扑与资产关系）的架构方向。

## 背景

Phase 1-4 的资产发现是"扁平"的——产出一个 IP 列表，每个 IP 有开放端口、备注等信息。但缺少关键的连接关系：

- 某个 IP 接在哪个交换机的哪个端口上？
- 网关上游链路是什么？
- ARP 表里的 MAC 地址对应什么设备？
- 网络里有没有不认识的设备？

这些信息对于排障至关重要。当用户报告"上不了网"时，知道他接在哪个交换机端口可以快速定位物理层问题。

当前平台已有：
- 资产发现（Ping + TCP 扫描）。
- 资产模型（IP、主机名、开放端口、备注）。
- 诊断（网络可达性、路由追踪概念）。

缺少：
- ARP 表采集（IP → MAC 映射）。
- MAC 地址厂商识别（OUI 查询）。
- 资产之间的连接关系。
- 拓扑可视化。

## 决策

### 1. ARP 表采集 Adapter

新增 `probes/arp.py`，采集本机 ARP 表。

**实现**：
- Windows: `arp -a` 命令输出解析。
- Linux: `ip neigh` 或 `arp -n` 命令输出解析。
- 输出 `ArpEntry` 列表。

**数据模型**：
```python
class ArpEntry(BaseModel):
    ip: str
    mac: str
    interface: str           # 网卡接口名
    state: str               # static | dynamic | stale（平台相关）
    vendor: str | None       # MAC OUI 厂商（可选，通过查询 OUI 数据库）
```

**OUI 厂商识别**：
- 内置一份精简 OUI 数据库（CSV 格式，约 3 万条，约 1MB）。
- 或在运行时从 `https://standards-oui.ieee.org/oui/oui.csv` 在线查询（可选，缓存到本地）。
- 优先使用内置数据，保证离线可用。

### 2. 资产模型扩展

在现有 `Asset` 模型上扩展关系字段：

```python
class Asset(BaseModel):
    # ... 已有字段 ...
    ip: str
    hostname: str | None
    open_ports: list[int]
    notes: str
    first_seen: datetime
    last_seen: datetime

    # 新增字段
    mac: str | None             # MAC 地址（从 ARP 表获取）
    vendor: str | None          # 设备厂商（从 OUI 查询）
    upstream_gateway: str | None  # 上游网关 IP
    interface: str | None       # 本机网卡接口
    switch_port: str | None     # 交换机端口（需要 SNMP，Phase 8 暂不支持）
    device_type: str | None     # 设备类型推断（server / router / printer / iot / unknown）
```

`switch_port` 需要交换机 SNMP 支持，Phase 8 暂不实现，预留字段。

### 3. Traceroute Adapter

新增 `probes/traceroute.py`，执行路由追踪。

**实现**：
- Windows: `tracert -d -h 15` 命令输出解析。
- Linux: `traceroute -n -m 15` 或 `tracepath -n` 命令输出解析。
- 输出 `TraceRouteHop` 列表。

**数据模型**：
```python
class TraceRouteHop(BaseModel):
    hop: int                  # 跳数
    ip: str | None            # 该跳 IP（超时则为 None）
    rtt_ms: list[float]       # 每次探测的 RTT（通常 3 次）
    timeout: bool             # 是否超时

class TraceRouteResult(BaseModel):
    target: str
    source: str
    hops: list[TraceRouteHop]
    total_hops: int
    reached: bool             # 是否到达目标
```

**使用场景**：
- 诊断"网络慢"时，traceroute 可以定位中断点或高延迟跳。
- 推断网络路径上的中间设备。
- 与 ARP 表结合，构建基础拓扑。

### 4. 拓扑推断策略

Phase 8 的拓扑不追求完整网络拓扑发现（那需要 SNMP/LLDP/CDP），而是基于本机视角的基础拓扑：

```
本机
  ├── 网卡接口 (interface)
  │     ├── IPv4 地址
  │     └── 默认网关 → 上游路由器/网关
  │
  ├── ARP 表
  │     ├── 192.168.1.1 → aa:bb:cc:dd:ee:ff (厂商: Cisco) → 网关
  │     ├── 192.168.1.10 → 11:22:33:44:55:66 (厂商: Dell) → 服务器
  │     ├── 192.168.1.50 → 77:88:99:aa:bb:cc (厂商: HP) → 打印机
  │     └── 192.168.1.200 → aa:bb:cc:11:22:33 (厂商: Unknown) → ⚠️ 未知设备
  │
  └── Traceroute (到外部目标)
        ├── Hop 1: 192.168.1.1 (网关)
        ├── Hop 2: 10.0.0.1 (上级路由)
        └── Hop 3: * * * (超时)
```

**设备类型推断规则**：
- MAC OUI 厂商 + 开放端口组合推断：
  - HP + 9100 端口 → 打印机
  - Cisco + 22/23 端口 → 网络设备
  - Dell + 445 端口 → Windows 服务器
  - 未知厂商 + 任意端口 → 未知设备（标记警告）

### 5. 未知 MAC 检测

将 ARP 表中的 MAC 地址与资产库对比：
- ARP 表中有但资产库中没有 → 标记为"未知设备"。
- 资产库中有但 ARP 表中没有 → 标记为"离线设备"。
- 两者都有 → 更新资产的 MAC 和厂商信息。

**输出**：
```python
class AssetReconciliation(BaseModel):
    new_devices: list[ArpEntry]          # ARP 表中有，资产库中没有
    offline_devices: list[Asset]         # 资产库中有，ARP 表中没有
    matched: list[tuple[Asset, ArpEntry]] # 匹配的资产和 ARP 条目
    unknown_vendors: list[ArpEntry]      # 无法识别厂商的设备
```

### 6. 拓扑展示

Web Console 新增拓扑视图，用 SVG 绘制基础拓扑：

- 本机在中心，网关在上方，ARP 设备围绕排列。
- 设备按类型用不同图标/颜色。
- 未知设备用警告色标注。
- 点击设备可查看详情（IP、MAC、厂商、开放端口）。

Phase 8 不做交互式拖拽拓扑，只做静态展示。

## 备选方案

### 方案 B：通过 SNMP/LLDP/CDP 发现完整拓扑

优点：
- 能获取交换机端口连接关系。
- 能发现二层拓扑。

缺点：
- 需要交换机开启 SNMP，中小企业配置参差不齐。
- 需要 `pysnmp` 重型依赖。
- 不同厂商交换机 MIB 不统一，适配成本高。
- 超出 Phase 8 范围，可作为未来扩展。

### 方案 C：通过被动流量分析推断拓扑

优点：
- 不需要主动探测。
- 能发现实际流量路径。

缺点：
- 需要镜像端口或 NTP 流量采集。
- 实现复杂度高。
- 中小企业网络环境不具备流量采集条件。

### 方案 D：不做拓扑，只增强资产列表

优点：
- 实现最简单。
- 不引入新概念。

缺点：
- 无法回答"设备接在哪"的问题。
- 缺少关系信息，排障效率低。

## 后果

正面影响：
- ARP 表采集让资产有 MAC 地址和厂商信息。
- 未知 MAC 检测提升安全可见性。
- Traceroute 补全路由诊断能力。
- 基础拓扑视图提升排障效率。
- 资产模型扩展为未来 SNMP 集成预留字段。

负面影响：
- ARP 表只包含本网段设备（跨网段需要登录网关采集）。
- 基础拓扑不如 SNMP/LLDP 拓扑完整。
- OUI 数据库需要维护更新。
- 设备类型推断不是 100% 准确。

## 执行要求

- ARP Adapter 实现为 `src/it_ops_toolkit/probes/arp.py`。
- Traceroute Adapter 实现为 `src/it_ops_toolkit/probes/traceroute.py`。
- 资产模型扩展在 `src/it_ops_toolkit/models.py` 中。
- 拓扑推断服务实现为 `src/it_ops_toolkit/topology.py`。
- OUI 数据库放在 `src/it_ops_toolkit/data/oui.csv`（精简版）。
- CLI 新增 `ops topology show` 命令。
- CLI 新增 `ops probe traceroute <target>` 命令。
- Web Console 新增拓扑视图页面。
- 跨平台：ARP 和 Traceroute 必须同时支持 Windows 和 Linux。
- 未知设备检测集成到安全检查模块。
