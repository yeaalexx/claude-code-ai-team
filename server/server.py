#!/usr/bin/env python3
"""
Enhanced Multi-AI MCP Server v6.0
Intelligent Findings + Always-On Agents — Claude + Grok collaboration with:
- RAG-based semantic memory retrieval (ChromaDB)
- Parallel Grok calls for the 2-call review pattern
- Persistent memory for Grok (with consolidation to prevent unbounded growth)
- Multi-turn collaboration sessions
- Agent-style task execution
- Bidirectional memory synchronization
- Integration-first protocol for multi-service projects
- Contract-driven development workflow
- Increased token budgets for Grok 4.20 multi-agent
- v5: File system watcher for automatic change detection
- v5: Proactive contract auditor (pattern-based, no AI cost)
- v5: Validation workflows (LangGraph-inspired state machine)
- v5: Agent control plane with FastAPI dashboard (localhost:3100)
"""

import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Ensure UTF-8 output (critical on Windows where default is cp1252)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

# Resolve import paths — works both as a package (server/) and flat install
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR.parent))
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from server import auto_review, context_builder, memory, rag_memory, sessions
except ImportError:
    import auto_review  # type: ignore[no-redef]
    import context_builder  # type: ignore[no-redef]
    import memory  # type: ignore[no-redef]
    import rag_memory  # type: ignore[no-redef]
    import sessions  # type: ignore[no-redef]

try:
    from server import auditor, control_plane, watcher, workflows
except ImportError:
    import auditor  # type: ignore[no-redef]
    import control_plane  # type: ignore[no-redef]
    import watcher  # type: ignore[no-redef]
    import workflows  # type: ignore[no-redef]

try:
    from server import decision_learner, feature_map, finding_analyzer, finding_lifecycle
except ImportError:
    import decision_learner  # type: ignore[no-redef]
    import feature_map  # type: ignore[no-redef]
    import finding_analyzer  # type: ignore[no-redef]
    import finding_lifecycle  # type: ignore[no-redef]

__version__ = "6.0.0"

# Load credentials
CREDENTIALS_FILE = SCRIPT_DIR / "credentials.json"
# If not found next to server.py, check the install directory
if not CREDENTIALS_FILE.exists():
    INSTALL_DIR = Path.home() / ".claude-mcp-servers" / "multi-ai-collab"
    CREDENTIALS_FILE = INSTALL_DIR / "credentials.json"

try:
    with open(CREDENTIALS_FILE, "r") as f:
        CREDENTIALS = json.load(f)
except Exception as e:
    print(
        json.dumps({"jsonrpc": "2.0", "error": {"code": -32603, "message": f"Failed to load credentials.json: {e!s}"}}),
        file=sys.stdout,
        flush=True,
    )
    sys.exit(1)

# Initialize AI clients
AI_CLIENTS: dict[str, dict[str, Any]] = {}

# Gemini
if CREDENTIALS.get("gemini", {}).get("enabled", False):
    try:
        import google.generativeai as genai

        genai.configure(api_key=CREDENTIALS["gemini"]["api_key"])
        AI_CLIENTS["gemini"] = {"client": genai.GenerativeModel(CREDENTIALS["gemini"]["model"]), "type": "gemini"}
    except Exception as e:
        print(f"Warning: Gemini initialization failed: {e}", file=sys.stderr)

# Grok and OpenAI (both use OpenAI client)
if CREDENTIALS.get("grok", {}).get("enabled", False) or CREDENTIALS.get("openai", {}).get("enabled", False):
    try:
        from openai import OpenAI

        if CREDENTIALS.get("grok", {}).get("enabled", False):
            AI_CLIENTS["grok"] = {
                "client": OpenAI(api_key=CREDENTIALS["grok"]["api_key"], base_url=CREDENTIALS["grok"]["base_url"]),
                "model": CREDENTIALS["grok"]["model"],
                "type": "openai",
            }

        if CREDENTIALS.get("openai", {}).get("enabled", False):
            AI_CLIENTS["openai"] = {
                "client": OpenAI(api_key=CREDENTIALS["openai"]["api_key"]),
                "model": CREDENTIALS["openai"]["model"],
                "type": "openai",
            }
    except Exception as e:
        print(f"Warning: OpenAI client initialization failed: {e}", file=sys.stderr)

# DeepSeek
if CREDENTIALS.get("deepseek", {}).get("enabled", False):
    try:
        from openai import OpenAI

        AI_CLIENTS["deepseek"] = {
            "client": OpenAI(api_key=CREDENTIALS["deepseek"]["api_key"], base_url=CREDENTIALS["deepseek"]["base_url"]),
            "model": CREDENTIALS["deepseek"]["model"],
            "type": "openai",
        }
    except Exception as e:
        print(f"Warning: DeepSeek initialization failed: {e}", file=sys.stderr)

# Initialize memory and session systems
# Use the install directory for memory storage (persists across updates)
MEMORY_BASE = Path.home() / ".claude-mcp-servers" / "multi-ai-collab"
memory.initialize(MEMORY_BASE)
sessions.initialize(MEMORY_BASE)

# Initialize RAG memory (ChromaDB) — non-blocking, graceful fallback
rag_memory.initialize(MEMORY_BASE)

# Migrate existing JSON learnings to RAG (idempotent, runs once per collection)
try:
    _migrated = memory.migrate_to_rag()
    if _migrated > 0:
        print(f"RAG: Migrated {_migrated} learnings from JSON to ChromaDB", file=sys.stderr)
except Exception as _e:
    print(f"RAG migration skipped: {_e}", file=sys.stderr)

# Initialize v5: Always-on agent system (non-blocking, graceful fallback)
_workflow_manager = workflows.WorkflowManager()
_auditor = auditor.ProactiveAuditor()

# Start control plane (FastAPI on localhost:3100) — non-blocking
_control_plane: Any = None
try:
    _control_plane = control_plane.get_control_plane()
    _control_plane.set_workflow_manager(_workflow_manager)
    _control_plane.set_auditor(_auditor)
    # Don't auto-start — user starts via tool or config
except Exception as _e:
    print(f"Control plane init skipped: {_e}", file=sys.stderr)

# Initialize v6: Intelligent findings system (non-blocking, graceful fallback)
_lifecycle_manager: Any = None
try:
    _lifecycle_manager = finding_lifecycle.get_lifecycle_manager()
    _lifecycle_manager.initialize(MEMORY_BASE / "memory" / "findings.db")
    if _control_plane:
        _control_plane.set_lifecycle_manager(_lifecycle_manager)
except Exception as _e:
    print(f"Finding lifecycle init skipped: {_e}", file=sys.stderr)

# decision_learner uses module-level state — no explicit init needed


# ─── Core AI Call Function (Enhanced) ────────────────────────────────────────


def send_response(response: dict[str, Any]) -> None:
    """Send a JSON-RPC response."""
    print(json.dumps(response), flush=True)


def call_ai(
    ai_name: str,
    prompt: str,
    temperature: float = 0.7,
    system_prompt: str | None = None,
    session_messages: list[dict[str, str]] | None = None,
    tool_name: str = "",
    project: str = "",
) -> str:
    """
    Call a specific AI and return response.

    Enhanced from v1: supports system prompts, session history, and auto-learning extraction.
    """
    if ai_name not in AI_CLIENTS:
        return f"Error: {ai_name.upper()} is not available or not configured"

    # Record the call in stats
    if tool_name:
        memory.record_call(tool_name)

    try:
        client_info = AI_CLIENTS[ai_name]
        client = client_info["client"]

        if client_info["type"] == "gemini":
            import google.generativeai as genai

            # Gemini doesn't support system prompts in the same way
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n---\n\n{prompt}"
            response = client.generate_content(
                full_prompt,
                generation_config=genai.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=8192,
                ),
            )
            result_text = response.text

        elif client_info["type"] == "openai":
            messages = []

            # System prompt with memory injection
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

            # Session history (for multi-turn collaboration)
            if session_messages:
                messages.extend(session_messages)

            # Current user message
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=client_info["model"], messages=messages, temperature=temperature, max_tokens=8192
            )
            result_text = response.choices[0].message.content

        else:
            return f"Error: Unknown client type for {ai_name}"

        # Auto-extract and save learnings from Grok's response
        extracted = memory.extract_learnings(result_text)
        for learning in extracted:
            memory.add_learning(
                source=ai_name,
                category=learning["category"],
                content=learning["content"],
                project=project,
                confidence=0.85,
            )

        return result_text

    except Exception as e:
        return f"Error calling {ai_name.upper()}: {e!s}"


def call_multiple_ais(prompt: str, ai_list: list[str], temperature: float = 0.7) -> str:
    """Call multiple AIs and return combined responses."""
    results = []
    available_ais = [ai for ai in ai_list if ai in AI_CLIENTS]

    if not available_ais:
        return "Error: None of the requested AIs are available"

    for ai_name in available_ais:
        response = call_ai(ai_name, prompt, temperature)
        results.append(f"## {ai_name.upper()} Response:\n\n{response}")

    return "\n\n" + ("=" * 80 + "\n\n").join(results)


