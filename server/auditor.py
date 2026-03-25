"""
Proactive Contract Auditor — v5.0

Periodically scans the codebase for latent contract violations.
Runs on a schedule (not on file changes) and produces recommendations.

The scanner uses grep/file reading (NOT AI calls) to keep it fast and free.
AI calls are only used for the optional final review of findings.

Patterns detected:
- Files importing from other services without contract headers
- API endpoint handlers missing expected header propagation
- Missing Kafka event emissions for mutation operations
- Hardcoded values that should come from shared contracts
"""

from __future__ import annotations

import logging
import re
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .feature_map import FeatureMap

logger = logging.getLogger(__name__)


class Severity:
    """Finding severity levels."""

    INFO = "info"
    WARNING = "warning"
    VIOLATION = "violation"


class FindingStatus:
    """Status of a finding."""

    PENDING = "pending"
    APPROVED = "approved"
    DISMISSED = "dismissed"


@dataclass
class Finding:
    """A single audit finding from the proactive scanner."""

    id: str
    service: str
    severity: str  # info | warning | violation
    description: str
    suggested_fix: str
    contract_reference: str
    status: str = FindingStatus.PENDING  # pending | approved | dismissed
    timestamp: str = ""
    file_path: str = ""
    line_number: int | None = None

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.id:
            self.id = str(uuid.uuid4())[:12]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "service": self.service,
            "severity": self.severity,
            "description": self.description,
            "suggested_fix": self.suggested_fix,
            "contract_reference": self.contract_reference,
            "status": self.status,
            "timestamp": self.timestamp,
            "file_path": self.file_path,
            "line_number": self.line_number,
        }


# --- Pattern Scanners ---
# Each scanner function takes a service name, service path, and contract data,
# and returns a list of Findings.

# Common HTTP mutation methods that should emit Kafka events
_MUTATION_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "python": [
        re.compile(r"@\w+\.(post|put|patch|delete)\(", re.IGNORECASE),
        re.compile(r'methods\s*=\s*\[.*"(POST|PUT|PATCH|DELETE)"', re.IGNORECASE),
    ],
    "typescript": [
        re.compile(r"@(Post|Put|Patch|Delete)\(", re.IGNORECASE),
        re.compile(r"\.(post|put|patch|delete)\s*\(", re.IGNORECASE),
    ],
    "java": [
        re.compile(r"@(PostMapping|PutMapping|PatchMapping|DeleteMapping)", re.IGNORECASE),
        re.compile(r"@RequestMapping\(.*method\s*=\s*RequestMethod\.(POST|PUT|PATCH|DELETE)", re.IGNORECASE),
    ],
}

# Patterns that indicate Kafka/event emission
_KAFKA_EMIT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"kafka|producer|emit_event|publish_event|send_event|produce\(", re.IGNORECASE),
    re.compile(r"EventEmitter|event_bus|message_bus", re.IGNORECASE),
]

# Header propagation patterns
_HEADER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"x-tenant-id|X-Tenant-ID|x_tenant_id", re.IGNORECASE),
    re.compile(r"x-request-id|X-Request-ID|x_request_id", re.IGNORECASE),
    re.compile(r"authorization|Authorization", re.IGNORECASE),
]

# Common hardcoded values that should come from config/contracts
_HARDCODED_PATTERNS: list[tuple[re.Pattern[str], str | None]] = [
    (re.compile(r'["\'](localhost|127\.0\.0\.1):\d{4,5}["\']'), "Hardcoded host:port — should use config/env var"),
    (re.compile(r'["\']application/json["\']'), None),  # This is OK — ignore
    (re.compile(r"schema_[a-f0-9]{8}"), "Hardcoded tenant schema name — should be dynamic"),
    (re.compile(r'["\']Bearer\s+[A-Za-z0-9._-]{20,}["\']'), "Hardcoded bearer token — use auth flow"),
]

