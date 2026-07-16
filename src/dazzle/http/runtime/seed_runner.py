"""
Runtime seed runner for reference data (#428).

Called at server startup to idempotently upsert rows generated
from entity ``seed_template`` specs.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from uuid import uuid4

import psycopg

from dazzle.core import ir
from dazzle.core.ir.fields import FieldModifier, FieldTypeKind
from dazzle.http.runtime.tenant_isolation import (
    _current_tenant_schema,
    set_current_tenant_schema,
)
from dazzle.seed.generator import generate_seed_rows, resolve_match_field

logger = logging.getLogger(__name__)


def _find_uuid_pk_field(entity: Any) -> str | None:
    """Return the name of the UUID pk field, or None if not applicable."""

    for f in entity.fields:
        if FieldModifier.PK in f.modifiers and f.type.kind == FieldTypeKind.UUID:
            return str(f.name)
    return None


def _tenancy_isolation_mode(appspec: ir.AppSpec) -> str:
    tenancy = getattr(appspec, "tenancy", None)
    if tenancy is None:
        return ""
    raw = getattr(tenancy, "isolation", None)
    if raw is None:
        return ""
    if hasattr(raw, "value"):
        return str(raw.value)
    return str(raw)


def _tenant_schemas_to_seed(appspec: ir.AppSpec) -> list[str | None]:
    """Schemas that should receive reference seed data.

    Returns ``[None]`` for non-schema tenancy (writes with default search_path).
    For schema isolation, returns every ``tenant_*`` schema found in the DB
    (via DATABASE_URL), falling back to ``[None]`` if discovery fails so boot
    still attempts a public/default write.
    """
    if _tenancy_isolation_mode(appspec) != "schema":
        return [None]

    url = os.environ.get("DATABASE_URL") or os.environ.get("DAZZLE_DATABASE_URL")
    if not url:
        logger.warning("Seed: schema tenancy but no DATABASE_URL; seeding default path only")
        return [None]
    try:
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT schema_name FROM information_schema.schemata
                    WHERE schema_name LIKE 'tenant\\_%' ESCAPE '\\'
                    ORDER BY schema_name
                    """
                )
                found: list[str | None] = [str(r[0]) for r in cur.fetchall()]
    except Exception:
        logger.warning("Seed: tenant schema discovery failed", exc_info=True)
        return [None]
    if not found:
        logger.warning("Seed: no tenant_* schemas found; seeding default path only")
        return [None]
    return found


async def _upsert_seed_row(
    repo: Any,
    *,
    entity_name: str,
    row: dict[str, Any],
    match_field: str,
    pk_field: str | None,
    schema_label: str,
) -> int:
    """Create one seed row if missing. Returns 1 if handled (exists or created)."""
    match_value = row.get(match_field)
    if match_value is None:
        return 0
    try:
        existing = await repo.list(
            page=1,
            page_size=1,
            filters={match_field: match_value},
        )
        items = existing.get("items", []) if isinstance(existing, dict) else existing
        if items:
            return 1

        payload = dict(row)
        if pk_field and pk_field not in payload:
            payload[pk_field] = str(uuid4())

        await repo.create(payload)
        logger.info(
            "Seed: created %s where %s=%s (schema=%s)",
            entity_name,
            match_field,
            match_value,
            schema_label,
        )
        return 1
    except Exception:
        logger.warning(
            "Seed: failed to upsert %s where %s=%s (schema=%s)",
            entity_name,
            match_field,
            match_value,
            schema_label,
            exc_info=True,
        )
        return 0


async def _run_seed_templates_in_schema(
    appspec: ir.AppSpec,
    repositories: dict[str, Any],
    *,
    schema: str | None,
) -> int:
    # Bind tenant schema for the duration of this pass (no request context at boot).
    token = set_current_tenant_schema(schema) if schema else None

    total = 0
    try:
        for entity in appspec.domain.entities:
            seed_tmpl = entity.seed_template
            if not seed_tmpl:
                continue

            repo = repositories.get(entity.name)
            if not repo:
                logger.warning("Seed: no repository for entity %s, skipping", entity.name)
                continue

            rows = generate_seed_rows(seed_tmpl)
            if not rows:
                continue

            match_field = resolve_match_field(seed_tmpl, entity)
            if not match_field:
                logger.warning(
                    "Seed: no match field for entity %s, cannot upsert idempotently",
                    entity.name,
                )
                continue

            pk_field = _find_uuid_pk_field(entity)
            schema_label = schema or "default"
            for row in rows:
                total += await _upsert_seed_row(
                    repo,
                    entity_name=entity.name,
                    row=row,
                    match_field=match_field,
                    pk_field=pk_field,
                    schema_label=schema_label,
                )
    finally:
        if token is not None:
            _current_tenant_schema.reset(token)

    return total


async def run_seed_templates(
    appspec: ir.AppSpec,
    repositories: dict[str, Any],
) -> int:
    """Generate and upsert seed rows for all entities with seed templates.

    Schema-per-tenant apps: boot has no request tenant context, so rows used
    to land only in ``public`` while API lists read ``tenant_*`` — FiscalYear
    and similar reference tables looked empty. We now seed each known tenant
    schema (plus ``public`` as fallback) with ``search_path`` bound.

    Args:
        appspec: The ``AppSpec`` IR object.
        repositories: Map of entity name → repository instance.

    Returns:
        Total number of rows upserted (created or already existed).
    """

    schemas = _tenant_schemas_to_seed(appspec)
    total = 0
    for schema in schemas:
        total += await _run_seed_templates_in_schema(appspec, repositories, schema=schema)
    return total
