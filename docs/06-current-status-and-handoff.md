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
- `docs/plans/phase-5-onwards-planning.md`
- `docs/plans/phase-10-web-ops-center.md`

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

最近确认时间：2026-06-28。

当前分支：`master`。

最近一次验证：

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/ -v --tb=short
```

结果：355 个测试通过。

### 代码规模

| 指标 | 数量 |
|---|---|
| 源码行数 | ~16,500 行 |
| 测试行数 | ~6,200 行 |
| CLI 命令 | 51 个 |
| Web API 端点 | 50 个（36 GET + 14 POST） |
| Web Console 页面 | 11 个 |
| 测试用例 | 355 个 |
| ADR | 10 条 |
| 模块文档 | 17 个 |

## 已完成 Phase 总览

| Phase | 名称 | 状态 | 完成时间 |
|---|---|---|---|
| Phase 0 | 文档与架构基础 | ✅ 已完成 | 2026-06-08 |
| Phase 1 | CLI 基础与最小运维闭环 | ✅ 已完成 | 2026-06-27 |
| Phase 2 | 场景化故障诊断 | ✅ 已完成 | 2026-06-27 |
| Phase 3 | 轻量安全与自动化 | ✅ 已完成 | 2026-06-27 |
| Phase 4 | Web Console MVP | ✅ 已完成 | 2026-06-27 |
| Phase 5 | 定时巡检与告警通知 | ✅ 已完成 | 2026-06-27 |
| Phase 6 | 历史趋势与可视化 | ✅ 已完成 | 2026-06-27 |
| Phase 7 | AI 运维助手 | ✅ 已完成 | 2026-06-27 |
| Phase 8 | 网络拓扑与资产关系 | ✅ 已完成 | 2026-06-27 |
| Phase 9 | 受控 Agent 工作流 | ✅ 已完成 | 2026-06-27 |
| Phase 10 | Web Console 操作中心 | ✅ 已完成 | 2026-06-28 |
| Phase 11 | 调度告警 Web 管理 + 打包分发 | ✅ 已完成 | 2026-06-28 |
| Phase 12 | CLI 体验优化 + SNMP Adapter | ✅ 已完成 | 2026-06-28 |

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
- ARP 表采集 Adapter（`probes/arp.py`）：跨平台支持 Windows `arp -a` 和 Linux `ip neigh` / `arp -n`。
- Traceroute Adapter（`probes/traceroute.py`）：跨平台支持 Windows `tracert` 和 Linux `traceroute` / `tracepath`。

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
- **12 个功能页面**：
  1. 概览页：概览统计（资产数、任务数、报告数、发现项数、严重程度分布、任务类型分布）、手动任务触发按钮（巡检和扫描）、快捷入口卡片。
  2. 资产列表页：表格展示所有资产，点击 IP 查看详情弹窗。
  3. 任务历史页：表格展示最近任务，支持按类型和状态筛选，点击任务 ID 查看详情。
  4. 报告页：报告列表，点击查看报告文件内容。
  5. 配置页：查看当前应用配置、巡检配置和扫描配置详情。
  6. 趋势分析页：探针类型/目标/指标/天数/粒度筛选，SVG 折线图展示指标趋势，柱状图展示状态分布和成功率。
  7. AI 助手页：任务摘要生成、异常解释（支持自然语言提问）、AI 周报生成、AI 调用日志表格。
  8. 网络拓扑页：本机网络信息、资产对比统计、ARP 表展示、未知设备检测、路由追踪。
  9. 工作流管理页：工作流定义卡片、一键执行工作流、执行历史表格、执行详情弹窗。
  10. **操作中心页**（Phase 10 新增）：7 个可执行操作卡片，支持通过 Web 界面直接触发诊断、安全检查、证书检查、报告生成、资产对比、本机采集和 DNS 缓存清理。
  11. **调度告警页**（Phase 11 新增）：定时任务管理（列表/添加/删除/启用禁用/立即执行）和告警事件列表（筛选/确认）。
  12. **SNMP 设备页**（Phase 12 新增）：SNMP v2c 设备信息采集（sysDescr/sysName/接口列表等）和单个 OID 查询。
- REST API：50 个端点（36 GET + 14 POST），覆盖概览、资产、任务、报告、配置、趋势、AI、拓扑、工作流、操作中心、调度管理、告警事件、SNMP 探针。
- Web Console 调用 `SQLiteStore` 和领域服务函数，不直接调用 Adapter。
- 手动触发任务以 `source="web"` 记录，方便区分 CLI 和 Web 来源。
- 自动生成 OpenAPI 文档（`/docs`）。
- 自包含前端：不依赖外部 CSS/JS 框架，数据可视化使用原生 SVG，适合离线运维环境。

### 定时巡检与告警通知（Phase 5）

- `ops schedule list`：列出所有定时任务。
- `ops schedule add`：添加定时任务（cron 表达式，支持 health_check / security_check / asset_scan）。
- `ops schedule remove`：删除定时任务。
- `ops schedule enable/disable`：启用/禁用定时任务。
- `ops schedule run-now`：立即执行一次定时任务。
- `ops schedule run`：以阻塞模式运行调度器（无 Web Console 环境）。
- `ops alert list`：列出告警事件，支持按状态筛选。
- `ops alert acknowledge`：确认告警事件。
- `ops alert rules`：列出已配置的告警规则。
- 调度引擎（`SchedulerEngine`）：进程内调度，cron 表达式解析，后台线程轮询。
- 告警引擎（`AlertEngine`）：规则驱动评估，三层降噪（冷却期 + 目标去重 + 恢复通知）。
- 通知中心（`NotificationCenter`）：Adapter 模式，5 种渠道（Email / Webhook / 企业微信 / 钉钉 / 飞书）。
- 告警规则和通知渠道配置在 YAML 中，凭据通过 `${ENV_VAR}` 环境变量注入。
- 调度状态和告警事件持久化到 SQLite，进程重启后可恢复。

### 历史趋势分析（Phase 6）

- `ops trend targets`：列出有历史数据的目标。
- `ops trend show`：查看趋势详情（含时间序列），支持按探针类型、目标、指标、天数、粒度筛选。
- `ops trend summary`：查看趋势摘要（快速概览，适合 AI 消费）。
- 存储层新增：`list_probe_results_between`（时间范围查询）、`get_probe_stats`（聚合统计，count/avg/min/max/p95）、`get_status_distribution`（状态分布和成功率）。
- 趋势服务（`trend.py`）：`get_trend`（完整趋势数据）、`get_trend_summary`（摘要）、`list_available_targets`（可用目标列表）。
- 聚合在 SQLite 层完成，支持 daily / hourly 两种粒度。
- 支持 ping / dns / tcp / http / tls_cert 五种探针类型的数值型指标。
- Web API 3 个端点：`/api/trends/targets`、`/api/trends/probe`、`/api/trends/summary`。
- 趋势数据结构化输出，可被 CLI、Web、AI 复用。

### AI 运维助手（Phase 7）

- `ops ai summarize`：对指定任务生成 AI 摘要，区分事实和推断。
- `ops ai explain`：解释指定任务中的异常，支持自然语言提问。
- `ops ai weekly`：生成 AI 周报摘要。
- `ops ai logs`：查看 AI 调用审计日志。
- AIAdapter 接口与三种实现：
  - `TemplateAdapter`：零成本规则模板引擎，不依赖外部服务（默认兜底）。
  - `OpenAIAdapter`：OpenAI 兼容 API（可选依赖 `openai`）。
  - `OllamaAdapter`：本地模型 Ollama REST API（可选依赖 `httpx`）。
- AI 脱敏处理（`sanitize_ai_input`）：移除敏感字段，代理 URL 凭据脱敏。
- AI 调用降级机制：后端调用失败时自动降级为 TemplateAdapter。
- AI 审计日志：每次调用记录到 SQLite（`ai_call_logs` 表）。
- AI 输出严格区分 facts（事实）和 inferences（推断）。
- `confidence < 0.7` 时自动设置 `needs_human_review = true`。
- Web API 4 个端点：`/api/ai/summarize` / `/api/ai/explain` / `/api/ai/weekly` / `/api/ai/logs`。

### 网络拓扑与资产关系（Phase 8）

- `ops topology show`：展示本机视角的网络拓扑（接口、网关、ARP 表、可选 traceroute、资产对比）。
- `ops topology arp`：采集并展示本机 ARP 表（IP-MAC-厂商-类型）。
- `ops topology unknown`：检测 ARP 表中不在资产库的未知设备。
- `ops probe traceroute`：执行路由追踪，展示每一跳的 IP 和 RTT。
- OUI 厂商识别：内置精简 OUI 数据库（40+ 常见厂商前缀），离线可用。
- 拓扑数据模型：`ArpEntry` / `TraceRouteHop` / `TraceRouteResult` / `AssetReconciliation` / `TopologyView`。
- 拓扑分析服务（`topology.py`）：采集接口、网关、ARP 表、可选 traceroute，与资产库对比。
- 设备类型推断：根据 OUI 厂商推断 `network_device` / `printer` / `server` / `iot` / `nas` / `virtual` 等。
- 资产对比：发现新设备（ARP 有、资产库无）和离线设备（资产库有、ARP 无）。
- Web API 4 个端点：`/api/topology` / `/api/topology/arp` / `/api/topology/unknown` / `/api/topology/traceroute/{target}`。

### 受控 Agent 工作流（Phase 9）

- `ops workflow list`：列出所有可用工作流。
- `ops workflow run`：执行指定工作流（支持 `--confirm` 自动批准低风险步骤）。
- `ops workflow show`：查看工作流执行详情。
- `ops workflow history`：查看工作流执行历史。
- 工作流定义模型：`WorkflowDefinition` / `WorkflowStepDef`。
- 工作流执行记录模型：`WorkflowExecution` / `WorkflowStepExecution`。
- Action 注册表（`ActionRegistry`）：管理所有可执行操作及其风险等级。
- 工作流执行引擎（`agent_workflow.py`）：按依赖顺序执行步骤，风险检查，审计记录。
- 风险分级执行策略：
  - `read_only`：自动执行，无需审批。
  - `low_change`：暂停等待审批（`--confirm` 或 Web 审批）。
  - `high_change`：拒绝执行（Phase 9 不支持）。
- 3 个内置工作流：
  - `network_troubleshoot`：网络故障排查（互联网诊断 → DNS 诊断 → AI 总结）
  - `full_inspection`：全面巡检（健康检查 → 安全检查 → AI 周报）
  - `new_device_investigate`：新设备调查（拓扑采集 → 安全检查 → AI 解释）
- 完整审计记录：每步执行状态、结果、耗时、错误信息均持久化到 SQLite。
- Web API 4 个端点：`/api/workflows` / `/api/workflows/{name}/run` / `/api/workflows/executions` / `/api/workflows/executions/{id}`。

### Web Console 操作中心（Phase 10）

Phase 10 将 Web Console 从"只读仪表盘"升级为"可执行控制台"。新增 8 个 POST 操作端点和操作中心 UI 页面：

| 操作端点 | 风险等级 | 说明 |
|---|---|---|
| `POST /api/ops/diagnose` | 只读 | 触发 6 种诊断场景（互联网/慢网络/内网/RDP/打印机/DNS） |
| `POST /api/ops/security-check` | 只读 | 基于已发现资产执行安全检查 |
| `POST /api/ops/cert-check` | 只读 | 检查 TLS 证书过期风险 |
| `POST /api/ops/report-generate` | 只读 | 基于指定任务生成 Markdown/CSV/JSON 报告 |
| `POST /api/ops/asset-diff` | 只读 | 执行资产变化对比 |
| `POST /api/ops/collect-local` | 只读 | 采集本机系统和网络排障上下文 |
| `POST /api/ops/flush-dns` | 低风险变更 | 清理本机 DNS 缓存（支持 dry-run 预览和确认执行） |
| `POST /api/workflows/{name}/run` | 依赖工作流 | 执行预定义工作流（Phase 9 已有） |

操作中心 UI 特性：
- 7 个操作卡片，每个卡片标注风险等级（只读/低风险变更）。
- 诊断卡片支持选择场景和输入目标参数。
- 报告生成卡片支持选择源任务和格式。
- DNS 缓存清理卡片区分"Dry Run 预览"和"确认执行"两个按钮。
- 每次操作结果直接在卡片下方展示，包含任务状态、诊断摘要、建议。
- 操作结果同时写入任务历史，可在任务历史页查看详情。

架构合规性：
- 所有操作端点只调用领域服务函数，不直接调用 Adapter。
- 每个操作创建 `TaskRun` 记录，结果写入存储，可审计。
- 变更操作有明确的风险标签和确认机制。

### 调度告警 Web 管理 + 打包分发（Phase 11）

Phase 11 包含两部分：

**调度告警 Web 管理**：在 Web Console 中新增"调度告警"页面，将 CLI 中已有的调度管理和告警查看能力对等映射到 Web 端。

新增 8 个 Web API 端点：

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/schedules` | GET | 列出所有定时任务 |
| `/api/schedules` | POST | 添加定时任务（验证 cron + 去重） |
| `/api/schedules/{id}` | DELETE | 删除定时任务 |
| `/api/schedules/{id}/enable` | POST | 启用定时任务 |
| `/api/schedules/{id}/disable` | POST | 禁用定时任务 |
| `/api/schedules/{id}/run-now` | POST | 立即执行一次定时任务 |
| `/api/alerts` | GET | 列出告警事件（支持按状态筛选） |
| `/api/alerts/{id}/acknowledge` | POST | 确认告警事件 |

