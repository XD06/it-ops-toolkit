# ADR 0010：受控 Agent 工作流架构

## 状态

已接受，作为 Phase 9（受控 Agent 工作流）的架构方向。

## 背景

Phase 1-8 已建立了完整的运维工具箱：

- 资产发现与拓扑（Phase 1, 8）
- 场景化故障诊断（Phase 2）
- 安全检查（Phase 3）
- Web Console（Phase 4）
- 定时巡检与告警（Phase 5）
- 历史趋势分析（Phase 6）
- AI 运维助手（Phase 7）

但所有操作都需要人工手动触发。当用户报告"上不了网"时，运维人员需要手动依次执行：

1. `ops diagnose internet` — 诊断互联网连通性
2. `ops diagnose dns` — 诊断 DNS 解析
3. `ops diagnose intranet` — 诊断内网系统
4. `ops ai summarize` — AI 总结
5. `ops report generate` — 生成报告

这些步骤是固定模式，适合自动化编排。但直接让 AI 自由操作系统是危险的——没有审计、没有审批、没有风险控制。

Phase 9 需要解决的核心问题：**如何让 Agent 在受控流程里调用已有能力，而不是变成不可审计的黑箱自动化。**

## 决策

### 1. 工作流即代码（Workflow as Code）

工作流不是 AI 动态生成的，而是预定义的 YAML/Python 定义。

```yaml
name: network_troubleshoot
description: "网络故障排查流程"
steps:
  - id: diagnose_internet
    action: diagnose.internet
    risk_level: read_only
    params:
      external_ip: "8.8.8.8"
      dns_name: "www.baidu.com"
  - id: diagnose_dns
    action: diagnose.dns
    risk_level: read_only
    params:
      name: "{{ trigger.target }}"
  - id: ai_summarize
    action: ai.summarize
    risk_level: read_only
    depends_on: [diagnose_internet, diagnose_dns]
```

**设计理由**：
- 预定义工作流可审查、可版本控制。
- AI 不决定执行什么，只辅助解释结果。
- 用户可以查看工作流定义，知道 Agent 会做什么。

### 2. Action 注册表

所有可执行的操作通过 Action 注册表暴露：

```python
@action(name="diagnose.internet", risk_level=RiskLevel.read_only)
def diagnose_internet(task, store, **params):
    ...
```

**Action 分类**：
| 类别 | 示例 | 风险等级 |
|---|---|---|
| 诊断 | `diagnose.internet`, `diagnose.dns`, `diagnose.intranet` | read_only |
| 巡检 | `health.check`, `health.tcp_matrix` | read_only |
| 资产 | `asset.scan`, `asset.diff` | read_only |
| 安全 | `security.check`, `security.cert_check` | read_only |
| 拓扑 | `topology.show`, `topology.arp` | read_only |
| AI | `ai.summarize`, `ai.explain` | read_only |
| 报告 | `report.generate` | read_only |
| 自动化 | `automate.flush_dns` | low_change |

Phase 9 只注册只读和低风险动作，不注册高风险动作。

### 3. 风险分级与审批

每个 Step 有风险等级：

- `read_only`：只读操作，自动执行，无需审批。
- `low_change`：低风险变更，需要确认（`--confirm` 或 Web 审批）。
- `high_change`：高风险变更，Phase 9 不支持，必须人工执行。

**执行策略**：
1. 工作流启动时，引擎检查所有 Step 的风险等级。
2. `read_only` Step 自动执行。
3. `low_change` Step 暂停，等待审批。
4. `high_change` Step 直接拒绝，工作流终止。

### 4. 工作流执行引擎

```
┌─────────────────────────────────────┐
│         WorkflowDefinition          │  (YAML / Python)
│  name, description, steps[],        │
│  triggers[], stop_conditions[]      │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│         WorkflowEngine              │
│  1. 解析工作流定义                    │
│  2. 按依赖顺序执行 Step              │
│  3. 风险检查 → 自动 / 暂停 / 拒绝     │
│  4. 记录每步执行结果                  │
│  5. 满足停止条件时终止                │
│  6. 生成执行报告                      │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│         WorkflowExecution           │
│  id, workflow_name, status,         │
│  steps[], started_at, ended_at,     │
│  trigger, context, result_summary   │
└─────────────────────────────────────┘
```

### 5. 数据模型

