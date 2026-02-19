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
3. **All CI checks must pass** before a PR can be merged (see below).
4. Keep PRs focused — one change per PR.

## CI Quality Gates

Every push and PR to `main` runs these checks automatically via GitHub Actions:

| Check | What it does | How to run locally |
|---|---|---|
| **Ruff lint** | Catches bugs, unused imports, style issues | `ruff check .` |
| **Ruff format** | Enforces consistent formatting | `ruff format --check .` (fix: `ruff format .`) |
| **mypy** | Static type checking on `server/` | `mypy server/` |
| **ShellCheck** | Validates bash script syntax | `shellcheck setup.sh` |
| **Unit tests** | Runs on Python 3.10, 3.11, 3.12 | `python tests/test_memory.py` etc. |
| **Smoke tests** | Validates repo structure and script syntax | `bash tests/smoke_test.sh` |

### Local dev setup

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

### Pre-submit checklist

```bash
ruff check .              # lint
ruff format .             # auto-format
mypy server/              # type check
python tests/test_memory.py
python tests/test_sessions.py
python tests/test_context_builder.py
bash tests/smoke_test.sh
```

If ruff reports fixable issues, run `ruff check --fix .` to auto-fix them.

## Updating the Pinned MCP Server Version

The setup scripts pin the upstream MCP bridge to a specific commit SHA for supply-chain safety. To update it:

1. Check the latest commit on [RaiAnsar/claude_code-multi-AI-MCP](https://github.com/RaiAnsar/claude_code-multi-AI-MCP).
2. Review the diff between the current pinned SHA and the new one.
3. Update `MCP_SERVER_SHA` in both `setup.sh` and `setup.ps1`.
4. Test the setup end-to-end.

## Code Style

- **Python**: enforced by [Ruff](https://docs.astral.sh/ruff/) (config in `pyproject.toml`) — line length 120, Python 3.10+ syntax
- **Type annotations**: checked by [mypy](https://mypy-lang.org/) — annotate function signatures, use `X | None` instead of `Optional[X]`
- **Shell scripts**: follow [ShellCheck](https://www.shellcheck.net/) recommendations
- **PowerShell**: target PS 5.1 compatibility (no PS 7-only features)
- **Markdown**: one sentence per line where practical
