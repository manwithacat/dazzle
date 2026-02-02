"""Integration action executor (v0.20.0).

Executes ``IntegrationAction`` definitions from the DSL against external APIs
when a surface form is submitted.

Data flow::

    Surface submit → post-submit hook → IntegrationExecutor.execute_action()
        → resolve service config from env vars
        → evaluate call_mapping (form/entity data → request params)
        → HTTP call via httpx
        → evaluate response_mapping (response → entity fields)
        → return ActionResult
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from dazzle.core.ir.integrations import Expression, IntegrationAction, MappingRule


# =============================================================================
# Data Types
# =============================================================================


@dataclass
class ServiceConfig:
    """Resolved external service configuration."""

    base_url: str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class ActionResult:
    """Result of executing an integration action."""

    success: bool
    status_code: int = 0
    response_data: dict[str, Any] = field(default_factory=dict)
    mapped_fields: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


# =============================================================================
# Integration Executor
# =============================================================================


class IntegrationExecutor:
    """Execute integration actions against external APIs.

    Initialized with the ``AppSpec`` and optional pre-built ``fragment_sources``.
    Provides methods to resolve services, evaluate expressions/mappings, and
    make HTTP calls.
    """

    def __init__(
        self,
        app_spec: Any | None = None,
        fragment_sources: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._app_spec = app_spec
        self._fragment_sources = fragment_sources or {}
        # Build a lookup of integration actions by surface name
        self._actions_by_surface: dict[str, list[IntegrationAction]] = {}
        if app_spec:
            for integration in getattr(app_spec, "integrations", []):
                for action in getattr(integration, "actions", []):
                    surface = action.when_surface
                    self._actions_by_surface.setdefault(surface, []).append(action)

    def get_actions_for_surface(self, surface_name: str) -> list[IntegrationAction]:
        """Return integration actions triggered by the given surface."""
        return self._actions_by_surface.get(surface_name, [])

    def resolve_service(self, api_ref: str) -> ServiceConfig:
        """Resolve a service reference to base_url and headers.

        Looks up environment variables::

            DAZZLE_API_{NAME}_URL   → base URL
            DAZZLE_API_{NAME}_KEY   → Bearer token (optional)

        Falls back to ``fragment_sources`` config.
        """
        env_name = api_ref.upper().replace("-", "_").replace(".", "_")
        base_url = os.environ.get(f"DAZZLE_API_{env_name}_URL", "")
        api_key = os.environ.get(f"DAZZLE_API_{env_name}_KEY", "")

        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Fall back to fragment_sources
        if not base_url:
            source_config = self._fragment_sources.get(api_ref, {})
            base_url = source_config.get("url", "")
            headers.update(source_config.get("headers", {}))

        return ServiceConfig(base_url=base_url, headers=headers)

    def evaluate_expression(self, expr: Expression, context: dict[str, Any]) -> Any:
        """Resolve a single Expression against the provided context.

        Supports:
        - ``expr.literal`` → returns the literal value directly
        - ``expr.path`` → dotted path resolution (``form.field``, ``entity.field``)
        """
        if expr.literal is not None:
            return expr.literal

        if expr.path:
            parts = expr.path.split(".")
            current: Any = context
            for part in parts:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    current = getattr(current, part, None)
                if current is None:
                    return None
            return current

        return None

    def apply_mapping(
        self,
        rules: list[MappingRule],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply a list of mapping rules to produce a flat dict.

        Each rule maps ``rule.source`` (an Expression) → ``rule.target_field``.
        """
        result: dict[str, Any] = {}
        for rule in rules:
            value = self.evaluate_expression(rule.source, context)
            result[rule.target_field] = value
        return result

    async def execute_action(
        self,
        action: IntegrationAction,
        form_data: dict[str, Any],
        entity_data: dict[str, Any] | None = None,
    ) -> ActionResult:
        """Execute an integration action.

        Args:
            action: The IntegrationAction definition from the DSL.
            form_data: Data submitted from the surface form.
            entity_data: Existing entity record (for edit surfaces).

        Returns:
            ActionResult with success status, response data, and mapped fields.
        """
        # Build evaluation context
        context: dict[str, Any] = {
            "form": form_data,
            "entity": entity_data or {},
        }

        # Resolve service
        service = self.resolve_service(action.call_service)
        if not service.base_url:
            return ActionResult(
                success=False,
                error=f"No URL configured for service '{action.call_service}'. "
                f"Set DAZZLE_API_{action.call_service.upper().replace('-', '_')}_URL",
            )

        # Evaluate call mapping
        call_params = self.apply_mapping(action.call_mapping, context)

        # Make HTTP call
        try:
            import httpx

            url = f"{service.base_url.rstrip('/')}/{action.call_operation}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    json=call_params,
                    headers=service.headers,
                )

            response_data: dict[str, Any] = {}
            try:
                response_data = resp.json()
            except Exception:
                response_data = {"raw": resp.text}

            # Evaluate response mapping
            mapped_fields: dict[str, Any] = {}
            if action.response_mapping:
                resp_context = {**context, "response": response_data}
                mapped_fields = self.apply_mapping(action.response_mapping, resp_context)

            success = 200 <= resp.status_code < 300

            if not success:
                logger.warning(
                    f"Integration action '{action.name}' returned {resp.status_code}: "
                    f"{resp.text[:200]}"
                )

            return ActionResult(
                success=success,
                status_code=resp.status_code,
                response_data=response_data,
                mapped_fields=mapped_fields,
            )

        except Exception as e:
            logger.error(f"Integration action '{action.name}' failed: {e}")
            return ActionResult(success=False, error=str(e))


# TODO: sync scheduler — extend IntegrationExecutor with cron/event-driven
# IntegrationSync execution. This would:
# 1. Read IntegrationSync definitions from AppSpec
# 2. Schedule periodic fetches (SyncMode.SCHEDULED)
# 3. Register event handlers (SyncMode.EVENT_DRIVEN)
# 4. Apply match_rules to reconcile foreign records with local entities
