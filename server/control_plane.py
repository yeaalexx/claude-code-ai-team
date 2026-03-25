"""
Agent Control Plane — v5.0

FastAPI HTTP server running alongside the MCP server (in a background thread).
Provides REST endpoints for the VS Code Agent Monitor panel and external tooling.

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

__version__ = "5.0.0"

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
<title>Agent Control Plane — Dashboard</title>
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
  .controls{display:flex;gap:.5rem;flex-wrap:wrap;margin:.75rem 0}
  button{padding:6px 14px;border:1px solid #30363d;border-radius:6px;background:#21262d;
         color:#c9d1d9;cursor:pointer;font-size:.85rem}
  button:hover{background:#30363d}
  button.primary{background:#238636;border-color:#238636;color:#fff}
  button.danger{background:#da3633;border-color:#da3633;color:#fff}
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
</style>
</head>
<body>
<h1>Agent Control Plane</h1>

<div class="status-bar">
  <span>Status: <span id="agentBadge" class="badge badge-off">loading</span></span>
  <span>Watcher: <span id="watcherBadge" class="badge badge-off">unknown</span></span>
  <span class="meta">Version: <span id="version">-</span></span>
  <span class="meta">Last refresh: <span id="lastRefresh">-</span></span>
</div>

<div class="controls">
  <button class="primary" onclick="apiPost('/watcher/start',{})">Start Watcher</button>
  <button class="danger" onclick="apiPost('/watcher/stop')">Stop Watcher</button>
  <button onclick="apiPost('/pause')">Pause</button>
  <button onclick="apiPost('/resume')">Resume</button>
  <button onclick="refresh()">Refresh Now</button>
</div>

<h2>Pending Findings</h2>
<table>
<thead><tr><th>ID</th><th>Service</th><th>Severity</th><th>Description</th><th>Actions</th></tr></thead>
<tbody id="findingsBody"><tr><td colspan="5">Loading…</td></tr></tbody>
</table>

<h2>Recent Events</h2>
<table>
<thead><tr><th>Time</th><th>Service</th><th>Path</th><th>Type</th></tr></thead>
<tbody id="eventsBody"><tr><td colspan="4">Loading…</td></tr></tbody>
</table>

<h2>Audit Log (last 20)</h2>
<table>
<thead><tr><th>Time</th><th>Action</th><th>Details</th></tr></thead>
<tbody id="auditBody"><tr><td colspan="3">Loading…</td></tr></tbody>
</table>

<div id="toast"></div>

<script>
const BASE = location.origin;
const $ = s => document.getElementById(s);

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

async function refresh() {
  try {
    // Health
    const health = await api('/health');
    $('version').textContent = health.version || '-';

    // Status
    const st = await api('/status');
    const badge = $('agentBadge');
    if (st.paused) { badge.textContent = 'paused'; badge.className = 'badge badge-paused'; }
    else { badge.textContent = 'running'; badge.className = 'badge badge-ok'; }

    const wb = $('watcherBadge');
    if (st.watcher_running) { wb.textContent = 'active'; wb.className = 'badge badge-ok'; }
    else { wb.textContent = 'stopped'; wb.className = 'badge badge-off'; }

    // Findings
    const findings = await api('/findings?status=pending&limit=20');
    const fb = $('findingsBody');
    if (!findings.length) {
      fb.innerHTML = '<tr><td colspan="5" style="color:#8b949e">No pending findings</td></tr>';
    } else {
      fb.innerHTML = findings.map(f => `<tr>
        <td style="font-family:monospace">${f.id.slice(0,8)}</td>
        <td>${f.service}</td>
        <td class="severity-${f.severity}">${f.severity}</td>
        <td>${f.description.slice(0,120)}</td>
        <td class="actions">
          <button class="primary" onclick="apiPost('/findings/${f.id}/approve')">Approve</button>
          <button onclick="apiPost('/findings/${f.id}/dismiss')">Dismiss</button>
        </td>
      </tr>`).join('');
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

// Initial load + auto-refresh every 10s
refresh();
setInterval(refresh, 10000);
</script>
</body>
</html>"""


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
                auditor = self._auditor
            if auditor is None:
                return []
            return auditor.get_findings(
                service=service,
                severity=severity,
                status=status,
                limit=min(limit, 200),
            )

        @app.get("/findings/{finding_id}")
        def get_finding(finding_id: str) -> JSONResponse:
            with self._lock:
                auditor = self._auditor
            if auditor is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": "Auditor not initialized"},
                )
            # Access the internal lookup dict
            finding = auditor._findings_by_id.get(finding_id)
            if finding is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Finding {finding_id} not found"},
                )
            return JSONResponse(content=finding.to_dict())

        @app.post("/findings/{finding_id}/approve")
        def approve_finding(finding_id: str) -> JSONResponse:
            with self._lock:
                auditor = self._auditor
            if auditor is None:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Auditor not initialized"},
                )
            ok = auditor.approve_finding(finding_id)
            if not ok:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Finding {finding_id} not found"},
                )
            self._audit_log.append("finding.approve", {"finding_id": finding_id})
            return JSONResponse(content={"status": "approved", "finding_id": finding_id})

        @app.post("/findings/{finding_id}/dismiss")
        def dismiss_finding(finding_id: str) -> JSONResponse:
            with self._lock:
                auditor = self._auditor
            if auditor is None:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Auditor not initialized"},
                )
            ok = auditor.dismiss_finding(finding_id)
            if not ok:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Finding {finding_id} not found"},
                )
            self._audit_log.append("finding.dismiss", {"finding_id": finding_id})
            return JSONResponse(content={"status": "dismissed", "finding_id": finding_id})

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
