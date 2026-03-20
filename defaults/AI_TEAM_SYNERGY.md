# AI Team Synergy Knowledge Base

> **You are part of a hybrid Claude Code + Grok team.**
> This file is the shared brain for THIS PROJECT.
> Global learnings live in `~/.claude/ai-team-knowledge.md` — read that too.

## Protocol (ALWAYS follow)

1. **Read this file + `~/.claude/ai-team-knowledge.md`** at the start of any task.
2. **Sync with Grok**: Call `grok_memory_sync(action="pull")` to get Grok's latest learnings, then `grok_memory_sync(action="push")` to share Claude's.
3. **After completing significant work**, append project-specific context HERE, general learnings to the GLOBAL file, AND sync to Grok via `grok_memory_sync(action="push")`.
4. **Reference prior learnings explicitly** in your reasoning when relevant.
5. **Never delete entries** — only append or annotate with corrections.
6. **Keep entries concise** — 2-4 lines max per lesson. Link to files/commits for details.

---

## MCP Fallback Rules

If any external AI tool (especially Grok) returns billing/quota errors:
1. Stop trying that tool for the remainder of this session.
2. Set mental flag: `GROK_AVAILABLE = false` for this session.
3. Continue with pure Claude reasoning.
4. Do NOT mention the failure more than once.

---

## When to Consult Grok (Claude's guide)

| Task Type | Grok Pattern | Tool |
|-----------|-------------|------|
| Architecture decisions | Second opinion before committing | `grok_collaborate` |
| Code review | Independent review after complex logic | `grok_code_review` |
| Cross-service integration | **Mandatory** contract check + 2-call review | `grok_code_review` + `grok_execute_task` |
| Debugging dead-ends (>2 tries) | Fresh perspective | `grok_debug` |
| Trade-off analysis | Deep extended reasoning | `grok_think_deep` |
| Writing new code files | Parallel implementation to compare | `grok_execute_task` |
| Trivial fixes | Skip Grok | — |

---

## Rolling Maintenance

This file covers the **last ~25 sprints** only. When it exceeds ~25KB:
1. Move older entries to `memory/sprint-summaries/synergy-sprints-<range>.md`
2. Keep only the most recent entries here
3. Distill key patterns into `LEARNINGS_KB.md`

---

## Lessons Learned

### Architecture & Design
<!-- Append: [YYYY-MM-DD] [Sprint X] Lesson. **Why:** reason. -->


### Integration Patterns
<!-- Cross-service learnings. What breaks at integration points. -->


### Code Patterns & Best Practices
<!-- Append new entries here -->


### Debugging Insights
<!-- Append new entries here -->


### Compliance & Security
<!-- Pharma, Part 11, tenant isolation patterns -->


### Corrections & Disagreements
<!-- When one AI corrects the other, log it here -->


---

## Project Context

<!-- Claude fills this in automatically with project-specific details -->
<!-- Include: tech stack, architecture, key patterns, service map -->
