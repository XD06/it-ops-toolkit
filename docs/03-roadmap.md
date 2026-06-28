# 路线图

## 路线图原则

路线图不是功能愿望清单，而是控制项目节奏的工具。

本项目要避免两个极端：

- 一开始只写零散脚本，后面无法扩展。
- 一开始就做大平台，长期没有可用成果。

正确路线是：先建立平台骨架，再通过一个个可运行模块逐步扩展。

## Phase 0：文档与架构基础 ✅

目标：在写代码前建立项目记忆。

交付物：

- 项目愿景。
- 总开发与架构文档。
- 模块地图。
- 开发规则。
- 术语表。
- 调研依据。
- 第一条 ADR。
- 初始模块文档。

验收标准：

- 能清楚说明第一阶段做什么，不做什么。
- 能清楚说明模块边界。
- 能清楚说明 CLI、Web、AI、Agent 的关系。
- 后续开发某模块时，不需要重新讨论整个大方向。

状态：已完成（2026-06-08）。

## Phase 1：CLI 基础与最小运维闭环 ✅

目标：做出一个实际可用的 CLI 工具箱。

交付物：

- CLI 入口（`ops`）。
- 配置中心（YAML 配置 + Pydantic 模型）。
- 基础 Adapter：Ping、DNS、TCP、HTTP、TLS 证书。
- 资产发现（网段扫描、Ping+TCP 发现、变化对比、备注导入）。
- 网络与服务巡检（批量检查、TCP Matrix、HTTP Matrix）。
- 结构化结果模型（ProbeResult：观察值、证据、状态）。
- 本地数据存储（SQLite）。
- 报告生成（Markdown / CSV / JSON）。
- 诊断包导出。

详细实施顺序见 `docs/plans/phase-1-cli-foundation.md`。

验收标准：

- 用户能配置一个网段或目标列表。
- 用户能运行资产发现命令。
- 用户能运行巡检命令。
- 系统能保存结构化结果。
- 系统能生成可读报告。
- CLI 不包含核心业务逻辑。
- 未来 Web 可以复用同一批服务。

状态：已完成（2026-06-27）。

## Phase 2：场景化故障诊断 ✅

目标：把单项检查变成排障流程。

交付物：

- 诊断工作流格式（DiagnosisResult + Finding 证据链）。
- 6 个诊断场景：
  - 上不了网（互联网连通性）。
  - 内网系统打不开（内网可达性）。
  - 远程桌面连不上（RDP 诊断）。
  - DNS 异常（多 DNS 服务器对比）。
  - 网络很慢（RTT + 丢包分析）。
  - 打印机不可达（打印机诊断）。
- 诊断报告。
- 证据链输出（Finding：严重程度、标题、描述、建议）。

验收标准：

- 用户能选择一个故障场景。
- 系统能自动执行相关检查。
- 系统能输出可能原因、证据和下一步建议。

状态：已完成（2026-06-27）。

## Phase 3：轻量安全与自动化动作 ✅

目标：覆盖中小企业最常见的基础风险，并标准化低风险动作。

交付物：

- 高风险端口检查。
- 证书过期检查。
- 自动化动作风险分级（只读 / 低风险变更 / 高风险变更）。
- DNS 缓存清理（dry-run + confirm 双确认）。

验收标准：

- 系统能输出风险清单。
- 自动化动作都有风险等级。
- 高风险动作不会被默认自动执行。

状态：已完成（2026-06-27）。

## Phase 4：Web Console MVP ✅

目标：在不重写核心逻辑的前提下增加 Web 可视化。

交付物：

- FastAPI REST API（15+ 端点）。
- 自包含 HTML/JS 仪表盘（暗色主题）。
- 资产列表与详情查看。
- 任务历史与筛选（按类型/状态）。
- 报告查看与下载。
- 配置查看。
- 手动任务触发（巡检、资产扫描）。
- CLI `ops web run` 命令。

验收标准：

- Web 调用已有应用服务。
- Web 不直接调用 Adapter。
- Web 能查看 CLI 产生的历史结果。

状态：已完成（2026-06-27）。

## Phase 5：定时巡检与告警通知 ✅

目标：从被动工具变成主动值守系统。

交付物：