Web UI 特性：
- 定时任务表格：展示任务名称、类型、配置、cron 表达式、启用状态、上次执行结果、下次执行时间。
- 添加任务表单：输入名称、选择类型、输入配置名和 cron 表达式。
- 每行操作按钮：启用/禁用切换、立即执行、删除。
- 告警事件表格：展示规则、严重程度、目标、探针、指标值/阈值、状态、触发时间、确认状态。
- 告警状态筛选下拉框（全部/活跃/已恢复/已抑制）。
- 未确认告警可一键确认。

**打包分发（PyInstaller）**：

- `build/it_ops_toolkit.spec`：PyInstaller spec 文件，配置了所有隐藏导入和排除模块。
- `build/build_exe.py`：打包脚本，支持 `--cli`（仅 CLI）和 `--clean`（清理重打包）选项。
- `pyproject.toml` 新增 `[build]` 可选依赖组。
- 打包后的单文件可执行程序无需 Python 环境即可运行。

```bash
# 打包命令
pip install -e ".[web,build]"
python build/build_exe.py              # 完整打包
python build/build_exe.py --cli        # 仅 CLI
python build/build_exe.py --clean      # 清理重打包
```

### CLI 体验优化 + SNMP Adapter（Phase 12）

Phase 12 包含两部分：

