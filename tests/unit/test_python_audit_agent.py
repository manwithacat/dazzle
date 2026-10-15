"""Tests for the PythonAuditAgent (PA)."""

import re
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dazzle.sentinel.models import AgentId, Severity
from tests.unit.helpers.python_audit import scan


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


class TestRuffDetectionLayer:
    def _make_agent(self, tmp_path: Path):
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


class TestSemgrepDetectionLayer:
    def _make_agent(self, tmp_path: Path):
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
                        "metadata": {
                            "sentinel_severity": "HIGH",
                            "min_python": "3.12",
                        },
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
        ruleset = (
            Path(__file__).parent.parent.parent
            / "src"
            / "dazzle"
            / "sentinel"
            / "rules"
            / "python_audit.yml"
        )
        assert ruleset.exists()


class TestLLMHeuristics:
    def _make_agent(self, tmp_path: Path):
        from dazzle.sentinel.agents.python_audit import PythonAuditAgent

        return PythonAuditAgent(project_path=tmp_path)

    def test_llm01_requests_in_async_codebase(self, tmp_path: Path) -> None:
        """Flag requests import when async def exists in project."""
        agent = self._make_agent(tmp_path)
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "server.py").write_text("async def handle():\n    pass\n")
        (app_dir / "client.py").write_text(
            "import requests\n\ndef fetch():\n    return requests.get('http://example.com')\n"
        )

        appspec = MagicMock()
        findings = agent.check_requests_in_async_codebase(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PA-LLM-01"

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
        (app_dir / "models.py").write_text(
            textwrap.dedent("""\
            class Config:
                def __init__(self, name, value):
                    self.name = name
                    self.value = value

                def __repr__(self):
                    return f"Config({self.name})"
        """)
        )

        appspec = MagicMock()
        findings = agent.check_manual_dunders(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PA-LLM-03"

    def test_llm03_no_flag_dataclass(self, tmp_path: Path) -> None:
        """Do not flag class that already uses @dataclass."""
        agent = self._make_agent(tmp_path)
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "models.py").write_text(
            textwrap.dedent("""\
            from dataclasses import dataclass

            @dataclass
            class Config:
                name: str
                value: str
        """)
        )

        appspec = MagicMock()
        findings = agent.check_manual_dunders(appspec)
        assert findings == []

    def test_llm04_unittest_in_pytest_project(self, tmp_path: Path) -> None:
        """Flag unittest.TestCase when conftest.py exists."""
        agent = self._make_agent(tmp_path)
        (tmp_path / "conftest.py").write_text("")
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "test_stuff.py").write_text(
            textwrap.dedent("""\
            import unittest

            class TestFoo(unittest.TestCase):
                def test_bar(self):
                    self.assertEqual(1, 1)
        """)
        )

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


class TestFileBasedHeuristics:
    def _make_agent(self, tmp_path: Path):
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


class TestVersionFiltering:
    def test_filter_by_python_version(self, tmp_path: Path) -> None:
        """Findings with min_version above target are filtered out."""
        from dazzle.sentinel.agents.python_audit import _should_include

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


# ---------------------------------------------------------------------------
# Contracts every source-scanning LLM heuristic (PA-LLM-07..11) shares.
# The per-heuristic files own the shape tables; these three tables own the
# wiring: catalogue entry, scan scope and noqa suppression.
# ---------------------------------------------------------------------------

_PA07_KEYERROR = "def sync():\n    try:\n        v = d[k]\n    except KeyError:\n        v = None\n"
_PA08_LOOP = "def render(orders):\n    for order in orders:\n        order.lines.all()\n"
_PA09_TWO_NONES = (
    "def parse(text: str) -> int | None:\n"
    "    if not text: return None\n"
    "    if text.isspace(): return None\n"
    "    return int(text)\n"
)
_PA10_ID_PARAM = "def get(user_id: str) -> None: ...\n"
_PA11_FSTRING = "def overdue(tid):\n    cur.execute(f\"SELECT * FROM invoice WHERE t = '{tid}'\")\n"


