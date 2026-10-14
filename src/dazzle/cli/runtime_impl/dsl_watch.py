"""``dazzle serve --watch``: re-validate the DSL whenever it changes.

A polling watcher (mtime-based, no extra dependency) over ``dsl/`` and
``dazzle.toml``. On a change it re-parses, links and lints the project and
prints the outcome to the server console. The running app keeps serving the
spec it booted with — restart ``dazzle serve`` to apply a valid change.

This replaced the hot-reload manager in flense ship AB (ADR-0057): its SSE
browser refresh had no listener, the regenerated specs were stored but never
read, and the ``--watch-source`` module reload re-imported modules whose
functions every caller had already bound by name.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules
from dazzle.core.renderer_registry import known_renderer_names

_DSL_PATTERNS = ("*.dsl", "dazzle.toml")


def validate_project(project_root: Path) -> list[str]:
    """Parse, link and lint *project_root*; return the errors (empty = valid)."""
    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        modules = parse_modules(discover_dsl_files(project_root, manifest))
        # known_renderers= mirrors the boot path, so `render: <unknown>` and
        # `[renderers] extra` resolve the same way (#1116).
        appspec = build_appspec(
            modules, manifest.project_root, known_renderers=known_renderer_names(manifest)
        )
        errors, _warnings, _relevance = lint_appspec(appspec)
    except Exception as exc:  # parse/link errors carry the file:line in the message
        return [str(exc)]
    return [str(e) for e in errors]


class DslWatcher:
    """Polls the project's DSL files and re-validates on change."""

    def __init__(
        self,
        project_root: Path,
        *,
        validate: Callable[[Path], list[str]] = validate_project,
        poll_interval: float = 0.5,
    ) -> None:
        self.project_root = project_root
        self._validate = validate
        self._poll_interval = poll_interval
        self._paths = [
            p for p in (project_root / "dsl", project_root / "dazzle.toml") if p.exists()
        ]
        self._mtimes: dict[Path, float] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _scan(self) -> dict[Path, float]:
        mtimes: dict[Path, float] = {}
        for path in self._paths:
            candidates = (
                [path] if path.is_file() else [f for pat in _DSL_PATTERNS for f in path.rglob(pat)]
            )
            for f in candidates:
                try:
                    mtimes[f] = f.stat().st_mtime
                except OSError:
                    continue
        return mtimes

    def check(self) -> list[str] | None:
        """One poll: re-validate when a file was added, changed or removed.

        Returns the validation errors when it re-validated, else ``None``.
        """
        current = self._scan()
        changed = current != self._mtimes
        self._mtimes = current
        if not changed:
            return None
        errors = self._validate(self.project_root)
        head = f"[Dazzle] {time.strftime('%H:%M:%S')} DSL changed —"
        if errors:
            print(f"{head} {len(errors)} validation error(s):", flush=True)
            for error in errors:
                print(f"[Dazzle]   {error}", flush=True)
        else:
            print(f"{head} valid. Restart `dazzle serve` to apply it.", flush=True)
        return errors

    def start(self) -> bool:
        """Start polling in a daemon thread; ``False`` when there is nothing to watch."""
        if not self._paths:
            return False
        self._mtimes = self._scan()
        self._thread = threading.Thread(target=self._loop, name="dazzle-dsl-watch", daemon=True)
        self._thread.start()
        return True

    def _loop(self) -> None:
        while not self._stop.wait(self._poll_interval):
            self.check()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
