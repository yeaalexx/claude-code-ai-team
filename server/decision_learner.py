"""
Decision Learner — v6.0

Learns from user approve/dismiss decisions to improve future recommendations.
Tracks patterns: if similar findings keep getting dismissed, auto-suppress.
Feeds decision context back into ChromaDB RAG for future AI analysis.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# In-memory decision history (supplements SQLite finding_decisions table)
_decision_history: list[dict[str, Any]] = []
_MAX_HISTORY = 500


def record_decision(finding: dict[str, Any], action: str, reason: str = "") -> None:
    """Store a decision in the local history and optionally in ChromaDB RAG.

    Args:
        finding: The finding dict that was acted upon.
        action: The action taken (e.g., "approve", "dismiss").
        reason: Optional reason for the action.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "finding_id": finding.get("id", ""),
        "service": finding.get("service", ""),
        "severity": finding.get("severity", ""),
        "description": finding.get("description", ""),
        "file": finding.get("file", finding.get("file_path", "")),
        "contract_reference": finding.get("contract_reference", ""),
        "action": action,
        "reason": reason,
    }

    _decision_history.append(entry)
    # Trim to bounded size
    while len(_decision_history) > _MAX_HISTORY:
        _decision_history.pop(0)

    logger.debug("Recorded decision: %s on %s (%s)", action, finding.get("id", "?"), reason)

    # Try to store in RAG for semantic search
    _store_in_rag(entry)


def _store_in_rag(entry: dict[str, Any]) -> None:
    """Attempt to store a decision in ChromaDB RAG for semantic retrieval."""
    try:
        import rag_memory  # type: ignore[import-untyped]

        content = (
            f"Decision: {entry['action']} on {entry['severity']} finding in {entry['service']}. "
            f"Description: {entry['description'][:200]}. "
            f"Reason: {entry.get('reason', 'none')}."
        )
        rag_memory.add_learning(
            source="decision_learner",
            category="finding_decision",
            content=content,
            project="",
            confidence=0.85,
        )
    except Exception:
        pass  # RAG is optional


def get_similar_decisions(finding: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    """Find past decisions on similar findings.

    Uses RAG semantic search if available, otherwise falls back to keyword matching.

    Args:
        finding: The finding to match against.
        limit: Maximum number of similar decisions to return.

    Returns:
        List of past decision dicts with similarity context.
    """
    # Try RAG semantic search first
    similar = _search_rag(finding, limit)
    if similar:
        return similar

    # Fallback: keyword matching on in-memory history
    return _keyword_match(finding, limit)


def _search_rag(finding: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """Search ChromaDB for similar past decisions."""
    try:
        import rag_memory  # type: ignore[import-untyped]

        query = (
            f"{finding.get('severity', '')} finding in {finding.get('service', '')}: "
            f"{finding.get('description', '')[:200]}"
        )
        results = rag_memory.query(query, n_results=limit, category="finding_decision")
        if results and isinstance(results, list):
            return [
                {"source": "rag", "content": r.get("content", ""), "distance": r.get("distance", 1.0)} for r in results
            ]
    except Exception:
        pass
    return []


def _keyword_match(finding: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """Match findings by service, severity, and description keywords."""
    if not _decision_history:
        return []

    service = finding.get("service", "")
    severity = finding.get("severity", "")
    desc_words = set(finding.get("description", "").lower().split())

    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in _decision_history:
        score = 0.0
        if entry.get("service") == service:
            score += 2.0
        if entry.get("severity") == severity:
            score += 1.0
        # Word overlap in description
        entry_words = set(entry.get("description", "").lower().split())
        overlap = len(desc_words & entry_words)
        if desc_words:
            score += overlap / len(desc_words) * 3.0

        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"source": "keyword", "score": s, **e} for s, e in scored[:limit]]


def should_auto_suppress(finding: dict[str, Any]) -> bool:
    """Check if a finding should be auto-suppressed based on past dismiss patterns.

    If >3 similar findings were dismissed with the same reason, suggest suppression.

    Args:
        finding: The finding to check.

    Returns:
        True if the finding matches a strong dismiss pattern.
    """
    service = finding.get("service", "")
    severity = finding.get("severity", "")
    desc_lower = finding.get("description", "").lower()

    dismiss_count = 0
    for entry in _decision_history:
        if entry.get("action") != "dismiss":
            continue
        if entry.get("service") != service:
            continue
        if entry.get("severity") != severity:
            continue
        # Check description similarity (simple word overlap)
        entry_desc = entry.get("description", "").lower()
        entry_words = set(entry_desc.split())
        finding_words = set(desc_lower.split())
        if finding_words and entry_words:
            overlap = len(finding_words & entry_words) / max(len(finding_words), 1)
            if overlap > 0.5:
                dismiss_count += 1

    return dismiss_count >= 3


def get_dismiss_patterns() -> list[dict[str, Any]]:
    """Summarize common dismiss patterns.

    Returns:
        List of pattern dicts with service, reason, count, and example.
    """
    # Group dismissals by (service, reason)
    dismiss_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for entry in _decision_history:
        if entry.get("action") != "dismiss":
            continue
        key = (entry.get("service", "unknown"), entry.get("reason", "unknown"))
        dismiss_groups.setdefault(key, []).append(entry)

    patterns: list[dict[str, Any]] = []
    for (service, reason), entries in sorted(dismiss_groups.items(), key=lambda x: len(x[1]), reverse=True):
        if len(entries) < 2:
            continue  # Not a pattern yet
        patterns.append(
            {
                "service": service,
                "reason": reason,
                "count": len(entries),
                "example": entries[0].get("description", "")[:120],
                "last_seen": entries[-1].get("timestamp", ""),
            }
        )

    return patterns


def enrich_with_history(finding: dict[str, Any]) -> dict[str, Any]:
    """Add historical context to a finding based on past decisions.

    Adds "similar_past_decisions" and "auto_suppress_suggested" fields.

    Args:
        finding: The finding dict to enrich.

    Returns:
        The enriched finding dict (modified in place and returned).
    """
    similar = get_similar_decisions(finding, limit=3)
    finding["similar_past_decisions"] = similar
    finding["auto_suppress_suggested"] = should_auto_suppress(finding)
    return finding


def load_history_from_db(db_path: Path) -> int:
    """Load decision history from the SQLite findings database.

    Populates the in-memory history from the finding_decisions table.
    Call this after FindingLifecycleManager.initialize() to seed the learner.

    Args:
        db_path: Path to the findings.db SQLite file.

    Returns:
        Number of decisions loaded.
    """
    import sqlite3

    if not db_path.exists():
        return 0

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT fd.*, f.service, f.severity, f.description, f.file, f.contract_reference
               FROM finding_decisions fd
               LEFT JOIN findings f ON fd.finding_id = f.id
               ORDER BY fd.timestamp DESC
               LIMIT ?""",
            (_MAX_HISTORY,),
        ).fetchall()
        conn.close()

        count = 0
        for row in reversed(rows):  # Oldest first
            entry = {
                "timestamp": row["timestamp"],
                "finding_id": row["finding_id"],
                "service": row["service"] or "",
                "severity": row["severity"] or "",
                "description": row["description"] or "",
                "file": row["file"] or "",
                "contract_reference": row["contract_reference"] or "",
                "action": row["action"],
                "reason": row["reason"] or "",
            }
            _decision_history.append(entry)
            count += 1

        # Trim
        while len(_decision_history) > _MAX_HISTORY:
            _decision_history.pop(0)

        logger.info("Loaded %d decisions from %s", count, db_path)
        return count
    except Exception:
        logger.exception("Failed to load decision history from %s", db_path)
        return 0
