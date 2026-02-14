"""Tests for the agent registry."""

from __future__ import annotations

from dazzle.sentinel.agents import get_agent, get_all_agents
from dazzle.sentinel.agents.auth_authorization import AuthAuthorizationAgent
from dazzle.sentinel.agents.business_logic import BusinessLogicAgent
from dazzle.sentinel.agents.data_integrity import DataIntegrityAgent
from dazzle.sentinel.agents.deployment_state import DeploymentStateAgent
from dazzle.sentinel.agents.integration_dependency import IntegrationDependencyAgent
from dazzle.sentinel.agents.multi_tenancy import MultiTenancyAgent
from dazzle.sentinel.agents.operational_hygiene import OperationalHygieneAgent
from dazzle.sentinel.agents.performance_resource import PerformanceResourceAgent


class TestGetAllAgents:
    def test_returns_eight_agents(self) -> None:
        agents = get_all_agents()
        assert len(agents) == 8

    def test_agent_types(self) -> None:
        agents = get_all_agents()
        types = {type(a) for a in agents}
        assert types == {
            DataIntegrityAgent,
            AuthAuthorizationAgent,
            MultiTenancyAgent,
            IntegrationDependencyAgent,
            DeploymentStateAgent,
            PerformanceResourceAgent,
            OperationalHygieneAgent,
            BusinessLogicAgent,
        }

    def test_unique_agent_ids(self) -> None:
        agents = get_all_agents()
        ids = [a.agent_id for a in agents]
        assert len(ids) == len(set(ids))


class TestGetAgent:
    def test_returns_agent_by_id(self) -> None:
        agent = get_agent("DI")
        assert agent is not None
        assert isinstance(agent, DataIntegrityAgent)

    def test_returns_none_for_unknown(self) -> None:
        assert get_agent("UNKNOWN") is None

    def test_all_registered_ids(self) -> None:
        for agent_id in ("DI", "AA", "MT", "ID", "DS", "PR", "OP", "BL"):
            assert get_agent(agent_id) is not None
