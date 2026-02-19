#!/usr/bin/env python3
"""
Enhanced Multi-AI MCP Server v2.0
Bidirectional learning between Claude Code and Grok with:
- Persistent memory for Grok
- Multi-turn collaboration sessions
- Agent-style task execution
- Bidirectional memory synchronization
"""

import json
import sys
import os
from typing import Dict, Any, Optional, List
from pathlib import Path

# Ensure UTF-8 output (critical on Windows where default is cp1252)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Resolve import paths — works both as a package (server/) and flat install
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR.parent))
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from server import memory, sessions, context_builder
except ImportError:
    import memory, sessions, context_builder

__version__ = "2.0.0"

# Load credentials
CREDENTIALS_FILE = SCRIPT_DIR / "credentials.json"
# If not found next to server.py, check the install directory
if not CREDENTIALS_FILE.exists():
    INSTALL_DIR = Path.home() / ".claude-mcp-servers" / "multi-ai-collab"
    CREDENTIALS_FILE = INSTALL_DIR / "credentials.json"

try:
    with open(CREDENTIALS_FILE, 'r') as f:
        CREDENTIALS = json.load(f)
except Exception as e:
    print(json.dumps({
        "jsonrpc": "2.0",
        "error": {
            "code": -32603,
            "message": f"Failed to load credentials.json: {str(e)}"
        }
    }), file=sys.stdout, flush=True)
    sys.exit(1)

# Initialize AI clients
AI_CLIENTS: Dict[str, Dict[str, Any]] = {}

# Gemini
if CREDENTIALS.get("gemini", {}).get("enabled", False):
    try:
        import google.generativeai as genai
        genai.configure(api_key=CREDENTIALS["gemini"]["api_key"])
        AI_CLIENTS["gemini"] = {
            "client": genai.GenerativeModel(CREDENTIALS["gemini"]["model"]),
            "type": "gemini"
        }
    except Exception as e:
        print(f"Warning: Gemini initialization failed: {e}", file=sys.stderr)

# Grok and OpenAI (both use OpenAI client)
if CREDENTIALS.get("grok", {}).get("enabled", False) or CREDENTIALS.get("openai", {}).get("enabled", False):
    try:
        from openai import OpenAI

        if CREDENTIALS.get("grok", {}).get("enabled", False):
            AI_CLIENTS["grok"] = {
                "client": OpenAI(
                    api_key=CREDENTIALS["grok"]["api_key"],
                    base_url=CREDENTIALS["grok"]["base_url"]
                ),
                "model": CREDENTIALS["grok"]["model"],
                "type": "openai"
            }

        if CREDENTIALS.get("openai", {}).get("enabled", False):
            AI_CLIENTS["openai"] = {
                "client": OpenAI(api_key=CREDENTIALS["openai"]["api_key"]),
                "model": CREDENTIALS["openai"]["model"],
                "type": "openai"
            }
    except Exception as e:
        print(f"Warning: OpenAI client initialization failed: {e}", file=sys.stderr)

# DeepSeek
if CREDENTIALS.get("deepseek", {}).get("enabled", False):
    try:
        from openai import OpenAI
        AI_CLIENTS["deepseek"] = {
            "client": OpenAI(
                api_key=CREDENTIALS["deepseek"]["api_key"],
                base_url=CREDENTIALS["deepseek"]["base_url"]
            ),
            "model": CREDENTIALS["deepseek"]["model"],
            "type": "openai"
        }
    except Exception as e:
        print(f"Warning: DeepSeek initialization failed: {e}", file=sys.stderr)

# Initialize memory and session systems
# Use the install directory for memory storage (persists across updates)
MEMORY_BASE = Path.home() / ".claude-mcp-servers" / "multi-ai-collab"
memory.initialize(MEMORY_BASE)
sessions.initialize(MEMORY_BASE)


# ─── Core AI Call Function (Enhanced) ────────────────────────────────────────


def send_response(response: Dict[str, Any]):
    """Send a JSON-RPC response."""
    print(json.dumps(response), flush=True)


def call_ai(
    ai_name: str,
    prompt: str,
    temperature: float = 0.7,
    system_prompt: Optional[str] = None,
    session_messages: Optional[List[Dict[str, str]]] = None,
    tool_name: str = "",
    project: str = ""
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
                )
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
                model=client_info["model"],
                messages=messages,
                temperature=temperature,
                max_tokens=8192
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
                confidence=0.85
            )

        return result_text

    except Exception as e:
        return f"Error calling {ai_name.upper()}: {str(e)}"