def call_ai_parallel(
    calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fire multiple Grok calls simultaneously and return all results.

    Each call is a dict with keys matching call_ai() parameters:
        ai_name, prompt, temperature, system_prompt, tool_name, project

    Returns a list of dicts: [{"label": ..., "result": ...}, ...]
    in the same order as the input calls.
    """
    results: list[dict[str, Any]] = [{"label": c.get("label", f"call_{i}"), "result": ""} for i, c in enumerate(calls)]

    def _do_call(index: int, call_spec: dict[str, Any]) -> tuple[int, str]:
        response = call_ai(
            ai_name=call_spec.get("ai_name", "grok"),
            prompt=call_spec.get("prompt", ""),
            temperature=call_spec.get("temperature", 0.7),
            system_prompt=call_spec.get("system_prompt"),
            tool_name=call_spec.get("tool_name", ""),
            project=call_spec.get("project", ""),
        )
        return index, response

    with ThreadPoolExecutor(max_workers=min(len(calls), 4)) as executor:
        futures = {executor.submit(_do_call, i, c): i for i, c in enumerate(calls)}
        for future in as_completed(futures):
            try:
                idx, response = future.result()
                results[idx]["result"] = response
            except Exception as e:
                idx = futures[future]
                results[idx]["result"] = f"Error: {e!s}"

    return results


# ─── Grok Multi-Agent Call (Responses API) ───────────────────────────────────


def call_grok_multi_agent(
    prompt: str,
    temperature: float = 0.7,
    system_prompt: str | None = None,
    tool_name: str = "",
    project: str = "",
) -> str:
    """Call Grok's multi-agent model via the /v1/responses endpoint.

    The multi-agent model (grok-4.20-multi-agent-0309) uses an internal team
    of AI agents that deliberate before answering.  It requires the Responses
    API (``/v1/responses``) instead of Chat Completions, with ``input`` instead
    of ``messages`` and a different response structure.

    This is 10-30x more expensive per call — use only for complex tasks.
    """
    grok_creds = CREDENTIALS.get("grok", {})
    if not grok_creds.get("enabled", False):
        return "Error: Grok is not available or not configured"

    api_key = grok_creds["api_key"]
    base_url = grok_creds.get("base_url", "https://api.x.ai/v1")
    model = grok_creds.get("multi_agent_model", "grok-4.20-multi-agent-0309")

    # Build the input text — combine system prompt + user prompt
    input_text = prompt
    if system_prompt:
        input_text = f"{system_prompt}\n\n---\n\n{prompt}"

    # Record the call in stats
    if tool_name:
        memory.record_call(tool_name)

    try:
        url = f"{base_url}/responses"
        payload = {
            "model": model,
            "input": input_text,
            "max_output_tokens": 16384,
            "temperature": temperature,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        # Extract text from Responses API format:
        #   data["output"][0]["content"][0]["text"]
        result_text = data["output"][0]["content"][0]["text"]

        # Auto-extract and save learnings (same pattern as call_ai)
        extracted = memory.extract_learnings(result_text)
        for learning in extracted:
            memory.add_learning(
                source="grok-multi-agent",
                category=learning["category"],
                content=learning["content"],
                project=project,
                confidence=0.90,
            )

        return result_text

    except httpx.HTTPStatusError as e:
        return f"Error calling Grok multi-agent (HTTP {e.response.status_code}): {e.response.text}"
    except Exception as e:
        return f"Error calling Grok multi-agent: {e!s}"


# ─── MCP Protocol Handlers ──────────────────────────────────────────────────


def handle_initialize(request_id: Any) -> dict[str, Any]:
    """Handle MCP initialization."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "multi-ai-mcp", "version": __version__},
        },
    }


