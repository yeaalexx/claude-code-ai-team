"""
Agent Control Plane — v6.0

FastAPI HTTP server running alongside the MCP server (in a background thread).
Provides REST endpoints for the VS Code Agent Monitor panel and external tooling.

v6: Finding lifecycle endpoints (approve/dismiss with reason, queue, sprint prompt,
    reminder, reopen, summary) and decision learner patterns endpoint.

Runs on localhost:3100 by default (configurable).
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conditional FastAPI / Uvicorn import — graceful fallback
# ---------------------------------------------------------------------------

try:
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse

    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False
    logger.warning(
        "FastAPI or uvicorn not installed. Control plane will not be available. "
        "Install with: pip install 'fastapi>=0.115.0' 'uvicorn>=0.34.0'"
    )

__version__ = "6.0.0"

# ---------------------------------------------------------------------------
# Audit log ring-buffer
# ---------------------------------------------------------------------------

_MAX_AUDIT_LOG = 500


class AuditLog:
    """Append-only in-memory ring buffer for agent action audit entries."""

    def __init__(self, max_entries: int = _MAX_AUDIT_LOG) -> None:
        self._entries: deque[dict[str, Any]] = deque(maxlen=max_entries)
        self._lock = threading.Lock()

    def append(self, action: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
        """Record an action and return the entry."""
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "details": details or {},
            "user": "local",
        }
        with self._lock:
            self._entries.append(entry)
        logger.info("audit | %s | %s", action, details)
        return entry

    def get(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent entries (newest first)."""
        with self._lock:
            items = list(self._entries)
        return list(reversed(items[-limit:]))


# ---------------------------------------------------------------------------
# Dashboard HTML (self-contained, dark theme, auto-refresh)
# ---------------------------------------------------------------------------

