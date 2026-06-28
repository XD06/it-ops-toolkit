# IT Ops Toolkit Platform

`IT Ops Toolkit Platform` 是一个面向中小企业 IT 运维、桌面运维、IT 网关和值班人员、初级网络工程师的模块化运维工具平台。

项目的第一阶段目标不是做一个庞大的 Web 系统，而是先做一个真正可用的 CLI 运维工具箱；但从第一天开始，架构就要为未来的 Web Console、API、AI 助手和受控 Agent 执行预留边界。

## 为什么要做这个项目

中小企业 IT 环境通常有几个特点：

- 人少，一个人常常要同时负责桌面、网络、服务器、账号、打印机、无线、监控和简单安全。
- 工具分散，日常会在 ping、tracert、nslookup、PowerShell、浏览器、Excel、远程桌面、设备管理页面之间来回切换。
- 文档不足，IP 使用情况、设备用途、端口开放原因、历史故障经常靠记忆。
- 故障压力高，业务方关心的是“能不能恢复”“多久恢复”“以后还会不会发生”。
- 安全基础参差不齐，未知设备、暴露端口、补丁滞后、备份不清晰、账号权限混乱都很常见。

这个项目希望把这些零散工作整理成一个可持续演进的平台。

## 长期形态

长期目标是形成以下能力：

- CLI：现场快速诊断、扫描、巡检和导出报告。
- Web Console：资产、任务、巡检结果、报告、告警、配置的统一界面。
- API：让其他系统或脚本可以调用平台能力。
- AI Copilot：解释日志、总结巡检、生成排障建议和报告。
- Agent Runner：在审批和审计保护下执行预定义运维流程。

## 第一阶段目标

第一阶段先做最小但完整的运维闭环：

```text
配置 -> CLI 命令 -> 探测 Adapter -> 领域服务 -> 结构化结果 -> 报告输出
```

第一阶段优先模块：

- 配置中心
- CLI 入口
- 基础探测能力：Ping、DNS、TCP、HTTP
- 资产发现最小流程
- 网络与服务巡检最小流程
- 结构化结果模型
- 报告输出
- 本地数据存储

## 文档入口

- [项目愿景](docs/00-project-vision.md)
- [总开发与架构文档](docs/01-architecture-overview.md)
- [模块地图](docs/02-module-map.md)
- [路线图](docs/03-roadmap.md)
- [开发规则](docs/04-development-rules.md)
- [文档协作与开发流程](docs/05-documentation-workflow.md)
- [当前进度与交接说明](docs/06-current-status-and-handoff.md)
- [AI 接手指南](docs/AI-HANDOVER.md)
- [Phase 1 实施计划](docs/plans/phase-1-cli-foundation.md)
- [数据模型](docs/data-model.md)
- [配置文件设计](docs/config-schema.md)
- [Probe 与 Adapter 接口设计](docs/probe-adapter-interface.md)
- [CLI 命令设计](docs/cli-command-design.md)
- [部署模型](docs/deployment-model.md)
- [风险策略](docs/risk-policy.md)
- [术语表](docs/glossary.md)
- [调研依据](docs/research/2026-06-08-smb-it-ops-research.md)
- [ADR 索引](docs/adr/README.md)

模块设计文档位于 [docs/modules](docs/modules)。

## 当前代码状态

Phase 1 已经跑通一批可用的 CLI 运维闭环，并开始覆盖常见桌面运维与网络排障场景。

当前已实现：

