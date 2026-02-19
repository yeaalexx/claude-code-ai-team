"""
Grok's Persistent Memory System.

Manages a JSON-based memory store that gives Grok persistent knowledge
across calls and sessions. The server injects relevant memories into
Grok's system prompt before each API call.

Memory file: memory/grok-memory.json (relative to server install directory)
"""

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# Memory file location (set by server.py at startup)
MEMORY_DIR: Optional[Path] = None
MEMORY_FILE: Optional[Path] = None

# In-memory cache
_memory_cache: Optional[Dict[str, Any]] = None
_cache_timestamp: float = 0.0
CACHE_TTL: float = 60.0  # seconds


def initialize(base_dir: Path) -> None:
    """Initialize memory system with the server's base directory."""
    global MEMORY_DIR, MEMORY_FILE
    MEMORY_DIR = base_dir / "memory"
    MEMORY_FILE = MEMORY_DIR / "grok-memory.json"

    # Create directories
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    (MEMORY_DIR / "sessions").mkdir(parents=True, exist_ok=True)

    # Create initial memory file if it doesn't exist
    if not MEMORY_FILE.exists():
        initial_memory = _create_initial_memory()
        _write_memory_file(initial_memory)


def _create_initial_memory() -> Dict[str, Any]:
    """Create the initial empty memory structure."""
    return {
        "version": 1,
        "created": datetime.now(timezone.utc).isoformat(),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "identity": {
            "role": (
                "You are Grok, part of a Claude+Grok AI collaboration team. "
                "Claude Code is the primary agent who executes code and manages files. "
                "You provide independent analysis, code review, architecture advice, "
                "and creative problem-solving. You have persistent memory from past "
                "collaborations — your accumulated learnings are injected into your "
                "context. Build on them."
            ),
            "style": (
                "Direct, concise, opinionated. Disagree with Claude when you have "
                "strong reasons. Flag risks Claude might miss. Offer alternatives."
            )
        },
        "learnings": [],
        "corrections": [],
        "project_contexts": {},
        "statistics": {
            "total_calls": 0,
            "calls_by_tool": {},
            "learnings_count": 0,
            "corrections_count": 0,
            "sessions_count": 0
        }
    }


def _write_memory_file(memory: Dict[str, Any]) -> None:
    """Write memory to disk atomically (write to temp, then rename)."""
    if MEMORY_FILE is None:
        return
    tmp_path = MEMORY_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2, ensure_ascii=False)
    # On Windows, os.replace is atomic if on the same filesystem
    os.replace(str(tmp_path), str(MEMORY_FILE))


def load_memory() -> Dict[str, Any]:
    """Load memory from disk with caching."""
    global _memory_cache, _cache_timestamp

    now = time.time()
    if _memory_cache is not None and (now - _cache_timestamp) < CACHE_TTL:
        return _memory_cache

    if MEMORY_FILE is None or not MEMORY_FILE.exists():
        _memory_cache = _create_initial_memory()
        _cache_timestamp = now
        return _memory_cache

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            _memory_cache = json.load(f)
        _cache_timestamp = now
    except (json.JSONDecodeError, OSError):
        # Corrupted file — back up and start fresh
        if MEMORY_FILE.exists():
            backup = MEMORY_FILE.with_suffix(".backup.json")
            os.replace(str(MEMORY_FILE), str(backup))
        _memory_cache = _create_initial_memory()
        _cache_timestamp = now

    return _memory_cache


def save_memory(memory: Dict[str, Any]) -> None:
    """Save memory to disk and update cache."""
    global _memory_cache, _cache_timestamp

    memory["last_updated"] = datetime.now(timezone.utc).isoformat()
    _write_memory_file(memory)
    _memory_cache = memory
    _cache_timestamp = time.time()


def add_learning(
    source: str,
    category: str,
    content: str,
    project: str = "",
    confidence: float = 0.8
) -> str:
    """Add a learning to Grok's memory. Returns the learning ID."""
    memory = load_memory()

    # Deduplication: skip if first 80 chars match an existing learning in same category
    normalized = content.strip().lower()[:80]
    for existing in memory["learnings"]:
        if existing["category"] == category and existing["content"].strip().lower()[:80] == normalized:
            return existing["id"]  # Already exists

    learning_id = f"L{len(memory['learnings']) + 1:04d}"
    learning = {
        "id": learning_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "project": project,
        "category": category,
        "content": content.strip(),
        "confidence": confidence
    }
    memory["learnings"].append(learning)
    memory["statistics"]["learnings_count"] = len(memory["learnings"])
    save_memory(memory)
    return learning_id


def add_correction(
    corrector: str,
    original_claim: str,
    correction: str,
    category: str = "general"
) -> str:
    """Add a correction (when one AI corrects the other). Returns correction ID."""
    memory = load_memory()
    correction_id = f"C{len(memory['corrections']) + 1:04d}"
    entry = {
        "id": correction_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "corrector": corrector,
        "original_claim": original_claim.strip(),
        "correction": correction.strip(),
        "category": category
    }
    memory["corrections"].append(entry)
    memory["statistics"]["corrections_count"] = len(memory["corrections"])
    save_memory(memory)
    return correction_id