def handle_tools_list(request_id: Any) -> dict[str, Any]:
    """List all available tools (existing + new bidirectional learning tools)."""
    tools = [
        {
            "name": "server_status",
            "description": "Get server status and available AI models",
            "inputSchema": {"type": "object", "properties": {}},
        }
    ]

    # ── Per-AI tools (same as v1 but with optional project param) ────────

    for ai_name in AI_CLIENTS:
        tools.extend(
            [
                {
                    "name": f"ask_{ai_name}",
                    "description": f"Ask {ai_name.upper()} a question",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string", "description": "The question or prompt"},
                            "temperature": {"type": "number", "description": "Temperature (0.0-1.0)", "default": 0.7},
                            "project": {
                                "type": "string",
                                "description": "Project name for memory context",
                                "default": "",
                            },
                        },
                        "required": ["prompt"],
                    },
                },
                {
                    "name": f"{ai_name}_code_review",
                    "description": f"Have {ai_name.upper()} review code for issues and improvements",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string", "description": "The code to review"},
                            "focus": {
                                "type": "string",
                                "description": "Focus area (security, performance, readability, etc.)",
                                "default": "general",
                            },
                            "project": {
                                "type": "string",
                                "description": "Project name for memory context",
                                "default": "",
                            },
                        },
                        "required": ["code"],
                    },
                },
                {
                    "name": f"{ai_name}_think_deep",
                    "description": f"Have {ai_name.upper()} do deep analysis with extended reasoning",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string", "description": "Topic or problem for deep analysis"},
                            "context": {
                                "type": "string",
                                "description": "Additional context or constraints",
                                "default": "",
                            },
                            "project": {
                                "type": "string",
                                "description": "Project name for memory context",
                                "default": "",
                            },
                        },
                        "required": ["topic"],
                    },
                },
                {
                    "name": f"{ai_name}_brainstorm",
                    "description": f"Brainstorm creative solutions with {ai_name.upper()}",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "challenge": {
                                "type": "string",
                                "description": "The challenge or problem to brainstorm about",
                            },
                            "constraints": {
                                "type": "string",
                                "description": "Any constraints or limitations",
                                "default": "",
                            },
                            "project": {
                                "type": "string",
                                "description": "Project name for memory context",
                                "default": "",
                            },
                        },
                        "required": ["challenge"],
                    },
                },
                {
                    "name": f"{ai_name}_debug",
                    "description": f"Get debugging help from {ai_name.upper()}",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "error": {"type": "string", "description": "Error message or description"},
                            "code": {
                                "type": "string",
                                "description": "Related code that's causing issues",
                                "default": "",
                            },
                            "context": {
                                "type": "string",
                                "description": "Additional context about the environment/setup",
                                "default": "",
                            },
                            "project": {
                                "type": "string",
                                "description": "Project name for memory context",
                                "default": "",
                            },
                        },
                        "required": ["error"],
                    },
                },
                {
                    "name": f"{ai_name}_architecture",
                    "description": f"Get architecture design advice from {ai_name.upper()}",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "requirements": {"type": "string", "description": "System requirements and goals"},
                            "constraints": {
                                "type": "string",
                                "description": "Technical constraints, budget, timeline etc.",
                                "default": "",
                            },
                            "scale": {
                                "type": "string",
                                "description": "Expected scale (users, data, etc.)",
                                "default": "",
                            },
                            "project": {
                                "type": "string",
                                "description": "Project name for memory context",
                                "default": "",
                            },
                        },
                        "required": ["requirements"],
                    },
                },
            ]
        )

    # ── Multi-AI collaborative tools (when 2+ AIs enabled) ──────────────

    if len(AI_CLIENTS) > 1:
        tools.extend(
            [
                {
                    "name": "ask_all_ais",
                    "description": "Ask all available AIs the same question and compare responses",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string", "description": "The question to ask all AIs"},
                            "temperature": {
                                "type": "number",
                                "description": "Temperature for responses",
                                "default": 0.7,
                            },
                        },
                        "required": ["prompt"],
                    },
                },
                {
                    "name": "ai_debate",
                    "description": "Have two AIs debate a topic",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string", "description": "The debate topic"},
                            "ai1": {"type": "string", "description": "First AI", "default": "gemini"},
                            "ai2": {"type": "string", "description": "Second AI", "default": "grok"},
                        },
                        "required": ["topic"],
                    },
                },
                {
                    "name": "collaborative_solve",
                    "description": "Have multiple AIs collaborate to solve a complex problem",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "problem": {"type": "string", "description": "The complex problem to solve"},
                            "approach": {
                                "type": "string",
                                "description": "How to divide work (sequential, parallel, debate)",
                                "default": "sequential",
                            },
                        },
                        "required": ["problem"],
                    },
                },
                {
                    "name": "ai_consensus",
                    "description": "Get consensus opinion from all available AIs",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string", "description": "Question to get consensus on"},
                            "options": {
                                "type": "string",
                                "description": "Available options or approaches",
                                "default": "",
                            },
                        },
                        "required": ["question"],
                    },
                },
            ]
        )

    # ── NEW: Bidirectional Learning & Collaboration Tools ────────────────

    tools.extend(
        [
            {
                "name": "grok_collaborate",
                "description": (
                    "Start or continue a multi-turn collaboration session with Grok. "
                    "Both AIs iterate toward an agreed solution. "
                    "First call: provide task+context to start. "
                    "Subsequent calls: provide session_id+message to continue."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID from a previous call (omit to start new session)",
                        },
                        "task": {
                            "type": "string",
                            "description": "The task or problem to collaborate on (required for new sessions)",
                        },
                        "message": {"type": "string", "description": "Your response/follow-up in an ongoing session"},
                        "context": {
                            "type": "string",
                            "description": "Relevant code, files, or context (for new sessions)",
                            "default": "",
                        },
                        "project": {"type": "string", "description": "Project name for memory scoping", "default": ""},
                    },
                },
            },
            {
                "name": "grok_execute_task",
                "description": (
                    "Give Grok a specific task to execute as an agent. "
                    "Grok works independently and returns a structured solution with "
                    "reasoning, confidence, caveats, and alternatives. "
                    "Claude reviews and applies the results."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "Specific task description"},
                        "files": {
                            "type": "string",
                            "description": "Relevant file contents Grok needs to see",
                            "default": "",
                        },
                        "constraints": {
                            "type": "string",
                            "description": "Constraints: coding style, framework, patterns to follow",
                            "default": "",
                        },
                        "output_format": {
                            "type": "string",
                            "description": "Expected output: code, plan, review, diff",
                            "default": "code",
                        },
                        "project": {"type": "string", "description": "Project name for memory context", "default": ""},
                    },
                    "required": ["task"],
                },
            },
            {
                "name": "grok_memory_sync",
                "description": (
                    "Synchronize learnings between Claude and Grok. "
                    "push: share Claude's learnings with Grok. "
                    "pull: retrieve Grok's learnings for Claude to integrate. "
                    "status: view memory statistics."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "Action: push (Claude->Grok), pull (Grok->Claude), status",
                            "enum": ["push", "pull", "status"],
                        },
                        "learnings": {
                            "type": "string",
                            "description": "For push: learnings text to share with Grok",
                            "default": "",
                        },
                        "project": {"type": "string", "description": "Project scope for filtering", "default": ""},
                        "category": {
                            "type": "string",
                            "description": "Category filter: architecture, code, debugging, domain, all",
                            "default": "all",
                        },
                    },
                    "required": ["action"],
                },
            },
            {
                "name": "grok_session_end",
                "description": (
                    "End a collaboration session. Saves transcript and optionally "
                    "extracts learnings from the full conversation."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "The session to end"},
                        "save_learnings": {
                            "type": "boolean",
                            "description": "Extract and save learnings from this session",
                            "default": True,
                        },
                        "claude_summary": {
                            "type": "string",
                            "description": "Claude's summary of what was decided/learned",
                            "default": "",
                        },
                    },
                    "required": ["session_id"],
                },
            },
            {
                "name": "grok_memory_status",
                "description": "View Grok's memory state: learning counts, recent entries, projects.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "detail": {
                            "type": "string",
                            "description": "Level of detail: summary, full, category",
                            "default": "summary",
                        },
                        "project": {"type": "string", "description": "Filter by project name", "default": ""},
                        "category": {"type": "string", "description": "Filter by category", "default": ""},
                    },
                },
            },
            {
                "name": "grok_multi_review",
                "description": (
                    "Run the 2-call Grok review pattern in parallel: "
                    "Call 1 checks code quality + integration contract compliance, "
                    "Call 2 checks regulatory compliance + extracts learnings. "
                    "Returns combined results from both calls."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "The code to review"},
                        "contracts_context": {
                            "type": "string",
                            "description": "Related API contracts, OpenAPI specs, or interface definitions",
                            "default": "",
                        },
                        "project": {"type": "string", "description": "Project name for memory context", "default": ""},
                    },
                    "required": ["code"],
                },
            },
            {
                "name": "grok_retrieve_context",
                "description": (
                    "Retrieve relevant learnings from Grok's memory using semantic search (RAG). "
                    "Does NOT call Grok — just returns stored knowledge relevant to the task. "
                    "Use this to get context before starting work, without API cost."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "Description of the task or topic to find context for",
                        },
                        "n_results": {
                            "type": "integer",
                            "description": "Maximum number of results (default 20)",
                            "default": 20,
                        },
                        "category": {
                            "type": "string",
                            "description": "Optional category filter",
                            "default": "",
                        },
                        "project": {
                            "type": "string",
                            "description": "Optional project filter",
                            "default": "",
                        },
                    },
                    "required": ["task"],
                },
            },
            {
                "name": "grok_multi_agent",
                "description": (
                    "Use Grok's multi-agent team (4 AI agents deliberate internally) for complex analysis. "
                    "More powerful but 10-30x more expensive than regular Grok. "
                    "Use for: architecture reviews, complex debugging, compliance analysis, design decisions. "
                    "Do NOT use for simple questions."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "The complex question or analysis request",
                        },
                        "context": {
                            "type": "string",
                            "description": "Additional context, code, or constraints",
                            "default": "",
                        },
                        "project": {
                            "type": "string",
                            "description": "Project name for memory context",
                            "default": "",
                        },
                    },
                    "required": ["prompt"],
                },
            },
            {
                "name": "grok_auto_review",
                "description": (
                    "Automatically evaluate whether changed files need a Grok review, "
                    "based on configurable threshold rules (file patterns, count thresholds, "
                    "sensitive paths). If triggered, runs grok_code_review + grok_execute_task "
                    "in parallel and returns structured pass/warn/fail findings. "
                    "Prevents integration gaps from slipping through unreviewed."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "changed_files": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of changed file paths",
                        },
                        "diff_summary": {
                            "type": "string",
                            "description": "Summary of what changed",
                            "default": "",
                        },
                        "project": {
                            "type": "string",
                            "description": "Project name for memory context",
                            "default": "",
                        },
                        "skip_review": {
                            "type": "boolean",
                            "description": "Override: skip review regardless of thresholds",
                            "default": False,
                        },
                        "force_review": {
                            "type": "boolean",
                            "description": "Override: force full review regardless of thresholds",
                            "default": False,
                        },
                    },
                    "required": ["changed_files"],
                },
            },
            # ── v5: Always-on agent tools ──
            {
                "name": "agent_watcher_start",
                "description": "Start the file system watcher to monitor project directories for changes. Validates changes against integration contracts automatically.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "config_path": {
                            "type": "string",
                            "description": "Path to watcher-config.json in the project root",
                            "default": "",
                        },
                        "project_root": {"type": "string", "description": "Project root directory to watch"},
                    },
                    "required": ["project_root"],
                },
            },
            {
                "name": "agent_watcher_stop",
                "description": "Stop the file system watcher.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "agent_watcher_status",
                "description": "Get the current status of the file watcher and recent events.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "agent_audit_scan",
                "description": "Run the proactive contract auditor to scan for latent integration violations. Scans service code against contracts/ without AI calls (fast, free).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_root": {"type": "string", "description": "Project root directory"},
                        "service": {
                            "type": "string",
                            "description": "Specific service to scan (optional — scans all if omitted)",
                            "default": "",
                        },
                    },
                    "required": ["project_root"],
                },
            },
            {
                "name": "agent_audit_findings",
                "description": "Get proactive auditor findings (pending contract violations and recommendations).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "description": "Filter by status: pending, approved, dismissed, all",
                            "default": "pending",
                        },
                    },
                },
            },
            {
                "name": "agent_control_plane",
                "description": "Start or manage the Agent Monitor control plane (FastAPI dashboard on localhost:3100).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "start, stop, or status",
                            "default": "status",
                        },
                        "port": {
                            "type": "number",
                            "description": "Port for the dashboard (default 3100)",
                            "default": 3100,
                        },
                    },
                },
            },
            {
                "name": "agent_load_feature_map",
                "description": "Load a FEATURE_MAP.yaml to enable cross-feature monitoring. The feature map defines how features depend on each other and which services they span.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "yaml_path": {
                            "type": "string",
                            "description": "Path to FEATURE_MAP.yaml in the project root",
                        },
                    },
                    "required": ["yaml_path"],
                },
            },
            {
                "name": "agent_analyze_findings",
                "description": "Run AI analysis on pending audit findings. Adds approve/dismiss recommendations with confidence scores and reasoning.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Analyze findings for a specific service (optional — analyzes all if omitted)",
                            "default": "",
                        },
                    },
                },
            },
            {
                "name": "agent_finding_action",
                "description": "Approve or dismiss a finding. Approved findings queue for sprint fixes. Dismissed findings record the reason for learning.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "finding_id": {"type": "string", "description": "The finding ID"},
                        "action": {
                            "type": "string",
                            "description": "approve or dismiss",
                        },
                        "reason": {
                            "type": "string",
                            "description": "For dismiss: false_positive, test_code, docs_only, vendor_code, intentional, duplicate",
                            "default": "",
                        },
                    },
                    "required": ["finding_id", "action"],
                },
            },
            {
                "name": "agent_sprint_prompt",
                "description": "Generate a sprint fix prompt for approved findings. Returns a ready-to-use prompt that Claude can execute to fix all approved audit findings.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Generate prompt for a specific service (optional)",
                            "default": "",
                        },
                    },
                },
            },
            {
                "name": "agent_findings_reminder",
                "description": "Check if there are approved findings that need attention. Returns a reminder message if findings are pending.",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]
    )

    return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools}}


# ─── Tool Execution ─────────────────────────────────────────────────────────


