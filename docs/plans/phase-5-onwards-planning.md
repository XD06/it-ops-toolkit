# Phase 5+ 全局规划

## 文档目的

本文档是 Phase 1-4 完成后的全局规划。它回答三个问题：

1. 当前项目到了哪里。
2. 还缺什么。
3. 接下来按什么顺序补。

本文档不是功能愿望清单，而是基于中小企业网络运维真实场景的差距分析和优先级排序。具体实现前，每个方向应先补充 ADR 和模块文档更新。

## 当前状态

### 已完成的 Phase

| Phase | 名称 | 完成时间 | 交付物 |
|---|---|---|---|
| Phase 0 | 文档与架构基础 | 2026-06-08 | 愿景、架构、模块地图、开发规则、6 条 ADR、17 个模块文档 |
| Phase 1 | CLI 基础与最小运维闭环 | 2026-06-27 | CLI、配置、5 种探针、资产发现、巡检、存储、报告 |
| Phase 2 | 场景化故障诊断 | 2026-06-27 | 6 个诊断场景（互联网、内网、RDP、打印机、DNS、网络慢） |
| Phase 3 | 轻量安全与自动化 | 2026-06-27 | 高风险端口、证书检查、DNS 缓存清理 |
| Phase 4 | Web Console | 2026-06-27 | 仪表盘、REST API、手动触发、配置查看、任务筛选 |
| Phase 5 | 定时巡检与告警通知 | 2026-06-27 | 调度引擎、告警引擎、通知中心（5 种渠道） |
| Phase 6 | 历史趋势与可视化 | 2026-06-27 | 趋势分析服务、SVG 图表、CLI/Web API |
| Phase 7 | AI 运维助手 | 2026-06-27 | AI Adapter（OpenAI/Ollama/Template）、脱敏、降级、审计 |
| Phase 8 | 网络拓扑与资产关系 | 2026-06-27 | ARP 表、OUI 厂商识别、Traceroute、拓扑视图 |
| Phase 9 | 受控 Agent 工作流 | 2026-06-27 | 工作流引擎、风险分级、3 个内置工作流、审计记录 |
| Phase 10 | Web Console 操作中心 | 2026-06-28 | 8 个操作端点、操作中心 UI 页面、Web 可执行控制台 |

测试覆盖：321 个单元测试。

### 已实现的能力矩阵

#### 探针 / Adapter 层

| 探针 | 能力 | 跨平台 |
|---|---|---|
| Ping | 可达性、RTT(min/avg/max)、丢包率 | Windows + Linux |
| DNS | 系统解析、nslookup 指定服务器对比 | Windows + Linux |
| TCP | 端口可达性、连接耗时 | 跨平台 |
| HTTP | 状态码、响应时间 | 跨平台 |
| TLS 证书 | 过期时间、剩余天数 | 跨平台 |
| ARP 表 | IP-MAC-厂商映射、未知设备检测 | Windows + Linux |
| Traceroute | 路由追踪、每跳 RTT | Windows + Linux |

#### 领域服务层

| 模块 | 能力 |
|---|---|
| 资产与拓扑 | 网段扫描、Ping+TCP 发现、资产列表/详情/导出/变化对比/备注导入、ARP 表、拓扑视图 |
| 巡检 | 按配置批量检查(Ping/DNS/TCP/HTTP)、TCP Matrix、HTTP Matrix |
| 诊断 | 互联网、内网、RDP、打印机、DNS(多服务器对比)、网络慢(RTT+丢包) |
| 安全 | 高风险端口、证书过期 |
| 自动化 | DNS 缓存清理(dry-run + confirm) |
| 报告 | Markdown/CSV/JSON 生成 |
| 采集 | 本机系统信息、网卡、路由、DNS、代理(脱敏) |
| 导出 | 诊断包(任务+资产+结果+发现+快照+摘要) |
| 调度 | 定时任务(cron)、告警引擎、通知中心(5种渠道) |
| 趋势 | 时间范围查询、聚合统计(avg/min/max/p95)、状态分布 |
| AI | 任务摘要、异常解释、周报、脱敏、降级、审计日志 |
| 工作流 | 工作流引擎、风险分级、3个内置工作流、审计记录 |

#### 入口层

| 入口 | 能力 |
|---|---|
| CLI | 51 个命令覆盖全部运维操作 |
| Web Console | 10 个页面、40 个 API 端点（30 GET + 10 POST）、操作中心可执行运维操作 |

