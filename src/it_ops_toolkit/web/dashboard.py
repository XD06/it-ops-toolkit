"""HTML 仪表盘渲染。

生成一个自包含的单页 HTML，通过 fetch 调用 /api/* 端点获取数据并展示。
不依赖任何外部 CSS/JS 框架，适合离线运维环境。
"""

from __future__ import annotations

from ..storage import SQLiteStore


def render_dashboard(store: SQLiteStore, *, config_available: bool = False) -> str:
    """渲染仪表盘 HTML 页面。"""
    assets = store.list_assets()
    tasks = store.list_task_runs(limit=20)
    reports = store.list_reports(limit=20)
    findings = store.list_all_findings()

    return _HTML_TEMPLATE.format(
        assets_count=len(assets),
        tasks_count=len(tasks),
        reports_count=len(reports),
        findings_count=len(findings),
        config_available="true" if config_available else "false",
    )


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IT Ops Toolkit — Web Console</title>
<style>
:root {{
  --bg: #0f1117;
  --bg-card: #1a1d27;
  --bg-hover: #232732;
  --border: #2a2e3a;
  --text: #e0e0e8;
  --text-dim: #8888a0;
  --accent: #4a9eff;
  --accent-dim: #2a6ec0;
  --green: #3dd68c;
  --red: #f0506e;
  --orange: #ff9f43;
  --yellow: #f0d050;
  --radius: 8px;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
}}
header {{
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  padding: 16px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 100;
}}
header h1 {{ font-size: 18px; font-weight: 600; color: var(--accent); }}
header .meta {{ font-size: 13px; color: var(--text-dim); }}
nav {{
  display: flex;
  gap: 4px;
  padding: 0 24px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
}}
nav button {{
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-dim);
  padding: 10px 16px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.15s;
}}
nav button:hover {{ color: var(--text); }}
nav button.active {{ color: var(--accent); border-bottom-color: var(--accent); }}
.container {{ padding: 24px; max-width: 1400px; margin: 0 auto; }}
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}}
.stat-card {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
}}
.stat-card .label {{ font-size: 13px; color: var(--text-dim); margin-bottom: 8px; }}
.stat-card .value {{ font-size: 32px; font-weight: 700; color: var(--text); }}
.stat-card .value.green {{ color: var(--green); }}
.stat-card .value.red {{ color: var(--red); }}
.stat-card .value.accent {{ color: var(--accent); }}
.section {{ display: none; }}
.section.active {{ display: block; }}
table {{
  width: 100%;
  border-collapse: collapse;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}}
th, td {{
  padding: 10px 14px;
  text-align: left;
  font-size: 13px;
  border-bottom: 1px solid var(--border);
}}
th {{
  background: var(--bg-hover);
  color: var(--text-dim);
  font-weight: 600;
  white-space: nowrap;
}}
tr:hover {{ background: var(--bg-hover); }}
tr:last-child td {{ border-bottom: none; }}
.badge {{
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}}
.badge-success {{ background: rgba(61,214,140,0.15); color: var(--green); }}
.badge-failed {{ background: rgba(240,80,110,0.15); color: var(--red); }}
.badge-running {{ background: rgba(74,158,255,0.15); color: var(--accent); }}
.badge-info {{ background: rgba(240,208,80,0.15); color: var(--yellow); }}
.badge-warning {{ background: rgba(255,159,67,0.15); color: var(--orange); }}
.empty {{
  text-align: center;
  padding: 40px;
  color: var(--text-dim);
  font-size: 14px;
}}
.loading {{
  text-align: center;
  padding: 40px;
  color: var(--text-dim);
}}
.monospace {{
  font-family: "Cascadia Code", "Consolas", monospace;
  font-size: 12px;
}}
.detail-link {{ color: var(--accent); cursor: pointer; text-decoration: none; }}
.detail-link:hover {{ text-decoration: underline; }}
.modal-overlay {{
  display: none;
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.6);
  z-index: 200;
  justify-content: center;
  align-items: center;
}}
.modal-overlay.active {{ display: flex; }}
.modal {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  max-width: 800px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
}}
.modal h2 {{ font-size: 16px; margin-bottom: 16px; color: var(--accent); }}
.modal-close {{
  float: right;
  cursor: pointer;
  color: var(--text-dim);
  font-size: 20px;
  background: none;
  border: none;
}}
.modal-close:hover {{ color: var(--text); }}
pre {{
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 12px;
  font-size: 12px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}}
.toolbar {{
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  align-items: center;
  flex-wrap: wrap;
}}
.toolbar select, .toolbar input {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text);
  padding: 6px 10px;
  font-size: 13px;
}}
.toolbar select:focus, .toolbar input:focus {{
  outline: none;
  border-color: var(--accent);
}}
.btn {{
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 4px;
  padding: 8px 16px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}}
.btn:hover {{ background: var(--accent-dim); }}
.btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
.btn-success {{ background: var(--green); }}
.btn-success:hover {{ opacity: 0.85; }}
.trigger-bar {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  margin-bottom: 24px;
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}}
.trigger-bar select {{
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text);
  padding: 6px 10px;
  font-size: 13px;
}}
.trigger-bar select:focus {{ outline: none; border-color: var(--accent); }}
.btn-sm {{
  padding: 4px 10px;
  font-size: 12px;
  border-radius: 4px;
  cursor: pointer;
  transition: opacity 0.2s;
}}
.btn-sm:hover {{ opacity: 0.85; }}
.status-badge {{
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}}
.toast {{
  position: fixed;
  bottom: 24px;
  right: 24px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 20px;
  font-size: 14px;
  z-index: 300;
  display: none;
  max-width: 400px;
}}
.toast.success {{ border-color: var(--green); color: var(--green); }}
.toast.error {{ border-color: var(--red); color: var(--red); }}
.toast.active {{ display: block; }}
/* 趋势图表 */
.chart-container {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  margin-bottom: 16px;
}}
.chart-container h3 {{ font-size: 14px; color: var(--accent); margin-bottom: 12px; }}
.chart-svg {{ width: 100%; height: 200px; }}
.chart-svg .grid-line {{ stroke: var(--border); stroke-width: 0.5; }}
.chart-svg .axis-text {{ fill: var(--text-dim); font-size: 10px; }}
.chart-svg .data-line {{ fill: none; stroke: var(--accent); stroke-width: 2; }}
.chart-svg .data-area {{ fill: rgba(74,158,255,0.1); }}
.chart-svg .data-point {{ fill: var(--accent); r: 3; }}
.chart-svg .warn-line {{ stroke: var(--orange); stroke-width: 1; stroke-dasharray: 4 2; }}
.bar-chart {{ display: flex; gap: 12px; align-items: flex-end; height: 120px; padding: 12px 0; }}
.bar-chart .bar {{ flex: 1; min-width: 40px; text-align: center; }}
.bar-chart .bar-fill {{ border-radius: 4px 4px 0 0; transition: height 0.3s; }}
.bar-chart .bar-label {{ font-size: 11px; color: var(--text-dim); margin-top: 4px; }}
/* AI 助手 */
.ai-panel {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  margin-bottom: 16px;
}}
.ai-panel h3 {{ font-size: 14px; color: var(--accent); margin-bottom: 12px; }}
.ai-result {{
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 16px;
  margin-top: 12px;
  min-height: 40px;
}}
.ai-result .ai-facts {{ color: var(--text); margin-bottom: 8px; }}
.ai-result .ai-inferences {{ color: var(--text-dim); font-style: italic; }}
.ai-result .ai-label {{ font-size: 12px; color: var(--accent); margin-bottom: 4px; }}
.ai-meta {{ font-size: 12px; color: var(--text-dim); margin-top: 8px; }}
textarea.ai-input {{
  width: 100%;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text);
  padding: 8px 12px;
  font-size: 13px;
  font-family: inherit;
  resize: vertical;
  min-height: 60px;
}}
textarea.ai-input:focus {{ outline: none; border-color: var(--accent); }}
/* 拓扑 */
.topo-section {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  margin-bottom: 16px;
}}
.topo-section h3 {{ font-size: 14px; color: var(--accent); margin-bottom: 12px; }}
.topo-graph {{
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 16px;
  font-family: "Cascadia Code", "Consolas", monospace;
  font-size: 12px;
  white-space: pre;
  overflow-x: auto;
  margin-top: 12px;
}}
/* 工作流 */
.wf-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}}
.wf-card {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
}}
.wf-card h3 {{ font-size: 15px; color: var(--accent); margin-bottom: 8px; }}
.wf-card .wf-desc {{ font-size: 13px; color: var(--text-dim); margin-bottom: 12px; }}
.wf-card .wf-steps {{ font-size: 12px; color: var(--text); margin-bottom: 12px; }}
.wf-step-item {{
  display: inline-block;
  padding: 2px 8px;
  margin: 2px;
  border-radius: 4px;
  font-size: 11px;
  background: var(--bg-hover);
}}
.wf-step-item.read_only {{ border-left: 3px solid var(--green); }}
.wf-step-item.low_change {{ border-left: 3px solid var(--orange); }}
.wf-step-item.high_change {{ border-left: 3px solid var(--red); }}
.wf-step-row {{
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}}
.wf-step-row:last-child {{ border-bottom: none; }}
.wf-step-status {{
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}}
.wf-step-status.success {{ background: var(--green); }}
.wf-step-status.failed {{ background: var(--red); }}
.wf-step-status.skipped {{ background: var(--text-dim); }}
.wf-step-status.pending {{ background: var(--yellow); }}
.wf-step-status.running {{ background: var(--accent); }}
.quick-link {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  gap: 12px;
}}
.quick-link:hover {{ border-color: var(--accent); background: var(--bg-hover); }}
.quick-link .ql-icon {{ font-size: 24px; }}
.quick-link .ql-text {{ font-size: 14px; color: var(--text); }}
.quick-link .ql-desc {{ font-size: 12px; color: var(--text-dim); }}
/* 操作中心 */
.ops-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}}
.ops-card {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
}}
.ops-card h3 {{ font-size: 15px; color: var(--accent); margin-bottom: 8px; }}
.ops-card .ops-desc {{ font-size: 13px; color: var(--text-dim); margin-bottom: 16px; }}
.ops-card .ops-form {{ display: flex; flex-direction: column; gap: 10px; }}
.ops-card label {{ font-size: 12px; color: var(--text-dim); }}
.ops-card select, .ops-card input {{
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text);
  padding: 8px 10px;
  font-size: 13px;
}}
.ops-card select:focus, .ops-card input:focus {{ outline: none; border-color: var(--accent); }}
.ops-card .btn {{ align-self: flex-start; margin-top: 4px; }}
.ops-result {{
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 12px;
  margin-top: 12px;
  font-size: 13px;
  display: none;
}}
.ops-result.active {{ display: block; }}
.ops-result .ops-summary-title {{ font-size: 14px; color: var(--accent); margin-bottom: 6px; }}
.ops-result .ops-summary-area {{ color: var(--orange); margin-bottom: 4px; }}
.ops-result .ops-summary-rec {{ color: var(--text-dim); }}
.ops-risk-tag {{
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  margin-bottom: 8px;
}}
.ops-risk-tag.read_only {{ background: rgba(61,214,140,0.15); color: var(--green); }}
.ops-risk-tag.low_change {{ background: rgba(255,159,67,0.15); color: var(--orange); }}
</style>
</head>
<body>

<header>
  <h1>IT Ops Toolkit</h1>
  <span class="meta">Web Console</span>
</header>

<nav>
  <button class="active" onclick="showSection('overview', event)">概览</button>
  <button onclick="showSection('assets', event)">资产列表</button>
  <button onclick="showSection('tasks', event)">任务历史</button>
  <button onclick="showSection('reports', event)">报告</button>
  <button onclick="showSection('config', event)">配置</button>
  <button onclick="showSection('trends', event)">趋势</button>
  <button onclick="showSection('ai', event)">AI助手</button>
  <button onclick="showSection('topology', event)">网络拓扑</button>
  <button onclick="showSection('workflows', event)">工作流</button>
  <button onclick="showSection('ops', event)">操作中心</button>
  <button onclick="showSection('schedule', event)">调度告警</button>