# File extensions by language
_LANG_EXTENSIONS: dict[str, list[str]] = {
    "python": [".py"],
    "typescript": [".ts", ".tsx"],
    "javascript": [".js", ".jsx"],
    "java": [".java"],
    "go": [".go"],
}

# Ignore patterns for scanning
_SCAN_IGNORE: list[str] = [
    "node_modules",
    "__pycache__",
    ".git",
    "dist",
    "build",
    ".venv",
    "venv",
    "coverage",
    "target",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "migrations",
    "alembic",
    "*.test.*",
    "*.spec.*",
    "__tests__",
    "test_*",
    "*_test.py",
]


def _should_skip(path: Path) -> bool:
    """Check if a file path should be skipped during scanning."""
    path_str = str(path)
    return any(ignore in path_str for ignore in _SCAN_IGNORE)


def _detect_language(path: Path) -> str | None:
    """Detect the programming language from a file extension."""
    suffix = path.suffix.lower()
    for lang, extensions in _LANG_EXTENSIONS.items():
        if suffix in extensions:
            return lang
    return None


def _read_file_safe(path: Path, max_size: int = 512_000) -> str:
    """Read a file safely, skipping binary or oversized files."""
    try:
        if path.stat().st_size > max_size:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return ""


def _scan_missing_kafka_events(
    service: str,
    service_path: Path,
    contracts: dict[str, str],
) -> list[Finding]:
    """Find mutation endpoints that don't appear to emit Kafka events.

    Scans for HTTP mutation handlers (POST, PUT, PATCH, DELETE) and checks
    whether the same file or a nearby service module references Kafka/event
    emission. If not, it flags a potential missing audit trail event.
    """
    findings: list[Finding] = []

    for file_path in service_path.rglob("*"):
        if not file_path.is_file() or _should_skip(file_path):
            continue

        lang = _detect_language(file_path)
        if lang is None:
            continue

        content = _read_file_safe(file_path)
        if not content:
            continue

        # Check if file has mutation endpoints
        mutation_patterns = _MUTATION_PATTERNS.get(lang, [])
        has_mutation = False
        mutation_lines: list[int] = []

        for i, line in enumerate(content.splitlines(), 1):
            for pattern in mutation_patterns:
                if pattern.search(line):
                    has_mutation = True
                    mutation_lines.append(i)
                    break

        if not has_mutation:
            continue

        # Check if the same file references Kafka/event emission
        has_kafka = any(p.search(content) for p in _KAFKA_EMIT_PATTERNS)

        if not has_kafka:
            findings.append(
                Finding(
                    id=str(uuid.uuid4())[:12],
                    service=service,
                    severity=Severity.WARNING,
                    description=(
                        f"Mutation endpoint(s) found at line(s) {mutation_lines[:5]} "
                        f"but no Kafka/event emission detected in {file_path.name}. "
                        f"Data mutations should emit audit trail events."
                    ),
                    suggested_fix=(
                        "Add event emission after the mutation operation. "
                        "Example: await producer.send_event('entity.mutated', payload)"
                    ),
                    contract_reference="contracts/events/catalog.md — mutation events",
                    file_path=str(file_path),
                    line_number=mutation_lines[0] if mutation_lines else None,
                )
            )

    return findings


