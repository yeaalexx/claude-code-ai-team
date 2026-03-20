# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

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
- New learning categories: `integration`, `compliance`, `pharma-ux`, `pharma-eln`, `ui-ux`

### Changed
- **Token budgets doubled**: `DEFAULT_TOKEN_BUDGET` 8K → 16K, `SESSION_TOKEN_BUDGET` 50K → 80K (leveraging Grok 4.20's larger context)
- **Broader learning retrieval**: None-category queries now fetch up to 80 learnings (was 50), with relevance boost for integration/compliance categories
- **Global CLAUDE.md**: Completely rewritten with integration protocol, 2-call review pattern, contract-driven development, and context budget management
- **AI_TEAM_SYNERGY.md template**: Now includes Grok involvement table, rolling maintenance instructions, and integration-specific sections
- **Category detection**: `_detect_category` now recognizes integration, compliance, and pharma-specific keywords
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
