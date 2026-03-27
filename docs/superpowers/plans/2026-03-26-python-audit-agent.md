# Python Audit Sentinel Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `PythonAuditAgent` (PA) to sentinel that detects obsolete Python patterns via three layers: ruff rules, semgrep rules, and custom AST-based heuristics for LLM training-bias patterns.

**Architecture:** New sentinel agent class extending `DetectionAgent`. Override `run()` to scan `.py` files on disk (not AppSpec IR). Three detection layers: (1) subprocess call to `ruff check` with curated rule selection, parsing JSON output into `Finding` objects; (2) subprocess call to `semgrep` with a shipped YAML ruleset; (3) `@heuristic`-decorated methods using `ast.parse()` for LLM-bias patterns. The orchestrator needs a minor change to pass `project_path` to agents.

**Tech Stack:** Python 3.12, `ast` stdlib, `subprocess` (ruff/semgrep), `packaging.version`, Pydantic, pytest

---

### Task 1: Add PA to AgentId Enum + Agent Skeleton

**Files:**
- Modify: `src/dazzle/sentinel/models.py`
- Create: `src/dazzle/sentinel/agents/python_audit.py`
- Modify: `src/dazzle/sentinel/agents/__init__.py`
- Create: `tests/unit/test_python_audit_agent.py`

- [ ] **Step 1: Write test for PA agent registration**

Create `tests/unit/test_python_audit_agent.py`:

```python
"""Tests for the PythonAuditAgent (PA)."""

from dazzle.sentinel.models import AgentId


class TestPythonAuditAgentRegistration:
    def test_pa_in_agent_id_enum(self) -> None:
        """PA is a valid AgentId."""
        assert AgentId.PA == "PA"

    def test_pa_agent_in_registry(self) -> None:
        """PythonAuditAgent appears in get_all_agents()."""
        from dazzle.sentinel.agents import get_all_agents

        agents = get_all_agents()
        agent_ids = [a.agent_id for a in agents]
        assert AgentId.PA in agent_ids

    def test_pa_agent_by_id(self) -> None:
        """get_agent('PA') returns the PythonAuditAgent."""
        from dazzle.sentinel.agents import get_agent

        agent = get_agent("PA")
        assert agent is not None
        assert agent.agent_id == AgentId.PA
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_python_audit_agent.py::TestPythonAuditAgentRegistration -v`
Expected: FAIL — `AgentId` has no attribute `PA`

- [ ] **Step 3: Add PA to AgentId enum**

In `src/dazzle/sentinel/models.py`, add to the `AgentId` enum (after `BL = "BL"`):

```python
    PA = "PA"
```

- [ ] **Step 4: Create the agent skeleton**

Create `src/dazzle/sentinel/agents/python_audit.py`:

```python
"""Python Audit detection agent (PA) — detects obsolete Python patterns.

Three detection layers:
1. Ruff profile scan (UP, PTH, ASYNC, C4, SIM rules)
2. Semgrep ruleset (deprecated stdlib, patterns ruff misses)
3. @heuristic methods (LLM training-bias patterns)
"""

from __future__ import annotations  # required: DetectionAgent forward ref

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
            import tomllib

            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            requires = data.get("project", {}).get("requires-python", "")
            # Parse ">=3.12" or ">=3.10,<4"
            import re

            match = re.search(r"(\d+)\.(\d+)", requires)
            if match:
                return (int(match.group(1)), int(match.group(2)))
        except Exception:
            pass
        return (3, 10)
```

- [ ] **Step 5: Register in agents/__init__.py**

In `src/dazzle/sentinel/agents/__init__.py`, add to `get_all_agents()`:

Add the import:
```python
    from .python_audit import PythonAuditAgent
```

Add to the return list:
```python
        PythonAuditAgent(),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_python_audit_agent.py -v`
Expected: All 3 tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/sentinel/models.py src/dazzle/sentinel/agents/python_audit.py src/dazzle/sentinel/agents/__init__.py tests/unit/test_python_audit_agent.py
git commit -m "feat: PythonAuditAgent skeleton with PA agent ID (#sentinel)"
```

---

### Task 2: Pass project_path to Agents via Orchestrator

**Files:**
- Modify: `src/dazzle/sentinel/orchestrator.py`
- Modify: `src/dazzle/sentinel/agents/__init__.py`

- [ ] **Step 1: Write test for project_path propagation**

Append to `tests/unit/test_python_audit_agent.py`:

```python
from pathlib import Path