- 定时任务调度器（cron 式周期巡检）。
- 告警规则模型与评估引擎。
- 通知中心（邮件 + Webhook 优先）。
- 通知降噪（同一问题不重复告警）。
- CLI `ops schedule` 命令组。
- CLI `ops alert` 命令组。
- 5 种通知渠道（Email / Webhook / 企业微信 / 钉钉 / 飞书）。
- 告警规则配置驱动（YAML），不硬编码。
- 凭据通过环境变量注入（`${ENV_VAR}`）。
- 调度状态和告警事件持久化到 SQLite。

验收标准：

- 能配置定时巡检并自动执行。
- 告警规则能触发通知。
- 通知能发送到至少邮件和 Webhook。
- 同一问题在恢复前不重复告警。
- 定时任务有审计记录。

详细架构决策见 ADR-0008。

状态：已完成（2026-06-27）。

## Phase 6：历史趋势与可视化 ✅

目标：让已有数据产生洞察。

交付物：

- 存储层时间范围查询和聚合（`list_probe_results_between`、`get_probe_stats`、`get_status_distribution`）。
- 趋势分析服务（`trend.py`：`get_trend`、`get_trend_summary`、`list_available_targets`）。
- Web API 趋势端点（3 个：targets / probe / summary）。
- CLI `ops trend` 命令组（targets / show / summary）。
- 聚合在 SQLite 层完成，支持 daily / hourly 粒度，计算 count / avg / min / max / p95。
- 状态分布统计（success / failed / timeout / skipped + success_rate）。
- 趋势数据结构化输出，可被 CLI、Web、AI 复用。

验收标准：

- 能查询指定时间范围内的探测结果。
- 能生成按天/小时的聚合统计。
- 聚合结果包含 avg/min/max/p95。
- 能统计状态分布和成功率。
- 趋势数据可作为 AI 输入。

状态：已完成（2026-06-27）。

## Phase 7：AI 运维助手 ✅

目标：让 AI 基于结构化数据做解释、总结和建议。

交付物：

- `AIInput` / `AIOutput` / `AICallLog` 数据模型（`models.py`）。
- `AIAdapter` 接口与三种实现（`ai_copilot.py`）：
  - `TemplateAdapter`：零成本规则模板引擎，不依赖任何外部服务。
  - `OpenAIAdapter`：OpenAI 兼容 API（可选依赖 `openai`）。
  - `OllamaAdapter`：本地模型 Ollama REST API（可选依赖 `httpx`）。
- AI 脱敏处理（`sanitize_ai_input`）：移除 password/token/secret/api_key，代理 URL 凭据脱敏。
- AI 领域服务：`summarize_task`（任务摘要）、`summarize_recent`（周报）、`explain_anomaly`（异常解释）。
- AI 调用降级机制：AI 后端调用失败时自动降级为 TemplateAdapter。
- AI 审计日志：每次 AI 调用记录到 SQLite（`ai_call_logs` 表）。
- CLI `ops ai` 命令组：`summarize` / `explain` / `weekly` / `logs`。
- Web API 4 个端点：`/api/ai/summarize/{task_id}` / `/api/ai/explain/{task_id}` / `/api/ai/weekly` / `/api/ai/logs`。
- AI 输出严格区分 `facts`（事实）和 `inferences`（推断）。
- `confidence < 0.7` 时自动设置 `needs_human_review = true`。

验收标准：

- AI 能引用结构化结果。
- AI 输出能区分事实、推断和建议。
- AI 不默认执行高风险动作。
- AI 后端可切换（OpenAI / Ollama / Template）。
- AI 输入不包含敏感信息。
- TemplateAdapter 作为默认兜底，不依赖任何外部服务。
- OpenAI 和 Ollama 适配器是可选依赖，核心包不强依赖。
- AI 调用有审计日志。

详细架构决策见 ADR-0007。

状态：已完成（2026-06-27）。

## Phase 8：网络拓扑与资产关系 ✅

目标：从扁平 IP 列表升级为有连接关系的网络视图。

交付物：

