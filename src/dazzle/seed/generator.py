"""
Seed data generator for rolling-window reference data (#428).

Evaluates ``SeedTemplateSpec`` attached to entities and produces
rows suitable for idempotent upsert into the repository.

Template variables (rolling_window strategy):
    {y}        — start year (e.g. 2025)
    {y1}       — end year, y + 1 (e.g. 2026)
    {y_short}  — last 2 digits of y (e.g. 25)
    {y1_short} — last 2 digits of y + 1 (e.g. 26)

Special template expressions:
    "y == current_year"  → evaluates to ``true`` or ``false`` (string)
"""

from __future__ import annotations

import datetime
from typing import Any


def generate_seed_rows(
    seed_template: Any,
    *,
    reference_date: datetime.date | None = None,
) -> list[dict[str, Any]]:
    """Generate seed rows from a SeedTemplateSpec.

    Args:
        seed_template: A ``SeedTemplateSpec`` IR object.
        reference_date: Override the "current" date (default: today).
            Useful for testing.

    Returns:
        List of row dicts ready for repository upsert.
    """
    if reference_date is None:
        reference_date = datetime.date.today()

    current_year = reference_date.year
    strategy = seed_template.strategy
    if hasattr(strategy, "value"):
        strategy = strategy.value

    if strategy != "rolling_window":
        return []

    rows: list[dict[str, Any]] = []
    for offset in range(seed_template.window_start, seed_template.window_end + 1):
        y = current_year + offset
        y1 = y + 1
        ctx = {
            "y": str(y),
            "y1": str(y1),
            "y_short": f"{y % 100:02d}",
            "y1_short": f"{y1 % 100:02d}",
        }

        row: dict[str, Any] = {}
        for ft in seed_template.fields:
            value = _render_template(ft.template, ctx, y, current_year)
            row[ft.field] = value
        rows.append(row)

    return rows


def _render_template(
    template: str,
    ctx: dict[str, str],
    y: int,
    current_year: int,
) -> str:
    """Render a single field template string.

    Handles both ``{var}`` substitution and special expressions
    like ``y == current_year``.
    """
    # Special boolean expression
    stripped = template.strip()
    if stripped == "y == current_year":
        return "true" if y == current_year else "false"
    if stripped == "y != current_year":
        return "true" if y != current_year else "false"

    # Standard {var} substitution
    result = template
    for key, val in ctx.items():
        result = result.replace("{" + key + "}", val)
    return result


def resolve_match_field(
    seed_template: Any,
    entity_spec: Any,
) -> str | None:
    """Determine which field to match on for idempotent upsert.

    Priority:
    1. Explicit ``match_field`` on the seed template
    2. First ``unique`` field on the entity
    3. None (caller should skip upsert logic)
    """
    if seed_template.match_field:
        return str(seed_template.match_field)

    if entity_spec and hasattr(entity_spec, "fields"):
        from dazzle.core.ir.fields import FieldModifier

        for f in entity_spec.fields:
            if FieldModifier.UNIQUE in f.modifiers:
                return str(f.name)

    return None
