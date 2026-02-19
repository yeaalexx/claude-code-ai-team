# Claude Code AI Team

![Version](https://img.shields.io/badge/version-0.2.0-blue)

**Bidirectional AI collaboration for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — Claude and Grok learn from each other, collaborate on solutions, and build shared knowledge that persists forever.**

Claude Code is powerful on its own. But sometimes you want a second opinion — an independent code review, a gut-check on architecture, a fresh perspective on a stubborn bug. This setup gives Claude Code a teammate that *remembers* and *learns*.

## What This Does

- **Bidirectional learning**: Both Claude and Grok have persistent memory — they learn from each interaction and carry knowledge forward
- **Grok has memory**: Grok receives its accumulated learnings as context on every call. It also auto-extracts new learnings from its own responses.
- **Multi-turn collaboration**: Claude and Grok can have iterative conversations (`grok_collaborate`) with consensus detection — they work toward agreed solutions
- **Grok as agent**: Give Grok independent tasks (`grok_execute_task`) and get back structured code, plans, or reviews
- **Persistent cross-project memory**: Learnings from any project automatically benefit all future projects for *both* AIs
- **Per-project context**: Each project gets its own `AI_TEAM_SYNERGY.md` that's auto-created on first use
- **Auto-fallback on billing exhaustion**: When xAI credits run out, Claude seamlessly continues solo — no workflow interruption
- **Zero-config for new projects**: Global rules auto-bootstrap collaboration files in every project you open

## Architecture

```
Global (shared across all projects):
  ~/.claude/CLAUDE.md                                    <-- Global rules (collaboration, sync, fallback)
  ~/.claude/ai-team-knowledge.md                         <-- Claude's brain (cross-project learnings)
  ~/.claude.json                                         <-- MCP server registration (user scope)
  ~/.claude-mcp-servers/multi-ai-collab/                 <-- Enhanced MCP server v2
  ~/.claude-mcp-servers/multi-ai-collab/.venv/           <-- Isolated Python environment
  ~/.claude-mcp-servers/multi-ai-collab/memory/
      +-- grok-memory.json                               <-- Grok's brain (persistent memory)
      +-- sessions/                                      <-- Collaboration session transcripts

Per project (auto-created by Claude):
  ~/projects/any-project/
      +-- AI_TEAM_SYNERGY.md              <-- Project-specific AI team knowledge
      +-- CLAUDE.md                       <-- Project conventions (AI team section auto-added)
```

### Knowledge Flow (Bidirectional)

```
Claude discovers insight              Grok discovers insight
        |                                      |
        v                                      v
ai-team-knowledge.md              [LEARNING] block in response
  (Claude writes)                   (server auto-extracts)
        |                                      |
        v                                      v
grok_memory_sync(push) -----> grok-memory.json <---- auto-saved
                                    |
                             next Grok call:
                             context_builder injects
                             relevant learnings into
                             Grok's system prompt
                                    |
                                    v
                          BOTH AIs now have the learning
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
1. Install the enhanced MCP server v2 (from this repo's `server/` directory)
2. Create an isolated Python venv and install pinned dependencies
3. Create Grok's memory directory (`memory/grok-memory.json`)
4. Prompt for your API key(s) and secure the credentials file
5. Register the MCP server globally (using the venv Python)
6. Install the global `CLAUDE.md` and knowledge base defaults

### Option B: Manual Setup

<details>
<summary>Click to expand manual steps</summary>

#### 1. Copy the enhanced server
```bash
mkdir -p ~/.claude-mcp-servers/multi-ai-collab/memory/sessions
cp server/*.py server/credentials.template.json ~/.claude-mcp-servers/multi-ai-collab/
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
cp server/credentials.template.json ~/.claude-mcp-servers/multi-ai-collab/credentials.json
```

Edit `~/.claude-mcp-servers/multi-ai-collab/credentials.json` and add your API key(s). Set `"enabled": true` for each AI you configure.

Secure the file:
```bash
# macOS/Linux
chmod 600 ~/.claude-mcp-servers/multi-ai-collab/credentials.json
```

#### 4. Register the MCP server

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

#### 5. Install defaults

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
| MCP server | `~/.claude-mcp-servers/multi-ai-collab/` | Enhanced MCP server v2 with bidirectional learning |
| Grok memory | `~/.claude-mcp-servers/multi-ai-collab/memory/` | Grok's persistent memory and session transcripts |
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

### Core Tools (per AI)
| Tool | What it does |
|------|-------------|
| `ask_grok` | Ask Grok any question (with memory-aware context) |
| `grok_code_review` | Independent code review (security, performance, readability) |
| `grok_think_deep` | Extended reasoning on complex problems |
| `grok_brainstorm` | Creative brainstorming with constraints |
| `grok_debug` | Debugging help with error context |
| `grok_architecture` | Architecture design advice |
| `server_status` | Check which AIs are available + memory stats |

### v2: Bidirectional Learning & Collaboration
| Tool | What it does |
|------|-------------|
| `grok_collaborate` | Multi-turn sessions — both AIs iterate toward an agreed solution with consensus detection |
| `grok_execute_task` | Grok works independently as an agent — returns structured code, plans, reviews, or diffs |
| `grok_memory_sync` | Push Claude's learnings to Grok / pull Grok's learnings to Claude / check status |
| `grok_session_end` | End a collaboration session and extract learnings from the full conversation |
| `grok_memory_status` | View Grok's memory state (learning counts, categories, active sessions) |

### Multi-AI Tools (when 2+ AIs enabled)
`ask_all_ais`, `ai_debate`, `collaborative_solve`, `ai_consensus`

## How Collaboration Works in Practice

The global `CLAUDE.md` instructs Claude Code to follow these collaboration guidelines. You don't need to explicitly invoke tools — Claude will:

1. **Sync memory with Grok** at session start (pull Grok's learnings, push Claude's)
2. **Auto-create `AI_TEAM_SYNERGY.md`** in new projects
3. **Consult Grok** before major architecture decisions
4. **Send code to Grok for review** after writing complex logic
5. **Start collaboration sessions** for complex decisions requiring iteration
6. **Delegate tasks to Grok** when independent work is beneficial
7. **Log learnings to all three stores** (Claude's brain, Grok's brain, project brain)
8. **Fall back to solo mode** if Grok's API returns billing errors

> **Note:** These behaviors are driven by the `CLAUDE.md` instructions. Claude follows them as guidelines, so the degree of automation may vary between sessions. You can always invoke tools explicitly for guaranteed collaboration.

### Example Prompts

```
Ask Grok to review this authentication middleware for security issues

Start a collaboration session with Grok to design the caching strategy

Have Grok independently write the retry logic while I work on the API endpoints

Get Grok's opinion on whether we should use WebSockets or SSE for real-time updates

Have Grok debug this — I've tried 3 approaches and none work

Sync memory with Grok to make sure we're both up to date
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

Originally inspired by [RaiAnsar/claude_code-multi-AI-MCP](https://github.com/RaiAnsar/claude_code-multi-AI-MCP). v2 is a complete rewrite with bidirectional learning:

| Feature | Base MCP Server | v0.1 | v0.2 (Current) |
|---------|----------------|------|----------------|
| Claude-to-Grok calls | Yes | Yes | Yes |
| Grok persistent memory | No | No | **Yes** |
| Bidirectional learning | No | No | **Yes** |
| Multi-turn collaboration | No | No | **Yes** |
| Grok as agent | No | No | **Yes** |
| Memory synchronization | No | No | **Yes** |
| Consensus detection | No | No | **Yes** |
| System prompt injection | No | No | **Yes** |
| Persistent cross-project memory | No | Yes | Yes |
| Auto-bootstrap in new projects | No | Yes | Yes |
| Billing fallback protocol | No | Yes | Yes |

## Troubleshooting

### MCP tools not appearing after restart
The MCP server must be registered with `--scope user`. Run:
```bash
claude mcp add --scope user --transport stdio multi-ai-collab -- \
  ~/.claude-mcp-servers/multi-ai-collab/.venv/bin/python \
  ~/.claude-mcp-servers/multi-ai-collab/server.py
```

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
