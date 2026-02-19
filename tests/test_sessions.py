#!/usr/bin/env python3
"""Unit tests for the sessions module (multi-turn collaboration)."""

import sys
import json
import tempfile
import shutil
from pathlib import Path

# Add the installed server directory to path
SERVER_DIR = Path.home() / ".claude-mcp-servers" / "multi-ai-collab"
sys.path.insert(0, str(SERVER_DIR))

import memory
import sessions

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

    # Use a temp directory for session transcripts
    test_dir = Path(tempfile.mkdtemp(prefix="grok_sessions_test_"))

    try:
        print("\n=== Sessions Module Tests ===\n")

        # Initialize both memory and sessions
        memory.initialize(test_dir)
        sessions.initialize(test_dir)

        # Clear any existing sessions
        sessions.ACTIVE_SESSIONS.clear()

        # --- Test 1: Create Session ---
        print("[1] Create Session")
        sid = sessions.create_session(
            task="Design the authentication module",
            context="Building a FastAPI microservice with JWT auth",
            project="test-project"
        )
        test("Returns session ID string", isinstance(sid, str))
        test("Session ID has prefix", sid.startswith("sess_"))
        test("Session ID has 12 hex chars", len(sid) == 17)  # "sess_" + 12 hex

        session = sessions.get_session(sid)
        test("Session retrievable", session is not None)
        test("Session has task", session["task"] == "Design the authentication module")
        test("Session has project", session["project"] == "test-project")
        test("Session has context", session["context"] == "Building a FastAPI microservice with JWT auth")
        test("Status is active", session["status"] == "active")
        test("History is empty", len(session["history"]) == 0)
        test("Turn count is 0", session["turn_count"] == 0)

        # --- Test 2: Add Turns ---
        print("\n[2] Add Turns")
        sessions.add_turn(sid, "user", "I think we should use JWT with RS256 for token signing.")
        session = sessions.get_session(sid)
        test("User turn added", len(session["history"]) == 1)
        test("Turn count still 0 (user turn)", session["turn_count"] == 0)

        sessions.add_turn(sid, "assistant",
            "I agree with RS256 for production but suggest also supporting HS256 for dev.\n[STATUS: PARTIAL]")
        session = sessions.get_session(sid)
        test("Assistant turn added", len(session["history"]) == 2)
        test("Turn count is 1 (assistant)", session["turn_count"] == 1)

        sessions.add_turn(sid, "user",
            "Good point. We'll use RS256 in production and HS256 in dev via environment config.")
        sessions.add_turn(sid, "assistant",
            "That's clean. Environment-based algorithm selection is the right pattern.\n[STATUS: AGREE]")
        session = sessions.get_session(sid)
        test("Four messages total", len(session["history"]) == 4)
        test("Turn count is 2", session["turn_count"] == 2)

        # --- Test 3: Get History (for API calls) ---
        print("\n[3] Get History for Context Injection")
        history = sessions.get_history(sid)
        test("History is list", isinstance(history, list))
        test("History has 4 entries", len(history) == 4)
        test("First message is user role", history[0]["role"] == "user")
        test("Second message is assistant role", history[1]["role"] == "assistant")
        test("History is a copy (not reference)", history is not session["history"])

        # --- Test 4: Consensus Detection — Single AGREE ---
        print("\n[4] Consensus Detection — First AGREE")
        grok_agree_response = "Environment-based algorithm selection is the right pattern.\n[STATUS: AGREE]"
        status = sessions.detect_consensus(sid, grok_agree_response)
        session = sessions.get_session(sid)
        test("Status returned as string", isinstance(status, str))
        test("One AGREE counted", session["consecutive_agrees"] == 1)
        test("Not yet consensus", status != "consensus")

        # --- Test 5: Consensus Detection — Two AGREEs = Consensus ---
        print("\n[5] Consensus Detection — Two AGREEs = Consensus")
        sessions.add_turn(sid, "user", "Let's finalize this approach.")
        grok_agree2 = "Agreed, this is the right architecture for this service.\n[STATUS: AGREE]"
        sessions.add_turn(sid, "assistant", grok_agree2)
        status2 = sessions.detect_consensus(sid, grok_agree2)
        session = sessions.get_session(sid)
        test("Two AGREEs counted", session["consecutive_agrees"] == 2)
        test("Consensus reached", status2 == "consensus")

        # --- Test 6: Disagreement Detection ---
        print("\n[6] Disagreement Detection — 3 DISAGREEs = Persistent")
        sid2 = sessions.create_session(
            task="Choose database engine",
            context="Need to pick between PostgreSQL and MongoDB"
        )

        sessions.add_turn(sid2, "user", "PostgreSQL is better — we need ACID transactions.")
        r1 = "MongoDB's document model fits the schema-less data better.\n[STATUS: DISAGREE]"
        sessions.add_turn(sid2, "assistant", r1)
        s1 = sessions.detect_consensus(sid2, r1)
        test("First DISAGREE counted", sessions.get_session(sid2)["consecutive_disagrees"] == 1)
        test("Status still active", s1 == "active")

        sessions.add_turn(sid2, "user", "But we need referential integrity for billing.")
        r2 = "Billing is only 20% of the data. MongoDB handles the other 80% better.\n[STATUS: DISAGREE]"
        sessions.add_turn(sid2, "assistant", r2)
        s2 = sessions.detect_consensus(sid2, r2)
        test("Second DISAGREE counted", sessions.get_session(sid2)["consecutive_disagrees"] == 2)

        sessions.add_turn(sid2, "user", "I still think PostgreSQL with JSONB covers both needs.")
        r3 = "PostgreSQL JSONB lacks MongoDB's aggregation pipeline power.\n[STATUS: DISAGREE]"
        sessions.add_turn(sid2, "assistant", r3)
        s3 = sessions.detect_consensus(sid2, r3)
        test("Three DISAGREEs counted", sessions.get_session(sid2)["consecutive_disagrees"] == 3)
        test("Persistent disagreement detected", s3 == "persistent_disagreement")

        # --- Test 7: AGREE resets DISAGREE counter ---
        print("\n[7] AGREE Resets DISAGREE Counter")
        sid3 = sessions.create_session(task="Test counter reset")
        sessions.add_turn(sid3, "user", "Option A")
        r_dis = "I disagree.\n[STATUS: DISAGREE]"
        sessions.add_turn(sid3, "assistant", r_dis)
        sessions.detect_consensus(sid3, r_dis)
        test("One DISAGREE", sessions.get_session(sid3)["consecutive_disagrees"] == 1)

        sessions.add_turn(sid3, "user", "How about option B?")
        r_agr = "That works.\n[STATUS: AGREE]"
        sessions.add_turn(sid3, "assistant", r_agr)
        sessions.detect_consensus(sid3, r_agr)
        test("DISAGREE reset to 0", sessions.get_session(sid3)["consecutive_disagrees"] == 0)
        test("AGREE set to 1", sessions.get_session(sid3)["consecutive_agrees"] == 1)

        # --- Test 8: Status Line Stripping ---
        print("\n[8] Status Line Stripping")
        text_with_status = "This is my analysis.\n[STATUS: AGREE]"
        stripped = sessions.strip_status_line(text_with_status)
        test("Status line removed", "[STATUS:" not in stripped)
        test("Content preserved", "This is my analysis." in stripped)

        text_without_status = "Plain text with no status marker."
        stripped2 = sessions.strip_status_line(text_without_status)
        test("Text without status unchanged", stripped2 == text_without_status)

        # --- Test 9: End Session ---
        print("\n[9] End Session")
        ended = sessions.end_session(sid)
        test("End returns session dict", isinstance(ended, dict))
        test("Ended session has history", len(ended.get("history", [])) >= 4)
        test("Ended session has ended timestamp", "ended" in ended)
        test("Session removed from active", sessions.get_session(sid) is None)

        # Check transcript file was saved
        transcript_file = test_dir / "memory" / "sessions" / f"{sid}.json"
        test("Transcript file created", transcript_file.is_file())
        if transcript_file.is_file():
            transcript = json.loads(transcript_file.read_text(encoding="utf-8"))
            test("Transcript has history", len(transcript.get("history", [])) >= 4)
            test("Transcript has task", transcript.get("task") == "Design the authentication module")

        # --- Test 10: List Sessions ---
        print("\n[10] List Sessions")
        session_list = sessions.list_sessions()
        test("List returns list", isinstance(session_list, list))
        # sid was ended, sid2 and sid3 should still be active
        active_ids = [s["id"] for s in session_list]
        test("Ended session not in list", sid not in active_ids)
        test("Active sessions still listed", sid2 in active_ids)

        # --- Test 11: Multiple Concurrent Sessions ---
        print("\n[11] Multiple Concurrent Sessions")
        sid_a = sessions.create_session(task="Task A")
        sid_b = sessions.create_session(task="Task B")
        test("Different session IDs", sid_a != sid_b)

        sessions.add_turn(sid_a, "user", "Working on Task A")
        sessions.add_turn(sid_b, "user", "Working on Task B")

        state_a = sessions.get_session(sid_a)
        state_b = sessions.get_session(sid_b)
        test("Session A has 1 message", len(state_a["history"]) == 1)
        test("Session B has 1 message", len(state_b["history"]) == 1)
        test("Sessions are independent",
             state_a["history"][0]["content"] != state_b["history"][0]["content"])

        # --- Test 12: Invalid Session ID ---
        print("\n[12] Invalid Session ID Handling")
        test("get_session returns None", sessions.get_session("invalid_id") is None)
        test("get_history returns empty", sessions.get_history("invalid_id") == [])
        test("detect_consensus returns error",
             sessions.detect_consensus("invalid_id", "text") == "error")
        test("end_session returns None", sessions.end_session("invalid_id") is None)

        try:
            sessions.add_turn("invalid_id", "user", "test")
            test("add_turn raises ValueError", False, "Should have raised ValueError")
        except ValueError:
            test("add_turn raises ValueError", True)

        # --- Test 13: Session Summary ---
        print("\n[13] Session Summary")
        summary = sessions.get_session_summary(sid_a)
        test("Summary is non-empty string", isinstance(summary, str) and len(summary) > 0)
        test("Summary contains task", "Task A" in summary)

        test("Invalid session returns empty", sessions.get_session_summary("invalid") == "")

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)

    print(f"\n--- Sessions Module: {passed} passed, {failed} failed ---")
    return failed


if __name__ == "__main__":
    failures = run_tests()
    sys.exit(1 if failures > 0 else 0)