<button onclick="showSection('snmp', event)">SNMP设备</button>
</nav>

<div class="container">
  <!-- 概览 -->
  <div id="section-overview" class="section active">
    <div class="trigger-bar" id="trigger-bar" style="display:none;">
      <span style="font-size:14px;font-weight:600;color:var(--text-dim);">手动触发：</span>
      <select id="trigger-health-profile">
        <option value="">选择巡检配置...</option>
      </select>
      <button class="btn btn-success" onclick="triggerHealthCheck()">执行巡检</button>
      <select id="trigger-scan-profile">
        <option value="">选择扫描配置...</option>
      </select>
      <button class="btn" onclick="triggerAssetScan()">执行扫描</button>
    </div>
    <div class="stats-grid">
      <div class="stat-card">
        <div class="label">资产总数</div>
        <div class="value accent" id="stat-assets">—</div>
      </div>
      <div class="stat-card">
        <div class="label">任务总数</div>
        <div class="value" id="stat-tasks">—</div>
      </div>
      <div class="stat-card">
        <div class="label">报告总数</div>
        <div class="value green" id="stat-reports">—</div>
      </div>
      <div class="stat-card">
        <div class="label">发现项总数</div>
        <div class="value red" id="stat-findings">—</div>
      </div>
    </div>
    <div class="stats-grid" id="severity-grid"></div>
    <div class="stats-grid" id="task-type-grid"></div>
    <div class="stats-grid">
      <div class="quick-link" onclick="showSectionByName('trends')">
        <span class="ql-icon">📊</span>
        <div><div class="ql-text">趋势分析</div><div class="ql-desc">查看历史趋势和状态分布</div></div>
      </div>
      <div class="quick-link" onclick="showSectionByName('ai')">
        <span class="ql-icon">🤖</span>
        <div><div class="ql-text">AI 运维助手</div><div class="ql-desc">任务摘要、异常解释、周报</div></div>
      </div>
      <div class="quick-link" onclick="showSectionByName('topology')">
        <span class="ql-icon">🔗</span>
        <div><div class="ql-text">网络拓扑</div><div class="ql-desc">ARP 表、路由追踪、未知设备</div></div>
      </div>
      <div class="quick-link" onclick="showSectionByName('workflows')">
        <span class="ql-icon">⚡</span>
        <div><div class="ql-text">工作流</div><div class="ql-desc">受控 Agent 自动化流程</div></div>
      </div>
      <div class="quick-link" onclick="showSectionByName('snmp')">
        <span class="ql-icon">📡</span>
        <div><div class="ql-text">SNMP 设备</div><div class="ql-desc">采集网络设备信息和接口状态</div></div>
      </div>
    </div>
  </div>

  <!-- 资产列表 -->
  <div id="section-assets" class="section">
    <table id="assets-table">
      <thead>
        <tr>
          <th>IP</th>
          <th>主机名</th>
          <th>MAC</th>
          <th>厂商</th>
          <th>OS 猜测</th>
          <th>开放端口</th>
          <th>状态</th>
          <th>最后发现</th>
        </tr>
      </thead>
      <tbody id="assets-body">
        <tr><td colspan="8" class="loading">加载中...</td></tr>
      </tbody>
    </table>
  </div>

  <!-- 任务历史 -->
  <div id="section-tasks" class="section">
    <div class="toolbar">
      <select id="filter-task-type" onchange="loadTasks()">
        <option value="">全部类型</option>
        <option value="asset_scan">资产扫描</option>
        <option value="health_check">巡检</option>
        <option value="diagnosis">诊断</option>
        <option value="security_check">安全检查</option>
        <option value="report_generate">报告生成</option>
        <option value="ops_collect">本机采集</option>
        <option value="automation">自动化动作</option>
        <option value="health_matrix">健康矩阵</option>
        <option value="workflow_execution">工作流执行</option>
      </select>
      <select id="filter-task-status" onchange="loadTasks()">
        <option value="">全部状态</option>
        <option value="success">成功</option>
        <option value="failed">失败</option>
        <option value="running">运行中</option>
        <option value="pending">等待中</option>
        <option value="cancelled">已取消</option>
      </select>
    </div>
    <table id="tasks-table">
      <thead>
        <tr>
          <th>任务 ID</th>
          <th>类型</th>
          <th>状态</th>
          <th>风险等级</th>
          <th>请求人</th>
          <th>来源</th>
          <th>开始时间</th>
          <th>结束时间</th>
        </tr>
      </thead>
      <tbody id="tasks-body">
        <tr><td colspan="8" class="loading">加载中...</td></tr>
      </tbody>
    </table>
  </div>

  <!-- 报告 -->
  <div id="section-reports" class="section">
    <table id="reports-table">
      <thead>
        <tr>
          <th>报告 ID</th>
          <th>标题</th>
          <th>类型</th>
          <th>格式</th>
          <th>关联任务</th>
          <th>生成时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody id="reports-body">
        <tr><td colspan="7" class="loading">加载中...</td></tr>
      </tbody>
    </table>
  </div>

  <!-- 配置 -->
  <div id="section-config" class="section">
    <div id="config-content">
      <p class="loading">加载中...</p>
    </div>
  </div>

  <!-- 趋势 -->
  <div id="section-trends" class="section">
    <div class="toolbar">
      <select id="trend-probe-type" onchange="loadTrendTargets()">
        <option value="ping">Ping</option>
        <option value="dns">DNS</option>
        <option value="tcp">TCP</option>
        <option value="http">HTTP</option>
        <option value="tls_cert">TLS证书</option>
      </select>
      <select id="trend-target"><option value="">全部目标</option></select>
      <select id="trend-metric"><option value="">全部指标</option></select>
      <select id="trend-days" onchange="loadTrendData()">
        <option value="7">最近7天</option>
        <option value="14">最近14天</option>
        <option value="30">最近30天</option>
        <option value="90">最近90天</option>
      </select>
      <select id="trend-granularity" onchange="loadTrendData()">
        <option value="daily">按天</option>
        <option value="hourly">按小时</option>
      </select>
      <button class="btn" onclick="loadTrendData()">查询</button>
    </div>
    <div id="trend-content"><p class="loading">选择探针类型后点击查询...</p></div>
  </div>

  <!-- AI 助手 -->
  <div id="section-ai" class="section">
    <div class="ai-panel">
      <h3>📝 任务摘要</h3>
      <div class="toolbar">
        <input type="text" id="ai-summarize-task" placeholder="输入任务 ID..." style="flex:1;min-width:200px;">
        <button class="btn" onclick="aiSummarize()">生成摘要</button>
      </div>
      <div class="ai-result" id="ai-summarize-result"><p class="loading" style="color:var(--text-dim);">输入任务 ID 后点击生成...</p></div>
    </div>
    <div class="ai-panel">
      <h3>🔍 异常解释</h3>
      <div class="toolbar">
        <input type="text" id="ai-explain-task" placeholder="输入任务 ID..." style="flex:1;min-width:200px;">
      </div>
      <textarea class="ai-input" id="ai-explain-question" placeholder="输入你的问题，例如：为什么这个任务失败了？" style="margin-top:8px;"></textarea>
      <button class="btn" onclick="aiExplain()" style="margin-top:8px;">解释异常</button>
      <div class="ai-result" id="ai-explain-result"><p class="loading" style="color:var(--text-dim);">输入任务 ID 和问题后点击解释...</p></div>
    </div>
    <div class="ai-panel">
      <h3>📅 AI 周报</h3>
      <div class="toolbar">
        <select id="ai-weekly-days">
          <option value="7">最近7天</option>
          <option value="14">最近14天</option>
          <option value="30">最近30天</option>
        </select>
        <button class="btn" onclick="aiWeekly()">生成周报</button>
      </div>
      <div class="ai-result" id="ai-weekly-result"><p class="loading" style="color:var(--text-dim);">点击生成 AI 周报摘要...</p></div>
    </div>
    <div class="ai-panel">
      <h3>📋 AI 调用日志</h3>
      <table id="ai-logs-table">
        <thead><tr><th>时间</th><th>场景</th><th>任务ID</th><th>后端</th><th>状态</th><th>耗时(ms)</th></tr></thead>
        <tbody id="ai-logs-body"><tr><td colspan="6" class="loading">点击加载...</td></tr></tbody>
      </table>
      <button class="btn" onclick="loadAILogs()" style="margin-top:8px;">加载日志</button>
    </div>
  </div>

  <!-- 网络拓扑 -->
  <div id="section-topology" class="section">
    <div class="toolbar">
      <button class="btn" onclick="loadTopology()">刷新拓扑视图</button>
      <button class="btn btn-success" onclick="loadUnknownDevices()">检测未知设备</button>
    </div>
    <div id="topo-overview"><p class="loading">点击刷新加载拓扑数据...</p></div>
    <div class="topo-section">
      <h3>ARP 表</h3>
      <button class="btn" onclick="loadArpTable()" style="margin-bottom:12px;">加载 ARP 表</button>
      <table id="topo-arp-table">
        <thead><tr><th>IP</th><th>MAC</th><th>接口</th><th>状态</th><th>厂商</th><th>设备类型</th></tr></thead>
        <tbody id="topo-arp-body"><tr><td colspan="6" class="loading">点击加载...</td></tr></tbody>
      </table>
    </div>
    <div class="topo-section">
      <h3>路由追踪 (Traceroute)</h3>
      <div class="toolbar">
        <input type="text" id="topo-traceroute-target" placeholder="输入目标 IP 或域名..." style="flex:1;min-width:200px;">
        <button class="btn" onclick="runTraceroute()">追踪</button>
      </div>
      <div id="topo-traceroute-result"></div>
    </div>
  </div>

  <!-- 工作流 -->
  <div id="section-workflows" class="section">
    <h3 style="font-size:15px;color:var(--accent);margin-bottom:16px;">可用工作流</h3>
    <div class="wf-grid" id="wf-list"><p class="loading">加载中...</p></div>
    <h3 style="font-size:15px;color:var(--accent);margin-bottom:16px;">执行历史</h3>
    <table id="wf-history-table">
      <thead><tr><th>执行ID</th><th>工作流</th><th>状态</th><th>触发者</th><th>步骤数</th><th>开始时间</th><th>结束时间</th><th>操作</th></tr></thead>
      <tbody id="wf-history-body"><tr><td colspan="8" class="loading">加载中...</td></tr></tbody>
    </table>
  </div>

  <!-- 操作中心 -->
  <div id="section-ops" class="section">
    <div class="ops-grid">
      <!-- 诊断 -->
      <div class="ops-card">
        <h3>🔧 网络诊断</h3>
        <p class="ops-desc">选择诊断场景，快速定位网络问题</p>
        <span class="ops-risk-tag read_only">只读</span>
        <div class="ops-form">
          <label>诊断场景</label>
          <select id="ops-diagnose-scenario">
            <option value="internet">互联网连通性诊断</option>
            <option value="slow_network">慢网络诊断</option>
            <option value="intranet">内网服务诊断</option>
            <option value="rdp">远程桌面诊断</option>
            <option value="printer">打印机诊断</option>
            <option value="dns">DNS 解析诊断</option>
          </select>
          <label>目标（内网URL/RDP地址/打印机IP/DNS域名）</label>
          <input type="text" id="ops-diagnose-target" placeholder="如 192.168.1.10:3389 或 example.com">
          <button class="btn" onclick="opsDiagnose()">开始诊断</button>
        </div>
        <div class="ops-result" id="ops-diagnose-result"></div>
      </div>

      <!-- 安全检查 -->
      <div class="ops-card">
        <h3>🔒 安全检查</h3>
        <p class="ops-desc">基于已发现资产扫描高风险端口</p>
        <span class="ops-risk-tag read_only">只读</span>
        <div class="ops-form">
          <button class="btn" onclick="opsSecurityCheck()">执行安全检查</button>
        </div>
        <div class="ops-result" id="ops-security-result"></div>
      </div>

      <!-- 证书检查 -->
      <div class="ops-card">
        <h3>📜 证书检查</h3>
        <p class="ops-desc">检查 TLS/SSL 证书过期风险</p>
        <span class="ops-risk-tag read_only">只读</span>
        <div class="ops-form">
          <label>主机名</label>
          <input type="text" id="ops-cert-hostname" placeholder="如 example.com" value="example.com">
          <label>端口</label>
          <input type="number" id="ops-cert-port" value="443" min="1" max="65535">
          <button class="btn" onclick="opsCertCheck()">检查证书</button>
        </div>
        <div class="ops-result" id="ops-cert-result"></div>
      </div>

      <!-- 报告生成 -->
      <div class="ops-card">
        <h3>📊 报告生成</h3>
        <p class="ops-desc">基于已有任务生成 Markdown/CSV/JSON 报告</p>
        <span class="ops-risk-tag read_only">只读</span>
        <div class="ops-form">
          <label>源任务 ID</label>
          <input type="text" id="ops-report-task-id" placeholder="如 task-xxxx">
          <label>报告格式</label>
          <select id="ops-report-format">
            <option value="markdown">Markdown</option>
            <option value="csv">CSV</option>
            <option value="json">JSON</option>
          </select>
          <button class="btn" onclick="opsReportGenerate()">生成报告</button>
        </div>
        <div class="ops-result" id="ops-report-result"></div>
      </div>

      <!-- 资产对比 -->
      <div class="ops-card">
        <h3>📋 资产变化对比</h3>
        <p class="ops-desc">重新扫描并与上次资产对比</p>
        <span class="ops-risk-tag read_only">只读</span>
        <div class="ops-form">
          <label>扫描配置</label>
          <select id="ops-diff-profile">
            <option value="">选择扫描配置...</option>
          </select>
          <button class="btn" onclick="opsAssetDiff()">执行对比</button>
        </div>
        <div class="ops-result" id="ops-diff-result"></div>
      </div>

      <!-- 本机采集 -->
      <div class="ops-card">
        <h3>💻 本机信息采集</h3>
        <p class="ops-desc">采集本机系统和网络排障上下文</p>
        <span class="ops-risk-tag read_only">只读</span>
        <div class="ops-form">
          <button class="btn" onclick="opsCollectLocal()">立即采集</button>
        </div>
        <div class="ops-result" id="ops-collect-result"></div>
      </div>

      <!-- 清理 DNS 缓存 -->
      <div class="ops-card">
        <h3>🧹 清理 DNS 缓存</h3>
        <p class="ops-desc">清理本机 DNS 缓存，解决解析异常</p>
        <span class="ops-risk-tag low_change">低风险变更</span>
        <div class="ops-form">
          <button class="btn" onclick="opsFlushDns(false)">预览（Dry Run）</button>
          <button class="btn btn-success" onclick="opsFlushDns(true)" style="background:var(--orange);">确认执行</button>
        </div>
        <div class="ops-result" id="ops-flushdns-result"></div>
      </div>
    </div>
  </div>

  <!-- 调度告警 -->
  <div id="section-schedule" class="section">
    <h3 style="font-size:15px;color:var(--accent);margin-bottom:16px;">定时任务</h3>
    <div class="trigger-bar">
      <span style="font-size:14px;font-weight:600;color:var(--text-dim);">添加任务：</span>
      <input type="text" id="sched-add-name" placeholder="任务名称" style="background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);padding:6px 10px;font-size:13px;width:140px;">
      <select id="sched-add-type" style="background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);padding:6px 10px;font-size:13px;">
        <option value="health_check">巡检</option>
        <option value="security_check">安全检查</option>
        <option value="asset_scan">资产扫描</option>
      </select>
      <input type="text" id="sched-add-profile" placeholder="配置名" value="default" style="background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);padding:6px 10px;font-size:13px;width:100px;">
      <input type="text" id="sched-add-cron" placeholder="cron 表达式" style="background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);padding:6px 10px;font-size:13px;width:160px;">
      <button class="btn btn-success" onclick="addSchedule()">添加</button>
    </div>
    <table id="schedule-table">
      <thead><tr><th>名称</th><th>类型</th><th>配置</th><th>Cron</th><th>状态</th><th>上次执行</th><th>下次执行</th><th>操作</th></tr></thead>
      <tbody id="schedule-body"><tr><td colspan="8" class="loading">加载中...</td></tr></tbody>
    </table>

    <h3 style="font-size:15px;color:var(--accent);margin-bottom:16px;margin-top:24px;">告警事件</h3>
    <div class="toolbar">
      <select id="alert-filter-status" onchange="loadAlerts()">
        <option value="">全部状态</option>
        <option value="active">活跃</option>
        <option value="resolved">已恢复</option>
        <option value="suppressed">已抑制</option>
      </select>
      <button class="btn" onclick="loadAlerts()">刷新</button>
    </div>
    <table id="alert-table">
      <thead><tr><th>规则</th><th>严重程度</th><th>目标</th><th>探针</th><th>指标</th><th>值</th><th>阈值</th><th>状态</th><th>触发时间</th><th>已确认</th><th>操作</th></tr></thead>
      <tbody id="alert-body"><tr><td colspan="11" class="loading">加载中...</td></tr></tbody>
    </table>
  </div>

  <!-- SNMP 设备管理 -->
  <div id="section-snmp" class="section">
    <h3 style="font-size:15px;color:var(--accent);margin-bottom:16px;">SNMP 设备信息采集</h3>
    <div class="trigger-bar">
      <span style="font-size:14px;font-weight:600;color:var(--text-dim);">目标设备：</span>
      <input type="text" id="snmp-target" placeholder="IP 地址" style="background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);padding:6px 10px;font-size:13px;width:160px;">
      <input type="text" id="snmp-community" placeholder="community" value="public" style="background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);padding:6px 10px;font-size:13px;width:100px;">
      <input type="number" id="snmp-port" placeholder="端口" value="161" style="background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);padding:6px 10px;font-size:13px;width:80px;">
      <button class="btn btn-success" onclick="snmpCollect()">采集设备信息</button>
    </div>
    <div id="snmp-result" style="margin-top:16px;"></div>

    <h3 style="font-size:15px;color:var(--accent);margin-bottom:16px;margin-top:24px;">SNMP OID 查询</h3>
    <div class="trigger-bar">
      <span style="font-size:14px;font-weight:600;color:var(--text-dim);">OID：</span>
      <input type="text" id="snmp-oid" placeholder="1.3.6.1.2.1.1.1.0" style="background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);padding:6px 10px;font-size:13px;width:280px;">
      <button class="btn" onclick="snmpGetOid()">查询</button>
    </div>
    <div id="snmp-oid-result" style="margin-top:12px;"></div>
  </div>
