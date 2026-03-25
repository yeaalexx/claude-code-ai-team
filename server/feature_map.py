"""
Feature Map — v6.0

Parses FEATURE_MAP.yaml to build a dependency graph of features, services,
and their interactions. Enables cross-feature auditing by understanding
which features depend on each other and how they communicate.
"""

import fnmatch
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Feature:
    """A single feature in the feature map with its dependencies and metadata."""

    name: str
    services: list[str] = field(default_factory=list)
    owning_files: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    produces: list[str] = field(default_factory=list)
    required_patterns: list[str] = field(default_factory=list)
    related_contracts: list[str] = field(default_factory=list)
    blast_radius: str = "low"  # "low" | "medium" | "high"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "services": self.services,
            "owning_files": self.owning_files,
            "depends_on": self.depends_on,
            "produces": self.produces,
            "required_patterns": self.required_patterns,
            "related_contracts": self.related_contracts,
            "blast_radius": self.blast_radius,
        }


class FeatureMap:
    """In-memory graph of features, services, and their dependencies.

    Loaded from a FEATURE_MAP.yaml file. Provides lookup methods for
    querying which features are affected by a code change, which features
    depend on a given feature, and the full transitive dependency chain.
    """

    def __init__(self) -> None:
        self._features: dict[str, Feature] = {}
        self._loaded: bool = False
        self._source_path: Path | None = None

    def load(self, yaml_path: Path) -> None:
        """Parse FEATURE_MAP.yaml and build the internal graph.

        Args:
            yaml_path: Path to the FEATURE_MAP.yaml file.

        Raises:
            FileNotFoundError: If the YAML file does not exist.
            ValueError: If the YAML structure is invalid.
        """
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            logger.error("PyYAML not installed. Install with: pip install 'pyyaml>=6.0'")
            raise ImportError("pyyaml is required for feature map parsing") from None

        if not yaml_path.is_file():
            raise FileNotFoundError(f"Feature map not found: {yaml_path}")

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in feature map: {e}") from e

        if not isinstance(data, dict) or "features" not in data:
            raise ValueError("Feature map must be a YAML dict with a top-level 'features' key")

        features_data = data["features"]
        if not isinstance(features_data, dict):
            raise ValueError("'features' must be a mapping of feature_name -> definition")

        self._features.clear()

        for name, definition in features_data.items():
            if definition is None:
                definition = {}
            if not isinstance(definition, dict):
                logger.warning("Skipping feature '%s': definition is not a mapping", name)
                continue

            feature = Feature(
                name=str(name),
                services=_as_str_list(definition.get("services")),
                owning_files=_as_str_list(definition.get("owning_files")),
                depends_on=_as_str_list(definition.get("depends_on")),
                produces=_as_str_list(definition.get("produces")),
                required_patterns=_as_str_list(definition.get("required_patterns")),
                related_contracts=_as_str_list(definition.get("related_contracts")),
                blast_radius=str(definition.get("blast_radius", "low")),
            )
            self._features[name] = feature

        self._loaded = True
        self._source_path = yaml_path
        logger.info(
            "Feature map loaded: %d features from %s",
            len(self._features),
            yaml_path,
        )

    def is_loaded(self) -> bool:
        """Check whether the feature map has been successfully loaded."""
        return self._loaded

    def get_feature(self, name: str) -> Feature | None:
        """Look up a feature by name.

        Args:
            name: The feature name (case-sensitive, matches YAML key).

        Returns:
            The Feature dataclass or None if not found.
        """
        return self._features.get(name)

    def get_all_features(self) -> list[Feature]:
        """Return all features in the map."""
        return list(self._features.values())

    def get_features_for_service(self, service: str) -> list[Feature]:
        """Find all features that include a given service.

        Args:
            service: Service name (e.g., "eln-core", "frontend").

        Returns:
            List of features that list this service.
        """
        return [f for f in self._features.values() if service in f.services]

    def get_features_for_file(self, file_path: str) -> list[Feature]:
        """Find all features whose owning_files globs match a file path.

        Args:
            file_path: Relative or absolute file path to match against
                owning_files glob patterns.

        Returns:
            List of features that own this file.
        """
        # Normalize to forward slashes for cross-platform glob matching
        normalized = file_path.replace("\\", "/")
        matches: list[Feature] = []

        for feature in self._features.values():
            for pattern in feature.owning_files:
                if fnmatch.fnmatch(normalized, pattern):
                    matches.append(feature)
                    break  # One match per feature is enough

        return matches

    def get_dependent_features(self, feature_name: str) -> list[Feature]:
        """Find features that directly depend on the given feature.

        Args:
            feature_name: The feature to find dependents of.

        Returns:
            List of features whose depends_on includes feature_name.
        """
        return [f for f in self._features.values() if feature_name in f.depends_on]

    def get_dependency_chain(self, feature_name: str) -> list[Feature]:
        """Get the full transitive dependency chain for a feature.

        Walks the depends_on graph breadth-first, collecting all features
        that the given feature transitively depends on. Handles cycles.

        Args:
            feature_name: Starting feature name.

        Returns:
            List of all transitive dependencies (not including the feature itself).
        """
        visited: set[str] = set()
        queue: list[str] = []
        result: list[Feature] = []

        # Seed with direct dependencies
        root = self._features.get(feature_name)
        if root is None:
            return []

        queue.extend(root.depends_on)

        while queue:
            current_name = queue.pop(0)
            if current_name in visited:
                continue
            visited.add(current_name)

            current = self._features.get(current_name)
            if current is None:
                logger.debug(
                    "Dependency '%s' referenced by '%s' not found in feature map",
                    current_name,
                    feature_name,
                )
                continue

            result.append(current)
            # Add transitive dependencies
            for dep in current.depends_on:
                if dep not in visited:
                    queue.append(dep)

        return result

    def get_affected_features(self, file_path: str) -> list[Feature]:
        """Given a changed file, find all directly owning features plus their dependents.

        This is the key method for change-impact analysis: it answers
        "if this file changed, which features could be affected?"

        Args:
            file_path: Path to the changed file.

        Returns:
            Deduplicated list of affected features (owners + their dependents).
        """
        owners = self.get_features_for_file(file_path)

        # Collect all affected features (owners + anything that depends on them)
        seen: set[str] = set()
        affected: list[Feature] = []

        for owner in owners:
            if owner.name not in seen:
                seen.add(owner.name)
                affected.append(owner)

            # Add features that depend on this owner
            for dep in self.get_dependent_features(owner.name):
                if dep.name not in seen:
                    seen.add(dep.name)
                    affected.append(dep)

        return affected

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entire feature map for inspection/debugging."""
        return {
            "loaded": self._loaded,
            "source": str(self._source_path) if self._source_path else None,
            "feature_count": len(self._features),
            "features": {name: f.to_dict() for name, f in self._features.items()},
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_feature_map: FeatureMap | None = None


def load_map(path: Path) -> FeatureMap:
    """Load (or reload) the module-level feature map singleton.

    Args:
        path: Path to FEATURE_MAP.yaml.

    Returns:
        The loaded FeatureMap instance.
    """
    global _feature_map
    fm = FeatureMap()
    fm.load(path)
    _feature_map = fm
    return fm


def get_map() -> FeatureMap | None:
    """Return the module-level feature map singleton, or None if not loaded."""
    return _feature_map


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _as_str_list(value: Any) -> list[str]:
    """Coerce a YAML value to a list of strings.

    Handles None, a single string, or a list of mixed types.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]