class TestProjectPathPropagation:
    def test_pa_agent_receives_project_path(self) -> None:
        """PythonAuditAgent stores its project_path."""
        from dazzle.sentinel.agents.python_audit import PythonAuditAgent

        agent = PythonAuditAgent(project_path=Path("/tmp/test-project"))
        assert agent._project_path == Path("/tmp/test-project")

    def test_get_all_agents_with_project_path(self) -> None:
        """get_all_agents(project_path=...) passes path to PA agent."""
        from dazzle.sentinel.agents import get_all_agents
        from dazzle.sentinel.agents.python_audit import PythonAuditAgent

        agents = get_all_agents(project_path=Path("/tmp/test"))
        pa_agents = [a for a in agents if isinstance(a, PythonAuditAgent)]
        assert len(pa_agents) == 1
        assert pa_agents[0]._project_path == Path("/tmp/test")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_python_audit_agent.py::TestProjectPathPropagation -v`
Expected: FAIL — `get_all_agents()` doesn't accept `project_path`

- [ ] **Step 3: Update get_all_agents to accept project_path**

In `src/dazzle/sentinel/agents/__init__.py`, change the function signature:

```python
def get_all_agents(*, project_path: Path | None = None) -> list[DetectionAgent]:
    """Return an instance of every registered detection agent."""
    from pathlib import Path as _Path

    from .auth_authorization import AuthAuthorizationAgent
    from .business_logic import BusinessLogicAgent
    from .data_integrity import DataIntegrityAgent
    from .deployment_state import DeploymentStateAgent
    from .integration_dependency import IntegrationDependencyAgent
    from .multi_tenancy import MultiTenancyAgent
    from .operational_hygiene import OperationalHygieneAgent
    from .performance_resource import PerformanceResourceAgent
    from .python_audit import PythonAuditAgent

    return [
        DataIntegrityAgent(),
        AuthAuthorizationAgent(),
        MultiTenancyAgent(),
        IntegrationDependencyAgent(),
        DeploymentStateAgent(),
        PerformanceResourceAgent(),
        OperationalHygieneAgent(),
        BusinessLogicAgent(),
        PythonAuditAgent(project_path=project_path),
    ]
```

- [ ] **Step 4: Update orchestrator to pass project_path**

In `src/dazzle/sentinel/orchestrator.py`, in `run_scan()`, change the `get_all_agents()` call (around line 49):

```python
        agents = get_all_agents(project_path=self._store._project_path)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_python_audit_agent.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Run existing sentinel tests to verify no breakage**

Run: `pytest tests/unit/test_sentinel*.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/sentinel/agents/__init__.py src/dazzle/sentinel/orchestrator.py tests/unit/test_python_audit_agent.py
git commit -m "feat: pass project_path through orchestrator to agents"
```

---

### Task 3: Ruff Detection Layer

**Files:**
- Modify: `src/dazzle/sentinel/agents/python_audit.py`

- [ ] **Step 1: Write tests for ruff layer**

Append to `tests/unit/test_python_audit_agent.py`:

```python
import json
from unittest.mock import MagicMock, patch

from dazzle.sentinel.models import Finding, Severity


class TestRuffDetectionLayer:
    def _make_agent(self, tmp_path: Path) -> "PythonAuditAgent":
        from dazzle.sentinel.agents.python_audit import PythonAuditAgent

        return PythonAuditAgent(project_path=tmp_path)

    def test_parse_ruff_json_to_findings(self, tmp_path: Path) -> None:
        """Ruff JSON output is converted to Finding objects."""
        agent = self._make_agent(tmp_path)
        ruff_output = [
            {
                "code": "UP007",
                "message": "Use `X | Y` instead of `Optional[X]`",
                "filename": str(tmp_path / "app" / "main.py"),
                "location": {"row": 5, "column": 1},
                "end_location": {"row": 5, "column": 20},
                "fix": {"message": "Convert to `X | Y`", "edits": []},
            }
        ]
        findings = agent._parse_ruff_findings(ruff_output)
        assert len(findings) == 1
        f = findings[0]
        assert f.heuristic_id == "PA-UP007"
        assert f.agent == AgentId.PA
        assert f.severity == Severity.LOW
        assert "Optional" in f.title

    def test_empty_ruff_output(self, tmp_path: Path) -> None:
        """Empty ruff output produces no findings."""
        agent = self._make_agent(tmp_path)
        findings = agent._parse_ruff_findings([])
        assert findings == []

    def test_ruff_severity_mapping(self, tmp_path: Path) -> None:
        """Ruff rule codes map to correct severities."""
        from dazzle.sentinel.agents.python_audit import _ruff_severity

        assert _ruff_severity("UP007") == Severity.LOW
        assert _ruff_severity("PTH100") == Severity.INFO
        assert _ruff_severity("ASYNC100") == Severity.MEDIUM
        assert _ruff_severity("SIM110") == Severity.INFO
        assert _ruff_severity("C400") == Severity.INFO
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_python_audit_agent.py::TestRuffDetectionLayer -v`
Expected: FAIL — `_parse_ruff_findings` and `_ruff_severity` not defined

- [ ] **Step 3: Implement ruff detection layer**

Add to `src/dazzle/sentinel/agents/python_audit.py`:

```python
# At module level, after imports:

def _ruff_severity(code: str) -> Severity:
    """Map ruff rule code prefix to sentinel severity."""
    from dazzle.sentinel.models import Severity

    prefix = code.rstrip("0123456789")
    return {
        "UP": Severity.LOW,
        "PTH": Severity.INFO,
        "ASYNC": Severity.MEDIUM,
        "C": Severity.INFO,
        "SIM": Severity.INFO,
    }.get(prefix, Severity.INFO)
```

Add these methods to `PythonAuditAgent`:

```python
    def _run_ruff(self) -> list[Finding]:
        """Run ruff with curated rules and parse JSON output."""
        import subprocess

        from dazzle.sentinel.models import Finding

        scan_paths = [str(d) for d in self._get_scan_dirs() if d.exists()]
        if not scan_paths:
            return []

        major, minor = self._get_target_python_version()
        target = f"py{major}{minor}"

        try:
            result = subprocess.run(
                [
                    "ruff", "check",
                    "--select", "UP,PTH,ASYNC,C4,SIM",
                    "--output-format", "json",
                    "--target-version", target,
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

    def _parse_ruff_findings(self, items: list[dict]) -> list[Finding]:
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
                    ) if fix_msg else None,
                )
            )
        return findings

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_python_audit_agent.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/sentinel/agents/python_audit.py tests/unit/test_python_audit_agent.py
git commit -m "feat: ruff detection layer for PythonAuditAgent"
```

---

### Task 4: Semgrep Ruleset + Detection Layer

**Files:**
- Create: `src/dazzle/sentinel/rules/python_audit.yml`
- Modify: `src/dazzle/sentinel/agents/python_audit.py`

- [ ] **Step 1: Create the semgrep ruleset**

Create `src/dazzle/sentinel/rules/python_audit.yml`:

```yaml
rules:
  - id: PA-SG-distutils
    patterns:
      - pattern-either:
          - pattern: import distutils
          - pattern: from distutils import ...
    message: "distutils removed in Python 3.12. Use setuptools or packaging."
    languages: [python]
    severity: ERROR
    metadata:
      min_python: "3.12"
      sentinel_severity: HIGH

  - id: PA-SG-pkg-resources
    patterns:
      - pattern-either:
          - pattern: import pkg_resources
          - pattern: from pkg_resources import ...
    message: "pkg_resources is deprecated. Use importlib.metadata or importlib.resources."
    languages: [python]
    severity: WARNING
    metadata:
      min_python: "3.9"
      sentinel_severity: MEDIUM

  - id: PA-SG-cgi
    patterns:
      - pattern-either:
          - pattern: import cgi
          - pattern: import cgitb
          - pattern: from cgi import ...
    message: "cgi module removed in Python 3.13. Use urllib.parse or a framework."
    languages: [python]
    severity: ERROR
    metadata:
      min_python: "3.13"
      sentinel_severity: HIGH

  - id: PA-SG-imp
    patterns:
      - pattern-either:
          - pattern: import imp
          - pattern: from imp import ...
    message: "imp module removed in Python 3.12. Use importlib."
    languages: [python]
    severity: ERROR
    metadata:
      min_python: "3.12"
      sentinel_severity: HIGH

  - id: PA-SG-event-loop
    pattern: asyncio.get_event_loop()
    message: "asyncio.get_event_loop() deprecated in 3.10. Use asyncio.get_running_loop() or asyncio.run()."
    languages: [python]
    severity: WARNING
    metadata:
      min_python: "3.10"
      sentinel_severity: HIGH

  - id: PA-SG-timezone-utc
    pattern: datetime.timezone.utc
    message: "Use datetime.UTC (Python 3.11+) instead of datetime.timezone.utc."
    languages: [python]
    severity: INFO
    metadata:
      min_python: "3.11"
      sentinel_severity: INFO

  - id: PA-SG-nose
    patterns:
      - pattern-either:
          - pattern: import nose
          - pattern: from nose import ...
    message: "nose is abandoned. Migrate to pytest."
    languages: [python]
    severity: ERROR
    metadata:
      min_python: "3.0"
      sentinel_severity: HIGH

  - id: PA-SG-toml-pypi
    patterns:
      - pattern-either:
          - pattern: import toml
          - pattern: from toml import ...
    message: "Use tomllib (stdlib 3.11+) instead of the toml PyPI package."
    languages: [python]
    severity: WARNING
    metadata:
      min_python: "3.11"
      sentinel_severity: MEDIUM
```

- [ ] **Step 2: Write tests for semgrep layer**

Append to `tests/unit/test_python_audit_agent.py`:

```python
class TestSemgrepDetectionLayer:
    def _make_agent(self, tmp_path: Path) -> "PythonAuditAgent":
        from dazzle.sentinel.agents.python_audit import PythonAuditAgent

        return PythonAuditAgent(project_path=tmp_path)

    def test_parse_semgrep_json_to_findings(self, tmp_path: Path) -> None:
        """Semgrep JSON output is converted to Finding objects."""
        agent = self._make_agent(tmp_path)
        semgrep_output = {
            "results": [
                {
                    "check_id": "PA-SG-distutils",
                    "path": str(tmp_path / "app" / "setup.py"),
                    "start": {"line": 1, "col": 1},
                    "end": {"line": 1, "col": 20},
                    "extra": {
                        "message": "distutils removed in Python 3.12.",
                        "severity": "ERROR",
                        "metadata": {"sentinel_severity": "HIGH", "min_python": "3.12"},
                        "lines": "import distutils",
                    },
                }
            ]
        }
        findings = agent._parse_semgrep_findings(semgrep_output)
        assert len(findings) == 1
        f = findings[0]
        assert f.heuristic_id == "PA-SG-distutils"
        assert f.severity == Severity.HIGH

    def test_empty_semgrep_results(self, tmp_path: Path) -> None:
        """Empty semgrep results produce no findings."""
        agent = self._make_agent(tmp_path)
        findings = agent._parse_semgrep_findings({"results": []})
        assert findings == []

    def test_semgrep_ruleset_file_exists(self) -> None:
        """The shipped semgrep ruleset YAML file exists."""
        ruleset = Path(__file__).parent.parent.parent / "src" / "dazzle" / "sentinel" / "rules" / "python_audit.yml"
        assert ruleset.exists()
```

- [ ] **Step 3: Implement semgrep detection layer**

Add to `PythonAuditAgent` in `python_audit.py`:

```python
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
                    "--config", str(ruleset),
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

    def _parse_semgrep_findings(self, data: dict) -> list[Finding]:
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
```

- [ ] **Step 4: Create the rules directory**

```bash
mkdir -p src/dazzle/sentinel/rules
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_python_audit_agent.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/sentinel/rules/python_audit.yml src/dazzle/sentinel/agents/python_audit.py tests/unit/test_python_audit_agent.py
git commit -m "feat: semgrep detection layer + ruleset for PythonAuditAgent"
```

---

### Task 5: LLM Training-Bias Heuristics (PA-LLM-01 through PA-LLM-04)