def _scan_missing_header_propagation(
    service: str,
    service_path: Path,
    contracts: dict[str, str],
) -> list[Finding]:
    """Find files that make HTTP calls to other services without propagating headers.

    Looks for outbound HTTP client calls (httpx, requests, fetch, axios, HttpClient)
    and checks whether the same file references standard propagation headers.
    """
    findings: list[Finding] = []

    # Patterns for outbound HTTP calls
    http_call_patterns: list[re.Pattern[str]] = [
        re.compile(r"httpx\.(get|post|put|patch|delete|request)\(", re.IGNORECASE),
        re.compile(r"requests\.(get|post|put|patch|delete)\(", re.IGNORECASE),
        re.compile(r"fetch\s*\(", re.IGNORECASE),
        re.compile(r"axios\.(get|post|put|patch|delete)\(", re.IGNORECASE),
        re.compile(r"HttpClient|this\.http\.", re.IGNORECASE),
        re.compile(r"http\.Client|http\.Get|http\.Post", re.IGNORECASE),
    ]

    for file_path in service_path.rglob("*"):
        if not file_path.is_file() or _should_skip(file_path):
            continue

        lang = _detect_language(file_path)
        if lang is None:
            continue

        content = _read_file_safe(file_path)
        if not content:
            continue

        # Check for outbound HTTP calls
        has_http_call = False
        http_lines: list[int] = []

        for i, line in enumerate(content.splitlines(), 1):
            for pattern in http_call_patterns:
                if pattern.search(line):
                    has_http_call = True
                    http_lines.append(i)
                    break

        if not has_http_call:
            continue

        # Check if the file references standard headers
        has_tenant_header = any(p.search(content) for p in _HEADER_PATTERNS[:1])
        has_request_id = any(p.search(content) for p in _HEADER_PATTERNS[1:2])

        missing_headers: list[str] = []
        if not has_tenant_header:
            missing_headers.append("X-Tenant-ID")
        if not has_request_id:
            missing_headers.append("X-Request-ID")

        if missing_headers:
            findings.append(
                Finding(
                    id=str(uuid.uuid4())[:12],
                    service=service,
                    severity=Severity.WARNING,
                    description=(
                        f"Outbound HTTP call(s) at line(s) {http_lines[:5]} in {file_path.name} "
                        f"without propagating header(s): {', '.join(missing_headers)}. "
                        f"Cross-service calls must forward tenant and request context."
                    ),
                    suggested_fix=(
                        f"Add missing headers to outbound requests: "
                        f"{', '.join(missing_headers)}. "
                        f"Use a shared HTTP client wrapper that auto-propagates headers."
                    ),
                    contract_reference="contracts/shared/headers.md — header propagation",
                    file_path=str(file_path),
                    line_number=http_lines[0] if http_lines else None,
                )
            )

    return findings


def _scan_hardcoded_values(
    service: str,
    service_path: Path,
    contracts: dict[str, str],
) -> list[Finding]:
    """Find hardcoded values that should come from configuration or contracts."""
    findings: list[Finding] = []

    for file_path in service_path.rglob("*"):
        if not file_path.is_file() or _should_skip(file_path):
            continue

        lang = _detect_language(file_path)
        if lang is None:
            continue

        content = _read_file_safe(file_path)
        if not content:
            continue

        for i, line in enumerate(content.splitlines(), 1):
            for pattern, message in _HARDCODED_PATTERNS:
                if message is None:
                    continue  # Explicitly allowed pattern
                if pattern.search(line):
                    findings.append(
                        Finding(
                            id=str(uuid.uuid4())[:12],
                            service=service,
                            severity=Severity.INFO,
                            description=f"{message} in {file_path.name}:{i}",
                            suggested_fix=(
                                "Move this value to an environment variable, config file, "
                                "or shared contract definition."
                            ),
                            contract_reference="contracts/shared/ — shared configuration values",
                            file_path=str(file_path),
                            line_number=i,
                        )
                    )
                    break  # One finding per line is enough

    return findings


