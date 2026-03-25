"""
Auto-Review Threshold Engine — v1.0

Evaluates changed file lists against configurable threshold rules to determine
whether an automatic Grok code review should be triggered, and what type.

Supports:
- Default rules from defaults/threshold-rules.json
- Per-project overrides via ai-team-thresholds.json in the project root
- Force/skip overrides via parameters

Used by the grok_auto_review MCP tool.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Resolve the defaults directory (relative to this file's location in server/)
_DEFAULTS_DIR = Path(__file__).resolve().parent.parent / "defaults"
_DEFAULT_RULES_PATH = _DEFAULTS_DIR / "threshold-rules.json"


def load_rules(project_root: str = "") -> dict[str, Any]:
    """Load threshold rules with optional per-project overrides.

    Priority: project ai-team-thresholds.json > defaults/threshold-rules.json > hardcoded fallback.
    """
    # Start with hardcoded fallback (in case JSON files are missing)
    rules: dict[str, Any] = {
        "thresholds": {"frontend_file_count": 8, "total_file_count": 12, "skip_below_file_count": 5},
        "sensitive_patterns": ["auth", "tenant", "branding", "routing", "nginx"],
        "deploy_patterns": ["docker-compose", "Dockerfile", ".tf", "terraform"],
        "integration_patterns": ["controller", "router", "middleware", "gateway"],
        "frontend_extensions": [".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss"],
        "excluded_paths": ["node_modules/", "dist/", "build/", ".git/", "__pycache__/"],
    }

    # Load defaults
    if _DEFAULT_RULES_PATH.exists():
        try:
            with open(_DEFAULT_RULES_PATH, "r") as f:
                defaults = json.load(f)
            rules.update(defaults)
        except Exception as e:
            logger.warning("Failed to load default threshold rules: %s", e)

    # Load per-project overrides
    if project_root:
        project_overrides = Path(project_root) / "ai-team-thresholds.json"
        if project_overrides.exists():
            try:
                with open(project_overrides, "r") as f:
                    overrides = json.load(f)
                # Merge: override-level keys replace default-level keys
                for key, value in overrides.items():
                    if isinstance(value, dict) and isinstance(rules.get(key), dict):
                        rules[key].update(value)
                    else:
                        rules[key] = value
            except Exception as e:
                logger.warning("Failed to load project threshold overrides: %s", e)

    return rules


def _filter_excluded(files: list[str], excluded_paths: list[str]) -> list[str]:
    """Remove files matching excluded path prefixes."""
    result = []
    for f in files:
        normalized = f.replace("\\", "/")
        if not any(excl in normalized for excl in excluded_paths):
            result.append(f)
    return result


def _matches_any_pattern(filepath: str, patterns: list[str]) -> bool:
    """Check if a filepath contains any of the given patterns (case-insensitive)."""
    lower = filepath.lower().replace("\\", "/")
    return any(p.lower() in lower for p in patterns)


def _count_frontend_files(files: list[str], frontend_extensions: list[str]) -> int:
    """Count files with frontend extensions."""
    return sum(1 for f in files if any(f.lower().endswith(ext) for ext in frontend_extensions))


def evaluate_thresholds(
    changed_files: list[str],
    diff_summary: str = "",
    skip_review: bool = False,
    force_review: bool = False,
    project_root: str = "",
) -> dict[str, Any]:
    """Evaluate changed files against threshold rules.

    Returns a dict describing the review decision:
        {
            "review_triggered": bool,
            "review_type": "full" | "deploy" | "integration" | "skipped",
            "threshold_reason": str,
            "matched_patterns": list[str],
        }
    """
    # Override: skip
    if skip_review:
        return {
            "review_triggered": False,
            "review_type": "skipped",
            "threshold_reason": "skip_review=true override",
            "matched_patterns": [],
        }

    rules = load_rules(project_root)
    thresholds = rules.get("thresholds", {})
    sensitive_patterns = rules.get("sensitive_patterns", [])
    deploy_patterns = rules.get("deploy_patterns", [])
    integration_patterns = rules.get("integration_patterns", [])
    frontend_extensions = rules.get("frontend_extensions", [])
    excluded_paths = rules.get("excluded_paths", [])

    # Filter out excluded paths
    effective_files = _filter_excluded(changed_files, excluded_paths)
    total = len(effective_files)

    # Override: force
    if force_review:
        return {
            "review_triggered": True,
            "review_type": "full",
            "threshold_reason": f"force_review=true override ({total} files)",
            "matched_patterns": ["force_review"],
        }

    # Collect all matching reasons
    reasons: list[str] = []
    matched_patterns: list[str] = []

    # Check sensitive patterns (auth, tenant, etc.)
    sensitive_matches = [f for f in effective_files if _matches_any_pattern(f, sensitive_patterns)]
    if sensitive_matches:
        matched_names = [p for p in sensitive_patterns if any(p.lower() in f.lower() for f in sensitive_matches)]
        reasons.append(f"sensitive patterns matched: {', '.join(matched_names)}")
        matched_patterns.extend(matched_names)

    # Check deploy patterns
    deploy_matches = [f for f in effective_files if _matches_any_pattern(f, deploy_patterns)]
    if deploy_matches:
        matched_names = [p for p in deploy_patterns if any(p.lower() in f.lower() for f in deploy_matches)]
        reasons.append(f"deploy patterns matched: {', '.join(matched_names)}")
        matched_patterns.extend(matched_names)

    # Check integration patterns
    integration_matches = [f for f in effective_files if _matches_any_pattern(f, integration_patterns)]
    if integration_matches:
        matched_names = [p for p in integration_patterns if any(p.lower() in f.lower() for f in integration_matches)]
        reasons.append(f"integration patterns matched: {', '.join(matched_names)}")
        matched_patterns.extend(matched_names)

    # Check frontend file count
    frontend_count = _count_frontend_files(effective_files, frontend_extensions)
    frontend_threshold = thresholds.get("frontend_file_count", 8)
    if frontend_count >= frontend_threshold:
        reasons.append(f"{frontend_count} frontend files (threshold: {frontend_threshold})")
        matched_patterns.append("frontend_file_count")

    # Check total file count
    total_threshold = thresholds.get("total_file_count", 12)
    if total >= total_threshold:
        reasons.append(f"{total} total files (threshold: {total_threshold})")
        matched_patterns.append("total_file_count")

    # If nothing matched and below skip threshold, skip
    skip_below = thresholds.get("skip_below_file_count", 5)
    if not reasons and total < skip_below:
        return {
            "review_triggered": False,
            "review_type": "skipped",
            "threshold_reason": f"{total} files, below {skip_below} threshold, no sensitive patterns",
            "matched_patterns": [],
        }

    # If nothing matched but file count is moderate, still skip
    if not reasons:
        return {
            "review_triggered": False,
            "review_type": "skipped",
            "threshold_reason": f"{total} files, no threshold rules matched",
            "matched_patterns": [],
        }

    # Determine review type based on what matched
    if deploy_matches and not sensitive_matches and not integration_matches:
        review_type = "deploy"
    elif integration_matches and not sensitive_matches and not deploy_matches:
        review_type = "integration"
    else:
        # Sensitive patterns, multiple pattern types, or high file counts → full review
        review_type = "full"

    return {
        "review_triggered": True,
        "review_type": review_type,
        "threshold_reason": "; ".join(reasons),
        "matched_patterns": matched_patterns,
    }


def parse_review_findings(quality_result: str, compliance_result: str = "") -> dict[str, Any]:
    """Parse Grok's review responses into structured pass/warn/fail findings.

    Analyzes the text of Grok's responses to determine severity levels.
    Returns a structured findings dict.
    """
    findings: dict[str, Any] = {
        "quality": {"status": "pass", "issues": []},
        "integration": {"status": "pass", "issues": []},
        "compliance": {"status": "pass", "issues": []},
        "learnings": [],
    }

    # Keywords that indicate issues at different severity levels
    fail_keywords = [
        "critical",
        "vulnerability",
        "security hole",
        "data leak",
        "injection",
        "broken",
        "crash",
        "fatal",
        "must fix",
        "blocking",
    ]
    warn_keywords = [
        "warning",
        "concern",
        "should",
        "consider",
        "potential issue",
        "risk",
        "missing",
        "incomplete",
        "inconsistent",
        "deprecated",
    ]

    def _assess_section(text: str, section_name: str) -> dict[str, Any]:
        """Assess a review section and return status + issues."""
        if not text:
            return {"status": "pass", "issues": []}

        lower = text.lower()
        issues: list[str] = []

        has_fail = any(kw in lower for kw in fail_keywords)
        has_warn = any(kw in lower for kw in warn_keywords)

        # Extract bullet points or numbered items as issues
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith(("-", "*", "•")) or (
                len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in ".)"
            ):
                # Remove the bullet/number prefix
                issue = stripped.lstrip("-*•0123456789.) ").strip()
                if issue and len(issue) > 10:
                    issues.append(issue)

        if has_fail:
            status = "fail"
        elif has_warn or issues:
            status = "warn"
        else:
            status = "pass"

        return {"status": status, "issues": issues[:10]}  # Cap at 10 issues per section

    # Assess quality from the first review call
    if quality_result:
        # Try to split quality result into quality vs integration sections
        lower_result = quality_result.lower()

        # Look for integration-related sections
        integration_markers = ["integration", "contract", "header propagation", "tenant isolation", "service boundar"]

        # Simple heuristic: split on section headers
        quality_text = quality_result
        integration_text = ""

        for marker in integration_markers:
            idx = lower_result.find(marker)
            if idx > 0:
                # Found integration section, split there
                integration_text = quality_result[max(0, idx - 50) :]
                quality_text = quality_result[:idx]
                break

        findings["quality"] = _assess_section(quality_text, "quality")
        if integration_text:
            findings["integration"] = _assess_section(integration_text, "integration")

    # Assess compliance from the second review call
    if compliance_result:
        findings["compliance"] = _assess_section(compliance_result, "compliance")

        # Also check for integration issues in compliance result
        if findings["integration"]["status"] == "pass":
            integration_check = _assess_section(compliance_result, "integration")
            if integration_check["status"] != "pass":
                findings["integration"] = integration_check

    return findings


def determine_recommendation(findings: dict[str, Any]) -> str:
    """Determine overall recommendation based on findings.

    Returns: "proceed" | "fix_before_commit" | "discuss_with_user"
    """
    statuses = [
        findings.get("quality", {}).get("status", "pass"),
        findings.get("integration", {}).get("status", "pass"),
        findings.get("compliance", {}).get("status", "pass"),
    ]

    if "fail" in statuses:
        return "fix_before_commit"
    elif statuses.count("warn") >= 2:
        return "discuss_with_user"
    elif "warn" in statuses:
        return "proceed"
    else:
        return "proceed"
