"""Comparison context for scalar metric tiles (#1678).

#1491 inferred a 30-day period-over-period ``DeltaSpec`` for every unset
``metrics`` / ``summary`` tile whose entity had ``created_at``. That lied
on ops boards whose book is shorter than the window (BioChart
``week_energy``: 14-day demo, ``↑ +473893 vs prior 30 days`` vs empty).

#1678 reverses the default: an unset tile is **value + tone only**.
Authors who want a trend declare ``delta:`` (#884). This seam stays so
``_compute_aggregate_metrics`` has one place that decides "no inferred
delta" — both the HTML path and the JSON region path call it.
"""

from __future__ import annotations

from typing import Any

from dazzle.core.ir import DeltaSpec


def resolve_comparison(
    aggregates: dict[str, Any] | None,
    repositories: dict[str, Any] | None,
    source_entity: str | None = None,
) -> DeltaSpec | None:
    """Never infer a comparison. Unset metrics tiles stay a lone KPI (#1678).

    ``aggregates`` / ``repositories`` / ``source_entity`` are accepted so
    call sites stay unchanged. An explicit author ``delta:`` is passed in
    by the caller and never reaches this function.
    """
    return None