_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Control Plane — Dashboard v6</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
       background:#0d1117;color:#c9d1d9;padding:1.5rem}
  h1{font-size:1.4rem;margin-bottom:.5rem;color:#58a6ff}
  h2{font-size:1.1rem;margin:1rem 0 .5rem;color:#79c0ff;border-bottom:1px solid #21262d;padding-bottom:.3rem}
  .badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:.75rem;font-weight:600}
  .badge-ok{background:#238636;color:#fff}
  .badge-paused{background:#d29922;color:#000}
  .badge-off{background:#da3633;color:#fff}
  .badge-detected{background:#484f58;color:#c9d1d9}
  .badge-ai_analyzed{background:#6e7681;color:#fff}
  .badge-approved{background:#d29922;color:#000}
  .badge-dismissed{background:#484f58;color:#8b949e;text-decoration:line-through}
  .badge-queued{background:#1f6feb;color:#fff}
  .badge-in_progress{background:#8957e5;color:#fff}
  .badge-fix_proposed{background:#a371f7;color:#fff}
  .badge-verified{background:#238636;color:#fff}
  .badge-resolved{background:#238636;color:#fff}
  .controls{display:flex;gap:.5rem;flex-wrap:wrap;margin:.75rem 0}
  button{padding:6px 14px;border:1px solid #30363d;border-radius:6px;background:#21262d;
         color:#c9d1d9;cursor:pointer;font-size:.85rem}
  button:hover{background:#30363d}
  button.primary{background:#238636;border-color:#238636;color:#fff}
  button.danger{background:#da3633;border-color:#da3633;color:#fff}
  button.queue-btn{background:#1f6feb;border-color:#1f6feb;color:#fff}
  button.sprint-btn{background:#8957e5;border-color:#8957e5;color:#fff}
  table{width:100%;border-collapse:collapse;margin-top:.5rem;font-size:.85rem}
  th,td{text-align:left;padding:6px 10px;border-bottom:1px solid #21262d}
  th{color:#8b949e;font-weight:600}
  tr:hover{background:#161b22}
  .actions button{padding:2px 8px;font-size:.75rem;margin-right:4px}
  .severity-violation{color:#f85149}
  .severity-warning{color:#d29922}
  .severity-info{color:#58a6ff}
  .status-bar{display:flex;gap:1rem;align-items:center;margin-bottom:.5rem;flex-wrap:wrap}
  .meta{font-size:.8rem;color:#8b949e}
  #toast{position:fixed;bottom:1rem;right:1rem;background:#238636;color:#fff;
         padding:8px 16px;border-radius:6px;display:none;font-size:.85rem;z-index:100}
  .reminder-banner{background:#d29922;color:#000;padding:10px 16px;border-radius:6px;
                   margin-bottom:1rem;display:none;font-weight:600;font-size:.9rem}
  .reminder-banner button{background:#21262d;color:#fff;margin-left:1rem}
  .ai-badge{display:inline-block;padding:1px 6px;border-radius:4px;font-size:.7rem;font-weight:700;margin-left:4px}
  .ai-approve{background:#238636;color:#fff}
  .ai-dismiss{background:#da3633;color:#fff}
  .ai-confidence{font-size:.7rem;color:#8b949e;margin-left:2px}
  .expandable{cursor:pointer;color:#58a6ff;font-size:.75rem;text-decoration:underline}
  .expanded-content{display:none;font-size:.8rem;color:#8b949e;padding:4px 0 4px 12px;
                    border-left:2px solid #21262d;margin-top:4px}
  .features-list{font-size:.75rem;color:#a5d6ff}
  select.dismiss-select{background:#21262d;color:#c9d1d9;border:1px solid #30363d;
                        border-radius:4px;font-size:.75rem;padding:2px 4px}
  .summary-cards{display:flex;gap:1rem;flex-wrap:wrap;margin:.75rem 0}
  .summary-card{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:12px 16px;min-width:100px}
  .summary-card .label{font-size:.75rem;color:#8b949e}
  .summary-card .value{font-size:1.4rem;font-weight:700;color:#58a6ff}
  .tab-bar{display:flex;gap:0;border-bottom:1px solid #21262d;margin-top:1rem}
  .tab{padding:8px 16px;cursor:pointer;border-bottom:2px solid transparent;color:#8b949e;font-size:.9rem}
  .tab.active{color:#58a6ff;border-bottom-color:#58a6ff}
  .tab-content{display:none}
  .tab-content.active{display:block}
</style>
</head>
<body>
<h1>Agent Control Plane <span class="meta">v6</span></h1>

<div id="reminderBanner" class="reminder-banner"></div>

<div class="status-bar">
  <span>Status: <span id="agentBadge" class="badge badge-off">loading</span></span>
  <span>Watcher: <span id="watcherBadge" class="badge badge-off">unknown</span></span>
  <span class="meta">Version: <span id="version">-</span></span>
  <span class="meta">Last refresh: <span id="lastRefresh">-</span></span>
</div>

<div id="summaryCards" class="summary-cards"></div>

<div class="controls">
  <button class="primary" onclick="apiPost('/watcher/start',{})">Start Watcher</button>
  <button class="danger" onclick="apiPost('/watcher/stop')">Stop Watcher</button>
  <button onclick="apiPost('/pause')">Pause</button>
  <button onclick="apiPost('/resume')">Resume</button>
  <button class="sprint-btn" onclick="showSprintPrompt()">Start Sprint Fix</button>
  <button onclick="refresh()">Refresh Now</button>
</div>

<div class="tab-bar">
  <div class="tab active" onclick="switchTab('findings')">Findings</div>
  <div class="tab" onclick="switchTab('events')">Events</div>
  <div class="tab" onclick="switchTab('patterns')">Dismiss Patterns</div>
  <div class="tab" onclick="switchTab('audit')">Audit Log</div>
</div>

<div id="tab-findings" class="tab-content active">
<h2>Findings</h2>
<div class="controls" style="margin-top:0">
  <select id="statusFilter" onchange="refresh()" style="background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:4px 8px;font-size:.85rem">
    <option value="all">All statuses</option>
    <option value="detected" selected>Detected</option>
    <option value="ai_analyzed">AI Analyzed</option>
    <option value="approved">Approved</option>
    <option value="queued">Queued</option>
    <option value="in_progress">In Progress</option>
    <option value="fix_proposed">Fix Proposed</option>
    <option value="verified">Verified</option>
    <option value="resolved">Resolved</option>
    <option value="dismissed">Dismissed</option>
  </select>
  <button class="queue-btn" onclick="queueAllApproved()">Queue All Approved</button>
</div>
<table>
<thead><tr><th>ID</th><th>Service</th><th>Severity</th><th>Status</th><th>Description</th><th>AI</th><th>Actions</th></tr></thead>
<tbody id="findingsBody"><tr><td colspan="7">Loading...</td></tr></tbody>
</table>
</div>

<div id="tab-events" class="tab-content">
<h2>Recent Events</h2>
<table>
<thead><tr><th>Time</th><th>Service</th><th>Path</th><th>Type</th></tr></thead>
<tbody id="eventsBody"><tr><td colspan="4">Loading...</td></tr></tbody>
</table>
</div>

<div id="tab-patterns" class="tab-content">
<h2>Dismiss Patterns</h2>
<p class="meta" style="margin-bottom:.5rem">Common patterns of dismissed findings — potential auto-suppress candidates.</p>
<table>
<thead><tr><th>Service</th><th>Reason</th><th>Count</th><th>Example</th><th>Last Seen</th></tr></thead>
<tbody id="patternsBody"><tr><td colspan="5">Loading...</td></tr></tbody>
</table>
</div>

<div id="tab-audit" class="tab-content">
<h2>Audit Log (last 20)</h2>
<table>
<thead><tr><th>Time</th><th>Action</th><th>Details</th></tr></thead>
<tbody id="auditBody"><tr><td colspan="3">Loading...</td></tr></tbody>
</table>
</div>

<div id="sprintModal" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;
  background:rgba(0,0,0,.7);z-index:200;padding:2rem;overflow:auto">
  <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;max-width:800px;
    margin:0 auto;padding:1.5rem">
    <h2 style="margin-top:0">Sprint Fix Prompt</h2>
    <pre id="sprintPromptContent" style="background:#0d1117;padding:1rem;border-radius:6px;
      font-size:.8rem;white-space:pre-wrap;max-height:60vh;overflow:auto;color:#c9d1d9"></pre>
    <div class="controls" style="margin-top:1rem">
      <button onclick="copySprintPrompt()" class="primary">Copy to Clipboard</button>
      <button onclick="document.getElementById('sprintModal').style.display='none'">Close</button>
    </div>
  </div>
</div>

<div id="toast"></div>

<script>
const BASE = location.origin;
const $ = s => document.getElementById(s);

const DISMISS_REASONS = [
  {value:'false_positive', label:'False Positive'},
  {value:'test_code', label:'Test Code'},
  {value:'docs_only', label:'Docs Only'},
  {value:'vendor_code', label:'Vendor Code'},
  {value:'intentional', label:'Intentional'},
  {value:'duplicate', label:'Duplicate'}
];

function toast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.style.display = 'block';
  setTimeout(() => { t.style.display = 'none'; }, 2500);
}

async function api(path) {
  const r = await fetch(BASE + path);
  return r.json();
}

async function apiPost(path, body) {
  try {
    const opts = {method:'POST', headers:{'Content-Type':'application/json'}};
    if (body !== undefined) opts.body = JSON.stringify(body);
    const r = await fetch(BASE + path, opts);
    const d = await r.json();
    toast(d.message || d.status || 'Done');
    setTimeout(refresh, 500);
  } catch(e) { toast('Error: ' + e.message); }
}

function shortTime(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  return d.toLocaleTimeString();
}

function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelector(`.tab-content#tab-${name}`).classList.add('active');
  event.target.classList.add('active');
}

function toggleExpand(id) {
  const el = document.getElementById('expand-' + id);
  if (el) el.style.display = el.style.display === 'block' ? 'none' : 'block';
}

function dismissWithReason(findingId) {
  const sel = document.getElementById('dismiss-' + findingId);
  const reason = sel ? sel.value : 'false_positive';
  apiPost('/findings/' + findingId + '/dismiss', {reason: reason});
}

async function queueAllApproved() {
  apiPost('/findings/queue', {service: ''});
}

async function showSprintPrompt() {
  try {
    const data = await api('/findings/sprint-prompt');
    $('sprintPromptContent').textContent = data.prompt || 'No findings to fix.';
    $('sprintModal').style.display = 'block';
  } catch(e) { toast('Error: ' + e.message); }
}

function copySprintPrompt() {
  const text = $('sprintPromptContent').textContent;
  navigator.clipboard.writeText(text).then(() => toast('Copied!')).catch(() => toast('Copy failed'));
}

function renderAiBadge(f) {
  if (!f.ai_recommendation) return '';
  const cls = f.ai_recommendation.toLowerCase().includes('dismiss') ? 'ai-dismiss' : 'ai-approve';
  const label = f.ai_recommendation.toLowerCase().includes('dismiss') ? 'DISMISS' : 'APPROVE';
  const conf = f.ai_confidence ? Math.round(f.ai_confidence * 100) + '%' : '';
  return `<span class="ai-badge ${cls}">${label}</span><span class="ai-confidence">${conf}</span>`;
}

function renderActions(f) {
  const s = f.status;
  let html = '';
  if (s === 'detected' || s === 'ai_analyzed') {
    html += `<button class="primary" onclick="apiPost('/findings/${f.id}/approve')">Approve</button>`;
    html += `<select id="dismiss-${f.id}" class="dismiss-select">` +
      DISMISS_REASONS.map(r => `<option value="${r.value}">${r.label}</option>`).join('') +
      `</select>`;
    html += `<button onclick="dismissWithReason('${f.id}')">Dismiss</button>`;
  } else if (s === 'approved') {
    html += `<button class="queue-btn" onclick="apiPost('/findings/queue',{finding_ids:['${f.id}']})">Queue</button>`;
  } else if (s === 'dismissed') {
    html += `<button onclick="apiPost('/findings/${f.id}/reopen')">Reopen</button>`;
  }
  return html;
}

async function refresh() {
  try {
    const health = await api('/health');
    $('version').textContent = health.version || '-';

    const st = await api('/status');
    const badge = $('agentBadge');
    if (st.paused) { badge.textContent = 'paused'; badge.className = 'badge badge-paused'; }
    else { badge.textContent = 'running'; badge.className = 'badge badge-ok'; }

    const wb = $('watcherBadge');
    if (st.watcher_running) { wb.textContent = 'active'; wb.className = 'badge badge-ok'; }
    else { wb.textContent = 'stopped'; wb.className = 'badge badge-off'; }

    // Reminder banner
    try {
      const rem = await api('/findings/reminder');
      const rb = $('reminderBanner');
      if (rem.should_remind && rem.message) {
        rb.textContent = rem.message;
        rb.style.display = 'block';
      } else {
        rb.style.display = 'none';
      }
    } catch(e) { $('reminderBanner').style.display = 'none'; }

    // Summary cards
    try {
      const sum = await api('/findings/summary');
      const cards = $('summaryCards');
      const items = [
        {label:'Total', value: sum.total || 0},
        {label:'Approved', value: (sum.by_status||{}).approved || 0},
        {label:'Queued', value: (sum.by_status||{}).queued || 0},
        {label:'Violations', value: (sum.by_severity||{}).violation || 0},
        {label:'Resolved', value: (sum.by_status||{}).resolved || 0},
      ];
      cards.innerHTML = items.map(i =>
        `<div class="summary-card"><div class="label">${i.label}</div><div class="value">${i.value}</div></div>`
      ).join('');
    } catch(e) {}

    // Findings
    const statusFilter = $('statusFilter').value;
    const qp = statusFilter === 'all' ? '' : '&status=' + statusFilter;
    const findings = await api('/findings?limit=30' + qp);
    const fb = $('findingsBody');
    if (!findings.length) {
      fb.innerHTML = '<tr><td colspan="7" style="color:#8b949e">No findings</td></tr>';
    } else {
      fb.innerHTML = findings.map(f => {
        const features = (f.affected_features && f.affected_features.length)
          ? `<div class="features-list">Features: ${f.affected_features.join(', ')}</div>` : '';
        const reasoning = f.ai_reasoning
          ? `<span class="expandable" onclick="toggleExpand('${f.id}')">AI reasoning</span>
             <div id="expand-${f.id}" class="expanded-content">${f.ai_reasoning}</div>` : '';
        return `<tr>
          <td style="font-family:monospace">${f.id.slice(0,8)}</td>
          <td>${f.service}</td>
          <td class="severity-${f.severity}">${f.severity}</td>
          <td><span class="badge badge-${f.status}">${f.status}</span></td>
          <td>${f.description.slice(0,120)}${features}${reasoning}</td>
          <td>${renderAiBadge(f)}</td>
          <td class="actions">${renderActions(f)}</td>
        </tr>`;
      }).join('');
    }

    // Events
    const events = await api('/events?limit=15');
    const eb = $('eventsBody');
    if (!events.length) {
      eb.innerHTML = '<tr><td colspan="4" style="color:#8b949e">No events yet</td></tr>';
    } else {
      eb.innerHTML = events.map(e => `<tr>
        <td>${shortTime(e.timestamp)}</td>
        <td>${e.service || '-'}</td>
        <td style="font-family:monospace;font-size:.8rem">${e.path || '-'}</td>
        <td>${e.event_type || '-'}</td>
      </tr>`).join('');
    }

    // Dismiss patterns
    try {
      const patterns = await api('/decisions/patterns');
      const pb = $('patternsBody');
      if (!patterns.length) {
        pb.innerHTML = '<tr><td colspan="5" style="color:#8b949e">No patterns yet</td></tr>';
      } else {
        pb.innerHTML = patterns.map(p => `<tr>
          <td>${p.service}</td>
          <td>${p.reason}</td>
          <td>${p.count}</td>
          <td style="font-size:.8rem">${(p.example||'').slice(0,100)}</td>
          <td>${shortTime(p.last_seen)}</td>
        </tr>`).join('');
      }
    } catch(e) {}

    // Audit log
    const audit = await api('/audit-log?limit=20');
    const ab = $('auditBody');
    if (!audit.length) {
      ab.innerHTML = '<tr><td colspan="3" style="color:#8b949e">No audit entries yet</td></tr>';
    } else {
      ab.innerHTML = audit.map(a => `<tr>
        <td>${shortTime(a.timestamp)}</td>
        <td>${a.action}</td>
        <td style="font-size:.8rem">${JSON.stringify(a.details).slice(0,120)}</td>
      </tr>`).join('');
    }

    $('lastRefresh').textContent = new Date().toLocaleTimeString();
  } catch(e) {
    console.error('Refresh error', e);
  }
}

refresh();
setInterval(refresh, 10000);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Decision recording helper (bridges finding_lifecycle -> decision_learner)
# ---------------------------------------------------------------------------


def _record_decision_safe(finding_id: str, lifecycle_manager: Any, action: str, reason: str = "") -> None:
    """Record a decision in the decision learner, non-fatally."""
    try:
        from server import decision_learner
    except ImportError:
        try:
            import decision_learner  # type: ignore[no-redef]
        except ImportError:
            return

    try:
        finding = lifecycle_manager.get_finding(finding_id)
        if finding:
            decision_learner.record_decision(finding, action, reason)
    except Exception:
        logger.debug("Failed to record decision for %s", finding_id, exc_info=True)


# ---------------------------------------------------------------------------
# ControlPlane class
# ---------------------------------------------------------------------------


class ControlPlane:
    """FastAPI HTTP server for the VS Code Agent Monitor panel.

    Provides REST endpoints to inspect and control the file watcher,
    proactive auditor, and workflow manager.  Runs in a background daemon
    thread via uvicorn so it does not block the MCP server.

    Uses dependency injection — call ``set_watcher``, ``set_auditor``,
    and ``set_workflow_manager`` to wire up the live instances.
    """

    def __init__(self) -> None:
        self._watcher: Any = None  # server.watcher.FileWatcher
        self._auditor: Any = None  # server.auditor.ProactiveAuditor
        self._workflow_manager: Any = None  # server.workflows.WorkflowManager
        self._lifecycle_manager: Any = None  # server.finding_lifecycle.FindingLifecycleManager
        self._paused: bool = False
        self._lock = threading.Lock()
        self._audit_log = AuditLog()
        self._server_thread: threading.Thread | None = None
        self._uvicorn_server: Any = None  # uvicorn.Server
        self._app: Any = None  # FastAPI

    # -- Dependency injection -----------------------------------------------

    def set_watcher(self, watcher: Any) -> None:
        """Inject the FileWatcher instance."""
        with self._lock:
            self._watcher = watcher

    def set_auditor(self, auditor: Any) -> None:
        """Inject the ProactiveAuditor instance."""
        with self._lock:
            self._auditor = auditor

    def set_workflow_manager(self, wm: Any) -> None:
        """Inject the WorkflowManager instance."""
        with self._lock:
            self._workflow_manager = wm

    def set_lifecycle_manager(self, lm: Any) -> None:
        """Inject the FindingLifecycleManager instance."""
        with self._lock:
            self._lifecycle_manager = lm

    # -- Server lifecycle ---------------------------------------------------

    def start(self, port: int = 3100) -> None:
        """Start the FastAPI server in a background daemon thread.

        Args:
            port: TCP port to bind on localhost.  Defaults to 3100.
        """
        if not _FASTAPI_AVAILABLE:
            logger.error("Cannot start control plane — FastAPI/uvicorn not installed.")
            return

        if self._server_thread is not None and self._server_thread.is_alive():
            logger.warning("Control plane already running.")
            return

        self._app = self._build_app()
        config = uvicorn.Config(
            app=self._app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            # Disable signal handlers so they don't interfere with the main process
            # (we're running in a background thread).
        )
        self._uvicorn_server = uvicorn.Server(config)

        self._server_thread = threading.Thread(
            target=self._uvicorn_server.run,
            daemon=True,
            name="control-plane",
        )
        self._server_thread.start()
        logger.info("Control plane started on http://127.0.0.1:%d", port)
        self._audit_log.append("control_plane.start", {"port": port})

    def stop(self) -> None:
        """Signal the uvicorn server to shut down gracefully."""
        if self._uvicorn_server is not None:
            self._uvicorn_server.should_exit = True
            logger.info("Control plane stop requested.")
            self._audit_log.append("control_plane.stop")
        # The daemon thread will exit when the process exits or uvicorn shuts down.
        self._server_thread = None
        self._uvicorn_server = None

    # -- FastAPI app builder ------------------------------------------------

    def _build_app(self) -> FastAPI:
        """Construct the FastAPI application with all routes."""
        app = FastAPI(
            title="Agent Control Plane",
            version=__version__,
            docs_url="/docs",
            redoc_url=None,
        )

        # CORS — allow VS Code webview and any localhost origin
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "http://localhost:*",
                "http://127.0.0.1:*",
                "vscode-webview://*",
            ],
            allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # ---- Health / status ----

        @app.get("/health")
        def health() -> dict[str, str]:
            return {"status": "ok", "version": __version__}

        @app.get("/status")
        def status() -> dict[str, Any]:
            with self._lock:
                paused = self._paused
                watcher = self._watcher
                auditor = self._auditor
                wm = self._workflow_manager

            result: dict[str, Any] = {
                "version": __version__,
                "paused": paused,
                "watcher_running": False,
                "watcher_config": None,
                "auditor_stats": None,
                "workflow_summary": None,
            }

            if watcher is not None:
                result["watcher_running"] = watcher.is_running()
                result["watcher_config"] = watcher.get_config()

            if auditor is not None:
                result["auditor_stats"] = auditor.get_stats()

            if wm is not None:
                result["workflow_summary"] = wm.get_summary()

            return result

        # ---- Events ----

        @app.get("/events")
        def events(limit: int = 20) -> list[dict[str, Any]]:
            with self._lock:
                watcher = self._watcher
            if watcher is None:
                return []
            return watcher.get_recent_events(limit=min(limit, 200))

        # ---- Findings ----

        @app.get("/findings")
        def get_findings(
            service: str | None = None,
            severity: str | None = None,
            status: str | None = None,
            limit: int = 50,
        ) -> list[dict[str, Any]]:
            with self._lock:
                lm = self._lifecycle_manager
                auditor = self._auditor
            # Prefer lifecycle manager (SQLite-backed) over in-memory auditor
            if lm is not None:
                return lm.get_findings(
                    status=status or "all",
                    service=service or "",
                    severity=severity or "",
                    limit=min(limit, 200),
                )
            if auditor is not None:
                return auditor.get_findings(
                    service=service,
                    severity=severity,
                    status=status,
                    limit=min(limit, 200),
                )
            return []

        @app.get("/findings/{finding_id}")
        def get_finding(finding_id: str) -> JSONResponse:
            with self._lock:
                lm = self._lifecycle_manager
                auditor = self._auditor
            # Try lifecycle manager first
            if lm is not None:
                finding = lm.get_finding(finding_id)
                if finding is not None:
                    return JSONResponse(content=finding)
            # Fall back to auditor
            if auditor is not None:
                f = auditor._findings_by_id.get(finding_id)
                if f is not None:
                    return JSONResponse(content=f.to_dict())
            return JSONResponse(
                status_code=404,
                content={"error": f"Finding {finding_id} not found"},
            )

        @app.post("/findings/{finding_id}/approve")
        def approve_finding(finding_id: str, body: dict[str, Any] | None = None) -> JSONResponse:
            note = (body or {}).get("note", "")
            # Try lifecycle manager first, fall back to auditor
            with self._lock:
                lm = self._lifecycle_manager
                auditor = self._auditor
            ok = False
            if lm is not None:
                ok = lm.approve(finding_id, note=note)
                if ok:
                    _record_decision_safe(finding_id, lm, "approve", note)
            if not ok and auditor is not None:
                ok = auditor.approve_finding(finding_id)
            if not ok:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Finding {finding_id} not found"},
                )
            self._audit_log.append("finding.approve", {"finding_id": finding_id, "note": note})
            return JSONResponse(content={"status": "approved", "finding_id": finding_id})

        @app.post("/findings/{finding_id}/dismiss")
        def dismiss_finding(finding_id: str, body: dict[str, Any] | None = None) -> JSONResponse:
            reason = (body or {}).get("reason", "false_positive")
            with self._lock:
                lm = self._lifecycle_manager
                auditor = self._auditor
            ok = False
            if lm is not None:
                ok = lm.dismiss(finding_id, reason=reason)
                if ok:
                    _record_decision_safe(finding_id, lm, "dismiss", reason)
            if not ok and auditor is not None:
                ok = auditor.dismiss_finding(finding_id)
            if not ok:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Finding {finding_id} not found"},
                )
            self._audit_log.append("finding.dismiss", {"finding_id": finding_id, "reason": reason})
            return JSONResponse(content={"status": "dismissed", "finding_id": finding_id})

        @app.post("/findings/{finding_id}/reopen")
        def reopen_finding(finding_id: str) -> JSONResponse:
            with self._lock:
                lm = self._lifecycle_manager
            if lm is None:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Lifecycle manager not initialized"},
                )
            ok = lm.reopen(finding_id)
            if not ok:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Finding {finding_id} not found or cannot be reopened"},
                )
            self._audit_log.append("finding.reopen", {"finding_id": finding_id})
            return JSONResponse(content={"status": "approved", "finding_id": finding_id, "message": "Finding reopened"})

        @app.post("/findings/queue")
        def queue_findings(body: dict[str, Any] | None = None) -> JSONResponse:
            with self._lock:
                lm = self._lifecycle_manager
            if lm is None:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Lifecycle manager not initialized"},
                )
            body = body or {}
            finding_ids = body.get("finding_ids", [])
            service = body.get("service", "")
            if not finding_ids:
                # Queue all approved for the given service (or all)
                approved = lm.get_approved_batch(service=service)
                finding_ids = [f["id"] for f in approved]
            if not finding_ids:
                return JSONResponse(content={"status": "nothing_to_queue", "message": "No approved findings to queue"})
            results = lm.queue_for_fix(finding_ids)
            queued = sum(1 for v in results.values() if v)
            self._audit_log.append("findings.queue", {"count": queued, "ids": finding_ids[:10]})
            return JSONResponse(content={"status": "queued", "queued": queued, "total": len(finding_ids)})

        @app.get("/findings/sprint-prompt")
        def sprint_prompt(service: str = "") -> JSONResponse:
            with self._lock:
                lm = self._lifecycle_manager
            if lm is None:
                return JSONResponse(content={"prompt": "Lifecycle manager not initialized."})
            prompt = lm.get_sprint_prompt(service=service)
            return JSONResponse(content={"prompt": prompt})

        @app.get("/findings/reminder")
        def findings_reminder() -> JSONResponse:
            with self._lock:
                lm = self._lifecycle_manager
            if lm is None:
                return JSONResponse(content={"should_remind": False, "message": ""})
            return JSONResponse(
                content={
                    "should_remind": lm.should_remind(),
                    "message": lm.get_reminder_message(),
                }
            )

        @app.get("/findings/summary")
        def findings_summary() -> JSONResponse:
            with self._lock:
                lm = self._lifecycle_manager
            if lm is None:
                return JSONResponse(content={"total": 0, "by_status": {}, "by_service": {}, "by_severity": {}})
            return JSONResponse(content=lm.get_summary())

        @app.get("/decisions/patterns")
        def decision_patterns() -> list[dict[str, Any]]:
            try:
                from server import decision_learner
            except ImportError:
                try:
                    import decision_learner  # type: ignore[no-redef]
                except ImportError:
                    return []
            return decision_learner.get_dismiss_patterns()

        # ---- Watcher control ----

        @app.post("/watcher/start")
        def watcher_start(body: dict[str, Any] | None = None) -> JSONResponse:
            with self._lock:
                watcher = self._watcher
            if watcher is None:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Watcher not initialized"},
                )
            config_path = (body or {}).get("config_path", "watcher-config.json")
            try:
                ok = watcher.start(config_path)
            except Exception as exc:
                logger.exception("Failed to start watcher")
                return JSONResponse(
                    status_code=500,
                    content={"error": str(exc)},
                )
            self._audit_log.append("watcher.start", {"config_path": config_path, "result": ok})
            return JSONResponse(
                content={
                    "status": "started" if ok else "already_running",
                    "message": "Watcher started" if ok else "Watcher was already running",
                },
            )

        @app.post("/watcher/stop")
        def watcher_stop() -> JSONResponse:
            with self._lock:
                watcher = self._watcher
            if watcher is None:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Watcher not initialized"},
                )
            watcher.stop()
            self._audit_log.append("watcher.stop")
            return JSONResponse(content={"status": "stopped", "message": "Watcher stopped"})

        @app.get("/watcher/status")
        def watcher_status() -> dict[str, Any]:
            with self._lock:
                watcher = self._watcher
            if watcher is None:
                return {"running": False, "initialized": False}
            return {
                "running": watcher.is_running(),
                "initialized": True,
                "config": watcher.get_config(),
            }

        # ---- Assign / Pause / Resume ----

        @app.post("/assign")
        def assign_service(body: dict[str, Any]) -> JSONResponse:
            service = body.get("service", "")
            mode = body.get("mode", "validate")
            if not service:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Missing 'service' in request body"},
                )
            self._audit_log.append("assign", {"service": service, "mode": mode})
            # The actual assignment logic is delegated to the watcher/workflow
            # manager.  For now we log it and acknowledge.
            return JSONResponse(
                content={
                    "status": "assigned",
                    "service": service,
                    "mode": mode,
                    "message": f"Service '{service}' assigned for {mode}",
                },
            )

        @app.post("/pause")
        def pause() -> JSONResponse:
            with self._lock:
                self._paused = True
            self._audit_log.append("pause")
            return JSONResponse(content={"status": "paused", "message": "Monitoring paused"})

        @app.post("/resume")
        def resume() -> JSONResponse:
            with self._lock:
                self._paused = False
            self._audit_log.append("resume")
            return JSONResponse(content={"status": "running", "message": "Monitoring resumed"})

        # ---- Audit log ----

        @app.get("/audit-log")
        def audit_log(limit: int = 50) -> list[dict[str, Any]]:
            return self._audit_log.get(limit=min(limit, 500))

        # ---- Dashboard ----

        @app.get("/dashboard", response_class=HTMLResponse)
        def dashboard() -> HTMLResponse:
            return HTMLResponse(content=_DASHBOARD_HTML)

        return app


# ---------------------------------------------------------------------------
# Module-level singleton (mirrors the pattern in watcher.py)
# ---------------------------------------------------------------------------

_instance: ControlPlane | None = None


def get_control_plane() -> ControlPlane:
    """Return (or create) the module-level ControlPlane singleton."""
    global _instance
    if _instance is None:
        _instance = ControlPlane()
    return _instance