- Python 包结构。
- Typer CLI 入口。
- `ops config init`。
- `ops config validate`。
- 配置模型和校验。
- 基础数据模型。
- SQLite 本地存储骨架。
- `TaskRun` 任务记录读写。
- Ping Probe。
- TCP Probe。
- DNS Probe，当前使用系统解析器。
- HTTP Probe。
- `ops asset scan`。
- `ops asset list`。
- `ops asset show`。
- `ops asset export`，导出当前资产清单，支持 CSV 和 JSON。
- `ops asset diff`，对比本次扫描与历史资产库，发现新增设备、未出现设备和新增开放端口。
- `ops asset import-notes`，从 CSV 导入资产负责人、用途、类型、描述和标签。
- `ops health check`。
- `ops diagnose internet`。
- `ops diagnose intranet`。
- `ops diagnose rdp`，诊断远程桌面基础连接链路。
- `ops collect local`，采集本机系统和网络排障上下文。
- `ops task list`。
- `ops task show`，包含任务下的探测结果。
- `ops report generate`，支持 Markdown、CSV、JSON。
- `ops export bundle`。
- `ops security check`。
- `ops automate flush-dns`，默认 dry-run，显式 `--confirm` 才清理本机 DNS 缓存。
- `ops health tcp-matrix`，从 CSV 批量读取 TCP 目标并逐行测试端口可达性。
- `ops health http-matrix`，从 CSV 批量读取 HTTP/HTTPS 目标并逐行测试可达性。
- 当前自动化测试 76 个。

开发环境直接运行：

```powershell
$env:PYTHONPATH='src'
python -m it_ops_toolkit --version
python -m it_ops_toolkit config init --path .\ops.yaml
python -m it_ops_toolkit config validate --config .\ops.yaml
python -m it_ops_toolkit asset scan --config .\ops.yaml --profile office_lan
python -m it_ops_toolkit asset scan --config .\ops.yaml --profile office_lan --tcp-without-ping
python -m it_ops_toolkit asset diff --config .\ops.yaml --profile office_lan
python -m it_ops_toolkit asset import-notes --config .\ops.yaml --file .\assets.csv
python -m it_ops_toolkit asset list --config .\ops.yaml
python -m it_ops_toolkit asset export --config .\ops.yaml --format csv
python -m it_ops_toolkit asset show 192.168.1.10 --config .\ops.yaml
python -m it_ops_toolkit health check --config .\ops.yaml --profile daily_basic
python -m it_ops_toolkit diagnose internet --config .\ops.yaml
python -m it_ops_toolkit diagnose intranet --config .\ops.yaml --url https://intranet.example.local
python -m it_ops_toolkit diagnose rdp --config .\ops.yaml --target 192.168.1.50
python -m it_ops_toolkit diagnose printer --config .\ops.yaml --target printer-01.example.local
python -m it_ops_toolkit diagnose dns --config .\ops.yaml --name intranet.example.local --expected-ip 192.168.1.10 --tcp-port 443
python -m it_ops_toolkit diagnose slow-network --config .\ops.yaml
python -m it_ops_toolkit collect local --config .\ops.yaml
python -m it_ops_toolkit task list --config .\ops.yaml
python -m it_ops_toolkit task show <task-id> --config .\ops.yaml
python -m it_ops_toolkit report generate --config .\ops.yaml --task <task-id> --format markdown
python -m it_ops_toolkit export bundle --config .\ops.yaml --task <task-id>
python -m it_ops_toolkit security check --config .\ops.yaml
python -m it_ops_toolkit security cert-check --config .\ops.yaml --target intranet.example.local
python -m it_ops_toolkit automate flush-dns --config .\ops.yaml --dry-run
python -m it_ops_toolkit automate flush-dns --config .\ops.yaml --confirm
python -m it_ops_toolkit health tcp-matrix --config .\ops.yaml --file .\targets.csv
python -m it_ops_toolkit health http-matrix --config .\ops.yaml --file .\targets.csv
python -m unittest discover -s tests
```

## 打包分发

项目支持使用 PyInstaller 打包为单文件可执行程序，方便在没有 Python 环境的机器上使用。

### 前置条件

```bash
pip install -e ".[web,build]"
```

### 打包命令

```bash
# 完整打包（含 Web Console）
python build/build_exe.py

# 仅 CLI（排除 Web 依赖，体积更小）
python build/build_exe.py --cli

# 清理后重新打包
python build/build_exe.py --clean
```

### 输出

打包完成后，可执行文件位于 `dist/ops.exe`（Windows）或 `dist/ops`（Linux/macOS）。

```bash
# 使用打包后的可执行文件
./dist/ops.exe --help
./dist/ops.exe web run --config ops.yaml
```
