"""Typed render context for the region builders.

`RegionContext` is the structured bag the dispatcher (`_dispatcher.py`) hands each
`_build_*` region builder — replacing the former `ctx: dict[str, Any]`. It is the
documented contract of every key a builder may read, keyed by the display modes that
produce them. `total=False`: each builder reads only the subset its mode populates, so
all keys are optional; accessing an undeclared key is a typo mypy now catches.

Value types are tightened where unambiguous (names/URLs/flags); the richer per-mode
payloads (row/cell/series structures) stay `Any` because their element shapes vary by
builder — narrowing those is a follow-up, not a blocker for the readability win.
"""

from typing import Any, TypedDict


class RegionContext(TypedDict, total=False):
    """Render context consumed by the `_build_*` region builders (#1042 substrate)."""

    # --- identity / wiring (shared across modes) ---
    entity_name: str
    region_name: str
    region_url: str
    endpoint: str
    name: str
    label: str
    label_field: str
    display_key: str
    description: str
    message: str
    empty_message: str
    placeholder: str
    prompt: str

    # --- list / table ---
    columns: Any  # polymorphic: list[col-def] in tables, int (grid width) in cards
    rows: list[Any]
    items: list[Any]
    item: Any
    fields: list[Any]
    filter_columns: Any
    active_filters: Any
    detail_url_template: str
    row_action_routes: Any
    relations: Any
    source_tabs: Any
    tabs: Any

    # --- actions / CTAs ---
    action_cards: Any
    action_card_data: Any
    action_label: str
    primary_label: str
    secondary_label: str
    primary_action_url: str
    secondary_action_url: str
    primary_action_url_field: str

    # --- CSV export ---
    csv_export: bool
    csv_filename: str

    # --- dates ---
    date_range: bool
    date_from: Any
    date_to: Any

    # --- metrics / KPIs ---
    metrics: Any
    total: Any
    aggregates: Any
    complete_count: Any
    complete_pct: Any
    progress_total: Any
    stage_counts: Any
    coaching_message: str
    audit_enabled: bool

    # --- charts (bar / bullet / histogram / heatmap / cohort / pivot) ---
    axes: Any
    buckets: Any
    cells: Any
    chart_label: str
    bar_track_rows: Any
    bar_track_max: Any
    # #1470 display: comparison — ranked-league rows + shared bar scale.
    comparison_rows: Any
    comparison_max: Any
    # #1470 outlier_on — list-column outlier decorator.
    outlier_flags: Any
    outlier_on: Any
    bullet_rows: Any
    bullet_max_value: Any
    histogram_bins: Any
    heatmap_matrix: Any
    heatmap_col_values: Any
    heatmap_thresholds: Any
    cohort_cells: Any
    cohort_active_lens: Any
    cohort_endpoint: str
    pivot_buckets: Any
    pivot_dim_specs: Any
    reference_bands: Any
    reference_lines: Any
    points: Any
    slices: Any

    # --- grouping ---
    group_by: Any
    group_by_field: str
    group_keys: Any
    groups: Any

    # --- graph / diagram / tree ---
    nodes: Any
    edges: Any
    diagram_data: Any
    tree_items: Any
    source_entity: str

    # --- timeline / pipeline / kanban / queue ---
    day_timeline_slots: Any
    pipeline_stage_data: Any
    kanban_columns: Any
    queue_api_endpoint: str
    queue_status_field: str
    queue_transitions: Any
    state_value: Any
    status_entries: Any

    # --- cards (profile / entity / task-inbox) ---
    profile_card_data: Any
    entity_card_sections: Any
    entity_card_record_label: str
    task_inbox_items: Any
    task_inbox_chips: Any

    # --- misc ---
    confirmations: Any
    revoke_url: str
