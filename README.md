# Claude Code AI Team

![Version](https://img.shields.io/badge/version-4.0.0-blue)

**Bidirectional AI collaboration for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — Claude and Grok learn from each other, collaborate on solutions, and build shared knowledge that persists forever.**

Claude Code is powerful on its own. But sometimes you want a second opinion — an independent code review, a gut-check on architecture, a fresh perspective on a stubborn bug. This setup gives Claude Code a teammate that *remembers* and *learns*.

## What's New in v4 (RAG Memory + Parallel Calls)

v4 adds **semantic memory retrieval** and **parallel Grok calls** — the AI team now finds relevant knowledge by meaning (not just category) and runs multi-call review patterns in half the time.

- **RAG semantic memory**: ChromaDB-powered semantic search over all learnings. Query by natural language to find the most relevant past insights, regardless of category labels.
- **Parallel Grok calls**: The 2-call review pattern now fires both calls simultaneously via `ThreadPoolExecutor`, cutting review time in half.
- **`grok_multi_review` tool**: Single tool call replaces the manual 2-call pattern — quality+integration AND compliance+knowledge in parallel.
- **`grok_retrieve_context` tool**: Get relevant learnings without calling Grok at all — zero API cost context retrieval.
- **Graceful fallback**: If chromadb is not installed, the server works exactly like v3 (JSON-based filtering). RAG is an enhancement layer, not a requirement.
- **Automatic migration**: Existing JSON learnings are migrated to ChromaDB on first startup (idempotent, safe to run multiple times).

All v3 features (integration contracts, 2-call review, context budget, consolidation, Grok 4.20 budgets) and v2 features (persistent memory, collaboration sessions, agent execution, memory sync) are preserved.

## What This Does

- **Bidirectional learning**: Both Claude and Grok have persistent memory — they learn from each interaction and carry knowledge forward
- **Integration-first protocol**: Claude checks cross-service contracts before making changes in multi-service monorepos
- **Grok has memory**: Grok receives its accumulated learnings as context on every call. It also auto-extracts new learnings from its own responses.
- **Multi-turn collaboration**: Claude and Grok can have iterative conversations (`grok_collaborate`) with consensus detection
- **Grok as agent**: Give Grok independent tasks (`grok_execute_task`) and get back structured code, plans, or reviews
- **Persistent cross-project memory**: Learnings from any project automatically benefit all future projects for *both* AIs
- **Per-project context**: Each project gets its own `AI_TEAM_SYNERGY.md` and optionally `INTEGRATION_CONTRACTS.md`
- **Auto-fallback on billing exhaustion**: When xAI credits run out, Claude seamlessly continues solo
- **Zero-config for new projects**: Global rules auto-bootstrap collaboration files in every project

## Architecture

```
Global (shared across all projects):
  ~/.claude/CLAUDE.md                                    <-- Global rules (integration protocol, sync, fallback)
  ~/.claude/ai-team-knowledge.md                         <-- Claude's brain (cross-project learnings)
  ~/.claude.json                                         <-- MCP server registration (user scope)
  ~/.claude-mcp-servers/multi-ai-collab/                 <-- Enhanced MCP server v3
  ~/.claude-mcp-servers/multi-ai-collab/.venv/           <-- Isolated Python environment
  ~/.claude-mcp-servers/multi-ai-collab/defaults/        <-- v3 templates (contracts, KB, synergy)
  ~/.claude-mcp-servers/multi-ai-collab/memory/
      +-- grok-memory.json                               <-- Grok's brain (persistent memory, JSON)
      +-- chroma/                                        <-- RAG vector store (ChromaDB, semantic search)
      +-- sessions/                                      <-- Collaboration session transcripts

Per project (auto-created by Claude):
  ~/projects/any-project/
      +-- AI_TEAM_SYNERGY.md              <-- Project-specific AI team knowledge (rolling log)
      +-- LEARNINGS_KB.md                 <-- Distilled patterns (categorized, tagged)
      +-- CLAUDE.md                       <-- Project conventions (AI team section auto-added)
      +-- INTEGRATION_CONTRACTS.md        <-- Cross-service contracts (multi-service projects)
      +-- contracts/                      <-- Machine-readable API/event/shared contracts
          +-- registry.md                 <-- Service manifest + dependency matrix
          +-- apis/                       <-- Per-service API contracts
          +-- events/catalog.md           <-- Kafka/event schema catalog
          +-- shared/                     <-- Headers, tenant rules, error codes
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
1. Install the enhanced MCP server v3 (from this repo's `server/` directory)
2. Create an isolated Python venv and install pinned dependencies
3. Create Grok's memory directory (`memory/grok-memory.json`)
4. Prompt for your API key(s) and secure the credentials file
5. Register the MCP server globally (using the venv Python)
6. Install the global `CLAUDE.md` and knowledge base defaults
7. Copy v3 templates (contracts, integration, learnings KB) to discoverable location

### Option B: Manual Setup

<details>
<summary>Click to expand manual steps</summary>

#### 1. Copy the enhanced server
```bash
mkdir -p ~/.claude-mcp-servers/multi-ai-collab/memory/sessions
cp server/*.py server/credentials.template.json ~/.claude-mcp-servers/multi-ai-collab/
cp -r defaults/ ~/.claude-mcp-servers/multi-ai-collab/defaults/
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
| `CLAUDE.md` | `~/.claude/CLAUDE.md` | Global rules: integration protocol, auto-bootstrap, collaboration, MCP fallback |
| `ai-team-knowledge.md` | `~/.claude/ai-team-knowledge.md` | Global knowledge base — learnings from all projects |
| MCP server | `~/.claude-mcp-servers/multi-ai-collab/` | Enhanced MCP server v3 with integration architecture |
| Grok memory | `~/.claude-mcp-servers/multi-ai-collab/memory/` | Grok's persistent memory and session transcripts |
| v3 Templates | `~/.claude-mcp-servers/multi-ai-collab/defaults/` | Contract, KB, and synergy templates for new projects |
| Python venv | `~/.claude-mcp-servers/multi-ai-collab/.venv/` | Isolated Python environment (no global pip pollution) |
| Credentials | `~/.claude-mcp-servers/multi-ai-collab/credentials.json` | Your API keys (local only, never committed) |

Per-project files (auto-created by Claude on first task):
| File | Location | Purpose |
|------|----------|---------|
| `AI_TEAM_SYNERGY.md` | Project root | Project-specific AI team knowledge (rolling log) |
| `LEARNINGS_KB.md` | Project root | Distilled patterns (categorized, tagged) |
| `INTEGRATION_CONTRACTS.md` | Project root | Cross-service contracts (multi-service projects) |
| `contracts/` | Project root | API, event, and shared contract files |
| AI team section in `CLAUDE.md` | Project root | Project-specific collaboration rules |

## Available Tools

Once installed, Claude Code gains these MCP tools:

### Core Tools (per AI)
| Tool | What it does |
|------|-------------|
| `ask_grok` | Ask Grok any question (with memory-aware context) |
| `grok_code_review` | Independent code review (security, performance, integration) |
| `grok_think_deep` | Extended reasoning on complex problems |
| `grok_brainstorm` | Creative brainstorming with constraints |
| `grok_debug` | Debugging help with error context |
| `grok_architecture` | Architecture design advice |
| `server_status` | Check which AIs are available + memory stats |

### Bidirectional Learning & Collaboration
| Tool | What it does |
|------|-------------|
| `grok_collaborate` | Multi-turn sessions — both AIs iterate toward an agreed solution with consensus detection |
| `grok_execute_task` | Grok works independently as an agent — returns structured code, plans, reviews, or diffs |
| `grok_memory_sync` | Push Claude's learnings to Grok / pull Grok's learnings to Claude / check status |
| `grok_session_end` | End a collaboration session and extract learnings from the full conversation |
| `grok_memory_status` | View Grok's memory state (learning counts, categories, active sessions) |

### RAG & Parallel Review (v4)
| Tool | What it does |
|------|-------------|
| `grok_multi_review` | Parallel 2-call review: quality+integration AND compliance+knowledge in one tool call |
| `grok_retrieve_context` | Semantic search over learnings (RAG) — zero API cost, no Grok call needed |

### Multi-AI Tools (when 2+ AIs enabled)
`ask_all_ais`, `ai_debate`, `collaborative_solve`, `ai_consensus`

## How It Works in Practice

### For Single-Service Projects
Claude and Grok collaborate using the v2 workflow: memory sync, code review, collaboration sessions, agent execution. LEARNINGS_KB.md captures patterns.

### For Multi-Service Projects (v3 Integration Architecture)
On first task, Claude auto-creates:
1. `INTEGRATION_CONTRACTS.md` — dependency matrix, universal rules, anti-patterns
2. `contracts/` — per-service API contracts, event catalog, shared headers/tenant/error rules
3. `LEARNINGS_KB.md` — distilled patterns

Before every cross-service change, Claude:
1. Reads the relevant contracts
2. Implements the change
3. Runs the **2-call Grok review**:
   - Call 1 (`grok_code_review`): Quality + Integration compliance
   - Call 2 (`grok_execute_task`): Compliance + Knowledge extraction
4. Updates contracts if API changed
5. Extracts learnings

### The 2-Call Grok Review Pattern

```
Claude finishes a meaningful change
        |
        v
Call 1: grok_code_review
  "Review for Quality + Integration.
   Section 1: Code quality, tests, error handling
   Section 2: Does this match INTEGRATION_CONTRACTS.md?
              Header propagation? Event schemas? Hardcoded values?"
        |
        v
Call 2: grok_execute_task (output_format="review")
  "Review for Compliance + extract learnings.
   Section 1: Regulatory compliance (if applicable)
   Section 2: Extract 0-3 new learnings for LEARNINGS_KB.md"
        |
        v
Claude applies feedback, updates contracts/learnings
```

## RAG Semantic Memory (v4)

v4 adds a semantic search layer on top of the existing JSON memory. Instead of filtering learnings by category alone, Claude can now search by meaning.

### How it works

1. **Storage**: All learnings are stored in both JSON (`grok-memory.json`) and ChromaDB (`memory/chroma/`)
2. **Embeddings**: ChromaDB uses its built-in default embedding function (onnxruntime-based, ~200MB, no torch needed)
3. **Search**: When Grok is called, the task description is used as a semantic query to find the most relevant past learnings
4. **Fallback**: If ChromaDB is not installed, the server falls back to category-based JSON filtering (same as v3)

### Key tools

- **`grok_retrieve_context`**: Search learnings by meaning without calling Grok. Example: *"Find past learnings about tenant isolation in multi-service architectures"* — returns semantically similar learnings even if they are categorized as "architecture", "security", or "integration".
- **`grok_multi_review`**: Fires both review calls in parallel, each enriched with RAG-retrieved context relevant to the code being reviewed.

### Migration

Existing learnings in `grok-memory.json` are automatically migrated to ChromaDB on first v4 startup. The migration is idempotent — safe to run multiple times. The first run will be slower as the embedding model (~200MB) is downloaded.

## MCP Fallback (Billing Protection)

When xAI credits run out, Claude automatically:
1. Detects the billing error (HTTP 402, "insufficient funds", etc.)
2. Stops calling Grok for the rest of the session
3. Continues with pure Claude reasoning
4. Mentions the outage exactly once

No workflow interruption. No error spam. Just seamless degradation.

## Migration from v3

v4 is **fully backward compatible** with v3:
- Your existing `grok-memory.json` (all learnings) works unchanged
- Learnings are automatically migrated to ChromaDB on first v4 startup
- If chromadb is not installed, the server falls back to JSON-based filtering (same as v3)
- All v3 features (integration contracts, 2-call review, consolidation) are preserved

To upgrade:
```bash
cd claude-code-ai-team
git pull
./setup.ps1   # or ./setup.sh
```

First run after upgrade will download the embedding model (~200MB). Then restart VS Code.

## Uninstall

**macOS / Linux:**
```bash
./setup.sh --uninstall
```

**Windows (PowerShell):**
```powershell
.\setup.ps1 -Uninstall
```

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

### Enable Additional AIs

Add API keys and set `"enabled": true` in `credentials.json` for any combination of Gemini, OpenAI, or DeepSeek.

### Customize Collaboration Rules

Edit `~/.claude/CLAUDE.md` to change when and how Claude consults Grok.

## Version History

| Version | Feature | Status |
|---------|---------|--------|
| v4.0.0 | RAG Memory + Parallel Calls — semantic search, parallel review, zero-cost context retrieval | **Current** |
| v0.3.0 | Integration Architecture — contracts, 2-call review, context budget, consolidation | Stable |
| v0.2.0 | Bidirectional Learning — persistent memory, collaboration, agent execution | Stable |
| v0.1.0 | Initial Setup — auto-bootstrap, fallback protocol, knowledge base | Stable |

## Credits

- MCP Bridge: [RaiAnsar/claude_code-multi-AI-MCP](https://github.com/RaiAnsar/claude_code-multi-AI-MCP)
- Claude Code: [Anthropic](https://docs.anthropic.com/en/docs/claude-code)
- Grok: [xAI](https://x.ai/)

## License

MIT