def update_project_context(project: str, tech_stack: str = "", summary: str = "") -> None:
    """Update or create a project context entry."""
    memory = load_memory()
    if project not in memory["project_contexts"]:
        memory["project_contexts"][project] = {}
    ctx = memory["project_contexts"][project]
    if tech_stack:
        ctx["tech_stack"] = tech_stack
    if summary:
        ctx["summary"] = summary
    ctx["last_active"] = datetime.now(timezone.utc).isoformat()
    save_memory(memory)


def query_learnings(
    category: Optional[str] = None,
    project: Optional[str] = None,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """Query learnings filtered by category and/or project."""
    memory = load_memory()
    results = memory.get("learnings", [])

    if category and category != "all":
        results = [l for l in results if l["category"] == category]

    if project:
        # Include both project-specific and general (no project) learnings
        results = [l for l in results if l["project"] in ("", project)]

    # Sort by confidence (desc), then timestamp (desc)
    results.sort(key=lambda x: (x.get("confidence", 0.5), x.get("timestamp", "")), reverse=True)

    return results[:limit]


def get_corrections(category: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent corrections, optionally filtered by category."""
    memory = load_memory()
    results = memory.get("corrections", [])
    if category:
        results = [c for c in results if c["category"] == category]
    return results[-limit:]  # Most recent


def get_memory_stats() -> Dict[str, Any]:
    """Get memory statistics."""
    memory = load_memory()
    learnings = memory.get("learnings", [])
    categories = {}
    for l in learnings:
        cat = l.get("category", "uncategorized")
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "total_learnings": len(learnings),
        "learnings_by_category": categories,
        "total_corrections": len(memory.get("corrections", [])),
        "projects": list(memory.get("project_contexts", {}).keys()),
        "last_updated": memory.get("last_updated", "never"),
        "statistics": memory.get("statistics", {})
    }


def record_call(tool_name: str) -> None:
    """Record a tool call in statistics."""
    memory = load_memory()
    stats = memory.setdefault("statistics", {})
    stats["total_calls"] = stats.get("total_calls", 0) + 1
    by_tool = stats.setdefault("calls_by_tool", {})
    by_tool[tool_name] = by_tool.get(tool_name, 0) + 1
    save_memory(memory)


# --- Learning Extraction from Grok Responses ---

# Pattern: [LEARNING category="..."] content [/LEARNING]
_LEARNING_PATTERN = re.compile(
    r'\[LEARNING\s+category=["\']([^"\']+)["\']\]\s*\n?(.*?)\n?\s*\[/LEARNING\]',
    re.DOTALL | re.IGNORECASE
)


def extract_learnings(response_text: str) -> List[Dict[str, str]]:
    """
    Extract [LEARNING] blocks from a Grok response.
    Returns list of {"category": ..., "content": ...} dicts.
    """
    matches = _LEARNING_PATTERN.findall(response_text)
    learnings = []
    for category, content in matches:
        content = content.strip()
        if content and len(content) > 10:  # Skip trivially short learnings
            learnings.append({
                "category": category.lower(),
                "content": content
            })
    return learnings


def strip_learning_blocks(response_text: str) -> str:
    """Remove [LEARNING] blocks from response text (for cleaner display)."""
    return _LEARNING_PATTERN.sub("", response_text).strip()


def bulk_push_learnings(learnings_text: str, source: str = "claude", project: str = "") -> int:
    """
    Parse and store multiple learnings from Claude's knowledge base.
    Accepts newline-separated learnings or markdown list items.
    Returns count of learnings stored.
    """
    count = 0
    lines = learnings_text.strip().split("\n")
    for line in lines:
        line = line.strip().lstrip("-*").strip()
        if not line or len(line) < 15:
            continue

        # Try to detect category from content
        category = _detect_category(line)
        existing_id = add_learning(
            source=source,
            category=category,
            content=line,
            project=project,
            confidence=0.75  # Lower confidence for bulk-pushed learnings
        )
        # add_learning returns existing ID if duplicate, new ID if new
        if existing_id.startswith("L"):
            count += 1

    return count


def _detect_category(text: str) -> str:
    """Simple heuristic to detect learning category from content."""
    text_lower = text.lower()
    if any(w in text_lower for w in ["architect", "design", "pattern", "schema", "tenant", "microservice"]):
        return "architecture"
    if any(w in text_lower for w in ["bug", "debug", "error", "fix", "crash", "exception"]):
        return "debugging"
    if any(w in text_lower for w in ["docker", "kubernetes", "ci/cd", "deploy", "npm", "pip", "maven"]):
        return "devops"
    if any(w in text_lower for w in ["security", "auth", "encrypt", "token", "csrf", "xss"]):
        return "security"
    if any(w in text_lower for w in ["test", "mock", "assert", "coverage", "tdd"]):
        return "testing"
    if any(w in text_lower for w in ["perf", "optim", "cache", "latency", "throughput"]):
        return "performance"
    return "code"
