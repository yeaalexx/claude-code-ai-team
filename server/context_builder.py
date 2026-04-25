"""
Dynamic System Prompt Builder — v4.0

Assembles Grok's system prompt by injecting:
1. Identity (always)
2. Project context (if provided)
3. Relevant learnings (RAG semantic search when available, JSON fallback)
4. Corrections (recent, relevant)
5. Learning extraction instructions (always)
6. Collaboration protocol (for session-based calls)

v4: RAG-based semantic search for learnings via ChromaDB.

Uses a token budget to avoid exceeding context limits.
"""

import logging

try:
    from . import memory
except ImportError:
    import memory  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


# Token budget for system prompt — increased for Grok 4.20's larger context window
DEFAULT_TOKEN_BUDGET = 16000  # Was 8000; Grok 4.20 has 256K+ context
SESSION_TOKEN_BUDGET = 80000  # Was 50000; sessions benefit most from extra room

# Map tool names to learning categories for relevance filtering
TOOL_CATEGORY_MAP = {
    "ask_grok": None,  # No specific category — include top learnings from all
    "grok_code_review": "code",
    "grok_think_deep": None,
    "grok_brainstorm": None,
    "grok_debug": "debugging",
    "grok_architecture": "architecture",
    "grok_collaborate": None,
    "grok_execute_task": None,
}

# Categories that are always relevant in multi-service / cross-cutting contexts
ALWAYS_RELEVANT_CATEGORIES = {"integration", "compliance"}


def estimate_tokens(text: str) -> int:
    """Estimate token count. Heuristic: ~3.5 chars per token for English."""
    return max(1, int(len(text) / 3.5))


def build_system_prompt(
    tool_name: str = "",
    project: str | None = None,
    session_id: str | None = None,
    include_learnings: bool = True,
    extra_instructions: str = "",
    task_description: str = "",
) -> str:
    """
    Build a complete system prompt for a Grok API call.

    Args:
        tool_name: The MCP tool being called (for category filtering)
        project: Project name (for memory scoping)
        session_id: Active session ID (for session context)
        include_learnings: Whether to inject learnings
        extra_instructions: Additional tool-specific instructions

    Returns:
        Complete system prompt string
    """
    is_session = session_id is not None
    budget = SESSION_TOKEN_BUDGET if is_session else DEFAULT_TOKEN_BUDGET
    parts = []
    used_tokens = 0

    # --- Tier 1: Always included ---

    # Identity
    identity = _get_identity_prompt()
    parts.append(identity)
    used_tokens += estimate_tokens(identity)

    # Project context
    if project:
        project_ctx = _get_project_context(project)
        if project_ctx:
            parts.append(project_ctx)
            used_tokens += estimate_tokens(project_ctx)

    # Learning format instructions
    learning_instructions = _get_learning_instructions()
    parts.append(learning_instructions)
    used_tokens += estimate_tokens(learning_instructions)

    # Session collaboration protocol
    if is_session:
        collab_protocol = _get_collaboration_protocol()
        parts.append(collab_protocol)
        used_tokens += estimate_tokens(collab_protocol)

    # Extra tool-specific instructions
    if extra_instructions:
        parts.append(extra_instructions)
        used_tokens += estimate_tokens(extra_instructions)

    # --- Tier 2: Relevant learnings (if budget allows) ---

    if include_learnings:
        remaining_budget = budget - used_tokens - 500  # Reserve 500 for corrections
        if remaining_budget > 200:
            category = TOOL_CATEGORY_MAP.get(tool_name)
            learnings_text = _get_relevant_learnings(
                category=category,
                project=project,
                token_budget=remaining_budget,
                task_description=task_description,
            )
            if learnings_text:
                parts.append(learnings_text)
                used_tokens += estimate_tokens(learnings_text)

        # Recent corrections
        corrections_text = _get_relevant_corrections(category=TOOL_CATEGORY_MAP.get(tool_name), token_budget=500)
        if corrections_text:
            parts.append(corrections_text)
            used_tokens += estimate_tokens(corrections_text)

    return "\n\n".join(parts)


def _get_identity_prompt() -> str:
    """Get Grok's identity/role description."""
    mem = memory.load_memory()
    identity = mem.get("identity", {})
    role = identity.get("role", "You are Grok, an AI assistant.")
    style = identity.get("style", "Be direct and concise.")
    return f"""{role}

Communication style: {style}"""


def _get_project_context(project: str) -> str:
    """Get project-specific context from memory."""
    mem = memory.load_memory()
    ctx = mem.get("project_contexts", {}).get(project)
    if not ctx:
        return ""

    parts = [f"## Current Project: {project}"]
    if ctx.get("tech_stack"):
        parts.append(f"Tech stack: {ctx['tech_stack']}")
    if ctx.get("summary"):
        parts.append(f"Summary: {ctx['summary']}")
    return "\n".join(parts)


