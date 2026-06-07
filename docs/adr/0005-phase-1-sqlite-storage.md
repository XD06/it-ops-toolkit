# ADR 0005：Phase 1 选择 SQLite 作为本地存储

## 状态

已接受，作为 Phase 1 本地存储方向。

## 背景

第一阶段需要保存：

- 资产。
- 任务记录。
- ProbeResult。
- Finding。
- Report 元数据。

如果只用文件散落保存，后续查询任务历史、资产变化、报告来源会变困难。

## 决策

Phase 1 使用 SQLite 作为本地结构化存储。

SQLite 官方站点：[SQLite](https://www.sqlite.org/)。

Python 标准库提供 sqlite3 模块：[sqlite3 — DB-API 2.0 interface for SQLite databases](https://docs.python.org/3/library/sqlite3.html)。

同时保留 JSON、CSV、Markdown 等导出格式。

## 备选方案

### 纯 JSON 文件

优点：

- 简单。
- 人工可查看。
- 初期实现快。

缺点：

- 查询复杂。
- 并发和历史管理弱。
- 容易产生多个文件格式。

### CSV 文件

优点：

- 适合导出资产表。
- Excel 友好。

缺点：

- 不适合保存嵌套结果。
- 不适合作为主存储。

### PostgreSQL

优点：

- 长期扩展能力强。
- 适合中心服务模式。

缺点：

- 第一阶段部署过重。
- 不适合单机 CLI 最小闭环。

## 后果

正面影响：

- 单机部署简单。
- 查询能力比 JSON/CSV 强。
- Python 标准库可直接使用。
- 后续迁移到中心数据库时模型更清楚。

负面影响：

- 需要设计表结构和迁移策略。
- 用户直接看数据库不如 CSV 直观。
- 多进程并发写入需要谨慎。

## 执行要求

- SQLite 是主存储。
- CSV/Markdown/JSON 是导出格式，不是主存储。
- 所有任务必须写 TaskRun。
- 所有探测结果必须关联 TaskRun。
- 数据库文件路径通过配置中心管理。