```python
class WorkflowStepDef(BaseModel):
    id: str
    action: str               # 注册的 action 名
    risk_level: RiskLevel
    params: dict[str, Any]
    depends_on: list[str] = []
    condition: str | None     # 条件表达式（可选）
    stop_on_failure: bool = True

class WorkflowDefinition(BaseModel):
    name: str
    description: str
    steps: list[WorkflowStepDef]
    triggers: list[str] = []  # manual, alert, schedule

class WorkflowStepExecution(BaseModel):
    step_id: str
    action: str
    status: StepStatus        # pending, running, success, failed, skipped, awaiting_approval, approved, rejected
    risk_level: RiskLevel
    started_at: datetime | None
    ended_at: datetime | None
    result: dict[str, Any] | None
    error: str | None
    task_id: str | None       # 关联的 TaskRun ID

class WorkflowExecution(BaseModel):
    id: str
    workflow_name: str
    status: WorkflowStatus    # pending, running, paused, success, failed, cancelled
    trigger: str              # manual, cli, web, alert
    steps: list[WorkflowStepExecution]
    started_at: datetime
    ended_at: datetime | None
    context: dict[str, Any]
    result_summary: str | None
```

### 6. 停止条件

工作流可以在以下情况下停止：

- **Step 失败**：`stop_on_failure=True` 的 Step 失败时，工作流终止。
- **手动停止**：用户通过 CLI 或 Web 手动取消。
- **审批超时**：等待审批超过配置时间（默认 30 分钟）。
- **条件满足**：Step 的 `condition` 表达式求值为 False 时跳过后续依赖。

### 7. 审计记录

每次工作流执行产生完整的审计记录：

- 工作流定义版本。
- 每个 Step 的输入参数、输出结果、耗时、状态。
- 审批记录（谁审批、何时审批、批准/拒绝）。
- 触发来源（CLI / Web / 告警 / 调度）。
- 最终结果摘要。

所有审计记录持久化到 SQLite，可被 Web Console 和报告系统查询。

### 8. 内置工作流

Phase 9 预置以下工作流：

| 工作流 | 描述 | Steps |
|---|---|---|
| `network_troubleshoot` | 网络故障排查 | 互联网诊断 → DNS 诊断 → AI 总结 → 报告 |
| `full_inspection` | 全面巡检 | 健康检查 → 安全检查 → 资产扫描 → AI 周报 |
| `new_device_investigate` | 新设备调查 | 拓扑采集 → 未知设备检测 → 安全检查 → AI 解释 |

## 备选方案

### 方案 B：AI 驱动的自由 Agent

让 AI 动态决定执行什么操作。

优点：
- 灵活性高，能处理未预见的情况。
- 不需要预定义工作流。

缺点：
- 不可审计：AI 的决策过程是黑箱。
- 不可控：无法保证 AI 不执行危险操作。
- 不可复现：同样的输入可能产生不同的执行路径。
- 超出 Phase 9 范围。

### 方案 C：纯脚本编排

用 Shell/Python 脚本串联命令。

优点：
- 实现简单。
- 不需要新架构。

缺点：
- 没有风险分级和审批机制。
- 没有结构化审计记录。
- 没有暂停/恢复能力。
- 无法被 Web Console 和 API 复用。

## 后果

正面影响：
- 预定义工作流可审查、可版本控制。
- 风险分级确保只读操作自动执行，变更操作需要审批。
- 完整审计记录满足合规要求。
- 工作流可被 CLI、Web、API、调度器复用。
- AI 辅助解释结果，不控制执行。

负面影响：
- 工作流需要预定义，不能处理完全未预见的情况。
- 低风险变更需要人工审批，有等待延迟。
- 工作流引擎增加架构复杂度。

## 执行要求

- 工作流引擎实现为 `src/it_ops_toolkit/agent_workflow.py`。
- Action 注册表在同一文件中实现。
- 数据模型在 `src/it_ops_toolkit/models.py` 中定义。
- 存储扩展在 `src/it_ops_toolkit/storage.py` 中。
- CLI 新增 `ops workflow` 命令组。
- Web Console 新增工作流 API 端点。
- 内置工作流定义放在 `src/it_ops_toolkit/workflows/` 目录。
- Phase 9 只支持 `read_only` 和 `low_change` 风险等级。
- 每个工作流执行产生 `WorkflowExecution` 记录，持久化到 SQLite。
