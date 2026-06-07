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
