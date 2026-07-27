"""ADR-0039 (#778/#1398) — the auth↔domain-`User` provisioning mirror.

A path-neutral helper that upserts the DSL-defined ``User`` domain row when an auth
user is created, so apps with ``ref User`` foreign keys can create owned rows for the
authenticated principal. Called from **both** the production auth-user choke point
(`AuthStore.create_user`, via a server-set hook) and the test/QA `/__test__/authenticate`
route — one rule, no divergent copy (D4).

Two modes, both keyed on the `User` entity's core-IR ``auth_identity`` declaration:

* **declared** (``auth_identity:`` present, D2/D3a): resolve each domain column from the
  declared ``link_via`` + ``map`` (auth-attribute → column) + literal ``default``s. The
  binding is validate-time complete (D6/A1), so the upsert can't fail on an unsatisfied
  NOT-NULL column.
* **undeclared** (no binding, D5): the schema-derived best-effort that shipped for #1398 —
  map the auth user's id/email/username/role onto whatever common columns the entity
  declares, placeholder-fill other required scalars. Preserves today's behaviour exactly.

The domain row's ``id`` is set to the auth ``user_id`` (id-equality by construction), so
the #774 ``ref User`` auto-injection keeps resolving; ADR-0039 D3b's link-resolution
(Slice 4) generalises this to the email join for externally-created rows. Idempotent
``INSERT ... ON CONFLICT (id) DO UPDATE``. Never touches the auth store / session (D1).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from dazzle.core import ir
from dazzle.http.runtime.query_builder import quote_identifier

logger = logging.getLogger(__name__)

# Sentinel: a field type with no safe scalar placeholder (enum / ref / uuid / email / date).
_NO_PLACEHOLDER = object()

_SCALAR_PLACEHOLDERS: dict[ir.FieldTypeKind, Any] = {
    ir.FieldTypeKind.STR: "",
    ir.FieldTypeKind.TEXT: "",
    ir.FieldTypeKind.SLUG: "",
    ir.FieldTypeKind.URL: "",
    ir.FieldTypeKind.TIMEZONE: "UTC",
    ir.FieldTypeKind.INT: 0,
    ir.FieldTypeKind.DECIMAL: 0,
    ir.FieldTypeKind.FLOAT: 0.0,
    ir.FieldTypeKind.MONEY: 0,
    ir.FieldTypeKind.BOOL: False,
    ir.FieldTypeKind.JSON: "{}",
}


def _scalar_placeholder(field: ir.FieldSpec) -> Any:
    """A NOT-NULL-satisfying placeholder for a required-without-default column.

    Only plain scalars get one — enum/ref/uuid/email/date(time)/file are
    format- or referent-constrained and return the ``_NO_PLACEHOLDER`` sentinel.
    """
    return _SCALAR_PLACEHOLDERS.get(field.type.kind, _NO_PLACEHOLDER)


def _coerce_enum_role(field: ir.FieldSpec, role: str) -> str | None:
    """Map an auth role onto a domain enum column without inventing invalid values.

    ``/__test__/authenticate`` historically defaulted ``role="user"`` when the
    caller omitted a persona. Apps that declare ``role: enum[admin,manager,member]``
    then got a domain row that failed Pydantic validation on every workspace
    ``source: User`` list — fail-closed regions rendered "No team members yet"
    even when valid teammates existed (project_tracker people_desk, cycle 1350).

    Returns a legal enum token (caller role if allowed, else field default, else
    first enum value), or ``None`` when the field is not an enum / has no values
    (caller should write the raw role string for free-form ``str`` role columns).
    """
    if field.type.kind != ir.FieldTypeKind.ENUM:
        return None
    values = list(field.type.enum_values or [])
    if not values:
        return None
    if role in values:
        return role
    if field.default is not None and str(field.default) in values:
        return str(field.default)
    return values[0]


def _resolve_source(source: str, *, user_id: str, email: str, username: str, role: str) -> str:
    """Resolve an ``auth_identity: map`` source token to the auth principal's value."""
    localpart = email.split("@", 1)[0] if email else (username or user_id)
    return {
        "id": user_id,
        "email": email,
        "email_localpart": localpart,
        "username": username or localpart,
        "role": role,
    }.get(source, "")


