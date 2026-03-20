# Global Instructions (All Projects) — v3

## AI Team Collaboration (Claude + Grok)

This user runs a hybrid AI team. Claude Code is the primary agent. Grok (xAI) is available via MCP (`multi-ai-collab` server) in every project.

### Mandatory at EVERY Session Start
1. Read `~/.claude/ai-team-knowledge.md` — the **global** knowledge base with learnings from ALL projects.
2. If the current project has an `AI_TEAM_SYNERGY.md`, read that too for project-specific context.
3. If the current project has a `FEATURES.md`, read it (or grep selectively if >20KB — see Context Budget).
4. If the current project has an `INTEGRATION_CONTRACTS.md`, read it.
5. Check if Grok is available: if any prior MCP call returned a billing/quota error this session, set `GROK_AVAILABLE = false` and do not retry.
6. **Sync memory with Grok**: Call `grok_memory_sync(action="pull")` to check for new Grok learnings. Review and integrate valuable ones into `~/.claude/ai-team-knowledge.md`.
7. **Share Claude's learnings**: Call `grok_memory_sync(action="push", learnings="<recent entries from ai-team-knowledge.md>")` so Grok has Claude's latest knowledge.

### Auto-Bootstrap (MANDATORY on first task in any project)
On the FIRST substantive task in a project, Claude MUST check:
1. Does `AI_TEAM_SYNERGY.md` exist in the project root?
   - If NO: create it from the AI_TEAM_SYNERGY.md template below.
2. Does the project's `CLAUDE.md` have an "AI Team Collaboration" section?
   - If NO and a `CLAUDE.md` exists: prepend the collaboration section.
   - If NO `CLAUDE.md` exists: create one with the collaboration section + basic project conventions.
3. Does `INTEGRATION_CONTRACTS.md` exist?
   - If NO and project has `services/` dir or `docker-compose.yml`: create from the Integration Contracts template below.
4. Does `LEARNINGS_KB.md` exist?
   - If NO: create from the Learnings KB template below.
5. Does `contracts/` dir exist?
   - If NO and project is multi-service (has `services/` dir or multiple service definitions in docker-compose): create skeleton with `contracts/apis/`, `contracts/events/`, `contracts/shared/` from templates below.

Do this silently -- no need to ask the user. Just create the files and mention it briefly.

### Default: Grok is ALWAYS Involved
**Grok participates in every non-trivial task by default.** This is opt-OUT, not opt-in.

| Task Type | Grok Pattern | Tool |
|-----------|-------------|------|
| New feature / sprint work | Review approach before coding | `grok_collaborate` |
| Bug fix (non-trivial) | Fresh perspective on error | `grok_debug` |
| Code review / PR prep | Independent code review | `grok_code_review` |
| Architecture / design | Multi-turn consensus | `grok_collaborate` |
| New code files | Parallel implementation to compare | `grok_execute_task` |
| Documentation / planning | Review structure + gaps | `ask_grok` |
| Debugging dead-end (>2 tries) | Escalate immediately | `grok_debug` |
| Cross-service integration | Mandatory contract check + 2-call review | `grok_code_review` + `grok_execute_task` |
| Trivial (typo, 1-line fix) | Skip Grok | -- |

**When in doubt, involve Grok.** The cost of an extra call is negligible vs. the cost of a wrong decision.

---

## Integration-First Protocol (MANDATORY for Multi-Service Projects)

Before making ANY change to a service that touches APIs, events, or cross-service data flow, Claude MUST:
1. **Read** `INTEGRATION_CONTRACTS.md` for the overview of all service boundaries.
2. **Check** `contracts/apis/` for the service being modified AND every service it calls or is called by.
3. **Check** `contracts/shared/` for header conventions, tenant propagation rules, and auth patterns.
4. **Never hardcode** values defined in `contracts/shared/` (tenant header names, auth schemes, error shapes).
5. **After implementation**, run the 2-Call Grok Review Pattern (see below).
6. **After completion**, extract 0-3 learnings and append to `LEARNINGS_KB.md`.

If `contracts/` does not exist yet and the change is cross-service, create the relevant contract files first.

---

## 2-Call Grok Review Pattern

Use after any meaningful change touching APIs, events, data flow, tenant isolation, or compliance.

**Call 1 -- Quality + Integration compliance:**
```
grok_code_review(
  code="<changed files>",
  context="Service: X. Contract: <paste relevant contract snippet>. Check: (1) code matches contract, (2) tenant header propagated, (3) error shape matches shared contract, (4) no hardcoded contract values.",
  focus="integration_compliance"
)
```

**Call 2 -- Compliance + Knowledge extraction:**
```
grok_execute_task(
  task="Review this change for: (1) compliance violations (audit, auth, data integrity), (2) extract 0-3 reusable learnings for LEARNINGS_KB.md.",
  files="<changed files + relevant contract>",
  constraints="Output JSON: {compliance_issues: [...], learnings: [...]}",
  output_format="review"
)
```

Apply fixes from Call 1. Log learnings from Call 2 into `LEARNINGS_KB.md`.

---

## Contract-Driven Development

When modifying any API, event schema, or cross-service behavior:
1. **Edit the contract FIRST** (`contracts/apis/`, `contracts/events/`, or `contracts/shared/`).
2. **Implement** the code change to match the updated contract.
3. **Verify** code matches contract after implementation (field names, types, status codes, headers).
4. **If drift detected**, fix the code or update the contract before marking complete.

Contracts are the source of truth for service boundaries. Code follows contracts, not the other way around.

---

## Context Budget Management

