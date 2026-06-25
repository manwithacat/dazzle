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
        "marker": "dz-list-region",
        "sample_items": _BOXES,
        "canned_buckets": None,
    },
    "cat_metrics": {
        "description": "KPI tiles — scalar aggregates over the scoped set.",
        "marker": "dz-metric-tile",
        "sample_items": [],
        "canned_buckets": [{"dimensions": {}, "measures": {"avg_latency": 41}}],
        "canned_list_totals": [42, 7],  # total, critical (popped in order)
    },
    "cat_bar_chart": {
        "description": "Distribution by a category — one bar per group. One scope-aware GROUP BY.",
        "marker": "dz-bar-chart-region",
        "sample_items": [],
        "canned_buckets": [
            {
                "dimensions": {"team": "platform", "team_label": "platform"},
                "measures": {"count": 12},
            },
            {
                "dimensions": {"team": "payments", "team_label": "payments"},
                "measures": {"count": 7},
            },
            {"dimensions": {"team": "growth", "team_label": "growth"}, "measures": {"count": 4}},
            {"dimensions": {"team": "data", "team_label": "data"}, "measures": {"count": 9}},
        ],
    },
    "cat_comparison": {
        "description": "Ranked league — rows ranked by a metric with inline bars + automatic outlier flag.",
        "marker": "dz-bar-track",
        "sample_items": [],
        "canned_buckets": [
            {
                "dimensions": {"team": "platform", "team_label": "platform"},
                "measures": {"total": 12},
            },
            {
                "dimensions": {"team": "payments", "team_label": "payments"},
                "measures": {"total": 11},
            },
            {"dimensions": {"team": "growth", "team_label": "growth"}, "measures": {"total": 10}},
            {"dimensions": {"team": "data", "team_label": "data"}, "measures": {"total": 9}},
            {"dimensions": {"team": "infra", "team_label": "infra"}, "measures": {"total": 9}},
            {"dimensions": {"team": "ml", "team_label": "ml"}, "measures": {"total": 1}},
        ],
    },
    "cat_heatmap": {
        "description": "Matrix density — latency shaded across team × status.",
        "marker": "dz-heatmap-region",
        "sample_items": _BOXES,
        "canned_buckets": None,
    },
    "cat_pivot": {
        "description": "Cross-tab — counts across two dimensions (team × status).",
        "marker": "dz-pivot-region",
        "sample_items": [],
        "canned_buckets": [
            {"dimensions": {"team": "platform", "status": "healthy"}, "measures": {"count": 8}},
            {"dimensions": {"team": "platform", "status": "critical"}, "measures": {"count": 1}},
            {"dimensions": {"team": "payments", "status": "healthy"}, "measures": {"count": 6}},
            {"dimensions": {"team": "payments", "status": "degraded"}, "measures": {"count": 2}},
        ],
    },
    "cat_bullet": {
        "description": "Actual-vs-target rows — each box's latency against its target.",
        "marker": "dz-bullet-region",
        "sample_items": _BOXES,
        "canned_buckets": None,
    },
    "cat_kanban": {
        "description": "Board view — boxes grouped into status columns.",
        "marker": "dz-kanban-board",
        "sample_items": _BOXES,
        "canned_buckets": None,
    },
    "cat_rag": {
        "description": (
            "Fixed-band RAG decorator — `error_rate` cells are coloured green/amber/red "
            "against author thresholds (WCAG-safe tone + icon + label). The deterministic "
            "sibling of the outlier decorator."
        ),
        "marker": "dz-badge",
        "sample_items": _BOXES,
        "canned_buckets": None,
    },
    "cat_insight": {
        "description": (
            "A grounded, deterministic narrative — scale + leader + outlier — over a "
            "grouped aggregate, with the underlying values cited so every claim is "
            "verifiable. No LLM (that's Slice 2)."
        ),
        "marker": "dz-stack",
        "sample_items": [],
        "canned_buckets": [
            {
                "dimensions": {"team": "platform", "team_label": "platform"},
                "measures": {"count": 20},
            },
            {
                "dimensions": {"team": "payments", "team_label": "payments"},
                "measures": {"count": 19},
            },
            {"dimensions": {"team": "growth", "team_label": "growth"}, "measures": {"count": 18}},
            {"dimensions": {"team": "data", "team_label": "data"}, "measures": {"count": 17}},
            {"dimensions": {"team": "infra", "team_label": "infra"}, "measures": {"count": 16}},
            {"dimensions": {"team": "ml", "team_label": "ml"}, "measures": {"count": 1}},
        ],
    },
    "cat_histogram": {
        "description": "Continuous-axis distribution — `latency_ms` binned (Sturges' rule).",
        "marker": "dz-histogram-region",
        "sample_items": _BOXES,
        "canned_buckets": None,
    },
    "cat_box_plot": {
        "description": (
            "Quartile spread per team — Q1/median/Q3 + Tukey whiskers over `latency_ms`."
        ),
        "marker": "dz-box-plot-region",
        "sample_items": _BOXES,
        "canned_buckets": None,
    },
    "cat_funnel": {
        "description": "Stage funnel — boxes counted through the status lifecycle.",
        "marker": "dz-funnel-chart-region",
        "sample_items": _BOXES,
        "canned_buckets": None,
    },
}
