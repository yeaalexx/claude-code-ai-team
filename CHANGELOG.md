# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

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