- ARP 表采集 Adapter（`probes/arp.py`）：跨平台支持 Windows `arp -a` 和 Linux `ip neigh` / `arp -n`。
- OUI 厂商识别：内置精简 OUI 数据库（40+ 常见厂商前缀），离线可用。
- Traceroute Adapter（`probes/traceroute.py`）：跨平台支持 Windows `tracert` 和 Linux `traceroute` / `tracepath`。
- 拓扑数据模型（`models.py`）：`ArpEntry` / `TraceRouteHop` / `TraceRouteResult` / `AssetReconciliation` / `TopologyView`。
- 拓扑分析服务（`topology.py`）：采集接口、网关、ARP 表、可选 traceroute，与资产库对比。
- 未知设备检测：ARP 表中有但资产库中没有的设备标记为“新设备”。
- 设备类型推断：根据 OUI 厂商推断 `network_device` / `printer` / `server` / `iot` / `nas` / `virtual` 等。
- CLI `ops topology` 命令组：`show` / `arp` / `unknown`。
- CLI `ops probe traceroute` 命令。
- Web API 端点：`/api/topology` / `/api/topology/arp` / `/api/topology/unknown` / `/api/topology/traceroute/{target}`。
- 测试覆盖：30 个测试覆盖 ARP 解析、OUI 查询、设备类型推断、traceroute 解析、资产对比、未知设备检测。

验收标准：

- ✅ 能采集本机 ARP 表。
- ✅ 能展示 IP-MAC-厂商对应关系。
- ✅ 能检测 ARP 表中不在资产库的 MAC。
- ✅ 能展示基础网关→终端拓扑。

详细架构决策见 ADR-0009。

## Phase 9：受控 Agent 工作流 ✅

目标：让 Agent 在审批和审计保护下执行预定义流程。

交付物：

- 工作流定义模型（`WorkflowDefinition` / `WorkflowStepDef`）。
- 工作流执行记录模型（`WorkflowExecution` / `WorkflowStepExecution`）。
- Action 注册表（`ActionRegistry`）：管理所有可执行操作及其风险等级。
- 工作流执行引擎（`agent_workflow.py`）：按依赖顺序执行步骤，风险检查，审计记录。
- 风险分级执行策略：
  - `read_only`：自动执行，无需审批。
  - `low_change`：暂停等待审批（`--confirm` 或 Web 审批）。
  - `high_change`：拒绝执行（Phase 9 不支持）。
- 3 个内置工作流：`network_troubleshoot` / `full_inspection` / `new_device_investigate`。
- 存储层扩展：`workflow_executions` 表，支持保存/查询执行记录。
- CLI `ops workflow` 命令组：`list` / `run` / `show` / `history`。
- Web API 4 个端点：`/api/workflows` / `/api/workflows/{name}/run` / `/api/workflows/executions` / `/api/workflows/executions/{id}`。
- 测试覆盖：24 个测试覆盖工作流定义、Action 注册表、执行引擎、风险分级、存储层、数据模型。

验收标准：

- ✅ Agent 可以执行只读诊断流程。
- ✅ 涉及风险动作时必须请求审批。
- ✅ 每一步执行都有审计记录。

详细架构决策见 ADR-0010。

## Phase 10：Web Console 操作中心 ✅

目标：将 Web Console 从"只读仪表盘"升级为"可执行控制台"，让运维人员可以在浏览器中直接执行操作。

交付物：

- 新增 8 个 POST 操作端点（`/api/ops/*`）：诊断触发、安全检查、证书检查、报告生成、资产对比、本机采集、DNS 缓存清理。
- 操作中心 UI 页面：7 个操作卡片，每个标注风险等级。
- 诊断卡片支持 6 种场景选择和目标参数输入。
- DNS 缓存清理区分 Dry Run 预览和确认执行。
- 操作结果直接在卡片下方展示，同时写入任务历史。
- 所有操作端点只调用领域服务函数，不直接调用 Adapter。

验收标准：

- ✅ 用户可在 Web Console 中触发所有核心运维操作。
- ✅ 操作结果有结构化输出和任务记录。
- ✅ 变更操作有风险标签和确认机制。
- ✅ Web 层不直接调用 Adapter。

详细规划见 `docs/plans/phase-10-web-ops-center.md`。

## Phase 11：调度告警 Web 管理 + 打包分发 ✅

目标：在 Web Console 中实现定时任务和告警的可视化管理，并提供 PyInstaller 打包能力。

交付物：

**调度告警 Web 管理**：

- 新增 8 个 Web API 端点（`/api/schedules` CRUD + `/api/alerts` 列表/确认）。
- Web Console 新增“调度告警”页面：
  - 定时任务表格（列表/添加/删除/启用禁用/立即执行）。
  - 告警事件表格（状态筛选/一键确认）。
