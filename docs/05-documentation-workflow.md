# 文档协作与开发流程

## 文档目的

这份文档用于防止项目在长期开发中丢失上下文。

本项目会逐步经历 CLI、Web、AI、Agent 多个阶段。如果只依赖聊天记录或个人记忆，后期一定会出现模块边界混乱、重复实现、架构反复推翻的问题。

## 总原则

每次开发都按固定流程走：

```text
读总文档 -> 读模块地图 -> 读模块文档 -> 读落地设计 -> 写具体实现计划 -> 开发 -> 更新文档
```

## 开发一个新模块前

必须先确认：

1. 这个模块是否已经在 `docs/02-module-map.md` 中出现。
2. 是否已有对应模块文档。
3. 模块职责是否清楚。
4. 模块不负责什么是否清楚。
5. 它依赖哪些模块。
6. 哪些模块会调用它。
7. 第一阶段是否真的需要实现。

如果这些问题回答不清楚，不应直接写代码。

## 修改现有模块前

必须先阅读：

- `docs/01-architecture-overview.md`
- `docs/02-module-map.md`
- 对应的 `docs/modules/*.md`
- `docs/04-development-rules.md`

如果修改改变了模块边界，需要同步更新模块地图和对应模块文档。

## 做重要技术决策时

需要新增 ADR。

适合写 ADR 的情况：

- 选择主要编程语言。
- 选择配置格式。
- 选择本地存储方式。
- 选择 CLI 框架。
- 选择 Web 技术栈。
- 选择 AI 接入方式。
- 改变模块边界。
- 引入新的执行或权限模型。

ADR 文件放在 `docs/adr/`。

## 写具体实现计划时

实现计划应包含：

- 本次目标。
- 不做什么。
- 涉及模块。
- 数据结构。
- 命令或接口。
- 错误处理。
- 测试方法。
- 验收标准。

实现计划不应替代总架构文档。它只服务某一次开发。

## Phase 1 开发前必须阅读

进入第一阶段编码前，必须阅读：

- `docs/plans/phase-1-cli-foundation.md`
- `docs/data-model.md`
- `docs/config-schema.md`
- `docs/probe-adapter-interface.md`
- `docs/cli-command-design.md`
- `docs/deployment-model.md`
- `docs/risk-policy.md`
- `docs/adr/README.md`

这些文档把总架构落到第一阶段实现边界。

## AI 协作注意事项

以后让 AI 继续开发时，应该让 AI 先读：

- `AGENTS.md`
- `docs/00-project-vision.md`
- `docs/01-architecture-overview.md`
- `docs/02-module-map.md`
- `docs/04-development-rules.md`
- 当前模块文档

不要直接让 AI “做个扫描工具”。

更好的说法是：

```text
请先阅读 AGENTS.md 和 docs/ 下的总架构文档，然后基于 config-center 和 plugin-system 模块设计，写 Phase 1 CLI 基础实现计划。
```

## 文档维护节奏

建议节奏：

- 每完成一个模块，更新对应模块文档。
- 每做一次重要取舍，新增 ADR。
- 每发现一个新术语，更新术语表。
- 每完成一个阶段，更新路线图。
- 每次实现偏离原设计，要么修正实现，要么更新文档解释原因。
