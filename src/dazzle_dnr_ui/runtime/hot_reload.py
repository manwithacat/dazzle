"""
Hot reload support for DNR development server.

Watches DSL files for changes and triggers browser refresh via Server-Sent Events.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle_dnr_back.specs import BackendSpec
    from dazzle_dnr_ui.specs import UISpec


class FileWatcher:
    """
    Watches files for changes using polling (cross-platform compatible).

    Uses mtime-based change detection to avoid external dependencies.
    """

    def __init__(
        self,
        paths: list[Path],
        on_change: Callable[[Path], None],
        patterns: list[str] | None = None,
        poll_interval: float = 0.5,
    ):
        """
        Initialize the file watcher.

        Args:
            paths: Directories or files to watch
            on_change: Callback when a file changes
            patterns: Glob patterns to match (e.g., ["*.dsl", "dazzle.toml"])
            poll_interval: How often to check for changes (seconds)
        """
        self.paths = paths
        self.on_change = on_change
        self.patterns = patterns or ["*.dsl", "dazzle.toml"]
        self.poll_interval = poll_interval

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._file_mtimes: dict[Path, float] = {}

    def start(self) -> None:
        """Start watching for file changes."""
        # Initialize mtimes
        self._scan_files()

        # Start watcher thread
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop watching for file changes."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _scan_files(self) -> dict[Path, float]:
        """Scan all watched paths and return file mtimes."""
        mtimes: dict[Path, float] = {}

        for watch_path in self.paths:
            if not watch_path.exists():
                continue

            if watch_path.is_file():
                try:
                    mtimes[watch_path] = watch_path.stat().st_mtime
                except OSError:
                    pass
            else:
                # Directory - scan for matching files
                for pattern in self.patterns:
                    for file_path in watch_path.rglob(pattern):
                        try:
                            mtimes[file_path] = file_path.stat().st_mtime
                        except OSError:
                            pass

        return mtimes

    def _watch_loop(self) -> None:
        """Main watch loop that polls for file changes."""
        while not self._stop_event.is_set():
            try:
                current_mtimes = self._scan_files()

                # Check for changes
                changed_files: list[Path] = []

                # Check modified files
                for file_path, mtime in current_mtimes.items():
                    if file_path not in self._file_mtimes:
                        # New file
                        changed_files.append(file_path)
                    elif mtime > self._file_mtimes[file_path]:
                        # Modified file
                        changed_files.append(file_path)

                # Update mtimes
                self._file_mtimes = current_mtimes

                # Trigger callbacks for changed files
                for file_path in changed_files:
                    try:
                        self.on_change(file_path)
                    except Exception as e:
                        print(f"[DNR] Error in change callback: {e}")

            except Exception as e:
                print(f"[DNR] File watcher error: {e}")

            # Wait before next poll
            self._stop_event.wait(self.poll_interval)


class HotReloadManager:
    """
    Manages hot reload for DNR development server.

    Coordinates file watching, spec regeneration, and browser notification.
    """

    def __init__(
        self,
        project_root: Path,
        on_reload: Callable[[], tuple[BackendSpec, UISpec] | None] | None = None,
    ):
        """
        Initialize hot reload manager.

        Args:
            project_root: Root directory of the DAZZLE project
            on_reload: Callback to regenerate specs. Returns (BackendSpec, UISpec) or None on error.
        """
        self.project_root = project_root
        self.on_reload = on_reload

        # SSE clients waiting for reload signals
        self._sse_clients: list[threading.Event] = []
        self._sse_lock = threading.Lock()

        # Debounce settings
        self._last_change_time: float = 0
        self._debounce_delay: float = 0.3  # seconds
        self._pending_reload = threading.Event()

        # File watcher
        self._watcher: FileWatcher | None = None

        # Current specs (can be updated on reload)
        self._backend_spec: BackendSpec | None = None
        self._ui_spec: UISpec | None = None
        self._spec_lock = threading.Lock()

    def start(self) -> None:
        """Start watching for file changes."""
        watch_paths = [
            self.project_root / "dsl",
            self.project_root / "dazzle.toml",
        ]

        # Filter to existing paths
        existing_paths = [p for p in watch_paths if p.exists()]

        if not existing_paths:
            print("[DNR] Warning: No DSL files found to watch")
            return

        self._watcher = FileWatcher(
            paths=existing_paths,
            on_change=self._on_file_change,
            patterns=["*.dsl", "dazzle.toml"],
        )
        self._watcher.start()
        print(f"[DNR] Hot reload: watching {len(existing_paths)} path(s)")

    def stop(self) -> None:
        """Stop watching for file changes."""
        if self._watcher:
            self._watcher.stop()
            self._watcher = None

    def register_sse_client(self) -> threading.Event:
        """
        Register an SSE client for reload notifications.

        Returns:
            Event that will be set when a reload is triggered.
        """
        event = threading.Event()
        with self._sse_lock:
            self._sse_clients.append(event)
        return event

    def unregister_sse_client(self, event: threading.Event) -> None:
        """Unregister an SSE client."""
        with self._sse_lock:
            if event in self._sse_clients:
                self._sse_clients.remove(event)

    def get_specs(self) -> tuple[BackendSpec | None, UISpec | None]:
        """Get current specs (thread-safe)."""
        with self._spec_lock:
            return self._backend_spec, self._ui_spec

    def set_specs(self, backend_spec: BackendSpec, ui_spec: UISpec) -> None:
        """Set current specs (thread-safe)."""
        with self._spec_lock:
            self._backend_spec = backend_spec
            self._ui_spec = ui_spec

    def _on_file_change(self, file_path: Path) -> None:
        """Handle file change event with debouncing."""
        current_time = time.time()

        # Debounce rapid changes
        if current_time - self._last_change_time < self._debounce_delay:
            return

        self._last_change_time = current_time

        print(f"[DNR] File changed: {file_path.name}")

        # Regenerate specs if callback provided
        if self.on_reload:
            try:
                result = self.on_reload()
                if result:
                    backend_spec, ui_spec = result
                    self.set_specs(backend_spec, ui_spec)
                    print("[DNR] Specs regenerated successfully")
                else:
                    print("[DNR] Spec regeneration failed (validation error?)")
                    return
            except Exception as e:
                print(f"[DNR] Error regenerating specs: {e}")
                return

        # Notify all SSE clients
        self._notify_clients()

    def _notify_clients(self) -> None:
        """Notify all SSE clients to reload."""
        with self._sse_lock:
            client_count = len(self._sse_clients)
            for event in self._sse_clients:
                event.set()

        if client_count > 0:
            print(f"[DNR] Notified {client_count} browser(s) to reload")


def create_reload_callback(
    project_root: Path,
) -> Callable[[], tuple[BackendSpec, UISpec] | None]:
    """
    Create a reload callback that regenerates specs from DSL.

    Args:
        project_root: Root directory of the DAZZLE project

    Returns:
        Callback function that returns (BackendSpec, UISpec) or None on error
    """

    def reload_specs() -> tuple[BackendSpec, UISpec] | None:
        try:
            from dazzle.core.fileset import discover_dsl_files
            from dazzle.core.linker import build_appspec
            from dazzle.core.manifest import load_manifest
            from dazzle.core.parser import parse_modules
            from dazzle.validation.lint import lint_appspec
            from dazzle_dnr_back.converters import convert_appspec_to_backend
            from dazzle_dnr_ui.converters import convert_appspec_to_ui

            # Load manifest
            manifest = load_manifest(project_root / "dazzle.toml")

            # Parse DSL files
            dsl_files = discover_dsl_files(project_root, manifest)
            modules = parse_modules(dsl_files)

            # Link modules
            app_spec = build_appspec(modules, manifest.project_root)

            # Validate
            result = lint_appspec(app_spec)
            if result.errors:
                for error in result.errors:
                    print(f"[DNR] Validation error: {error.message}")
                return None

            # Generate specs
            backend_spec = convert_appspec_to_backend(app_spec)
            ui_spec = convert_appspec_to_ui(app_spec, shell_config=manifest.shell)

            return backend_spec, ui_spec

        except Exception as e:
            print(f"[DNR] Error parsing DSL: {e}")
            return None

    return reload_specs