def handle_tool_call(request_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Handle tool execution — dispatches to the appropriate handler."""
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    try:
        result = _dispatch_tool(tool_name, arguments)
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": result}]}}
    except Exception as e:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": str(e)}}


def _dispatch_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    """Route tool calls to their handlers."""

    project = arguments.get("project", "")

    # ── Server status ────────────────────────────────────────────────────

    if tool_name == "server_status":
        return _handle_server_status()

    # ── NEW: Collaboration sessions ──────────────────────────────────────

    if tool_name == "grok_collaborate":
        return _handle_grok_collaborate(arguments)

    if tool_name == "grok_execute_task":
        return _handle_grok_execute_task(arguments)

    if tool_name == "grok_memory_sync":
        return _handle_grok_memory_sync(arguments)

    if tool_name == "grok_session_end":
        return _handle_grok_session_end(arguments)

    if tool_name == "grok_memory_status":
        return _handle_grok_memory_status(arguments)

    if tool_name == "grok_multi_review":
        return _handle_grok_multi_review(arguments)

    if tool_name == "grok_retrieve_context":
        return _handle_grok_retrieve_context(arguments)

    if tool_name == "grok_multi_agent":
        return _handle_grok_multi_agent(arguments)

    if tool_name == "grok_auto_review":
        return _handle_grok_auto_review(arguments)

    # ── v5: Always-on agent tools ──
    if tool_name == "agent_watcher_start":
        return _handle_agent_watcher_start(arguments)
    if tool_name == "agent_watcher_stop":
        return _handle_agent_watcher_stop(arguments)
    if tool_name == "agent_watcher_status":
        return _handle_agent_watcher_status(arguments)
    if tool_name == "agent_audit_scan":
        return _handle_agent_audit_scan(arguments)
    if tool_name == "agent_audit_findings":
        return _handle_agent_audit_findings(arguments)
    if tool_name == "agent_control_plane":
        return _handle_agent_control_plane(arguments)
    if tool_name == "agent_load_feature_map":
        return _handle_agent_load_feature_map(arguments)
    if tool_name == "agent_analyze_findings":
        return _handle_agent_analyze_findings(arguments)
    if tool_name == "agent_finding_action":
        return _handle_agent_finding_action(arguments)
    if tool_name == "agent_sprint_prompt":
        return _handle_agent_sprint_prompt(arguments)
    if tool_name == "agent_findings_reminder":
        return _handle_agent_findings_reminder(arguments)

    # ── Multi-AI tools ───────────────────────────────────────────────────

    if tool_name == "ask_all_ais":
        prompt = arguments.get("prompt", "")
        temperature = arguments.get("temperature", 0.7)
        return call_multiple_ais(prompt, list(AI_CLIENTS.keys()), temperature)

    if tool_name == "ai_debate":
        return _handle_ai_debate(arguments)

    if tool_name == "collaborative_solve":
        return _handle_collaborative_solve(arguments)

    if tool_name == "ai_consensus":
        return _handle_ai_consensus(arguments)

    # ── Per-AI individual tools ──────────────────────────────────────────

    # ask_{ai_name}
    if tool_name.startswith("ask_"):
        ai_name = tool_name[4:]  # Remove "ask_"
        prompt = arguments.get("prompt", "")
        temperature = arguments.get("temperature", 0.7)
        sys_prompt = context_builder.build_system_prompt(tool_name=tool_name, project=project)
        return call_ai(ai_name, prompt, temperature, system_prompt=sys_prompt, tool_name=tool_name, project=project)

    # {ai_name}_code_review
    if tool_name.endswith("_code_review"):
        ai_name = tool_name.replace("_code_review", "")
        code = arguments.get("code", "")
        focus = arguments.get("focus", "general")
        prompt = (
            f"Please review this code with a focus on {focus}:\n\n```\n{code}\n```\n\n"
            "Provide specific, actionable feedback on:\n"
            "1. Potential issues or bugs\n"
            "2. Security concerns\n"
            "3. Performance optimizations\n"
            "4. Best practices\n"
            "5. Code clarity and maintainability"
        )
        sys_prompt = context_builder.build_system_prompt(tool_name=tool_name, project=project)
        return call_ai(ai_name, prompt, 0.3, system_prompt=sys_prompt, tool_name=tool_name, project=project)

    # {ai_name}_think_deep
    if tool_name.endswith("_think_deep"):
        ai_name = tool_name.replace("_think_deep", "")
        topic = arguments.get("topic", "")
        ctx = arguments.get("context", "")
        prompt = f"Think deeply and analytically about: {topic}"
        if ctx:
            prompt += f"\n\nContext: {ctx}"
        prompt += "\n\nProvide comprehensive analysis with multiple perspectives, implications, and detailed reasoning."
        sys_prompt = context_builder.build_system_prompt(tool_name=tool_name, project=project)
        return call_ai(ai_name, prompt, 0.4, system_prompt=sys_prompt, tool_name=tool_name, project=project)

    # {ai_name}_brainstorm
    if tool_name.endswith("_brainstorm"):
        ai_name = tool_name.replace("_brainstorm", "")
        challenge = arguments.get("challenge", "")
        constraints = arguments.get("constraints", "")
        prompt = f"Brainstorm creative solutions for: {challenge}"
        if constraints:
            prompt += f"\n\nConstraints: {constraints}"
        prompt += "\n\nGenerate multiple innovative ideas, alternatives, and out-of-the-box approaches."
        sys_prompt = context_builder.build_system_prompt(tool_name=tool_name, project=project)
        return call_ai(ai_name, prompt, 0.8, system_prompt=sys_prompt, tool_name=tool_name, project=project)

    # {ai_name}_debug
    if tool_name.endswith("_debug"):
        ai_name = tool_name.replace("_debug", "")
        error = arguments.get("error", "")
        code = arguments.get("code", "")
        ctx = arguments.get("context", "")
        prompt = f"Help debug this issue: {error}"
        if code:
            prompt += f"\n\nRelated code:\n```\n{code}\n```"
        if ctx:
            prompt += f"\n\nContext: {ctx}"
        prompt += "\n\nProvide debugging steps, potential causes, and specific solutions."
        sys_prompt = context_builder.build_system_prompt(tool_name=tool_name, project=project)
        return call_ai(ai_name, prompt, 0.3, system_prompt=sys_prompt, tool_name=tool_name, project=project)

    # {ai_name}_architecture
    if tool_name.endswith("_architecture"):
        ai_name = tool_name.replace("_architecture", "")
        requirements = arguments.get("requirements", "")
        constraints = arguments.get("constraints", "")
        scale = arguments.get("scale", "")
        prompt = f"Design architecture for: {requirements}"
        if constraints:
            prompt += f"\n\nConstraints: {constraints}"
        if scale:
            prompt += f"\n\nScale requirements: {scale}"
        prompt += "\n\nProvide detailed architecture recommendations, patterns, and implementation guidance."
        sys_prompt = context_builder.build_system_prompt(tool_name=tool_name, project=project)
        return call_ai(ai_name, prompt, 0.5, system_prompt=sys_prompt, tool_name=tool_name, project=project)

    raise ValueError(f"Unknown tool: {tool_name}")


# ─── New Tool Handlers ───────────────────────────────────────────────────────


def _handle_server_status() -> str:
    """Server status with memory info."""
    available_ais = list(AI_CLIENTS.keys())
    total_configured = len([ai for ai in CREDENTIALS if CREDENTIALS[ai].get("enabled", False)])

    stats = memory.get_memory_stats()

    result = f"Multi-AI MCP Server v{__version__} (Bidirectional Learning)\n\n"
    result += f"Available AIs: {', '.join([ai.upper() for ai in available_ais])}\n"
    result += f"Status: {len(available_ais)}/{total_configured} AIs ready\n\n"
    result += "Configured Models:\n"
    for ai_name, client_info in AI_CLIENTS.items():
        model = client_info.get("model", CREDENTIALS[ai_name]["model"])
        result += f"  {ai_name.upper()}: {model}\n"

    disabled = [ai for ai in CREDENTIALS if not CREDENTIALS[ai].get("enabled", False) or ai not in AI_CLIENTS]
    if disabled:
        result += f"\nDisabled: {', '.join([ai.upper() for ai in disabled])}\n"

    result += f"\nGrok Memory: {stats['total_learnings']} learnings, {stats['total_corrections']} corrections\n"
    result += f"Active Sessions: {len(sessions.list_sessions())}\n"
    if stats.get("learnings_by_category"):
        result += (
            "Learnings by category: " + ", ".join(f"{k}: {v}" for k, v in stats["learnings_by_category"].items()) + "\n"
        )

    return result


def _handle_grok_collaborate(arguments: dict[str, Any]) -> str:
    """Handle multi-turn collaboration sessions."""
    session_id = arguments.get("session_id")
    task = arguments.get("task", "")
    message = arguments.get("message", "")
    context = arguments.get("context", "")
    project = arguments.get("project", "")

    if "grok" not in AI_CLIENTS:
        return "Error: Grok is not available for collaboration"

    # Start new session
    if not session_id:
        if not task:
            return "Error: 'task' is required to start a new collaboration session"

        session_id = sessions.create_session(task=task, project=project, context=context)
        sys_prompt = context_builder.build_system_prompt(
            tool_name="grok_collaborate", project=project, session_id=session_id
        )

        # Build initial prompt for Grok
        prompt = f"## Collaboration Task\n{task}\n"
        if context:
            prompt += f"\n## Context\n{context}\n"
        prompt += "\nAnalyze this task and provide your initial assessment. What approach do you recommend?"

        # Call Grok
        result = call_ai("grok", prompt, 0.6, system_prompt=sys_prompt, tool_name="grok_collaborate", project=project)

        # Record in session
        sessions.add_turn(session_id, "user", prompt)
        sessions.add_turn(session_id, "assistant", result)

        # Detect consensus status
        status = sessions.detect_consensus(session_id, result)

        # Clean response for display
        display_text = sessions.strip_status_line(result)
        display_text = memory.strip_learning_blocks(display_text)

        session = sessions.get_session(session_id)
        assert session is not None  # just created above
        return f"SESSION: {session_id}\nSTATUS: {status}\nTURN: {session['turn_count']}\n\n---\n\nGROK:\n{display_text}"

    # Continue existing session
    session = sessions.get_session(session_id)
    if session is None:
        return f"Error: Session {session_id} not found. It may have expired or been ended."

    if not message:
        return "Error: 'message' is required to continue a session"

    # Record Claude's message
    sessions.add_turn(session_id, "user", message)

    # Build system prompt and get session history
    sys_prompt = context_builder.build_system_prompt(
        tool_name="grok_collaborate", project=session.get("project", ""), session_id=session_id
    )
    history = sessions.get_history(session_id)

    # Call Grok with full conversation history
    # The latest user message is already in history, so we send "" as prompt
    # Actually, we need the history minus the last user message, then send last as prompt
    session_messages = history[:-1]  # All except the last (which is Claude's new message)
    current_prompt = history[-1]["content"]  # Claude's latest message

    result = call_ai(
        "grok",
        current_prompt,
        0.6,
        system_prompt=sys_prompt,
        session_messages=session_messages,
        tool_name="grok_collaborate",
        project=session.get("project", ""),
    )

    # Record Grok's response
    sessions.add_turn(session_id, "assistant", result)
    status = sessions.detect_consensus(session_id, result)

    display_text = sessions.strip_status_line(result)
    display_text = memory.strip_learning_blocks(display_text)

    session = sessions.get_session(session_id)
    assert session is not None  # validated above
    output = f"SESSION: {session_id}\nSTATUS: {status}\nTURN: {session['turn_count']}\n\n---\n\nGROK:\n{display_text}"

    if status == "consensus":
        output += "\n\n--- CONSENSUS REACHED ---\nBoth AIs agree. Consider calling grok_session_end to save learnings."
    elif status == "persistent_disagreement":
        output += "\n\n--- PERSISTENT DISAGREEMENT ---\nMultiple rounds without agreement. Consider presenting both views to the user."

    return output


def _handle_grok_execute_task(arguments: dict[str, Any]) -> str:
    """Grok as an independent agent executing a task."""
    task = arguments.get("task", "")
    files = arguments.get("files", "")
    constraints = arguments.get("constraints", "")
    output_format = arguments.get("output_format", "code")
    project = arguments.get("project", "")

    if "grok" not in AI_CLIENTS:
        return "Error: Grok is not available"

    # Build system prompt with agent instructions
    sys_prompt = context_builder.build_system_prompt(
        tool_name="grok_execute_task",
        project=project,
        extra_instructions=(
            "You are executing a task independently as an agent. "
            "Provide a complete, production-ready solution. "
            "Be thorough — Claude will review your output but should be able to apply it directly."
        ),
    )

    # Build the agent-style user prompt
    prompt = context_builder.build_agent_prompt(
        task=task, files=files, constraints=constraints, output_format=output_format
    )

    result = call_ai("grok", prompt, 0.4, system_prompt=sys_prompt, tool_name="grok_execute_task", project=project)

    display_text = memory.strip_learning_blocks(result)
    return f"GROK AGENT RESULT ({output_format}):\n\n{display_text}"


def _handle_grok_memory_sync(arguments: dict[str, Any]) -> str:
    """Bidirectional memory synchronization between Claude and Grok."""
    action = arguments.get("action", "status")
    learnings_text = arguments.get("learnings", "")
    project = arguments.get("project", "")
    category = arguments.get("category", "all")

    if action == "push":
        if not learnings_text:
            return "Error: 'learnings' text is required for push action"
        count = memory.bulk_push_learnings(learnings_text, source="claude", project=project)
        return f"MEMORY SYNC (push): {count} learnings from Claude stored in Grok's memory."

    elif action == "pull":
        learnings = memory.query_learnings(
            category=category if category != "all" else None, project=project or None, limit=30
        )
        if not learnings:
            return "MEMORY SYNC (pull): No learnings found matching filters."

        result = f"MEMORY SYNC (pull): {len(learnings)} learnings from Grok's memory\n\n"
        for entry in learnings:
            source_tag = f"[{entry['source']}]" if entry.get("source") else ""
            project_tag = f"(project: {entry['project']})" if entry.get("project") else ""
            result += f"- [{entry['category']}] {source_tag} {entry['content']} {project_tag}\n"
        return result

    elif action == "status":
        stats = memory.get_memory_stats()
        result = "MEMORY SYNC (status):\n"
        result += f"  Total learnings: {stats['total_learnings']}\n"
        result += f"  Total corrections: {stats['total_corrections']}\n"
        result += f"  Projects: {', '.join(stats['projects']) or 'none'}\n"
        result += f"  Last updated: {stats['last_updated']}\n"
        if stats.get("learnings_by_category"):
            result += "  By category:\n"
            for cat, count in stats["learnings_by_category"].items():
                result += f"    {cat}: {count}\n"
        return result

    return f"Error: Unknown action '{action}'. Use push, pull, or status."


def _handle_grok_session_end(arguments: dict[str, Any]) -> str:
    """End a collaboration session and optionally extract learnings."""
    session_id = arguments.get("session_id", "")
    save_learnings = arguments.get("save_learnings", True)
    claude_summary = arguments.get("claude_summary", "")

    if not session_id:
        return "Error: session_id is required"

    session = sessions.get_session(session_id)
    if session is None:
        return f"Error: Session {session_id} not found"

    # Optionally extract learnings from the full session
    extracted_learnings = []
    if save_learnings and "grok" in AI_CLIENTS and session["turn_count"] > 0:
        # Build a summary of the session for learning extraction
        history_text = ""
        for msg in session["history"]:
            role_label = "Claude" if msg["role"] == "user" else "Grok"
            history_text += f"\n{role_label}: {msg['content']}\n"

        extraction_prompt = (
            f"Review this collaboration session and extract 1-5 key learnings "
            f"that should be remembered for future sessions.\n\n"
            f"Session task: {session['task']}\n"
            f"Session status: {session['status']}\n"
        )
        if claude_summary:
            extraction_prompt += f"Claude's summary: {claude_summary}\n"
        extraction_prompt += f"\nConversation:\n{history_text}\n\n"
        extraction_prompt += (
            "Format each learning as:\n"
            '[LEARNING category="..."] content [/LEARNING]\n\n'
            "Focus on reusable insights, not session-specific details."
        )

        result = call_ai("grok", extraction_prompt, 0.3, tool_name="grok_session_end")
        extracted_learnings = memory.extract_learnings(result)

        # Save extracted learnings
        for entry in extracted_learnings:
            memory.add_learning(
                source="collaboration",
                category=entry["category"],
                content=entry["content"],
                project=session.get("project", ""),
                confidence=0.9,
            )

    # End the session (saves transcript to disk)
    transcript = sessions.end_session(session_id)
    assert transcript is not None  # session existed (checked above)

    result = f"Session {session_id} ended.\n"
    result += f"Turns: {transcript['turn_count']}\n"
    result += f"Final status: {transcript['status']}\n"
    if extracted_learnings:
        result += f"\nExtracted {len(extracted_learnings)} learnings:\n"
        for entry in extracted_learnings:
            result += f"  - [{entry['category']}] {entry['content']}\n"
    else:
        result += "No learnings extracted.\n"

    return result


def _handle_grok_memory_status(arguments: dict[str, Any]) -> str:
    """View Grok's memory state."""
    detail = arguments.get("detail", "summary")
    project_filter = arguments.get("project", "")
    category_filter = arguments.get("category", "")

    stats = memory.get_memory_stats()

    if detail == "summary":
        result = "GROK MEMORY STATUS\n"
        result += f"  Total learnings: {stats['total_learnings']}\n"
        result += f"  Corrections: {stats['total_corrections']}\n"
        result += f"  Projects: {', '.join(stats['projects']) or 'none'}\n"
        result += f"  API calls: {stats.get('statistics', {}).get('total_calls', 0)}\n"
        result += f"  Last updated: {stats['last_updated']}\n"
        if stats.get("learnings_by_category"):
            result += "\n  Learnings by category:\n"
            for cat, count in sorted(stats["learnings_by_category"].items()):
                result += f"    {cat}: {count}\n"
        active = sessions.list_sessions()
        if active:
            result += f"\n  Active sessions: {len(active)}\n"
            for s in active:
                result += f"    - {s['id']}: {s['task'][:60]} (turn {s['turn_count']}, {s['status']})\n"
        return result

    elif detail == "full" or detail == "category":
        learnings = memory.query_learnings(category=category_filter or None, project=project_filter or None, limit=50)
        result = f"GROK MEMORY ({len(learnings)} learnings"
        if category_filter:
            result += f", category={category_filter}"
        if project_filter:
            result += f", project={project_filter}"
        result += ")\n\n"
        for entry in learnings:
            conf = f"[conf={entry.get('confidence', '?')}]"
            src = f"[{entry.get('source', '?')}]"
            result += f"  {entry['id']} [{entry['category']}] {src} {conf} {entry['content']}\n"
            if entry.get("project"):
                result += f"       project: {entry['project']}\n"
        return result

    return f"Error: Unknown detail level '{detail}'. Use summary, full, or category."


def _handle_grok_multi_review(arguments: dict[str, Any]) -> str:
    """Run the 2-call Grok review pattern in parallel.

    Call 1: Code quality + integration contract compliance
    Call 2: Regulatory compliance + knowledge extraction
    """
    code = arguments.get("code", "")
    contracts_context = arguments.get("contracts_context", "")
    project = arguments.get("project", "")

    if "grok" not in AI_CLIENTS:
        return "Error: Grok is not available for multi-review"

    # Build system prompts for both calls
    sys_prompt_quality = context_builder.build_system_prompt(
        tool_name="grok_code_review",
        project=project,
        task_description=code[:500],
        extra_instructions=(
            "You are performing Call 1 of a 2-call review pattern. "
            "Focus on: (1) Code quality, tests, error handling. "
            "(2) Integration contract compliance — does this match the provided contracts? "
            "Check header propagation, event schemas, hardcoded values."
        ),
    )

    sys_prompt_compliance = context_builder.build_system_prompt(
        tool_name="grok_execute_task",
        project=project,
        task_description=code[:500],
        extra_instructions=(
            "You are performing Call 2 of a 2-call review pattern. "
            "Focus on: (1) Regulatory / 21 CFR Part 11 compliance. "
            "(2) Extract 0-3 reusable learnings for future sessions. "
            'Format learnings as [LEARNING category="..."] content [/LEARNING] blocks.'
        ),
    )

    # Build prompts
    integration_prompt = context_builder.build_integration_review_prompt(code=code, contracts_context=contracts_context)
    compliance_prompt = (
        f"## Compliance & Knowledge Review\n\n"
        f"Review this code for regulatory compliance and extract learnings:\n\n"
        f"```\n{code}\n```\n"
    )
    if contracts_context:
        compliance_prompt += f"\n### Service Contracts Context\n```\n{contracts_context}\n```\n"
    compliance_prompt += (
        "\n### Expected Output\n"
        "1. **Compliance issues** — Part 11, audit trail, data integrity concerns\n"
        "2. **Security review** — authentication, authorization, input validation\n"
        "3. **Extracted learnings** — 0-3 [LEARNING] blocks for the knowledge base\n"
    )

    # Fire both calls in parallel
    calls = [
        {
            "label": "quality_integration",
            "ai_name": "grok",
            "prompt": integration_prompt,
            "temperature": 0.3,
            "system_prompt": sys_prompt_quality,
            "tool_name": "grok_code_review",
            "project": project,
        },
        {
            "label": "compliance_knowledge",
            "ai_name": "grok",
            "prompt": compliance_prompt,
            "temperature": 0.3,
            "system_prompt": sys_prompt_compliance,
            "tool_name": "grok_execute_task",
            "project": project,
        },
    ]

    results = call_ai_parallel(calls)

    # Format combined output
    output = "GROK MULTI-REVIEW (2 parallel calls)\n\n"
    for r in results:
        label = r["label"].replace("_", " ").title()
        display_text = memory.strip_learning_blocks(r["result"])
        output += f"{'=' * 60}\n## {label}\n{'=' * 60}\n\n{display_text}\n\n"

    return output


def _handle_grok_retrieve_context(arguments: dict[str, Any]) -> str:
    """Retrieve relevant learnings via RAG without calling Grok."""
    task = arguments.get("task", "")
    n_results = arguments.get("n_results", 20)
    category = arguments.get("category", "") or None
    project = arguments.get("project", "") or None

    if not task:
        return "Error: 'task' description is required"

    # Try RAG first
    import contextlib

    rag_results: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        rag_results = rag_memory.query_relevant(
            query_text=task,
            n_results=n_results,
            category_filter=category,
            project_filter=project,
        )

    if rag_results:
        output = f"CONTEXT RETRIEVAL (RAG semantic search, {len(rag_results)} results)\n\n"
        for entry in rag_results:
            dist_pct = f"{(1 - entry.get('distance', 0)) * 100:.0f}%"
            output += f"- [{entry['category']}] (relevance: {dist_pct}) {entry['content']}"
            if entry.get("project"):
                output += f" (project: {entry['project']})"
            output += "\n"

        # Also include RAG stats
        stats = rag_memory.get_stats()
        output += f"\nRAG stats: {stats.get('count', 0)} total learnings indexed"
        return output

    # Fallback to JSON-based query
    learnings = memory.query_learnings(
        category=category,
        project=project,
        limit=n_results,
    )

    if not learnings:
        return "CONTEXT RETRIEVAL: No relevant learnings found."

    output = f"CONTEXT RETRIEVAL (JSON fallback, {len(learnings)} results)\n\n"
    for entry in learnings:
        output += f"- [{entry['category']}] {entry['content']}"
        if entry.get("project"):
            output += f" (project: {entry['project']})"
        output += "\n"
    return output


def _handle_grok_multi_agent(arguments: dict[str, Any]) -> str:
    """Handle Grok multi-agent calls for complex analysis tasks."""
    prompt = arguments.get("prompt", "")
    context = arguments.get("context", "")
    project = arguments.get("project", "")

    if not prompt:
        return "Error: 'prompt' is required"

    grok_creds = CREDENTIALS.get("grok", {})
    if not grok_creds.get("enabled", False):
        return "Error: Grok is not available or not configured"

    # Build system prompt with memory context
    sys_prompt = context_builder.build_system_prompt(
        tool_name="grok_multi_agent",
        project=project,
        extra_instructions=(
            "You are Grok's multi-agent team — a group of AI agents deliberating together. "
            "Provide thorough, well-reasoned analysis. This tool is reserved for complex tasks "
            "that benefit from multi-perspective deliberation."
        ),
    )

    # Combine prompt and context
    full_prompt = prompt
    if context:
        full_prompt = f"{prompt}\n\n## Additional Context\n{context}"

    result = call_grok_multi_agent(
        prompt=full_prompt,
        temperature=0.6,
        system_prompt=sys_prompt,
        tool_name="grok_multi_agent",
        project=project,
    )

    display_text = memory.strip_learning_blocks(result)
    return f"GROK MULTI-AGENT RESULT:\n\n{display_text}"


def _handle_grok_auto_review(arguments: dict[str, Any]) -> str:
    """Auto-review: evaluate thresholds, trigger Grok review if needed.

    Uses the threshold engine (auto_review module) to decide whether a review
    is warranted, then internally calls grok_code_review + grok_execute_task
    via the parallel call pattern (same as grok_multi_review).
    """
    changed_files = arguments.get("changed_files", [])
    diff_summary = arguments.get("diff_summary", "")
    project = arguments.get("project", "")
    skip_review = arguments.get("skip_review", False)
    force_review = arguments.get("force_review", False)

    if not changed_files:
        return json.dumps(
            {
                "review_triggered": False,
                "review_type": "skipped",
                "threshold_reason": "No changed files provided",
                "findings": None,
                "recommendation": "proceed",
            },
            indent=2,
        )

    # Evaluate thresholds
    evaluation = auto_review.evaluate_thresholds(
        changed_files=changed_files,
        diff_summary=diff_summary,
        skip_review=skip_review,
        force_review=force_review,
    )

    # If review not triggered, return early
    if not evaluation["review_triggered"]:
        return json.dumps(
            {
                "review_triggered": False,
                "review_type": evaluation["review_type"],
                "threshold_reason": evaluation["threshold_reason"],
                "findings": None,
                "recommendation": "proceed",
            },
            indent=2,
        )

    # Review is triggered — check Grok availability
    if "grok" not in AI_CLIENTS:
        return json.dumps(
            {
                "review_triggered": True,
                "review_type": evaluation["review_type"],
                "threshold_reason": evaluation["threshold_reason"],
                "findings": None,
                "recommendation": "discuss_with_user",
                "error": "Grok is not available — review was triggered but cannot be executed",
            },
            indent=2,
        )

    # Build the code context from file list and diff summary
    code_context = f"## Changed Files ({len(changed_files)} files)\n"
    for f in changed_files:
        code_context += f"- {f}\n"
    if diff_summary:
        code_context += f"\n## Diff Summary\n{diff_summary}\n"

    code_context += f"\n## Threshold Trigger\n{evaluation['threshold_reason']}\n"
    code_context += f"Matched patterns: {', '.join(evaluation['matched_patterns'])}\n"

    review_type = evaluation["review_type"]

    # Build review calls based on review type
    calls: list[dict[str, Any]] = []

    if review_type in ("full", "deploy"):
        # Call 1: Quality + Integration review
        sys_prompt_1 = context_builder.build_system_prompt(
            tool_name="grok_code_review",
            project=project,
            task_description=diff_summary or f"Review of {len(changed_files)} changed files",
            extra_instructions=(
                f"AUTO-REVIEW triggered ({review_type}): {evaluation['threshold_reason']}. "
                "Focus on: (1) Code quality and correctness. "
                "(2) Integration contract compliance — API contracts, header propagation, tenant isolation. "
                "Return your findings with clear severity levels (critical/warning/info). "
                "Be specific about file paths and line-level issues where possible."
            ),
        )

        prompt_1 = (
            f"## Auto-Review: Quality + Integration Check\n\n"
            f"{code_context}\n\n"
            "Analyze these changes for:\n"
            "1. **Code quality issues** — bugs, error handling gaps, test coverage\n"
            "2. **Integration risks** — contract violations, missing headers, tenant leaks\n"
            "3. **Specific recommendations** with severity (critical/warning/info)\n"
        )

        calls.append(
            {
                "label": "quality_integration",
                "ai_name": "grok",
                "prompt": prompt_1,
                "temperature": 0.3,
                "system_prompt": sys_prompt_1,
                "tool_name": "grok_code_review",
                "project": project,
            }
        )

        # Call 2: Compliance + deploy parity review
        focus_2 = "deploy parity and environment consistency" if review_type == "deploy" else "compliance and security"
        sys_prompt_2 = context_builder.build_system_prompt(
            tool_name="grok_execute_task",
            project=project,
            task_description=diff_summary or f"Compliance review of {len(changed_files)} changed files",
            extra_instructions=(
                f"AUTO-REVIEW triggered ({review_type}): {evaluation['threshold_reason']}. "
                f"Focus on: {focus_2}. "
                "Check for: regulatory compliance, audit trail gaps, security concerns, "
                "and environment-specific configuration drift. "
                "Return findings with severity levels."
            ),
        )

        prompt_2 = (
            f"## Auto-Review: Compliance + {'Deploy Parity' if review_type == 'deploy' else 'Security'} Check\n\n"
            f"{code_context}\n\n"
            "Analyze these changes for:\n"
            "1. **Compliance issues** — audit trail, data integrity, regulatory concerns\n"
            "2. **Security review** — authentication, authorization, input validation\n"
        )
        if review_type == "deploy":
            prompt_2 += "3. **Deploy parity** — environment consistency, config drift, infrastructure changes\n"
        else:
            prompt_2 += "3. **Cross-cutting concerns** — logging, monitoring, error propagation\n"

        calls.append(
            {
                "label": "compliance_review",
                "ai_name": "grok",
                "prompt": prompt_2,
                "temperature": 0.3,
                "system_prompt": sys_prompt_2,
                "tool_name": "grok_execute_task",
                "project": project,
            }
        )

    elif review_type == "integration":
        # Single call: focused integration review
        sys_prompt = context_builder.build_system_prompt(
            tool_name="grok_code_review",
            project=project,
            task_description=diff_summary or f"Integration review of {len(changed_files)} changed files",
            extra_instructions=(
                f"AUTO-REVIEW triggered (integration): {evaluation['threshold_reason']}. "
                "Focus specifically on API contracts, route definitions, middleware chains, "
                "and service boundary correctness."
            ),
        )

        prompt = (
            f"## Auto-Review: Integration Check\n\n"
            f"{code_context}\n\n"
            "Analyze these changes for:\n"
            "1. **Route/controller correctness** — URL patterns, HTTP methods, middleware ordering\n"
            "2. **API contract compliance** — request/response shapes, status codes\n"
            "3. **Middleware chain** — correct ordering, context propagation\n"
            "4. **Specific recommendations** with severity (critical/warning/info)\n"
        )

        calls.append(
            {
                "label": "integration_review",
                "ai_name": "grok",
                "prompt": prompt,
                "temperature": 0.3,
                "system_prompt": sys_prompt,
                "tool_name": "grok_code_review",
                "project": project,
            }
        )

    # Execute the review call(s)
    results = call_ai_parallel(calls)

    # Parse findings from results
    quality_text = ""
    compliance_text = ""
    for r in results:
        clean = memory.strip_learning_blocks(r["result"])
        if r["label"] in ("quality_integration", "integration_review"):
            quality_text = clean
        elif r["label"] == "compliance_review":
            compliance_text = clean

    findings = auto_review.parse_review_findings(quality_text, compliance_text)

    # Extract learnings from results
    for r in results:
        learnings = memory.extract_learnings(r["result"])
        for entry in learnings:
            findings["learnings"].append(entry["content"])

    recommendation = auto_review.determine_recommendation(findings)

    # Build structured response
    response = {
        "review_triggered": True,
        "review_type": review_type,
        "threshold_reason": evaluation["threshold_reason"],
        "findings": findings,
        "recommendation": recommendation,
    }

    # Also build a human-readable summary
    summary = f"GROK AUTO-REVIEW ({review_type.upper()})\n"
    summary += f"Trigger: {evaluation['threshold_reason']}\n"
    summary += f"Files: {len(changed_files)} | Patterns: {', '.join(evaluation['matched_patterns'])}\n\n"

    for section in ("quality", "integration", "compliance"):
        s = findings[section]
        status_icon = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}.get(s["status"], "?")
        summary += f"  {section.title()}: [{status_icon}]"
        if s["issues"]:
            summary += f" ({len(s['issues'])} issues)"
        summary += "\n"

    summary += f"\nRecommendation: {recommendation.upper()}\n"

    if findings.get("learnings"):
        summary += f"\nLearnings extracted: {len(findings['learnings'])}\n"

    summary += f"\n--- Structured Response ---\n{json.dumps(response, indent=2)}"

    # Append raw Grok output for full context
    summary += "\n\n--- Raw Review Output ---\n"
    for r in results:
        label = r["label"].replace("_", " ").title()
        clean = memory.strip_learning_blocks(r["result"])
        summary += f"\n{'=' * 50}\n## {label}\n{'=' * 50}\n{clean}\n"

    return summary