**CLI 体验优化**：

- **交互式诊断引导**（`ops diagnose`）：不指定子命令时进入交互式菜单，列出 6 种诊断场景，逐步收集参数，确认后自动执行。
- **Rich 进度条**：`ops health check`、`ops asset scan`、`ops health tcp-matrix`、`ops health http-matrix` 新增实时进度显示（检查项、完成数/总数、耗时）。
- 领域服务新增 `progress_callback` 可选参数（`run_health_check`、`run_asset_scan`、`run_health_tcp_matrix`、`run_health_http_matrix`），不破坏现有 API。

**SNMP Adapter**：

- 纯 Python SNMP v2c 实现（`probes/snmp.py`），不依赖外部库或 net-snmp 工具。
- 支持 SNMP GET（单个 OID）、GETNEXT、WALK（子树遍历）。
- 高级接口 `collect_snmp_info`：一次采集 sysDescr、sysName、sysObjectID、sysUpTime、sysContact、sysLocation、sysServices、ifNumber 和接口表信息。
- CLI 命令 `ops probe snmp`：支持设备信息采集和单个 OID 查询。
- Web API 2 个端点：`GET /api/snmp/{target}`（设备信息采集）、`GET /api/snmp/{target}/get`（单个 OID 查询）。
- `ProbeResult.probe_type` 新增 `"snmp"` 类型。
- 告警规则 `AlertCondition.probe_type` 的 Literal 类型已包含 `"snmp"`，但当前未内置 SNMP 告警规则（SNMP 观察值以字符串为主，无数值型指标可直接告警）。