def _get_learning_instructions() -> str:
    """Instructions for Grok on how to report learnings."""
    return """## Memory Instructions
You have persistent memory. After each interaction, if you discover something worth
remembering for future conversations, include a [LEARNING] block at the END of your response:

[LEARNING category="architecture|code|debugging|domain|security|performance|devops|testing|integration|compliance|ui-ux|meta"]
Brief, reusable insight (1-2 sentences max). Only include learnings useful in future,
unrelated conversations. Skip learnings specific to only this prompt.
[/LEARNING]

You may include 0-3 learning blocks per response. Quality over quantity."""


def _get_collaboration_protocol() -> str:
    """Instructions for Grok during collaboration sessions."""
    return """## Collaboration Protocol
You are in a multi-turn collaboration session with Claude. You will discuss, iterate,
and work toward an agreed solution.

At the END of each response, include exactly one status line:

[STATUS: AGREE] — You agree with Claude's approach. The solution is ready.
[STATUS: DISAGREE reason="brief reason"] — You disagree. Explain why and propose alternatives.
[STATUS: PARTIAL agree="what you agree with" disagree="what you disagree with"] — Mixed.
[STATUS: PROPOSAL] — You are proposing something new for Claude to evaluate.
[STATUS: NEED_INFO question="what you need to know"] — You need more information.

Be direct about disagreements. Do not agree just to be agreeable — push back when
you see issues. Both you and Claude benefit from honest evaluation."""


def _get_relevant_learnings_rag(
    task_description: str,
    category: str | None,
    project: str | None,
    token_budget: int,
) -> str:
    """Get formatted learnings using RAG semantic search.

    Uses the task description as the search query for semantic relevance.
    Falls back to empty string if RAG is not available.
    """
    try:
        import rag_memory  # type: ignore[import-untyped]

        if not rag_memory._is_available():
            return ""

        results = rag_memory.query_relevant(
            query_text=task_description,
            n_results=40,
            category_filter=category,
            project_filter=project,
        )

        if not results:
            return ""

        header = "## Your Accumulated Learnings (semantic match)"
        if category:
            header += f" ({category})"
        lines = [header]
        tokens_used = estimate_tokens(header)

        for entry in results:
            line = f"- [{entry['category']}] {entry['content']}"
            if entry.get("project"):
                line += f" (project: {entry['project']})"
            line_tokens = estimate_tokens(line)
            if tokens_used + line_tokens > token_budget:
                break
            lines.append(line)
            tokens_used += line_tokens

        if len(lines) <= 1:
            return ""
        return "\n".join(lines)

    except Exception as e:
        logger.debug("RAG learning retrieval failed, falling back to JSON: %s", e)
        return ""


def _get_relevant_learnings(
    category: str | None,
    project: str | None,
    token_budget: int,
    task_description: str = "",
) -> str:
    """Get formatted learnings that fit within the token budget.

    Tries RAG semantic search first (when available and task_description provided),
    falls back to the original JSON-based category filtering.

    When category is None (for collaborate/execute_task/think_deep), fetches a
    broader set of learnings to give Grok maximum context. Integration-category
    learnings get a relevance boost since they're useful in multi-service contexts.
    """
    # Try RAG first if we have a task description
    if task_description:
        rag_result = _get_relevant_learnings_rag(
            task_description=task_description,
            category=category,
            project=project,
            token_budget=token_budget,
        )
        if rag_result:
            return rag_result

    # Fallback: original JSON-based filtering
    # Broader fetch for uncategorized (general) queries
    limit = 80 if category is None else 50
    learnings = memory.query_learnings(category=category, project=project, limit=limit)

    # Relevance boost: when no specific category, also pull in integration/compliance
    # learnings and interleave them near the top (they're cross-cutting and always useful)
    if category is None and learnings:
        integration_ids = {e["id"] for e in learnings if e.get("category") in ALWAYS_RELEVANT_CATEGORIES}
        if not integration_ids:
            # None were included naturally — fetch them explicitly
            extra = memory.query_learnings(categories=list(ALWAYS_RELEVANT_CATEGORIES), project=project, limit=20)
            # Merge without duplicates
            existing_ids = {e["id"] for e in learnings}
            for entry in extra:
                if entry["id"] not in existing_ids:
                    learnings.append(entry)
            # Re-sort: boost integration/compliance by treating them as +0.1 confidence
            learnings.sort(
                key=lambda x: (
                    x.get("confidence", 0.5) + (0.1 if x.get("category") in ALWAYS_RELEVANT_CATEGORIES else 0.0),
                    x.get("timestamp", ""),
                ),
                reverse=True,
            )

    if not learnings:
        return ""

    header = "## Your Accumulated Learnings"
    if category:
        header += f" ({category})"
    lines = [header]
    tokens_used = estimate_tokens(header)

    for entry in learnings:
        line = f"- [{entry['category']}] {entry['content']}"
        if entry.get("project"):
            line += f" (project: {entry['project']})"
        line_tokens = estimate_tokens(line)
        if tokens_used + line_tokens > token_budget:
            break
        lines.append(line)
        tokens_used += line_tokens

    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


