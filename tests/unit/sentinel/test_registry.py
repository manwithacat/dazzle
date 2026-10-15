"""Tests for the agent registry and each agent's identity and clean run.

The per-agent heuristic behaviour lives in ``test_agent_*.py``; this file pins
what every agent shares: its registry id, its class, its heuristic ids in run
order, and what a full ``run()`` over a minimal clean spec reports.
"""

from typing import Any

import pytest

from dazzle.sentinel.agents import get_agent, get_all_agents
from dazzle.sentinel.agents.auth_authorization import AuthAuthorizationAgent
from dazzle.sentinel.agents.business_logic import BusinessLogicAgent
from dazzle.sentinel.agents.data_integrity import DataIntegrityAgent
from dazzle.sentinel.agents.deployment_state import DeploymentStateAgent
from dazzle.sentinel.agents.integration_dependency import IntegrationDependencyAgent
from dazzle.sentinel.agents.multi_tenancy import MultiTenancyAgent
from dazzle.sentinel.agents.operational_hygiene import OperationalHygieneAgent
from dazzle.sentinel.agents.performance_resource import PerformanceResourceAgent
from dazzle.sentinel.agents.python_audit import PythonAuditAgent
from dazzle.sentinel.models import AgentId

from .conftest import make_appspec, make_entity, pk_field, str_field

# (registry id, class, heuristic ids in run order). PythonAuditAgent's
# heuristics and run are covered by tests/unit/test_python_audit_*.py.
AGENTS = [
    pytest.param("DI", DataIntegrityAgent, [f"DI-0{i}" for i in range(1, 8)], id="DI"),
    pytest.param("AA", AuthAuthorizationAgent, [f"AA-0{i}" for i in range(1, 8)], id="AA"),
    pytest.param(
        "MT", MultiTenancyAgent, ["MT-01", "MT-02", "MT-03", "MT-04", "MT-06", "MT-07"], id="MT"
    ),
    pytest.param(
        "ID",
        IntegrationDependencyAgent,
        ["ID-01", "ID-02", "ID-03", "ID-06", "ID-07", "ID-08"],
        id="ID",
    ),
    pytest.param("DS", DeploymentStateAgent, ["DS-05", "DS-08"], id="DS"),
    pytest.param(
        "PR",
        PerformanceResourceAgent,
        ["PR-01", "PR-02", "PR-03", "PR-05", "PR-07", "PR-08"],
        id="PR",
    ),
    pytest.param(
        "OP",
        OperationalHygieneAgent,
        ["OP-01", "OP-02", "OP-03", "OP-04", "OP-06", "OP-07", "OP-08"],
        id="OP",
    ),
    pytest.param("BL", BusinessLogicAgent, ["BL-01", "BL-02", "BL-05", "BL-06", "BL-07"], id="BL"),
]


def test_registry_holds_each_agent_once() -> None:
    agents = get_all_agents()
    assert sorted(type(a).__name__ for a in agents) == sorted(
        c.__name__
        for c in (
            DataIntegrityAgent,
            AuthAuthorizationAgent,
            MultiTenancyAgent,
            IntegrationDependencyAgent,
            DeploymentStateAgent,
            PerformanceResourceAgent,
            OperationalHygieneAgent,
            BusinessLogicAgent,
            PythonAuditAgent,
        )
    )
    ids = [a.agent_id for a in agents]
    assert len(ids) == len(set(ids)) == 9


@pytest.mark.parametrize(
    ("agent_id", "cls"),
    [*[pytest.param(p.values[0], p.values[1], id=p.id) for p in AGENTS], ("PA", PythonAuditAgent)],
)
def test_get_agent_by_id(agent_id: str, cls: type) -> None:
    agent = get_agent(agent_id)
    assert isinstance(agent, cls)
    assert agent.agent_id == AgentId(agent_id)


def test_get_agent_unknown_id_is_none() -> None:
    assert get_agent("UNKNOWN") is None


@pytest.mark.parametrize(("agent_id", "cls", "heuristic_ids"), AGENTS)
def test_agent_heuristics_in_run_order(agent_id: str, cls: type, heuristic_ids: list[str]) -> None:
    agent: Any = cls()
    assert agent.agent_id == AgentId(agent_id)
    assert [meta.heuristic_id for meta, _ in agent.get_heuristics()] == heuristic_ids


# A Task with a pk and a required title, nothing else. Two heuristics fire by
# design on so bare a spec: AA-02 (no access spec) and BL-07 (no surface).
_CLEAN_FINDINGS = {"AA": ["AA-02"], "BL": ["BL-07"]}


@pytest.mark.parametrize(("agent_id", "cls", "heuristic_ids"), AGENTS)
def test_run_over_clean_spec(agent_id: str, cls: type, heuristic_ids: list[str]) -> None:
    entity = make_entity("Task", [pk_field(), str_field("title", required=True)])
    result = cls().run(make_appspec([entity]))
    assert result.agent == AgentId(agent_id)
    assert result.errors == []
    assert result.heuristics_run == len(heuristic_ids)
    assert result.duration_ms >= 0
    assert [f.heuristic_id for f in result.findings] == _CLEAN_FINDINGS.get(agent_id, [])
