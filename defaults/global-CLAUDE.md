# Global Instructions (All Projects)

## AI Team Collaboration (Claude + Grok)

This user runs a hybrid AI team. Claude Code is the primary agent. Grok (xAI) is available via MCP (`multi-ai-collab` server) in every project.

### Mandatory at EVERY Session Start
1. Read `~/.claude/ai-team-knowledge.md` — the **global** knowledge base with learnings from ALL projects.
2. If the current project has an `AI_TEAM_SYNERGY.md`, read that too for project-specific context.
3. Check if Grok is available: if any prior MCP call returned a billing/quota error this session, set `GROK_AVAILABLE = false` and do not retry.
4. **Sync memory with Grok**: Call `grok_memory_sync(action="pull")` to check for new Grok learnings. Review and integrate valuable ones into `~/.claude/ai-team-knowledge.md`.
5. **Share Claude's learnings**: Call `grok_memory_sync(action="push", learnings="<recent entries from ai-team-knowledge.md>")` so Grok has Claude's latest knowledge.

### Auto-Bootstrap (MANDATORY on first task in any project)
On the FIRST substantive task in a project, Claude MUST check:
1. Does `AI_TEAM_SYNERGY.md` exist in the project root?
   - If NO: create it from the template below.
2. Does the project's `CLAUDE.md` have an "AI Team Collaboration" section?
   - If NO and a `CLAUDE.md` exists: prepend the collaboration section.
   - If NO `CLAUDE.md` exists: create one with the collaboration section + basic project conventions.

Do this silently — no need to ask the user. Just create the files and mention it briefly.

### AI_TEAM_SYNERGY.md Template
When auto-creating, use this structure:
```markdown
# AI Team Synergy Knowledge Base

> You are part of a hybrid Claude Code + Grok team.
> This file is the shared brain for THIS PROJECT.
> Global learnings live in ~/.claude/ai-team-knowledge.md

## Protocol
1. Read this file + ~/.claude/ai-team-knowledge.md at the start of any task.
2. After significant work, append project-specific context HERE and general learnings to the GLOBAL file.
3. Reference prior learnings in your reasoning.
4. Never delete entries — only append or annotate with corrections.

## MCP Fallback Rules
If Grok returns billing/quota errors (insufficient funds, HTTP 402, rate_limit_exceeded):
1. Stop calling Grok tools for this session.
2. Continue with pure Claude reasoning.
3. Mention the outage once, then move on.

## When to Consult Grok
- Architecture decisions (second opinion)
- Code review (independent review via grok_code_review)
- Debugging dead-ends (fresh perspective via grok_debug)
- Domain-specific questions
- Trade-off analysis (grok_think_deep)

Do NOT use Grok for: trivial edits, when latency matters, when billing is exhausted.

## Project-Specific Lessons
[Project-specific learnings go here]

## Project Context
[Claude fills this in with project-specific details on first creation]
```

### Collaboration Rules (apply to every project)
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
3. Review Grok's output critically — do NOT apply blindly
4. If Grok's approach is better, use it. If yours is better, keep yours. If hybrid, merge.
5. Log the decision in `AI_TEAM_SYNERGY.md`

### Memory Sync Protocol (Bidirectional Learning)
After any significant Grok collaboration:
1. Save general learnings to `~/.claude/ai-team-knowledge.md` (Claude's brain)
2. Call `grok_memory_sync(action="push", learnings="<the new learning>")` (Grok's brain)
3. Save project-specific context to `AI_TEAM_SYNERGY.md` (project brain)

This ensures **both** AIs learn from every interaction. Grok will have these learnings injected into its system prompt on future calls.

### MCP Fallback (Billing/Quota Exhaustion)
If Grok MCP tools return errors matching: `insufficient funds`, `insufficient_quota`, `payment required`, `credit balance too low`, `rate_limit_exceeded` (billing context), HTTP 402, or any xAI billing error:
1. Immediately stop calling Grok tools for this session.
2. Continue with pure Claude reasoning.
3. Mention the outage exactly once, then move on.
4. Only suggest "Add xAI credits to restore Grok" if the user explicitly asks about external models.

### Knowledge Flow (CRITICAL — Bidirectional, NEVER siloed)
```
Claude discovers insight              Grok discovers insight
        |                                      |
        v                                      v
ai-team-knowledge.md              [LEARNING] block in response
  (Claude writes)                   (server auto-extracts)
        |                                      |
        v                                      v
grok_memory_sync(push) -----> grok-memory.json <---- auto-saved
        |                           |
        |                    next Grok call:
        |                    context_builder injects
        |                    relevant learnings into
        |                    Grok's system prompt
        v                           v
   BOTH AIs now have the learning
```

After ANY significant AI team learning, Claude MUST update ALL THREE stores:
1. **`~/.claude/ai-team-knowledge.md`** — Claude's global brain (general patterns, tech notes, debugging insights, corrections)
2. **`AI_TEAM_SYNERGY.md`** — the project brain (project-specific context only)
3. **`grok_memory_sync(action="push")`** — Grok's brain (so Grok remembers too)

If a learning is general (applies to any project), it goes in the global file + Grok's memory.
If a learning is project-specific, it goes in the project file + Grok's memory.
If it's both, it goes in ALL THREE.
