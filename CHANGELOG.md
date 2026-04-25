# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [4.0.0] - 2026-03-21

### Added
- **RAG Semantic Memory** (`server/rag_memory.py`): New module providing semantic search over learnings using ChromaDB with built-in lightweight embeddings (onnxruntime, no torch required)
  - Persistent ChromaDB client at `~/.claude-mcp-servers/multi-ai-collab/memory/chroma/`
  - `query_relevant()` — semantic search by natural language query with optional category/project filters
  - `add_learning()` — writes to both ChromaDB and JSON for backward compatibility
  - `migrate_from_json()` — idempotent one-time migration of existing grok-memory.json learnings
  - `get_stats()` — collection count and category breakdown
  - Graceful fallback: all functions return empty/no-op if chromadb is not installed
- **Parallel Grok Calls** (`call_ai_parallel()`): Fires multiple Grok calls simultaneously using `ThreadPoolExecutor`, returns all results in order
- **`grok_multi_review` tool**: Replaces the manual 2-call review pattern — fires quality+integration AND compliance+knowledge calls in parallel, returns combined result
- **`grok_retrieve_context` tool**: Queries RAG for relevant learnings without calling Grok — zero API cost context retrieval
- **RAG-aware context builder**: `_get_relevant_learnings_rag()` uses the task description as semantic search query; `_get_relevant_learnings()` tries RAG first, falls back to JSON filtering
- **`task_description` parameter** on `build_system_prompt()`: enables RAG-based learning selection for any tool call

### Changed
- **Server version**: 3.0.0 -> 4.0.0
- **memory.py**: `add_learning()` now also writes to ChromaDB when available; new `migrate_to_rag()` function
- **context_builder.py**: `_get_relevant_learnings()` tries RAG semantic search first, falls back to category-based JSON filtering
- **Server startup**: Initializes RAG memory and runs idempotent JSON-to-ChromaDB migration
- **Setup scripts**: Copy `rag_memory.py`, note about first-run embedding model download
- **requirements.txt**: Added `chromadb==0.6.3`

### Migration from v0.3.0
- **No breaking changes**: All v3 functionality is preserved
- **Memory is preserved**: Existing `grok-memory.json` works unchanged; learnings are automatically migrated to ChromaDB on first startup
- **RAG is optional**: If chromadb is not installed, the server falls back to JSON-based filtering (same as v3)
- To upgrade: run `setup.ps1`/`setup.sh` to update server code and install chromadb
- First run after upgrade will be slower (downloading ~200MB embedding model)

## [0.3.0] - 2026-03-20

### Added
- **Integration Architecture**: New `contracts/` directory with templates for API contracts, event catalogs, shared headers, tenant rules, and error codes
- **INTEGRATION_CONTRACTS.md template**: Central hub for cross-service dependency matrix, universal rules, and anti-patterns — auto-created in multi-service projects
- **LEARNINGS_KB.md template**: Distilled knowledge base with categorized patterns, separate from the collaboration log
- **Integration-First Protocol**: Mandatory pre-flight checks before any cross-service change (read contracts, check APIs, never hardcode shared values)
- **2-Call Grok Review Pattern**: Structured review workflow — Call 1 for quality+integration, Call 2 for compliance+knowledge extraction
- **Contract-Driven Development**: Edit contract first, implement second, verify match
- **Context Budget Management**: Guidelines for efficient context window usage (selective loading, distillation, file size caps)
- **Learning consolidation** (`memory.consolidate_learnings`): Prevents unbounded memory growth by pruning low-confidence entries per category
- **Learning summary** (`memory.get_learning_summary`): Condensed category-grouped summary for quick context injection
- **Integration review prompt builder** (`context_builder.build_integration_review_prompt`): Formats code + contracts for the 2-call review pattern
- **Multi-category learning queries** (`memory.query_learnings(categories=[...])`)
- New learning categories: `integration`, `compliance`, `domain`, `ui-ux`

