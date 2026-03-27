"""
Agent registry for Sentinel detection agents.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import DetectionAgent


def get_all_agents(*, project_path: Path | None = None) -> list[DetectionAgent]:
    """Return an instance of every registered detection agent."""
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


def get_agent(agent_id: str, *, project_path: Path | None = None) -> DetectionAgent | None:
    """Return a single agent by its ID string."""
    for agent in get_all_agents(project_path=project_path):
        if agent.agent_id.value == agent_id:
            return agent
    return None
