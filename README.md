# Claude Code AI Team

![Version](https://img.shields.io/badge/version-0.1.0-blue)

**Persistent multi-AI collaboration for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — make Claude and Grok (or other AIs) work together with shared memory that never forgets.**

Claude Code is powerful on its own. But sometimes you want a second opinion — an independent code review, a gut-check on architecture, a fresh perspective on a stubborn bug. This setup gives Claude Code a teammate.

## What This Does

- **Claude + Grok as a team**: Claude Code can call Grok (xAI) for code review, architecture advice, debugging help, brainstorming, and deep analysis — all from within your editor
- **Persistent cross-project memory**: Learnings from any project automatically benefit all future projects via a global knowledge base
- **Per-project context**: Each project gets its own `AI_TEAM_SYNERGY.md` that's auto-created on first use
- **Auto-fallback on billing exhaustion**: When xAI credits run out, Claude seamlessly continues solo — no workflow interruption
- **Zero-config for new projects**: Global rules auto-bootstrap collaboration files in every project you open

## Architecture

```
Global (shared across all projects):
  ~/.claude/CLAUDE.md                           <-- Global rules (auto-bootstrap, collaboration, fallback)
  ~/.claude/ai-team-knowledge.md                <-- Global brain (cross-project learnings)
  ~/.claude.json                                <-- MCP server registration (user scope)
  ~/.claude-mcp-servers/multi-ai-collab/        <-- MCP bridge server (pinned commit) + credentials
  ~/.claude-mcp-servers/multi-ai-collab/.venv/  <-- Isolated Python environment

Per project (auto-created by Claude):
  ~/projects/any-project/
      +-- AI_TEAM_SYNERGY.md              <-- Project-specific AI team knowledge
      +-- CLAUDE.md                       <-- Project conventions (AI team section auto-added)

  ~/projects/another-project/
      +-- AI_TEAM_SYNERGY.md              <-- Auto-created, inherits global learnings
```

### Knowledge Flow

```
Project A learns something (e.g., "Grok caught a race condition pattern")
        |
        +---> AI_TEAM_SYNERGY.md    (Project A only)
        |
        +---> ai-team-knowledge.md  (GLOBAL -- all projects benefit)

Project B starts
        |
        +---> Reads ai-team-knowledge.md (gets Project A's learnings automatically)
        |
        +---> Creates its own AI_TEAM_SYNERGY.md (Project B context)
```

## Prerequisites

- **Claude Code** (CLI or VS Code extension) — [Install guide](https://docs.anthropic.com/en/docs/claude-code)
- **Python 3.10+** — [Download](https://www.python.org/downloads/)
- **At least one AI API key** (Grok recommended):
  - [xAI / Grok](https://console.x.ai/) — $0.20/M tokens with `grok-4-1-fast-reasoning`
  - [Google Gemini](https://aistudio.google.com/apikey) — Free tier available
  - [OpenAI](https://platform.openai.com/api-keys) — GPT-4o
  - [DeepSeek](https://platform.deepseek.com/) — Budget option

## Quick Start

### Option A: Automated Setup (Recommended)

**macOS / Linux:**
```bash
git clone https://github.com/yeaalexx/claude-code-ai-team.git
cd claude-code-ai-team
chmod +x setup.sh
./setup.sh
```

**Windows (PowerShell 5.1+):**
```powershell
git clone https://github.com/yeaalexx/claude-code-ai-team.git
cd claude-code-ai-team
.\setup.ps1
```

The setup script will:
1. Clone the MCP bridge server and pin it to a known-good commit
2. Create an isolated Python venv and install pinned dependencies
3. Prompt for your API key(s) and secure the credentials file
4. Register the MCP server globally (using the venv Python)
5. Install the global `CLAUDE.md` and knowledge base defaults
6. Apply the Windows UTF-8 fix (if on Windows)

### Option B: Manual Setup

<details>
<summary>Click to expand manual steps</summary>

#### 1. Clone the MCP bridge server
```bash
git clone https://github.com/RaiAnsar/claude_code-multi-AI-MCP.git ~/.claude-mcp-servers/multi-ai-collab
cd ~/.claude-mcp-servers/multi-ai-collab
git checkout b66b56f33fc99cf359cc797c4591589323d0ccc5
```

#### 2. Create a venv and install dependencies
```bash
python3 -m venv ~/.claude-mcp-servers/multi-ai-collab/.venv

# macOS/Linux
~/.claude-mcp-servers/multi-ai-collab/.venv/bin/pip install -r requirements.txt

# Windows
~/.claude-mcp-servers/multi-ai-collab/.venv/Scripts/pip install -r requirements.txt
```

#### 3. Configure credentials
```bash
cp ~/.claude-mcp-servers/multi-ai-collab/credentials.template.json ~/.claude-mcp-servers/multi-ai-collab/credentials.json
```

Edit `~/.claude-mcp-servers/multi-ai-collab/credentials.json` and add your API key(s). Set `"enabled": true` for each AI you configure.

Secure the file:
```bash
# macOS/Linux
chmod 600 ~/.claude-mcp-servers/multi-ai-collab/credentials.json
```

#### 4. Fix Windows encoding (Windows only)

Open `~/.claude-mcp-servers/multi-ai-collab/server.py` and replace:
```python
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 1)
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', 1)
```
With:
```python
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1, encoding='utf-8', errors='replace')
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1, encoding='utf-8', errors='replace')
```

#### 5. Register the MCP server

Use the venv Python, not the system Python:
```bash
# macOS/Linux
claude mcp add --scope user --transport stdio multi-ai-collab -- \
  ~/.claude-mcp-servers/multi-ai-collab/.venv/bin/python \
  ~/.claude-mcp-servers/multi-ai-collab/server.py

# Windows
claude mcp add --scope user --transport stdio multi-ai-collab -- ^
  %USERPROFILE%\.claude-mcp-servers\multi-ai-collab\.venv\Scripts\python.exe ^
  %USERPROFILE%\.claude-mcp-servers\multi-ai-collab\server.py
```

#### 6. Install defaults

Copy the default config files to your Claude config:
```bash
cp defaults/global-CLAUDE.md ~/.claude/CLAUDE.md
cp defaults/ai-team-knowledge.md ~/.claude/ai-team-knowledge.md
```

If you already have a `~/.claude/CLAUDE.md`, append the contents of `defaults/global-CLAUDE.md` to it.

</details>

### Verify Installation

Restart VS Code (or open a new Claude Code CLI session), then:

```
Ask Grok to say hello
```

You should see Grok respond directly through the MCP bridge. You can also check:

```
Check the server status for the multi-ai-collab MCP
```

## What Gets Installed

| File | Location | Purpose |
|------|----------|---------|
| `CLAUDE.md` | `~/.claude/CLAUDE.md` | Global rules: auto-bootstrap, collaboration protocol, MCP fallback |
| `ai-team-knowledge.md` | `~/.claude/ai-team-knowledge.md` | Global knowledge base — learnings from all projects |
| MCP server | `~/.claude-mcp-servers/multi-ai-collab/` | Bridge between Claude Code and external AIs (pinned to known-good commit) |
| Python venv | `~/.claude-mcp-servers/multi-ai-collab/.venv/` | Isolated Python environment (no global pip pollution) |
| Credentials | `~/.claude-mcp-servers/multi-ai-collab/credentials.json` | Your API keys (local only, never committed) |
| Cred helper | `scripts/update_creds.py` (in this repo) | Writes API keys to credentials.json via stdin |

Per-project files (auto-created by Claude on first task):
| File | Location | Purpose |
|------|----------|---------|
| `AI_TEAM_SYNERGY.md` | Project root | Project-specific AI team knowledge |
| AI team section in `CLAUDE.md` | Project root | Project-specific collaboration rules |

## Available Tools

Once installed, Claude Code gains these MCP tools:

| Tool | What it does |
|------|-------------|
| `ask_grok` | Ask Grok any question |
| `grok_code_review` | Independent code review (security, performance, readability) |
| `grok_think_deep` | Extended reasoning on complex problems |
| `grok_brainstorm` | Creative brainstorming with constraints |
| `grok_debug` | Debugging help with error context |
| `grok_architecture` | Architecture design advice |
| `server_status` | Check which AIs are available |

If you enable multiple AIs, you also get: `ask_all_ais`, `ai_debate`, `collaborative_solve`, `ai_consensus`.

## How Collaboration Works in Practice

The global `CLAUDE.md` instructs Claude Code to follow these collaboration guidelines. You don't need to explicitly invoke tools — Claude will:

1. **Read the global knowledge base** at session start
2. **Auto-create `AI_TEAM_SYNERGY.md`** in new projects
3. **Consult Grok** before major architecture decisions
4. **Send code to Grok for review** after writing complex logic
5. **Ask Grok for help** when stuck on debugging
6. **Log learnings** to both the project and global knowledge bases
7. **Fall back to solo mode** if Grok's API returns billing errors

> **Note:** These behaviors are driven by the `CLAUDE.md` instructions. Claude follows them as guidelines, so the degree of automation may vary between sessions. You can always invoke tools explicitly (e.g., "Ask Grok to review this code") for guaranteed collaboration.

### Example Prompts

```
Ask Grok to review this authentication middleware for security issues

Get Grok's opinion on whether we should use WebSockets or SSE for real-time updates

Have Grok debug this — I've tried 3 approaches and none work

Ask Grok to brainstorm approaches for caching this expensive query
```

## MCP Fallback (Billing Protection)

When xAI credits run out, Claude automatically:
1. Detects the billing error (HTTP 402, "insufficient funds", etc.)
2. Stops calling Grok for the rest of the session
3. Continues with pure Claude reasoning
4. Mentions the outage exactly once

No workflow interruption. No error spam. Just seamless degradation.

## Uninstall

**macOS / Linux:**
```bash
./setup.sh --uninstall
```

**Windows (PowerShell):**
```powershell
.\setup.ps1 -Uninstall
```

This removes the MCP server registration, the server directory, and optionally the global knowledge base. The AI team section in `~/.claude/CLAUDE.md` must be removed manually if desired.

## Customization

### Change the Default Grok Model

Edit `~/.claude-mcp-servers/multi-ai-collab/credentials.json`:
```json
{
  "grok": {
    "model": "grok-4-1-fast-reasoning",
    "api_key": "your-key-here",
    "enabled": true
  }
}
```

Available models: `grok-4-1-fast-reasoning` ($0.20/M), `grok-4-1-fast-non-reasoning` ($0.20/M), `grok-3` ($3.00/M)

### Enable Additional AIs

Add API keys and set `"enabled": true` in `credentials.json` for any combination of Gemini, OpenAI, or DeepSeek.

### Customize Collaboration Rules

Edit `~/.claude/CLAUDE.md` to change when and how Claude consults Grok. For example, to make Grok reviews mandatory for all PRs, add:
```markdown
- **Mandatory review**: Before any git commit, run `grok_code_review` on all changed files.
```

## How It Differs from the Base MCP Server

This project builds on [RaiAnsar/claude_code-multi-AI-MCP](https://github.com/RaiAnsar/claude_code-multi-AI-MCP) (the MCP bridge) and adds:

| Feature | Base MCP Server | This Project |
|---------|----------------|-------------|
| Claude-to-Grok calls | Yes | Yes |
| Persistent cross-project memory | No | Yes |
| Auto-bootstrap in new projects | No | Yes |
| Billing fallback protocol | No | Yes |
| Global collaboration rules | No | Yes |
| Per-project knowledge base | No | Yes |
| Isolated Python venv | No | Yes |
| Pinned upstream dependency | No | Yes |
| Windows UTF-8 fix | No | Yes |
| Cross-platform setup script | No | Yes |

## Troubleshooting

### MCP tools not appearing after restart
The MCP server must be registered with `--scope user`. Run:
```bash
claude mcp add --scope user --transport stdio multi-ai-collab -- \
  ~/.claude-mcp-servers/multi-ai-collab/.venv/bin/python \
  ~/.claude-mcp-servers/multi-ai-collab/server.py
```

### Grok returns encoding errors on Windows
Apply the UTF-8 fix to `server.py` (the setup script does this automatically).

### "command not found: claude"
Install Claude Code CLI globally: `npm install -g @anthropic-ai/claude-code`
Or use npx: `npx @anthropic-ai/claude-code mcp add ...`

### pip install fails during setup
The setup script creates an isolated venv. If it fails, check that `python3 -m venv` works on your system. On Debian/Ubuntu you may need: `sudo apt install python3-venv`

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on reporting bugs, suggesting features, and submitting pull requests.

## Credits

- MCP Bridge: [RaiAnsar/claude_code-multi-AI-MCP](https://github.com/RaiAnsar/claude_code-multi-AI-MCP)
- Claude Code: [Anthropic](https://docs.anthropic.com/en/docs/claude-code)
- Grok: [xAI](https://x.ai/)

## License

MIT