# ── Legacy Multi-AI Handlers ────────────────────────────────────────────────


def _handle_ai_debate(arguments: dict[str, Any]) -> str:
    topic = arguments.get("topic", "")
    ai1 = arguments.get("ai1", "gemini")
    ai2 = arguments.get("ai2", "grok")
    prompt1 = f"You are debating the topic: '{topic}'. Present your argument in favor of your position. Be persuasive and use examples."
    prompt2 = f"You are debating the topic: '{topic}'. Present a counter-argument to the previous position. Be persuasive and use examples."
    response1 = call_ai(ai1, prompt1, 0.8)
    response2 = call_ai(ai2, prompt2, 0.8)
    return (
        f"AI DEBATE: {topic}\n\n"
        f"## {ai1.upper()}'s Opening Argument:\n{response1}\n\n"
        f"## {ai2.upper()}'s Counter-Argument:\n{response2}\n\n"
        f"---\nBoth AIs presented their best arguments."
    )


def _handle_collaborative_solve(arguments: dict[str, Any]) -> str:
    problem = arguments.get("problem", "")
    approach = arguments.get("approach", "sequential")
    if approach == "sequential":
        result = "COLLABORATIVE PROBLEM SOLVING (Sequential)\n\n"
        for i, ai_name in enumerate(AI_CLIENTS.keys(), 1):
            prompt = f"Step {i}: Analyze this problem: {problem}. Build on previous insights if any, and provide your unique perspective and solution approach."
            response = call_ai(ai_name, prompt, 0.6)
            result += f"## Step {i} - {ai_name.upper()} Analysis:\n{response}\n\n"
    else:
        result = call_multiple_ais(f"Solve this complex problem: {problem}", list(AI_CLIENTS.keys()), 0.6)
    return result


