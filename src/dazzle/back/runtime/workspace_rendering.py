"""Re-export shim for the workspace-region runtime modules.

Historical home of the 4,483-line workspace region rendering monolith.
Decomposed across #1057 cuts 1-15 (v0.67.100 → v0.67.114) into 16
focused sibling modules; the handler itself moved to
``workspace_region_handler.py`` in cut 16 (v0.67.115). This file is
now a pure re-export surface kept for back-compat with the ~50 test
sites that import these names from ``workspace_rendering``.

Where things live now:

- ``_workspace_region_handler`` → ``workspace_region_handler``
- ``WorkspaceRegionContext`` → ``workspace_context``
- ``_apply_workspace_scope_filters`` → ``workspace_scope``
- ``_resolve_workspace_user`` → ``workspace_user``
- ``_render_csv_response`` → ``workspace_csv``
- Aggregation regex + helpers → ``workspace_aggregation``
- Card-body HTML renderers → ``workspace_card_bodies``
- Card-data shapers → ``workspace_card_data``
- Async card fetchers + ``_build_entity_card_sections`` → ``workspace_card_fetchers``
- Column metadata builders → ``workspace_columns``
- Per-display data computes → ``workspace_region_computes``
- Phase 1 prelude → ``workspace_region_prelude``
- Phase 2 fetch → ``workspace_region_fetch``
- Phases 4-5 orchestration → ``workspace_region_orchestration``
- Phase 6 render tail → ``workspace_region_render``
- Sibling request handlers (region-JSON / batch / stats) → ``workspace_handlers``

New code should import directly from the module of origin; the
re-exports here are kept only so external test imports don't break.
"""

from dazzle.back.runtime.workspace_aggregation import (  # noqa: F401
    _AGGREGATE_RE,
    _aggregate_via_groupby,
    _bucket_key_label,
    _build_aggregate_filters,
    _compute_aggregate_metrics,
    _compute_box_plot_stats,
    _compute_bucketed_aggregates,
    _compute_histogram_bins,
    _compute_pivot_buckets,
    _enumerate_distinct_buckets,
    _fetch_count_metric,
    _fetch_scalar_metric,
    _format_bucket_label,
    _parse_simple_where,
    _resolve_fk_target_spec,
)
from dazzle.back.runtime.workspace_card_data import (  # noqa: F401
    _CARD_TEMPLATE_RE,
    _build_cohort_cells,
    _build_day_timeline_slots,
    _build_task_inbox_payload,
    _coerce_pipeline_progress,
    _coerce_urgency,
    _initials_from,
    _inject_display_names,
    _interpolate_card_template,
    _items_from_template,
    _resolve_display_name,
    _resolve_path,
    _resolve_task_inbox_multi_source,
)
from dazzle.back.runtime.workspace_card_fetchers import (  # noqa: F401
    _build_entity_card_sections,
    _empty_list_coro,
    _fetch_entity_card_section_rows,
    _fetch_task_inbox_items_per_source,
    _safe_fetch,
)
from dazzle.back.runtime.workspace_columns import (
    build_entity_columns as _build_entity_columns,  # noqa: F401
)
from dazzle.back.runtime.workspace_columns import (
    build_surface_columns as _build_surface_columns,  # noqa: F401
)
from dazzle.back.runtime.workspace_columns import (
    field_kind_to_col_type as _field_kind_to_col_type,  # noqa: F401
)
from dazzle.back.runtime.workspace_context import WorkspaceRegionContext  # noqa: F401
from dazzle.back.runtime.workspace_csv import _render_csv_response  # noqa: F401
from dazzle.back.runtime.workspace_region_handler import _workspace_region_handler  # noqa: F401
from dazzle.back.runtime.workspace_scope import _apply_workspace_scope_filters  # noqa: F401
from dazzle.back.runtime.workspace_user import _resolve_workspace_user  # noqa: F401
