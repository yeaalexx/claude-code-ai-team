"""
Finding Analyzer — v6.0

Enriches raw audit findings with AI-guided recommendations.
For each finding, produces: recommendation (approve/dismiss), confidence,
reasoning (referencing specific criteria), affected features, severity assessment.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

try:
    from .feature_map import FeatureMap
except ImportError:
    from feature_map import FeatureMap  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# Type alias for the AI caller callback (same as workflows.py)
AiCaller = Callable[[str, str], Awaitable[str]]


async def analyze_finding(
    finding: dict[str, Any],
    feature_map: FeatureMap,
    ai_caller: AiCaller,
    contracts_context: str = "",
) -> dict[str, Any]:
    """Enrich a raw audit finding with AI-guided analysis.

    Takes a raw finding dict from the auditor, builds context from the
    feature map and contracts, calls the AI for analysis, and returns
    an enriched finding with recommendation, confidence, and reasoning.

    Args:
        finding: Raw finding dict (from Finding.to_dict()).
        feature_map: Loaded feature map for dependency lookups.
        ai_caller: Async callback: (system_prompt, user_message) -> response.
        contracts_context: Optional contract text for additional context.

    Returns:
        The finding dict enriched with an 'ai_recommendation' sub-dict containing:
        recommendation, confidence, reasoning, affected_features, severity, similar_past.
    """
    # Build feature context from the finding's file path
    file_path = finding.get("file_path", "")
    affected_features: list[dict[str, Any]] = []
    blast_radius = "unknown"

    if feature_map.is_loaded() and file_path:
        features = feature_map.get_affected_features(file_path)
        affected_features = [
            {
                "name": f.name,
                "services": f.services,
                "blast_radius": f.blast_radius,
                "depends_on": f.depends_on,
            }
            for f in features
        ]
        # Overall blast radius is the max of all affected features
        radii = [f.blast_radius for f in features]
        if "high" in radii:
            blast_radius = "high"
        elif "medium" in radii:
            blast_radius = "medium"
        elif radii:
            blast_radius = "low"

    system_prompt = _build_analysis_system_prompt()
    user_message = _build_analysis_user_message(
        finding=finding,
        affected_features=affected_features,
        blast_radius=blast_radius,
        contracts_context=contracts_context,
    )

    try:
        response = await ai_caller(system_prompt, user_message)
        analysis = _parse_analysis_response(response)
    except Exception as e:
        logger.warning("AI analysis failed for finding %s: %s", finding.get("id"), e)
        analysis = {
            "recommendation": "approve",
            "confidence": 0.0,
            "reasoning": [f"AI analysis failed: {e}"],
            "severity": finding.get("severity", "warning"),
            "similar_past": "",
        }

    # Enrich the finding
    analysis["affected_features"] = [f["name"] for f in affected_features]
    enriched = {**finding, "ai_recommendation": analysis}
    return enriched


async def batch_analyze(
    findings: list[dict[str, Any]],
    feature_map: FeatureMap,
    ai_caller: AiCaller,
    contracts_context: str = "",
) -> list[dict[str, Any]]:
    """Analyze multiple findings efficiently.

    Groups findings by service to share context, then analyzes each one.
    Findings that share a service benefit from shared contract context.

    Args:
        findings: List of raw finding dicts.
        feature_map: Loaded feature map.
        ai_caller: Async AI callback.
        contracts_context: Optional contract text.

    Returns:
        List of enriched finding dicts.
    """
    if not findings:
        return []

    # Group by service for shared context
    by_service: dict[str, list[dict[str, Any]]] = {}
    for f in findings:
        service = f.get("service", "unknown")
        by_service.setdefault(service, []).append(f)

    results: list[dict[str, Any]] = []

    for service, service_findings in by_service.items():
        # Build service-specific contracts context
        service_context = contracts_context
        if feature_map.is_loaded():
            service_features = feature_map.get_features_for_service(service)
            if service_features:
                feature_names = [f.name for f in service_features]
                service_context += f"\n\nFeatures in service '{service}': {', '.join(feature_names)}"

        for finding in service_findings:
            enriched = await analyze_finding(
                finding=finding,
                feature_map=feature_map,
                ai_caller=ai_caller,
                contracts_context=service_context,
            )
            results.append(enriched)

    return results


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _build_analysis_system_prompt() -> str:
    """Build the system prompt for finding analysis."""
    return (
        "You are an expert code auditor analyzing a finding from an automated "
        "contract compliance scanner. Your job is to determine whether this "
        "finding is a genuine issue that needs attention or a false positive "
        "that should be dismissed.\n\n"
        "Evaluate the finding against these criteria:\n"
        "1. Is this production code, or is it test/seed/docs/vendor code?\n"
        "2. Does this violate a specific integration contract?\n"
        "3. What is the blast radius? (check feature dependencies)\n"
        "4. Are there similar past findings that were consistently approved or dismissed?\n"
        "5. Does this have cross-feature impact? (affects features that depend on the changed code)\n\n"
        "Respond with a JSON object (no markdown fences):\n"
        "{\n"
        '  "recommendation": "approve" or "dismiss",\n'
        '  "confidence": 0.0 to 1.0,\n'
        '  "reasoning": ["bullet point 1", "bullet point 2", ...],\n'
        '  "severity": "info" or "warning" or "violation" or "critical",\n'
        '  "similar_past": "brief note about similar past patterns, or empty string"\n'
        "}\n\n"
        "Guidelines:\n"
        "- Recommend 'dismiss' for test files, seed data, docs, vendor/generated code.\n"
        "- Recommend 'approve' for genuine contract violations in production code.\n"
        "- High confidence (>0.8) when the evidence is clear-cut.\n"
        "- Low confidence (<0.5) when it's ambiguous or context-dependent.\n"
        "- 'critical' severity only for compliance risks (e.g., missing audit trail, "
        "tenant isolation breach)."
    )


def _build_analysis_user_message(
    finding: dict[str, Any],
    affected_features: list[dict[str, Any]],
    blast_radius: str,
    contracts_context: str,
) -> str:
    """Build the user message with finding details and context."""
    parts: list[str] = []

    parts.append("## Finding to Analyze")
    parts.append(f"- **ID**: {finding.get('id', 'unknown')}")
    parts.append(f"- **Service**: {finding.get('service', 'unknown')}")
    parts.append(f"- **Severity (scanner)**: {finding.get('severity', 'unknown')}")
    parts.append(f"- **File**: {finding.get('file_path', 'unknown')}")
    if finding.get("line_number"):
        parts.append(f"- **Line**: {finding['line_number']}")
    parts.append(f"- **Description**: {finding.get('description', '')}")
    parts.append(f"- **Suggested fix**: {finding.get('suggested_fix', '')}")
    parts.append(f"- **Contract reference**: {finding.get('contract_reference', '')}")

    if affected_features:
        parts.append("\n## Affected Features (from feature map)")
        parts.append(f"- **Blast radius**: {blast_radius}")
        for feat in affected_features:
            deps = ", ".join(feat["depends_on"]) if feat["depends_on"] else "none"
            parts.append(
                f"- **{feat['name']}** (services: {', '.join(feat['services'])}, "
                f"blast_radius: {feat['blast_radius']}, depends_on: {deps})"
            )

    if contracts_context:
        parts.append("\n## Relevant Contracts")
        parts.append(contracts_context[:4000])  # Limit to avoid context overflow

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------


def _parse_analysis_response(response: str) -> dict[str, Any]:
    """Parse the AI's analysis response into a structured dict.

    Tries JSON parsing first, then falls back to sensible defaults.

    Args:
        response: Raw AI response text.

    Returns:
        Dict with keys: recommendation, confidence, reasoning, severity, similar_past.
    """
    text = response.strip()

    # Strip markdown fences if present
    if "```json" in text:
        start = text.index("```json") + len("```json")
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        text = text[start:end].strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return {
                "recommendation": data.get("recommendation", "approve"),
                "confidence": float(data.get("confidence", 0.5)),
                "reasoning": _as_list(data.get("reasoning", [])),
                "severity": data.get("severity", "warning"),
                "similar_past": str(data.get("similar_past", "")),
            }
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: couldn't parse JSON — use heuristics
    logger.debug("Could not parse AI analysis response as JSON, using defaults")
    recommendation = "approve"
    if any(w in text.lower() for w in ["dismiss", "false positive", "not a real issue"]):
        recommendation = "dismiss"

    return {
        "recommendation": recommendation,
        "confidence": 0.3,
        "reasoning": [f"AI response could not be parsed as JSON. Raw: {text[:200]}"],
        "severity": "warning",
        "similar_past": "",
    }


def _as_list(value: Any) -> list[str]:
    """Coerce a value to a list of strings."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [value]
    return []
