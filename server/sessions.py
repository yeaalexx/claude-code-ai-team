"""
Collaboration Session Management.

Manages multi-turn Claude<->Grok conversation sessions with:
- Session state tracking (in-memory, with disk persistence on end)
- Consensus detection via structured [STATUS] markers
- Session transcript archiving
"""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Session storage
ACTIVE_SESSIONS: dict[str, dict[str, Any]] = {}

# Sessions archive directory (set by initialize())
SESSIONS_DIR: Path | None = None


def initialize(base_dir: Path) -> None:
    """Initialize sessions system."""
    global SESSIONS_DIR
    SESSIONS_DIR = base_dir / "memory" / "sessions"
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def create_session(task: str, project: str = "", context: str = "") -> str:
    """Create a new collaboration session. Returns session_id."""
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    session = {
        "id": session_id,
        "created": datetime.now(timezone.utc).isoformat(),
        "project": project,
        "task": task,
        "context": context,
        "history": [],  # OpenAI-format messages (excluding system prompt)
        "turn_count": 0,
        "status": "active",
        "consecutive_agrees": 0,
        "consecutive_disagrees": 0,
        "last_disagree_topic": "",
    }
    ACTIVE_SESSIONS[session_id] = session
    return session_id


def get_session(session_id: str) -> dict[str, Any] | None:
    """Get an active session by ID."""
    return ACTIVE_SESSIONS.get(session_id)


def add_turn(session_id: str, role: str, content: str) -> None:
    """
    Add a conversation turn to a session.
    role: "user" (Claude's messages) or "assistant" (Grok's responses)
    """
    session = ACTIVE_SESSIONS.get(session_id)
    if session is None:
        raise ValueError(f"Session {session_id} not found")

    session["history"].append({"role": role, "content": content})
    if role == "assistant":
        session["turn_count"] += 1


def get_history(session_id: str) -> list[dict[str, str]]:
    """Get the conversation history for a session (for API calls)."""
    session = ACTIVE_SESSIONS.get(session_id)
    if session is None:
        return []
    return list(session["history"])


def detect_consensus(session_id: str, grok_response: str) -> str:
    """
    Analyze Grok's response for consensus markers.
    Updates session state and returns the current status.

    Expected format from Grok:
        [STATUS: AGREE]
        [STATUS: DISAGREE reason="..."]
        [STATUS: PARTIAL agree="..." disagree="..."]
        [STATUS: PROPOSAL]
        [STATUS: NEED_INFO question="..."]
    """
    session = ACTIVE_SESSIONS.get(session_id)
    if session is None:
        return "error"

    status_match = re.search(
        r"\[STATUS:\s*(AGREE|DISAGREE|PARTIAL|PROPOSAL|NEED_INFO)(?:\s+[^\]]*)?\]", grok_response, re.IGNORECASE
    )

    if not status_match:
        # No status marker — treat as ongoing
        return session["status"]

    status_type = status_match.group(1).upper()

    if status_type == "AGREE":
        session["consecutive_agrees"] += 1
        session["consecutive_disagrees"] = 0
        if session["consecutive_agrees"] >= 2:
            session["status"] = "consensus"
        else:
            session["status"] = "active"

    elif status_type == "DISAGREE":
        session["consecutive_agrees"] = 0
        session["consecutive_disagrees"] += 1
        # Extract reason if present
        reason_match = re.search(r'reason=["\']([^"\']*)["\']', status_match.group(0))
        topic = reason_match.group(1) if reason_match else ""
        if session["consecutive_disagrees"] >= 3 and (not topic or topic == session.get("last_disagree_topic", "")):
            session["status"] = "persistent_disagreement"
        else:
            session["status"] = "active"
        session["last_disagree_topic"] = topic

    elif status_type == "PARTIAL":
        # Partial agreement — reset both counters, keep active
        session["consecutive_agrees"] = 0
        session["consecutive_disagrees"] = 0
        session["status"] = "active"

    elif status_type == "PROPOSAL":
        # New proposal — reset counters
        session["consecutive_agrees"] = 0
        session["consecutive_disagrees"] = 0
        session["status"] = "active"

    elif status_type == "NEED_INFO":
        session["status"] = "needs_info"

    return session["status"]


def strip_status_line(response_text: str) -> str:
    """Remove [STATUS: ...] lines from response text for cleaner display."""
    return re.sub(r"\n?\s*\[STATUS:\s*[^\]]*\]\s*$", "", response_text, flags=re.IGNORECASE).strip()


def end_session(session_id: str) -> dict[str, Any] | None:
    """
    End a session: archive transcript to disk, remove from active sessions.
    Returns the full session transcript.
    """
    session = ACTIVE_SESSIONS.pop(session_id, None)
    if session is None:
        return None

    session["ended"] = datetime.now(timezone.utc).isoformat()
    session["status"] = session.get("status", "ended")

    # Save transcript to disk
    if SESSIONS_DIR is not None:
        transcript_path = SESSIONS_DIR / f"{session_id}.json"
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2, ensure_ascii=False)

    return session


def list_sessions() -> list[dict[str, Any]]:
    """List all active sessions (summary info only)."""
    return [
        {
            "id": s["id"],
            "task": s["task"][:100],
            "project": s["project"],
            "turn_count": s["turn_count"],
            "status": s["status"],
            "created": s["created"],
        }
        for s in ACTIVE_SESSIONS.values()
    ]


def get_session_summary(session_id: str) -> str:
    """Get a brief text summary of a session for context injection."""
    session = ACTIVE_SESSIONS.get(session_id)
    if session is None:
        return ""

    summary = f"Collaboration session on: {session['task']}\n"
    summary += f"Status: {session['status']}, Turn: {session['turn_count']}\n"
    if session["project"]:
        summary += f"Project: {session['project']}\n"
    return summary