</div>
<div class="modal-overlay" id="modal-overlay" onclick="closeModal(event)">
  <div class="modal" onclick="event.stopPropagation()">
    <button class="modal-close" onclick="closeModal()">&times;</button>
    <h2 id="modal-title">详情</h2>
    <div id="modal-body"></div>
  </div>
</div>

<!-- 提示框 -->
<div class="toast" id="toast"></div>

<script>
const CONFIG_AVAILABLE = {config_available};

const TASK_TYPE_LABELS = {{
  asset_scan: "资产扫描",
  asset_diff: "资产变化对比",
  asset_import_notes: "资产备注导入",
  health_check: "巡检",
  health_matrix: "健康矩阵",
  diagnosis: "诊断",
  security_check: "安全检查",
  report_generate: "报告生成",
  ops_collect: "本机采集",
  automation: "自动化动作",
  workflow_execution: "工作流执行",
  snmp_probe: "SNMP 探测",
}};

const SEVERITY_LABELS = {{
  info: "信息",
  low: "低",
  medium: "中",
  high: "高",
  critical: "严重",
}};

function showSection(name, event) {{
  document.querySelectorAll(".section").forEach(s => s.classList.remove("active"));
  document.querySelectorAll("nav button").forEach(b => b.classList.remove("active"));
  document.getElementById("section-" + name).classList.add("active");
  if (event) event.target.classList.add("active");
  if (name === "overview") loadOverview();
  if (name === "assets") loadAssets();
  if (name === "tasks") loadTasks();
  if (name === "reports") loadReports();
  if (name === "config") loadConfig();
  if (name === "trends") loadTrendTargets();
  if (name === "ai") loadAILogs();
  if (name === "topology") loadTopology();
  if (name === "workflows") loadWorkflows();
  if (name === "ops") loadOpsCenter();
  if (name === "schedule") loadSchedules();
  if (name === "snmp") loadSnmpDefault();
}}

function showSectionByName(name) {{
  document.querySelectorAll(".section").forEach(s => s.classList.remove("active"));
  document.querySelectorAll("nav button").forEach(b => b.classList.remove("active"));
  document.getElementById("section-" + name).classList.add("active");
  const navBtns = document.querySelectorAll("nav button");
  for (const btn of navBtns) {{
    if (btn.textContent.includes(name === "trends" ? "趋势" : name === "ai" ? "AI" : name === "topology" ? "拓扑" : name === "workflows" ? "工作流" : name === "ops" ? "操作中心" : name === "snmp" ? "SNMP" : name === "schedule" ? "调度" : "")) {{
      btn.classList.add("active");
      break;
    }}
  }}
  if (name === "trends") loadTrendTargets();
  if (name === "ai") loadAILogs();
  if (name === "topology") loadTopology();
  if (name === "workflows") loadWorkflows();
  if (name === "snmp") loadSnmpDefault();
}}

async function fetchJSON(url, options) {{
  const resp = await fetch(url, options);
  if (!resp.ok) {{
    const data = await resp.json().catch(() => ({{}}));
    throw new Error(data.detail || `HTTP ${{resp.status}}`);
  }}
  return resp.json();
}}

function showToast(msg, type) {{
  const toast = document.getElementById("toast");
  toast.textContent = msg;
  toast.className = "toast " + (type || "") + " active";
  setTimeout(() => toast.classList.remove("active"), 4000);
}}

async function loadOverview() {{
  try {{
    const data = await fetchJSON("/api/overview");
    document.getElementById("stat-assets").textContent = data.assets_count;
    document.getElementById("stat-tasks").textContent = data.tasks_count;
    document.getElementById("stat-reports").textContent = data.reports_count;
    document.getElementById("stat-findings").textContent = data.findings_count;

    if (data.config_available) {{
      document.getElementById("trigger-bar").style.display = "flex";
      await loadTriggerProfiles();
    }}

    const sevGrid = document.getElementById("severity-grid");
    if (data.severity_counts && Object.keys(data.severity_counts).length > 0) {{
      sevGrid.innerHTML = Object.entries(data.severity_counts).map(([sev, count]) => {{
        const label = SEVERITY_LABELS[sev] || sev;
        const cls = sev === "critical" || sev === "high" ? "red" :
                     sev === "medium" ? "orange" : "green";
        return `<div class="stat-card"><div class="label">${{label}}</div><div class="value ${{cls}}">${{count}}</div></div>`;
      }}).join("");
    }} else {{
      sevGrid.innerHTML = "";
    }}

    const typeGrid = document.getElementById("task-type-grid");
    if (data.task_type_counts && Object.keys(data.task_type_counts).length > 0) {{
      typeGrid.innerHTML = Object.entries(data.task_type_counts).map(([type, count]) => {{
        const label = TASK_TYPE_LABELS[type] || type;
        return `<div class="stat-card"><div class="label">${{label}}</div><div class="value">${{count}}</div></div>`;
      }}).join("");
    }} else {{
      typeGrid.innerHTML = "";
    }}
  }} catch (e) {{
    console.error("load overview failed:", e);
  }}
}}

async function loadTriggerProfiles() {{
  try {{
    const [healthProfiles, scanProfiles] = await Promise.all([
      fetchJSON("/api/config/health-profiles"),
      fetchJSON("/api/config/scan-profiles"),
    ]);
    const healthSelect = document.getElementById("trigger-health-profile");
    healthSelect.innerHTML = '<option value="">选择巡检配置...</option>' +
      healthProfiles.map(p => `<option value="${{p.name}}">${{p.name}} (${{p.targets.length}}个目标)</option>`).join("");
    const scanSelect = document.getElementById("trigger-scan-profile");
    scanSelect.innerHTML = '<option value="">选择扫描配置...</option>' +
      scanProfiles.map(p => `<option value="${{p.name}}">${{p.name}} (${{p.subnets.length}}个网段)</option>`).join("");
  }} catch (e) {{
    console.error("load trigger profiles failed:", e);
  }}
}}

