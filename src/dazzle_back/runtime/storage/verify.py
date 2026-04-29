"""Storage-bound field verification (#932 cycle 4).

When a DSL field is declared ``field foo: file storage=<name>``, the
client-side flow under cycle 1-3 looks like:

    1. POST /api/{entity}/upload-ticket  → server mints presigned form
    2. browser uploads bytes directly to S3
    3. POST /api/{entity}                 → ordinary create with s3_key
                                              in the body

This module provides the verification step the ordinary create path
needs in (3): without it, user A could claim user B's uploaded object
just by submitting B's s3_key. The check has two parts:

    - **Prefix sandbox** — the s3_key must lie under the prefix
      ``provider.render_prefix(user_id=A, record_id=*)`` would produce.
      Stops cross-user key claims.
    - **Object existence** — ``provider.head_object(s3_key)`` must
      return non-None. Stops the client from finalising a record
      before the upload actually committed.

The verifier is invoked from ``create_create_handler`` and
``create_update_handler`` in route_generator.py, between body parse
and Pydantic validation. Fields without a ``storage=`` binding are
ignored. Bodies that omit a storage-bound field are ignored (the
field may be optional, or this update isn't touching it).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StorageVerificationError(Exception):
    """Raised by ``verify_storage_field_keys`` when a body's
    storage-bound s3_key fails sandbox or existence checks.

    The ``status_code`` attribute distinguishes the two failure
    classes so the route handler can map to the right HTTP status:
    403 for sandbox escapes (someone else's prefix), 400 for missing
    objects (premature finalize).
    """

    field: str
    s3_key: str
    storage: str
    reason: str
    status_code: int

    def __str__(self) -> str:
        return (
            f"Storage verification failed for field '{self.field}' "
            f"(storage='{self.storage}', s3_key='{self.s3_key}'): "
            f"{self.reason}"
        )


def _expected_prefix_pattern(prefix_template: str, user_id: str) -> re.Pattern[str]:
    """Build a regex that matches every key the user's own
    upload-ticket flow can produce.

    ``{user_id}`` is fixed to the caller's id; ``{record_id}`` is
    replaced with a non-slash wildcard because we don't know the
    record_id ahead of time (the upload-ticket route generates it).
    Any other placeholders the project added are also passed through
    as wildcards.
    """
    # Escape the literal parts first, then plug placeholders back as
    # regex wildcards. Order matters: the literal-escape would mangle
    # the curly braces if we did it the other way around.
    pattern = re.escape(prefix_template)
    pattern = pattern.replace(re.escape("{user_id}"), re.escape(user_id))
    pattern = re.sub(r"\\\{[a-zA-Z_]+\\\}", "[^/]+", pattern)
    return re.compile("^" + pattern)


def verify_storage_field_keys(
    body: dict[str, Any],
    storage_bindings: Mapping[str, str],
    registry: Any,
    user_id: str | None,
) -> None:
    """Run sandbox + existence checks on every storage-bound field
    that has a value in this request body.

    Args:
        body: Parsed request JSON (mutable; not modified).
        storage_bindings: Map of field_name → storage_name for the
            entity being created/updated. Empty map = no-op.
        registry: ``StorageRegistry`` instance from
            ``app.state.storage_registry``. ``None`` skips verification
            with a logged warning — the dev hasn't wired storage yet.
        user_id: Authenticated user id. ``None`` raises a sandbox
            failure for any storage-bound field present in the body —
            you cannot finalise an upload anonymously.

    Raises:
        StorageVerificationError: Any check failed.
    """
    if not storage_bindings or not body:
        return

    for field_name, storage_name in storage_bindings.items():
        raw = body.get(field_name)
        if raw is None or raw == "":
            # Field absent or explicitly empty — not being set this
            # request, nothing to verify.
            continue
        if not isinstance(raw, str):
            raise StorageVerificationError(
                field=field_name,
                s3_key=str(raw),
                storage=storage_name,
                reason="value must be a string s3_key",
                status_code=400,
            )

        if registry is None:
            raise StorageVerificationError(
                field=field_name,
                s3_key=raw,
                storage=storage_name,
                reason=(
                    "no StorageRegistry available — server is missing "
                    "[storage.<name>] config or has not finished startup"
                ),
                status_code=500,
            )

        if user_id is None:
            raise StorageVerificationError(
                field=field_name,
                s3_key=raw,
                storage=storage_name,
                reason="authentication required to finalise an upload",
                status_code=401,
            )

        try:
            provider = registry.get(storage_name)
        except KeyError:
            raise StorageVerificationError(
                field=field_name,
                s3_key=raw,
                storage=storage_name,
                reason=f"storage '{storage_name}' is not registered",
                status_code=503,
            ) from None

        prefix_template = getattr(provider, "prefix_template", None)
        if prefix_template:
            sandbox = _expected_prefix_pattern(prefix_template, user_id)
            if not sandbox.match(raw):
                raise StorageVerificationError(
                    field=field_name,
                    s3_key=raw,
                    storage=storage_name,
                    reason=(
                        "s3_key falls outside the caller's sandbox prefix — "
                        "did the request reuse another user's key?"
                    ),
                    status_code=403,
                )

        try:
            head = provider.head_object(raw)
        except Exception as exc:  # noqa: BLE001 — provider may raise anything
            raise StorageVerificationError(
                field=field_name,
                s3_key=raw,
                storage=storage_name,
                reason=f"head_object raised: {exc}",
                status_code=503,
            ) from exc
        if head is None:
            raise StorageVerificationError(
                field=field_name,
                s3_key=raw,
                storage=storage_name,
                reason=(
                    "no object at this key — the upload either failed or has not committed yet"
                ),
                status_code=400,
            )


def build_entity_storage_bindings(appspec: Any) -> dict[str, dict[str, str]]:
    """Compute ``{entity_name: {field_name: storage_name}}`` from the
    AppSpec. Called once at server startup; consumed by RouteGenerator
    so create/update handlers know which body fields to verify.
    """
    bindings: dict[str, dict[str, str]] = {}
    domain = getattr(appspec, "domain", None)
    if domain is None:
        return bindings
    for entity in getattr(domain, "entities", []) or []:
        per_entity: dict[str, str] = {}
        for field in getattr(entity, "fields", []) or []:
            storage_name = getattr(field, "storage", None)
            if storage_name:
                per_entity[field.name] = storage_name
        if per_entity:
            bindings[entity.name] = per_entity
    return bindings
