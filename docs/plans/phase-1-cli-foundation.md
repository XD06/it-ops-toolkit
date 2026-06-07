# Phase 1：CLI 基础与最小运维闭环实施计划

## 文档目的

这份文档把 Phase 1 从“路线图中的目标”拆成可执行步骤。

Phase 1 的目标不是做完整平台，而是跑通第一条真实闭环：

```text
配置 -> CLI 命令 -> Probe / Adapter -> 领域服务 -> 数据存储 -> 报告输出
```

## Phase 1 总目标

完成一个可运行的 CLI 运维工具箱最小版本，支持：

- 初始化配置。
- 读取配置。
- 执行基础资产发现。
- 执行基础网络与服务巡检。
- 保存结构化结果。
- 生成可读报告。

## Phase 1 不做什么

本阶段不做：

- Web Console。
- 多用户登录。
- 完整权限系统。
- 复杂定时调度。
- SNMP 深度拓扑。
- SSH / WinRM 批量操作。
- AI 自动总结。
- Agent 自动执行。
- 高风险自动化修复。

## 推荐技术决策顺序

开始编码前，需要先阅读这些 ADR：

1. `docs/adr/0002-phase-1-python-first.md`
2. `docs/adr/0003-phase-1-typer-cli.md`
3. `docs/adr/0004-phase-1-yaml-config.md`
4. `docs/adr/0005-phase-1-sqlite-storage.md`
5. `docs/adr/0006-phase-1-report-formats.md`

这些决策会影响后续目录结构和接口设计。

## 开发顺序

### Step 1：项目骨架

目标：

- 建立基础目录结构。
- 建立 CLI 入口。
- 建立测试入口。
- 建立配置、领域服务、Adapter、存储、报告的代码边界。

验收标准：

- 能运行一个空 CLI 命令。
- 能输出版本信息或帮助信息。
- 目录结构能体现分层架构。

### Step 2：配置中心最小版本

目标：

- 支持本地配置文件。
- 支持配置校验。
- 支持默认值。
- 支持清晰错误提示。

验收标准：

- `ops config init` 能生成示例配置。
- 工具能读取配置。
- 配置错误时能指出具体字段。

### Step 3：Probe / Adapter 接口

目标：

- 定义统一 Probe 请求结构。
- 定义统一 Probe 结果结构。
- 实现 Ping、DNS、TCP、HTTP 四个基础 Probe。

验收标准：

- 四个 Probe 的输出结构一致。
- 单个 Probe 失败不会导致程序崩溃。
- 错误信息可被报告模块展示。

### Step 4：数据模型与本地存储

目标：

- 定义 Target、Asset、ProbeResult、TaskRun、Finding、Report。
- 支持本地保存任务和结果。
- 支持按任务查询结果。

验收标准：

- 每次 CLI 执行都有 TaskRun。
- ProbeResult 能关联 TaskRun。
- Report 能关联 TaskRun。

### Step 5：资产发现最小流程

目标：

- 从配置读取网段。
- 对网段执行基础存活探测。
- 尝试获取主机名。
- 对配置端口做开放性检查。
- 保存 Asset 和 ProbeResult。

验收标准：

- `ops asset scan` 能扫描配置网段。
- 能输出在线目标。
- 能保存资产结果。
- 能生成资产报告。

### Step 6：网络与服务巡检最小流程

目标：

- 从配置读取巡检目标。
- 执行 Ping、DNS、TCP、HTTP 检查。
- 保存结构化结果。
- 生成巡检报告。

验收标准：

- `ops health check` 能执行基础巡检。
- 能区分正常、异常、超时。
- 能输出异常清单。
- 能保存结果。

### Step 7：报告输出

目标：

- 支持 CLI 简洁输出。
- 支持 Markdown 报告。
- 支持 CSV 导出。

验收标准：

- `ops report generate` 能基于任务生成报告。
- 报告包含执行时间、目标、结果、异常、证据、建议。
- 报告不直接执行检查。

### Step 8：文档回填

目标：

- 根据实现修正文档。
- 更新 ADR。
- 更新模块文档。

验收标准：

- 文档与实现不明显矛盾。
- 新增决策都有记录。

## Phase 1 推荐命令闭环

最小闭环命令：

```text
ops config init
ops asset scan
ops health check
ops task list
ops report generate
```

## Phase 1 成功标准

Phase 1 完成时，用户应该可以：

1. 初始化配置。
2. 修改网段和目标。
3. 执行资产发现。
4. 执行网络巡检。
5. 查看任务记录。
6. 生成报告。

开发者应该可以：

1. 新增一个 Probe 而不改 CLI 主逻辑。
2. 新增一种报告格式而不改探测逻辑。
3. 未来接 Web 时复用现有服务。
