"""Python Audit detection agent (PA) — detects obsolete Python patterns.

Three detection layers:
1. Ruff profile scan (UP, PTH, ASYNC, C4, SIM rules)
2. Semgrep ruleset (deprecated stdlib, patterns ruff misses)
3. @heuristic methods (LLM training-bias patterns)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from dazzle.sentinel.agents.base import DetectionAgent
from dazzle.sentinel.models import AgentId

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec
    from dazzle.sentinel.models import AgentResult


class PythonAuditAgent(DetectionAgent):
    """Detects obsolete Python patterns in user project code."""

    def __init__(self, project_path: Path | None = None) -> None:
        self._project_path = project_path or Path.cwd()

    @property
    def agent_id(self) -> AgentId:
        return AgentId.PA

    def run(self, appspec: AppSpec) -> AgentResult:
        """Override base run to scan .py files on disk instead of AppSpec IR."""
        import time

        from dazzle.sentinel.models import AgentResult as AR

        t0 = time.monotonic()
        all_findings = []
        errors = []

        # Run @heuristic methods (they receive appspec for interface compat,
        # but internally use self._project_path)
        heuristics = self.get_heuristics()
        for meta, method in heuristics:
            try:
                findings = method(appspec)
                all_findings.extend(findings)
            except Exception as exc:
                errors.append(f"{meta.heuristic_id}: {exc}")

        elapsed = (time.monotonic() - t0) * 1000
        return AR(
            agent=self.agent_id,
            findings=all_findings,
            heuristics_run=len(heuristics),
            duration_ms=round(elapsed, 2),
            errors=errors,
        )

    def _get_python_files(self) -> list[Path]:
        """Collect .py files in the user's project (not framework code)."""
        root = self._project_path
        scan_dirs = []
        for d in ["app", "scripts"]:
            candidate = root / d
            if candidate.is_dir():
                scan_dirs.append(candidate)
        # Also include root-level .py files
        scan_dirs.append(root)

        files: list[Path] = []
        skip_dirs = {"__pycache__", ".venv", "node_modules", ".dazzle", ".git"}
        for scan_dir in scan_dirs:
            if scan_dir == root:
                # Only root-level .py files, not recursive
                files.extend(f for f in scan_dir.glob("*.py") if f.is_file())
            else:
                for f in scan_dir.rglob("*.py"):
                    if any(part in skip_dirs for part in f.parts):
                        continue
                    if f.is_file():
                        files.append(f)
        return files

    def _get_target_python_version(self) -> tuple[int, int]:
        """Read requires-python from pyproject.toml, return (major, minor)."""
        pyproject = self._project_path / "pyproject.toml"
        if not pyproject.exists():
            return (3, 10)  # conservative default
        try:
            import re
            import tomllib

            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            requires = data.get("project", {}).get("requires-python", "")
            match = re.search(r"(\d+)\.(\d+)", requires)
            if match:
                return (int(match.group(1)), int(match.group(2)))
        except Exception:
            pass
        return (3, 10)