async function triggerHealthCheck() {{
  const profile = document.getElementById("trigger-health-profile").value;
  if (!profile) {{ showToast("请先选择巡检配置", "error"); return; }}
  try {{
    showToast("巡检任务已触发，请稍候...", "success");
    const task = await fetchJSON("/api/tasks/trigger/health-check", {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify({{profile_name: profile}}),
    }});
    showToast(`巡检完成: ${{task.status}} (${{task.id}})`, task.status === "success" ? "success" : "error");
    loadOverview();
  }} catch (e) {{
    showToast("巡检触发失败: " + e.message, "error");
  }}
}}

async function triggerAssetScan() {{
  const profile = document.getElementById("trigger-scan-profile").value;
  if (!profile) {{ showToast("请先选择扫描配置", "error"); return; }}
  try {{
    showToast("资产扫描已触发，请稍候...", "success");
    const task = await fetchJSON("/api/tasks/trigger/asset-scan", {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify({{profile_name: profile}}),
    }});
    showToast(`扫描完成: ${{task.status}} (${{task.id}})`, task.status === "success" ? "success" : "error");
    loadOverview();
  }} catch (e) {{
    showToast("扫描触发失败: " + e.message, "error");
  }}
}}

async function loadAssets() {{
  const tbody = document.getElementById("assets-body");
  try {{
    const assets = await fetchJSON("/api/assets");
    if (assets.length === 0) {{
      tbody.innerHTML = '<tr><td colspan="8" class="empty">暂无资产数据。运行 `ops asset scan` 发现资产。</td></tr>';
      return;
    }}
    tbody.innerHTML = assets.map(a => {{
      const ports = a.open_ports.length > 0 ? a.open_ports.join(", ") : "—";
      const statusBadge = a.status === "active"
        ? '<span class="badge badge-success">活跃</span>'
        : a.status === "missing"
        ? '<span class="badge badge-failed">消失</span>'
        : '<span class="badge badge-info">未知</span>';
      const lastSeen = a.last_seen ? new Date(a.last_seen).toLocaleString("zh-CN") : "—";
      return `<tr>
        <td><span class="detail-link" onclick="showAssetDetail('${{a.ip}}')">${{a.ip}}</span></td>
        <td>${{a.hostname || "—"}}</td>
        <td class="monospace">${{a.mac || "—"}}</td>
        <td>${{a.vendor || "—"}}</td>
        <td>${{a.os_hint || "—"}}</td>
        <td class="monospace">${{ports}}</td>
        <td>${{statusBadge}}</td>
        <td>${{lastSeen}}</td>
      </tr>`;
    }}).join("");
  }} catch (e) {{
    tbody.innerHTML = `<tr><td colspan="8" class="empty">加载失败: ${{e.message}}</td></tr>`;
  }}
}}

async function loadTasks() {{
  const tbody = document.getElementById("tasks-body");
  try {{
    const typeFilter = document.getElementById("filter-task-type").value;
    const statusFilter = document.getElementById("filter-task-status").value;
    let url = "/api/tasks?limit=50";
    if (typeFilter) url += `&task_type=${{encodeURIComponent(typeFilter)}}`;
    if (statusFilter) url += `&status=${{encodeURIComponent(statusFilter)}}`;
    const tasks = await fetchJSON(url);
    if (tasks.length === 0) {{
      tbody.innerHTML = '<tr><td colspan="8" class="empty">暂无任务记录。运行 `ops asset scan` 或 `ops health check` 产生数据。</td></tr>';
      return;
    }}
    tbody.innerHTML = tasks.map(t => {{
      const typeLabel = TASK_TYPE_LABELS[t.task_type] || t.task_type;
      const statusBadge = t.status === "success"
        ? '<span class="badge badge-success">成功</span>'
        : t.status === "failed"
        ? '<span class="badge badge-failed">失败</span>'
        : t.status === "running"
        ? '<span class="badge badge-running">运行中</span>'
        : `<span class="badge badge-info">${{t.status}}</span>`;
      const riskBadge = t.risk_level === "read_only"
        ? '<span class="badge badge-success">只读</span>'
        : t.risk_level === "low_change"
        ? '<span class="badge badge-warning">低风险变更</span>'
        : '<span class="badge badge-failed">高风险变更</span>';
      const started = t.started_at ? new Date(t.started_at).toLocaleString("zh-CN") : "—";
      const ended = t.ended_at ? new Date(t.ended_at).toLocaleString("zh-CN") : "—";
      return `<tr>
        <td><span class="detail-link monospace" onclick="showTaskDetail('${{t.id}}')">${{t.id}}</span></td>
        <td>${{typeLabel}}</td>
        <td>${{statusBadge}}</td>
        <td>${{riskBadge}}</td>
        <td>${{t.requested_by}}</td>
        <td>${{t.source}}</td>
        <td>${{started}}</td>
        <td>${{ended}}</td>
      </tr>`;
    }}).join("");
  }} catch (e) {{
    tbody.innerHTML = `<tr><td colspan="8" class="empty">加载失败: ${{e.message}}</td></tr>`;
  }}
}}

async function loadReports() {{
  const tbody = document.getElementById("reports-body");
  try {{
    const reports = await fetchJSON("/api/reports?limit=50");
    if (reports.length === 0) {{
      tbody.innerHTML = '<tr><td colspan="7" class="empty">暂无报告。运行 `ops report generate` 生成报告。</td></tr>';
      return;
    }}
    tbody.innerHTML = reports.map(r => {{
      const generated = r.generated_at ? new Date(r.generated_at).toLocaleString("zh-CN") : "—";
      return `<tr>
        <td class="monospace">${{r.id}}</td>
        <td>${{r.title}}</td>
        <td>${{r.report_type}}</td>
        <td>${{r.format}}</td>
        <td class="monospace">${{r.source_task_id}}</td>
        <td>${{generated}}</td>
        <td><span class="detail-link" onclick="showReportContent('${{r.id}}')">查看内容</span></td>
      </tr>`;
    }}).join("");
  }} catch (e) {{
    tbody.innerHTML = `<tr><td colspan="7" class="empty">加载失败: ${{e.message}}</td></tr>`;
  }}
}}

async function loadConfig() {{
  const container = document.getElementById("config-content");
  try {{
    const config = await fetchJSON("/api/config");
    let html = `<table>
      <tr><th>字段</th><th>值</th></tr>
      <tr><td>应用名称</td><td>${{config.app.name}}</td></tr>
      <tr><td>环境</td><td>${{config.app.environment}}</td></tr>
      <tr><td>巡检配置</td><td>${{config.health_profiles.join(", ") || "无"}}</td></tr>
      <tr><td>扫描配置</td><td>${{config.scan_profiles.join(", ") || "无"}}</td></tr>
      <tr><td>探针超时(ms)</td><td>${{config.probe_defaults.timeout_ms}}</td></tr>
      <tr><td>探针重试</td><td>${{config.probe_defaults.retries}}</td></tr>
      <tr><td>并发数</td><td>${{config.probe_defaults.concurrency}}</td></tr>
      <tr><td>报告输出目录</td><td class="monospace">${{config.reports.output_dir}}</td></tr>
      <tr><td>报告格式</td><td>${{config.reports.formats.join(", ")}}</td></tr>
      <tr><td>存储类型</td><td>${{config.storage.type}}</td></tr>
      <tr><td>存储路径</td><td class="monospace">${{config.storage.path}}</td></tr>
      <tr><td>高风险端口</td><td class="monospace">${{config.security.risky_ports.join(", ") || "无"}}</td></tr>
    </table>`;

    // 加载详细配置
    const [healthProfiles, scanProfiles] = await Promise.all([
      fetchJSON("/api/config/health-profiles"),
      fetchJSON("/api/config/scan-profiles"),
    ]);

    if (healthProfiles.length > 0) {{
      html += `<h3 style="margin:20px 0 10px;color:var(--accent);">巡检配置详情</h3>`;
      for (const p of healthProfiles) {{
        html += `<table style="margin-bottom:12px;">
          <tr><th colspan="4">${{p.name}} (${{p.description || "无描述"}})</th></tr>
          <tr><th>名称</th><th>类型</th><th>值</th><th>检查项</th></tr>
          ${{p.targets.map(t => `<tr>
            <td>${{t.name}}</td>
            <td>${{t.type}}</td>
            <td class="monospace">${{t.value}}</td>
            <td>${{t.checks.join(", ")}}</td>
          </tr>`).join("")}}
        </table>`;
      }}
    }}

    if (scanProfiles.length > 0) {{
      html += `<h3 style="margin:20px 0 10px;color:var(--accent);">扫描配置详情</h3>`;
      for (const p of scanProfiles) {{
        html += `<table style="margin-bottom:12px;">
          <tr><th colspan="2">${{p.name}} (${{p.description || "无描述"}})</th></tr>
          <tr><td>网段</td><td class="monospace">${{p.subnets.join(", ")}}</td></tr>
          <tr><td>Ping</td><td>${{p.ping.enabled ? "启用" : "禁用"}} (超时 ${{p.ping.timeout_ms}}ms, 重试 ${{p.ping.retries}})</td></tr>
          <tr><td>TCP 端口</td><td class="monospace">${{p.tcp_ports.join(", ") || "无"}}</td></tr>
        </table>`;
      }}
    }}

    container.innerHTML = html;
  }} catch (e) {{
    container.innerHTML = `<p class="empty">加载配置失败: ${{e.message}}<br><br>请通过 <code>ops web run</code> 启动 Web Console 以加载配置。</p>`;
  }}
}}

async function showAssetDetail(ip) {{
  try {{
    const asset = await fetchJSON(`/api/assets/${{encodeURIComponent(ip)}}`);
    document.getElementById("modal-title").textContent = `资产详情: ${{ip}}`;
    const ports = asset.open_ports.length > 0 ? asset.open_ports.join(", ") : "无";
    document.getElementById("modal-body").innerHTML = `
      <table>
        <tr><th>字段</th><th>值</th></tr>
        ${{Object.entries({{
          "IP": asset.ip,
          "主机名": asset.hostname || "—",
          "MAC": asset.mac || "—",
          "厂商": asset.vendor || "—",
          "OS 猜测": asset.os_hint || "—",
          "资产类型": asset.asset_type || "—",
          "开放端口": ports,
          "状态": asset.status,
          "首次发现": asset.first_seen ? new Date(asset.first_seen).toLocaleString("zh-CN") : "—",
          "最后发现": asset.last_seen ? new Date(asset.last_seen).toLocaleString("zh-CN") : "—",
          "来源": asset.source,
          "负责人": asset.owner || "—",
          "描述": asset.description || "—",
          "标签": asset.tags.length > 0 ? asset.tags.join(", ") : "—",
        }}).map(([k, v]) => `<tr><td>${{k}}</td><td>${{v}}</td></tr>`).join("")}}
      </table>`;
    document.getElementById("modal-overlay").classList.add("active");
  }} catch (e) {{
    showToast("加载资产详情失败: " + e.message, "error");
  }}
}}

