# 资产与拓扑模块

## 模块职责

资产与拓扑模块负责回答一个基础问题：当前 IT 环境里到底有什么。

它需要发现、记录和维护网络中的设备和服务线索，例如 IP、MAC、主机名、厂商、开放端口、首次发现时间、最后发现时间、设备变化等。

## 现实场景

中小企业常见问题：

- IP 地址靠 Excel 或个人记忆维护。
- 新设备接入后没人知道。
- 某台设备消失了，只有业务出故障时才发现。
- 打印机、摄像头、NAS、AP、电脑、服务器混在同一网段。
- 不清楚某个 IP 对应什么设备、谁负责、开放了什么端口。

资产模块的价值是建立最基本的“可见性”。

## 不负责什么

本模块不负责：

- 告警发送。
- 自动修复。
- 权限管理。
- 深度漏洞扫描。
- 完整物理网络拓扑推断。
- 判断端口是否一定有安全风险。

这些能力分别属于通知中心、自动化模块、权限审计、安全合规模块或未来拓扑扩展。

## 输入

输入可以包括：

- 网段，例如 `192.168.1.0/24`。
- 单个 IP。
- 主机名。
- 扫描配置。
- 端口探测配置。
- 历史资产记录。

## 输出

输出应是结构化资产记录，例如：

- IP。
- 主机名。
- MAC。
- 厂商。
- OS 线索。
- 开放端口摘要。
- 首次发现时间。
- 最后发现时间。
- 来源。
- 标签。
- 变化状态：新增、仍存在、消失、信息变化。

## 依赖模块

依赖：

- 配置中心：读取扫描网段和扫描策略。
- 插件与探针系统：调用 Ping、DNS、TCP 等 Probe。
- 数据存储：保存资产和历史变化。
- 日志与观测性：记录扫描错误和耗时。

被依赖：

- 网络与服务巡检。
- 场景化故障诊断。
- 轻量安全与合规。
- 报告中心。
- AI 运维助手。

## 第一阶段范围

第一阶段只做基础资产发现：

- 扫描配置中的 IP 范围。
- 判断 IP 是否存活。
- 尝试获取主机名。
- 尝试获取 MAC 和厂商信息。
- 对配置端口做简单开放性检查。
- 保存资产结果。
- 输出资产报告。

第一阶段不做复杂拓扑图，不做交换机端口级发现。

## 未来扩展

后续可扩展：

- SNMP 获取交换机和路由器信息。
- DHCP 租约整合。
- 交换机端口映射。
- 资产负责人和用途维护。
- IPAM 简化能力。
- 资产变更告警。

## Phase 8 扩展：网络拓扑与资产关系

Phase 8 在基础资产发现之上，新增了网络连接关系可见性：

### ARP 表采集

- **文件**：`probes/arp.py`
- 跨平台支持：Windows `arp -a`、Linux `ip neigh` / `arp -n`
- 输出 `ArpEntry` 列表（IP、MAC、接口、状态、厂商、设备类型）
- 内置精简 OUI 数据库（40+ 常见厂商前缀），离线可用
- 根据厂商推断设备类型：`network_device` / `printer` / `server` / `iot` / `nas` / `virtual` / `workstation`

### Traceroute Adapter

- **文件**：`probes/traceroute.py`
- 跨平台支持：Windows `tracert`、Linux `traceroute` / `tracepath`
- 输出 `TraceRouteResult`（每一跳 IP、RTT、超时状态）
- 自动检测是否到达目标

### 拓扑分析服务

- **文件**：`topology.py`
- 采集本机网络接口、默认网关、ARP 表
- 可选执行 traceroute 到外部目标
- 将 ARP 表与资产库对比（`reconcile_arp_with_assets`）：
  - 新设备：ARP 有、资产库无
  - 离线设备：资产库有、ARP 无
  - 匹配设备：两者都有
  - 未知厂商：无法识别 OUI 的设备
- 未知设备检测（`detect_unknown_devices`）：安全相关功能

### 数据模型

- `ArpEntry`：ARP 表条目
- `TraceRouteHop` / `TraceRouteResult`：路由追踪结果
- `AssetReconciliation`：资产对比结果
- `TopologyView`：完整拓扑视图

### CLI 命令

- `ops topology show`：展示本机视角拓扑
- `ops topology arp`：采集 ARP 表
- `ops topology unknown`：检测未知设备
- `ops probe traceroute <target>`：路由追踪

### Web API

- `GET /api/topology`：拓扑视图
- `GET /api/topology/arp`：ARP 表
- `GET /api/topology/unknown`：未知设备
- `GET /api/topology/traceroute/{target}`：路由追踪

### Phase 8 验收标准

- ✅ 能采集本机 ARP 表
- ✅ 能展示 IP-MAC-厂商对应关系
- ✅ 能检测 ARP 表中不在资产库的 MAC
- ✅ 能展示基础网关→终端拓扑

## 验收标准

本模块第一阶段完成时，应满足：

- 能扫描一个网段。
- 能输出在线 IP 列表。
- 能记录至少 IP、主机名、端口摘要和发现时间。
- 能区分新增资产和历史资产。
- 能生成资产导出结果。
- 不依赖 CLI 内部逻辑即可运行。