def _scan_cross_service_imports(
    service: str,
    service_path: Path,
    contracts: dict[str, str],
    project_root: Path | None = None,
) -> list[Finding]:
    """Find files that import directly from other services (bypassing contracts).

    Direct imports between microservices indicate tight coupling. Services should
    communicate via APIs, events, or shared contracts — not by importing each
    other's code.
    """
    findings: list[Finding] = []

    # Patterns for cross-service imports
    cross_import_patterns: list[re.Pattern[str]] = [
        # Python: from services.X.something import ...
        re.compile(r"from\s+services\.(\w+)", re.IGNORECASE),
        # TypeScript: import ... from '../../services/X/...'
        re.compile(r"from\s+['\"].*services/(\w+)", re.IGNORECASE),
        # Go: import "project/services/X/..."
        re.compile(r'"[^"]*services/(\w+)', re.IGNORECASE),
    ]

    for file_path in service_path.rglob("*"):
        if not file_path.is_file() or _should_skip(file_path):
            continue

        lang = _detect_language(file_path)
        if lang is None:
            continue

        content = _read_file_safe(file_path)
        if not content:
            continue

        for i, line in enumerate(content.splitlines(), 1):
            for pattern in cross_import_patterns:
                match = pattern.search(line)
                if match:
                    imported_service = match.group(1)
                    if imported_service != service:
                        findings.append(
                            Finding(
                                id=str(uuid.uuid4())[:12],
                                service=service,
                                severity=Severity.VIOLATION,
                                description=(
                                    f"Direct import from service '{imported_service}' "
                                    f"in {file_path.name}:{i}. Services must communicate "
                                    f"via APIs or events, not direct imports."
                                ),
                                suggested_fix=(
                                    f"Replace the direct import with an API call to "
                                    f"the '{imported_service}' service, or move shared "
                                    f"types to contracts/shared/."
                                ),
                                contract_reference="INTEGRATION_CONTRACTS.md — service boundaries",
                                file_path=str(file_path),
                                line_number=i,
                            )
                        )

    return findings


# Registry of all scanner functions
_SCANNERS: list[
    tuple[str, Any]  # (name, scan_function)
] = [
    ("missing_kafka_events", _scan_missing_kafka_events),
    ("missing_header_propagation", _scan_missing_header_propagation),
    ("hardcoded_values", _scan_hardcoded_values),
    ("cross_service_imports", _scan_cross_service_imports),
]


