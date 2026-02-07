"""
Mission definitions for the DazzleAgent.

Missions define what an agent should accomplish: system prompt,
available tools, completion criteria, and token budget.
"""

from .discovery import build_discovery_mission
from .entity_completeness import build_entity_completeness_mission
from .workflow_coherence import build_workflow_coherence_mission

__all__ = [
    "build_discovery_mission",
    "build_entity_completeness_mission",
    "build_workflow_coherence_mission",
]