def build_domain_user_upsert(
    user_spec: ir.EntitySpec,
    *,
    user_id: str,
    email: str,
    username: str,
    role: str,
) -> tuple[str, tuple[Any, ...]] | None:
    """Build the idempotent ``User`` upsert ``(sql, params)``, or ``None`` if not mirrorable.

    ``user_spec`` is the core-IR ``User`` entity (its ``auth_identity`` selects declared vs
    heuristic mode). Identifiers come only from validated ``FieldSpec.name`` via
    ``quote_identifier``; every value is a bound parameter.
    """
    auto = {ir.FieldModifier.AUTO_ADD, ir.FieldModifier.AUTO_UPDATE}
    writable = {f.name: f for f in user_spec.fields if auto.isdisjoint(f.modifiers)}
    bound: dict[str, Any] = {}

    # id-equality by construction: keeps #774 ref-User auto-injection resolving until D3b.
    if "id" in writable:
        bound["id"] = user_id

    binding = user_spec.auth_identity
    if binding is not None:
        # Declared path (D2/D3a) — the binding is validate-complete (D6/A1).
        if binding.link_via in writable:
            bound[binding.link_via] = email
        for col, source in binding.field_map:
            if col in writable:
                value = _resolve_source(
                    source, user_id=user_id, email=email, username=username, role=role
                )
                if source == "role":
                    coerced = _coerce_enum_role(writable[col], value)
                    if coerced is not None:
                        if coerced != value:
                            logger.warning(
                                "auth→domain User mirror (declared): role %r not in "
                                "enum %s — using %r",
                                value,
                                writable[col].type.enum_values,
                                coerced,
                            )
                        value = coerced
                bound[col] = value
        for col, literal in binding.defaults:
            if col in writable:
                bound[col] = literal
    else:
        # Undeclared path (D5) — schema-derived best-effort (#1398). `username` is the
        # display string the test/QA flow supplies; `name` flows to any common label col.
        if "email" in writable:
            bound["email"] = email
        for label_col in ("name", "display_name", "full_name"):
            if label_col in writable:
                bound[label_col] = username
        if "username" in writable:
            bound["username"] = username or (email.split("@", 1)[0] if email else user_id)
        if "role" in writable:
            role_field = writable["role"]
            coerced = _coerce_enum_role(role_field, role)
            bound["role"] = role if coerced is None else coerced
            if coerced is not None and coerced != role:
                logger.warning(
                    "auth→domain User mirror: role %r not in enum %s — using %r",
                    role,
                    role_field.type.enum_values,
                    coerced,
                )
        if "is_active" in writable:
            bound["is_active"] = True
        for fname, f in writable.items():
            if fname in bound or ir.FieldModifier.REQUIRED not in f.modifiers:
                continue
            if f.default is not None or f.default_expr is not None:
                continue
            placeholder = _scalar_placeholder(f)
            if placeholder is not _NO_PLACEHOLDER:
                bound[fname] = placeholder

    if "id" not in bound:
        return None  # no id column to conflict on — can't upsert deterministically

    has_created_at = any(f.name == "created_at" for f in user_spec.fields)
    cols = list(bound.keys())
    col_sql = ", ".join(quote_identifier(c) for c in cols)
    val_sql = ", ".join(["%s"] * len(cols))
    params: list[Any] = [bound[c] for c in cols]
    if has_created_at:
        col_sql += ', "created_at"'
        val_sql += ", NOW()"
    table = quote_identifier(user_spec.name)
    update_cols = [c for c in cols if c != "id"]
    if update_cols:
        # Preserve seed-quality display labels already on the domain row
        # (Ken Manager, Sam Member, …). Auth username ("manager") must not
        # clobber them on every /__test__/authenticate mirror.
        _label_cols = {"name", "display_name", "full_name"}
        set_parts: list[str] = []
        for c in update_cols:
            qc = quote_identifier(c)
            if c in _label_cols:
                existing = f"{table}.{qc}"
                set_parts.append(
                    f"{qc} = CASE WHEN {existing} IS NULL OR "
                    f"BTRIM(COALESCE({existing}::text, '')) = '' "
                    f"THEN EXCLUDED.{qc} ELSE {existing} END"
                )
            else:
                set_parts.append(f"{qc} = EXCLUDED.{qc}")
        conflict = f"ON CONFLICT (id) DO UPDATE SET {', '.join(set_parts)}"
    else:
        conflict = "ON CONFLICT (id) DO NOTHING"
    sql = f"INSERT INTO {table} ({col_sql}) VALUES ({val_sql}) {conflict}"
    return sql, tuple(params)


def mirror_auth_user_to_domain(
    execute: Callable[[str, tuple[Any, ...]], Any],
    user_spec: ir.EntitySpec,
    *,
    user_id: str,
    email: str,
    username: str,
    role: str,
) -> None:
    """Run the domain-`User` upsert via ``execute(sql, params)``. Best-effort + idempotent.

    ``execute`` is the caller's DB executor (the auth store's ``_execute_modify`` in
    production; a connection-bound runner in the test route). Failures are logged, never
    raised — a mirror miss must not break auth-user creation (D1).
    """
    built = build_domain_user_upsert(
        user_spec, user_id=user_id, email=email, username=username, role=role
    )
    if built is None:
        return
    sql, params = built
    try:
        # Closed templated SQL: identifiers via quote_identifier(validated FieldSpec.name);
        # all values are bound parameters.
        # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query
        execute(sql, params)
    except Exception:
        logger.warning(
            "Could not mirror auth user %s into '%s' entity", user_id, user_spec.name, exc_info=True
        )
