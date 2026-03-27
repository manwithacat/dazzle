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