def _handle_ai_consensus(arguments: dict[str, Any]) -> str:
    question = arguments.get("question", "")
    options = arguments.get("options", "")
    prompt = f"Question: {question}"
    if options:
        prompt += f"\nAvailable options: {options}"
    prompt += "\nProvide your recommendation and reasoning. Be concise but thorough."
    responses = []
    for ai_name in AI_CLIENTS:
        response = call_ai(ai_name, prompt, 0.4)
        responses.append(f"## {ai_name.upper()} Recommendation:\n{response}")
    return "AI CONSENSUS ANALYSIS\n\n" + "\n\n".join(responses)


# ─── v5: Always-on Agent Handlers ──────────────────────────────────────────


def _handle_agent_watcher_start(arguments: dict[str, Any]) -> str:
    project_root = arguments.get("project_root", "")
    config_path = arguments.get("config_path", "")

    if not project_root:
        return "Error: project_root is required"

    root = Path(project_root)
    if not root.exists():
        return f"Error: project root does not exist: {project_root}"

    # Look for watcher config
    cfg_path = Path(config_path) if config_path else root / "watcher-config.json"

    if not cfg_path.exists():
        # Create a minimal config dict and write it so from_file can load it
        default_config = {
            "enabled": True,
            "project_root": str(root),
            "watch_paths": [
                str(root / "services"),
                str(root / "frontend" / "src"),
                str(root / "contracts"),
            ],
            "contracts_path": str(root / "contracts"),
            "integration_contracts": str(root / "INTEGRATION_CONTRACTS.md"),
        }
        cfg_path = root / "watcher-config.json"
        cfg_path.write_text(json.dumps(default_config, indent=2), encoding="utf-8")

    def on_change(event: Any) -> None:
        # Record the event — workflow submission requires async context
        logger.info("Watcher event: %s %s", event.event_type, event.path)

    file_watcher = watcher.get_watcher()
    ok = file_watcher.start(cfg_path, on_change)

    if _control_plane:
        _control_plane.set_watcher(file_watcher)

    if ok:
        config = file_watcher.get_config()
        watch_paths = config.get("watch_paths", []) if config else []
        return f"File watcher started. Monitoring: {watch_paths}"
    return "File watcher could not be started (check config or logs)."