**Files:**
- Modify: `src/dazzle/sentinel/agents/python_audit.py`

- [ ] **Step 1: Write tests for LLM heuristics**

Append to `tests/unit/test_python_audit_agent.py`:

```python
import ast
import textwrap


class TestLLMHeuristics:
    def _make_agent(self, tmp_path: Path) -> "PythonAuditAgent":
        from dazzle.sentinel.agents.python_audit import PythonAuditAgent

        return PythonAuditAgent(project_path=tmp_path)

    def test_llm01_requests_in_async_codebase(self, tmp_path: Path) -> None:
        """Flag requests import when async def exists in project."""
        agent = self._make_agent(tmp_path)
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        # File with async def
        (app_dir / "server.py").write_text("async def handle():\n    pass\n")
        # File importing requests
        (app_dir / "client.py").write_text("import requests\n\ndef fetch():\n    return requests.get('http://example.com')\n")

        appspec = MagicMock()
        findings = agent.check_requests_in_async_codebase(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PA-LLM-01"
        assert "httpx" in findings[0].description.lower() or "httpx" in findings[0].remediation.summary.lower()

    def test_llm01_no_flag_sync_only(self, tmp_path: Path) -> None:
        """Do not flag requests if project has no async code."""
        agent = self._make_agent(tmp_path)
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "client.py").write_text("import requests\n")

        appspec = MagicMock()
        findings = agent.check_requests_in_async_codebase(appspec)
        assert findings == []

    def test_llm03_manual_dunders(self, tmp_path: Path) -> None:
        """Flag class with manual __init__ + __repr__ but no @dataclass."""
        agent = self._make_agent(tmp_path)
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "models.py").write_text(textwrap.dedent("""\
            class Config:
                def __init__(self, name, value):
                    self.name = name
                    self.value = value

                def __repr__(self):
                    return f"Config({self.name})"
        """))

        appspec = MagicMock()
        findings = agent.check_manual_dunders(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PA-LLM-03"

    def test_llm03_no_flag_dataclass(self, tmp_path: Path) -> None:
        """Do not flag class that already uses @dataclass."""
        agent = self._make_agent(tmp_path)
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "models.py").write_text(textwrap.dedent("""\
            from dataclasses import dataclass

            @dataclass
            class Config:
                name: str
                value: str
        """))

        appspec = MagicMock()
        findings = agent.check_manual_dunders(appspec)
        assert findings == []

    def test_llm04_unittest_in_pytest_project(self, tmp_path: Path) -> None:
        """Flag unittest.TestCase when conftest.py exists."""
        agent = self._make_agent(tmp_path)
        (tmp_path / "conftest.py").write_text("")
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "test_stuff.py").write_text(textwrap.dedent("""\
            import unittest

            class TestFoo(unittest.TestCase):
                def test_bar(self):
                    self.assertEqual(1, 1)
        """))

        appspec = MagicMock()
        findings = agent.check_unittest_in_pytest_project(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PA-LLM-04"

    def test_llm04_no_flag_without_conftest(self, tmp_path: Path) -> None:
        """Do not flag unittest if no conftest.py (not a pytest project)."""
        agent = self._make_agent(tmp_path)
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "test_stuff.py").write_text("import unittest\n")

        appspec = MagicMock()
        findings = agent.check_unittest_in_pytest_project(appspec)
        assert findings == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_python_audit_agent.py::TestLLMHeuristics -v`
Expected: FAIL — heuristic methods don't exist

- [ ] **Step 3: Implement LLM heuristics**

Add these `@heuristic`-decorated methods to `PythonAuditAgent`:

```python
    @heuristic(
        heuristic_id="PA-LLM-01",
        category="python_audit",
        subcategory="llm_bias",
        title="requests library in async codebase — prefer httpx",
    )
    def check_requests_in_async_codebase(self, appspec: AppSpec) -> list[Finding]:
        """Flag `import requests` when project has async code."""
        import ast

        from dazzle.sentinel.models import (
            Confidence,
            Evidence,
            Finding,
            Remediation,
            RemediationEffort,
            Severity,
        )

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
                evidence=[Evidence(evidence_type="source_pattern", location=f"{path}:{line}")]
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

        findings = []
        dunder_set = {"__init__", "__repr__", "__eq__"}

        for f in self._get_python_files():
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                # Skip if already decorated with @dataclass
                has_dataclass = any(
                    (isinstance(d, ast.Name) and d.id == "dataclass")
                    or (isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "dataclass")
                    or (isinstance(d, ast.Attribute) and d.attr == "dataclass")
                    for d in node.decorator_list
                )
                if has_dataclass:
                    continue
                methods = {
                    n.name for n in node.body
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
                            evidence=[Evidence(evidence_type="source_pattern", location=f"{f}:{node.lineno}")],
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

        # Only flag if this is a pytest project
        if not (self._project_path / "conftest.py").exists():
            return []

        findings = []
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
                                    evidence=[Evidence(evidence_type="source_pattern", location=f"{f}:{node.lineno}")],
                                    remediation=Remediation(
                                        summary="Rewrite as pytest functions with assert statements",
                                        effort=RemediationEffort.MEDIUM,
                                    ),
                                )
                            )
        return findings
```

Also add the `heuristic` import at the top of the file if not already present:

```python
from dazzle.sentinel.agents.base import DetectionAgent, heuristic
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_python_audit_agent.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/sentinel/agents/python_audit.py tests/unit/test_python_audit_agent.py
git commit -m "feat: LLM training-bias heuristics PA-LLM-01/03/04"
```

---

### Task 6: Wire Heuristics into run() + Python Version Filtering

**Files:**
- Modify: `src/dazzle/sentinel/agents/python_audit.py`

- [ ] **Step 1: Write tests for version filtering and full run**

Append to `tests/unit/test_python_audit_agent.py`:

```python
class TestVersionFiltering:
    def test_filter_by_python_version(self, tmp_path: Path) -> None:
        """Findings with min_version above target are filtered out."""
        from dazzle.sentinel.agents.python_audit import PythonAuditAgent, _should_include

        # Project targets 3.9 — 3.11+ findings filtered
        assert _should_include("3.9", (3, 9)) is True
        assert _should_include("3.11", (3, 9)) is False
        assert _should_include("3.12", (3, 12)) is True
        assert _should_include("3.10", (3, 12)) is True

    def test_get_target_version_from_pyproject(self, tmp_path: Path) -> None:
        """Reads requires-python from pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12"\n')
        from dazzle.sentinel.agents.python_audit import PythonAuditAgent

        agent = PythonAuditAgent(project_path=tmp_path)
        assert agent._get_target_python_version() == (3, 12)

    def test_default_version_when_no_pyproject(self, tmp_path: Path) -> None:
        """Default to 3.10 when no pyproject.toml."""
        from dazzle.sentinel.agents.python_audit import PythonAuditAgent

        agent = PythonAuditAgent(project_path=tmp_path)
        assert agent._get_target_python_version() == (3, 10)


class TestFullRun:
    def test_run_returns_agent_result(self, tmp_path: Path) -> None:
        """run() returns an AgentResult with PA agent ID."""
        from dazzle.sentinel.agents.python_audit import PythonAuditAgent

        agent = PythonAuditAgent(project_path=tmp_path)
        appspec = MagicMock()
        result = agent.run(appspec)
        assert result.agent == AgentId.PA
        assert result.heuristics_run >= 0
        assert result.duration_ms >= 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_python_audit_agent.py::TestVersionFiltering -v`
Expected: FAIL — `_should_include` not defined

- [ ] **Step 3: Add version filtering and wire layers into run()**

Add at module level in `python_audit.py`:

```python
def _should_include(min_version_str: str, target: tuple[int, int]) -> bool:
    """Return True if the finding's min Python version <= the project's target."""
    try:
        parts = min_version_str.split(".")
        min_ver = (int(parts[0]), int(parts[1]))
        return min_ver <= target
    except (IndexError, ValueError):
        return True
```

Update the `run()` method to call all three layers:

```python
    def run(self, appspec: AppSpec) -> AgentResult:
        """Run all detection layers against user project code."""
        import time

        from dazzle.sentinel.models import AgentResult as AR

        t0 = time.monotonic()
        all_findings = []
        errors = []

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_python_audit_agent.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/sentinel/agents/python_audit.py tests/unit/test_python_audit_agent.py
git commit -m "feat: version filtering + wire all layers into PA run()"
```

