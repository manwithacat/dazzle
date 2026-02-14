"""
Agent registry for Sentinel detection agents.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import DetectionAgent


def get_all_agents() -> list[DetectionAgent]:
    """Return an instance of every registered detection agent."""
    from .auth_authorization import AuthAuthorizationAgent
    from .business_logic import BusinessLogicAgent
    from .data_integrity import DataIntegrityAgent
    from .deployment_state import DeploymentStateAgent
    from .integration_dependency import IntegrationDependencyAgent
    from .multi_tenancy import MultiTenancyAgent
    from .operational_hygiene import OperationalHygieneAgent
    from .performance_resource import PerformanceResourceAgent

    return [
        DataIntegrityAgent(),
        AuthAuthorizationAgent(),
        MultiTenancyAgent(),
        IntegrationDependencyAgent(),
        DeploymentStateAgent(),
        PerformanceResourceAgent(),
        OperationalHygieneAgent(),
        BusinessLogicAgent(),
    ]


def get_agent(agent_id: str) -> DetectionAgent | None:
    """Return a single agent by its ID string."""
    for agent in get_all_agents():
        if agent.agent_id.value == agent_id:
            return agent
    return None