## 下一步规划

Phase 0-12 已全部完成，项目已具备完整的 CLI + Web 运维工具箱 + 主动告警值守 + 历史趋势分析 + AI 运维助手 + 网络拓扑与资产关系 + 受控 Agent 工作流 + Web 操作中心 + 调度告警 Web 管理 + 打包分发 + CLI 交互式诊断 + SNMP 设备管理能力。

核心路线图全部完成。后续按需推进能力扩展路线中的项目。

详细规划见 `docs/plans/phase-5-onwards-planning.md` 和 `docs/plans/phase-10-web-ops-center.md`。

### 后续方向一览

| 方向 | 优先级 | 核心价值 | 状态 |
|---|---|---|---|
| 调度管理 Web UI | P1 | 在 Web 中管理定时任务 | ✅ 已完成 |
| 打包分发（PyInstaller） | P1 | 降低部署门槛，无需 Python 环境 | ✅ 已完成 |
| CLI 体验优化 | P2 | 交互式诊断引导、进度条 | ✅ 已完成 |
| SNMP Adapter | P2 | 扩展网络设备管理能力 | ✅ 已完成 |
| SSH Adapter | P3 | Linux 服务器远程检查 | 待实现 |
| WinRM/WMI Adapter | P3 | Windows 远程管理 | 待实现 |
| WiFi 网络评估 | P3 | 无线网络覆盖检测 | 待实现 |
| 配置备份与变更检测 | P3 | 网络设备配置管理 | 待实现 |

### 关键 ADR

- ADR-0007：AI 集成策略——Copilot 模式与 Adapter 解耦
- ADR-0008：定时巡检与告警通知架构
- ADR-0009：网络拓扑与资产关系采集策略
- ADR-0010：受控 Agent 工作流架构

推荐验证：

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/ -v
python -m it_ops_toolkit workflow list
python -m it_ops_toolkit workflow run network_troubleshoot
python -m it_ops_toolkit workflow history
python -m it_ops_toolkit web run
# 浏览器访问 http://127.0.0.1:8080 体验 Web Console（含操作中心）
```

## 注意事项

- 不要把聊天记录里的无关项目内容带入本仓库。
- 曾经有一次无关上下文混入对话，但已确认没有写进当前仓库文件，也没有进入 git 提交。
- 后续接手应以仓库文档、源码和 git 记录为准。
- 如果新增重要能力，保持小提交，每个提交完成一个可验证切片。
- 新增模块时，先写模块设计文档。
- 改变模块边界时，更新 `docs/02-module-map.md`。
- 做出重要架构选择时，新增 ADR。