async function showTaskDetail(taskId) {{
  try {{
    const [task, results, findings] = await Promise.all([
      fetchJSON(`/api/tasks/${{encodeURIComponent(taskId)}}`),
      fetchJSON(`/api/tasks/${{encodeURIComponent(taskId)}}/results`),
      fetchJSON(`/api/tasks/${{encodeURIComponent(taskId)}}/findings`),
    ]);
    const typeLabel = TASK_TYPE_LABELS[task.task_type] || task.task_type;
    document.getElementById("modal-title").textContent = `任务详情: ${{taskId}}`;

    let findingsHtml = "";
    if (findings.length > 0) {{
      findingsHtml = `<h3 style="margin:16px 0 8px;color:var(--accent);">发现项 (${{findings.length}})</h3>
      <table>
        <tr><th>严重程度</th><th>类别</th><th>标题</th><th>描述</th><th>建议</th></tr>
        ${{findings.map(f => `<tr>
          <td><span class="badge badge-${{f.severity === "critical" || f.severity === "high" ? "failed" : f.severity === "medium" ? "warning" : "info"}}">${{SEVERITY_LABELS[f.severity] || f.severity}}</span></td>
          <td>${{f.category}}</td>
          <td>${{f.title}}</td>
          <td>${{f.description}}</td>
          <td>${{f.recommendation || "—"}}</td>
        </tr>`).join("")}}
      </table>`;
    }}

    let resultsHtml = "";
    if (results.length > 0) {{
      resultsHtml = `<h3 style="margin:16px 0 8px;color:var(--accent);">探测结果 (${{results.length}})</h3>
      <table>
        <tr><th>探针类型</th><th>目标</th><th>状态</th><th>耗时(ms)</th><th>观察值</th></tr>
        ${{results.map(r => `<tr>
          <td>${{r.probe_type}}</td>
          <td class="monospace">${{r.target.value}}</td>
          <td><span class="badge badge-${{r.status === "success" ? "success" : "failed"}}">${{r.status}}</span></td>
          <td>${{r.duration_ms ?? "—"}}</td>
          <td class="monospace">${{JSON.stringify(r.observations).substring(0, 100)}}</td>
        </tr>`).join("")}}
      </table>`;
    }}

    document.getElementById("modal-body").innerHTML = `
      <table>
        <tr><th>字段</th><th>值</th></tr>
        <tr><td>任务 ID</td><td class="monospace">${{task.id}}</td></tr>
        <tr><td>类型</td><td>${{typeLabel}}</td></tr>
        <tr><td>状态</td><td>${{task.status}}</td></tr>
        <tr><td>风险等级</td><td>${{task.risk_level}}</td></tr>
        <tr><td>请求人</td><td>${{task.requested_by}}</td></tr>
        <tr><td>来源</td><td>${{task.source}}</td></tr>
        <tr><td>开始时间</td><td>${{task.started_at ? new Date(task.started_at).toLocaleString("zh-CN") : "—"}}</td></tr>
        <tr><td>结束时间</td><td>${{task.ended_at ? new Date(task.ended_at).toLocaleString("zh-CN") : "—"}}</td></tr>
        ${{task.summary && Object.keys(task.summary).length > 0 ? `<tr><td>摘要</td><td><pre>${{JSON.stringify(task.summary, null, 2)}}</pre></td></tr>` : ""}}
      </table>
      ${{resultsHtml}}
      ${{findingsHtml}}`;
    document.getElementById("modal-overlay").classList.add("active");
  }} catch (e) {{
    showToast("加载任务详情失败: " + e.message, "error");
  }}
}}

async function showReportContent(reportId) {{
  try {{
    const data = await fetchJSON(`/api/reports/${{encodeURIComponent(reportId)}}/content`);
    document.getElementById("modal-title").textContent = data.title || "报告内容";
    const isJson = data.format === "json";
    document.getElementById("modal-body").innerHTML = `
      <p style="margin-bottom:12px;color:var(--text-dim);">格式: ${{data.format}} | 路径: <span class="monospace">${{data.path}}</span></p>
      <pre>${{isJson ? JSON.stringify(JSON.parse(data.content), null, 2) : data.content}}</pre>`;
    document.getElementById("modal-overlay").classList.add("active");
  }} catch (e) {{
    showToast("加载报告内容失败: " + e.message, "error");
  }}
}}

function closeModal(event) {{
  if (event && event.target !== document.getElementById("modal-overlay")) return;
  document.getElementById("modal-overlay").classList.remove("active");
}}

// ===========================================================================
// 趋势分析
// ===========================================================================

const PROBE_METRIC_LABELS = {{
  avg_rtt_ms: "平均RTT(ms)", min_rtt_ms: "最小RTT(ms)", max_rtt_ms: "最大RTT(ms)",
  packet_loss_percent: "丢包率(%)", duration_ms: "耗时(ms)",
  response_time_ms: "响应时间(ms)", days_remaining: "剩余天数",
}};

async function loadTrendTargets() {{
  const probeType = document.getElementById("trend-probe-type").value;
  try {{
    const targets = await fetchJSON(`/api/trends/targets?probe_type=${{encodeURIComponent(probeType)}}`);
    const targetSel = document.getElementById("trend-target");
    targetSel.innerHTML = '<option value="">全部目标</option>' +
      targets.map(t => `<option value="${{t.target}}">${{t.target}}</option>`).join("");
    loadTrendData();
  }} catch (e) {{
    document.getElementById("trend-content").innerHTML = `<p class="empty">加载失败: ${{e.message}}</p>`;
  }}
}}

async function loadTrendData() {{
  const probeType = document.getElementById("trend-probe-type").value;
  const target = document.getElementById("trend-target").value;
  const metric = document.getElementById("trend-metric").value;
  const days = document.getElementById("trend-days").value;
  const granularity = document.getElementById("trend-granularity").value;
  const content = document.getElementById("trend-content");
  content.innerHTML = '<p class="loading">查询中...</p>';
  try {{
    let url = `/api/trends/probe?probe_type=${{encodeURIComponent(probeType)}}&days=${{days}}&granularity=${{granularity}}`;
    if (target) url += `&target=${{encodeURIComponent(target)}}`;
    if (metric) url += `&metric=${{encodeURIComponent(metric)}}`;
    const data = await fetchJSON(url);
    renderTrendContent(data);
  }} catch (e) {{
    content.innerHTML = `<p class="empty">查询失败: ${{e.message}}</p>`;
  }}
}}

function renderTrendContent(data) {{
  const content = document.getElementById("trend-content");
  let html = "";

  // 状态分布
  const sd = data.status_distribution;
  if (sd && sd.total > 0) {{
    const successPct = sd.total > 0 ? (sd.success / sd.total * 100).toFixed(1) : 0;
    html += `<div class="chart-container">
      <h3>状态分布 (共 ${{sd.total}} 次检查)</h3>
      <div class="bar-chart">
        <div class="bar"><div class="bar-fill" style="height:${{sd.success>0?(sd.success/sd.total*100):0}}%;background:var(--green);"></div><div class="bar-label">成功 ${{sd.success}}</div></div>
        <div class="bar"><div class="bar-fill" style="height:${{sd.failed>0?(sd.failed/sd.total*100):0}}%;background:var(--red);"></div><div class="bar-label">失败 ${{sd.failed}}</div></div>
        <div class="bar"><div class="bar-fill" style="height:${{sd.timeout>0?(sd.timeout/sd.total*100):0}}%;background:var(--orange);"></div><div class="bar-label">超时 ${{sd.timeout}}</div></div>
      </div>
      <p style="margin-top:8px;font-size:13px;color:var(--text-dim);">成功率: ${{successPct}}%</p>
    </div>`;
  }}

  // 指标趋势图
  const ms = data.metric_stats;
  if (ms && Object.keys(ms).length > 0) {{
    for (const [metric, stats] of Object.entries(ms)) {{
      if (!stats || stats.length === 0) continue;
      const label = PROBE_METRIC_LABELS[metric] || metric;
      html += `<div class="chart-container"><h3>${{label}} 趋势</h3>${{renderSvgLineChart(stats, metric)}}</div>`;
    }}
  }}

  if (!html) {{
    html = '<p class="empty">暂无趋势数据。运行巡检任务产生历史数据后再查询。</p>';
  }}

  content.innerHTML = html;
}}

function renderSvgLineChart(stats, metric) {{
  if (!stats || stats.length === 0) return '<p class="empty">无数据</p>';
  const width = 800, height = 200, padding = 40;
  const allVals = stats.flatMap(s => [s.avg, s.min, s.max].filter(v => v !== null && v !== undefined));
  if (allVals.length === 0) return '<p class="empty">无有效数值</p>';
  const minVal = Math.min(...allVals);
  const maxVal = Math.max(...allVals);
  const range = maxVal - minVal || 1;
  const xStep = (width - padding * 2) / Math.max(stats.length - 1, 1);

  const points = stats.map((s, i) => {{
    const x = padding + i * xStep;
    const y = height - padding - ((s.avg !== null ? s.avg : minVal) - minVal) / range * (height - padding * 2);
    return `${{x}},${{y}}`;
  }});

  const areaPoints = `${{padding}},${{height - padding}} ${{points.join(" ")}} ${{padding + (stats.length - 1) * xStep}},${{height - padding}}`;

  let gridLines = "";
  for (let i = 0; i <= 4; i++) {{
    const y = padding + (height - padding * 2) * i / 4;
    const val = maxVal - (range * i / 4);
    gridLines += `<line class="grid-line" x1="${{padding}}" y1="${{y}}" x2="${{width - padding}}" y2="${{y}}"/>`;
    gridLines += `<text class="axis-text" x="${{padding - 4}}" y="${{y + 3}}" text-anchor="end">${{val.toFixed(1)}}</text>`;
  }}

  let xLabels = "";
  const labelStep = Math.ceil(stats.length / 8);
  stats.forEach((s, i) => {{
    if (i % labelStep === 0) {{
      const x = padding + i * xStep;
      const label = s.period ? String(s.period).substring(5) : "";
      xLabels += `<text class="axis-text" x="${{x}}" y="${{height - padding + 14}}" text-anchor="middle">${{label}}</text>`;
    }}
  }});

  let dataPoints = "";
  stats.forEach((s, i) => {{
    const x = padding + i * xStep;
    const y = height - padding - ((s.avg !== null ? s.avg : minVal) - minVal) / range * (height - padding * 2);
    dataPoints += `<circle class="data-point" cx="${{x}}" cy="${{y}}"/>`;
  }});

  return `<svg class="chart-svg" viewBox="0 0 ${{width}} ${{height}}" preserveAspectRatio="xMidYMid meet">
    ${{gridLines}}
    ${{xLabels}}
    <polygon class="data-area" points="${{areaPoints}}"/>
    <polyline class="data-line" points="${{points.join(" ")}}"/>
    ${{dataPoints}}
  </svg>`;
}}

// ===========================================================================
// AI 助手
// ===========================================================================

async function aiSummarize() {{
  const taskId = document.getElementById("ai-summarize-task").value.trim();
  if (!taskId) {{ showToast("请输入任务 ID", "error"); return; }}
  const result = document.getElementById("ai-summarize-result");
  result.innerHTML = '<p class="loading">正在生成 AI 摘要...</p>';
  try {{
    const data = await fetchJSON(`/api/ai/summarize/${{encodeURIComponent(taskId)}}`);
    renderAIResult(result, data);
  }} catch (e) {{
    result.innerHTML = `<p class="empty">生成失败: ${{e.message}}</p>`;
  }}
}}

async function aiExplain() {{
  const taskId = document.getElementById("ai-explain-task").value.trim();
  if (!taskId) {{ showToast("请输入任务 ID", "error"); return; }}
  const question = document.getElementById("ai-explain-question").value.trim();
  const result = document.getElementById("ai-explain-result");
  result.innerHTML = '<p class="loading">正在分析异常...</p>';
  try {{
    let url = `/api/ai/explain/${{encodeURIComponent(taskId)}}`;
    if (question) url += `?question=${{encodeURIComponent(question)}}`;
    const data = await fetchJSON(url);
    renderAIResult(result, data);
  }} catch (e) {{
    result.innerHTML = `<p class="empty">分析失败: ${{e.message}}</p>`;
  }}
}}

async function aiWeekly() {{
  const days = document.getElementById("ai-weekly-days").value;
  const result = document.getElementById("ai-weekly-result");
  result.innerHTML = '<p class="loading">正在生成 AI 周报...</p>';
  try {{
    const data = await fetchJSON(`/api/ai/weekly?days=${{days}}`);
    renderAIResult(result, data);
  }} catch (e) {{
    result.innerHTML = `<p class="empty">生成失败: ${{e.message}}</p>`;
  }}
}}

