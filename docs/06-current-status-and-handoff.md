# 当前进度与交接说明

## 文档目的

这份文档用于让新的模型或开发者快速接手当前工作。

它不是完整架构说明，完整背景仍以这些文档为准：

- `README.md`
- `docs/00-project-vision.md`
- `docs/01-architecture-overview.md`
- `docs/02-module-map.md`
- `docs/03-roadmap.md`
- `docs/04-development-rules.md`
- `docs/cli-command-design.md`
- `docs/plans/phase-1-cli-foundation.md`

## 当前项目原则

当前最重要的产品原则：

> 桌面运维和网络工程里，如果一件事需要重复三遍以上，就应该想办法把它自动化成命令、配置、报告或工作流。

实现时要继续遵守：

- 中文优先，专业术语可保留英文。
- 贴近中小企业真实运维场景，不做空泛平台化。
- CLI 优先，但保持未来 Web Console、API、AI Copilot、Agent Runner 可复用。
- 高内聚、低耦合；CLI 只做入口，不承载核心业务逻辑。
- 第一阶段优先只读能力，不做高风险自动修复。
- 每个可执行功能尽量产生 `TaskRun`、结构化结果、报告或可导出的证据。

## 当前仓库状态

最近确认时间：2026-06-13。

当前分支：`master`。

最近有效提交：

```text
48762cd feat: add rdp diagnosis workflow
81da50c feat: add asset inventory export
864f462 feat: support tcp scan without ping
14c5693 feat: add local ops collection
69ac15f feat: add risky port security check
3e93914 feat: support tcp health checks
312a603 feat: add diagnostic bundle export
dbfb6d9 feat: add intranet diagnosis workflow
cd63120 feat: add internet diagnosis workflow
e76a180 feat: improve asset and task detail commands
9a95fd0 feat: add report generation workflow
980a293 feat: add minimal health check workflow
```

最近一次验证：

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests
```

结果：31 个测试通过。

## 已实现能力

### 配置与基础设施

- Python 包结构和 Typer CLI 入口。
- YAML 配置生成与校验。
- SQLite 本地存储。
- `TaskRun` 任务记录。
- `ProbeResult`、`Asset`、`Finding`、`Report`、`LocalSnapshot` 等核心模型。

### Probe / Adapter

- Ping Probe。
- DNS Probe，当前使用系统解析器。
- TCP Probe。
- HTTP Probe。

### 资产与拓扑基础

- `ops asset scan`：从配置网段做基础资产发现。
- `ops asset scan --tcp-without-ping`：即使 Ping 不通也尝试配置 TCP 端口，适合发现禁 ICMP 但端口开放的主机。
- `ops asset list`：查看资产列表。
- `ops asset show`：查看单个资产详情。
- `ops asset export`：导出当前资产清单，支持 CSV 和 JSON。

### 巡检与诊断

- `ops health check`：按巡检配置执行 Ping、DNS、TCP、HTTP 检查。
- `ops diagnose internet`：诊断本机基础互联网连通性。
- `ops diagnose intranet`：诊断内网系统打不开。
- `ops diagnose rdp`：诊断远程桌面连不上，只做 DNS、Ping、TCP 端口检查，不尝试登录。

### 本机信息采集

- `ops collect local`：采集本机系统和网络排障上下文。
- 当前采集主机名、FQDN、用户、系统、网卡、IPv4、IPv6、默认网关、DNS、代理摘要。
- 代理 URL 中用户名和密码会脱敏。

### 安全与报告

- `ops security check`：基于已发现资产检查高风险端口。
- `ops report generate`：基于任务生成 Markdown、CSV、JSON 报告。
- `ops export bundle`：导出诊断包，包含任务、资产、探测结果、风险发现、本机快照和摘要。

## 当前尚未开始但已规划的能力

这些方向适合继续按小切片推进：

- 打印机不可达诊断：`ops diagnose printer`。
- DNS 异常专项诊断：例如解析指定域名、查看系统 DNS、对比多个 DNS 服务器。
- 网络慢的基础诊断：延迟、丢包、DNS 耗时、HTTP 耗时分解。
- 证书过期检查。
- 新开放端口检测或资产变化对比。
- CSV 导入资产备注、负责人、资产类型。
- 低风险自动化动作，例如清理 DNS 缓存，但必须先设计风险边界。

## 当前推荐下一步

建议从 `ops diagnose printer` 开始接手。

理由：

- 打印机问题是桌面运维中非常高频的问题。
- 只读检查即可产生明显价值。
- 可以复用现有 DNS、Ping、TCP Probe。
- 不需要引入新依赖或复杂协议。

建议第一版范围：

- 命令：`ops diagnose printer --target <ip-or-hostname>`。
- 可选端口：默认检查 `9100`、`515`、`631`，允许 `--ports 9100,515,631`。
- 检查步骤：
  - 如果目标是主机名，先做 DNS。
  - Ping 目标。
  - TCP 检查常见打印端口。
  - 输出结论：DNS 异常、目标不可达、端口都不可达、至少一个打印端口可达。
- 不做内容：
  - 不发送打印任务。
  - 不登录打印机后台。
  - 不修改驱动、端口、队列或打印机配置。

推荐修改文件：

- `src/it_ops_toolkit/diagnosis.py`
- `src/it_ops_toolkit/cli.py`
- `tests/test_diagnosis.py`
- `README.md`
- `docs/cli-command-design.md`

推荐验证：

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_diagnosis
python -m unittest discover -s tests
python -m it_ops_toolkit diagnose printer --help
```

## 注意事项

- 不要把聊天记录里的无关项目内容带入本仓库。
- 曾经有一次无关上下文混入对话，但已确认没有写进当前仓库文件，也没有进入 git 提交。
- 后续接手应以仓库文档、源码和 git 记录为准。
- 如果新增重要能力，保持小提交，每个提交完成一个可验证切片。