def call_multiple_ais(prompt: str, ai_list: List[str], temperature: float = 0.7) -> str:
    """Call multiple AIs and return combined responses."""
    results = []
    available_ais = [ai for ai in ai_list if ai in AI_CLIENTS]

    if not available_ais:
        return "Error: None of the requested AIs are available"

    for ai_name in available_ais:
        response = call_ai(ai_name, prompt, temperature)
        results.append(f"## {ai_name.upper()} Response:\n\n{response}")

    return "\n\n" + ("=" * 80 + "\n\n").join(results)


# ─── MCP Protocol Handlers ──────────────────────────────────────────────────


def handle_initialize(request_id: Any) -> Dict[str, Any]:
    """Handle MCP initialization."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "multi-ai-mcp",
                "version": __version__
            }
        }
    }


def handle_tools_list(request_id: Any) -> Dict[str, Any]:
    """List all available tools (existing + new bidirectional learning tools)."""
    tools = [
        {
            "name": "server_status",
            "description": "Get server status and available AI models",
            "inputSchema": {
                "type": "object",
                "properties": {}
            }
        }
    ]

    # ── Per-AI tools (same as v1 but with optional project param) ────────

    for ai_name in AI_CLIENTS.keys():
        tools.extend([
            {
                "name": f"ask_{ai_name}",
                "description": f"Ask {ai_name.upper()} a question",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "The question or prompt"},
                        "temperature": {"type": "number", "description": "Temperature (0.0-1.0)", "default": 0.7},
                        "project": {"type": "string", "description": "Project name for memory context", "default": ""}
                    },
                    "required": ["prompt"]
                }
            },
            {
                "name": f"{ai_name}_code_review",
                "description": f"Have {ai_name.upper()} review code for issues and improvements",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "The code to review"},
                        "focus": {"type": "string", "description": "Focus area (security, performance, readability, etc.)", "default": "general"},
                        "project": {"type": "string", "description": "Project name for memory context", "default": ""}
                    },
                    "required": ["code"]
                }
            },
            {
                "name": f"{ai_name}_think_deep",
                "description": f"Have {ai_name.upper()} do deep analysis with extended reasoning",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "Topic or problem for deep analysis"},
                        "context": {"type": "string", "description": "Additional context or constraints", "default": ""},
                        "project": {"type": "string", "description": "Project name for memory context", "default": ""}
                    },
                    "required": ["topic"]
                }
            },
            {
                "name": f"{ai_name}_brainstorm",
                "description": f"Brainstorm creative solutions with {ai_name.upper()}",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "challenge": {"type": "string", "description": "The challenge or problem to brainstorm about"},
                        "constraints": {"type": "string", "description": "Any constraints or limitations", "default": ""},
                        "project": {"type": "string", "description": "Project name for memory context", "default": ""}
                    },
                    "required": ["challenge"]
                }
            },
            {
                "name": f"{ai_name}_debug",
                "description": f"Get debugging help from {ai_name.upper()}",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string", "description": "Error message or description"},
                        "code": {"type": "string", "description": "Related code that's causing issues", "default": ""},
                        "context": {"type": "string", "description": "Additional context about the environment/setup", "default": ""},
                        "project": {"type": "string", "description": "Project name for memory context", "default": ""}
                    },
                    "required": ["error"]
                }
            },
            {
                "name": f"{ai_name}_architecture",
                "description": f"Get architecture design advice from {ai_name.upper()}",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "requirements": {"type": "string", "description": "System requirements and goals"},
                        "constraints": {"type": "string", "description": "Technical constraints, budget, timeline etc.", "default": ""},
                        "scale": {"type": "string", "description": "Expected scale (users, data, etc.)", "default": ""},
                        "project": {"type": "string", "description": "Project name for memory context", "default": ""}
                    },
                    "required": ["requirements"]
                }
            }
        ])

    # ── Multi-AI collaborative tools (when 2+ AIs enabled) ──────────────

    if len(AI_CLIENTS) > 1:
        tools.extend([
            {
                "name": "ask_all_ais",
                "description": "Ask all available AIs the same question and compare responses",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "The question to ask all AIs"},
                        "temperature": {"type": "number", "description": "Temperature for responses", "default": 0.7}
                    },
                    "required": ["prompt"]
                }
            },
            {
                "name": "ai_debate",
                "description": "Have two AIs debate a topic",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "The debate topic"},
                        "ai1": {"type": "string", "description": "First AI", "default": "gemini"},
                        "ai2": {"type": "string", "description": "Second AI", "default": "grok"}
                    },
                    "required": ["topic"]
                }
            },
            {
                "name": "collaborative_solve",
                "description": "Have multiple AIs collaborate to solve a complex problem",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "problem": {"type": "string", "description": "The complex problem to solve"},
                        "approach": {"type": "string", "description": "How to divide work (sequential, parallel, debate)", "default": "sequential"}
                    },
                    "required": ["problem"]
                }
            },
            {
                "name": "ai_consensus",
                "description": "Get consensus opinion from all available AIs",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "Question to get consensus on"},
                        "options": {"type": "string", "description": "Available options or approaches", "default": ""}
                    },
                    "required": ["question"]
                }
            }
        ])

    # ── NEW: Bidirectional Learning & Collaboration Tools ────────────────

    tools.extend([
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
                    "session_id": {"type": "string", "description": "Session ID from a previous call (omit to start new session)"},
                    "task": {"type": "string", "description": "The task or problem to collaborate on (required for new sessions)"},
                    "message": {"type": "string", "description": "Your response/follow-up in an ongoing session"},
                    "context": {"type": "string", "description": "Relevant code, files, or context (for new sessions)", "default": ""},
                    "project": {"type": "string", "description": "Project name for memory scoping", "default": ""}
                }
            }
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
                    "files": {"type": "string", "description": "Relevant file contents Grok needs to see", "default": ""},
                    "constraints": {"type": "string", "description": "Constraints: coding style, framework, patterns to follow", "default": ""},
                    "output_format": {"type": "string", "description": "Expected output: code, plan, review, diff", "default": "code"},
                    "project": {"type": "string", "description": "Project name for memory context", "default": ""}
                },
                "required": ["task"]
            }
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
                        "enum": ["push", "pull", "status"]
                    },
                    "learnings": {"type": "string", "description": "For push: learnings text to share with Grok", "default": ""},
                    "project": {"type": "string", "description": "Project scope for filtering", "default": ""},
                    "category": {"type": "string", "description": "Category filter: architecture, code, debugging, domain, all", "default": "all"}
                },
                "required": ["action"]
            }
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
                    "save_learnings": {"type": "boolean", "description": "Extract and save learnings from this session", "default": True},
                    "claude_summary": {"type": "string", "description": "Claude's summary of what was decided/learned", "default": ""}
                },
                "required": ["session_id"]
            }
        },
        {
            "name": "grok_memory_status",
            "description": "View Grok's memory state: learning counts, recent entries, projects.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "detail": {"type": "string", "description": "Level of detail: summary, full, category", "default": "summary"},
                    "project": {"type": "string", "description": "Filter by project name", "default": ""},
                    "category": {"type": "string", "description": "Filter by category", "default": ""}
                }
            }
        }
    ])

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {"tools": tools}
    }


# ─── Tool Execution ─────────────────────────────────────────────────────────


def handle_tool_call(request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle tool execution — dispatches to the appropriate handler."""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    try:
        result = _dispatch_tool(tool_name, arguments)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": result}]
            }
        }
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32603, "message": str(e)}
        }


