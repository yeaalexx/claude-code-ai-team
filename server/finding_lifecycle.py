"""
Finding Lifecycle Manager — v6.0

Manages the full lifecycle of audit findings from detection to resolution.
States: detected -> ai_analyzed -> user_decided -> queued -> in_progress -> fix_proposed -> verified -> resolved
Also handles: dismissed findings with categorized reasons.

Persistence: SQLite database at ~/.claude-mcp-servers/multi-ai-collab/memory/findings.db
"""

import enum
import json
import logging
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FindingStatus(enum.Enum):
    """States in the finding lifecycle."""

    DETECTED = "detected"
    AI_ANALYZED = "ai_analyzed"
    APPROVED = "approved"
    DISMISSED = "dismissed"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    FIX_PROPOSED = "fix_proposed"
    VERIFIED = "verified"
    RESOLVED = "resolved"


class DismissReason(enum.Enum):
    """Categorized reasons for dismissing a finding."""

    FALSE_POSITIVE = "false_positive"
    TEST_CODE = "test_code"
    DOCS_ONLY = "docs_only"
    VENDOR_CODE = "vendor_code"
    INTENTIONAL = "intentional"
    DUPLICATE = "duplicate"


# Valid state transitions (from -> set of allowed to-states)
_VALID_TRANSITIONS: dict[FindingStatus, set[FindingStatus]] = {
    FindingStatus.DETECTED: {FindingStatus.AI_ANALYZED, FindingStatus.APPROVED, FindingStatus.DISMISSED},
    FindingStatus.AI_ANALYZED: {FindingStatus.APPROVED, FindingStatus.DISMISSED},
    FindingStatus.APPROVED: {FindingStatus.QUEUED, FindingStatus.DISMISSED},
    FindingStatus.DISMISSED: {FindingStatus.APPROVED},  # reopen
    FindingStatus.QUEUED: {FindingStatus.IN_PROGRESS, FindingStatus.APPROVED},  # un-queue
    FindingStatus.IN_PROGRESS: {FindingStatus.FIX_PROPOSED, FindingStatus.QUEUED},  # back to queue
    FindingStatus.FIX_PROPOSED: {FindingStatus.VERIFIED, FindingStatus.IN_PROGRESS},  # reject fix
    FindingStatus.VERIFIED: {FindingStatus.RESOLVED, FindingStatus.FIX_PROPOSED},  # verification failed
    FindingStatus.RESOLVED: set(),  # terminal state
}


@dataclass
class FindingRecord:
    """A finding with full lifecycle state."""

    id: str
    service: str
    file: str
    line: int | None
    severity: str
    description: str
    contract_reference: str
    status: str = FindingStatus.DETECTED.value
    ai_recommendation: str = ""
    ai_confidence: float = 0.0
    ai_reasoning: str = ""
    affected_features: list[str] = field(default_factory=list)
    dismiss_reason: str = ""
    created_at: str = ""
    updated_at: str = ""
    resolved_at: str = ""
    fix_branch: str = ""
    fix_diff: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        return d


_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    service TEXT NOT NULL,
    file TEXT NOT NULL DEFAULT '',
    line INTEGER,
    severity TEXT NOT NULL DEFAULT 'info',
    description TEXT NOT NULL DEFAULT '',
    contract_reference TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'detected',
    ai_recommendation TEXT NOT NULL DEFAULT '',
    ai_confidence REAL NOT NULL DEFAULT 0.0,
    ai_reasoning TEXT NOT NULL DEFAULT '',
    affected_features TEXT NOT NULL DEFAULT '[]',
    dismiss_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT NOT NULL DEFAULT '',
    fix_branch TEXT NOT NULL DEFAULT '',
    fix_diff TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS finding_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    timestamp TEXT NOT NULL,
    FOREIGN KEY(finding_id) REFERENCES findings(id)
);

CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status);
CREATE INDEX IF NOT EXISTS idx_findings_service ON findings(service);
CREATE INDEX IF NOT EXISTS idx_findings_severity ON findings(severity);
CREATE INDEX IF NOT EXISTS idx_decisions_finding_id ON finding_decisions(finding_id);
"""


class FindingLifecycleManager:
    """Manages the full lifecycle of audit findings with SQLite persistence.

    Thread-safe via SQLite's built-in locking. Each method opens its own
    connection (or reuses a cached one) so callers don't need to manage
    transactions.
    """

    def __init__(self) -> None:
        self._db_path: Path | None = None
        self._initialized: bool = False

    def initialize(self, db_path: Path | None = None) -> None:
        """Create SQLite DB and tables if they don't exist.

        Args:
            db_path: Path to the SQLite database file. If None, uses
                the default location under ~/.claude-mcp-servers/multi-ai-collab/memory/.
        """
        if db_path is None:
            base = Path.home() / ".claude-mcp-servers" / "multi-ai-collab" / "memory"
            base.mkdir(parents=True, exist_ok=True)
            db_path = base / "findings.db"

        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.executescript(_CREATE_TABLES_SQL)
            conn.commit()
        finally:
            conn.close()

        self._initialized = True
        logger.info("Finding lifecycle DB initialized at %s", self._db_path)

    def _conn(self) -> sqlite3.Connection:
        """Get a SQLite connection. Raises if not initialized."""
        if not self._initialized or self._db_path is None:
            raise RuntimeError("FindingLifecycleManager not initialized — call initialize() first")
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def add_finding(self, finding: dict[str, Any]) -> str:
        """Insert a new finding into the database.

        Args:
            finding: Dictionary with finding fields. At minimum: service, description.
                Missing fields get defaults.

        Returns:
            The finding ID (first 8 chars of a UUID).
        """
        finding_id = finding.get("id", str(uuid.uuid4())[:8])
        now = datetime.now(timezone.utc).isoformat()

        affected = finding.get("affected_features", [])
        if isinstance(affected, list):
            affected_json = json.dumps(affected)
        else:
            affected_json = str(affected)

        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO findings
                   (id, service, file, line, severity, description, contract_reference,
                    status, ai_recommendation, ai_confidence, ai_reasoning,
                    affected_features, dismiss_reason, created_at, updated_at,
                    resolved_at, fix_branch, fix_diff)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    finding_id,
                    finding.get("service", ""),
                    finding.get("file", finding.get("file_path", "")),
                    finding.get("line", finding.get("line_number")),
                    finding.get("severity", "info"),
                    finding.get("description", ""),
                    finding.get("contract_reference", ""),
                    finding.get("status", FindingStatus.DETECTED.value),
                    finding.get("ai_recommendation", ""),
                    finding.get("ai_confidence", 0.0),
                    finding.get("ai_reasoning", ""),
                    affected_json,
                    finding.get("dismiss_reason", ""),
                    finding.get("created_at", now),
                    now,
                    "",
                    "",
                    "",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        logger.debug("Added finding %s for service=%s", finding_id, finding.get("service", ""))
        return finding_id

    def update_status(self, finding_id: str, new_status: FindingStatus, **kwargs: Any) -> bool:
        """Transition a finding to a new status with validation.

        Args:
            finding_id: The finding ID.
            new_status: Target status.
            **kwargs: Additional fields to update (e.g., dismiss_reason, fix_branch).

        Returns:
            True if the transition was valid and applied.
        """
        conn = self._conn()
        try:
            row = conn.execute("SELECT status FROM findings WHERE id = ?", (finding_id,)).fetchone()
            if row is None:
                logger.warning("Finding %s not found", finding_id)
                return False

            current = FindingStatus(row["status"])
            if new_status not in _VALID_TRANSITIONS.get(current, set()):
                logger.warning(
                    "Invalid transition for %s: %s -> %s",
                    finding_id,
                    current.value,
                    new_status.value,
                )
                return False

            now = datetime.now(timezone.utc).isoformat()
            updates = ["status = ?", "updated_at = ?"]
            params: list[Any] = [new_status.value, now]

            if new_status == FindingStatus.RESOLVED:
                updates.append("resolved_at = ?")
                params.append(now)

            for key in (
                "dismiss_reason",
                "fix_branch",
                "fix_diff",
                "ai_recommendation",
                "ai_confidence",
                "ai_reasoning",
            ):
                if key in kwargs:
                    updates.append(f"{key} = ?")
                    params.append(kwargs[key])

            params.append(finding_id)
            conn.execute(f"UPDATE findings SET {', '.join(updates)} WHERE id = ?", params)

            # Record the decision
            action = new_status.value
            reason = kwargs.get("reason", kwargs.get("dismiss_reason", ""))
            conn.execute(
                "INSERT INTO finding_decisions (finding_id, action, reason, timestamp) VALUES (?, ?, ?, ?)",
                (finding_id, action, reason, now),
            )
            conn.commit()
        finally:
            conn.close()

        logger.info("Finding %s transitioned to %s", finding_id, new_status.value)
        return True

    def approve(self, finding_id: str, note: str = "") -> bool:
        """Approve a finding (user confirms it as a real issue).

        Args:
            finding_id: The finding ID.
            note: Optional note about why it was approved.

        Returns:
            True if successful.
        """
        return self.update_status(finding_id, FindingStatus.APPROVED, reason=note)

    def dismiss(self, finding_id: str, reason: DismissReason | str = DismissReason.FALSE_POSITIVE) -> bool:
        """Dismiss a finding with a categorized reason.

        Args:
            finding_id: The finding ID.
            reason: Why the finding is being dismissed.

        Returns:
            True if successful.
        """
        if isinstance(reason, DismissReason):
            reason_val = reason.value
        else:
            reason_val = reason

        return self.update_status(finding_id, FindingStatus.DISMISSED, dismiss_reason=reason_val)

    def reopen(self, finding_id: str) -> bool:
        """Reopen a previously dismissed finding.

        Args:
            finding_id: The finding ID.

        Returns:
            True if successful.
        """
        return self.update_status(finding_id, FindingStatus.APPROVED, reason="reopened")

    def queue_for_fix(self, finding_ids: list[str]) -> dict[str, bool]:
        """Batch queue approved findings for sprint fix.

        Args:
            finding_ids: List of finding IDs to queue.

        Returns:
            Dict mapping finding_id -> success boolean.
        """
        results: dict[str, bool] = {}
        for fid in finding_ids:
            results[fid] = self.update_status(fid, FindingStatus.QUEUED)
        return results

    def mark_fix_proposed(self, finding_id: str, fix_branch: str = "", fix_diff: str = "") -> bool:
        """Mark that a fix has been proposed for this finding.

        Args:
            finding_id: The finding ID.
            fix_branch: Git branch name with the fix.
            fix_diff: The diff of the fix.

        Returns:
            True if successful.
        """
        return self.update_status(
            finding_id,
            FindingStatus.FIX_PROPOSED,
            fix_branch=fix_branch,
            fix_diff=fix_diff,
        )

    def mark_verified(self, finding_id: str) -> bool:
        """Mark a finding as verified (re-audit confirms fix works).

        Args:
            finding_id: The finding ID.

        Returns:
            True if successful.
        """
        return self.update_status(finding_id, FindingStatus.VERIFIED)

    def mark_resolved(self, finding_id: str) -> bool:
        """Mark a finding as resolved (merged and done).

        Args:
            finding_id: The finding ID.

        Returns:
            True if successful.
        """
        return self.update_status(finding_id, FindingStatus.RESOLVED)

    def get_findings(
        self,
        status: str = "all",
        service: str = "",
        feature: str = "",
        severity: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query findings with optional filters.

        Args:
            status: Filter by status, or "all" for everything.
            service: Filter by service name.
            feature: Filter by affected feature (substring match in JSON array).
            severity: Filter by severity level.
            limit: Maximum number of results.

        Returns:
            List of finding dictionaries, most recent first.
        """
        conn = self._conn()
        try:
            clauses: list[str] = []
            params: list[Any] = []

            if status != "all":
                clauses.append("status = ?")
                params.append(status)
            if service:
                clauses.append("service = ?")
                params.append(service)
            if feature:
                clauses.append("affected_features LIKE ?")
                params.append(f"%{feature}%")
            if severity:
                clauses.append("severity = ?")
                params.append(severity)

            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(min(limit, 500))

            rows = conn.execute(
                f"SELECT * FROM findings{where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()

            results = []
            for row in rows:
                d = dict(row)
                # Parse affected_features from JSON string
                try:
                    d["affected_features"] = json.loads(d.get("affected_features", "[]"))
                except (json.JSONDecodeError, TypeError):
                    d["affected_features"] = []
                results.append(d)

            return results
        finally:
            conn.close()

    def get_finding(self, finding_id: str) -> dict[str, Any] | None:
        """Get a single finding by ID.

        Args:
            finding_id: The finding ID.

        Returns:
            Finding dict or None if not found.
        """
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()
            if row is None:
                return None
            d = dict(row)
            try:
                d["affected_features"] = json.loads(d.get("affected_features", "[]"))
            except (json.JSONDecodeError, TypeError):
                d["affected_features"] = []
            return d
        finally:
            conn.close()

    def get_decisions(self, finding_id: str) -> list[dict[str, Any]]:
        """Get the decision history for a finding.

        Args:
            finding_id: The finding ID.

        Returns:
            List of decision dicts ordered by timestamp.
        """
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM finding_decisions WHERE finding_id = ? ORDER BY timestamp",
                (finding_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_summary(self) -> dict[str, Any]:
        """Get aggregate counts by status, service, and severity.

        Returns:
            Summary dictionary with counts.
        """
        conn = self._conn()
        try:
            by_status: dict[str, int] = {}
            for row in conn.execute("SELECT status, COUNT(*) as cnt FROM findings GROUP BY status"):
                by_status[row["status"]] = row["cnt"]

            by_service: dict[str, int] = {}
            for row in conn.execute("SELECT service, COUNT(*) as cnt FROM findings GROUP BY service"):
                by_service[row["service"]] = row["cnt"]

            by_severity: dict[str, int] = {}
            for row in conn.execute("SELECT severity, COUNT(*) as cnt FROM findings GROUP BY severity"):
                by_severity[row["severity"]] = row["cnt"]

            total = conn.execute("SELECT COUNT(*) as cnt FROM findings").fetchone()

            return {
                "total": total["cnt"] if total else 0,
                "by_status": by_status,
                "by_service": by_service,
                "by_severity": by_severity,
            }
        finally:
            conn.close()

    def get_approved_batch(self, service: str = "") -> list[dict[str, Any]]:
        """Get all approved findings ready for fixing.

        Args:
            service: Optionally filter by service.

        Returns:
            List of approved finding dicts.
        """
        return self.get_findings(status=FindingStatus.APPROVED.value, service=service)

    def get_sprint_prompt(self, service: str = "") -> str:
        """Generate a prompt for Claude to fix approved/queued findings.

        Args:
            service: Optionally focus on one service.

        Returns:
            Formatted prompt string.
        """
        approved = self.get_findings(status=FindingStatus.APPROVED.value, service=service)
        queued = self.get_findings(status=FindingStatus.QUEUED.value, service=service)
        findings = approved + queued

        if not findings:
            return "No approved or queued findings to fix."

        # Group by service
        by_service: dict[str, list[dict[str, Any]]] = {}
        for f in findings:
            svc = f.get("service", "unknown")
            by_service.setdefault(svc, []).append(f)

        lines = [
            f"# Fix {len(findings)} Approved Findings",
            "",
            "The following findings have been reviewed and approved for fixing.",
            "Fix each one, verify the fix, and mark as resolved.",
            "",
        ]

        for svc, svc_findings in sorted(by_service.items()):
            lines.append(f"## Service: {svc} ({len(svc_findings)} findings)")
            lines.append("")
            for f in svc_findings:
                lines.append(f"### [{f['id']}] {f['severity'].upper()} — {f['description'][:120]}")
                if f.get("file"):
                    loc = f["file"]
                    if f.get("line"):
                        loc += f":{f['line']}"
                    lines.append(f"- **Location**: `{loc}`")
                if f.get("contract_reference"):
                    lines.append(f"- **Contract**: {f['contract_reference']}")
                if f.get("ai_recommendation"):
                    lines.append(f"- **AI Recommendation**: {f['ai_recommendation']}")
                lines.append("")

        return "\n".join(lines)

    def should_remind(self) -> bool:
        """Check if the user should be reminded about pending findings.

        Returns True if there are >5 approved findings or approved findings
        older than 3 days.

        Returns:
            True if a reminder is appropriate.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM findings WHERE status = ?",
                (FindingStatus.APPROVED.value,),
            ).fetchone()
            count = row["cnt"] if row else 0

            if count > 5:
                return True

            # Check for approved findings older than 3 days
            row = conn.execute(
                """SELECT COUNT(*) as cnt FROM findings
                   WHERE status = ? AND created_at < datetime('now', '-3 days')""",
                (FindingStatus.APPROVED.value,),
            ).fetchone()
            old_count = row["cnt"] if row else 0

            return old_count > 0
        finally:
            conn.close()

    def get_reminder_message(self) -> str:
        """Generate a reminder message about pending findings.

        Returns:
            Human-readable reminder string.
        """
        if not self.should_remind():
            return ""

        summary = self.get_summary()
        approved = summary["by_status"].get("approved", 0)
        queued = summary["by_status"].get("queued", 0)

        # Count violations among approved
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM findings WHERE status = ? AND severity = 'violation'",
                (FindingStatus.APPROVED.value,),
            ).fetchone()
            violations = row["cnt"] if row else 0
        finally:
            conn.close()

        parts = [f"You have {approved} approved finding(s)"]
        if queued:
            parts.append(f" and {queued} queued for fix")
        parts.append(".")
        if violations:
            parts.append(f" {violations} are contract violations.")
        parts.append(" Run the sprint fix prompt to address them.")

        return "".join(parts)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: FindingLifecycleManager | None = None


def get_lifecycle_manager() -> FindingLifecycleManager:
    """Return (or create) the module-level FindingLifecycleManager singleton."""
    global _instance
    if _instance is None:
        _instance = FindingLifecycleManager()
    return _instance