### 架构健康度

- 分层清晰：入口层 → 领域服务 → Adapter → 数据层
- 结构化优先：所有探测产生 `ProbeResult`，包含观察值、证据、状态
- 任务记录：所有操作有 `TaskRun` 记录，可审计
- 风险分级：只读 / 低风险变更 / 高风险变更
- 证据链：诊断产生 `Finding`，含严重程度和建议
- Web Console 可执行：不仅查看，还能通过操作中心触发运维操作
- 完整审计：CLI 和 Web 触发的操作都有 `source` 标记和审计记录

## 差距分析

Phase 0-10 已全部完成，原差距分析中的紧迫缺口已全部补齐：

- ✅ 定时巡检与告警通知（Phase 5）
- ✅ 历史趋势与对比（Phase 6）
- ✅ 网络拓扑与资产关系（Phase 8）
- ✅ AI 报告摘要（Phase 7）
- ✅ 受控 Agent 工作流（Phase 9）
- ✅ Web Console 可执行操作（Phase 10）

## 当前待推进的方向

以下方向按优先级排序，可作为后续开发的参考：

### P1：调度管理 Web UI

**现状**：调度功能只在 CLI 中可用（`ops schedule`），Web Console 缺少调度管理页面。

**需要**：
- 新增 `/api/schedules` Web API（GET 列表 / POST 添加 / DELETE 删除 / PUT 启用禁用）
- Web Console 新增调度管理页（定时任务列表、添加/删除/启用/禁用）
- 告警事件列表页（查看/确认告警）

### P1：打包分发

**现状**：使用需要 Python 环境和 `pip install`。

**需要**：
- PyInstaller 打包为 Windows 可执行文件
- 降低部署门槛，运维人员不需要 Python 环境
- 生成单文件 exe 或 onedir 目录

### P2：CLI 体验优化

**现状**：CLI 命令功能完整，但缺少交互式引导和进度反馈。

**需要**：
- 交互式诊断引导（选择场景 → 输入目标 → 查看结果）
- 彩色进度条和实时反馈
- `ops` 无参数时的交互式菜单

### P2：SNMP Adapter

**现状**：无法获取交换机/路由器接口状态和流量数据。

**需要**：
- `pysnmp` 可选依赖
- 交换机接口状态查询
- 端口列表和流量采集

### P3：SSH Adapter

**现状**：无法远程检查 Linux 服务器。

**需要**：
- `paramiko` 可选依赖
- 远程命令执行
- 配置文件备份

### P3：WinRM/WMI Adapter

**现状**：无法远程管理 Windows 主机。

**需要**：
- `pywinrm` 可选依赖
- 远程 Windows 管理

### P3：WiFi 网络评估

**现状**：无无线网络相关能力。

**需要**：
- 信号强度检测（`netsh wlan show interfaces`）
- 已连接设备列表
- 信道信息

## AI 集成策略

### 定位

AI 是 Copilot（助手），不是自动执行者。AI 消费结构化数据做解释、总结和建议，不替代确定性业务规则，不默认执行高风险动作。

### 分阶段落地

#### 第一步：AI 报告摘要

**价值**：最高性价比，风险最低。把结构化 `ProbeResult` + `Finding` 转成人类可读摘要。

**实现**：
- 定义 `AIInput` 和 `AIOutput` 数据模型
- `AIOutput` 区分 `facts`（事实）、`inferences`（推断）、`recommendations`（建议）、`needs_human_review`（需人工确认）
- 新增 `ai_adapter.py`，封装 AI 调用，支持切换后端（OpenAI API / 本地模型 / 模板引擎）
- CLI 新增 `ops ai summarize --task <task_id>` 命令
- Web Console 新增"AI 总结"按钮

**输入示例**：
```json
{
  "task": {"id": "task-abc", "task_type": "health_check", "status": "success"},
  "results": [
    {"probe_type": "ping", "target": "192.168.1.1", "status": "success", "observations": {"avg_rtt_ms": 5, "packet_loss_percent": 0}},
    {"probe_type": "dns", "target": "www.example.com", "status": "success", "observations": {"addresses": ["93.184.216.34"], "duration_ms": 12}}
  ],
  "findings": [
    {"severity": "high", "title": "192.168.1.50 的 445 端口开放", "description": "SMB 端口暴露在非可信网段"}
  ]
}
```