Prevent context window exhaustion in large projects:
- **Never full-load files >15K tokens.** Use selective grep/read with line ranges instead.
- **FEATURES.md**: If >20KB, grep for the relevant feature/sprint rather than reading entirely.
- **AI_TEAM_SYNERGY.md**: If >25KB, read only the last 25 sprint entries.
- **MEMORY.md**: Cap at 180 lines. Keep it as an index; move detail into topic files under `memory/`.
- **Periodic distillation**: Every 10-15 turns, summarize findings into the appropriate memory file and release working context.
- **Large code files**: Read the function/class you need, not the entire file.

---

## Collaboration Rules (apply to every project)
- **Gut-check major decisions**: Before committing to architecture changes, complex algorithms, or non-obvious design choices, consult Grok via `ask_grok` or `grok_code_review`.
- **Log learnings**: After significant collaboration, append general learnings to `~/.claude/ai-team-knowledge.md` (global) AND project-specific context to `AI_TEAM_SYNERGY.md` (local).
- **Sync with Grok**: After logging learnings, also call `grok_memory_sync(action="push")` so Grok remembers too.
- **Never blindly accept**: If Grok contradicts project conventions or compliance rules, prefer project conventions. Log disagreements.
- **Preserve user labels**: Never overwrite user-facing terms based on AI suggestions.

### Collaboration Sessions (`grok_collaborate`)
Use multi-turn sessions for decisions requiring iteration:
- Architecture decisions with trade-offs
- Complex debugging where first attempts fail
- Design reviews needing back-and-forth refinement
- Any task where convergence/consensus is important

**Pattern:**
1. Start: `grok_collaborate(task="...", context="...", project="...")`
2. Iterate: `grok_collaborate(session_id="...", message="I agree with X but disagree with Y because...")`
3. Check the `STATUS` field. If "consensus", proceed. If "persistent_disagreement", present both views to user.
4. End: `grok_session_end(session_id="...", save_learnings=true, claude_summary="...")`

### Grok as Agent (`grok_execute_task`)
Use agent-style execution when Grok should work independently:
- Writing code from scratch (not just reviewing yours)
- Generating a second implementation to compare approaches
- Splitting work: Claude handles some files, Grok designs others
- Getting an unbiased implementation unaffected by your current approach

**Pattern:**
1. Read the relevant files
2. Call `grok_execute_task(task="...", files="<contents>", constraints="...", output_format="code")`
3. Review Grok's output critically -- do NOT apply blindly
4. If Grok's approach is better, use it. If yours is better, keep yours. If hybrid, merge.
5. Log the decision in `AI_TEAM_SYNERGY.md`

---

## Memory Sync Protocol (Bidirectional Learning)
After any significant Grok collaboration:
1. Save general learnings to `~/.claude/ai-team-knowledge.md` (Claude's brain)
2. Call `grok_memory_sync(action="push", learnings="<the new learning>")` (Grok's brain)
3. Save project-specific context to `AI_TEAM_SYNERGY.md` (project brain)

This ensures **both** AIs learn from every interaction.

## MCP Fallback (Billing/Quota Exhaustion)
If Grok MCP tools return errors matching: `insufficient funds`, `insufficient_quota`, `payment required`, `credit balance too low`, `rate_limit_exceeded` (billing context), HTTP 402, or any xAI billing error:
1. Immediately stop calling Grok tools for this session.
2. Continue with pure Claude reasoning.
3. Mention the outage exactly once, then move on.
4. Only suggest "Add xAI credits to restore Grok" if the user explicitly asks about external models.

## Knowledge Flow (CRITICAL -- Bidirectional, NEVER siloed)
After ANY significant learning, Claude MUST update ALL THREE stores:
1. **`~/.claude/ai-team-knowledge.md`** -- Claude's global brain
2. **`AI_TEAM_SYNERGY.md`** -- the project brain (project-specific only)
3. **`grok_memory_sync(action="push")`** -- Grok's brain

General learnings → global file + Grok. Project-specific → project file + Grok. Both → all three.

---

## Templates

### AI_TEAM_SYNERGY.md Template
```markdown
# AI Team Synergy Knowledge Base
> Hybrid Claude + Grok team. Shared brain for THIS PROJECT.
> Global learnings: ~/.claude/ai-team-knowledge.md
## Protocol
1. Read this file + global knowledge at session start.
2. After significant work, append context HERE and general learnings to GLOBAL file.
3. Never delete -- only append or annotate.
## When to Consult Grok
Architecture, code review, debugging dead-ends, domain questions, trade-offs.
NOT for: trivial edits, latency-sensitive work, billing exhausted.
## Project-Specific Lessons
## Project Context
```

### INTEGRATION_CONTRACTS.md Template
```markdown
# Integration Contracts
> Source of truth for service-to-service boundaries. Edit BEFORE implementing.
## Services
| Service | Port | Base Path | Owner |
|---------|------|-----------|-------|
## Contract Files
- `contracts/apis/` -- endpoint specs per service
- `contracts/events/` -- event schemas (topics, payloads)
- `contracts/shared/` -- headers, auth, tenant rules, error shapes
## Rules
1. Cross-service changes must update the contract file first.
2. Shared conventions must not be hardcoded in service code.
3. Verify code matches contract after implementation.
```

### LEARNINGS_KB.md Template
```markdown
# Learnings Knowledge Base
> Reusable patterns extracted via 2-Call Grok Review.
## Format
`[DATE] [SERVICE] [CATEGORY] -- Learning text`
Categories: integration, compliance, performance, debugging, pattern
## Entries
```

### contracts/ Skeleton
Create: `contracts/apis/`, `contracts/events/`, `contracts/shared/` with `headers.md`, `errors.md`, `auth.md`.