def _get_relevant_corrections(category: str | None, token_budget: int) -> str:
    """Get recent corrections formatted within token budget."""
    corrections = memory.get_corrections(category=category, limit=5)
    if not corrections:
        return ""

    header = "## Recent Corrections (avoid repeating these mistakes)"
    lines = [header]
    tokens_used = estimate_tokens(header)

    for c in corrections:
        line = f"- WRONG: {c['original_claim'][:100]} → CORRECT: {c['correction'][:100]}"
        line_tokens = estimate_tokens(line)
        if tokens_used + line_tokens > token_budget:
            break
        lines.append(line)
        tokens_used += line_tokens

    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


def build_agent_prompt(task: str, files: str = "", constraints: str = "", output_format: str = "code") -> str:
    """Build the user-facing prompt for grok_execute_task."""

    format_instructions = {
        "code": (
            "Return your solution as code. Include:\n"
            "1. The complete code (not just snippets)\n"
            "2. Brief comments explaining key decisions\n"
            "3. Any caveats or assumptions"
        ),
        "plan": (
            "Return a detailed implementation plan. Include:\n"
            "1. Step-by-step approach\n"
            "2. Files to create/modify\n"
            "3. Key decisions and their rationale\n"
            "4. Potential risks"
        ),
        "review": (
            "Provide a thorough review. Include:\n"
            "1. Issues found (bugs, security, performance)\n"
            "2. Specific suggestions with code examples\n"
            "3. What's done well\n"
            "4. Priority ranking of changes"
        ),
        "diff": (
            "Return your changes as a unified diff format. Include:\n"
            "1. The diff with context lines\n"
            "2. Brief explanation of each change\n"
            "3. Any files that need to be created"
        ),
    }

    prompt = f"## Task\n{task}\n"

    if files:
        prompt += f"\n## Relevant Files\n```\n{files}\n```\n"

    if constraints:
        prompt += f"\n## Constraints\n{constraints}\n"

    prompt += f"\n## Expected Output Format\n{format_instructions.get(output_format, format_instructions['code'])}\n"

    prompt += (
        "\n## Response Structure\n"
        "Structure your response with these sections:\n"
        "### Reasoning\nWhy you chose this approach.\n"
        "### Solution\nThe actual code/plan/review/diff.\n"
        "### Confidence\nRate your confidence: HIGH / MEDIUM / LOW and explain why.\n"
        "### Caveats\nAny assumptions, limitations, or things to watch out for.\n"
        "### Alternatives Considered\nBriefly mention 1-2 alternative approaches you rejected and why.\n"
    )

    return prompt


def build_integration_review_prompt(code: str, contracts_context: str = "") -> str:
    """Build a prompt for integration-focused code review (2-call review pattern).

    Formats code alongside service contracts/interfaces so Grok can verify
    cross-service compatibility, header propagation, tenant isolation, etc.

    Args:
        code: The code to review
        contracts_context: Related API contracts, OpenAPI specs, or interface
            definitions from other services that this code must integrate with

    Returns:
        Formatted prompt string for Grok's user message
    """
    prompt = "## Integration Review\n\n"
    prompt += (
        "Review this code with a focus on **cross-service integration correctness**. "
        "Check for:\n"
        "- API contract compliance (request/response shapes, status codes)\n"
        "- Header propagation (Authorization, X-Tenant-ID, X-Request-ID)\n"
        "- Tenant isolation (tenant context not leaking across boundaries)\n"
        "- Error handling at service boundaries (timeouts, retries, circuit breaking)\n"
        "- Data format consistency (dates as ISO 8601, IDs as UUIDs, etc.)\n\n"
    )

    prompt += f"### Code Under Review\n```\n{code}\n```\n"

    if contracts_context:
        prompt += f"\n### Related Service Contracts\n```\n{contracts_context}\n```\n"

    prompt += (
        "\n### Expected Output\n"
        "1. **Contract violations** — where the code breaks API contracts\n"
        "2. **Integration risks** — subtle issues that only appear at service boundaries\n"
        "3. **Missing propagation** — headers/context that should be forwarded but aren't\n"
        "4. **Recommendations** — specific fixes with code examples\n"
    )

    return prompt