**输出示例**：
```json
{
  "summary": "巡检整体正常，1 个安全发现需关注",
  "facts": [
    "网关 192.168.1.1 可达，平均延迟 5ms，无丢包",
    "DNS 解析 www.example.com 正常，耗时 12ms",
    "192.168.1.50 的 445 端口处于开放状态"
  ],
  "inferences": [
    "445 端口是 SMB 文件共享端口，在非可信网段暴露存在勒索病毒攻击风险"
  ],
  "recommendations": [
    "建议在防火墙限制 192.168.1.50 的 445 端口访问来源",
    "确认该主机是否需要提供文件共享服务"
  ],
  "needs_human_review": true
}
```

#### 第二步：AI 诊断助手

**价值**：自然语言交互，降低使用门槛。

**实现**：
- 用户在 Web Console 或 CLI 中用自然语言提问
- AI 理解意图 → 选择诊断场景 → 调用 `run_*_diagnosis` → 解释结果
- 关键设计：AI 只做意图理解和结果解释，实际探测由确定性代码执行
- AI 不能自己调用 `ping` 或 `nslookup`

#### 第三步：AI 周报和复盘

- 自动汇总一周的巡检结果、异常事件、处理动作
- 生成管理层可读版本（突出影响和趋势）
- 生成运维团队技术版本（包含证据链和操作记录）

#### 第四步：SOP 匹配

- 维护知识库（SOP 文档）
- 诊断发现问题时，AI 自动匹配相关 SOP
- AI 引用知识库时必须标注来源

### AI 后端选型

| 方案 | 优点 | 缺点 | 适用场景 |
|---|---|---|---|
| OpenAI API | 效果最好 | 需要外网、费用、数据隐私 | 有外网环境 |
| 本地模型 (Ollama) | 数据不出内网、免费 | 效果不如 GPT-4、需要硬件 | 注重隐私的中小企业 |
| 规则模板引擎 | 零成本、零风险 | 不够灵活 | 最简单的摘要 |

**架构决策**：采用 Adapter 模式，AI 调用封装成 `AIAdapter` 接口，支持切换后端。领域服务不依赖具体 AI 实现。详见 ADR-0007。

### AI 安全规则

已在 `docs/04-development-rules.md` 中定义：

- AI 输出区分：已确认事实 / 推断 / 建议 / 需人工确认
- AI 不能看到明文密码、Token、私钥
- AI 不能默认执行高风险动作
- AI 不能把推断伪装成确定结论
- AI 不应隐藏事实来源

## 新 Phase 划分

基于差距分析，重新划分后续 Phase。原 Phase 5 (AI) 和 Phase 6 (Agent) 保持，但插入新的 Phase 来覆盖紧迫缺口。

### Phase 5：定时巡检与告警通知

**目标**：从被动工具变成主动值守系统。

**交付物**：
- 定时任务调度器（cron 式周期巡检）
- 告警规则模型与评估引擎
- 通知中心（邮件 + Webhook 优先）
- 通知降噪（同一问题不重复告警）
- CLI `ops schedule` 命令组
- Web Console 调度管理页

**验收标准**：
- 能配置定时巡检并自动执行
- 告警规则能触发通知
- 通知能发送到至少邮件和 Webhook
- 同一问题在恢复前不重复告警
- 定时任务有审计记录

**详细架构决策**：见 ADR-0008。

### Phase 6：历史趋势与可视化

**目标**：让已有数据产生洞察。

**交付物**：
- 存储层时间范围查询和聚合
- 趋势分析服务
- Web API 趋势端点
- Web Console 趋势图表（SVG 折线图、状态分布图）
- CLI `ops trend` 命令

**验收标准**：
- 能查询指定时间范围内的探测结果
- 能生成按天/小时的聚合统计
- Web Console 能展示趋势图
- 趋势数据可作为 AI 输入

### Phase 7：AI 运维助手

**目标**：让 AI 基于结构化数据做解释、总结和建议。

**交付物**：
- `AIInput` / `AIOutput` 数据模型
- `AIAdapter` 接口与实现（OpenAI / Ollama / 模板引擎）
- AI 报告摘要（`ops ai summarize`）
- AI 异常解释
- AI 排障建议
- AI 周报草稿
- Web Console AI 辅助功能

**验收标准**：
- AI 能引用结构化结果
- AI 输出区分事实、推断和建议
- AI 不默认执行高风险动作
- AI 后端可切换
- AI 输入不包含敏感信息

**详细架构决策**：见 ADR-0007。

