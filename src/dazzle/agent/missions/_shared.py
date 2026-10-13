"""
IR access helpers shared by the headless discovery analyses.

Used by ``persona_journey``, ``entity_completeness`` and ``workflow_coherence``
(the static passes behind ``discovery(operation=coherence)``).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# IR Access Helpers
# =============================================================================


def get_surface_entity(surface: Any) -> str | None:
    """Get the entity reference from a surface, handling both IR and test mocks."""
    return surface.entity_ref or getattr(surface, "entity", None)


def is_step_kind(step: Any, kind_name: str) -> bool:
    """
    Check if a process step matches a given kind name.

    Handles both StrEnum values (StepKind.HUMAN_TASK) and plain strings
    ("human_task") as used in test mocks.
    """
    kind = getattr(step, "kind", None)
    if kind is None:
        return False
    kind_str = str(kind)
    return kind_str == kind_name or kind_str == f"StepKind.{kind_name.upper()}"


def is_trigger_kind(trigger: Any, kind_name: str) -> bool:
    """
    Check if a process trigger matches a given kind name.

    Handles both StrEnum values and plain strings.
    """
    trigger_kind = getattr(trigger, "kind", None)
    if trigger_kind is None:
        return False
    kind_str = str(trigger_kind)
    return kind_str == kind_name or kind_str == f"ProcessTriggerKind.{kind_name.upper()}"