### Changed
- **Token budgets doubled**: `DEFAULT_TOKEN_BUDGET` 8K → 16K, `SESSION_TOKEN_BUDGET` 50K → 80K (leveraging Grok 4.20's larger context)
- **Broader learning retrieval**: None-category queries now fetch up to 80 learnings (was 50), with relevance boost for integration/compliance categories
- **Global CLAUDE.md**: Completely rewritten with integration protocol, 2-call review pattern, contract-driven development, and context budget management
- **AI_TEAM_SYNERGY.md template**: Now includes Grok involvement table, rolling maintenance instructions, and integration-specific sections
- **Category detection**: `_detect_category` now recognizes integration, compliance, and domain-specific keywords
- **Auto-bootstrap**: Now detects multi-service projects and creates `INTEGRATION_CONTRACTS.md`, `LEARNINGS_KB.md`, and `contracts/` skeleton

### Migration from v0.2.0
- **No breaking changes**: All v2 functionality is preserved
- **Memory is preserved**: Existing `grok-memory.json` works unchanged with v3
- **New files are additive**: `contracts/`, `INTEGRATION_CONTRACTS.md`, `LEARNINGS_KB.md` are auto-created only in new projects — existing projects are not modified
- To adopt in existing projects: run `setup.ps1`/`setup.sh` to update server code, then ask Claude to "set up integration contracts for this project"

## [0.2.0] - 2026-02-18

### Added
- **Grok persistent memory**: Grok now has a JSON-based memory system (`grok-memory.json`) that persists across calls and sessions
- **Bidirectional learning**: Both Claude and Grok learn from each other — Claude's learnings are pushed to Grok's memory, and Grok auto-extracts learnings from its own responses
- **Multi-turn collaboration sessions** (`grok_collaborate`): Claude and Grok can have iterative conversations with consensus detection
- **Grok as agent** (`grok_execute_task`): Grok can independently execute tasks and return structured results (code, plans, reviews, diffs)
- **Memory synchronization** (`grok_memory_sync`): Push/pull learnings between Claude's markdown files and Grok's memory store
- **Session management** (`grok_session_end`): End collaboration sessions with automatic learning extraction
- **Memory status** (`grok_memory_status`): View Grok's memory state, learning counts, and active sessions
- **Context-aware system prompts**: All Grok calls now include a system prompt with Grok's identity, relevant learnings, and project context
- **Consensus detection**: Collaboration sessions track agreement/disagreement and detect when both AIs converge

### Changed
- **Server architecture**: Replaced upstream MCP server clone with modular server owned by this repo (`server/` directory with `memory.py`, `sessions.py`, `context_builder.py`)
- **Setup scripts**: Now copy server files from this repo instead of cloning upstream — full ownership of all code
- **Removed UTF-8 fix step**: The enhanced server already includes proper UTF-8 handling
- **All existing tools**: Now accept optional `project` parameter and inject memory-aware system prompts

### Removed
- Dependency on pinned upstream MCP server SHA (no longer needed — server is in this repo)

## [0.1.0] - 2026-02-18

### Added
- Automated setup scripts for macOS/Linux (bash) and Windows (PowerShell 5.1+)
- Pinned upstream MCP bridge server to known-good commit for supply-chain safety
- Isolated Python venv to avoid global pip pollution
- Pinned exact Python dependency versions for reproducibility
- Interactive API key configuration with input masking
- Global CLAUDE.md with auto-bootstrap rules for new projects
- Global ai-team-knowledge.md for cross-project learning persistence
- Per-project AI_TEAM_SYNERGY.md template (auto-created by Claude)
- MCP billing fallback protocol (graceful degradation when credits run out)
- Windows UTF-8 encoding fix (applied automatically on Windows/WSL)
- --uninstall flag for clean removal
- CI with ShellCheck linting and smoke tests
- Issue templates for bug reports and feature requests
