"""
Side-effect executor for process step effects.

Executes create/update actions declared in process step `effects:` blocks.
Each effect calls the target entity's CRUDService, which naturally fires
downstream lifecycle events (process triggers, channel sends, etc.).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from dazzle.core.ir.process import EffectAction, FieldAssignment, StepEffect

logger = logging.getLogger(__name__)


@dataclass
class EffectResult:
    """Result of a single side-effect execution."""

    action: str
    entity_name: str
    entity_id: str | None = None
    success: bool = True
    error: str | None = None
    affected_count: int = 0


@dataclass
class EffectContext:
    """Context available during effect expression resolution."""

    trigger_entity: dict[str, Any] = field(default_factory=dict)
    process_inputs: dict[str, Any] = field(default_factory=dict)
    step_outputs: dict[str, Any] = field(default_factory=dict)


class SideEffectExecutor:
    """Executes side-effect actions declared on process steps.

    Effects run after a step succeeds and before the next step starts.
    Each effect calls the target entity's CRUDService for create/update,
    which ensures downstream triggers and callbacks fire normally.
    """

    def __init__(
        self,
        services: dict[str, Any],
        repositories: dict[str, Any] | None = None,
    ) -> None:
        self._services = services
        self._repositories = repositories or {}

    async def execute_effects(
        self,
        effects: list[StepEffect],
        context: EffectContext,
    ) -> list[EffectResult]:
        """Execute a list of step effects, returning results for each."""
        results: list[EffectResult] = []
        for effect in effects:
            try:
                result = await self._execute_one(effect, context)
                results.append(result)
            except Exception as e:
                logger.error(
                    "Effect %s %s failed: %s",
                    effect.action.value,
                    effect.entity_name,
                    e,
                )
                results.append(
                    EffectResult(
                        action=effect.action.value,
                        entity_name=effect.entity_name,
                        success=False,
                        error=str(e),
                    )
                )
        return results

    async def _execute_one(
        self,
        effect: StepEffect,
        context: EffectContext,
    ) -> EffectResult:
        """Execute a single effect."""
        service = self._services.get(effect.entity_name)
        if not service:
            return EffectResult(
                action=effect.action.value,
                entity_name=effect.entity_name,
                success=False,
                error=f"No service found for entity '{effect.entity_name}'",
            )

        if effect.action == EffectAction.CREATE:
            return await self._execute_create(effect, context, service)
        elif effect.action == EffectAction.UPDATE:
            return await self._execute_update(effect, context, service)
        else:
            return EffectResult(
                action=effect.action.value,
                entity_name=effect.entity_name,
                success=False,
                error=f"Unknown effect action: {effect.action}",
            )

    async def _execute_create(
        self,
        effect: StepEffect,
        context: EffectContext,
        service: Any,
    ) -> EffectResult:
        """Execute a create effect."""
        data = self._resolve_assignments(effect.assignments, context)

        # Build a create schema instance from the data
        create_schema = service.create_schema
        create_data = create_schema(**data)
        entity = await service.create(create_data)

        entity_id = str(getattr(entity, "id", None) or data.get("id", ""))

        logger.info(
            "Effect: created %s (id=%s)",
            effect.entity_name,
            entity_id,
        )

        return EffectResult(
            action="create",
            entity_name=effect.entity_name,
            entity_id=entity_id,
            affected_count=1,
        )

    async def _execute_update(
        self,
        effect: StepEffect,
        context: EffectContext,
        service: Any,
    ) -> EffectResult:
        """Execute an update effect."""
        data = self._resolve_assignments(effect.assignments, context)
        target_ids = await self._resolve_where(effect, context, service)

        if not target_ids:
            logger.warning(
                "Effect: update %s matched no records (where=%s)",
                effect.entity_name,
                effect.where,
            )
            return EffectResult(
                action="update",
                entity_name=effect.entity_name,
                affected_count=0,
            )

        update_schema = service.update_schema
        count = 0
        for entity_id in target_ids:
            update_data = update_schema(**data)
            result = await service.update(UUID(str(entity_id)), update_data)
            if result is not None:
                count += 1

        logger.info(
            "Effect: updated %d %s record(s)",
            count,
            effect.entity_name,
        )

        return EffectResult(
            action="update",
            entity_name=effect.entity_name,
            affected_count=count,
        )

    async def _resolve_where(
        self,
        effect: StepEffect,
        context: EffectContext,
        service: Any,
    ) -> list[str]:
        """Resolve a where clause to a list of entity IDs."""
        if not effect.where:
            return []

        # Parse simple "field = value" where clause
        parts = effect.where.split("=", 1)
        if len(parts) != 2:
            logger.warning("Cannot parse where clause: %s", effect.where)
            return []

        field_name = parts[0].strip()
        raw_value = parts[1].strip()
        resolved_value = self._resolve_value(raw_value, context)

        # Use service.list with filter to find matching records
        result = await service.list(
            page=1,
            page_size=1000,
            filters={field_name: resolved_value},
        )

        ids: list[str] = []
        items = result.get("items", []) if isinstance(result, dict) else []
        for item in items:
            if isinstance(item, dict):
                item_id = item.get("id")
            else:
                item_id = getattr(item, "id", None)
            if item_id is not None:
                ids.append(str(item_id))

        return ids

    def _resolve_assignments(
        self,
        assignments: list[FieldAssignment],
        context: EffectContext,
    ) -> dict[str, Any]:
        """Resolve field assignments to a data dict."""
        data: dict[str, Any] = {}
        for assignment in assignments:
            # Extract field name (strip entity prefix if present, e.g. "Task.title" -> "title")
            field_path = assignment.field_path
            if "." in field_path:
                field_name = field_path.split(".", 1)[1]
            else:
                field_name = field_path

            data[field_name] = self._resolve_value(assignment.value, context)
        return data

    def _resolve_value(self, value_expr: str, context: EffectContext) -> Any:
        """Resolve a value expression to a concrete value.

        Supports:
        - String literals: "some text"
        - self.field: references trigger entity data
        - now(): current UTC datetime
        - current_user(): placeholder for current user
        - Bare identifiers: treated as string literals
        """
        expr = value_expr.strip()

        # String literal
        if (expr.startswith('"') and expr.endswith('"')) or (
            expr.startswith("'") and expr.endswith("'")
        ):
            return expr[1:-1]

        # self.field reference
        if expr.startswith("self."):
            field_name = expr[5:]
            return context.trigger_entity.get(field_name)

        # Built-in functions
        if expr == "now()":
            return datetime.now(UTC)

        if expr == "current_user()":
            return context.process_inputs.get("current_user", "system")

        # Boolean literals
        if expr.lower() == "true":
            return True
        if expr.lower() == "false":
            return False

        # Numeric literal
        try:
            if "." in expr:
                return float(expr)
            return int(expr)
        except ValueError:
            pass

        # Treat as string literal
        return expr
