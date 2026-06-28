# Agent Runner 模块

## 模块职责

Agent Runner 在权限、审批、审计和风险控制下执行预定义运维工作流。

它不是"让 AI 随便操作系统"，而是"让 Agent 在受控流程里调用已有能力"。

## 现实场景

运维中常见需要多步骤串联的流程：

- 收到"上不了网"后执行只读诊断流程（互联网诊断 → DNS 诊断 → AI 总结 → 报告）。
- 定期全面巡检（健康检查 → 安全检查 → 资产扫描 → AI 周报）。
- 发现新设备后自动调查（拓扑采集 → 未知设备检测 → 安全检查 → AI 解释）。

如果没有工作流编排，运维人员需要手动依次执行多个命令。Agent Runner 把这些固定模式编排成可审查、可审计的工作流。

## 不负责什么

本模块不负责：

- 无限权限执行。
- 直接绕过审批。
- 自己实现底层探测（调用已有 Probe / Adapter）。
- 隐藏执行步骤。
- 直接处理明文凭据。
- AI 动态决定执行什么操作（工作流是预定义的）。

## 架构设计

### 工作流即代码

工作流是预定义的，不是 AI 动态生成的。用户可以查看工作流定义，知道 Agent 会做什么。

### Action 注册表

所有可执行操作通过 Action 注册表暴露，每个 Action 标注风险等级：

| 类别 | 示例 Action | 风险等级 |
|---|---|---|
| 诊断 | `diagnose.internet`, `diagnose.dns`, `diagnose.intranet` | read_only |
| 巡检 | `health.check`, `health.tcp_matrix` | read_only |
| 资产 | `asset.scan`, `asset.diff` | read_only |
| 安全 | `security.check`, `security.cert_check` | read_only |
| 拓扑 | `topology.show`, `topology.arp` | read_only |
| AI | `ai.summarize`, `ai.explain` | read_only |
| 报告 | `report.generate` | read_only |
| 自动化 | `automate.flush_dns` | low_change |

### 风险分级与执行策略

| 风险等级 | 执行策略 | 审批 |
|---|---|---|
| `read_only` | 自动执行 | 不需要 |
| `low_change` | 暂停等待 | 需要（CLI `--confirm` 或 Web 审批） |
| `high_change` | 拒绝执行 | Phase 9 不支持 |

### 执行引擎

1. 解析工作流定义。
2. 按依赖顺序执行 Step。
3. 风险检查 → 自动 / 暂停 / 拒绝。
4. 记录每步执行结果到 SQLite。
5. 满足停止条件时终止。
6. 生成执行报告。

## 输入

- 工作流名称（选择预定义工作流）。
- 触发来源（manual / cli / web / alert）。
- 上下文参数（如目标 IP、目标 URL 等）。
- 审批状态（对低风险变更步骤）。

## 输出

- `WorkflowExecution`：完整执行记录。
- 每个 Step 的 `WorkflowStepExecution`：状态、结果、耗时。
- 最终结果摘要。
- 审计记录（持久化到 SQLite）。

## 数据模型

### WorkflowStepDef

工作流步骤定义：
- `id`：步骤标识。
- `action`：注册的 action 名。
- `risk_level`：风险等级。
- `params`：参数。
- `depends_on`：依赖步骤。
- `condition`：条件表达式（可选）。
- `stop_on_failure`：失败时是否停止工作流。

### WorkflowDefinition

工作流定义：
- `name`：工作流名称。
- `description`：描述。
- `steps`：步骤列表。
- `triggers`：支持的触发方式。

### WorkflowStepExecution

步骤执行记录：
- `step_id`、`action`、`status`、`risk_level`。
- `started_at`、`ended_at`。
- `result`：执行结果。
- `error`：错误信息。
- `task_id`：关联的 TaskRun ID。

### WorkflowExecution

工作流执行记录：
- `id`、`workflow_name`、`status`。
- `trigger`：触发来源。
- `steps`：步骤执行列表。
- `started_at`、`ended_at`。
- `context`：上下文参数。
- `result_summary`：结果摘要。

## 内置工作流

| 工作流 | 描述 | Steps |
|---|---|---|
| `network_troubleshoot` | 网络故障排查 | 互联网诊断 → DNS 诊断 → AI 总结 |
| `full_inspection` | 全面巡检 | 健康检查 → 安全检查 → AI 周报 |
| `new_device_investigate` | 新设备调查 | 拓扑采集 → 未知设备检测 → AI 解释 |

## 依赖模块

依赖：

- 配置中心：读取工作流配置。
- 数据存储：保存执行记录。
- 诊断模块：`diagnose.*` action。
- 巡检模块：`health.*` action。
- 资产模块：`asset.*` action。
- 安全模块：`security.*` action。
- 拓扑模块：`topology.*` action。
- AI 模块：`ai.*` action。
- 报告模块：`report.*` action。
- 自动化模块：`automate.*` action。

被依赖：

- Web Console。
- CLI。
- 未来 API。

## Phase 9 实现计划

1. 定义数据模型（`models.py`）。
2. 实现 Action 注册表和工作流引擎（`agent_workflow.py`）。
3. 扩展存储层（`storage.py`）。
4. 实现 CLI 命令（`cli.py`）。
5. 实现 Web API（`web/app.py`）。
6. 预置 3 个内置工作流。
7. 编写测试。

## 验收标准

Phase 9 完成时应满足：

- ✅ 能定义和执行预定义工作流。
- ✅ Agent 可以执行只读诊断流程。
- ✅ 涉及风险动作时必须请求审批。
- ✅ 每一步执行都有审计记录。
- ✅ 工作流可被 CLI 和 Web 调用。
- ✅ 支持暂停/恢复（审批后继续）。
- ✅ 支持手动取消。

详细架构决策见 ADR-0010。