- Web 端能力与 CLI `ops schedule` / `ops alert` 完全对等。

**打包分发（PyInstaller）**：

- `build/it_ops_toolkit.spec`：PyInstaller spec 文件。
- `build/build_exe.py`：打包脚本（支持 `--cli` / `--clean`）。
- `pyproject.toml` 新增 `[build]` 可选依赖组。
- 打包为单文件可执行程序，无需 Python 环境。

验收标准：

- ✅ 用户可在 Web Console 中管理定时任务和查看告警。
- ✅ 打包后的可执行程序可独立运行。
- ✅ Web API 与 CLI 能力对等。

## Phase 12：CLI 体验优化 + SNMP Adapter ✅

目标：提升 CLI 使用体验，并扩展网络设备管理能力。

交付物：

**CLI 体验优化**：

- 交互式诊断引导（`ops diagnose`）：不指定子命令时进入交互式菜单。
- Rich 进度条：巡检、资产扫描、TCP/HTTP Matrix 新增实时进度显示。
- 领域服务新增 `progress_callback` 可选参数，不破坏现有 API。

**SNMP Adapter**：

- 纯 Python SNMP v2c 实现，不依赖外部库。
- 支持 GET / GETNEXT / WALK。
- 高级接口 `collect_snmp_info`：采集设备基础信息。
- CLI `ops probe snmp` 命令。
- Web API 2 个端点。
- `probe_type` 新增 `"snmp"` 类型（ProbeResult 和 AlertCondition 的 Literal 已包含，但当前无内置 SNMP 告警规则实现）。

验收标准：

- ✅ 用户可通过交互式菜单选择诊断场景。
- ✅ 长耗时操作有进度反馈。
- ✅ 可通过 SNMP 采集网络设备信息。
- ✅ SNMP 探针不依赖外部库。

## 能力扩展路线（穿插推进）

以下能力不单独成 Phase，而是作为持续改进项，按需穿插在各 Phase 中：

### Adapter 扩展

| Adapter | 预计 Phase | 前置条件 |
|---|---|---|
| ARP 表 | Phase 8 | 无 |
| Traceroute | Phase 8 | 无 |
| SNMP | Phase 12 | 无（纯 Python 实现） |
| WinRM/WMI | Phase 9+ | 可选依赖 `pywinrm` |
| SSH | Phase 9+ | 可选依赖 `paramiko` |

### Web Console UI 升级

- ~~Phase 5：调度管理页。~~
- ~~Phase 6：趋势图表、数据可视化升级。~~ ✅
- ~~Phase 7：AI 辅助面板。~~ ✅
- ~~Phase 8：拓扑视图。~~ ✅
- ~~Phase 9：工作流管理页。~~ ✅
- ~~Phase 10：操作中心页。~~ ✅
- ~~Phase 11：调度告警页。~~ ✅

### CLI 体验优化

- ~~交互式诊断引导。~~ ✅
- ~~进度条和实时反馈。~~ ✅
- 彩色输出优化。

### 打包与分发

- ~~Windows 可执行文件打包。~~ ✅
- ~~降低部署门槛，运维人员不需要 Python 环境。~~ ✅

## 当前推荐下一步

Phase 0-12 已全部完成，项目已具备完整的 CLI + Web 运维工具箱 + 主动告警值守 + 历史趋势分析 + AI 运维助手 + 网络拓扑与资产关系 + 受控 Agent 工作流 + Web 操作中心 + 调度告警 Web 管理 + 打包分发 + CLI 交互式诊断 + SNMP 设备管理能力。

核心路线图全部完成。后续可按需推进能力扩展路线中的项目：

| 方向 | 优先级 | 核心价值 |
|---|---|---|
| SSH Adapter | P3 | Linux 服务器远程检查 |
| WinRM/WMI Adapter | P3 | Windows 远程管理 |
| WiFi 网络评估 | P3 | 无线网络覆盖检测 |
| 配置备份与变更检测 | P3 | 网络设备配置管理 |

详细规划见 `docs/plans/phase-5-onwards-planning.md` 和 `docs/plans/phase-10-web-ops-center.md`。

接手细节见 `docs/06-current-status-and-handoff.md`。
