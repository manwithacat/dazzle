"""
Runtime seed runner for reference data (#428).

Called at server startup to idempotently upsert rows generated
from entity ``seed_template`` specs.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


def _find_uuid_pk_field(entity: Any) -> str | None:
    """Return the name of the UUID pk field, or None if not applicable."""
    from dazzle.core.ir.fields import FieldModifier, FieldTypeKind

    for f in entity.fields:
        if FieldModifier.PK in f.modifiers and f.type.kind == FieldTypeKind.UUID:
            return str(f.name)
    return None


async def run_seed_templates(
    appspec: Any,
    repositories: dict[str, Any],
) -> int:
    """Generate and upsert seed rows for all entities with seed templates.

    Args:
        appspec: The ``AppSpec`` IR object.
        repositories: Map of entity name → repository instance.

    Returns:
        Total number of rows upserted (created or already existed).
    """
    from dazzle.seed.generator import generate_seed_rows, resolve_match_field

    total = 0
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

        # Detect UUID pk field for auto-generation
        pk_field = _find_uuid_pk_field(entity)

        for row in rows:
            match_value = row.get(match_field)
            if match_value is None:
                continue
            try:
                # Check if row already exists
                existing = await repo.list(
                    page=1,
                    page_size=1,
                    filters={match_field: match_value},
                )
                items = existing.get("items", []) if isinstance(existing, dict) else existing
                if items:
                    # Row exists, skip
                    total += 1
                    continue

                # Auto-generate UUID pk if not provided
                if pk_field and pk_field not in row:
                    row[pk_field] = str(uuid4())

                # Create new row
                await repo.create(row)
                total += 1
                logger.info(
                    "Seed: created %s where %s=%s",
                    entity.name,
                    match_field,
                    match_value,
                )
            except Exception:
                logger.warning(
                    "Seed: failed to upsert %s where %s=%s",
                    entity.name,
                    match_field,
                    match_value,
                    exc_info=True,
                )

    return total
