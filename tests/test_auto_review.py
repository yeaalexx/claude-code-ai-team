#!/usr/bin/env python3
"""Unit tests for the auto_review threshold engine."""

import json
import sys
import tempfile
from pathlib import Path

# Add the server directory to path — prefer repo version for development
REPO_SERVER_DIR = Path(__file__).resolve().parent.parent / "server"
INSTALL_DIR = Path.home() / ".claude-mcp-servers" / "multi-ai-collab"
sys.path.insert(0, str(REPO_SERVER_DIR))
if INSTALL_DIR.exists():
    sys.path.insert(1, str(INSTALL_DIR))

import auto_review  # noqa: E402

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

    print("\n=== Auto-Review Threshold Engine Tests ===\n")

    # --- Test 1: Skip override ---
    print("[1] Skip Override")
    result = auto_review.evaluate_thresholds(
        changed_files=["src/auth/guard.ts", "src/tenant/middleware.ts"],
        skip_review=True,
    )
    test("skip_review returns not triggered", result["review_triggered"] is False)
    test("skip_review type is skipped", result["review_type"] == "skipped")
    test("skip_review reason mentions override", "override" in result["threshold_reason"])

    # --- Test 2: Force override ---
    print("\n[2] Force Override")
    result = auto_review.evaluate_thresholds(
        changed_files=["src/utils/format.ts"],
        force_review=True,
    )
    test("force_review returns triggered", result["review_triggered"] is True)
    test("force_review type is full", result["review_type"] == "full")
    test("force_review reason mentions override", "override" in result["threshold_reason"])

    # --- Test 3: Sensitive pattern matching ---
    print("\n[3] Sensitive Pattern Matching")
    result = auto_review.evaluate_thresholds(
        changed_files=["src/auth/guard.ts", "src/tenant/middleware.ts"],
    )
    test("auth+tenant triggers review", result["review_triggered"] is True)
    test("auth+tenant is full review", result["review_type"] == "full")
    test("auth pattern matched", "auth" in result["matched_patterns"])
    test("tenant pattern matched", "tenant" in result["matched_patterns"])

    # --- Test 4: Deploy patterns ---
    print("\n[4] Deploy Pattern Matching")
    result = auto_review.evaluate_thresholds(
        changed_files=["docker-compose.yml", "terraform/main.tf"],
    )
    test("deploy files trigger review", result["review_triggered"] is True)
    test("deploy files get deploy review type", result["review_type"] == "deploy")

    # --- Test 5: Integration patterns ---
    print("\n[5] Integration Pattern Matching")
    result = auto_review.evaluate_thresholds(
        changed_files=["src/controller/users.ts", "src/router/index.ts"],
    )
    test("controller+router triggers review", result["review_triggered"] is True)
    test("controller+router is integration type", result["review_type"] == "integration")

    # --- Test 6: Below skip threshold ---
    print("\n[6] Below Skip Threshold (no sensitive patterns)")
    result = auto_review.evaluate_thresholds(
        changed_files=["src/utils/format.ts", "src/helpers/date.ts"],
    )
    test("2 safe files not triggered", result["review_triggered"] is False)
    test("2 safe files type is skipped", result["review_type"] == "skipped")

    # --- Test 7: Frontend file count threshold ---
    print("\n[7] Frontend File Count Threshold")
    frontend_files = [f"src/components/Component{i}.tsx" for i in range(9)]
    result = auto_review.evaluate_thresholds(changed_files=frontend_files)
    test("9 frontend files triggers review", result["review_triggered"] is True)
    test("frontend threshold matched", "frontend_file_count" in result["matched_patterns"])

    # --- Test 8: Total file count threshold ---
    print("\n[8] Total File Count Threshold")
    many_files = [f"src/module{i}/index.ts" for i in range(13)]
    result = auto_review.evaluate_thresholds(changed_files=many_files)
    test("13 files triggers review", result["review_triggered"] is True)
    test("total_file_count matched", "total_file_count" in result["matched_patterns"])

    # --- Test 9: Excluded paths filtered ---
    print("\n[9] Excluded Paths Filtering")
    result = auto_review.evaluate_thresholds(
        changed_files=[
            "node_modules/pkg/auth.js",
            "dist/bundle.js",
            "src/utils/helper.ts",
        ],
    )
    test("node_modules/dist files excluded, 1 file below threshold", result["review_triggered"] is False)

    # --- Test 10: Mixed patterns -> full review ---
    print("\n[10] Mixed Patterns (sensitive + deploy)")
    result = auto_review.evaluate_thresholds(
        changed_files=["src/auth/login.ts", "docker-compose.yml"],
    )
    test("mixed patterns triggers review", result["review_triggered"] is True)
    test("mixed patterns gets full review", result["review_type"] == "full")

    # --- Test 11: Empty file list ---
    print("\n[11] Empty File List")
    result = auto_review.evaluate_thresholds(changed_files=[])
    test("empty list not triggered", result["review_triggered"] is False)

    # --- Test 12: parse_review_findings ---
    print("\n[12] Parse Review Findings")
    quality = (
        "## Quality Review\n"
        "- Missing error handling in auth service\n"
        "- Warning: deprecated API usage detected\n"
        "## Integration\n"
        "- Critical: tenant header not propagated to downstream service\n"
    )
    compliance = (
        "## Compliance\n- Warning: audit trail missing for delete operations\n- Consider adding timestamp validation\n"
    )
    findings = auto_review.parse_review_findings(quality, compliance)
    test("quality has issues", len(findings["quality"]["issues"]) > 0)
    test("integration detected from quality text", findings["integration"]["status"] in ("warn", "fail"))
    test("compliance has warn status", findings["compliance"]["status"] in ("warn", "fail"))

    # --- Test 13: determine_recommendation ---
    print("\n[13] Determine Recommendation")
    test(
        "all pass -> proceed",
        auto_review.determine_recommendation(
            {
                "quality": {"status": "pass"},
                "integration": {"status": "pass"},
                "compliance": {"status": "pass"},
            }
        )
        == "proceed",
    )
    test(
        "one fail -> fix_before_commit",
        auto_review.determine_recommendation(
            {
                "quality": {"status": "fail"},
                "integration": {"status": "pass"},
                "compliance": {"status": "pass"},
            }
        )
        == "fix_before_commit",
    )
    test(
        "two warns -> discuss_with_user",
        auto_review.determine_recommendation(
            {
                "quality": {"status": "warn"},
                "integration": {"status": "warn"},
                "compliance": {"status": "pass"},
            }
        )
        == "discuss_with_user",
    )
    test(
        "one warn -> proceed",
        auto_review.determine_recommendation(
            {
                "quality": {"status": "warn"},
                "integration": {"status": "pass"},
                "compliance": {"status": "pass"},
            }
        )
        == "proceed",
    )

    # --- Test 14: load_rules defaults ---
    print("\n[14] Load Rules")
    rules = auto_review.load_rules()
    test("rules have thresholds", "thresholds" in rules)
    test("rules have sensitive_patterns", "sensitive_patterns" in rules)
    test("auth in sensitive patterns", "auth" in rules["sensitive_patterns"])

    # --- Test 15: Project-specific overrides ---
    print("\n[15] Project-Specific Overrides")
    test_dir = Path(tempfile.mkdtemp(prefix="auto_review_test_"))
    override_file = test_dir / "ai-team-thresholds.json"
    override_file.write_text(
        json.dumps(
            {
                "thresholds": {"skip_below_file_count": 2},
                "sensitive_patterns": ["auth", "custom-pattern"],
            }
        )
    )
    rules = auto_review.load_rules(str(test_dir))
    test("override applied: skip_below is 2", rules["thresholds"]["skip_below_file_count"] == 2)
    test("override applied: custom pattern", "custom-pattern" in rules["sensitive_patterns"])
    # Clean up
    override_file.unlink()
    test_dir.rmdir()

    # --- Test 16: Nginx pattern matching ---
    print("\n[16] Nginx Pattern Matching")
    result = auto_review.evaluate_thresholds(
        changed_files=["nginx/default.conf", "src/utils/helper.ts"],
    )
    test("nginx triggers review", result["review_triggered"] is True)
    test("nginx pattern matched", "nginx" in result["matched_patterns"])

    # --- Summary ---
    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed > 0:
        print("SOME TESTS FAILED!")
        return 1
    else:
        print("ALL TESTS PASSED!")
        return 0


if __name__ == "__main__":
    sys.exit(run_tests())
