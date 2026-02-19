# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

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
