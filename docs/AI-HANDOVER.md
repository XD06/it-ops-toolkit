# AI 接手指南

> 本文档专为"下一个接手本项目的 AI 助手"编写。
> 目标：让 AI 在 10 分钟内建立完整项目认知，并能立即开始有效工作。

---

## 第一步：必须读取的文件（按顺序）

接手后第一件事：按顺序读取以下文件，建立项目全貌。

```
1. AGENTS.md                          ← 工作指南（必读，项目规则）
2. docs/06-current-status-and-handoff.md ← 当前进度与交接说明
3. docs/00-project-vision.md          ← 项目愿景
4. docs/01-architecture-overview.md   ← 架构总览
5. docs/02-module-map.md             ← 模块地图
6. docs/04-development-rules.md      ← 开发规则
```

如果处理具体模块，再读 `docs/modules/` 下对应文档。

## 第二步：理解项目定位

一句话：**中小企业 IT 运维工具平台，CLI 优先，架构预留 Web/API/AI/Agent。**

当前状态：Phase 0-12 已全部完成。

- 51 个 CLI 命令
- 50 个 Web API 端点
- 12 个 Web Console 页面
- 355 个自动化测试（全部通过）
- 纯 Python，无编译步骤

## 第三步：理解技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| CLI | Typer + Rich | `src/it_ops_toolkit/cli.py` |
| Web | FastAPI + Uvicorn | `src/it_ops_toolkit/web/` |
| 存储 | SQLite（原生 `sqlite3`） | `src/it_ops_toolkit/storage.py` |
| 配置 | YAML | `src/it_ops_toolkit/config.py` |
| 模型 | Pydantic v2 | `src/it_ops_toolkit/models.py` |
| 探针 | 纯 Python（无外部依赖） | `src/it_ops_toolkit/probes/` |
| 测试 | unittest + pytest | `tests/` |
| 打包 | PyInstaller（可选） | `build/` |

**无前端框架**：Web Console 是自包含 HTML，内联 CSS + JS，不依赖外部资源。

## 第四步：理解代码结构

```
src/it_ops_toolkit/
├── cli.py              ← CLI 入口（所有命令定义）
├── models.py           ← Pydantic 数据模型（ProbeResult, Asset, TaskRun 等）
├── config.py           ← 配置加载与校验
├── storage.py          ← SQLite 存储层
├── tasks.py            ← 任务生命周期管理
├── health.py           ← 巡检服务
├── assets.py           ← 资产发现服务
├── diagnosis.py        ← 故障诊断服务
├── security.py         ← 安全检查服务
├── reports.py          ← 报告生成服务
├── export.py           ← 诊断包导出
├── alert_engine.py     ← 告警引擎
├── scheduler.py        ← 定时调度引擎
├── notify.py           ← 通知中心
├── trend.py            ← 趋势分析
├── ai_copilot.py       ← AI 运维助手
├── topology.py         ← 网络拓扑
├── agent_workflow.py   ← 受控工作流引擎
├── automation.py       ← 自动化动作
├── local_collect.py    ← 本机信息采集
├── probes/             ← 探针实现
│   ├── ping.py
│   ├── dns.py
│   ├── tcp.py
│   ├── http.py
│   ├── tls_cert.py
│   ├── arp.py
│   ├── traceroute.py
│   └── snmp.py         ← Phase 12 新增
├── adapters/           ← 外部工具适配器
│   └── local_system.py
└── web/
    ├── app.py          ← FastAPI 应用（50 个端点）
    └── dashboard.py    ← Web Console HTML（自包含）
```

## 第五步：理解核心规则

1. **CLI 只做入口**：不把业务逻辑写在 CLI 命令里。CLI 调用领域服务函数。
2. **领域服务不含 UI**：`health.py`、`assets.py` 等不 import CLI 或 Web。
3. **探针只读**：所有 Probe 都是只读的，不做变更操作。
4. **结构化输出**：所有执行结果都是 `ProbeResult` 或 `TaskRun`，可被 CLI/Web/AI/报告复用。
5. **测试先行**：每个功能都有对应的 unittest 测试。改代码前先跑 `python -m pytest tests/ -v`。
6. **中文优先**：代码注释、文档、CLI 输出都用中文。专业术语可保留英文。
7. **文档同步**：新增模块先写 `docs/modules/` 文档；改模块边界更新 `docs/02-module-map.md`。

## 第六步：快速验证环境

```powershell
# Windows
cd c:\Users\dsk\Desktop\network
set PYTHONPATH=src
python -m pytest tests/ -v --tb=short

# 如果全部通过，说明环境正常
# 预期：355 passed
```

```powershell
# 快速体验 CLI
python -m it_ops_toolkit --version
python -m it_ops_toolkit --help
python -m it_ops_toolkit diagnose --help

# 快速体验 Web Console
python -m it_ops_toolkit web run
# 浏览器访问 http://127.0.0.1:8080
```

## 第七步：了解已完成和待实现

**已完成（Phase 0-12）**：
- CLI 运维工具箱（51 个命令）
- Web Console（12 个页面，50 个 API）
- 定时巡检与告警通知（5 种渠道）
- 历史趋势分析
- AI 运维助手（3 种后端）
- 网络拓扑与资产关系
- 受控 Agent 工作流
- 打包分发（PyInstaller）
- SNMP v2c 设备管理
- 交互式诊断引导 + 进度条

**待实现（按优先级）**：
| 方向 | 优先级 | 说明 |
|---|---|---|
| SSH Adapter | P3 | Linux 服务器远程检查 |
| WinRM/WMI Adapter | P3 | Windows 远程管理 |
| WiFi 网络评估 | P3 | 无线网络覆盖检测 |
| 配置备份与变更检测 | P3 | 网络设备配置管理 |

## 第八步：常见陷阱

1. **dashboard.py 的花括号**：Web Console HTML 使用 Python `.format()` 模板，JavaScript 中的 `{` 必须写成 `{{`，`}` 必须写成 `}}`。
2. **probe_type 是 Literal**：`models.py` 中 `ProbeResult.probe_type` 是 `Literal` 类型，新增探针类型需要同时更新 `ProbeResult` 和 `AlertCondition`。
3. **可选依赖**：`openai`、`httpx`、`uvicorn` 等是可选依赖，代码中使用延迟导入（`from xxx import yyy` 放在函数内部）。
4. **Windows 环境**：项目主要在 Windows 上开发，ping/traceroute/arp 命令需要同时支持 Windows 和 Linux 格式。
5. **测试不依赖网络**：所有测试都是本地可运行的，不依赖真实网络设备。SNMP 测试使用模拟服务器。

## 第九步：给 AI 的具体建议

1. **改代码前**：先读目标文件，理解上下文。不要只看搜索结果的片段。
2. **改代码后**：立即跑测试。如果引入了 linter 错误，立即修复。
3. **新增功能**：先写文档（`docs/modules/`），再写代码，最后写测试。
4. **不要猜测**：如果不确定某个实现细节，用工具读源码，不要猜。
5. **保持小提交**：每个功能切片完成后就可以提交，不要攒一大堆。
6. **文档是记忆**：这个项目的文档就是项目记忆。任何重要决策都要写进文档。

---

最后更新：2026-06-28