function renderAIResult(container, data) {{
  let html = "";
  if (data.facts && data.facts.length > 0) {{
    html += `<div class="ai-label">📋 事实 (Facts)</div><div class="ai-facts">`;
    data.facts.forEach(f => {{ html += `<p>• ${{f}}</p>`; }});
    html += `</div>`;
  }}
  if (data.inferences && data.inferences.length > 0) {{
    html += `<div class="ai-label" style="margin-top:12px;">💡 推断 (Inferences)</div><div class="ai-inferences">`;
    data.inferences.forEach(i => {{ html += `<p>• ${{i}}</p>`; }});
    html += `</div>`;
  }}
  if (data.summary) {{
    html += `<div class="ai-label" style="margin-top:12px;">📝 摘要</div><div class="ai-facts">${{data.summary}}</div>`;
  }}
  if (data.recommendation) {{
    html += `<div class="ai-label" style="margin-top:12px;">✅ 建议</div><div class="ai-facts">${{data.recommendation}}</div>`;
  }}
  if (!html) {{
    html = `<pre>${{JSON.stringify(data, null, 2)}}</pre>`;
  }}
  if (data.backend || data.model || data.duration_ms !== undefined) {{
    html += `<div class="ai-meta">后端: ${{data.backend || "—"}} | 模型: ${{data.model || "—"}} | 耗时: ${{data.duration_ms ?? "—"}}ms</div>`;
  }}
  container.innerHTML = html;
}}

async function loadAILogs() {{
  const tbody = document.getElementById("ai-logs-body");
  try {{
    const logs = await fetchJSON("/api/ai/logs?limit=50");
    if (logs.length === 0) {{
      tbody.innerHTML = '<tr><td colspan="6" class="empty">暂无 AI 调用记录</td></tr>';
      return;
    }}
    tbody.innerHTML = logs.map(l => {{
      const time = l.called_at ? new Date(l.called_at).toLocaleString("zh-CN") : "—";
      const statusBadge = l.success
        ? '<span class="badge badge-success">成功</span>'
        : '<span class="badge badge-failed">失败</span>';
      return `<tr>
        <td>${{time}}</td>
        <td>${{l.scenario || "—"}}</td>
        <td class="monospace">${{l.task_id || "—"}}</td>
        <td>${{l.backend || "—"}}</td>
        <td>${{statusBadge}}</td>
        <td>${{l.duration_ms ?? "—"}}</td>
      </tr>`;
    }}).join("");
  }} catch (e) {{
    tbody.innerHTML = `<tr><td colspan="6" class="empty">加载失败: ${{e.message}}</td></tr>`;
  }}
}}

// ===========================================================================
// 网络拓扑
// ===========================================================================

async function loadTopology() {{
  const container = document.getElementById("topo-overview");
  container.innerHTML = '<p class="loading">正在采集拓扑数据...</p>';
  try {{
    const data = await fetchJSON("/api/topology?reconcile=true");
    let html = '<div class="topo-section"><h3>本机网络信息</h3>';
    html += `<table>
      <tr><th>字段</th><th>值</th></tr>
      <tr><td>本机标识</td><td class="monospace">${{data.source || "—"}}</td></tr>
      <tr><td>默认网关</td><td class="monospace">${{data.gateway || "—"}}</td></tr>
      <tr><td>采集时间</td><td>${{data.collected_at ? new Date(data.collected_at).toLocaleString("zh-CN") : "—"}}</td></tr>
    </table>`;

    if (data.interfaces && data.interfaces.length > 0) {{
      html += `<h3 style="margin-top:16px;">网络接口 (${{data.interfaces.length}})</h3><table>
        <tr><th>名称</th><th>IP</th><th>MAC</th><th>状态</th></tr>`;
      data.interfaces.forEach(iface => {{
        html += `<tr>
          <td>${{iface.name || "—"}}</td>
          <td class="monospace">${{iface.ip || "—"}}</td>
          <td class="monospace">${{iface.mac || "—"}}</td>
          <td>${{iface.up ? '<span class="badge badge-success">UP</span>' : '<span class="badge badge-failed">DOWN</span>'}}</td>
        </tr>`;
      }});
      html += `</table>`;
    }}

    if (data.reconciliation) {{
      const r = data.reconciliation;
      html += `<h3 style="margin-top:16px;">资产对比</h3><table>
        <tr><th>类别</th><th>数量</th></tr>
        <tr><td>匹配设备</td><td>${{r.matched ? r.matched.length : 0}}</td></tr>
        <tr><td>新设备 (ARP 有/资产库无)</td><td style="color:var(--orange);">${{r.new_devices ? r.new_devices.length : 0}}</td></tr>
        <tr><td>离线设备 (资产库有/ARP 无)</td><td style="color:var(--red);">${{r.offline_devices ? r.offline_devices.length : 0}}</td></tr>
        <tr><td>未知厂商</td><td>${{r.unknown_vendors ? r.unknown_vendors.length : 0}}</td></tr>
      </table>`;
    }}

    html += '</div>';
    container.innerHTML = html;
  }} catch (e) {{
    container.innerHTML = `<p class="empty">加载失败: ${{e.message}}</p>`;
  }}
}}

async function loadArpTable() {{
  const tbody = document.getElementById("topo-arp-body");
  tbody.innerHTML = '<tr><td colspan="6" class="loading">加载中...</td></tr>';
  try {{
    const entries = await fetchJSON("/api/topology/arp");
    if (entries.length === 0) {{
      tbody.innerHTML = '<tr><td colspan="6" class="empty">ARP 表为空</td></tr>';
      return;
    }}
    tbody.innerHTML = entries.map(e => `<tr>
      <td class="monospace">${{e.ip}}</td>
      <td class="monospace">${{e.mac}}</td>
      <td>${{e.interface || "—"}}</td>
      <td>${{e.state || "—"}}</td>
      <td>${{e.vendor || "—"}}</td>
      <td>${{e.device_type || "—"}}</td>
    </tr>`).join("");
  }} catch (err) {{
    tbody.innerHTML = `<tr><td colspan="6" class="empty">加载失败: ${{err.message}}</td></tr>`;
  }}
}}

async function loadUnknownDevices() {{
  const container = document.getElementById("topo-overview");
  container.innerHTML = '<p class="loading">正在检测未知设备...</p>';
  try {{
    const unknown = await fetchJSON("/api/topology/unknown");
    let html = '<div class="topo-section"><h3>⚠️ 未知设备检测</h3>';
    if (unknown.length === 0) {{
      html += '<p class="empty">未发现未知设备，ARP 表中所有设备均在资产库中。</p>';
    }} else {{
      html += `<p style="color:var(--orange);margin-bottom:12px;">发现 ${{unknown.length}} 个不在资产库中的设备：</p><table>
        <tr><th>IP</th><th>MAC</th><th>接口</th><th>厂商</th></tr>`;
      unknown.forEach(e => {{
        html += `<tr>
          <td class="monospace">${{e.ip}}</td>
          <td class="monospace">${{e.mac}}</td>
          <td>${{e.interface || "—"}}</td>
          <td>${{e.vendor || "—"}}</td>
        </tr>`;
      }});
      html += `</table>`;
    }}
    html += '</div>';
    container.innerHTML = html;
  }} catch (e) {{
    container.innerHTML = `<p class="empty">检测失败: ${{e.message}}</p>`;
  }}
}}

async function runTraceroute() {{
  const target = document.getElementById("topo-traceroute-target").value.trim();
  if (!target) {{ showToast("请输入目标地址", "error"); return; }}
  const container = document.getElementById("topo-traceroute-result");
  container.innerHTML = '<p class="loading">正在追踪路由...</p>';
  try {{
    const data = await fetchJSON(`/api/topology/traceroute/${{encodeURIComponent(target)}}?max_hops=15`);
    let html = `<div class="topo-graph">`;
    html += `目标: ${{data.target}}  |  总跳数: ${{data.total_hops}}  |  ${{data.reached ? "✅ 已到达" : "❌ 未到达"}}\n\n`;
    if (data.hops && data.hops.length > 0) {{
      data.hops.forEach(hop => {{
        const rtt = hop.rtt_ms && hop.rtt_ms.length > 0 ? hop.rtt_ms.map(r => r.toFixed(1) + "ms").join("  ") : "*";
        const ip = hop.ip || "*";
        html += `${{hop.hop.toString().padStart(2)}}  ${{ip.padEnd(18)}}  ${{rtt}}\n`;
      }});
    }}
    html += `</div>`;
    container.innerHTML = html;
  }} catch (e) {{
    container.innerHTML = `<p class="empty">追踪失败: ${{e.message}}</p>`;
  }}
}}

// ===========================================================================
// 工作流
// ===========================================================================

async function loadWorkflows() {{
  await Promise.all([loadWorkflowList(), loadWorkflowHistory()]);
}}

async function loadWorkflowList() {{
  const container = document.getElementById("wf-list");
  try {{
    const workflows = await fetchJSON("/api/workflows");
    if (workflows.length === 0) {{
      container.innerHTML = '<p class="empty">暂无可用工作流</p>';
      return;
    }}
    container.innerHTML = workflows.map(wf => {{
      const stepsHtml = wf.steps.map(s => {{
        const riskCls = s.risk_level || "read_only";
        return `<span class="wf-step-item ${{riskCls}}">${{s.id}} (${{s.action}})</span>`;
      }}).join("");
      return `<div class="wf-card">
        <h3>${{wf.name}}</h3>
        <div class="wf-desc">${{wf.description || "无描述"}}</div>
        <div class="wf-steps">${{stepsHtml}}</div>
        <button class="btn btn-success" onclick="runWorkflow('${{wf.name}}')">执行工作流</button>
      </div>`;
    }}).join("");
  }} catch (e) {{
    container.innerHTML = `<p class="empty">加载失败: ${{e.message}}</p>`;
  }}
}}

async function runWorkflow(name) {{
  if (!confirm(`确认执行工作流 "${{name}}"？\\n\\n只读步骤将自动执行，低风险变更步骤需要确认。`)) return;
  showToast(`正在执行工作流: ${{name}}...`, "success");
  try {{
    const data = await fetchJSON(`/api/workflows/${{encodeURIComponent(name)}}/run`, {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify({{confirm: true}}),
    }});
    const statusBadge = data.status === "success"
      ? '<span class="badge badge-success">成功</span>'
      : data.status === "failed"
      ? '<span class="badge badge-failed">失败</span>'
      : `<span class="badge badge-info">${{data.status}}</span>`;
    showToast(`工作流执行完成: ${{data.status}}`, data.status === "success" ? "success" : "error");
    loadWorkflowHistory();
    showWorkflowDetail(data.id);
  }} catch (e) {{
    showToast("工作流执行失败: " + e.message, "error");
  }}
}}

async function loadWorkflowHistory() {{
  const tbody = document.getElementById("wf-history-body");
  try {{
    const executions = await fetchJSON("/api/workflows/executions?limit=50");
    if (executions.length === 0) {{
      tbody.innerHTML = '<tr><td colspan="8" class="empty">暂无工作流执行记录</td></tr>';
      return;
    }}
    tbody.innerHTML = executions.map(e => {{
      const statusBadge = e.status === "success"
        ? '<span class="badge badge-success">成功</span>'
        : e.status === "failed"
        ? '<span class="badge badge-failed">失败</span>'
        : e.status === "running"
        ? '<span class="badge badge-running">运行中</span>'
        : `<span class="badge badge-info">${{e.status}}</span>`;
      const started = e.started_at ? new Date(e.started_at).toLocaleString("zh-CN") : "—";
      const ended = e.ended_at ? new Date(e.ended_at).toLocaleString("zh-CN") : "—";
      return `<tr>
        <td><span class="detail-link monospace" onclick="showWorkflowDetail('${{e.id}}')">${{e.id.substring(0,8)}}</span></td>
        <td>${{e.workflow_name}}</td>
        <td>${{statusBadge}}</td>
        <td>${{e.trigger}}</td>
        <td>${{e.steps ? e.steps.length : 0}}</td>
        <td>${{started}}</td>
        <td>${{ended}}</td>
        <td><span class="detail-link" onclick="showWorkflowDetail('${{e.id}}')">详情</span></td>
      </tr>`;
    }}).join("");
  }} catch (e) {{
    tbody.innerHTML = `<tr><td colspan="8" class="empty">加载失败: ${{e.message}}</td></tr>`;
  }}
}}

