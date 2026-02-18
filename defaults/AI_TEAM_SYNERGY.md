# AI Team Synergy Knowledge Base

> **You are part of a hybrid Claude Code + Grok team.**
> This file is the shared brain for THIS PROJECT.
> Global learnings live in `~/.claude/ai-team-knowledge.md` — read that too.

## Protocol (ALWAYS follow)

1. **Read this file + `~/.claude/ai-team-knowledge.md`** at the start of any task.
2. **After completing significant work**, append project-specific context HERE and general learnings to the GLOBAL file.
3. **Reference prior learnings explicitly** in your reasoning when relevant.
4. **Never delete entries** — only append or annotate with corrections.
5. **Keep entries concise** — 2-4 lines max per lesson. Link to files/commits for details.

---

## MCP Fallback Rules

If any external AI tool (especially Grok) returns **any** of these signals:
- "insufficient funds", "insufficient_quota", "payment required", "credit balance too low"
- "rate_limit_exceeded", "billing", "quota", HTTP 402/429 with billing context
- Any authentication/billing error from xAI API

**Then immediately:**
1. Stop trying that tool for the remainder of this session.
2. Set mental flag: `GROK_AVAILABLE = false` for this session.
3. Continue with pure Claude reasoning.
4. Do NOT mention the failure more than once.
5. Only suggest "Add xAI credits if you want Grok back" if the user explicitly asks about external models.

---

## When to Consult Grok (Claude's guide)

Use Grok as a **gut-check agent** in these scenarios:
- **Architecture decisions**: Before committing to a major design choice, ask Grok for a second opinion via `ask_grok`.
- **Code review**: After writing complex logic, send it to `grok_code_review` for an independent review.
- **Debugging dead-ends**: When stuck for >2 attempts on the same bug, ask `grok_debug` for a fresh perspective.
- **Domain knowledge**: Grok may have different training data — consult on ambiguous questions.
- **Trade-off analysis**: Use `grok_think_deep` when evaluating competing approaches.

Do NOT use Grok for:
- Trivial tasks (simple file edits, formatting, obvious fixes)
- Tasks where latency matters more than accuracy
- When GROK_AVAILABLE = false (see fallback rules above)

---

## Lessons Learned

### Architecture & Design
<!-- Append new entries here. Format: [DATE] Source: Claude|Grok -- Lesson -->


### Code Patterns & Best Practices
<!-- Append new entries here -->


### Debugging Insights
<!-- Append new entries here -->


### Domain Knowledge
<!-- Append new entries here -->


### Corrections & Disagreements
<!-- When one AI corrects the other, log it here so we don't repeat mistakes -->


---

## Project Context

<!-- Claude fills this in automatically with project-specific details -->
<!-- Include: tech stack, architecture, key patterns, service map -->