def _dispatch_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
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
    total_configured = len([ai for ai in CREDENTIALS.keys() if CREDENTIALS[ai].get("enabled", False)])

    stats = memory.get_memory_stats()

    result = f"Multi-AI MCP Server v{__version__} (Bidirectional Learning)\n\n"
    result += f"Available AIs: {', '.join([ai.upper() for ai in available_ais])}\n"
    result += f"Status: {len(available_ais)}/{total_configured} AIs ready\n\n"
    result += "Configured Models:\n"
    for ai_name, client_info in AI_CLIENTS.items():
        model = client_info.get("model", CREDENTIALS[ai_name]["model"])
        result += f"  {ai_name.upper()}: {model}\n"

    disabled = [ai for ai in CREDENTIALS.keys() if not CREDENTIALS[ai].get("enabled", False) or ai not in AI_CLIENTS]
    if disabled:
        result += f"\nDisabled: {', '.join([ai.upper() for ai in disabled])}\n"

    result += f"\nGrok Memory: {stats['total_learnings']} learnings, {stats['total_corrections']} corrections\n"
    result += f"Active Sessions: {len(sessions.list_sessions())}\n"
    if stats.get("learnings_by_category"):
        result += "Learnings by category: " + ", ".join(
            f"{k}: {v}" for k, v in stats["learnings_by_category"].items()
        ) + "\n"

    return result


