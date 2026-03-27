"""Tests for the PythonAuditAgent (PA)."""

from pathlib import Path

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
