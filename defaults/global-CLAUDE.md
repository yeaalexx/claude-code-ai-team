# Global Instructions (All Projects)

## AI Team Collaboration (Claude + Grok)

This user runs a hybrid AI team. Claude Code is the primary agent. Grok (xAI) is available via MCP (`multi-ai-collab` server) in every project.

### Mandatory at EVERY Session Start
1. Read `~/.claude/ai-team-knowledge.md` — the **global** knowledge base with learnings from ALL projects.
2. If the current project has an `AI_TEAM_SYNERGY.md`, read that too for project-specific context.
3. Check if Grok is available: if any prior MCP call returned a billing/quota error this session, set `GROK_AVAILABLE = false` and do not retry.

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
- **Never blindly accept**: If Grok contradicts project conventions or compliance rules, prefer project conventions. Log disagreements.
- **Preserve user labels**: Never overwrite user-facing terms based on AI suggestions.

### MCP Fallback (Billing/Quota Exhaustion)
If Grok MCP tools return errors matching: `insufficient funds`, `insufficient_quota`, `payment required`, `credit balance too low`, `rate_limit_exceeded` (billing context), HTTP 402, or any xAI billing error:
1. Immediately stop calling Grok tools for this session.
2. Continue with pure Claude reasoning.
3. Mention the outage exactly once, then move on.
4. Only suggest "Add xAI credits to restore Grok" if the user explicitly asks about external models.

### Knowledge Flow (CRITICAL — learnings are NEVER siloed)
```
Project A learns something
        |
        +---> AI_TEAM_SYNERGY.md (project A only — project-specific context)
        |
        +---> ~/.claude/ai-team-knowledge.md (GLOBAL — all projects benefit)

Project B starts
        |
        +---> Reads ~/.claude/ai-team-knowledge.md (gets Project A's learnings)
        |
        +---> Creates its own AI_TEAM_SYNERGY.md (project B context)
```

After ANY significant AI team learning, Claude MUST update BOTH:
1. **`~/.claude/ai-team-knowledge.md`** — the global brain (general patterns, tech notes, debugging insights, corrections)
2. **`AI_TEAM_SYNERGY.md`** — the project brain (project-specific context only)

If a learning is general (applies to any project), it goes in the global file ONLY.
If a learning is project-specific, it goes in the project file ONLY.
If it's both, it goes in BOTH (general version globally, detailed version locally).
