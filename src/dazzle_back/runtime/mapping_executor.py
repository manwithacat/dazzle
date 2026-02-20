"""Integration mapping executor (v0.30.0).

Executes declarative ``IntegrationMapping`` definitions against external APIs
when entity lifecycle events occur (create, update, delete, transition).

Data flow::

    Entity event → EntityEventBus → MappingExecutor.handle_event()
        → match triggers by entity_ref and event type
        → resolve base_url and auth from integration spec
        → interpolate URL template with entity fields
        → apply request_mapping (entity → request body)
        → check cache (ApiResponseCache, if available)
        → HTTP call via httpx (on cache miss)
        → cache response (for GET requests)
        → apply response_mapping (response → entity field updates)
        → handle errors per ErrorStrategy

Cache layer (optional, requires ``redis`` package and ``REDIS_URL``)::

    Uses :class:`~dazzle_back.runtime.api_cache.ApiResponseCache` for
    async Redis caching with scoped keys and dedup locking.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx

from dazzle.core.ir.integrations import (
    AuthType,
    ErrorAction,
    MappingTriggerType,
)
from dazzle_back.runtime.event_bus import EntityEvent, EntityEventType

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from dazzle.core.ir.integrations import (
        AuthSpec,
        ErrorStrategy,
        Expression,
        IntegrationMapping,
        IntegrationSpec,
        MappingRule,
    )
    from dazzle_back.runtime.api_cache import ApiResponseCache
    from dazzle_back.runtime.event_bus import EntityEventBus


# =============================================================================
# Data Types
# =============================================================================

# Pattern for {self.field_name} or {field_name} placeholders in URL templates
_URL_PLACEHOLDER = re.compile(r"\{(?:self\.)?(\w+)\}")

# Map event types to trigger types
_EVENT_TO_TRIGGER: dict[EntityEventType, MappingTriggerType] = {
    EntityEventType.CREATED: MappingTriggerType.ON_CREATE,
    EntityEventType.UPDATED: MappingTriggerType.ON_UPDATE,
    EntityEventType.DELETED: MappingTriggerType.ON_DELETE,
}

_MAX_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_BASE = 0.5  # seconds
_DEFAULT_CACHE_TTL = 86400  # 24 hours


@dataclass
class MappingResult:
    """Result of executing an integration mapping."""

    mapping_name: str
    integration_name: str
    success: bool
    status_code: int = 0
    response_data: dict[str, Any] = field(default_factory=dict)
    mapped_fields: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    cache_hit: bool = False


# =============================================================================
# Mapping Executor
# =============================================================================


class MappingExecutor:
    """Execute declarative integration mappings on entity events.

    Scans all integrations in the AppSpec for v0.30.0 ``IntegrationMapping``
    definitions and registers as a handler on the ``EntityEventBus``.

    Args:
        appspec: The application specification.
        event_bus: The entity event bus to register on.
        update_entity: Callback to persist entity field updates from
            response mappings. Signature: ``(entity_name, entity_id, fields) -> None``.
        cache: Optional :class:`~dazzle_back.runtime.api_cache.ApiResponseCache`.
            When provided, GET request responses are cached and dedup-locked.
            ``None`` (default) = no caching.
    """

    def __init__(
        self,
        appspec: Any,
        event_bus: EntityEventBus,
        *,
        update_entity: Any | None = None,
        cache: ApiResponseCache | None = None,
    ) -> None:
        self._appspec = appspec
        self._event_bus = event_bus
        self._update_entity = update_entity
        # Index: entity_name → list of (integration, mapping)
        self._mappings_by_entity: dict[str, list[tuple[IntegrationSpec, IntegrationMapping]]] = {}
        self._results: list[MappingResult] = []
        self._cache = cache
        self._pack_ttl_cache: dict[str, int | None] = {}  # integration:entity_ref → TTL

    @property
    def results(self) -> list[MappingResult]:
        """All execution results."""
        return list(self._results)

    def register_all(self) -> None:
        """Scan AppSpec integrations and register event handler."""
        for integration in getattr(self._appspec, "integrations", []):
            for mapping in getattr(integration, "mappings", []):
                if not mapping.triggers:
                    continue
                # Only register if there are non-MANUAL triggers
                has_auto_trigger = any(
                    t.trigger_type != MappingTriggerType.MANUAL for t in mapping.triggers
                )
                if has_auto_trigger:
                    entity = mapping.entity_ref
                    self._mappings_by_entity.setdefault(entity, []).append((integration, mapping))

        if self._mappings_by_entity:
            self._event_bus.add_handler(self.handle_event)
            entity_count = len(self._mappings_by_entity)
            mapping_count = sum(len(v) for v in self._mappings_by_entity.values())
            logger.info(
                "Mapping executor registered: %d mapping(s) across %d entity type(s)",
                mapping_count,
                entity_count,
            )

    async def handle_event(self, event: EntityEvent) -> None:
        """Handle an entity event by executing matching mappings."""
        pairs = self._mappings_by_entity.get(event.entity_name)
        if not pairs:
            return

        trigger_type = _EVENT_TO_TRIGGER.get(event.event_type)
        if trigger_type is None:
            return

        entity_data = event.data or {}

        for integration, mapping in pairs:
            for trigger in mapping.triggers:
                if trigger.trigger_type == trigger_type:
                    # Check transition state match
                    if trigger_type == MappingTriggerType.ON_UPDATE:
                        # ON_TRANSITION is a special case of ON_UPDATE
                        pass
                    if not self._evaluate_condition(trigger, entity_data):
                        continue
                    await self._execute_mapping(integration, mapping, entity_data, event)
                    break  # Only fire once per mapping per event
                elif (
                    trigger.trigger_type == MappingTriggerType.ON_TRANSITION
                    and event.event_type == EntityEventType.UPDATED
                ):
                    # Transition triggers fire on update events with state changes
                    if self._check_transition(trigger, entity_data):
                        await self._execute_mapping(integration, mapping, entity_data, event)
                        break

    async def execute_manual(
        self,
        integration_name: str,
        mapping_name: str,
        entity_data: dict[str, Any],
        *,
        entity_name: str | None = None,
        entity_id: str | None = None,
        force_refresh: bool = False,
    ) -> MappingResult:
        """Execute a manual mapping trigger.

        Args:
            integration_name: Name of the integration.
            mapping_name: Name of the mapping within the integration.
            entity_data: Current entity record data.
            entity_name: Entity type name (for write-back).
            entity_id: Entity record ID (for write-back).
            force_refresh: If True, bypass cache and call the API directly.

        Returns:
            MappingResult with execution details.

        Raises:
            ValueError: If the integration or mapping is not found.
        """
        for integration in getattr(self._appspec, "integrations", []):
            if integration.name != integration_name:
                continue
            for mapping in getattr(integration, "mappings", []):
                if mapping.name != mapping_name:
                    continue
                result = await self._execute_mapping(
                    integration, mapping, entity_data, force_refresh=force_refresh
                )
                # Write back mapped fields for manual triggers (including cache hits)
                if (
                    result.success
                    and result.mapped_fields
                    and self._update_entity
                    and entity_name
                    and entity_id
                ):
                    try:
                        await self._update_entity(entity_name, entity_id, result.mapped_fields)
                    except Exception as e:
                        logger.warning(
                            "Failed to update entity %s/%s: %s",
                            entity_name,
                            entity_id,
                            e,
                        )
                return result

        raise ValueError(f"Mapping '{mapping_name}' not found in integration '{integration_name}'")

    # =========================================================================
    # Internal Execution
    # =========================================================================

    async def _execute_mapping(
        self,
        integration: IntegrationSpec,
        mapping: IntegrationMapping,
        entity_data: dict[str, Any],
        event: EntityEvent | None = None,
        *,
        force_refresh: bool = False,
    ) -> MappingResult:
        """Execute a single mapping against an external API."""
        result = MappingResult(
            mapping_name=mapping.name,
            integration_name=integration.name,
            success=False,
        )

        # Resolve base URL
        base_url = self._resolve_base_url(integration)
        if not base_url:
            result.error = f"No base_url configured for integration '{integration.name}'"
            logger.warning(result.error)
            self._results.append(result)
            return result

        # Build request
        if mapping.request is None:
            result.error = f"No request spec for mapping '{mapping.name}'"
            self._results.append(result)
            return result

        url = self._interpolate_url(base_url, mapping.request.url_template, entity_data)
        method = mapping.request.method.value
        body = self._apply_request_mapping(mapping.request_mapping, entity_data)
        headers = self._resolve_auth_headers(integration)

        # Cache: only for GET requests (reads, not mutations)
        cache = self._cache
        scope = f"{integration.name}:{mapping.name}"
        is_cacheable = method == "GET" and cache is not None

        # Check cache before making HTTP call
        if is_cacheable and not force_refresh and cache is not None:
            cached = await cache.get(scope, url)
            if cached is not None:
                logger.info(
                    "Cache HIT for %s/%s → %s",
                    integration.name,
                    mapping.name,
                    url[:80],
                )
                result.success = True
                result.cache_hit = True
                result.response_data = cached
                if mapping.response_mapping:
                    result.mapped_fields = self._apply_response_mapping(
                        mapping.response_mapping, cached
                    )
                self._results.append(result)
                return result

        # Dedup lock: prevent duplicate in-flight calls to the same URL
        # force_refresh bypasses the lock
        if (
            is_cacheable
            and not force_refresh
            and cache is not None
            and not await cache.acquire_lock(scope, url)
        ):
            logger.info("Dedup lock active for %s, skipping", url[:80])
            result.error = "Duplicate request suppressed (in-flight)"
            self._results.append(result)
            return result

        # Determine retry behavior
        should_retry = (
            mapping.on_error is not None and ErrorAction.RETRY in mapping.on_error.actions
        )
        max_attempts = _MAX_RETRY_ATTEMPTS if should_retry else 1

        # Execute HTTP request with optional retry
        try:
            for attempt in range(max_attempts):
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        if method in ("POST", "PUT", "PATCH"):
                            resp = await client.request(method, url, json=body, headers=headers)
                        else:
                            resp = await client.request(method, url, headers=headers)

                    result.status_code = resp.status_code

                    try:
                        result.response_data = resp.json()
                    except Exception:
                        result.response_data = {"raw": resp.text[:1000]}

                    if 200 <= resp.status_code < 300:
                        result.success = True

                        # Cache successful GET responses
                        if is_cacheable and cache is not None:
                            cache_ttl = getattr(mapping, "cache_ttl", None)
                            if cache_ttl is None:
                                cache_ttl = self._lookup_pack_cache_ttl(integration, mapping)
                            cache_ttl = cache_ttl or _DEFAULT_CACHE_TTL
                            await cache.put(scope, url, result.response_data, ttl=cache_ttl)

                        # Apply response mapping
                        if mapping.response_mapping:
                            mapped = self._apply_response_mapping(
                                mapping.response_mapping, result.response_data
                            )
                            result.mapped_fields = mapped
                            if mapped and self._update_entity and event:
                                try:
                                    await self._update_entity(
                                        event.entity_name, event.entity_id, mapped
                                    )
                                except Exception as e:
                                    logger.warning(
                                        "Failed to update entity %s/%s: %s",
                                        event.entity_name,
                                        event.entity_id,
                                        e,
                                    )
                        break  # Success, no retry needed

                    # Non-2xx response
                    logger.warning(
                        "Mapping '%s' returned %d: %s",
                        mapping.name,
                        resp.status_code,
                        resp.text[:200],
                    )

                    if attempt < max_attempts - 1:
                        await asyncio.sleep(_RETRY_BACKOFF_BASE * (2**attempt))
                        continue

                except Exception as e:
                    result.error = str(e)
                    logger.warning("Mapping '%s' failed: %s", mapping.name, e)
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(_RETRY_BACKOFF_BASE * (2**attempt))
                        continue
        finally:
            # Always release dedup lock after the request completes
            if is_cacheable and cache is not None:
                await cache.release_lock(scope, url)

        # Handle error strategy if not successful
        if not result.success:
            await self._handle_error(mapping, result, entity_data, event)

        self._results.append(result)
        return result

    # =========================================================================
    # URL and Mapping Helpers
    # =========================================================================

    def _resolve_base_url(self, integration: IntegrationSpec) -> str:
        """Resolve the integration base URL.

        Supports:
        - Direct URL string from the DSL ``base_url: "https://..."``
        - Environment variable fallback: ``DAZZLE_API_{NAME}_URL``
        """
        if integration.base_url:
            return integration.base_url.rstrip("/")

        # Fallback to environment variable
        env_name = integration.name.upper().replace("-", "_").replace(".", "_")
        url = os.environ.get(f"DAZZLE_API_{env_name}_URL", "")
        return url.rstrip("/") if url else ""

    def _lookup_pack_cache_ttl(
        self,
        integration: IntegrationSpec,
        mapping: IntegrationMapping,
    ) -> int | None:
        """Look up cache_ttl from the API pack's foreign model definition.

        Uses integration's api_refs → first service's spec_inline → pack name,
        then finds the matching ForeignModelSpec by mapping.entity_ref.

        Results are cached per integration:entity_ref pair.
        """
        cache_key = f"{integration.name}:{mapping.entity_ref}"
        if cache_key in self._pack_ttl_cache:
            return self._pack_ttl_cache[cache_key]

        ttl: int | None = None
        try:
            # Extract pack name from integration's service references
            pack_name: str | None = None
            for svc in getattr(self._appspec, "services", []) or []:
                if svc.name in (integration.api_refs or []):
                    spec_inline = getattr(svc, "spec_inline", None) or ""
                    if spec_inline.startswith("pack:"):
                        pack_name = spec_inline.removeprefix("pack:")
                        break

            if pack_name:
                from dazzle.api_kb import load_pack

                pack = load_pack(pack_name)
                if pack:
                    for fm in pack.foreign_models:
                        if fm.name == mapping.entity_ref:
                            ttl = fm.cache_ttl
                            break
        except Exception:
            logger.debug(
                "Failed to look up pack cache_ttl for %s:%s",
                integration.name,
                mapping.entity_ref,
            )

        self._pack_ttl_cache[cache_key] = ttl
        return ttl

    def _interpolate_url(
        self, base_url: str, url_template: str, entity_data: dict[str, Any]
    ) -> str:
        """Resolve {self.field} or {field} placeholders in a URL template."""

        def replace_match(m: re.Match[str]) -> str:
            field_name = m.group(1)
            value = entity_data.get(field_name, "")
            return str(value) if value is not None else ""

        path = _URL_PLACEHOLDER.sub(replace_match, url_template)
        return f"{base_url}{path}"

    def _apply_request_mapping(
        self,
        rules: list[MappingRule],
        entity_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply request mapping rules: entity fields → request body."""
        context = {"self": entity_data}
        result: dict[str, Any] = {}
        for rule in rules:
            value = self._evaluate_expression(rule.source, context)
            # Support dotted target fields (e.g., fixedInfo.firstName)
            self._set_nested_value(result, rule.target_field, value)
        return result

    def _apply_response_mapping(
        self,
        rules: list[MappingRule],
        response_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply response mapping rules: response → entity fields."""
        context = {"response": response_data}
        result: dict[str, Any] = {}
        for rule in rules:
            value = self._evaluate_expression(rule.source, context)
            result[rule.target_field] = value
        return result

    def _evaluate_expression(self, expr: Expression, context: dict[str, Any]) -> Any:
        """Evaluate a mapping expression against a context dict."""
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

    @staticmethod
    def _set_nested_value(d: dict[str, Any], key: str, value: Any) -> None:
        """Set a value in a nested dict using dotted key path."""
        parts = key.split(".")
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = value

    # =========================================================================
    # Auth Resolution
    # =========================================================================

    def _resolve_auth_headers(self, integration: IntegrationSpec) -> dict[str, str]:
        """Resolve auth credentials to HTTP headers."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        auth: AuthSpec | None = getattr(integration, "auth", None)
        if auth is None:
            return headers

        # Resolve credentials from environment variables
        cred_values = [os.environ.get(c, "") for c in auth.credentials]

        if auth.auth_type == AuthType.API_KEY:
            if cred_values:
                headers["Authorization"] = f"Token {cred_values[0]}"
        elif auth.auth_type == AuthType.BEARER:
            if cred_values:
                headers["Authorization"] = f"Bearer {cred_values[0]}"
        elif auth.auth_type == AuthType.BASIC:
            import base64

            if len(cred_values) >= 2:
                encoded = base64.b64encode(f"{cred_values[0]}:{cred_values[1]}".encode()).decode()
            elif cred_values:
                # Single credential = API key as username, empty password (e.g. Companies House)
                encoded = base64.b64encode(f"{cred_values[0]}:".encode()).decode()
            else:
                encoded = None
            if encoded:
                headers["Authorization"] = f"Basic {encoded}"
        elif auth.auth_type == AuthType.OAUTH2:
            if cred_values:
                headers["Authorization"] = f"Bearer {cred_values[0]}"

        return headers

    # =========================================================================
    # Condition and Transition Evaluation
    # =========================================================================

    def _evaluate_condition(
        self,
        trigger: Any,
        entity_data: dict[str, Any],
    ) -> bool:
        """Evaluate a trigger's condition expression against entity data."""
        if trigger.condition_expr is None:
            return True

        # Simple evaluation: support field != null and field == value
        try:
            from dazzle.core.ir.expressions import BinaryExpr, BinaryOp

            expr = trigger.condition_expr
            if isinstance(expr, BinaryExpr):
                left_val = self._resolve_expr_value(expr.left, entity_data)
                right_val = self._resolve_expr_value(expr.right, entity_data)

                if expr.op == BinaryOp.NE:
                    return bool(left_val != right_val)
                elif expr.op == BinaryOp.EQ:
                    return bool(left_val == right_val)
                elif expr.op == BinaryOp.GT:
                    return left_val is not None and right_val is not None and left_val > right_val
                elif expr.op == BinaryOp.LT:
                    return left_val is not None and right_val is not None and left_val < right_val
        except Exception as e:
            logger.debug("Condition evaluation failed: %s", e)

        return True  # Default to matching if evaluation fails

    def _resolve_expr_value(self, node: Any, entity_data: dict[str, Any]) -> Any:
        """Resolve an expression AST node to a value."""
        from dazzle.core.ir.expressions import FieldRef, Literal

        if isinstance(node, Literal):
            return node.value
        elif isinstance(node, FieldRef):
            current: Any = entity_data
            for part in node.path:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    current = getattr(current, part, None)
                if current is None:
                    return None
            return current
        return None

    def _check_transition(
        self,
        trigger: Any,
        entity_data: dict[str, Any],
    ) -> bool:
        """Check if entity data matches an on_transition trigger.

        Looks for ``_previous_state`` and ``status`` fields in entity data
        to determine if a state transition occurred.
        """
        if trigger.from_state is None and trigger.to_state is None:
            return True

        prev = entity_data.get("_previous_state") or entity_data.get("_old_status")
        current = entity_data.get("status") or entity_data.get("state")

        if trigger.from_state and prev != trigger.from_state:
            return False
        if trigger.to_state and current != trigger.to_state:
            return False
        return True

    # =========================================================================
    # Error Handling
    # =========================================================================

    async def _handle_error(
        self,
        mapping: IntegrationMapping,
        result: MappingResult,
        entity_data: dict[str, Any],
        event: EntityEvent | None = None,
    ) -> None:
        """Apply error strategy actions."""
        strategy: ErrorStrategy | None = mapping.on_error
        if strategy is None:
            return

        for action in strategy.actions:
            if action == ErrorAction.LOG_WARNING:
                logger.warning(
                    "Integration mapping '%s' failed: status=%s error=%s",
                    mapping.name,
                    result.status_code,
                    result.error,
                )
            elif action == ErrorAction.IGNORE:
                pass  # Silently continue
            elif action == ErrorAction.REVERT_TRANSITION:
                if event and self._update_entity:
                    prev_state = entity_data.get("_previous_state")
                    if prev_state:
                        try:
                            await self._update_entity(
                                event.entity_name,
                                event.entity_id,
                                {"status": prev_state},
                            )
                            logger.info(
                                "Reverted %s/%s state to '%s'",
                                event.entity_name,
                                event.entity_id,
                                prev_state,
                            )
                        except Exception as e:
                            logger.error("Failed to revert transition: %s", e)
            elif action == ErrorAction.RETRY:
                pass  # Retry already handled in _execute_mapping

        # Apply set_fields overrides
        if strategy.set_fields and event and self._update_entity:
            try:
                await self._update_entity(
                    event.entity_name,
                    event.entity_id,
                    dict(strategy.set_fields),
                )
            except Exception as e:
                logger.warning("Failed to set error fields: %s", e)
