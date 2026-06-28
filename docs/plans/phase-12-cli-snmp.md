# Phase 12：CLI 体验优化 + SNMP Adapter

## 背景

Phase 11 完成后，项目的核心路线图和 P1 级任务已全部完成。Phase 12 推进 P2 级任务：提升 CLI 使用体验和扩展网络设备管理能力。

## 设计决策

### CLI 体验优化

1. **交互式诊断引导**：`ops diagnose` 不指定子命令时，进入交互式菜单。用户选择场景编号后，逐步输入参数，确认后自动执行。
2. **进度条**：通过给领域服务函数添加可选的 `progress_callback` 参数实现，不改变现有 API 签名。CLI 层使用 Rich Progress 包装回调。

### SNMP Adapter

1. **纯 Python 实现**：不依赖 `pysnmp` 或系统 `snmpget` 命令。使用 `socket` + 手写 BER 编码实现 SNMP v2c。
2. **只读探针**：只实现 GET / GETNEXT / WALK，不实现 SET。
3. **`probe_type` 扩展**：在 `ProbeResult` 和 `AlertCondition` 的 `Literal` 类型中新增 `"snmp"`。

## 新增文件

| 文件 | 说明 |
|---|---|
| `src/it_ops_toolkit/probes/snmp.py` | SNMP v2c 探针实现 |
| `docs/modules/snmp.md` | SNMP 模块设计文档 |
| `docs/plans/phase-12-cli-snmp.md` | 本文档 |
| `tests/test_snmp.py` | SNMP 探针测试（31 个） |

## 修改文件

| 文件 | 修改内容 |
|---|---|
| `src/it_ops_toolkit/cli.py` | 交互式诊断引导 + Rich 进度条 + `ops probe snmp` 命令 |
| `src/it_ops_toolkit/health.py` | `run_health_check` 新增 `progress_callback` |
| `src/it_ops_toolkit/assets.py` | `run_asset_scan` 新增 `progress_callback` |
| `src/it_ops_toolkit/health_matrix.py` | `run_health_tcp_matrix` 新增 `progress_callback` |
| `src/it_ops_toolkit/health_matrix_http.py` | `run_health_http_matrix` 新增 `progress_callback` |
| `src/it_ops_toolkit/models.py` | `probe_type` Literal 新增 `"snmp"` |
| `src/it_ops_toolkit/probes/__init__.py` | 导出 SNMP 函数 |
| `src/it_ops_toolkit/web/app.py` | 新增 2 个 SNMP Web API 端点 |
| `tests/test_cli.py` | 新增交互式诊断引导测试 |
| `docs/02-module-map.md` | 更新探针数量 |
| `docs/03-roadmap.md` | 添加 Phase 12 |
| `docs/06-current-status-and-handoff.md` | 更新项目状态 |

## 状态

已完成（2026-06-28）。
