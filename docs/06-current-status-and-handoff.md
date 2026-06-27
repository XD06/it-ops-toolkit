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

最近确认时间：2026-06-27。

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

结果：137 个测试通过。

## 已实现能力

### 配置与基础设施

- Python 包结构和 Typer CLI 入口。
- YAML 配置生成与校验。
- SQLite 本地存储。
- `TaskRun` 任务记录。
- `ProbeResult`、`Asset`、`Finding`、`Report`、`LocalSnapshot` 等核心模型。

### Probe / Adapter

- Ping Probe，解析 ping 输出提取延迟（min/avg/max RTT）和丢包率统计，支持 Windows 和 Linux 格式。
- DNS Probe，使用系统解析器；新增 `resolve_with_server` 通过 nslookup 查询指定 DNS 服务器，支持多服务器对比。
- TCP Probe。
- HTTP Probe。
- TLS Certificate Probe。

### 资产与拓扑基础

- `ops asset scan`：从配置网段做基础资产发现。
- `ops asset scan --tcp-without-ping`：即使 Ping 不通也尝试配置 TCP 端口，适合发现禁 ICMP 但端口开放的主机。
- `ops asset list`：查看资产列表。
- `ops asset show`：查看单个资产详情。
- `ops asset export`：导出当前资产清单，支持 CSV 和 JSON。
- `ops asset diff`：执行只读资产变化对比，发现新增设备、未出现设备和新增开放端口。
- `ops asset import-notes`：从 CSV 导入资产负责人、用途、类型、描述和标签，不覆盖扫描端口和发现时间。

### 巡检与诊断

- `ops health check`：按巡检配置执行 Ping、DNS、TCP、HTTP 检查。
- `ops diagnose internet`：诊断本机基础互联网连通性。
- `ops diagnose intranet`：诊断内网系统打不开。
- `ops diagnose rdp`：诊断远程桌面连不上，只做 DNS、Ping、TCP 端口检查，不尝试登录。
- `ops diagnose printer`：诊断打印机不可达，只做 DNS、Ping、TCP 端口检查，不发送打印任务、不登录后台、不改配置。
- `ops diagnose dns`：诊断 DNS 解析结果和可选 TCP 端口，支持 `--dns-servers` 多 DNS 服务器对比，只读检查解析结果、期望 IP、端口可达性和服务器间结果一致性。
- `ops diagnose slow-network`：诊断网络慢的基础链路耗时，基于 Ping RTT 和丢包率、DNS 耗时、HTTP 耗时分解判断，只做只读检查。

### 本机信息采集

- `ops collect local`：采集本机系统和网络排障上下文。
- 当前采集主机名、FQDN、用户、系统、网卡、IPv4、IPv6、默认网关、DNS、代理摘要。
- 代理 URL 中用户名和密码会脱敏。

### 安全与报告

- `ops security check`：基于已发现资产检查高风险端口。
- `ops security cert-check`：只读检查 TLS 证书过期和即将过期风险。
- `ops report generate`：基于任务生成 Markdown、CSV、JSON 报告。
- `ops export bundle`：导出诊断包，包含任务、资产、探测结果、风险发现、本机快照和摘要。

### 自动化动作

- `ops automate flush-dns`：低风险本机动作，默认 dry-run，显式 `--confirm` 才清理本机 DNS 缓存。

### 巡检批量工具

- `ops health tcp-matrix`：从 CSV 批量读取 TCP 目标，逐行执行端口可达性测试。
- `ops health http-matrix`：从 CSV 批量读取 HTTP/HTTPS 目标，逐行执行可达性测试，支持只读方法 `GET` 和 `HEAD`，支持 `expected_status` 期望状态码比对（单个码、范围、多值）。

### Web Console

- `ops web run`：启动 Web Console 服务（FastAPI + Uvicorn），默认监听 `127.0.0.1:8080`。
- 仪表盘首页：概览统计（资产数、任务数、报告数、发现项数、严重程度分布、任务类型分布）。
- 资产列表页：表格展示所有资产，点击 IP 查看详情弹窗。
- 任务历史页：表格展示最近任务，点击任务 ID 查看详情（含探测结果和发现项）。
- 报告页：报告列表，点击查看报告文件内容。
- REST API：`/api/overview`、`/api/assets`、`/api/assets/{ip}`、`/api/tasks`、`/api/tasks/{id}`、`/api/tasks/{id}/results`、`/api/tasks/{id}/findings`、`/api/tasks/{id}/snapshots`、`/api/reports`、`/api/reports/{id}`、`/api/reports/{id}/content`、`/api/health`。
- Web Console 只读调用 `SQLiteStore`，不直接调用 Adapter，不承载业务判断逻辑。
- 自动生成 OpenAPI 文档（`/docs`）。

## 当前尚未开始但已规划的能力