@pytest.mark.parametrize(
    ("heuristic_id", "source", "catalogue_entry"),
    [
        pytest.param("PA-LLM-07", _PA07_KEYERROR, "exceptions-as-control-flow", id="PA-LLM-07"),
        pytest.param("PA-LLM-08", _PA08_LOOP, "n-plus-one-in-user-code", id="PA-LLM-08"),
        pytest.param("PA-LLM-09", _PA09_TWO_NONES, "optional-instead-of-result", id="PA-LLM-09"),
        pytest.param("PA-LLM-10", _PA10_ID_PARAM, "magic-string-typing", id="PA-LLM-10"),
        pytest.param("PA-LLM-11", _PA11_FSTRING, "raw-sql-string-building", id="PA-LLM-11"),
    ],
)
def test_finding_links_its_counter_prior(
    tmp_path: Path, heuristic_id: str, source: str, catalogue_entry: str
) -> None:
    """One finding per canonical shape, carrying the catalogue entry and a
    remediation reference to ``docs/counter-priors/<entry>.md``."""
    findings = scan(tmp_path, heuristic_id, {"app/x.py": source})
    assert len(findings) == 1
    finding = findings[0]
    assert finding.heuristic_id == heuristic_id
    assert finding.catalogue_entry == catalogue_entry
    assert finding.remediation is not None
    assert f"docs/counter-priors/{catalogue_entry}.md" in " ".join(finding.remediation.references)


@pytest.mark.parametrize(
    ("heuristic_id", "source"),
    [
        pytest.param("PA-LLM-07", _PA07_KEYERROR, id="PA-LLM-07"),
        pytest.param("PA-LLM-08", _PA08_LOOP, id="PA-LLM-08"),
        pytest.param("PA-LLM-09", _PA09_TWO_NONES, id="PA-LLM-09"),
        pytest.param("PA-LLM-10", _PA10_ID_PARAM, id="PA-LLM-10"),
    ],
)
def test_tests_and_scripts_dirs_are_out_of_scope(
    tmp_path: Path, heuristic_id: str, source: str
) -> None:
    """``tests/`` and ``scripts/`` are not user app code for these heuristics.
    (PA-LLM-11 deliberately scans ``scripts/`` — pinned in its own file.)"""
    files = {"tests/f.py": source, "scripts/f.py": source}
    assert scan(tmp_path, heuristic_id, files) == []


@pytest.mark.parametrize(
    ("heuristic_id", "source"),
    [
        pytest.param(
            "PA-LLM-07",
            "def f():\n    try:  # noqa: PA-LLM-07 - boundary\n"
            "        v = d[k]\n    except KeyError:\n        v = None\n",
            id="PA-LLM-07-on-try-line",
        ),
        pytest.param(
            "PA-LLM-08",
            "def f():\n    for order in orders:  # noqa: PA-LLM-08 - prefetched\n"
            "        x = order.lines.all()\n",
            id="PA-LLM-08-on-for-line",
        ),
        pytest.param(
            "PA-LLM-08",
            "def f():\n    for order in orders:\n        x = order.lines.all()  # noqa: PA-LLM-08\n",
            id="PA-LLM-08-on-call-line",
        ),
        pytest.param(
            "PA-LLM-08",
            "def f(orders):\n"
            "    return [order.lines.all() for order in orders]  # noqa: PA-LLM-08 - prefetched\n",
            id="PA-LLM-08-on-comprehension-line",
        ),
        pytest.param(
            "PA-LLM-09",
            "def lookup(k) -> int | None:  # noqa: PA-LLM-09 - both Nones mean 'miss'\n"
            "    if not k: return None\n"
            "    if k not in cache: return None\n"
            "    return cache[k]\n",
            id="PA-LLM-09-on-def-line",
        ),
        pytest.param(
            "PA-LLM-10",
            "def f(user_id: str, tenant_id: str) -> None:  # noqa: PA-LLM-10 - opaque\n    pass\n",
            id="PA-LLM-10-on-def-line-covers-every-param",
        ),
        pytest.param(
            "PA-LLM-10",
            "def handle(action: str) -> str:\n"
            "    if action == 'create': return 'A'  # noqa: PA-LLM-10 — user input\n"
            "    elif action == 'update': return 'B'\n"
            "    elif action == 'delete': return 'C'\n"
            "    return 'X'\n",
            id="PA-LLM-10-enum-dispatch-on-opening-if",
        ),
        pytest.param(
            "PA-LLM-11",
            "def fetch(table):\n"
            "    cur.execute(f'SELECT * FROM {table}')  # noqa: PA-LLM-11 — whitelisted\n",
            id="PA-LLM-11-on-execute-line",
        ),
    ],
)
def test_noqa_comment_suppresses_finding(tmp_path: Path, heuristic_id: str, source: str) -> None:
    """The comment silences the finding, and only the comment: the same
    source without it fires."""
    unsuppressed = re.sub(r"  # noqa: PA-LLM-\d+[^\n]*", "", source)
    assert scan(tmp_path / "bare", heuristic_id, {"app/x.py": unsuppressed}) != []
    assert scan(tmp_path / "noqa", heuristic_id, {"app/x.py": source}) == []