---

### Task 7: File-Based Heuristics (PA-LLM-05, PA-LLM-06)

**Files:**
- Modify: `src/dazzle/sentinel/agents/python_audit.py`

- [ ] **Step 1: Write tests**

Append to `tests/unit/test_python_audit_agent.py`:

```python
class TestFileBasedHeuristics:
    def _make_agent(self, tmp_path: Path) -> "PythonAuditAgent":
        from dazzle.sentinel.agents.python_audit import PythonAuditAgent

        return PythonAuditAgent(project_path=tmp_path)

    def test_llm05_setup_py_alongside_pyproject(self, tmp_path: Path) -> None:
        """Flag setup.py when pyproject.toml exists."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
        (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n")

        agent = self._make_agent(tmp_path)
        appspec = MagicMock()
        findings = agent.check_setup_py_with_pyproject(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PA-LLM-05"

    def test_llm05_no_flag_setup_py_alone(self, tmp_path: Path) -> None:
        """Do not flag setup.py if pyproject.toml doesn't exist."""
        (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n")

        agent = self._make_agent(tmp_path)
        appspec = MagicMock()
        findings = agent.check_setup_py_with_pyproject(appspec)
        assert findings == []

    def test_llm06_pip_when_uv_available(self, tmp_path: Path) -> None:
        """Flag pip install references when uv.lock exists."""
        (tmp_path / "uv.lock").write_text("")
        (tmp_path / "README.md").write_text("Run `pip install -r requirements.txt` to set up.\n")

        agent = self._make_agent(tmp_path)
        appspec = MagicMock()
        findings = agent.check_pip_when_uv_available(appspec)
        assert len(findings) >= 1
        assert findings[0].heuristic_id == "PA-LLM-06"

    def test_llm06_no_flag_without_uv(self, tmp_path: Path) -> None:
        """Do not flag pip references if no uv.lock."""
        (tmp_path / "README.md").write_text("Run `pip install -r requirements.txt`.\n")

        agent = self._make_agent(tmp_path)
        appspec = MagicMock()
        findings = agent.check_pip_when_uv_available(appspec)
        assert findings == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_python_audit_agent.py::TestFileBasedHeuristics -v`
Expected: FAIL — methods don't exist

- [ ] **Step 3: Implement file-based heuristics**

Add to `PythonAuditAgent`:

```python
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

        findings = []
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
                        evidence=[Evidence(evidence_type="source_pattern", location=str(path))],
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
        findings = []

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
                            evidence=[Evidence(evidence_type="source_pattern", location=f"{path}:{i}", snippet=line.strip())],
                            remediation=Remediation(
                                summary="Replace pip install with uv pip install, virtualenv with uv venv",
                                effort=RemediationEffort.TRIVIAL,
                            ),
                        )
                    )
                    break  # One finding per file is enough
        return findings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_python_audit_agent.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/sentinel/agents/python_audit.py tests/unit/test_python_audit_agent.py
git commit -m "feat: file-based heuristics PA-LLM-05/06"
```

---

### Task 8: Full Integration Test + Lint

**Files:**
- No new files

- [ ] **Step 1: Run all unit tests**

Run: `pytest tests/ -m "not e2e" -x -q`
Expected: All tests PASS

- [ ] **Step 2: Run lint**

Run: `ruff check src/dazzle/sentinel/agents/python_audit.py src/dazzle/sentinel/models.py src/dazzle/sentinel/orchestrator.py src/dazzle/sentinel/agents/__init__.py --fix && ruff format src/dazzle/sentinel/agents/python_audit.py src/dazzle/sentinel/models.py src/dazzle/sentinel/orchestrator.py src/dazzle/sentinel/agents/__init__.py`
Expected: Clean

- [ ] **Step 3: Run mypy**

Run: `mypy src/dazzle/sentinel/agents/python_audit.py src/dazzle/sentinel/models.py`
Expected: No errors

- [ ] **Step 4: Fix any issues and commit**

```bash
git add -u
git commit -m "fix: lint and type fixes for PythonAuditAgent"
```

(Skip this commit if no fixes needed.)