def _handle_agent_watcher_stop(arguments: dict[str, Any]) -> str:
    file_watcher = watcher.get_watcher()
    if file_watcher.is_running():
        file_watcher.stop()
        return "File watcher stopped."
    return "File watcher was not running."


def _handle_agent_watcher_status(arguments: dict[str, Any]) -> str:
    file_watcher = watcher.get_watcher()
    running = file_watcher.is_running()
    events = file_watcher.get_recent_events(limit=10)

    lines = [f"Watcher: {'RUNNING' if running else 'STOPPED'}"]
    if events:
        lines.append(f"Recent events ({len(events)}):")
        for e in events:
            lines.append(f"  [{e['event_type']}] {e['path']} (service: {e.get('service', 'unknown')})")
    else:
        lines.append("No recent events.")

    # Workflow status
    completed = _workflow_manager.get_completed(limit=5)
    lines.append(f"\nWorkflows: {len(completed)} recently completed")

    return "\n".join(lines)


def _handle_agent_audit_scan(arguments: dict[str, Any]) -> str:
    project_root = arguments.get("project_root", "")
    service = arguments.get("service", "")

    if not project_root:
        return "Error: project_root is required"

    root = Path(project_root)
    contracts_path = root / "contracts"

    if not contracts_path.exists():
        return f"Error: contracts/ directory not found at {contracts_path}"

    if service:
        service_path = root / "services" / service
        if not service_path.exists():
            return f"Error: service directory not found: {service_path}"
        findings = _auditor.scan_service(service, service_path)
    else:
        findings = _auditor.scan_all(str(root), str(contracts_path))

    # Sync findings to lifecycle manager so dashboard can display them
    if _lifecycle_manager and findings:
        for f in findings:
            if hasattr(f, "to_dict"):
                fd = f.to_dict()
            else:
                fd = {
                    "id": f.id,
                    "service": f.service,
                    "severity": f.severity,
                    "description": f.description,
                    "file": getattr(f, "file", ""),
                    "line": getattr(f, "line", 0),
                    "contract_ref": getattr(f, "contract_ref", ""),
                }
            # Auditor uses "pending", lifecycle uses "detected" — normalize
            fd["status"] = "detected"
            _lifecycle_manager.add_finding(fd)

    if service:
        return f"Scanned {service}: {len(findings)} findings\n" + "\n".join(
            f"  [{f.severity}] {f.description}" for f in findings
        )
    else:
        return f"Scanned all services: {len(findings)} findings\n" + "\n".join(
            f"  [{f.severity}] [{f.service}] {f.description}" for f in findings
        )


