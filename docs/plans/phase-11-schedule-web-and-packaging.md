# Phase 11：调度告警 Web 管理 + 打包分发

## 背景

Phase 10 完成后，Web Console 已具备操作中心能力，但调度管理（定时任务 CRUD、告警事件查看与确认）仍然只能通过 CLI 操作。同时，项目部署仍依赖 Python 环境，缺乏独立可执行程序。

Phase 11 的目标是：
1. 将调度管理和告警查看能力从 CLI 对等映射到 Web 端。
2. 提供 PyInstaller 打包方案，降低部署门槛。

## 设计决策

### 调度管理 Web API

- 定时任务的 CRUD 操作直接通过 `SQLiteStore` 持久化方法实现，不需要全局 `SchedulerEngine` 实例。
- `run-now` 操作按需创建 `SchedulerEngine` 实例执行单次任务。
- 添加任务时验证 cron 表达式和任务类型，检查名称重复。
- 告警事件列表和确认操作直接调用 `SQLiteStore` 方法。

### 调度管理 Web UI

- 在 Web Console 导航栏新增"调度告警"按钮。
- 页面分两部分：上方定时任务表格 + 添加表单，下方告警事件表格 + 筛选。
- 定时任务表格每行包含启用/禁用、立即执行、删除按钮。
- 告警事件表格未确认的告警显示"确认"按钮。

### PyInstaller 打包

- 使用 spec 文件配置，而非命令行参数，便于维护。
- 明确列出所有 hidden imports（PyInstaller 静态分析可能遗漏的动态导入）。
- 排除不需要的大型模块（tkinter、matplotlib、numpy 等）。
- 支持 `--cli` 模式排除 Web 依赖，生成更小的可执行文件。
- 打包为单文件（onefile）模式，便于分发。

## 新增文件

| 文件 | 说明 |
|---|---|
| `build/it_ops_toolkit.spec` | PyInstaller spec 文件 |
| `build/build_exe.py` | 打包脚本 |
| `docs/plans/phase-11-schedule-web-and-packaging.md` | 本文档 |

## 修改文件

| 文件 | 修改内容 |
|---|---|
| `src/it_ops_toolkit/web/app.py` | 新增 8 个 API 端点 |
| `src/it_ops_toolkit/web/dashboard.py` | 新增调度告警页面 HTML + JS + CSS |
| `pyproject.toml` | 新增 `[build]` 可选依赖组 |
| `.gitignore` | 调整 build/ 忽略规则 |
| `README.md` | 添加打包分发说明 |
| `docs/03-roadmap.md` | 添加 Phase 11，更新后续方向 |
| `docs/06-current-status-and-handoff.md` | 更新项目状态和代码统计 |

## API 端点

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/schedules` | GET | 列出所有定时任务 |
| `/api/schedules` | POST | 添加定时任务 |
| `/api/schedules/{task_id}` | DELETE | 删除定时任务 |
| `/api/schedules/{task_id}/enable` | POST | 启用定时任务 |
| `/api/schedules/{task_id}/disable` | POST | 禁用定时任务 |
| `/api/schedules/{task_id}/run-now` | POST | 立即执行一次 |
| `/api/alerts` | GET | 列出告警事件 |
| `/api/alerts/{event_id}/acknowledge` | POST | 确认告警事件 |

## 状态

已完成（2026-06-28）。