### Phase 8：网络拓扑与资产关系

**目标**：从扁平 IP 列表升级为有连接关系的网络视图。

**交付物**：
- ARP 表采集 Adapter
- 资产模型扩展（MAC→IP 映射、上游网关）
- 基础拓扑展示
- 未知 MAC 检测
- Web Console 拓扑视图

**验收标准**：
- 能采集本机 ARP 表
- 能展示 IP-MAC-厂商对应关系
- 能检测 ARP 表中不在资产库的 MAC
- 能展示基础网关→终端拓扑

**详细架构决策**：见 ADR-0009。

### Phase 9：受控 Agent 工作流

**目标**：让 Agent 在审批和审计保护下执行预定义流程。

**交付物**：
- 工作流定义
- 风险分类
- 权限检查
- 审批点
- 执行日志
- 停止条件
- 人工接管机制

**验收标准**：
- Agent 可以执行只读诊断流程
- 涉及风险动作时必须请求审批
- 每一步执行都有审计记录

## 能力扩展路线（与 Phase 并行推进）

以下能力不单独成 Phase，而是作为持续改进项，按需穿插在各 Phase 中：

### Adapter 扩展

| Adapter | 预计 Phase | 前置条件 |
|---|---|---|
| ARP 表 | Phase 8 | 无 |
| Traceroute | Phase 8 | 无 |
| SNMP | Phase 5+ | 可选依赖 `pysnmp` |
| WinRM/WMI | Phase 9+ | 可选依赖 `pywinrm` |
| SSH | Phase 9+ | 可选依赖 `paramiko` |

### Web Console UI 升级

穿插在 Phase 5-8 中：
- Phase 5：调度管理页
- Phase 6：趋势图表、数据可视化升级
- Phase 7：AI 辅助面板
- Phase 8：拓扑视图

### CLI 体验优化

穿插在各 Phase 中：
- 交互式诊断引导
- 进度条和实时反馈
- 彩色输出优化

### 打包与分发

在 Phase 5 完成后进行，降低分发门槛。

## 优先级排序

综合"对用户的实际价值"和"实现难度"：

| 优先级 | 任务 | 价值 | 难度 | 预计 Phase |
|---|---|---|---|---|
| P0 | 定时巡检 + 告警通知 | 从工具变成值守系统 | 中 | Phase 5 |
| P0 | 历史趋势查询 + 图表 | 数据已有，只缺消费 | 低 | Phase 6 |
| P1 | AI 报告摘要 | 最高性价比 AI 场景 | 中 | Phase 7 |
| P1 | Web Console UI 升级 | 提升使用体验 | 中 | 穿插 |
| P1 | ARP 表 + 资产关系 | 补全网络可见性 | 低 | Phase 8 |
| P2 | SNMP Adapter | 扩展设备管理能力 | 高 | Phase 5+ |
| P2 | Traceroute Adapter | 路由诊断 | 低 | Phase 8 |
| P2 | Windows 可执行文件打包 | 降低部署门槛 | 低 | Phase 5 后 |
| P3 | AI 诊断助手 | 自然语言交互 | 高 | Phase 7 |
| P3 | WinRM/WMI Adapter | Windows 远程管理 | 高 | Phase 9+ |
| P3 | WiFi 网络评估 | 无线网络覆盖 | 高 | 未来 |

## 技术约束

1. **可选依赖**：SNMP、SSH、WinRM 等重型依赖必须是可选安装（`pip install 'it-ops-toolkit[snmp]'`），核心工具箱只依赖 pydantic、PyYAML、rich、typer。
2. **自包含前端**：Web Console 不依赖外部 CSS/JS 框架，适合离线运维环境。数据可视化使用原生 SVG。
3. **跨平台**：所有 Adapter 必须同时兼容 Windows 和 Linux。Windows 是主要运维环境。
4. **数据隐私**：AI 输入不包含明文密码、Token、私钥。代理 URL 中的凭据已脱敏。
5. **结构化优先**：所有新功能必须产生结构化结果，不只是文本输出。
6. **风险分级**：新增自动化动作必须有风险等级标注，高风险动作不默认自动执行。

## 文档维护要求

- 每个新 Phase 开始前，先更新对应的 ADR 和模块文档。
- 新增高频术语时，补充 `docs/glossary.md`。
- 做出重要架构选择时，新增 ADR。
- Phase 完成后，更新 `docs/06-current-status-and-handoff.md`。
