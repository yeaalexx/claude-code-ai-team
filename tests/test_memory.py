#!/usr/bin/env python3
"""Unit tests for the memory module (Grok persistent memory)."""

import shutil
import sys
import tempfile
from pathlib import Path

# Add the server directory to path (installed location, or repo fallback for CI)
SERVER_DIR = Path.home() / ".claude-mcp-servers" / "multi-ai-collab"
if not SERVER_DIR.exists():
    SERVER_DIR = Path(__file__).resolve().parent.parent / "server"
sys.path.insert(0, str(SERVER_DIR))

import memory  # noqa: E402

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

    # Use a temp directory so we don't pollute real memory
    test_dir = Path(tempfile.mkdtemp(prefix="grok_memory_test_"))

    try:
        print("\n=== Memory Module Tests ===\n")

        # --- Test 1: Initialization ---
        print("[1] Initialization")
        memory.initialize(test_dir)
        test("Memory directory created", (test_dir / "memory").is_dir())
        test("Sessions directory created", (test_dir / "memory" / "sessions").is_dir())
        test("Memory file created", (test_dir / "memory" / "grok-memory.json").is_file())

        data = memory.load_memory()
        test("Memory has version", data.get("version") == 1)
        test("Memory has identity", "role" in data.get("identity", {}))
        test("Learnings is empty list", data.get("learnings") == [])
        test("Corrections is empty list", data.get("corrections") == [])
        test("Statistics initialized", data.get("statistics", {}).get("total_calls") == 0)

        # --- Test 2: Add Learning ---
        print("\n[2] Add Learning")
        result_id = memory.add_learning(
            source="test",
            category="architecture",
            content="Schema-per-tenant is the best isolation pattern for regulated SaaS",
            project="test-project",
        )
        test("Returns learning ID", isinstance(result_id, str) and result_id.startswith("L"))
        test("ID format correct", result_id == "L0001")

        data = memory.load_memory()
        test("Learning count is 1", len(data["learnings"]) == 1)
        test("Learning content stored", "Schema-per-tenant" in data["learnings"][0]["content"])
        test("Learning category correct", data["learnings"][0]["category"] == "architecture")
        test("Learning source correct", data["learnings"][0]["source"] == "test")
        test("Learning project correct", data["learnings"][0]["project"] == "test-project")

        # --- Test 3: Deduplication ---
        print("\n[3] Deduplication")
        dup_id = memory.add_learning(
            source="test",
            category="architecture",
            content="Schema-per-tenant is the best isolation pattern for regulated SaaS",
        )
        test("Duplicate returns existing ID", dup_id == "L0001")

        data = memory.load_memory()
        test("Still only 1 learning", len(data["learnings"]) == 1)

        # --- Test 4: Multiple Learnings ---
        print("\n[4] Multiple Learnings (different categories)")
        id2 = memory.add_learning(
            source="test",
            category="code",
            content="Always use atomic writes (temp file + rename) for critical data files",
        )
        id3 = memory.add_learning(
            source="test",
            category="debugging",
            content="Windows cp1252 encoding breaks emoji in Python stdio — force UTF-8",
        )
        test("Second learning gets L0002", id2 == "L0002")
        test("Third learning gets L0003", id3 == "L0003")

        data = memory.load_memory()
        test("Three learnings stored", len(data["learnings"]) == 3)

        # --- Test 5: Query Learnings ---
        print("\n[5] Query Learnings")
        arch_learnings = memory.query_learnings(category="architecture")
        test("Query by category returns 1", len(arch_learnings) == 1)
        test("Query returns correct content", "Schema-per-tenant" in arch_learnings[0]["content"])

        project_learnings = memory.query_learnings(project="test-project")
        test("Query by project returns results", len(project_learnings) >= 1)

        all_learnings = memory.query_learnings()
        test("Query all returns all 3", len(all_learnings) == 3)

        # --- Test 6: Add Correction ---
        print("\n[6] Add Correction")
        corr_id = memory.add_correction(
            corrector="test",
            original_claim="Schema-per-tenant is always best",
            correction="Schema-per-tenant is best for regulated SaaS but shared-schema can be better for high-scale B2C",
            category="architecture",
        )
        test("Correction returns ID", isinstance(corr_id, str) and corr_id.startswith("C"))

        data = memory.load_memory()
        test("Correction stored", len(data["corrections"]) == 1)
        test("Correction has original", "always best" in data["corrections"][0]["original_claim"])
        test("Correction has corrected text", "shared-schema" in data["corrections"][0]["correction"])

        # --- Test 7: Extract Learnings from Text ---
        print("\n[7] Extract Learnings from Grok Response Text")
        response_text = """
Here's my analysis of the codebase:

The authentication module needs refactoring.

[LEARNING category="security"]
Always validate JWT tokens on both the gateway and individual service level for defense-in-depth
[/LEARNING]

Also, the database queries could be optimized.

[LEARNING category="performance"]
Use database connection pooling with a minimum of 5 connections for microservices handling concurrent requests
[/LEARNING]

That's my review.
"""
        extracted = memory.extract_learnings(response_text)
        test("Extracted 2 learnings", len(extracted) == 2, f"Got {len(extracted)}")
        if len(extracted) >= 2:
            test("First learning is security", extracted[0]["category"] == "security")
            test("First learning has JWT content", "JWT" in extracted[0]["content"])
            test("Second learning is performance", extracted[1]["category"] == "performance")
            test("Second learning has pooling content", "pooling" in extracted[1]["content"])

        # --- Test 8: Strip Learning Blocks ---
        print("\n[8] Strip Learning Blocks from Response")
        stripped = memory.strip_learning_blocks(response_text)
        test("Learning blocks removed", "[LEARNING" not in stripped)
        test("Content preserved", "authentication module" in stripped)

        # --- Test 9: Bulk Push ---
        print("\n[9] Bulk Push Learnings")
        bulk_text = """
- Always use parameterized queries to prevent SQL injection attacks in production
- Docker multi-stage builds reduce final image size by 60-80 percent on average
"""
        bulk_count = memory.bulk_push_learnings(bulk_text, source="claude")
        test("Bulk push returns count", isinstance(bulk_count, int))
        test("Bulk push processed entries", bulk_count >= 2, f"Got {bulk_count}")

        data = memory.load_memory()
        test("Total learnings increased", len(data["learnings"]) >= 5)

        # --- Test 10: Memory Stats ---
        print("\n[10] Memory Stats")
        stats = memory.get_memory_stats()
        test("Stats has total_learnings", stats["total_learnings"] >= 5)
        test("Stats has total_corrections", stats["total_corrections"] == 1)
        test("Stats has learnings_by_category", isinstance(stats.get("learnings_by_category"), dict))
        test("Stats has architecture category", stats["learnings_by_category"].get("architecture", 0) >= 1)
        test("Stats has last_updated", stats.get("last_updated") != "never")

        # --- Test 11: Record Call ---
        print("\n[11] Record Call Statistics")
        memory.record_call("ask_grok")
        memory.record_call("ask_grok")
        memory.record_call("grok_code_review")
        data = memory.load_memory()
        test("Total calls recorded", data["statistics"]["total_calls"] == 3)
        test("ask_grok called twice", data["statistics"]["calls_by_tool"].get("ask_grok") == 2)
        test("grok_code_review called once", data["statistics"]["calls_by_tool"].get("grok_code_review") == 1)

        # --- Test 12: Cache Behavior ---
        print("\n[12] Cache Behavior")
        data1 = memory.load_memory()
        data2 = memory.load_memory()
        test("Cached load returns same object", data1 is data2)

        # --- Test 13: Persistence (reload from disk) ---
        print("\n[13] Persistence (reload from disk)")
        memory._memory_cache = None
        memory._cache_timestamp = 0.0
        data_reloaded = memory.load_memory()
        test("Data persists across cache flush", len(data_reloaded["learnings"]) >= 5)
        test("Corrections persist", len(data_reloaded["corrections"]) == 1)
        test("Statistics persist", data_reloaded["statistics"]["total_calls"] == 3)

        # --- Test 14: Category Detection ---
        print("\n[14] Category Detection Heuristic")
        test("Architecture detected", memory._detect_category("microservice design pattern") == "architecture")
        test("Security detected", memory._detect_category("JWT authentication token") == "security")
        test("Debugging detected", memory._detect_category("debug this error crash") == "debugging")
        test("DevOps detected", memory._detect_category("docker kubernetes deployment") == "devops")
        test("Performance detected", memory._detect_category("cache optimization latency") == "performance")
        test("Testing detected", memory._detect_category("unit test mock coverage") == "testing")
        test("Default is code", memory._detect_category("general programming advice") == "code")

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)

    print(f"\n--- Memory Module: {passed} passed, {failed} failed ---")
    return failed


if __name__ == "__main__":
    failures = run_tests()
    sys.exit(1 if failures > 0 else 0)
