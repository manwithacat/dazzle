"""Python Audit detection agent (PA) — detects obsolete Python patterns.

Three detection layers:
1. Ruff profile scan (UP, PTH, ASYNC, C4, SIM rules)
2. Semgrep ruleset (deprecated stdlib, patterns ruff misses)
3. @heuristic methods (LLM training-bias patterns)
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dazzle.sentinel.agents.base import DetectionAgent, heuristic
from dazzle.sentinel.models import AgentId, Severity

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec
    from dazzle.sentinel.models import AgentResult, Finding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_RUFF_SEVERITY: dict[str, Severity] = {
    "UP": Severity.LOW,
    "PTH": Severity.INFO,
    "ASYNC": Severity.MEDIUM,
    "C": Severity.INFO,
    "SIM": Severity.INFO,
}


def _ruff_severity(code: str) -> Severity:
    """Map ruff rule code prefix to sentinel severity."""
    prefix = code.rstrip("0123456789")
    return _RUFF_SEVERITY.get(prefix, Severity.INFO)


def _should_include(min_version_str: str, target: tuple[int, int]) -> bool:
    """Return True if the finding's min Python version <= the project's target."""
    try:
        parts = min_version_str.split(".")
        min_ver = (int(parts[0]), int(parts[1]))
        return min_ver <= target
    except (IndexError, ValueError):
        return True


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class PythonAuditAgent(DetectionAgent):
    """Detects obsolete Python patterns in user project code."""

    def __init__(self, project_path: Path | None = None) -> None:
        self._project_path = project_path or Path.cwd()

    @property
    def agent_id(self) -> AgentId:
        return AgentId.PA

    # ------------------------------------------------------------------
    # Orchestrator entry point
    # ------------------------------------------------------------------

    def run(self, appspec: AppSpec) -> AgentResult:
        """Run all detection layers against user project code."""
        import time

        from dazzle.sentinel.models import AgentResult as AR

        t0 = time.monotonic()
        all_findings: list[Finding] = []
        errors: list[str] = []

        # Layer 1: Ruff
        try:
            all_findings.extend(self._run_ruff())
        except Exception as exc:
            errors.append(f"ruff: {exc}")

        # Layer 2: Semgrep
        try:
            all_findings.extend(self._run_semgrep())
        except Exception as exc:
            errors.append(f"semgrep: {exc}")

        # Layer 3: @heuristic methods
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
            heuristics_run=len(heuristics) + 2,  # +2 for ruff and semgrep layers
            duration_ms=round(elapsed, 2),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Layer 1: Ruff
    # ------------------------------------------------------------------

    def _run_ruff(self) -> list[Finding]:
        """Run ruff with curated rules and parse JSON output."""
        import subprocess

        scan_paths = [str(d) for d in self._get_scan_dirs() if d.exists()]
        if not scan_paths:
            return []

        major, minor = self._get_target_python_version()
        target = f"py{major}{minor}"

        try:
            result = subprocess.run(
                [
                    "ruff",
                    "check",
                    "--select",
                    "UP,PTH,ASYNC,C4,SIM",
                    "--output-format",
                    "json",
                    "--target-version",
                    target,
                    *scan_paths,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        if not result.stdout.strip():
            return []

        try:
            import json

            items = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        return self._parse_ruff_findings(items)

    def _parse_ruff_findings(self, items: list[dict[str, Any]]) -> list[Finding]:
        """Convert ruff JSON items to Finding objects."""
        from dazzle.sentinel.models import (
            Confidence,
            Evidence,
            Finding,
            Remediation,
            RemediationEffort,
        )

        findings = []
        for item in items:
            code = item.get("code", "")
            message = item.get("message", "")
            filename = item.get("filename", "")
            row = item.get("location", {}).get("row", 0)
            fix_msg = (item.get("fix") or {}).get("message", "")

            findings.append(
                Finding(
                    agent=AgentId.PA,
                    heuristic_id=f"PA-{code}",
                    category="python_audit",
                    subcategory="modernisation",
                    severity=_ruff_severity(code),
                    confidence=Confidence.CONFIRMED,
                    title=f"{code}: {message}",
                    description=message,
                    evidence=[
                        Evidence(
                            evidence_type="source_pattern",
                            location=f"{filename}:{row}",
                        )
                    ],
                    remediation=Remediation(
                        summary=fix_msg or message,
                        effort=RemediationEffort.TRIVIAL,
                    )
                    if fix_msg
                    else None,
                )
            )
        return findings

    # ------------------------------------------------------------------
    # Layer 2: Semgrep
    # ------------------------------------------------------------------

    def _run_semgrep(self) -> list[Finding]:
        """Run semgrep with shipped ruleset and parse JSON output."""
        import subprocess

        ruleset = Path(__file__).parent.parent / "rules" / "python_audit.yml"
        if not ruleset.exists():
            return []

        scan_paths = [str(d) for d in self._get_scan_dirs() if d.exists()]
        if not scan_paths:
            return []

        try:
            result = subprocess.run(
                [
                    "semgrep",
                    "--config",
                    str(ruleset),
                    "--json",
                    "--quiet",
                    *scan_paths,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        if not result.stdout.strip():
            return []

        try:
            import json

            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        return self._parse_semgrep_findings(data)

    def _parse_semgrep_findings(self, data: dict[str, Any]) -> list[Finding]:
        """Convert semgrep JSON output to Finding objects."""
        from dazzle.sentinel.models import (
            Confidence,
            Evidence,
            Finding,
            Remediation,
            RemediationEffort,
            Severity,
        )

        findings = []
        for item in data.get("results", []):
            check_id = item.get("check_id", "")
            path = item.get("path", "")
            line = item.get("start", {}).get("line", 0)
            extra = item.get("extra", {})
            message = extra.get("message", "")
            metadata = extra.get("metadata", {})
            snippet = extra.get("lines", "")
            severity_str = metadata.get("sentinel_severity", "MEDIUM").upper()
            severity = getattr(Severity, severity_str, Severity.MEDIUM)

            findings.append(
                Finding(
                    agent=AgentId.PA,
                    heuristic_id=check_id,
                    category="python_audit",
                    subcategory="deprecated_stdlib",
                    severity=severity,
                    confidence=Confidence.CONFIRMED,
                    title=f"{check_id}: {message}",
                    description=message,
                    evidence=[
                        Evidence(
                            evidence_type="source_pattern",
                            location=f"{path}:{line}",
                            snippet=snippet.strip() if snippet else None,
                        )
                    ],
                    remediation=Remediation(
                        summary=message,
                        effort=RemediationEffort.SMALL,
                    ),
                )
            )
        return findings

    # ------------------------------------------------------------------
    # Layer 3: @heuristic methods
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="PA-LLM-01",
        category="python_audit",
        subcategory="llm_bias",
        title="requests library in async codebase — prefer httpx",
    )
    def check_requests_in_async_codebase(self, appspec: AppSpec) -> list[Finding]:
        """Flag `import requests` when project has async code."""
        import ast

        from dazzle.sentinel.models import Confidence, Evidence, Finding, Severity

        files = self._get_python_files()
        has_async = False
        requests_files: list[tuple[Path, int]] = []

        for f in files:
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.AsyncFunctionDef):
                    has_async = True
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "requests":
                            requests_files.append((f, node.lineno))
                if isinstance(node, ast.ImportFrom) and node.module == "requests":
                    requests_files.append((f, node.lineno))

        if not has_async:
            return []

        return [
            Finding(
                agent=AgentId.PA,
                heuristic_id="PA-LLM-01",
                category="python_audit",
                subcategory="llm_bias",
                severity=Severity.LOW,
                confidence=Confidence.LIKELY,
                title="requests library used in async codebase",
                description="Project has async code but uses requests (sync-only). httpx provides the same API with native async support.",
                evidence=[
                    Evidence(
                        evidence_type="source_pattern",
                        location=f"{path}:{line}",
                    )
                ],
            )
            for path, line in requests_files
        ]

    @heuristic(
        heuristic_id="PA-LLM-03",
        category="python_audit",
        subcategory="llm_bias",
        title="Manual dunder methods — consider @dataclass",
    )
    def check_manual_dunders(self, appspec: AppSpec) -> list[Finding]:
        """Flag classes with manual __init__ + __repr__/__eq__ but no @dataclass."""
        import ast

        from dazzle.sentinel.models import (
            Confidence,
            Evidence,
            Finding,
            Remediation,
            RemediationEffort,
            Severity,
        )

        findings: list[Finding] = []
        dunder_set = {"__init__", "__repr__", "__eq__"}

        for f in self._get_python_files():
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                has_dataclass = any(
                    (isinstance(d, ast.Name) and d.id == "dataclass")
                    or (
                        isinstance(d, ast.Call)
                        and isinstance(d.func, ast.Name)
                        and d.func.id == "dataclass"
                    )
                    or (isinstance(d, ast.Attribute) and d.attr == "dataclass")
                    for d in node.decorator_list
                )
                if has_dataclass:
                    continue
                methods = {
                    n.name
                    for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                has_init = "__init__" in methods
                has_other = bool(methods & (dunder_set - {"__init__"}))
                if has_init and has_other:
                    findings.append(
                        Finding(
                            agent=AgentId.PA,
                            heuristic_id="PA-LLM-03",
                            category="python_audit",
                            subcategory="llm_bias",
                            severity=Severity.LOW,
                            confidence=Confidence.POSSIBLE,
                            title=f"Class '{node.name}' has manual dunders — consider @dataclass",
                            description=f"Class '{node.name}' defines __init__ plus __repr__/__eq__ manually. @dataclass generates these automatically.",
                            evidence=[
                                Evidence(
                                    evidence_type="source_pattern",
                                    location=f"{f}:{node.lineno}",
                                )
                            ],
                            remediation=Remediation(
                                summary="Replace with @dataclass and type-annotated fields",
                                effort=RemediationEffort.SMALL,
                            ),
                        )
                    )
        return findings

    @heuristic(
        heuristic_id="PA-LLM-04",
        category="python_audit",
        subcategory="llm_bias",
        title="unittest.TestCase in a pytest project",
    )
    def check_unittest_in_pytest_project(self, appspec: AppSpec) -> list[Finding]:
        """Flag unittest usage when conftest.py exists (indicating pytest)."""
        import ast

        from dazzle.sentinel.models import (
            Confidence,
            Evidence,
            Finding,
            Remediation,
            RemediationEffort,
            Severity,
        )

        if not (self._project_path / "conftest.py").exists():
            return []

        findings: list[Finding] = []
        for f in self._get_python_files():
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "unittest":
                            findings.append(
                                Finding(
                                    agent=AgentId.PA,
                                    heuristic_id="PA-LLM-04",
                                    category="python_audit",
                                    subcategory="llm_bias",
                                    severity=Severity.INFO,
                                    confidence=Confidence.LIKELY,
                                    title="unittest used in pytest project",
                                    description="This project uses pytest (conftest.py present) but this file imports unittest. Use pytest functions + fixtures instead.",
                                    evidence=[
                                        Evidence(
                                            evidence_type="source_pattern",
                                            location=f"{f}:{node.lineno}",
                                        )
                                    ],
                                    remediation=Remediation(
                                        summary="Rewrite as pytest functions with assert statements",
                                        effort=RemediationEffort.MEDIUM,
                                    ),
                                )
                            )
        return findings

    @heuristic(
        heuristic_id="PA-LLM-05",
        category="python_audit",
        subcategory="llm_bias",
        title="setup.py alongside pyproject.toml",
    )
    def check_setup_py_with_pyproject(self, appspec: AppSpec) -> list[Finding]:
        """Flag setup.py/setup.cfg when pyproject.toml exists."""
        from dazzle.sentinel.models import (
            Confidence,
            Evidence,
            Finding,
            Remediation,
            RemediationEffort,
            Severity,
        )

        root = self._project_path
        if not (root / "pyproject.toml").exists():
            return []

        findings: list[Finding] = []
        for name in ["setup.py", "setup.cfg"]:
            path = root / name
            if path.exists():
                findings.append(
                    Finding(
                        agent=AgentId.PA,
                        heuristic_id="PA-LLM-05",
                        category="python_audit",
                        subcategory="llm_bias",
                        severity=Severity.LOW,
                        confidence=Confidence.LIKELY,
                        title=f"{name} exists alongside pyproject.toml",
                        description=f"Project has pyproject.toml (PEP 621) but also {name}. Consolidate into pyproject.toml.",
                        evidence=[
                            Evidence(
                                evidence_type="source_pattern",
                                location=str(path),
                            )
                        ],
                        remediation=Remediation(
                            summary=f"Migrate {name} contents into pyproject.toml and delete {name}",
                            effort=RemediationEffort.MEDIUM,
                        ),
                    )
                )
        return findings

    @heuristic(
        heuristic_id="PA-LLM-06",
        category="python_audit",
        subcategory="llm_bias",
        title="pip/virtualenv references when uv is available",
    )
    def check_pip_when_uv_available(self, appspec: AppSpec) -> list[Finding]:
        """Flag pip install / virtualenv references when uv.lock exists."""
        import re

        from dazzle.sentinel.models import (
            Confidence,
            Evidence,
            Finding,
            Remediation,
            RemediationEffort,
            Severity,
        )

        root = self._project_path
        if not (root / "uv.lock").exists():
            return []

        pip_pattern = re.compile(r"pip install|virtualenv|python -m venv")
        findings: list[Finding] = []

        for name in ["README.md", "CONTRIBUTING.md", "Makefile", "justfile"]:
            path = root / name
            if not path.exists():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if pip_pattern.search(line):
                    findings.append(
                        Finding(
                            agent=AgentId.PA,
                            heuristic_id="PA-LLM-06",
                            category="python_audit",
                            subcategory="llm_bias",
                            severity=Severity.INFO,
                            confidence=Confidence.POSSIBLE,
                            title="pip/virtualenv reference in uv project",
                            description=f"Project uses uv (uv.lock present) but {name} references pip/virtualenv. Update docs to use uv commands.",
                            evidence=[
                                Evidence(
                                    evidence_type="source_pattern",
                                    location=f"{path}:{i}",
                                    snippet=line.strip(),
                                )
                            ],
                            remediation=Remediation(
                                summary="Replace pip install with uv pip install, virtualenv with uv venv",
                                effort=RemediationEffort.TRIVIAL,
                            ),
                        )
                    )
                    break  # One finding per file is enough
        return findings

    # ------------------------------------------------------------------
    # Scanning helpers
    # ------------------------------------------------------------------

    def _get_scan_dirs(self) -> list[Path]:
        """Return directories to scan."""
        root = self._project_path
        dirs = []
        for name in ["app", "scripts"]:
            candidate = root / name
            if candidate.is_dir():
                dirs.append(candidate)
        if not dirs:
            dirs.append(root)
        return dirs

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
        # Malformed pyproject / missing tomllib falls back to the conservative default (#smells-1.1).
        with suppress(Exception):
            import re
            import tomllib

            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            requires = data.get("project", {}).get("requires-python", "")
            match = re.search(r"(\d+)\.(\d+)", requires)
            if match:
                return (int(match.group(1)), int(match.group(2)))
        return (3, 10)
