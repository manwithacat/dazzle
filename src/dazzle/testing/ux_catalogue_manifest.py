"""Sample data + descriptions for the ux_catalogue regions (UX catalogue, Sub-project A).

One entry per region in the ``ux_catalogue`` workspace of
``fixtures/component_showcase``. ``sample_items`` feed item-based modes
(list/bullet/kanban); ``canned_buckets`` feed aggregate modes (bar_chart/
comparison/heatmap/pivot/metrics) via the fake repository in the harness.
This is the single place catalogue sample data lives.
"""

from typing import Any

# Item-based sample rows. cat_list includes a clear latency outlier (foxtrot)
# so the `outlier_on` decorator renders a ⚠ badge over ≥6 finite values.
_BOXES: list[dict[str, Any]] = [
    {
        "name": "alpha",
        "team": "platform",
        "status": "healthy",
        "latency_ms": 42,
        "error_rate": 0.1,
        "target_ms": 50,
    },
    {
        "name": "bravo",
        "team": "platform",
        "status": "healthy",
        "latency_ms": 38,
        "error_rate": 0.2,
        "target_ms": 50,
    },
    {
        "name": "charlie",
        "team": "payments",
        "status": "degraded",
        "latency_ms": 44,
        "error_rate": 1.4,
        "target_ms": 50,
    },
    {
        "name": "delta",
        "team": "payments",
        "status": "healthy",
        "latency_ms": 40,
        "error_rate": 0.3,
        "target_ms": 50,
    },
    {
        "name": "echo",
        "team": "growth",
        "status": "healthy",
        "latency_ms": 46,
        "error_rate": 0.2,
        "target_ms": 50,
    },
    {
        "name": "foxtrot",
        "team": "data",
        "status": "critical",
        "latency_ms": 380,
        "error_rate": 7.2,
        "target_ms": 50,
    },
]

CatalogueEntry = dict[str, Any]

CATALOGUE_MANIFEST: dict[str, CatalogueEntry] = {
    "cat_list": {
        "description": (
            "The workhorse table. Here it carries the `outlier_on` decorator — the "
            "`latency_ms` cell flags the statistical outlier (⚠ high) vs the displayed rows."
        ),
        "sample_items": _BOXES,
        "canned_buckets": None,
    },
}