async function showWorkflowDetail(executionId) {{
  try {{
    const data = await fetchJSON(`/api/workflows/executions/${{encodeURIComponent(executionId)}}`);
    document.getElementById("modal-title").textContent = `工作流执行详情: ${{executionId.substring(0, 8)}}`;

    let stepsHtml = "";
    if (data.steps && data.steps.length > 0) {{
      stepsHtml = `<h3 style="margin:16px 0 8px;color:var(--accent);">执行步骤 (${{data.steps.length}})</h3>`;
      data.steps.forEach(s => {{
        const statusCls = s.status || "pending";
        const statusText = s.status || "—";
        const errorHtml = s.error ? `<span style="color:var(--red);margin-left:8px;">❌ ${{s.error}}</span>` : "";
        const resultHtml = s.result ? `<details style="margin-top:4px;"><summary style="cursor:pointer;color:var(--text-dim);font-size:12px;">查看结果</summary><pre>${{JSON.stringify(s.result, null, 2)}}</pre></details>` : "";
        stepsHtml += `<div class="wf-step-row">
          <span class="wf-step-status ${{statusCls}}"></span>
          <span style="flex:1;"><strong>${{s.step_id}}</strong> (${{s.action}}) — ${{statusText}}${{errorHtml}}</span>
          ${{resultHtml}}
        </div>`;
      }});
    }}

    document.getElementById("modal-body").innerHTML = `
      <table>
        <tr><th>字段</th><th>值</th></tr>
        <tr><td>执行 ID</td><td class="monospace">${{data.id}}</td></tr>
        <tr><td>工作流</td><td>${{data.workflow_name}}</td></tr>
        <tr><td>状态</td><td>${{data.status}}</td></tr>
        <tr><td>触发者</td><td>${{data.trigger}}</td></tr>
        <tr><td>开始时间</td><td>${{data.started_at ? new Date(data.started_at).toLocaleString("zh-CN") : "—"}}</td></tr>
        <tr><td>结束时间</td><td>${{data.ended_at ? new Date(data.ended_at).toLocaleString("zh-CN") : "—"}}</td></tr>
        ${{data.result_summary ? `<tr><td>结果摘要</td><td>${{data.result_summary}}</td></tr>` : ""}}
      </table>
      ${{stepsHtml}}`;
    document.getElementById("modal-overlay").classList.add("active");
  }} catch (e) {{
    showToast("加载工作流详情失败: " + e.message, "error");
  }}
}}

// =========== 操作中心 ===========

async function loadOpsCenter() {{
  if (CONFIG_AVAILABLE) {{
    try {{
      const [healthProfiles, scanProfiles] = await Promise.all([
        fetchJSON("/api/config/health-profiles"),
        fetchJSON("/api/config/scan-profiles"),
      ]);
      const diffSelect = document.getElementById("ops-diff-profile");
      if (diffSelect) {{
        diffSelect.innerHTML = '<option value="">选择扫描配置...</option>' +
          Object.keys(scanProfiles).map(k =>
            `<option value="${{k}}">${{k}} — ${{scanProfiles[k].description || scanProfiles[k].subnet || ""}}</option>`
          ).join("");
      }}
    }} catch (e) {{
      // 配置不可用时忽略
    }}
  }}
}}

function showOpsResult(elemId, html) {{
  const el = document.getElementById(elemId);
  el.innerHTML = html;
  el.classList.add("active");
}}

function formatTaskResult(task) {{
  let html = `<div style="margin-bottom:8px;">`;
  html += `<span class="badge badge-${{task.status === "success" ? "success" : task.status === "failed" ? "failed" : "info"}}">${{task.status}}</span> `;
  html += `<span style="color:var(--text-dim);font-size:12px;">任务ID: ${{task.id}}</span>`;
  html += `</div>`;
  if (task.summary) {{
    const s = task.summary;
    if (s.title) html += `<div class="ops-summary-title">${{s.title}}</div>`;
    if (s.likely_area) html += `<div class="ops-summary-area">可能原因: ${{s.likely_area}}</div>`;
    if (s.recommendation) html += `<div class="ops-summary-rec">建议: ${{s.recommendation}}</div>`;
    if (s.findings_count !== undefined) html += `<div style="margin-top:4px;">发现项: ${{s.findings_count}}</div>`;
    if (s.report_id) html += `<div style="margin-top:4px;">报告ID: ${{s.report_id}}</div>`;
    if (s.hostname) html += `<div style="margin-top:4px;">主机名: ${{s.hostname}} / OS: ${{s.os}}</div>`;
    if (s.executed !== undefined) html += `<div style="margin-top:4px;">已执行: ${{s.executed}} / 状态: ${{s.status || "—"}}</div>`;
    if (s.title && s.likely_area) {{}} else if (typeof s === "object" && !s.title) {{
      html += `<pre style="margin-top:8px;">${{JSON.stringify(s, null, 2)}}</pre>`;
    }}
  }}
  html += `<div style="margin-top:8px;"><a href="#" class="detail-link" onclick="showTaskDetail('${{task.id}}');return false;">查看详情 →</a></div>`;
  return html;
}}

async function opsDiagnose() {{
  const scenario = document.getElementById("ops-diagnose-scenario").value;
  const target = document.getElementById("ops-diagnose-target").value.trim();
  const resultEl = "ops-diagnose-result";
  showOpsResult(resultEl, '<span class="loading">诊断中...</span>');
  try {{
    const body = {{ scenario, target: target || null }};
    const task = await fetchJSON("/api/ops/diagnose", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(body),
    }});
    showOpsResult(resultEl, formatTaskResult(task));
    showToast("诊断完成", "success");
  }} catch (e) {{
    showOpsResult(resultEl, `<span style="color:var(--red);">诊断失败: ${{e.message}}</span>`);
    showToast("诊断失败: " + e.message, "error");
  }}
}}

async function opsSecurityCheck() {{
  showOpsResult("ops-security-result", '<span class="loading">安全检查中...</span>');
  try {{
    const task = await fetchJSON("/api/ops/security-check", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
    }});
    showOpsResult("ops-security-result", formatTaskResult(task));
    showToast("安全检查完成", "success");
  }} catch (e) {{
    showOpsResult("ops-security-result", `<span style="color:var(--red);">安全检查失败: ${{e.message}}</span>`);
    showToast("安全检查失败: " + e.message, "error");
  }}
}}

async function opsCertCheck() {{
  const hostname = document.getElementById("ops-cert-hostname").value.trim();
  const port = parseInt(document.getElementById("ops-cert-port").value) || 443;
  if (!hostname) {{
    showToast("请输入主机名", "error");
    return;
  }}
  showOpsResult("ops-cert-result", '<span class="loading">证书检查中...</span>');
  try {{
    const task = await fetchJSON("/api/ops/cert-check", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ hostname, port }}),
    }});
    showOpsResult("ops-cert-result", formatTaskResult(task));
    showToast("证书检查完成", "success");
  }} catch (e) {{
    showOpsResult("ops-cert-result", `<span style="color:var(--red);">证书检查失败: ${{e.message}}</span>`);
    showToast("证书检查失败: " + e.message, "error");
  }}
}}

async function opsReportGenerate() {{
  const sourceTaskId = document.getElementById("ops-report-task-id").value.trim();
  const reportFormat = document.getElementById("ops-report-format").value;
  if (!sourceTaskId) {{
    showToast("请输入源任务ID", "error");
    return;
  }}
  showOpsResult("ops-report-result", '<span class="loading">生成报告中...</span>');
  try {{
    const task = await fetchJSON("/api/ops/report-generate", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ source_task_id: sourceTaskId, report_format: reportFormat }}),
    }});
    showOpsResult("ops-report-result", formatTaskResult(task));
    showToast("报告生成完成", "success");
  }} catch (e) {{
    showOpsResult("ops-report-result", `<span style="color:var(--red);">报告生成失败: ${{e.message}}</span>`);
    showToast("报告生成失败: " + e.message, "error");
  }}
}}

async function opsAssetDiff() {{
  const profileName = document.getElementById("ops-diff-profile").value;
  if (!profileName) {{
    showToast("请选择扫描配置", "error");
    return;
  }}
  showOpsResult("ops-diff-result", '<span class="loading">资产对比中...</span>');
  try {{
    const task = await fetchJSON("/api/ops/asset-diff", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ profile_name: profileName }}),
    }});
    showOpsResult("ops-diff-result", formatTaskResult(task));
    showToast("资产对比完成", "success");
  }} catch (e) {{
    showOpsResult("ops-diff-result", `<span style="color:var(--red);">资产对比失败: ${{e.message}}</span>`);
    showToast("资产对比失败: " + e.message, "error");
  }}
}}

async function opsCollectLocal() {{
  showOpsResult("ops-collect-result", '<span class="loading">采集中...</span>');
  try {{
    const task = await fetchJSON("/api/ops/collect-local", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
    }});
    showOpsResult("ops-collect-result", formatTaskResult(task));
    showToast("本机信息采集完成", "success");
  }} catch (e) {{
    showOpsResult("ops-collect-result", `<span style="color:var(--red);">采集失败: ${{e.message}}</span>`);
    showToast("采集失败: " + e.message, "error");
  }}
}}

async function opsFlushDns(confirm) {{
  showOpsResult("ops-flushdns-result", '<span class="loading">${{confirm ? "执行中..." : "生成计划中..."}}</span>');
  try {{
    const task = await fetchJSON("/api/ops/flush-dns", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ dry_run: !confirm, confirm: confirm }}),
    }});
    showOpsResult("ops-flushdns-result", formatTaskResult(task));
    showToast(confirm ? "DNS 缓存清理完成" : "Dry Run 计划已生成", "success");
  }} catch (e) {{
    showOpsResult("ops-flushdns-result", `<span style="color:var(--red);">操作失败: ${{e.message}}</span>`);
    showToast("操作失败: " + e.message, "error");
  }}
}}

// ---------------------------------------------------------------------------
// 调度告警管理
// ---------------------------------------------------------------------------

async function loadSchedules() {{
  await loadScheduleList();
  await loadAlerts();
}}

async function loadScheduleList() {{
  const tbody = document.getElementById("schedule-body");
  tbody.innerHTML = '<tr><td colspan="8" class="loading">加载中...</td></tr>';
  try {{
    const tasks = await fetchJSON("/api/schedules");
    if (tasks.length === 0) {{
      tbody.innerHTML = '<tr><td colspan="8" class="loading">暂无定时任务</td></tr>';
      return;
    }}
    tbody.innerHTML = tasks.map(t => {{
      const statusBadge = t.enabled
        ? '<span class="status-badge" style="background:rgba(76,175,80,0.15);color:var(--green);">启用</span>'
        : '<span class="status-badge" style="background:rgba(255,152,0,0.15);color:var(--orange);">禁用</span>';
      const lastRun = t.last_run ? formatTime(t.last_run) : '<span class="text-dim">-</span>';
      const nextRun = t.next_run ? formatTime(t.next_run) : '<span class="text-dim">-</span>';
      const lastStatus = t.last_status
        ? (t.last_status === 'success'
          ? '<span style="color:var(--green);">成功</span>'
          : t.last_status === 'failed'
            ? '<span style="color:var(--red);">失败</span>'
            : '<span style="color:var(--orange);">运行中</span>')
        : '<span class="text-dim">-</span>';
      const enableBtn = t.enabled
        ? `<button class="btn-sm" style="background:rgba(255,152,0,0.15);color:var(--orange);border:none;" onclick="disableSchedule('${{t.id}}')">禁用</button>`
        : `<button class="btn-sm" style="background:rgba(76,175,80,0.15);color:var(--green);border:none;" onclick="enableSchedule('${{t.id}}')">启用</button>`;
      return `<tr>
        <td>${{escapeHtml(t.name)}}</td>
        <td>${{escapeHtml(t.task_type)}}</td>
        <td>${{escapeHtml(t.profile)}}</td>
        <td><code>${{escapeHtml(t.cron)}}</code></td>
        <td>${{statusBadge}} ${{lastStatus}}</td>
        <td>${{lastRun}}</td>
        <td>${{nextRun}}</td>
        <td style="white-space:nowrap;">
          ${{enableBtn}}
          <button class="btn-sm" style="background:rgba(33,150,243,0.15);color:var(--blue);border:none;" onclick="runScheduleNow('${{t.id}}')">立即执行</button>
          <button class="btn-sm" style="background:rgba(244,67,54,0.15);color:var(--red);border:none;" onclick="deleteSchedule('${{t.id}}')">删除</button>
        </td>
      </tr>`;
    }}).join("");
  }} catch (e) {{
    tbody.innerHTML = `<tr><td colspan="8" class="loading" style="color:var(--red);">加载失败: ${{escapeHtml(e.message)}}</td></tr>`;
  }}
}}

