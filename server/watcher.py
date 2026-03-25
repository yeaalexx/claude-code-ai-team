"""
File System Watcher — v5.0

Monitors project directories for file changes and triggers validation
workflows. Configurable via watcher-config.json in the project root.

Config format:
{
  "enabled": true,
  "project_root": "/path/to/project",
  "watch_paths": ["services/", "frontend/src/", "contracts/"],
  "ignore_patterns": ["**/node_modules/**", "**/__pycache__/**", "**/dist/**", "**/.git/**"],
  "contracts_path": "contracts/",
  "integration_contracts": "INTEGRATION_CONTRACTS.md",
  "debounce_seconds": 2.0,
  "on_change": "validate"
}

Uses the `watchdog` library for cross-platform filesystem monitoring.
Thread-safe, debounced, and works on Windows 10+.
"""

import fnmatch
import json
import logging
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

logger = logging.getLogger(__name__)

# Default configuration values
_DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "project_root": ".",
    "watch_paths": ["services/", "frontend/src/"],
    "ignore_patterns": [
        "**/node_modules/**",
        "**/__pycache__/**",
        "**/dist/**",
        "**/.git/**",
        "**/build/**",
        "**/target/**",
        "**/*.pyc",
        "**/.venv/**",
        "**/coverage/**",
    ],
    "contracts_path": "contracts/",
    "integration_contracts": "INTEGRATION_CONTRACTS.md",
    "debounce_seconds": 2.0,
    "on_change": "validate",
}


@dataclass
class FileChangeEvent:
    """Represents a single file change detected by the watcher."""

    path: str
    event_type: str  # "modified" | "created" | "deleted"
    timestamp: str
    service: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "service": self.service,
        }


@dataclass
class WatcherConfig:
    """Parsed and validated watcher configuration."""

    enabled: bool = False
    project_root: Path = field(default_factory=lambda: Path("."))
    watch_paths: list[str] = field(default_factory=lambda: ["services/", "frontend/src/"])
    ignore_patterns: list[str] = field(
        default_factory=lambda: [
            "**/node_modules/**",
            "**/__pycache__/**",
            "**/dist/**",
            "**/.git/**",
        ]
    )
    contracts_path: str = "contracts/"
    integration_contracts: str = "INTEGRATION_CONTRACTS.md"
    debounce_seconds: float = 2.0
    on_change: str = "validate"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WatcherConfig":
        """Create a WatcherConfig from a dictionary, applying defaults for missing keys."""
        merged = {**_DEFAULT_CONFIG, **data}
        return cls(
            enabled=bool(merged["enabled"]),
            project_root=Path(merged["project_root"]).resolve(),
            watch_paths=list(merged["watch_paths"]),
            ignore_patterns=list(merged["ignore_patterns"]),
            contracts_path=str(merged["contracts_path"]),
            integration_contracts=str(merged["integration_contracts"]),
            debounce_seconds=float(merged["debounce_seconds"]),
            on_change=str(merged["on_change"]),
        )

    @classmethod
    def from_file(cls, config_path: Path) -> "WatcherConfig":
        """Load configuration from a JSON file."""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # If project_root is relative ".", resolve relative to the config file's directory
            if data.get("project_root", ".") == ".":
                data["project_root"] = str(config_path.parent.resolve())
            return cls.from_dict(data)
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load watcher config from %s: %s", config_path, e)
            return cls()


def detect_service(path: str, project_root: Path) -> str | None:
    """Detect which service a file belongs to based on its path.

    Rules:
    - If path is under services/X/, the service is "X"
    - If path is under frontend/, the service is "frontend"
    - Otherwise None

    Args:
        path: Absolute or relative file path.
        project_root: The project root directory.

    Returns:
        Service name string or None.
    """
    try:
        rel = PurePosixPath(Path(path).resolve().relative_to(project_root).as_posix())
    except (ValueError, OSError):
        return None

    parts = rel.parts
    if len(parts) >= 2 and parts[0] == "services":
        return parts[1]
    if len(parts) >= 1 and parts[0] == "frontend":
        return "frontend"
    return None


