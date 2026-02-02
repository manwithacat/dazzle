"""
Hot reload support for DNR development server.

Watches DSL files and source files for changes and triggers browser refresh via SSE.

Two watch modes:
1. DSL files (*.dsl, dazzle.toml) - regenerates specs on change
2. Source files (*.py, *.css, *.js) - clears caches and triggers reload
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle_back.specs import BackendSpec
    from dazzle_ui.specs import UISpec


# Source file patterns to watch
SOURCE_PATTERNS = ["*.py", "*.css", "*.js"]


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
                        print(f"[Dazzle] Error in change callback: {e}")

            except Exception as e:
                print(f"[Dazzle] File watcher error: {e}")

            # Wait before next poll
            self._stop_event.wait(self.poll_interval)


class HotReloadManager:
    """
    Manages hot reload for DNR development server.

    Coordinates file watching, spec regeneration, and browser notification.
    Supports two watch modes:
    - DSL files: regenerate specs on change
    - Source files: clear caches and reload (for framework development)
    """

    def __init__(
        self,
        project_root: Path,
        on_reload: Callable[[], tuple[BackendSpec, UISpec] | None] | None = None,
        watch_source: bool = False,
    ):
        """
        Initialize hot reload manager.

        Args:
            project_root: Root directory of the DAZZLE project
            on_reload: Callback to regenerate specs. Returns (BackendSpec, UISpec) or None on error.
            watch_source: If True, also watch framework source files (Python, CSS, JS)
        """
        self.project_root = project_root
        self.on_reload = on_reload
        self.watch_source = watch_source

        # SSE clients waiting for reload signals
        self._sse_clients: list[threading.Event] = []
        self._sse_lock = threading.Lock()

        # Debounce settings
        self._last_change_time: float = 0
        self._debounce_delay: float = 0.3  # seconds
        self._pending_reload = threading.Event()

        # File watchers (DSL and source)
        self._watcher: FileWatcher | None = None
        self._source_watcher: FileWatcher | None = None

        # Current specs (can be updated on reload)
        self._backend_spec: BackendSpec | None = None
        self._ui_spec: UISpec | None = None
        self._spec_lock = threading.Lock()

    def start(self) -> None:
        """Start watching for file changes."""
        # DSL file watcher
        watch_paths = [
            self.project_root / "dsl",
            self.project_root / "dazzle.toml",
        ]

        # Filter to existing paths
        existing_paths = [p for p in watch_paths if p.exists()]

        if not existing_paths:
            print("[Dazzle] Warning: No DSL files found to watch")
        else:
            self._watcher = FileWatcher(
                paths=existing_paths,
                on_change=self._on_file_change,
                patterns=["*.dsl", "dazzle.toml"],
            )
            self._watcher.start()
            print(f"[Dazzle] Hot reload: watching {len(existing_paths)} path(s)")

        # Source file watcher (for framework development)
        if self.watch_source:
            self._start_source_watcher()

    def _start_source_watcher(self) -> None:
        """Start watching framework source files."""
        # Find the dazzle_ui package directory
        source_paths: list[Path] = []

        # Try to find installed package location
        try:
            import dazzle_ui

            pkg_path = Path(dazzle_ui.__file__).parent
            runtime_path = pkg_path / "runtime"
            if runtime_path.exists():
                source_paths.append(runtime_path)
        except ImportError:
            pass

        # Also check common development locations
        dev_locations = [
            Path(__file__).parent,  # Current runtime directory
            self.project_root.parent / "src" / "dazzle_ui" / "runtime",
            Path.cwd() / "src" / "dazzle_ui" / "runtime",
        ]

        for loc in dev_locations:
            if loc.exists() and loc not in source_paths:
                source_paths.append(loc)

        if not source_paths:
            print("[Dazzle] Warning: No source paths found to watch")
            return

        # Deduplicate by resolving paths
        unique_paths: list[Path] = []
        seen_resolved: set[Path] = set()
        for p in source_paths:
            resolved = p.resolve()
            if resolved not in seen_resolved:
                seen_resolved.add(resolved)
                unique_paths.append(p)

        self._source_watcher = FileWatcher(
            paths=unique_paths,
            on_change=self._on_source_change,
            patterns=SOURCE_PATTERNS,
            poll_interval=0.3,  # Faster polling for source changes
        )
        self._source_watcher.start()
        print(f"[Dazzle] Source reload: watching {len(unique_paths)} path(s)")

    def stop(self) -> None:
        """Stop watching for file changes."""
        if self._watcher:
            self._watcher.stop()
            self._watcher = None
        if self._source_watcher:
            self._source_watcher.stop()
            self._source_watcher = None

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
        """Handle DSL file change event with debouncing."""
        current_time = time.time()

        # Debounce rapid changes
        if current_time - self._last_change_time < self._debounce_delay:
            return

        self._last_change_time = current_time

        print(f"[Dazzle] File changed: {file_path.name}")

        # Regenerate specs if callback provided
        if self.on_reload:
            try:
                result = self.on_reload()
                if result:
                    backend_spec, ui_spec = result
                    self.set_specs(backend_spec, ui_spec)
                    print("[Dazzle] Specs regenerated successfully")
                else:
                    print("[Dazzle] Spec regeneration failed (validation error?)")
                    return
            except Exception as e:
                print(f"[Dazzle] Error regenerating specs: {e}")
                return

        # Notify all SSE clients
        self._notify_clients()

    def _on_source_change(self, file_path: Path) -> None:
        """Handle source file change event (Python, CSS, JS)."""
        current_time = time.time()

        # Debounce rapid changes
        if current_time - self._last_change_time < self._debounce_delay:
            return

        self._last_change_time = current_time

        suffix = file_path.suffix.lower()
        print(f"[Dazzle] Source changed: {file_path.name}")

        # Clear appropriate caches based on file type
        try:
            if suffix == ".py":
                # Reload Python modules and clear caches
                self._reload_python_modules(file_path)
                self._clear_runtime_cache()
                print("[Dazzle] Python modules reloaded")
            elif suffix == ".css":
                # Clear CSS cache (CSS is read fresh from disk)
                self._clear_css_cache()
                print("[Dazzle] CSS cache cleared")
            elif suffix == ".js":
                # Clear JS runtime cache
                self._clear_runtime_cache()
                print("[Dazzle] JS cache cleared")
        except Exception as e:
            print(f"[Dazzle] Error during reload: {e}")

        # Notify browsers to reload
        self._notify_clients()

    def _reload_python_modules(self, changed_file: Path) -> None:
        """
        Reload Python modules affected by a file change.

        Uses importlib.reload() to refresh module code without restarting.
        """
        import importlib
        import sys

        # Map of filename patterns to modules that should be reloaded
        # Order matters - reload dependencies first
        modules_to_reload = [
            "dazzle_ui.runtime.site_renderer",
            "dazzle_ui.runtime.vite_generator",
            "dazzle_ui.runtime.template_renderer",
            "dazzle_ui.converters.template_compiler",
        ]

        reloaded = []
        for module_name in modules_to_reload:
            if module_name in sys.modules:
                try:
                    module = sys.modules[module_name]
                    importlib.reload(module)
                    reloaded.append(module_name.split(".")[-1])
                except Exception as e:
                    print(f"[Dazzle] Failed to reload {module_name}: {e}")

        if reloaded:
            print(f"[Dazzle] Reloaded: {', '.join(reloaded)}")

    def _clear_runtime_cache(self) -> None:
        """Clear the template renderer cache."""
        try:
            from dazzle_ui.runtime.template_renderer import get_jinja_env

            # Force Jinja2 to reload templates from disk
            env = get_jinja_env()
            if hasattr(env, "cache"):
                env.cache.clear()  # type: ignore[union-attr]
        except ImportError:
            pass

    def _clear_css_cache(self) -> None:
        """Clear the CSS cache."""
        try:
            from dazzle_ui.runtime.vite_generator import clear_css_cache

            clear_css_cache()
        except (ImportError, AttributeError):
            pass

    def _notify_clients(self) -> None:
        """Notify all SSE clients to reload."""
        with self._sse_lock:
            client_count = len(self._sse_clients)
            for event in self._sse_clients:
                event.set()

        if client_count > 0:
            print(f"[Dazzle] Notified {client_count} browser(s) to reload")


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
            from dazzle.core.lint import lint_appspec
            from dazzle.core.manifest import load_manifest
            from dazzle.core.parser import parse_modules
            from dazzle_back.converters import convert_appspec_to_backend
            from dazzle_ui.converters import convert_appspec_to_ui

            # Load manifest
            manifest = load_manifest(project_root / "dazzle.toml")

            # Parse DSL files
            dsl_files = discover_dsl_files(project_root, manifest)
            modules = parse_modules(dsl_files)

            # Link modules
            app_spec = build_appspec(modules, manifest.project_root)

            # Validate - lint_appspec returns (errors, warnings) tuple
            errors, warnings = lint_appspec(app_spec)
            if errors:
                for error in errors:
                    print(f"[Dazzle] Validation error: {error}")
                return None

            # Generate specs
            backend_spec = convert_appspec_to_backend(app_spec)
            ui_spec = convert_appspec_to_ui(app_spec, shell_config=manifest.shell)

            return backend_spec, ui_spec

        except Exception as e:
            print(f"[Dazzle] Error parsing DSL: {e}")
            return None

    return reload_specs