async function addSchedule() {{
  const name = document.getElementById("sched-add-name").value.trim();
  const taskType = document.getElementById("sched-add-type").value;
  const profile = document.getElementById("sched-add-profile").value.trim() || "default";
  const cron = document.getElementById("sched-add-cron").value.trim();
  if (!name || !cron) {{
    showToast("请填写任务名称和 cron 表达式", "error");
    return;
  }}
  try {{
    await fetchJSON("/api/schedules", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ name, task_type: taskType, profile, cron }}),
    }});
    showToast("定时任务添加成功", "success");
    document.getElementById("sched-add-name").value = "";
    document.getElementById("sched-add-cron").value = "";
    await loadScheduleList();
  }} catch (e) {{
    showToast("添加失败: " + e.message, "error");
  }}
}}

async function deleteSchedule(taskId) {{
  if (!confirm("确认删除此定时任务？")) return;
  try {{
    await fetchJSON(`/api/schedules/${{encodeURIComponent(taskId)}}`, {{ method: "DELETE" }});
    showToast("已删除定时任务", "success");
    await loadScheduleList();
  }} catch (e) {{
    showToast("删除失败: " + e.message, "error");
  }}
}}

async function enableSchedule(taskId) {{
  try {{
    await fetchJSON(`/api/schedules/${{encodeURIComponent(taskId)}}/enable`, {{ method: "POST" }});
    showToast("已启用", "success");
    await loadScheduleList();
  }} catch (e) {{
    showToast("操作失败: " + e.message, "error");
  }}
}}

async function disableSchedule(taskId) {{
  try {{
    await fetchJSON(`/api/schedules/${{encodeURIComponent(taskId)}}/disable`, {{ method: "POST" }});
    showToast("已禁用", "success");
    await loadScheduleList();
  }} catch (e) {{
    showToast("操作失败: " + e.message, "error");
  }}
}}

async function runScheduleNow(taskId) {{
  showToast("正在执行...", "info");
  try {{
    await fetchJSON(`/api/schedules/${{encodeURIComponent(taskId)}}/run-now`, {{ method: "POST" }});
    showToast("任务执行完成", "success");
    await loadScheduleList();
  }} catch (e) {{
    showToast("执行失败: " + e.message, "error");
  }}
}}

async function loadAlerts() {{
  const tbody = document.getElementById("alert-body");
  const status = document.getElementById("alert-filter-status").value;
  tbody.innerHTML = '<tr><td colspan="11" class="loading">加载中...</td></tr>';
  try {{
    const url = `/api/alerts?limit=200${{status ? `&status=${{status}}` : ""}}`;
    const events = await fetchJSON(url);
    if (events.length === 0) {{
      tbody.innerHTML = '<tr><td colspan="11" class="loading">暂无告警事件</td></tr>';
      return;
    }}
    tbody.innerHTML = events.map(e => {{
      const sevColor = e.severity === 'critical' ? 'var(--red)' : e.severity === 'warning' ? 'var(--orange)' : 'var(--blue)';
      const sevBadge = `<span class="status-badge" style="background:${{sevColor}}22;color:${{sevColor}};">${{escapeHtml(e.severity)}}</span>`;
      const statusBadge = e.status === 'active'
        ? '<span class="status-badge" style="background:rgba(244,67,54,0.15);color:var(--red);">活跃</span>'
        : e.status === 'resolved'
          ? '<span class="status-badge" style="background:rgba(76,175,80,0.15);color:var(--green);">已恢复</span>'
          : '<span class="status-badge" style="background:rgba(158,158,158,0.15);color:var(--text-dim);">已抑制</span>';
      const ackBadge = e.acknowledged
        ? '<span style="color:var(--green);">已确认</span>'
        : '<span style="color:var(--text-dim);">未确认</span>';
      const ackBtn = !e.acknowledged
        ? `<button class="btn-sm" style="background:rgba(33,150,243,0.15);color:var(--blue);border:none;" onclick="ackAlert('${{e.id}}')">确认</button>`
        : '';
      return `<tr>
        <td>${{escapeHtml(e.rule_name)}}</td>
        <td>${{sevBadge}}</td>
        <td>${{escapeHtml(e.target)}}</td>
        <td>${{escapeHtml(e.probe_type)}}</td>
        <td>${{escapeHtml(e.metric)}}</td>
        <td>${{escapeHtml(e.value)}}</td>
        <td>${{escapeHtml(e.threshold)}}</td>
        <td>${{statusBadge}}</td>
        <td>${{formatTime(e.triggered_at)}}</td>
        <td>${{ackBadge}}</td>
        <td>${{ackBtn}}</td>
      </tr>`;
    }}).join("");
  }} catch (e) {{
    tbody.innerHTML = `<tr><td colspan="11" class="loading" style="color:var(--red);">加载失败: ${{escapeHtml(e.message)}}</td></tr>`;
  }}
}}

async function ackAlert(eventId) {{
  try {{
    await fetchJSON(`/api/alerts/${{encodeURIComponent(eventId)}}/acknowledge`, {{ method: "POST" }});
    showToast("告警已确认", "success");
    await loadAlerts();
  }} catch (e) {{
    showToast("操作失败: " + e.message, "error");
  }}
}}

function formatTime(dt) {{
  if (!dt) return '-';
  try {{
    const d = new Date(dt);
    return d.toLocaleString('zh-CN', {{ hour12: false }});
  }} catch {{
    return escapeHtml(String(dt));
  }}
}}

function escapeHtml(str) {{
  if (str === null || str === undefined) return '';
  return String(str).replace(/[&<>"']/g, c => ({{
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }})[c]);
}}

// 首次加载
loadOverview();

async function loadSnmpDefault() {{}}

async function snmpCollect() {{
  const target = document.getElementById('snmp-target').value.trim();
  if (!target) {{ showToast('请输入目标 IP', 'error'); return; }}
  const community = document.getElementById('snmp-community').value.trim() || 'public';
  const port = document.getElementById('snmp-port').value || 161;
  const resultDiv = document.getElementById('snmp-result');
  resultDiv.innerHTML = '<p class="loading">采集中...（可能需要数秒）</p>';
  try {{
    const data = await fetchJSON(`/api/snmp/${{encodeURIComponent(target)}}?community=${{encodeURIComponent(community)}}&port=${{port}}`);
    if (data.status === 'failed') {{
      resultDiv.innerHTML = `<div class="card" style="border-color:var(--red);"><p style="color:var(--red);font-weight:600;">采集失败</p><p>${{escapeHtml(data.error?.message || '未知错误')}}</p><p style="color:var(--text-dim);font-size:12px;">耗时: ${{data.duration_ms}}ms</p></div>`;
      return;
    }}
    const obs = data.observations || {{}};
    const interfaces = obs.interfaces || [];
    let ifaceRows = interfaces.map(iface => {{
      const statusStr = String(iface.oper_status);
      const statusBadge = statusStr === '1'
        ? '<span class="status-badge" style="background:rgba(76,175,80,0.15);color:var(--green);">up</span>'
        : statusStr === '2'
          ? '<span class="status-badge" style="background:rgba(244,67,54,0.15);color:var(--red);">down</span>'
          : statusStr === '3'
            ? '<span class="status-badge" style="background:rgba(255,152,0,0.15);color:var(--orange);">testing</span>'
            : `<span class="status-badge" style="background:rgba(158,158,158,0.15);color:var(--text-dim);">${{escapeHtml(statusStr)}}</span>`;
      return `<tr><td>${{escapeHtml(String(iface.index || '-'))}}</td><td>${{escapeHtml(String(iface.descr || '-'))}}</td><td>${{statusBadge}}</td></tr>`;
    }}).join('');
    if (!ifaceRows) ifaceRows = '<tr><td colspan="3" class="loading">无接口数据</td></tr>';

    resultDiv.innerHTML = `
      <div class="card">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px 24px;">
          <div><span style="color:var(--text-dim);">sysDescr:</span> ${{escapeHtml(String(obs.sysDescr || '-'))}}</div>
          <div><span style="color:var(--text-dim);">sysName:</span> ${{escapeHtml(String(obs.sysName || '-'))}}</div>
          <div><span style="color:var(--text-dim);">sysObjectID:</span> ${{escapeHtml(String(obs.sysObjectID || '-'))}}</div>
          <div><span style="color:var(--text-dim);">sysUpTime:</span> ${{escapeHtml(String(obs.sysUpTime || '-'))}}</div>
          <div><span style="color:var(--text-dim);">sysContact:</span> ${{escapeHtml(String(obs.sysContact || '-'))}}</div>
          <div><span style="color:var(--text-dim);">sysLocation:</span> ${{escapeHtml(String(obs.sysLocation || '-'))}}</div>
          <div><span style="color:var(--text-dim);">sysServices:</span> ${{escapeHtml(String(obs.sysServices || '-'))}}</div>
          <div><span style="color:var(--text-dim);">接口数量:</span> ${{escapeHtml(String(obs.interface_count || '-'))}}</div>
        </div>
        <p style="color:var(--text-dim);font-size:12px;margin-top:8px;">耗时: ${{data.duration_ms}}ms | 协议: ${{escapeHtml(String(data.evidence?.protocol || 'SNMPv2c'))}}</p>
      </div>
      ${{interfaces.length > 0 ? `<table style="margin-top:12px;"><thead><tr><th>序号</th><th>接口描述</th><th>状态</th></tr></thead><tbody>${{ifaceRows}}</tbody></table>` : ''}}
    `;
  }} catch (e) {{
    resultDiv.innerHTML = `<p style="color:var(--red);">采集失败: ${{escapeHtml(e.message)}}</p>`;
  }}
}}

async function snmpGetOid() {{
  const target = document.getElementById('snmp-target').value.trim();
  if (!target) {{ showToast('请先输入目标 IP', 'error'); return; }}
  const oid = document.getElementById('snmp-oid').value.trim();
  if (!oid) {{ showToast('请输入 OID', 'error'); return; }}
  const community = document.getElementById('snmp-community').value.trim() || 'public';
  const port = document.getElementById('snmp-port').value || 161;
  const resultDiv = document.getElementById('snmp-oid-result');
  resultDiv.innerHTML = '<p class="loading">查询中...</p>';
  try {{
    const data = await fetchJSON(`/api/snmp/${{encodeURIComponent(target)}}/get?oid=${{encodeURIComponent(oid)}}&community=${{encodeURIComponent(community)}}&port=${{port}}`);
    resultDiv.innerHTML = `<div class="card"><div><span style="color:var(--text-dim);">OID:</span> <span class="monospace">${{escapeHtml(data.oid)}}</span></div><div style="margin-top:6px;"><span style="color:var(--text-dim);">值:</span> <span style="font-weight:600;">${{escapeHtml(String(data.value))}}</span></div></div>`;
  }} catch (e) {{
    resultDiv.innerHTML = `<p style="color:var(--red);">查询失败: ${{escapeHtml(e.message)}}</p>`;
  }}
}}
</script>
</body>
</html>
"""
