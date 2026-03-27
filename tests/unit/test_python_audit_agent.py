"""Tests for the PythonAuditAgent (PA)."""

import textwrap
from pathlib import Path
from unittest.mock import MagicMock

from dazzle.sentinel.models import AgentId, Severity


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
