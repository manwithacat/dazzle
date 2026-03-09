"""
LLM intent trigger matcher.

Registers as an EntityEventBus handler and dispatches matching
entity events to the LLM job queue with write-back callbacks.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from dazzle.core.ir.llm import LLMTriggerEvent, LLMTriggerSpec

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec
    from dazzle_back.runtime.event_bus import EntityEvent
    from dazzle_back.runtime.llm_executor import ExecutionResult
    from dazzle_back.runtime.llm_queue import LLMJob, LLMJobQueue

logger = logging.getLogger(__name__)

# Map EntityEventType values to LLMTriggerEvent values
_EVENT_MAP: dict[str, LLMTriggerEvent] = {
    "entity:created": LLMTriggerEvent.CREATED,
    "entity:updated": LLMTriggerEvent.UPDATED,
    "entity:deleted": LLMTriggerEvent.DELETED,
}


class _TriggerEntry:
    """Internal trigger entry with resolved intent name."""

    __slots__ = ("intent_name", "trigger")

    def __init__(self, intent_name: str, trigger: LLMTriggerSpec):
        self.intent_name = intent_name
        self.trigger = trigger


class LLMTriggerMatcher:
    """Matches entity events to LLM intent triggers.

    Builds an index at startup from appspec.llm_intents triggers,
    keyed by (entity_name, event_type) for O(1) lookup per event.
    """

    def __init__(
        self, appspec: AppSpec, queue: LLMJobQueue, services: dict[str, Any] | None = None
    ):
        self._queue = queue
        self._services = services or {}
        self._index: dict[tuple[str, LLMTriggerEvent], list[_TriggerEntry]] = {}
        self._build_index(appspec)

    def _build_index(self, appspec: AppSpec) -> None:
        """Build the (entity, event) → triggers lookup index."""
        for intent in appspec.llm_intents or []:
            for trigger in intent.triggers:
                key = (trigger.on_entity, trigger.on_event)
                self._index.setdefault(key, []).append(_TriggerEntry(intent.name, trigger))
        if self._index:
            logger.info(
                "LLM trigger matcher: %d triggers across %d entity/event combinations",
                sum(len(v) for v in self._index.values()),
                len(self._index),
            )

    def _map_inputs(self, input_map: dict[str, str], event: EntityEvent) -> dict[str, Any]:
        """Map entity event data to intent input_data using input_map.

        Supports:
        - "entity.field_name" → event.data[field_name]
        - "entity.id" → event.entity_id
        - literal strings (no dot prefix)
        """
        result: dict[str, Any] = {}
        data = event.data or {}
        for target_key, source_expr in input_map.items():
            if source_expr.startswith("entity."):
                field_name = source_expr[len("entity.") :]
                if field_name == "id":
                    result[target_key] = event.entity_id
                else:
                    result[target_key] = data.get(field_name)
            else:
                result[target_key] = source_expr
        return result

    def _evaluate_condition(self, when: str, event: EntityEvent) -> bool:
        """Evaluate a simple condition expression against entity data.

        Supports: "entity.field == value", "entity.field != value",
        "entity.field == null"
        """
        data = event.data or {}
        parts = when.split()
        if len(parts) != 3:
            logger.warning("Invalid trigger condition: %s", when)
            return True  # Default to firing if condition is malformed

        field_expr, op, value = parts

        # Resolve field value
        if field_expr.startswith("entity."):
            field_name = field_expr[len("entity.") :]
            field_val = data.get(field_name)
        else:
            field_val = field_expr

        # Resolve comparison value
        if value == "null":
            cmp_val = None
        else:
            cmp_val = value.strip("'\"")

        if op == "==":
            return field_val == cmp_val
        elif op == "!=":
            return field_val != cmp_val
        else:
            logger.warning("Unsupported condition operator: %s", op)
            return True

    def _make_write_back_callback(
        self, write_back: dict[str, str], entity_name: str, entity_id: str
    ) -> Any:
        """Create a callback that writes intent output back to entity fields."""
        services = self._services

        async def callback(result: ExecutionResult, job: LLMJob) -> None:
            if not result.success or not result.output:
                return

            # Parse output as JSON if possible, else treat as string
            import json

            try:
                output_data = json.loads(result.output)
            except (json.JSONDecodeError, TypeError):
                output_data = result.output

            # Build update payload from write_back mapping
            updates: dict[str, Any] = {}
            for target_expr, source_expr in write_back.items():
                # target_expr: "Entity.field" or just "field"
                if "." in target_expr:
                    _, field_name = target_expr.split(".", 1)
                else:
                    field_name = target_expr

                # source_expr: "output" or "output.subfield"
                if source_expr == "output":
                    updates[field_name] = output_data
                elif source_expr.startswith("output."):
                    subfield = source_expr[len("output.") :]
                    if isinstance(output_data, dict):
                        updates[field_name] = output_data.get(subfield)
                    else:
                        updates[field_name] = output_data

            if not updates:
                return

            # Write back via CRUD service
            service = services.get(entity_name)
            if service:
                try:
                    import asyncio

                    await asyncio.to_thread(
                        service.execute,
                        action="update",
                        record_id=entity_id,
                        data=updates,
                    )
                    logger.info(
                        "Write-back for %s/%s: %s",
                        entity_name,
                        entity_id,
                        list(updates.keys()),
                    )
                except Exception:
                    logger.exception(
                        "Write-back failed for %s/%s",
                        entity_name,
                        entity_id,
                    )

        return callback

    async def handle_event(self, event: EntityEvent) -> None:
        """Handle an entity event by checking for matching triggers."""
        trigger_event = _EVENT_MAP.get(event.event_type.value)
        if not trigger_event:
            return

        key = (event.entity_name, trigger_event)
        entries = self._index.get(key)
        if not entries:
            return

        for entry in entries:
            trigger = entry.trigger

            # Check condition
            if trigger.when and not self._evaluate_condition(trigger.when, event):
                continue

            # Map inputs
            input_data = self._map_inputs(trigger.input_map, event)

            # Build write-back callback
            callback = None
            if trigger.write_back:
                callback = self._make_write_back_callback(
                    trigger.write_back, event.entity_name, event.entity_id
                )

            # Submit to queue
            await self._queue.submit(
                entry.intent_name,
                input_data,
                user_id=event.user_id,
                entity_type=event.entity_name,
                entity_id=event.entity_id,
                callback=callback,
            )
            logger.info(
                "Triggered intent %s from %s.%s (entity %s)",
                entry.intent_name,
                event.entity_name,
                trigger_event.value,
                event.entity_id,
            )
