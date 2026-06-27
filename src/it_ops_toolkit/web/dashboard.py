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
</div>

<!-- 详情弹窗 -->
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
    ]));
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
    container.innerHTML = `<p class="empty">加载配置失败: ${{e.message}}<br><br>请通过 `ops web run` 启动 Web Console 以加载配置。</p>`;
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

// 首次加载
loadOverview();
</script>
</body>
</html>
"""