def _handle_agent_audit_findings(arguments: dict[str, Any]) -> str:
    status = arguments.get("status", "pending")

    if status == "pending":
        findings = _auditor.get_pending_recommendations()
    elif status == "all":
        findings = _auditor.get_findings()
    else:
        findings = _auditor.get_findings(status=status)

    if not findings:
        return f"No {status} findings."

    lines = [f"{len(findings)} {status} findings:"]
    for f in findings:
        lines.append(f"  [{f['id']}] [{f['severity']}] [{f.get('service', '?')}] {f['description']}")
        if f.get("contract_reference"):
            lines.append(f"    Contract: {f['contract_reference']}")
    return "\n".join(lines)


def _handle_agent_control_plane(arguments: dict[str, Any]) -> str:
    action = arguments.get("action", "status")
    port = int(arguments.get("port", 3100))

    global _control_plane

    if action == "start":
        if _control_plane is None:
            _control_plane = control_plane.get_control_plane()
            _control_plane.set_workflow_manager(_workflow_manager)
            _control_plane.set_auditor(_auditor)
        _control_plane.start(port=port)
        return f"Agent Monitor dashboard started at http://localhost:{port}/dashboard"

    elif action == "stop":
        if _control_plane:
            _control_plane.stop()
            return "Agent Monitor dashboard stopped."
        return "Control plane was not running."

    else:  # status
        if _control_plane and _control_plane._server_thread is not None and _control_plane._server_thread.is_alive():
            return "Agent Monitor: RUNNING at http://localhost:3100/dashboard"
        return "Agent Monitor: NOT RUNNING. Use action='start' to launch."


# ─── v6 Intelligent Findings Handlers ────────────────────────────────────────


def _handle_agent_load_feature_map(arguments: dict[str, Any]) -> str:
    yaml_path = arguments.get("yaml_path", "")
    if not yaml_path:
        return "Error: yaml_path is required"
    path = Path(yaml_path)
    if not path.exists():
        return f"Error: {yaml_path} not found"
    try:
        fm = feature_map.load_map(path)
        all_features = fm.get_all_features()
        feature_names = [f.name for f in all_features]
        _auditor.set_feature_map(fm)
        return f"Feature map loaded: {len(feature_names)} features — {', '.join(feature_names)}"
    except Exception as e:
        return f"Error loading feature map: {e}"


def _handle_agent_analyze_findings(arguments: dict[str, Any]) -> str:
    service_filter = arguments.get("service", "")
    findings = _auditor.get_findings()
    if service_filter:
        findings = [f for f in findings if f.get("service") == service_filter]
    pending = [f for f in findings if f.get("status", "pending") == "pending"]
    if not pending:
        return "No pending findings to analyze."

    fm = feature_map.get_map()

    def ai_caller(prompt: str, _context: str = "") -> str:
        sys_prompt = context_builder.build_system_prompt(tool_name="grok_code_review", project="")
        return call_ai("grok", prompt, 0.3, system_prompt=sys_prompt, tool_name="agent_analyze_findings")

    try:
        analyzed = finding_analyzer.batch_analyze(pending, fm, ai_caller)
        # Store in lifecycle manager if available
        if _lifecycle_manager:
            for f in analyzed:
                _lifecycle_manager.add_finding(f)
        count = len(analyzed)
        approve_count = sum(1 for f in analyzed if f.get("ai_recommendation") == "approve")
        dismiss_count = count - approve_count
        return (
            f"Analyzed {count} findings. AI recommends: {approve_count} approve, {dismiss_count} dismiss.\n"
            "View details in the dashboard at http://127.0.0.1:3100/dashboard or use agent_audit_findings."
        )
    except Exception as e:
        return f"Analysis error: {e}"


def _handle_agent_finding_action(arguments: dict[str, Any]) -> str:
    finding_id = arguments.get("finding_id", "")
    action = arguments.get("action", "")
    reason = arguments.get("reason", "")

    if not finding_id or not action:
        return "Error: finding_id and action are required"

    if _lifecycle_manager is None:
        return "Error: Finding lifecycle manager not initialized"

    try:
        if action == "approve":
            _lifecycle_manager.approve(finding_id)
            decision_learner.record_decision({"id": finding_id}, action="approve")
            return f"Finding {finding_id} approved. It will be included in the next sprint fix batch."
        elif action == "dismiss":
            dismiss_reason = reason or "intentional"
            _lifecycle_manager.dismiss(finding_id, dismiss_reason)
            decision_learner.record_decision({"id": finding_id}, action="dismiss", reason=dismiss_reason)
            return f"Finding {finding_id} dismissed (reason: {dismiss_reason}). Decision recorded for learning."
        else:
            return f"Error: Unknown action '{action}'. Use 'approve' or 'dismiss'."
    except Exception as e:
        return f"Error: {e}"


def _handle_agent_sprint_prompt(arguments: dict[str, Any]) -> str:
    service = arguments.get("service", "")
    if _lifecycle_manager is None:
        return "Error: Finding lifecycle manager not initialized"
    try:
        prompt = _lifecycle_manager.get_sprint_prompt(service=service)
        if not prompt:
            return "No approved findings to fix."
        return prompt
    except Exception as e:
        return f"Error: {e}"


def _handle_agent_findings_reminder(arguments: dict[str, Any]) -> str:
    if _lifecycle_manager is None:
        return "No findings system initialized."
    try:
        if _lifecycle_manager.should_remind():
            return _lifecycle_manager.get_reminder_message()
        return "No findings need attention right now."
    except Exception as e:
        return f"Error: {e}"


# ─── Main Server Loop ───────────────────────────────────────────────────────


def main():
    """Main MCP server loop."""
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            request = json.loads(line.strip())
            method = request.get("method")
            request_id = request.get("id")
            params = request.get("params", {})

            if method == "initialize":
                response = handle_initialize(request_id)
            elif method == "tools/list":
                response = handle_tools_list(request_id)
            elif method == "tools/call":
                response = handle_tool_call(request_id, params)
            elif method == "notifications/initialized":
                continue  # Client notification, no response needed
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }

            send_response(response)

        except json.JSONDecodeError:
            continue
        except EOFError:
            break
        except Exception as e:
            if "request_id" in locals():
                send_response(
                    {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": f"Internal error: {e!s}"}}
                )


if __name__ == "__main__":
    main()
