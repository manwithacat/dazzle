"""Transition side-effect runner for entity state machines.

Fires create/update effects declared in on_transition: blocks when an
entity's status field changes. Reuses SideEffectExecutor for execution.
A ContextVar cascade depth limit prevents infinite loops.
"""

import logging
from contextvars import ContextVar
from typing import Any

from dazzle.core.ir.process import StepEffect

from .side_effect_executor import EffectContext, SideEffectExecutor

logger = logging.getLogger(__name__)

MAX_CASCADE_DEPTH = 3

_cascade_depth: ContextVar[int] = ContextVar("transition_cascade_depth", default=0)


class TransitionEffectRunner:
    """Orchestrates side effects for entity state transitions.

    Registered as an on_updated callback for entities that have
    on_transition effects declared in their state machine.
    """

    def __init__(
        self,
        executor: SideEffectExecutor,
        entity_transitions: dict[str, list[tuple[str, str, list[StepEffect]]]],
        status_fields: dict[str, str],
    ) -> None:
        self._executor = executor
        # {entity_name: [(from_state, to_state, effects), ...]}
        self._entity_transitions = entity_transitions
        # {entity_name: status_field_name}
        self._status_fields = status_fields

    async def on_entity_updated(
        self,
        entity_name: str,
        entity_id: str,
        entity_data: dict[str, Any],
        old_data: dict[str, Any] | None,
    ) -> None:
        """Callback fired after an entity update. Checks for status change and fires effects."""
        if entity_name not in self._entity_transitions:
            return
        if not old_data:
            return

        status_field = self._status_fields.get(entity_name)
        if not status_field:
            return

        old_status = old_data.get(status_field)
        new_status = entity_data.get(status_field)
        if old_status is None or new_status is None or old_status == new_status:
            return

        # Check cascade depth
        depth = _cascade_depth.get(0)
        if depth >= MAX_CASCADE_DEPTH:
            logger.warning(
                "Transition effect cascade depth %d reached for %s %s (%s -> %s), skipping",
                depth,
                entity_name,
                entity_id,
                old_status,
                new_status,
            )
            return

        # Find matching effects: exact match + wildcard
        effects_to_run: list[StepEffect] = []
        for from_state, to_state, effects in self._entity_transitions[entity_name]:
            if to_state == new_status and (from_state == old_status or from_state == "*"):
                effects_to_run.extend(effects)

        if not effects_to_run:
            return

        context = EffectContext(trigger_entity=entity_data)
        token = _cascade_depth.set(depth + 1)
        try:
            results = await self._executor.execute_effects(effects_to_run, context)
            for result in results:
                if not result.success:
                    logger.error(
                        "Transition effect %s %s failed for %s %s: %s",
                        result.action,
                        result.entity_name,
                        entity_name,
                        entity_id,
                        result.error,
                    )
        finally:
            _cascade_depth.reset(token)