这些方向适合继续按小切片推进：

- DNS 深化诊断：记录解析耗时趋势、定时探测。
- 自动化动作审计深化：例如记录更明确的执行人、确认来源和审批占位字段。

## 最近完成的切片

### Phase 4: Web Console MVP（2026-06-27）

- 新增 `src/it_ops_toolkit/web/` 包，包含 FastAPI 应用定义和 HTML 仪表盘渲染。
- `web/app.py`：定义所有 API 路由，通过 `set_store()` 注入 `SQLiteStore` 实例，复用已有存储层和应用服务。
- `web/dashboard.py`：生成自包含单页 HTML（暗色主题、不依赖外部 CSS/JS），通过 fetch 调用 `/api/*` 端点。
- 存储层新增 `list_reports()` 和 `get_report()` 方法，补全报告查询能力。
- CLI 新增 `ops web run` 命令，支持 `--host`、`--port`、`--reload` 参数。
- `pyproject.toml` 新增 `[web]` 可选依赖组（`fastapi`、`uvicorn`），`[dev]` 组追加 `httpx`。
- 新增 25 个单元测试覆盖所有 API 端点（健康检查、概览、资产、任务、探测结果、发现项、报告、报告内容、仪表盘页面）。
- 架构验证通过：Web Console 只调用 `SQLiteStore` 和应用服务函数，不直接调用 Adapter。

### DNS 深化诊断：多 DNS 服务器对比（2026-06-27）

- 新增 `resolve_with_server()` 探针函数，通过 `nslookup` 查询指定 DNS 服务器，解析输出提取地址、服务器名称和服务器地址。
- 支持 Windows（`Addresses:` 多行格式）和 Linux（`Address:` 逐行格式）两种 nslookup 输出。
- 增强 `run_dns_diagnosis`：新增 `dns_servers` 参数，查询多个 DNS 服务器并对比结果。
- 增强 `classify_dns_diagnosis`：新增三种多服务器对比分类：
  - “所有指定 DNS 服务器解析均失败”
  - “部分 DNS 服务器解析失败”
  - “多 DNS 服务器解析结果不一致”
- CLI `diagnose dns` 新增 `--dns-servers` 选项，逗号分隔。
- 报告渲染增强：DNS 诊断报告显示多服务器对比表格（服务器、状态、解析地址、耗时、错误）。
- 新增 13 个单元测试覆盖 nslookup 解析和诊断分类逻辑。

### Ping Probe 增强：延迟和丢包统计（2026-06-27）

- 增强 `ping_host` 探针，解析 ping 输出提取 `packets_sent`、`packets_received`、`packets_lost`、`packet_loss_percent`、`min_rtt_ms`、`avg_rtt_ms`、`max_rtt_ms`。
- 支持 Windows（`Packets: Sent =` 格式）和 Linux/macOS（`packets transmitted` 格式）两种输出。
- 更新 `classify_slow_network_diagnosis`：用 `avg_rtt_ms` 替代 `duration_ms` 判断网络延迟，新增高丢包率分类（阈值 20%），延迟阈值从 1000ms（进程总耗时）调整为 200ms（实际 RTT）。
- 新增 13 个单元测试覆盖解析和诊断逻辑。

### 批量 HTTP Matrix 状态码比对（2026-06-27）

- `ops health http-matrix` 支持 `expected_status` 期望状态码比对。
- CSV 字段新增 `expected_status`，支持单个码（`200`）、范围（`200-299`）和多值（`301,302`）。
- 报告渲染区分 TCP 和 HTTP matrix，HTTP matrix 显示 HTTP 状态码、期望状态码和匹配结果。

## 当前推荐下一步

Phase 4: Web Console MVP 已完成。建议继续深化 Web Console 或推进 Phase 5: AI 运维助手。

方向一：深化 Web Console

- 增加手动任务触发（在 Web 界面点击按钮触发巡检或扫描）。
- 增加配置查看页面。
- 增加任务筛选和搜索。
- 增加资产变化趋势可视化。

方向二：Phase 5: AI 运维助手

- 定义 AI 输入数据结构。
- 让 AI 基于结构化巡检结果生成总结和建议。
- AI 输出区分事实、推断和建议。

方向三：继续深化诊断能力

- DNS 解析耗时趋势记录、定时探测。
- 自动化动作审计深化。

推荐验证：

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/ -v
python -m it_ops_toolkit web run --help
python -m it_ops_toolkit web run --port 8080
```

## 注意事项

- 不要把聊天记录里的无关项目内容带入本仓库。
- 曾经有一次无关上下文混入对话，但已确认没有写进当前仓库文件，也没有进入 git 提交。
- 后续接手应以仓库文档、源码和 git 记录为准。
- 如果新增重要能力，保持小提交，每个提交完成一个可验证切片。
