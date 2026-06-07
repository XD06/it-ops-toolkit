# 术语表

## Adapter

适配器。用于封装外部协议、命令、脚本或服务。

例子：

- Ping Adapter。
- DNS Adapter。
- TCP Adapter。
- HTTP Adapter。
- SNMP Adapter。
- SSH Adapter。
- WinRM / WMI Adapter。
- PowerShell Adapter。

Adapter 的作用是把外部世界的不稳定输出转换成平台内部的结构化结果。

## Agent Runner

受控 Agent 执行器。未来用于执行预定义工作流。

它必须有权限、审批、审计、风险等级和停止条件，不能理解成“让 AI 随便操作系统”。

## AI Copilot

AI 运维助手。主要负责解释、总结、建议和生成报告草稿。

AI Copilot 不应该默认直接执行高风险操作。

## Asset

资产。可以是电脑、服务器、打印机、摄像头、NAS、路由器、交换机、AP、防火墙、业务系统或云资源。

## CLI

命令行入口。第一阶段的主要交付形态。

CLI 适合现场排障、批量检查、生成报告和脚本化调用。

## Configuration Center

配置中心。负责管理网段、目标、扫描配置、巡检配置、Adapter 配置、报告配置和未来通知配置。

## Domain Service

领域服务。承载业务逻辑的模块。

例如：

- 资产发现。
- 网络巡检。
- 故障诊断。
- 安全检查。
- 报告生成。

## Entry Layer

入口层。用户或系统进入平台的方式。

包括：

- CLI。
- Web Console。
- API。
- 定时任务入口。
- Agent Runner。

入口层不应该包含核心业务逻辑。

## Finding

发现。由系统根据探测或巡检结果产生的判断。

例子：

- 某端口不可达。
- 某证书即将过期。
- 某设备是新出现的未知设备。
- 某服务响应时间异常。

## Probe

探针。执行一种具体检查的小能力。

例子：

- Ping 探针。
- DNS 探针。
- TCP 端口探针。
- HTTP 状态探针。

## Scenario Diagnosis

场景化故障诊断。以用户现象为入口，自动组织多个检查并输出可能原因。

例子：

- 上不了网。
- 内网系统打不开。
- 远程桌面连不上。
- 网络很慢。

## Structured Result

结构化结果。平台内部保存和传递的标准结果对象。

它应包含目标、时间、状态、观察值、错误、证据和判断。CLI、Web、AI、报告、审计都应该消费结构化结果。

## Task

任务。一次被记录的执行。

例子：

- 一次资产扫描。
- 一次巡检。
- 一次诊断。
- 一次报告生成。
- 一次自动化动作。

## Web Console

Web 控制台。未来用于展示资产、任务、结果、报告、配置和告警。

Web Console 应该调用已有服务，不应该重写 CLI 的逻辑。