def _handle_grok_collaborate(arguments: Dict[str, Any]) -> str:
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
            tool_name="grok_collaborate",
            project=project,
            session_id=session_id
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
        return (
            f"SESSION: {session_id}\n"
            f"STATUS: {status}\n"
            f"TURN: {session['turn_count']}\n\n"
            f"---\n\n"
            f"GROK:\n{display_text}"
        )

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
        tool_name="grok_collaborate",
        project=session.get("project", ""),
        session_id=session_id
    )
    history = sessions.get_history(session_id)

    # Call Grok with full conversation history
    # The latest user message is already in history, so we send "" as prompt
    # Actually, we need the history minus the last user message, then send last as prompt
    session_messages = history[:-1]  # All except the last (which is Claude's new message)
    current_prompt = history[-1]["content"]  # Claude's latest message

    result = call_ai(
        "grok", current_prompt, 0.6,
        system_prompt=sys_prompt,
        session_messages=session_messages,
        tool_name="grok_collaborate",
        project=session.get("project", "")
    )

    # Record Grok's response
    sessions.add_turn(session_id, "assistant", result)
    status = sessions.detect_consensus(session_id, result)

    display_text = sessions.strip_status_line(result)
    display_text = memory.strip_learning_blocks(display_text)

    session = sessions.get_session(session_id)
    output = (
        f"SESSION: {session_id}\n"
        f"STATUS: {status}\n"
        f"TURN: {session['turn_count']}\n\n"
        f"---\n\n"
        f"GROK:\n{display_text}"
    )

    if status == "consensus":
        output += "\n\n--- CONSENSUS REACHED ---\nBoth AIs agree. Consider calling grok_session_end to save learnings."
    elif status == "persistent_disagreement":
        output += "\n\n--- PERSISTENT DISAGREEMENT ---\nMultiple rounds without agreement. Consider presenting both views to the user."

    return output


def _handle_grok_execute_task(arguments: Dict[str, Any]) -> str:
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
        )
    )

    # Build the agent-style user prompt
    prompt = context_builder.build_agent_prompt(
        task=task,
        files=files,
        constraints=constraints,
        output_format=output_format
    )

    result = call_ai("grok", prompt, 0.4, system_prompt=sys_prompt, tool_name="grok_execute_task", project=project)

    display_text = memory.strip_learning_blocks(result)
    return f"GROK AGENT RESULT ({output_format}):\n\n{display_text}"


def _handle_grok_memory_sync(arguments: Dict[str, Any]) -> str:
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
            category=category if category != "all" else None,
            project=project or None,
            limit=30
        )
        if not learnings:
            return "MEMORY SYNC (pull): No learnings found matching filters."

        result = f"MEMORY SYNC (pull): {len(learnings)} learnings from Grok's memory\n\n"
        for l in learnings:
            source_tag = f"[{l['source']}]" if l.get("source") else ""
            project_tag = f"(project: {l['project']})" if l.get("project") else ""
            result += f"- [{l['category']}] {source_tag} {l['content']} {project_tag}\n"
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


def _handle_grok_session_end(arguments: Dict[str, Any]) -> str:
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
        for l in extracted_learnings:
            memory.add_learning(
                source="collaboration",
                category=l["category"],
                content=l["content"],
                project=session.get("project", ""),
                confidence=0.9
            )

    # End the session (saves transcript to disk)
    transcript = sessions.end_session(session_id)

    result = f"Session {session_id} ended.\n"
    result += f"Turns: {transcript['turn_count']}\n"
    result += f"Final status: {transcript['status']}\n"
    if extracted_learnings:
        result += f"\nExtracted {len(extracted_learnings)} learnings:\n"
        for l in extracted_learnings:
            result += f"  - [{l['category']}] {l['content']}\n"
    else:
        result += "No learnings extracted.\n"

    return result


def _handle_grok_memory_status(arguments: Dict[str, Any]) -> str:
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
        learnings = memory.query_learnings(
            category=category_filter or None,
            project=project_filter or None,
            limit=50
        )
        result = f"GROK MEMORY ({len(learnings)} learnings"
        if category_filter:
            result += f", category={category_filter}"
        if project_filter:
            result += f", project={project_filter}"
        result += ")\n\n"
        for l in learnings:
            conf = f"[conf={l.get('confidence', '?')}]"
            src = f"[{l.get('source', '?')}]"
            result += f"  {l['id']} [{l['category']}] {src} {conf} {l['content']}\n"
            if l.get("project"):
                result += f"       project: {l['project']}\n"
        return result

    return f"Error: Unknown detail level '{detail}'. Use summary, full, or category."


# ── Legacy Multi-AI Handlers ────────────────────────────────────────────────


def _handle_ai_debate(arguments: Dict[str, Any]) -> str:
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


def _handle_collaborative_solve(arguments: Dict[str, Any]) -> str:
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


def _handle_ai_consensus(arguments: Dict[str, Any]) -> str:
    question = arguments.get("question", "")
    options = arguments.get("options", "")
    prompt = f"Question: {question}"
    if options:
        prompt += f"\nAvailable options: {options}"
    prompt += "\nProvide your recommendation and reasoning. Be concise but thorough."
    responses = []
    for ai_name in AI_CLIENTS.keys():
        response = call_ai(ai_name, prompt, 0.4)
        responses.append(f"## {ai_name.upper()} Recommendation:\n{response}")
    return "AI CONSENSUS ANALYSIS\n\n" + "\n\n".join(responses)


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
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }

            send_response(response)

        except json.JSONDecodeError:
            continue
        except EOFError:
            break
        except Exception as e:
            if 'request_id' in locals():
                send_response({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
                })


if __name__ == "__main__":
    main()
