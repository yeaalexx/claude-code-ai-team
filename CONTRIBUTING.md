# Contributing

Thanks for your interest in contributing to Claude Code AI Team.

## Reporting Bugs

Open an issue using the **Bug Report** template. Include:
- Your OS and PowerShell/bash version
- The full error output from the setup script
- Whether you're using Claude Code CLI or the VS Code extension

## Suggesting Features

Open an issue using the **Feature Request** template.

## Pull Requests

1. Fork the repo and create a branch from `main`.
2. If you changed the setup scripts, test on both macOS/Linux (bash) and Windows (PowerShell 5.1).
3. Run `shellcheck setup.sh` and fix any warnings.
4. Keep PRs focused — one change per PR.

## Updating the Pinned MCP Server Version

The setup scripts pin the upstream MCP bridge to a specific commit SHA for supply-chain safety. To update it:

1. Check the latest commit on [RaiAnsar/claude_code-multi-AI-MCP](https://github.com/RaiAnsar/claude_code-multi-AI-MCP).
2. Review the diff between the current pinned SHA and the new one.
3. Update `MCP_SERVER_SHA` in both `setup.sh` and `setup.ps1`.
4. Test the setup end-to-end.

## Code Style

- Shell scripts: follow [ShellCheck](https://www.shellcheck.net/) recommendations
- PowerShell: target PS 5.1 compatibility (no PS 7-only features)
- Markdown: one sentence per line where practical