def _matches_any_pattern(path: str, patterns: list[str]) -> bool:
    """Check if a path matches any of the glob ignore patterns.

    Uses forward-slash normalized paths for cross-platform consistency.
    """
    # Normalize to forward slashes for pattern matching
    normalized = path.replace("\\", "/")
    for pattern in patterns:
        if fnmatch.fnmatch(normalized, pattern):
            return True
        # Also check just the filename against basename-style patterns
        if "/" not in pattern and fnmatch.fnmatch(Path(path).name, pattern):
            return True
    return True if False else False  # noqa: SIM210 — explicit for clarity; always False


class _DebouncedHandler:
    """Collects filesystem events and debounces them before dispatching.

    This avoids triggering validation on every keystroke when an IDE does
    rapid save/format/save cycles. Events within the debounce window are
    collapsed into a single event per file.

    Thread-safe: the watchdog observer calls on_event from its own thread,
    while the debounce timer fires from yet another thread.
    """

    def __init__(
        self,
        config: WatcherConfig,
        callback: Callable[[FileChangeEvent], None],
    ) -> None:
        self.config = config
        self.callback = callback
        self._lock = threading.Lock()
        # Pending events keyed by absolute path — only the latest event per file is kept
        self._pending: dict[str, FileChangeEvent] = {}
        self._timer: threading.Timer | None = None

    def on_event(self, event_path: str, event_type: str) -> None:
        """Called by the watchdog handler when a file event occurs."""
        abs_path = str(Path(event_path).resolve())

        # Check ignore patterns
        try:
            rel_path = str(Path(abs_path).relative_to(self.config.project_root))
        except ValueError:
            rel_path = abs_path

        if _matches_any_pattern(rel_path, self.config.ignore_patterns):
            return

        service = detect_service(abs_path, self.config.project_root)
        change = FileChangeEvent(
            path=abs_path,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            service=service,
        )

        with self._lock:
            self._pending[abs_path] = change
            # Reset debounce timer
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.config.debounce_seconds, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        """Dispatch all pending events after the debounce window closes."""
        with self._lock:
            events = list(self._pending.values())
            self._pending.clear()
            self._timer = None

        for event in events:
            try:
                self.callback(event)
            except Exception:
                logger.exception("Error in watcher callback for %s", event.path)

    def cancel(self) -> None:
        """Cancel any pending debounce timer."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending.clear()


class FileWatcher:
    """Monitors project directories for file changes.

    Uses the `watchdog` library underneath. Runs the observer in a background
    daemon thread so it does not block the MCP server.

    Usage:
        watcher = FileWatcher()
        watcher.start(config_path, callback=my_handler)
        ...
        watcher.stop()
    """

    def __init__(self) -> None:
        self._observer: Any = None  # watchdog.observers.Observer
        self._handler: _DebouncedHandler | None = None
        self._config: WatcherConfig | None = None
        self._running = False
        self._lock = threading.Lock()
        # Circular buffer of recent events for inspection
        self._recent_events: deque[FileChangeEvent] = deque(maxlen=200)

    def start(
        self,
        config_path: Path | str,
        callback: Callable[[FileChangeEvent], None] | None = None,
    ) -> bool:
        """Start watching the project directories.

        Args:
            config_path: Path to watcher-config.json.
            callback: Function called for each debounced file change event.
                If None, events are only recorded in the recent events buffer.

        Returns:
            True if started successfully, False otherwise.
        """
        with self._lock:
            if self._running:
                logger.warning("Watcher is already running — stop it first")
                return False

        config = WatcherConfig.from_file(Path(config_path))
        if not config.enabled:
            logger.info("Watcher is disabled in config")
            return False

        try:
            from watchdog.events import FileSystemEvent, FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            logger.error("watchdog library not installed. Install with: pip install watchdog>=4.0.0")
            return False

        # Wrap the user callback to also record events
        def _recording_callback(event: FileChangeEvent) -> None:
            self._recent_events.append(event)
            if callback is not None:
                callback(event)

        handler = _DebouncedHandler(config, _recording_callback)

        # Create a watchdog event handler that forwards to our debouncer
        class _WatchdogBridge(FileSystemEventHandler):
            def on_modified(self, event: FileSystemEvent) -> None:
                if not event.is_directory:
                    handler.on_event(str(event.src_path), "modified")

            def on_created(self, event: FileSystemEvent) -> None:
                if not event.is_directory:
                    handler.on_event(str(event.src_path), "created")

            def on_deleted(self, event: FileSystemEvent) -> None:
                if not event.is_directory:
                    handler.on_event(str(event.src_path), "deleted")

        bridge = _WatchdogBridge()
        observer = Observer()

        # Schedule watches for each configured path
        watched_count = 0
        for watch_path in config.watch_paths:
            full_path = config.project_root / watch_path
            if full_path.is_dir():
                observer.schedule(bridge, str(full_path), recursive=True)
                watched_count += 1
                logger.info("Watching: %s", full_path)
            else:
                logger.warning("Watch path does not exist, skipping: %s", full_path)

        if watched_count == 0:
            logger.error("No valid watch paths found — watcher not started")
            return False

        observer.daemon = True
        observer.start()

        with self._lock:
            self._observer = observer
            self._handler = handler
            self._config = config
            self._running = True

        logger.info(
            "File watcher started — monitoring %d paths under %s",
            watched_count,
            config.project_root,
        )
        return True

    def stop(self) -> None:
        """Stop the file watcher and clean up resources."""
        with self._lock:
            if not self._running:
                return

            if self._handler is not None:
                self._handler.cancel()
                self._handler = None

            if self._observer is not None:
                self._observer.stop()
                # Join with a timeout to avoid blocking forever
                self._observer.join(timeout=5.0)
                self._observer = None

            self._config = None
            self._running = False

        logger.info("File watcher stopped")

    def is_running(self) -> bool:
        """Check whether the watcher is currently active."""
        with self._lock:
            return self._running

    def get_recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recent file change events.

        Args:
            limit: Maximum number of events to return (most recent first).

        Returns:
            List of event dictionaries.
        """
        # deque is thread-safe for iteration on CPython
        events = list(self._recent_events)
        # Most recent first
        events.reverse()
        return [e.to_dict() for e in events[:limit]]

    def get_config(self) -> dict[str, Any] | None:
        """Return the current configuration as a dict, or None if not started."""
        with self._lock:
            if self._config is None:
                return None
            return {
                "enabled": self._config.enabled,
                "project_root": str(self._config.project_root),
                "watch_paths": self._config.watch_paths,
                "ignore_patterns": self._config.ignore_patterns,
                "contracts_path": self._config.contracts_path,
                "integration_contracts": self._config.integration_contracts,
                "debounce_seconds": self._config.debounce_seconds,
                "on_change": self._config.on_change,
            }


# Module-level singleton for convenience
_instance: FileWatcher | None = None


def get_watcher() -> FileWatcher:
    """Get or create the module-level FileWatcher singleton."""
    global _instance
    if _instance is None:
        _instance = FileWatcher()
    return _instance


def start(
    config_path: Path | str,
    callback: Callable[[FileChangeEvent], None] | None = None,
) -> bool:
    """Start the module-level watcher. Convenience wrapper."""
    return get_watcher().start(config_path, callback)


def stop() -> None:
    """Stop the module-level watcher. Convenience wrapper."""
    get_watcher().stop()


def is_running() -> bool:
    """Check if the module-level watcher is running. Convenience wrapper."""
    return get_watcher().is_running()


def get_recent_events(limit: int = 20) -> list[dict[str, Any]]:
    """Get recent events from the module-level watcher. Convenience wrapper."""
    return get_watcher().get_recent_events(limit)
