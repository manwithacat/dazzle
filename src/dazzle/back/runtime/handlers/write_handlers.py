"""Create/update/delete/custom handler factory family for generated routes.

Extracted verbatim from ``route_generator.py`` (#1361 final slice). This is
the WRITE family: ``create_create_handler`` (storage-key verification,
idempotency-key injection, ``ref User`` + persona-backed-ref auto-injection,
scope: create: enforcement, #1311), ``create_update_handler`` (scope:
update: destination revalidation, #1312), ``create_delete_handler``
(soft-delete tombstoning, #1218 Option A), ``create_custom_handler``, the
ref-injection helpers (``resolve_backed_entity_refs``,
``inject_current_user_refs``), and ``_parse_request_body`` (used only by
this family — JSON/form body parsing with empty-string→None coercion).

A leaf module by design: it must not import ``route_generator`` at module
level (``route_generator`` imports these names back at module level so the
``route_generator.<name>`` call sites, importers, and patch points keep
resolving there). The shared route-dispatch surface it needs (``RouteSpec``,
``_extract_result_id``, ``_htmx_current_url``, ``_htmx_parent_url``,
``_set_handler_annotations``) comes from the ``route_support`` leaf at top
level — extracted there in the 2026-06-20 smells round to break the import
cycle that previously forced lazy in-function imports.

Deliberately NOT named ``*_routes.py`` — the runtime-urls api-surface walker
globs that pattern and this module defines no routes.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request
from pydantic import BaseModel

from dazzle.back.runtime.audit_wrap import _wrap_with_auth
from dazzle.back.runtime.htmx_render import _with_htmx_triggers
from dazzle.back.runtime.http_errors import require_found
from dazzle.back.runtime.repository import ConstraintViolationError

# Shared CRUD route-dispatch surface — from the route_support LEAF (smells round
# 2026-06-20). Was lazily imported from route_generator to dodge an import cycle;
# route_support is a leaf, so these are now plain top-level imports.
from dazzle.back.runtime.route_support import (
    RouteSpec,
    _extract_result_id,
    _htmx_current_url,
    _htmx_parent_url,
    _set_handler_annotations,
)
from dazzle.back.runtime.scope_filters import _enforce_create_scope, _enforce_update_scope


async def _parse_request_body(request: Any) -> dict[str, Any]:
    """Parse request body as JSON or form data.

    HTMX forms send JSON when the json-enc extension is loaded, but
    fall back to form-urlencoded otherwise.  Accept both so the API
    works regardless of client encoding.

    Empty string values are converted to None so that optional fields
    (e.g. ref/UUID fields) pass Pydantic validation.
    """
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        body = dict(form)
    else:
        # Default: JSON (covers application/json and missing header)
        body = await request.json()
    # Convert empty strings to None for optional field validation
    return {k: (None if v == "" else v) for k, v in body.items()}


async def resolve_backed_entity_refs(
    body: dict[str, Any],
    input_schema: type[BaseModel],
    persona_ref_map: dict[str, tuple[str, str, Any]] | None,
    user_roles: list[str],
    current_user: str | None,
    user_email: str | None,
) -> None:
    """Auto-inject persona-backed entity refs into missing form fields.

    Cycle 249 (closes EX-049). When a ``ref Tester`` field is missing
    from the request body AND the current user's role is ``tester``
    AND persona ``tester`` declares ``backed_by: Tester``, this
    helper looks up the Tester row via the ``link_via`` field and
    injects the Tester's ID.

    Args:
        body: Parsed request body dict (mutated in place).
        input_schema: Pydantic schema for required-field detection.
        persona_ref_map: Maps ``fk_field_name`` →
            ``(target_entity, link_via, repository)`` for each ref
            field that targets a persona-backed entity. Built at
            route-registration time from ``entity_ref_targets`` +
            the appspec's ``backed_by`` declarations.
        user_roles: The current user's roles (with or without
            ``role_`` prefix).
        current_user: Auth user id string (used for ``link_via: id``).
        user_email: Auth user email (used for ``link_via: email``).
    """
    if not persona_ref_map or not user_roles:
        return

    for fk_field, (target_entity, link_via, repo) in persona_ref_map.items():
        # Skip if the body already has a value for this field
        existing = body.get(fk_field)
        if existing is not None:
            continue

        # Skip if the field isn't required on the schema
        field_info = input_schema.model_fields.get(fk_field)
        if field_info is None or not field_info.is_required():
            continue

        # Resolve the lookup value based on link_via
        if link_via == "id" and current_user:
            # Convention: auth user ID == entity ID (zero-cost, no DB lookup)
            body[fk_field] = current_user
        elif link_via == "email" and user_email and repo:
            # DB lookup: find the entity row where email matches
            try:
                result = await repo.get_one(filters={link_via: user_email})
                if result:
                    entity_id = getattr(result, "id", None) or (
                        result.get("id") if isinstance(result, dict) else None
                    )
                    if entity_id:
                        body[fk_field] = str(entity_id)
            except Exception:
                import logging

                logging.getLogger(__name__).debug(
                    "backed_by lookup failed for %s.%s=%s",
                    target_entity,
                    link_via,
                    user_email,
                    exc_info=True,
                )
        elif user_email and repo:
            # Generic link_via field — DB lookup
            try:
                result = await repo.get_one(filters={link_via: user_email})
                if result:
                    entity_id = getattr(result, "id", None) or (
                        result.get("id") if isinstance(result, dict) else None
                    )
                    if entity_id:
                        body[fk_field] = str(entity_id)
            except Exception:
                import logging

                logging.getLogger(__name__).debug(
                    "backed_by lookup failed for %s.%s=%s",
                    target_entity,
                    link_via,
                    user_email,
                    exc_info=True,
                )


def inject_current_user_refs(
    body: dict[str, Any],
    input_schema: type[BaseModel],
    user_ref_fields: list[str] | None,
    current_user: str | None,
) -> None:
    """Auto-inject ``current_user`` into missing required ``ref User`` fields.

    Mutates ``body`` in place. Rules (all must hold for a field to be injected):

    1. ``current_user`` is non-empty (we know who to inject)
    2. ``user_ref_fields`` is non-empty (caller has identified ref-User fields)
    3. The field exists on ``input_schema.model_fields``
    4. The field is declared required on the schema (no default, not Optional)
    5. The body either does NOT contain the field OR contains ``None`` for it

    Closes manwithacat/dazzle#774. Before this helper existed, create surfaces that
    omitted ``created_by`` (or similar ``ref User required`` fields) from
    their DSL section would produce a pydantic ``Field required`` error on
    a field the user was never shown. The helper closes the gap by letting
    the framework supply ``current_user`` for any ref-User field the DSL
    author left out, without silently overriding explicit values.

    Args:
        body: Parsed request body dict (mutated in place)
        input_schema: The pydantic schema the handler will ``model_validate``
            against. Used to detect required fields.
        user_ref_fields: Names of fields on this entity whose ``ref_entity``
            is "User". Typically computed from the entity's
            ``entity_ref_targets`` at route-registration time.
        current_user: String representation of the current user's id.
    """
    if not current_user or not user_ref_fields:
        return
    for fname in user_ref_fields:
        existing = body.get(fname)
        if existing is not None:
            continue
        field_info = input_schema.model_fields.get(fname)
        if field_info is None:
            continue
        if not field_info.is_required():
            continue
        body[fname] = current_user


def create_create_handler(
    spec: "RouteSpec",
    *,
    entity_slug: str = "",
    user_ref_fields: list[str] | None = None,
    persona_ref_map: dict[str, tuple[str, str, Any]] | None = None,
) -> Callable[..., Any]:
    """Create a handler for create operations with optional Cedar-style access control.

    See :class:`RouteSpec` for the per-route contract (#1011).
    ``spec.input_schema`` is required for create handlers.

    Args:
        user_ref_fields: Names of fields on this entity that are ``ref User``
            foreign keys. When the request body omits any of these (because
            the DSL create surface didn't expose them — e.g. ``created_by``),
            the handler auto-injects ``current_user`` before schema
            validation, provided the field is declared required in the
            Pydantic input schema. See ``inject_current_user_refs``.
            Closes manwithacat/dazzle#774.
        persona_ref_map: Maps ``fk_field_name`` →
            ``(target_entity, link_via, repository)`` for each ref
            field that targets a persona-backed entity. Cycle 249
            (closes EX-049). See ``resolve_backed_entity_refs``.
    """

    service = spec.service
    if spec.input_schema is None:
        raise ValueError("create_create_handler requires spec.input_schema")
    input_schema = spec.input_schema
    storage_bindings = spec.storage_bindings
    auth_dep = spec.handler.auth_dep
    optional_auth_dep = spec.handler.optional_auth_dep
    require_auth_by_default = spec.handler.require_auth_by_default
    entity_name = spec.handler.entity_name
    audit_logger = spec.handler.audit_logger
    cedar_access_spec = spec.handler.cedar_access_spec

    def _build_redirect_url(result: Any) -> str | None:
        if not entity_slug:
            return None
        result_id = _extract_result_id(result)
        if result_id:
            return f"/app/{entity_slug}/{result_id}"
        return None

    async def _core(
        _id: Any,
        request: Request,
        *,
        current_user: str | None = None,
        existing: Any = None,
        **_extra: Any,
    ) -> Any:
        body = await _parse_request_body(request)

        # #932 cycle 4: verify any storage-bound s3_key in the body
        # against the caller's prefix sandbox + object existence. Runs
        # BEFORE Pydantic validation so an invalid key short-circuits
        # the create with the right 4xx/5xx and a precise message
        # rather than silently persisting an unverified key.
        if storage_bindings:
            from dazzle.back.runtime.storage import (
                StorageVerificationError,
                verify_storage_field_keys,
            )

            registry = getattr(request.app.state, "storage_registry", None)
            try:
                verify_storage_field_keys(body, storage_bindings, registry, current_user)
            except StorageVerificationError as exc:
                raise HTTPException(
                    status_code=exc.status_code,
                    detail={
                        "error": "storage_verification_failed",
                        "field": exc.field,
                        "storage": exc.storage,
                        "reason": exc.reason,
                    },
                ) from exc

        # Inject idempotency key from header if present (#693)
        idem_key = request.headers.get("x-idempotency-key")
        if idem_key and "idempotency_key" not in body:
            body["idempotency_key"] = idem_key

        # Auto-inject current_user for missing required `ref User` fields
        # (manwithacat/dazzle#774). See inject_current_user_refs for the full rule set.
        inject_current_user_refs(body, input_schema, user_ref_fields, current_user)

        # Auto-inject persona-backed entity refs for missing required fields
        # (cycle 249, closes EX-049). See resolve_backed_entity_refs for
        # the full rule set. Uses user_email from the auth context to do
        # an async DB lookup when link_via != "id".
        _user_email = _extra.get("user_email")
        _user_roles = _extra.get("user_roles", [])
        if persona_ref_map:
            await resolve_backed_entity_refs(
                body,
                input_schema,
                persona_ref_map,
                _user_roles or [],
                current_user,
                _user_email,
            )

        data = input_schema.model_validate(body)

        # #1124 / #1311: scope: create: enforcement. Predicate is
        # evaluated AFTER current_user / persona-backed-ref injection
        # (so `created_by = current_user as: member` evaluates against
        # the resolved payload) but BEFORE service.execute, so a
        # predicate rejection 403s before the insert. Simple leaves
        # (ColumnCheck, UserAttrCheck, PathCheck depth 1, BoolComposite)
        # evaluate in-Python against the payload; FK-path (depth > 1) and
        # EXISTS leaves resolve via a payload-time SQL probe on the
        # entity's repository (ADR-0028). See docs/reference/rbac-scope.md.
        _scope_user_roles = list(_extra.get("user_roles") or [])
        # `mode="json"` so UUID / datetime payload fields are normalised to
        # their string form. The create-scope walker compares them against
        # `current_user.<attr>` values, which `_resolve_user_attribute`
        # always returns as `str` — a bare `model_dump()` would leave a
        # `ref` field as a `UUID` object, and `UUID(...) == "..."` is always
        # False, so an own-org create would 403 on a pure type mismatch (#1174).
        _enforce_create_scope(
            cedar_access_spec=cedar_access_spec,
            payload=data.model_dump(mode="json"),
            user_id=current_user,
            user_roles=_scope_user_roles,
            entity_name=entity_name,
            auth_context=_extra.get("auth_context"),
            service=service,
            fk_graph=spec.handler.fk_graph,
        )

        # Handle idempotent duplicate: unique constraint on idempotency_key
        # returns a 200 instead of the normal 422 constraint error.
        try:
            result = await service.execute(operation="create", data=data)
        except ConstraintViolationError as exc:
            if idem_key and exc.field == "idempotency_key":
                return {"status": "duplicate", "message": "Already submitted"}
            raise

        return _with_htmx_triggers(
            request, result, entity_name, "created", redirect_url=_build_redirect_url(result)
        )

    return _wrap_with_auth(
        _core,
        service=service,
        cedar_access_spec=cedar_access_spec,
        auth_dep=auth_dep,
        optional_auth_dep=optional_auth_dep,
        require_auth_by_default=require_auth_by_default,
        operation="create",
        entity_name=entity_name,
        audit_logger=audit_logger,
    )


def create_update_handler(spec: "RouteSpec") -> Callable[..., Any]:
    """Create a handler for update operations with optional Cedar-style access control.

    See :class:`RouteSpec` for the per-route contract (#1011).
    ``spec.input_schema`` is required for update handlers.
    """

    service = spec.service
    if spec.input_schema is None:
        raise ValueError("create_update_handler requires spec.input_schema")
    input_schema = spec.input_schema
    storage_bindings = spec.storage_bindings
    include_field_changes = spec.include_field_changes
    auth_dep = spec.handler.auth_dep
    optional_auth_dep = spec.handler.optional_auth_dep
    require_auth_by_default = spec.handler.require_auth_by_default
    entity_name = spec.handler.entity_name
    audit_logger = spec.handler.audit_logger
    cedar_access_spec = spec.handler.cedar_access_spec

    async def _core(
        id: UUID,
        request: Request,
        *,
        current_user: str | None = None,
        existing: Any = None,
        user_roles: list[str] | None = None,
        is_superuser: bool = False,
        **_extra: Any,
    ) -> Any:
        body = await _parse_request_body(request)

        # #932 cycle 4: same verification gate as the create path —
        # an update that swaps in a new s3_key must satisfy the
        # caller's prefix sandbox + object existence. Body fields not
        # present (or null) are skipped: an update that doesn't touch
        # the file column re-uses the previously-stored key.
        if storage_bindings:
            from dazzle.back.runtime.storage import (
                StorageVerificationError,
                verify_storage_field_keys,
            )

            registry = getattr(request.app.state, "storage_registry", None)
            try:
                verify_storage_field_keys(body, storage_bindings, registry, current_user)
            except StorageVerificationError as exc:
                raise HTTPException(
                    status_code=exc.status_code,
                    detail={
                        "error": "storage_verification_failed",
                        "field": exc.field,
                        "storage": exc.storage,
                        "reason": exc.reason,
                    },
                ) from exc

        data = input_schema.model_validate(body)

        # #1312 (ADR-0028): scope: update: DESTINATION enforcement. The
        # pre-read validated the source row; this re-validates the row's
        # would-be-final state (existing ⊕ changed fields) so an update can't
        # repoint an FK to move the row INTO a foreign scope. Runs BEFORE the
        # write; 404 on denial (IDOR-avoidance, matching the pre-read). Uses
        # `exclude_unset` so untouched scope-key columns keep their existing
        # (already-validated) value rather than being treated as nulled.
        _enforce_update_scope(
            cedar_access_spec=cedar_access_spec,
            existing=existing,
            new_values=data.model_dump(mode="json", exclude_unset=True),
            user_id=current_user,
            user_roles=list(user_roles or []),
            entity_name=entity_name,
            auth_context=_extra.get("auth_context"),
            service=service,
            fk_graph=spec.handler.fk_graph,
        )

        kwargs: dict[str, Any] = {"operation": "update", "id": id, "data": data}
        if current_user is not None:
            kwargs["current_user"] = current_user
        if user_roles is not None:
            kwargs["user_roles"] = user_roles
        kwargs["is_superuser"] = is_superuser
        # #1319 / ADR-0032 Slice B — thread the full AuthContext so a status
        # transition's `invoke <flow>` runs each effect step scope-enforced as the
        # triggering principal (only a bare `current_user` string survived before).
        auth_ctx = _extra.get("auth_context")
        if auth_ctx is not None:
            kwargs["auth_context"] = auth_ctx
        result = require_found(await service.execute(**kwargs))
        return _with_htmx_triggers(
            request, result, entity_name, "updated", redirect_url=_htmx_current_url(request)
        )

    return _wrap_with_auth(
        _core,
        service=service,
        cedar_access_spec=cedar_access_spec,
        auth_dep=auth_dep,
        optional_auth_dep=optional_auth_dep,
        require_auth_by_default=require_auth_by_default,
        operation="update",
        entity_name=entity_name,
        audit_logger=audit_logger,
        include_field_changes=include_field_changes,
        needs_pre_read=True,
        # #1123 — scope: update: enforcement at request time.
        fk_graph=spec.handler.fk_graph,
        admin_personas=spec.handler.admin_personas,
    )


def create_delete_handler(spec: "RouteSpec") -> Callable[..., Any]:
    """Create a handler for delete operations with optional Cedar-style access control.

    See :class:`RouteSpec` for the per-route contract (#1011).
    """

    service = spec.service
    include_field_changes = spec.include_field_changes
    auth_dep = spec.handler.auth_dep
    optional_auth_dep = spec.handler.optional_auth_dep
    require_auth_by_default = spec.handler.require_auth_by_default
    entity_name = spec.handler.entity_name
    audit_logger = spec.handler.audit_logger
    cedar_access_spec = spec.handler.cedar_access_spec
    soft_delete_enabled = spec.soft_delete

    async def _core(
        id: UUID,
        request: Request,
        *,
        current_user: str | None = None,
        existing: Any = None,
        **_extra: Any,
    ) -> Any:
        try:
            if soft_delete_enabled:
                # #1218 Option A: stamp deleted_at instead of hard DELETE.
                # `existing` is populated by the `needs_pre_read` wrapper
                # below; if missing (e.g. already tombstoned), the read
                # path's tombstone filter has hidden the row → 404.
                result = await service.execute(
                    operation="update",
                    id=id,
                    data={"deleted_at": datetime.now(UTC)},
                )
            else:
                result = await service.execute(operation="delete", id=id)
        except ValueError as exc:
            # FK constraint violation — entity is referenced by child records.
            # `Repository.delete()` re-raises the psycopg IntegrityError as a
            # ValueError; without this guard it surfaces as an unhandled 500.
            raise HTTPException(status_code=409, detail=str(exc))
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        return _with_htmx_triggers(
            request,
            {"deleted": True},
            entity_name,
            "deleted",
            redirect_url=_htmx_parent_url(request),
        )

    return _wrap_with_auth(
        _core,
        service=service,
        cedar_access_spec=cedar_access_spec,
        auth_dep=auth_dep,
        optional_auth_dep=optional_auth_dep,
        require_auth_by_default=require_auth_by_default,
        operation="delete",
        entity_name=entity_name,
        audit_logger=audit_logger,
        include_field_changes=include_field_changes,
        needs_pre_read=True,
        # #1123 — scope: delete: enforcement at request time.
        fk_graph=spec.handler.fk_graph,
        admin_personas=spec.handler.admin_personas,
    )


def create_custom_handler(
    service: Any,
    input_schema: type[BaseModel] | None = None,
) -> Callable[..., Any]:
    """Create a handler for custom operations."""

    if input_schema:

        async def handler_with_input(request: Request) -> Any:
            body = await request.json()
            # Pydantic-validated input → Dazzle service layer → parameterized
            # Repository (cursor.execute(sql, params)); no string-built SQL.
            data = input_schema.model_validate(body)
            result = await service.execute(**data.model_dump())  # nosemgrep
            return result

        # Override annotations with the proper type so FastAPI recognizes it
        _set_handler_annotations(handler_with_input)

        return handler_with_input
    else:

        async def handler_no_input() -> Any:
            result = await service.execute()
            return result

        return handler_no_input