class ProactiveAuditor:
    """Scans codebases for latent contract violations.

    The auditor runs pattern-based scanners against service code. It does NOT
    make AI calls during scanning (to keep it fast and free). AI is only used
    for the optional final review of aggregated findings.

    Findings are stored in an in-memory bounded buffer.
    """

    def __init__(self, max_findings: int = 200) -> None:
        self._findings: deque[Finding] = deque(maxlen=max_findings)
        self._findings_by_id: dict[str, Finding] = {}
        self._last_scan_at: str | None = None
        self._scan_count: int = 0
        self._feature_map: FeatureMap | None = None

    def set_feature_map(self, feature_map: FeatureMap) -> None:
        """Inject a loaded feature map for cross-feature scanning.

        Args:
            feature_map: A FeatureMap instance (must already be loaded).
        """
        self._feature_map = feature_map

    def scan_service(
        self,
        service_name: str,
        service_path: str | Path,
        contracts: dict[str, str] | None = None,
    ) -> list[Finding]:
        """Scan a single service for contract violations.

        Args:
            service_name: Name of the service (e.g., "lims", "eln-core").
            service_path: Path to the service's root directory.
            contracts: Optional dict of {filename: content} for contract files.
                If not provided, scanners that need contracts will have limited
                effectiveness but still run.

        Returns:
            List of new findings from this scan.
        """
        service_path = Path(service_path)
        if not service_path.is_dir():
            logger.warning("Service path does not exist: %s", service_path)
            return []

        if contracts is None:
            contracts = {}

        new_findings: list[Finding] = []

        for scanner_name, scanner_fn in _SCANNERS:
            try:
                results = scanner_fn(service_name, service_path, contracts)
                new_findings.extend(results)
                logger.debug(
                    "Scanner '%s' found %d issues in %s",
                    scanner_name,
                    len(results),
                    service_name,
                )
            except Exception:
                logger.exception(
                    "Scanner '%s' failed for service %s",
                    scanner_name,
                    service_name,
                )

        # Store findings
        for finding in new_findings:
            self._findings.append(finding)
            self._findings_by_id[finding.id] = finding

        self._last_scan_at = datetime.now(timezone.utc).isoformat()
        self._scan_count += 1

        logger.info("Scanned service '%s': %d findings", service_name, len(new_findings))
        return new_findings

    def scan_all(
        self,
        project_root: str | Path,
        contracts_path: str = "contracts/",
    ) -> list[Finding]:
        """Scan all services in the project for contract violations.

        Discovers services by looking for subdirectories under `services/`.
        Also scans `frontend/` if it exists.

        Args:
            project_root: Path to the project root directory.
            contracts_path: Relative path to contracts directory from project root.

        Returns:
            List of all new findings across all services.
        """
        project_root = Path(project_root).resolve()
        all_findings: list[Finding] = []

        # Load contracts once for all services
        contracts = _load_contracts_from_disk(project_root / contracts_path)

        # Scan services/ directory
        services_dir = project_root / "services"
        if services_dir.is_dir():
            for item in sorted(services_dir.iterdir()):
                if item.is_dir() and not item.name.startswith("."):
                    findings = self.scan_service(item.name, item, contracts)
                    all_findings.extend(findings)

        # Scan frontend/
        frontend_dir = project_root / "frontend"
        if frontend_dir.is_dir():
            findings = self.scan_service("frontend", frontend_dir, contracts)
            all_findings.extend(findings)

        logger.info(
            "Full project scan complete: %d total findings across all services",
            len(all_findings),
        )
        return all_findings

    def get_findings(
        self,
        service: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return findings, optionally filtered.

        Args:
            service: Filter to this service only.
            severity: Filter to this severity only (info/warning/violation).
            status: Filter to this status only (pending/approved/dismissed).
            limit: Maximum number of results (most recent first).

        Returns:
            List of finding dictionaries.
        """
        results = list(self._findings)
        results.reverse()  # Most recent first

        if service is not None:
            results = [f for f in results if f.service == service]
        if severity is not None:
            results = [f for f in results if f.severity == severity]
        if status is not None:
            results = [f for f in results if f.status == status]

        return [f.to_dict() for f in results[:limit]]

    def get_pending_recommendations(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return findings that have not been approved or dismissed.

        Args:
            limit: Maximum number of results.

        Returns:
            List of pending finding dictionaries.
        """
        return self.get_findings(status=FindingStatus.PENDING, limit=limit)

    def approve_finding(self, finding_id: str) -> bool:
        """Mark a finding as approved (confirmed as a real issue).

        Args:
            finding_id: The ID of the finding to approve.

        Returns:
            True if the finding was found and updated, False otherwise.
        """
        finding = self._findings_by_id.get(finding_id)
        if finding is None:
            return False
        finding.status = FindingStatus.APPROVED
        return True

    def dismiss_finding(self, finding_id: str) -> bool:
        """Mark a finding as dismissed (false positive or not applicable).

        Args:
            finding_id: The ID of the finding to dismiss.

        Returns:
            True if the finding was found and updated, False otherwise.
        """
        finding = self._findings_by_id.get(finding_id)
        if finding is None:
            return False
        finding.status = FindingStatus.DISMISSED
        return True

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate statistics about audit findings."""
        findings = list(self._findings)

        by_severity: dict[str, int] = {}
        by_service: dict[str, int] = {}
        by_status: dict[str, int] = {}

        for f in findings:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
            by_service[f.service] = by_service.get(f.service, 0) + 1
            by_status[f.status] = by_status.get(f.status, 0) + 1

        return {
            "total_findings": len(findings),
            "by_severity": by_severity,
            "by_service": by_service,
            "by_status": by_status,
            "scan_count": self._scan_count,
            "last_scan_at": self._last_scan_at,
        }

    def clear_findings(self) -> int:
        """Clear all findings. Returns the count of cleared findings."""
        count = len(self._findings)
        self._findings.clear()
        self._findings_by_id.clear()
        return count

    def scan_feature_interactions(
        self,
        feature_name: str,
        project_root: str | Path,
    ) -> list[Finding]:
        """Scan a specific feature and its dependencies for contract violations.

        Checks whether the feature's `produces` (Kafka events, API calls)
        match what dependent features expect, verifies required patterns
        in owning files, and ensures cross-service headers/contracts are met.

        Args:
            feature_name: Name of the feature to scan.
            project_root: Path to the project root directory.

        Returns:
            List of findings from cross-feature scanning.
        """
        if self._feature_map is None or not self._feature_map.is_loaded():
            logger.warning("Feature map not loaded — skipping feature interaction scan")
            return []

        feature = self._feature_map.get_feature(feature_name)
        if feature is None:
            logger.warning("Feature '%s' not found in feature map", feature_name)
            return []

        project_root = Path(project_root).resolve()
        findings: list[Finding] = []

        # 1. Check required patterns in owning files
        findings.extend(_scan_required_patterns(feature, project_root))

        # 2. Check producer/consumer alignment with dependents
        dependents = self._feature_map.get_dependent_features(feature_name)
        findings.extend(_scan_producer_consumer_alignment(feature, dependents))

        # 3. Check that services listed in the feature actually exist on disk
        findings.extend(_scan_service_existence(feature, project_root))

        # Store findings
        for f in findings:
            self._findings.append(f)
            self._findings_by_id[f.id] = f

        if findings:
            logger.info(
                "Feature interaction scan for '%s': %d findings",
                feature_name,
                len(findings),
            )
        return findings

    def scan_cross_feature(
        self,
        project_root: str | Path,
    ) -> list[Finding]:
        """Scan all feature interactions in the feature map.

        Iterates over every feature and runs `scan_feature_interactions`
        for each one.

        Args:
            project_root: Path to the project root directory.

        Returns:
            List of all findings across all features.
        """
        if self._feature_map is None or not self._feature_map.is_loaded():
            logger.warning("Feature map not loaded — skipping cross-feature scan")
            return []

        project_root = Path(project_root).resolve()
        all_findings: list[Finding] = []

        for feature in self._feature_map.get_all_features():
            findings = self.scan_feature_interactions(feature.name, project_root)
            all_findings.extend(findings)

        logger.info(
            "Cross-feature scan complete: %d total findings across %d features",
            len(all_findings),
            len(self._feature_map.get_all_features()),
        )
        return all_findings


# ---------------------------------------------------------------------------
# Cross-feature scanning helpers
# ---------------------------------------------------------------------------


def _scan_required_patterns(
    feature: Any,
    project_root: Path,
) -> list[Finding]:
    """Check that required patterns are present in the feature's owning files.

    For each required_pattern, scans the owning files to see if the pattern
    text appears anywhere. If not, a finding is raised.
    """
    import fnmatch as _fnmatch

    if not feature.required_patterns or not feature.owning_files:
        return []

    findings: list[Finding] = []

    # Collect all files matching owning_files globs
    owned_files: list[Path] = []
    for glob_pattern in feature.owning_files:
        # Convert glob to a rglob-friendly pattern
        for file_path in project_root.rglob("*"):
            if not file_path.is_file() or _should_skip(file_path):
                continue
            rel = str(file_path.relative_to(project_root)).replace("\\", "/")
            if _fnmatch.fnmatch(rel, glob_pattern):
                owned_files.append(file_path)

    if not owned_files:
        return findings

    # Read all owned file contents (concatenated for pattern search)
    combined_content = ""
    for fp in owned_files[:100]:  # Cap to avoid scanning huge feature sets
        content = _read_file_safe(fp)
        if content:
            combined_content += content + "\n"

    for pattern_desc in feature.required_patterns:
        # Use a simple substring search — the pattern is a human description,
        # not a regex. Check for key terms in the description.
        key_terms = [t.strip().lower() for t in pattern_desc.replace(",", " ").split() if len(t.strip()) > 3]
        # If fewer than half the key terms appear in the codebase, flag it
        matches = sum(1 for term in key_terms if term in combined_content.lower())
        if key_terms and matches < len(key_terms) * 0.3:
            findings.append(
                Finding(
                    id=str(uuid.uuid4())[:12],
                    service=feature.services[0] if feature.services else "unknown",
                    severity=Severity.WARNING,
                    description=(
                        f"Feature '{feature.name}' requires pattern: '{pattern_desc}' "
                        f"but only {matches}/{len(key_terms)} key terms found in owning files."
                    ),
                    suggested_fix=(
                        f"Review the owning files for feature '{feature.name}' and "
                        f"ensure the required pattern is implemented: {pattern_desc}"
                    ),
                    contract_reference=(
                        feature.related_contracts[0]
                        if feature.related_contracts
                        else "FEATURE_MAP.yaml — required_patterns"
                    ),
                )
            )

    return findings


def _scan_producer_consumer_alignment(
    feature: Any,
    dependents: list[Any],
) -> list[Finding]:
    """Check that a feature's produces match what dependents expect.

    If feature A produces "kafka:user.created" and feature B depends on A,
    we check that B's own produces or required_patterns reference what A emits.
    This is a heuristic — it flags potential misalignment.
    """
    if not feature.produces or not dependents:
        return []

    findings: list[Finding] = []

    for dep in dependents:
        # Extract topics/paths from the producer's `produces` list
        for produced in feature.produces:
            # Parse "kafka:topic.name" or "api:POST /path" format
            parts = produced.split(":", 1)
            if len(parts) != 2:
                continue
            protocol, resource = parts[0].strip(), parts[1].strip()

            # Check if the dependent feature references this resource anywhere
            dep_text = " ".join(dep.produces + dep.required_patterns + dep.owning_files).lower()

            resource_lower = resource.lower()
            # Extract the key identifier (topic name or path)
            resource_key = resource_lower.split("/")[-1] if "/" in resource_lower else resource_lower

            if resource_key and resource_key not in dep_text:
                findings.append(
                    Finding(
                        id=str(uuid.uuid4())[:12],
                        service=dep.services[0] if dep.services else "unknown",
                        severity=Severity.INFO,
                        description=(
                            f"Feature '{dep.name}' depends on '{feature.name}' which "
                            f"produces '{produced}', but '{dep.name}' does not appear "
                            f"to reference '{resource_key}' in its configuration."
                        ),
                        suggested_fix=(
                            f"Verify that feature '{dep.name}' correctly consumes or "
                            f"handles the '{protocol}' resource '{resource}' produced "
                            f"by '{feature.name}'."
                        ),
                        contract_reference="FEATURE_MAP.yaml — produces/depends_on alignment",
                    )
                )

    return findings


def _scan_service_existence(
    feature: Any,
    project_root: Path,
) -> list[Finding]:
    """Check that services listed in a feature actually exist on disk."""
    findings: list[Finding] = []

    for service in feature.services:
        service_path = project_root / "services" / service
        frontend_check = service == "frontend" and (project_root / "frontend").is_dir()

        if not service_path.is_dir() and not frontend_check:
            findings.append(
                Finding(
                    id=str(uuid.uuid4())[:12],
                    service=service,
                    severity=Severity.INFO,
                    description=(
                        f"Feature '{feature.name}' lists service '{service}' but "
                        f"no directory found at services/{service}/"
                    ),
                    suggested_fix=(
                        f"Either create the service directory or update FEATURE_MAP.yaml "
                        f"to reflect the correct service path for '{feature.name}'."
                    ),
                    contract_reference="FEATURE_MAP.yaml — services",
                )
            )

    return findings


def _load_contracts_from_disk(contracts_dir: Path) -> dict[str, str]:
    """Load all contract files from a directory into a dict.

    Reads .md and .json files recursively.

    Args:
        contracts_dir: Path to the contracts directory.

    Returns:
        Dictionary of {relative_filename: file_content}.
    """
    contracts: dict[str, str] = {}

    if not contracts_dir.is_dir():
        return contracts

    for file_path in contracts_dir.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in (".md", ".json", ".yaml", ".yml"):
            continue
        if _should_skip(file_path):
            continue

        try:
            rel_path = str(file_path.relative_to(contracts_dir))
            content = file_path.read_text(encoding="utf-8", errors="replace")
            contracts[rel_path] = content
        except OSError:
            logger.warning("Failed to read contract file: %s", file_path)

    return contracts
