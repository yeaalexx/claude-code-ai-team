#!/usr/bin/env python3
"""Unit tests for the context_builder module (dynamic system prompt assembly)."""

import sys
import tempfile
import shutil
from pathlib import Path

# Add the installed server directory to path
SERVER_DIR = Path.home() / ".claude-mcp-servers" / "multi-ai-collab"
sys.path.insert(0, str(SERVER_DIR))

import memory
import sessions
import context_builder

# Track test results
passed = 0
failed = 0


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        failed += 1


def run_tests():
    global passed, failed

    # Use a temp directory for memory
    test_dir = Path(tempfile.mkdtemp(prefix="grok_context_test_"))

    try:
        print("\n=== Context Builder Module Tests ===\n")

        # Initialize memory and sessions with test data
        memory.initialize(test_dir)
        sessions.initialize(test_dir)
        sessions.ACTIVE_SESSIONS.clear()

        memory.add_learning(
            source="test", category="architecture",
            content="Schema-per-tenant with RLS defense-in-depth is the strongest isolation pattern",
            project="pharma-eln"
        )
        memory.add_learning(
            source="test", category="security",
            content="Always validate JWT tokens at both gateway and service level"
        )
        memory.add_learning(
            source="test", category="performance",
            content="Use connection pooling with minimum 5 connections for microservices"
        )
        memory.add_correction(
            corrector="test",
            original_claim="Always use MongoDB for microservices",
            correction="PostgreSQL with JSONB is often better for microservices needing ACID compliance"
        )

        # --- Test 1: Basic System Prompt ---
        print("[1] Basic System Prompt (no tool, no project)")
        prompt = context_builder.build_system_prompt()
        test("Prompt is non-empty string", isinstance(prompt, str) and len(prompt) > 100)
        test("Contains Grok identity", "Grok" in prompt)
        test("Contains Claude reference", "Claude" in prompt)
        test("Contains learning extraction format", "LEARNING" in prompt)

        # --- Test 2: System Prompt with Tool Context ---
        print("\n[2] System Prompt with Tool Context")
        prompt_ask = context_builder.build_system_prompt(tool_name="ask_grok")
        test("Tool-contextualized prompt generated", len(prompt_ask) > 100)
        # Should include learnings since we added some
        test("Prompt is at least as long as basic",
             len(prompt_ask) >= len(prompt) - 50,
             f"ask_grok={len(prompt_ask)}, basic={len(prompt)}")

        # --- Test 3: System Prompt with Project Filter ---
        print("\n[3] System Prompt with Project Context")
        prompt_proj = context_builder.build_system_prompt(project="pharma-eln")
        test("Project prompt generated", len(prompt_proj) > 100)
        test("Contains project name", "pharma-eln" in prompt_proj)

        # --- Test 4: System Prompt for Code Review ---
        print("\n[4] System Prompt for Code Review Tool")
        prompt_review = context_builder.build_system_prompt(tool_name="grok_code_review")
        test("Code review prompt generated", len(prompt_review) > 100)

        # --- Test 5: Collaboration Session Prompt ---
        print("\n[5] System Prompt for Collaboration Session")
        sid = sessions.create_session(
            task="Design auth module",
            context="FastAPI + JWT"
        )
        sessions.add_turn(sid, "user", "Let's use RS256 for token signing.")
        sessions.add_turn(sid, "assistant", "Agreed, RS256 is right for production.\n[STATUS: AGREE]")

        prompt_collab = context_builder.build_system_prompt(
            tool_name="grok_collaborate",
            session_id=sid
        )
        test("Collaboration prompt generated", len(prompt_collab) > 100)
        test("Contains STATUS protocol", "STATUS" in prompt_collab)

        # --- Test 6: Token Estimation ---
        print("\n[6] Token Estimation")
        short_text = "Hello world"
        long_text = "x" * 3500  # ~1000 tokens at 3.5 chars/token
        short_est = context_builder.estimate_tokens(short_text)
        long_est = context_builder.estimate_tokens(long_text)
        test("Short text estimate > 0", short_est > 0)
        test("Long text estimate reasonable", 800 <= long_est <= 1200,
             f"Got {long_est}")
        test("Longer text = more tokens", long_est > short_est)

        # --- Test 7: Agent Prompt ---
        print("\n[7] Agent Prompt (grok_execute_task)")
        agent_prompt = context_builder.build_agent_prompt(
            task="Implement a JWT validation middleware for FastAPI",
            constraints="Must support both RS256 and HS256. Must be async.",
            output_format="code"
        )
        test("Agent prompt is non-empty", len(agent_prompt) > 50)
        test("Contains task description", "JWT" in agent_prompt)
        test("Contains constraints", "RS256" in agent_prompt or "async" in agent_prompt.lower())
        test("Contains output format instruction", "code" in agent_prompt.lower())

        # --- Test 8: Agent Prompt with Files ---
        print("\n[8] Agent Prompt with File Context")
        agent_prompt_files = context_builder.build_agent_prompt(
            task="Review this authentication module",
            files="def authenticate(token):\n    return jwt.decode(token, SECRET_KEY)",
            output_format="review"
        )
        test("Agent prompt includes file content",
             "authenticate" in agent_prompt_files or "jwt.decode" in agent_prompt_files)

        # --- Test 9: Token Budget Enforcement ---
        print("\n[9] Token Budget Enforcement")
        # Add many learnings to test budget limits
        for i in range(50):
            memory.add_learning(
                source="test", category="code",
                content=f"Test learning number {i}: " + "x" * 200
            )

        prompt_budget = context_builder.build_system_prompt(tool_name="ask_grok")
        tokens = context_builder.estimate_tokens(prompt_budget)
        test("Prompt within budget",
             tokens <= context_builder.DEFAULT_TOKEN_BUDGET * 1.3,
             f"Got {tokens} tokens, budget is {context_builder.DEFAULT_TOKEN_BUDGET}")

        # --- Test 10: Tool Category Mapping ---
        print("\n[10] Tool Category Mapping")
        has_entries = len(context_builder.TOOL_CATEGORY_MAP) > 0
        test("Category map has entries", has_entries,
             f"Map has {len(context_builder.TOOL_CATEGORY_MAP)} entries")

        # Check known tools are mapped
        known_tools = ["ask_grok", "grok_code_review", "grok_debug", "grok_think_deep"]
        for tool in known_tools:
            test(f"{tool} is mapped", tool in context_builder.TOOL_CATEGORY_MAP,
                 f"{tool} not found in TOOL_CATEGORY_MAP")

        # --- Test 11: Empty Memory Prompt ---
        print("\n[11] Prompt with No Learnings")
        # Reset memory to empty
        test_dir2 = Path(tempfile.mkdtemp(prefix="grok_context_empty_"))
        memory.initialize(test_dir2)
        prompt_empty = context_builder.build_system_prompt()
        test("Empty memory still generates valid prompt", len(prompt_empty) > 50)
        test("Still has identity", "Grok" in prompt_empty)
        shutil.rmtree(test_dir2, ignore_errors=True)

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)

    print(f"\n--- Context Builder Module: {passed} passed, {failed} failed ---")
    return failed


if __name__ == "__main__":
    failures = run_tests()
    sys.exit(1 if failures > 0 else 0)
