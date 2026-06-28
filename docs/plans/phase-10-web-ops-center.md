# Phase 10：Web Console 操作中心

## 文档目的

记录 Phase 10 的设计决策和实现细节。Phase 10 将 Web Console 从"只读仪表盘"升级为"可执行控制台"。

## 背景

Phase 4-9 完成了 Web Console 的查看能力（概览、资产、任务、报告、配置、趋势、AI、拓扑、工作流），但运维人员仍需切换到 CLI 执行诊断、安全检查、报告生成等操作。Web Console 更多是一个"看结果的地方"，而不是"执行操作的地方"。

### 改造前的能力分布

| 能力 | Web 可执行？ | 说明 |
|---|---|---|
| 触发巡检 | ✅ | 概览页有按钮 |
| 触发资产扫描 | ✅ | 概览页有按钮 |
| 执行工作流 | ✅ | 工作流页有按钮 |
| 路由追踪 | ✅ | 拓扑页可输入目标 |
| AI 摘要/解释/周报 | ✅ | AI 页可操作 |
| 诊断（互联网/内网/DNS/RDP等） | ❌ | 只有 CLI |
| 安全检查 | ❌ | 只有 CLI |
| 报告生成 | ❌ | 只有 CLI |
| 资产变化对比 | ❌ | 只有 CLI |
| 自动化动作（flush-dns） | ❌ | 只有 CLI |
| 本机信息采集 | ❌ | 只有 CLI |

## 设计目标

1. **Web Console 可执行核心运维操作**：不再需要切换到 CLI。
2. **操作结果即时展示**：在操作卡片下方直接展示结果摘要。
3. **风险等级可视化**：每个操作卡片标注风险等级（只读/低风险变更）。
4. **架构合规**：Web 层只调用领域服务函数，不直接调用 Adapter。
5. **完整审计**：所有 Web 触发的操作创建 `TaskRun` 记录，`source="web"`。

## 实现内容

### 新增 API 端点

| 端点 | 方法 | 风险等级 | 说明 |
|---|---|---|---|
| `/api/ops/diagnose` | POST | 只读 | 触发 6 种诊断场景 |
| `/api/ops/security-check` | POST | 只读 | 基于已发现资产执行安全检查 |
| `/api/ops/cert-check` | POST | 只读 | 检查 TLS 证书过期风险 |
| `/api/ops/report-generate` | POST | 只读 | 基于指定任务生成报告 |
| `/api/ops/asset-diff` | POST | 只读 | 执行资产变化对比 |
| `/api/ops/collect-local` | POST | 只读 | 采集本机系统和网络排障上下文 |
| `/api/ops/flush-dns` | POST | 低风险变更 | 清理本机 DNS 缓存 |

### 操作中心 UI

7 个操作卡片，按功能分组：

1. **🔧 网络诊断**：选择场景（互联网/慢网络/内网/RDP/打印机/DNS），输入目标，点击执行。
2. **🔒 安全检查**：一键执行高风险端口扫描。
3. **📜 证书检查**：输入主机名和端口，检查 TLS 证书。
4. **📊 报告生成**：选择源任务和格式（Markdown/CSV/JSON），生成报告。
5. **📋 资产变化对比**：选择扫描配置，执行对比。
6. **💻 本机信息采集**：一键采集本机系统信息。
7. **🧹 清理 DNS 缓存**：区分 Dry Run 预览和确认执行两个按钮。

### 前端交互设计

- 每个操作卡片底部有结果区域，操作完成后展示任务状态、诊断摘要、建议。
- 结果区域包含"查看详情"链接，跳转到任务历史页的详情弹窗。
- 诊断结果展示 `DiagnosisSummary` 的 title、likely_area、recommendation。
- 使用 Toast 提示操作成功/失败。
- 加载中状态显示"诊断中..."/"安全检查中..."等提示。

### 架构合规性

```
Web 操作中心 UI
    ↓ fetch POST
Web API (/api/ops/*)
    ↓ 调用领域服务
领域服务 (diagnosis.py / security.py / reports.py / assets.py / automation.py / local_collect.py)
    ↓ 调用 Adapter
Probe / Adapter (ping / dns / tcp / http / tls_cert)
    ↓ 保存结果
SQLiteStore
```

关键规则：
- Web API 只调用领域服务函数，不直接调用 Adapter。
- 每个操作创建 `TaskRun` 记录，`source="web"`，`risk_level` 根据操作类型设置。
- 操作结果通过 `_task_to_dict()` 返回统一的任务字典格式。
- 变更操作（flush-dns）有 `dry_run` 和 `confirm` 双确认机制。

## 完成状态

- ✅ 8 个 POST 操作端点已实现。
- ✅ 操作中心 UI 页面已实现（7 个操作卡片）。
- ✅ 321 个测试全部通过。
- ✅ 无 linter 错误。

## 后续优化方向

- 调度管理 Web UI：在 Web Console 中管理定时任务（增删改查）。
- 操作历史页：在操作中心页面展示最近通过 Web 触发的操作记录。
- 批量操作：支持一次选择多个目标执行诊断。
- 操作模板：预设常用操作参数组合，一键执行。
