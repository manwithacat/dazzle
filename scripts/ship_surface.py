#!/usr/bin/env python3
"""Ship-surface pack — recurrent CI red classes that Tier 0 used to miss.

# Why this exists

``make ci-fast`` (Tier 0) was green while GitHub stayed red on a rotating set
of *deterministic, cheap* checks:

* bandit medium on ``src/`` (e.g. B324 hashlib)
* example SPECIFICATION.md freshness after DSL edits
* simple_task brief golden + IR golden snapshot
* patterns.toml ``pattern_count`` meta
* IR reader orphan baseline
* viewport DRAWER_PATTERN selector freshness (browser-free)

These are **not** Postgres/Playwright Tier 2. They belong in the ship path so
agents do not discover them only after a full ``ci.yml`` matrix multiplies one
failure × 3 Pythons.

Wired into:

* ``make ship-surface`` / ``bash scripts/ci_local.sh ship-surface``
* ``scripts/ci_local.sh`` tier0 (**after** preflight-surface, before long gate suite)
* ``/ship`` skill (part of Tier 0)

Exit 0 = pack clean. Exit 1 = unpaid debt; print playbook; do not ship.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Ordered: cheapest / highest-signal first. Prefer nodeids when the whole
# module is large or mixed.
SHIP_TESTS: tuple[str, ...] = (
    "tests/unit/test_example_spec_bar.py",
    "tests/unit/test_example_product_maturity.py",
    "tests/unit/test_demo_fleet_bar.py",
    "tests/unit/test_improve_example_probes.py",
    "tests/unit/test_improve_commit_contract.py",
    "tests/unit/test_nav_platform_isolation_1626.py",
    "tests/unit/test_human_create_cta_label.py",
    "tests/unit/test_dashboard_card_remove_gating.py",
    "tests/unit/test_spec_narrative_brief_snapshot.py",
    "tests/unit/test_patterns_phase2_kb_1217.py::test_pattern_count_meta_matches_actual_count",
    "tests/unit/test_patterns_subtype_of_kb_1248.py::test_pattern_count_meta_matches_actual_count",
    "tests/unit/test_ir_field_reader_parity.py::test_no_new_ir_field_orphans",
    "tests/integration/test_golden_master.py::test_simple_dsl_to_ir_snapshot",
    "tests/unit/test_viewport.py::test_drawer_pattern_selectors_match_current_markup",
    # #1629 G6 compact status.mcp changelog (CI red 2026-07-18 after world-model ship)
    "tests/unit/mcp/test_status_handlers.py::TestNewSinceLastCheck",
    "tests/unit/test_mcp_agent_cognition_1629.py::test_mcp_status_changelog_compact_by_default",
    # HM CONTRACT_SURFACE.md drift (CI red 2026-07-28 after KanbanCard.drill_url)
    "tests/unit/test_contract_surface_tool.py::test_committed_contract_surface_matches_generator",
    # HM dual-lock sole-emitter (CI red 2026-07-29 after tree #1303 drill in
    # _render_charts.py — contract attrs must assemble only under fragment/ingest)
    "tests/unit/test_hm_contract_dom_conformance.py::test_typed_path_is_sole_emitter",
    # HM generated maps after registry/controller ships (CI red 2026-07-30
    # cycle 1499 dz-toggle — CONSUMER_MAP + DUAL_LOCK_COVERAGE drift ×3 Pythons)
    "tests/unit/test_consumer_map_tool.py::test_committed_consumer_map_matches_generator",
    "tests/unit/test_dual_lock_coverage_tool.py::test_committed_coverage_matches_generator",
    # #1648 file-upload picker emit (cycle 2110 — Alpine hollow shell)
    "tests/unit/test_file_upload_primitive.py",
    # cycle 2140: empty form="" fails HM Nu/W3C (search-select leftover)
    "tests/unit/test_form_widget_search_select_phase3.py::test_no_empty_form_attribute_in_search_select_emit_sources",
    "tests/unit/test_form_widget_search_select_phase3.py::test_endpoint_and_typeahead_wiring",
    # cycle 2144: time leftover ISO must not invent a clock
    "tests/unit/test_form_widget_showcase_phase3.py::test_time_controller_leftover_iso_does_not_invent",
    "tests/unit/test_form_field_parity_phase3b.py::test_time_field_emits_iso_companion",
    "tests/unit/test_form_field_parity_phase3b.py::test_datetime_local_field_emits_iso_companion",
    # cycle 2145: standalone date leftover ISO must not invent a date
    "tests/unit/test_form_widget_showcase_phase3.py::test_date_controller_leftover_iso_does_not_invent",
    # cycle 2148: search-box leftover q must not invent Aurora
    "tests/unit/test_form_widget_showcase_phase3.py::test_search_box_mock_leftover_query_does_not_invent",
    "tests/unit/test_form_field_parity_phase3b.py::test_date_field_emits_iso_companion",
    # cycle 2149: standalone number leftover junk must not invent a value
    "tests/unit/test_form_widget_showcase_phase3.py::test_number_controller_leftover_does_not_invent",
    "tests/unit/test_form_field_parity_phase3b.py::test_number_field_emits_companion",
    # cycle 2150: grid-edit leftover ISO must not invent a date commit
    "tests/unit/test_form_widget_showcase_phase3.py::test_grid_edit_controller_leftover_iso_does_not_invent",
    # cycle 2153: grid-edit leftover time ISO must not invent a clock
    "tests/unit/test_form_widget_showcase_phase3.py::test_grid_edit_controller_leftover_time_iso_does_not_invent",
    "tests/unit/test_list_fragment_rows_present_gate.py::test_datetime_column_humanises_and_is_inline_editable",
    # cycle 2155: grid-edit leftover number junk must not invent a value
    "tests/unit/test_form_widget_showcase_phase3.py::test_grid_edit_controller_leftover_number_does_not_invent",
    # cycle 2157: grid leftover page / page_size must not invent a window
    "tests/unit/test_form_widget_showcase_phase3.py::test_grid_controller_leftover_page_does_not_invent",
    # cycle 2162: list leftover page / page_size must not invent an empty window
    "tests/unit/test_list_window_leftover.py",
    # cycle 2164: list leftover sort / filter / q must not invent a fetch
    "tests/unit/test_list_query_leftover.py",
    # cycle 2165: list leftover as_of / InvalidTemporalParam must not invent empty
    "tests/unit/test_list_as_of_leftover.py",
    # cycle 2166: page DETAIL leftover as_of must not invent current / 404
    "tests/unit/test_detail_as_of_leftover.py",
    # cycle 2167: DETAIL related-tab list leftover as_of must not invent current children
    "tests/unit/test_related_tab_as_of_leftover.py",
    # cycle 2168: HTML list include_closed must not invent the open-only collection
    "tests/unit/test_list_include_closed_leftover.py",
    # cycle 2169: bulk all-matching echo include_closed / as_of must not invent 422
    "tests/unit/test_bulk_temporal_echo_leftover.py",
    # cycle 2170: grid ownedKeys / buildQuery drop include_closed / as_of
    "tests/unit/test_grid_temporal_query_leftover.py",
    # cycle 2172: list-region sort-header hx-get drops include_closed / as_of
    "tests/unit/test_list_sort_header_temporal_leftover.py",
    # cycle 2174: list-region CSV data-dz-csv-endpoint drops include_closed / as_of
    "tests/unit/test_list_csv_temporal_leftover.py",
    # cycle 2253: CSV money minor / leftover junk / dict ref must not invent (oral #122)
    "tests/unit/test_csv_export.py::test_csv_money_minor_does_not_invent_raw_pence",
    "tests/unit/test_csv_export.py::test_csv_leftover_money_stays_put",
    "tests/unit/test_csv_export.py::test_csv_dict_ref_does_not_invent_repr",
    # cycle 2258: schema isolation lease must not invent public entity SQL (#1651)
    "tests/unit/test_tenant_connection.py::TestSchemaIsolationFailClosed",
    # cycle 2259: _setup_database isolation read must not break C-1 RLS-halt mock
    "tests/unit/test_rls_runtime_context.py::test_apply_rls_failure_propagates_out_of_setup_database",
    # cycle 2260: entity-list ?format=csv must not invent graph dialect (oral #129)
    "tests/unit/test_list_csv_format.py::test_list_export_kind_csv_is_not_graph",
    "tests/unit/test_list_csv_format.py::test_list_export_kind_leftover_stays_put",
    # cycle 2261: CSV badge must not invent snake_case tokens (oral #130)
    "tests/unit/test_csv_export.py::test_csv_badge_does_not_invent_raw_token",
    "tests/unit/test_csv_export.py::test_csv_leftover_badge_stays_put",
    "tests/unit/test_list_csv_format.py::test_entity_list_csv_badge_does_not_invent_snake_case",
    "tests/unit/test_list_csv_format.py::test_entity_list_csv_datetime_does_not_invent_wall_iso",
    # cycle 2262: CSV format: currency on decimal must not invent bare major units (oral #131)
    "tests/unit/test_csv_export.py::test_csv_format_currency_major_does_not_invent_bare_amount",
    "tests/unit/test_csv_export.py::test_csv_leftover_format_currency_stays_put",
    "tests/unit/test_list_csv_format.py::test_entity_list_csv_format_currency_does_not_invent_bare_amount",
    # cycle 2263: CSV headers must use surface labels, not schema titles (oral #132)
    "tests/unit/test_list_csv_format.py::test_surface_columns_use_author_label_not_schema_title",
    "tests/unit/test_list_csv_format.py::test_surface_columns_empty_label_stays_put_as_schema_title",
    "tests/unit/test_list_csv_format.py::test_entity_list_csv_headers_use_surface_labels",
    # cycle 2264: walk login must read __Host-/__Secure- session cookies (#1652, oral #133)
    "tests/unit/test_session_manager.py::TestSessionTokenFromLoginResponse",
    "tests/unit/test_session_manager.py::TestSessionManagerAsync::test_create_session_login_reads_host_session_cookie",
    # cycle 2267: related status_cards must not dump preview_url as title (oral #135)
    "tests/unit/test_media_thumb_goal_b.py::test_related_card_preview_url_is_thumb_not_title",
    "tests/unit/test_media_thumb_goal_b.py::test_related_card_leftover_url_stays_put",
    "tests/unit/test_related_groups_substrate_phase2.py::test_status_cards_preview_url_is_thumb_not_primary",
    "tests/unit/test_related_groups_substrate_phase2.py::test_status_cards_leftover_preview_stays_put",
    # cycle 2268: queue/timeline must not drop expanded money / title ISO date (oral #136)
    "tests/unit/test_queue_money_title.py",
    "tests/unit/test_queue_display_key.py::test_pick_display_key_skips_date_prefers_currency",
    # cycle 2269: timeline must not title sessions as raw duration minutes (oral #137)
    "tests/unit/test_timeline_duration_title.py",
    "tests/unit/test_queue_display_key.py::test_pick_display_key_skips_duration_prefers_notes",
    # cycle 2270: kanban must not title tasks as snake_case enum tokens (oral #138)
    "tests/unit/test_kanban_enum_title.py",
    "tests/unit/test_queue_display_key.py::test_pick_display_key_does_not_fallback_to_badge",
    "tests/unit/test_queue_display_key.py::test_entity_text_identity_key_notes_on_task",
    # cycle 2271: related file_list must not title the uploader (oral #139)
    "tests/unit/test_related_file_list_title.py",
    # cycle 2272: related/workspace queue must not title attempt numbers (oral #140)
    "tests/unit/test_related_queue_sequence_title.py",
    "tests/unit/test_queue_display_key.py::test_pick_display_key_skips_attempt_prefers_failure_reason",
    # cycle 2273: related salary history must not title the reason enum (oral #141)
    "tests/unit/test_related_queue_money_title.py",
    # cycle 2274: related/workspace conversation must not title ``Jul 2`` (oral #142)
    "tests/unit/test_conversation_clock_title.py",
    # cycle 2275: timeline must rail datetime when, not hide logged_at (oral #143)
    "tests/unit/test_timeline_datetime_rail.py",
    # cycle 2276: funnel/progress must not dump snake_case stage tokens (oral #144)
    "tests/unit/test_funnel_stage_label.py",
    "tests/unit/test_region_adapter.py::test_funnel_chart_renders_dedicated_primitive",
    # cycle 2277: related queue must not title severity/environment (oral #145)
    "tests/unit/test_related_queue_risk_title.py",
    # cycle 2278: workspace bool FilterBar must not dump true/false (oral #146)
    "tests/unit/test_bool_filter_label.py",
    # cycle 2279: workspace enum FilterBar must not dump snake_case (oral #147)
    "tests/unit/test_enum_filter_label.py",
    # cycle 2280: stacked area legend must not dump snake_case (oral #148)
    "tests/unit/test_area_chart_series_label.py",
    "tests/unit/test_timeseries_series_shaping.py::test_pivot_to_series_groups_by_second_dimension",
    # cycle 2282: chart day buckets must not dump ISO storage dates (oral #150)
    "tests/unit/test_chart_day_bucket_label.py",
    # cycle 2283: heatmap group_by must not dump an empty/zero matrix (oral #151)
    "tests/unit/test_heatmap_group_by.py",
    # cycle 2284: insight_summary must not dump aggregate key ``count`` (oral #152)
    "tests/unit/test_insight_measure_noun.py",
    # cycle 2285: comparison league must not dump integer counts as 12.00 (oral #153)
    "tests/unit/test_comparison_whole_count.py",
    # cycle 2286: *_ms measures must not dump unitless numbers (oral #154)
    "tests/unit/test_measure_unit_suffix.py",
    # cycle 2288: 0-100 rate fields must not dump unitless 2.40 (oral #155)
    "tests/unit/test_percent_points_display.py",
    # cycle 2290: queue datetime must not dump storage ISO (oral #156)
    "tests/unit/test_queue_datetime_timeago.py",
    # cycle 2291: entity-card halo/flags must not dump schema keys / raw storage (oral #157)
    "tests/unit/test_entity_card_schema_dump.py",
    # cycle 2292: entity-card quick_actions must use authored surface titles (oral #158)
    "tests/unit/test_quick_action_surface_title.py",
    # cycle 2293: entity-card stamps must not omit history when fields omitted (oral #159)
    "tests/unit/test_entity_card_stamps_chrono.py",
    # cycle 2294: pivot must not leak dimension keys as measure columns (oral #160)
    "tests/unit/test_pivot_measure_leak.py",
    # cycle 2295: pipeline_steps literal values must not become emdash (oral #161)
    "tests/unit/test_pipeline_literal_value.py",
    # cycle 2297: tree group_by scalar must nest folders, not a flat list (oral #163)
    "tests/unit/test_tree_group_by_scalar.py",
    # cycle 2298: tabbed_list group_by must slice status tabs, not dump empty (oral #164)
    "tests/unit/test_tabbed_list_group_by.py",
    # cycle 2299: progress group_by must slice status chips, not dump empty (oral #165)
    "tests/unit/test_progress_group_by.py",
    # cycle 2300: diagram must emit AppSpec ER, not dump empty relationships (oral #166)
    "tests/unit/test_diagram_er.py",
    # cycle 2301: display: map must pin devices, not dump empty locations (oral #167)
    "tests/unit/test_map_empty_dump.py",
    # cycle 2302: display: accordion must emit FAQ panels, not dump empty (oral #168)
    "tests/unit/test_accordion_empty_dump.py",
    # cycle 2303: kanban group_by FK must emit people columns, not dump empty (oral #169)
    "tests/unit/test_kanban_fk_group_by.py",
    # cycle 2304: workspace file cells must not dump storage UUIDs (oral #170)
    "tests/unit/test_workspace_file_uuid_dump.py",
    # cycle 2305: list/queue tags must render chips, not comma blobs (oral #171)
    "tests/unit/test_tags_cell_dump.py",
    # cycle 2306: list/queue 1–5 rating must not dump a bare integer (oral #172)
    "tests/unit/test_rating_cell_dump.py",
    # cycle 2307: list/queue email/phone must be mailto/tel, not dead text (oral #173)
    "tests/unit/test_channel_cell_dump.py",
    # cycle 2308: list/queue temperature must not dump a unitless decimal (oral #174)
    "tests/unit/test_temperature_cell_dump.py",
    # cycle 2309: INT cents amount must not dump raw pence (oral #175)
    "tests/unit/test_int_cents_amount_dump.py",
    # cycle 2310: list/queue IBAN must not dump an ungrouped blob (oral #176)
    "tests/unit/test_iban_cell_dump.py",
    # cycle 2313: audit-history must not dump ISO clocks / snake_case schema (oral #179)
    "tests/unit/test_audit_history_dump.py",
    # cycle 2314: FTS search_box snippets must not dump schema keys (oral #180)
    "tests/unit/test_fts_snippet_field_dump.py",
    # cycle 2315: conversation author suffix must not dump status_page (oral #181)
    "tests/unit/test_conversation_channel_dump.py",
    # cycle 2316: list find-by chrome must not dump schema keys (oral #182)
    "tests/unit/test_list_search_field_dump.py",
    # cycle 2317: related-tab FK disambiguation must not dump assigned to (oral #183)
    "tests/unit/test_related_tab_fk_dump.py",
    # cycle 2318: carousel aspect chip must not dump icon_glyph (oral #184)
    "tests/unit/test_carousel_chip_dump.py",
    # cycle 2319: bar-chart bool group_by must not dump True/False (oral #185)
    "tests/unit/test_bar_chart_bool_dump.py",
    # cycle 2320: bar-chart / badge level tokens must not dump Ic1 (oral #186)
    "tests/unit/test_bar_chart_level_acronym.py",
    # cycle 2321: kanban / badge / FilterBar region tokens must not dump Emea (oral #187)
    "tests/unit/test_region_acronym_dump.py",
    # cycle 2322: radar / box-plot / heatmap axes must not dump api/critical (oral #188)
    "tests/unit/test_chart_axis_dump.py",
    # cycle 2324: temporal workspace as-of snapshot must not be silent (oral #190)
    "tests/unit/test_as_of_snapshot_chrome.py",
    # cycle 2325: shell breadcrumbs must not dump Issuereport (oral #191)
    "tests/unit/test_entity_path_label_dump.py",
    # cycle 2326: mutation toast / fallback detail must not dump IssueReport (oral #192)
    "tests/unit/test_mutation_toast_entity_dump.py",
    # cycle 2328: delete confirm must not dump issuereport (oral #194)
    "tests/unit/test_delete_confirm_entity_dump.py",
    # cycle 2329: signed PDF / list CSV must not dump EngagementLetter (oral #195)
    "tests/unit/test_download_filename_entity_dump.py",
    # cycle 2330: signing ceremony must not dump EngagementLetter as principal (oral #196)
    "tests/unit/test_signing_ceremony_entity_dump.py",
    # cycle 2331: 403 permission speech must not dump EngagementLetter (oral #197)
    "tests/unit/test_forbidden_entity_dump.py",
    # cycle 2332: HTMX form errors must not dump first_name (oral #198)
    "tests/unit/test_form_error_field_dump.py",
    # cycle 2333: state-machine 422 must not dump in_progress (oral #199)
    "tests/unit/test_transition_speech_dump.py",
    # cycle 2335: unique/FK 422 must not dump IssueReport / ticket_number (oral #201)
    "tests/unit/test_constraint_speech_dump.py",
    # cycle 2336: invariant 422 must not dump duration_minutes (oral #202)
    "tests/unit/test_invariant_speech_dump.py",
    # cycle 2337: enum 422 must not dump in_progress / status (oral #203)
    "tests/unit/test_enum_speech_dump.py",
    "tests/unit/test_enum_validation.py::TestEnumEntityModel::test_invalid_enum_rejected",
    # cycle 2338: pydantic type 422 must not dump integer / UUID / date (oral #204)
    "tests/unit/test_type_speech_dump.py",
    # cycle 2339: length/pattern 422 must not dump String / slug must (oral #205)
    "tests/unit/test_string_constraint_speech_dump.py",
    # cycle 2340: decimal scale 422 must not dump Decimal input should (oral #206)
    "tests/unit/test_decimal_constraint_speech_dump.py",
    # cycle 2379: empty-list title must not dump issuereports (oral #213)
    "tests/unit/test_empty_collection_entity_dump.py",
    # cycle 2380: related-tab create CTA must not dump Task · Assigned To (oral #214)
    "tests/unit/test_related_create_cta_dump.py",
    # cycle 2336: unauthored qty invariant still asserted schema/generic
    "tests/unit/test_invariant_evaluator.py::TestViolationError::test_check_update_threads_entity",
    # cycle 2334 cimonitor: all_true checklist 422 still pinned snake_case keys
    "tests/unit/test_composite_guards.py::TestAllTrueGuard::test_all_true_transition_blocked_with_clear_message",
    # cycle 2323 cimonitor: region-adapter smokes still pinned mon/g1/p50 after #188
    "tests/unit/test_region_adapter.py::test_heatmap_renders_dedicated_primitive",
    "tests/unit/test_region_adapter.py::test_alternative_dict_item_shape_normalizes_to_same_render[box_plot]",
    "tests/unit/test_region_adapter.py::test_display_renders_dz_marker_and_item_content[box_plot]",
    # cycle 2289: typed percentage cells must keep % (CI red after 2288 pct→42)
    "tests/unit/test_data_row_characterization_1505.py::TestRenderDataRowParity::test_render_data_row_matches_fixture",
    "tests/unit/test_list_handler_substrate_parity_1505.py::test_build_data_table_rows_match_fixture",
    "tests/unit/test_build_comparison.py::test_renders_ranks_labels_values",
    "tests/unit/test_insight_summary_orchestration.py::test_build_insight_inputs_picks_first_aggregate",
    "tests/unit/test_insight_summary_orchestration.py::test_prefers_aggregate_with_func_over_derived",
    "tests/unit/test_bar_chart_bucketed_aggregate.py::TestTimeBucketedAggregates::test_format_bucket_label_every_unit",
    # cycle 2265: plain-file pdf_viewer must not invent PDF.js on .md/.xlsx (oral #134)
    "tests/unit/test_pdf_viewer_dsl_hook.py::TestTypedRenderer::test_plain_markdown_does_not_invent_pdf_chrome",
    "tests/unit/test_pdf_viewer_dsl_hook.py::TestTypedRenderer::test_plain_pdf_filename_keeps_pdf_chrome",
    "tests/unit/test_pdf_viewer_dsl_hook.py::TestTypedRenderer::test_leftover_filename_does_not_invent_pdf_chrome",
    "tests/unit/test_pdf_viewer_dsl_hook.py::TestTypedRenderer::test_document_route_empty_src_without_file_value",
    # cycle 2257: CSV datetime naive-UTC must not invent wall ISO (oral #126)
    "tests/unit/test_csv_export.py::test_csv_naive_utc_datetime_does_not_invent_wall_iso",
    "tests/unit/test_csv_export.py::test_csv_calendar_date_uses_profile_not_iso",
    "tests/unit/test_csv_export.py::test_csv_leftover_datetime_stays_put",
    "tests/unit/test_csv_export.py::test_csv_bool_uses_yes_no",
    # cycle 2254: timeago future due dates must not invent just now (oral #123)
    "tests/unit/test_workspace_rendering.py::TestTimeagoFilter::test_future_date_does_not_invent_just_now",
    "tests/unit/test_workspace_rendering.py::TestTimeagoFilter::test_due_today_is_today",
    "tests/unit/test_workspace_rendering.py::TestTimeagoFilter::test_future_datetime_does_not_invent_just_now",
    "tests/unit/test_workspace_rendering.py::TestTimeagoFilter::test_leftover_stays_put",
    # cycle 2255: timeago naive UTC must not invent elapsed vs wall now (oral #124)
    "tests/unit/test_workspace_rendering.py::TestTimeagoFilter::test_naive_utc_does_not_invent_elapsed_vs_wall_now",
    # cycle 2256: workspace today must not invent unbounded / whole-book / on-time (oral #125)
    "tests/unit/test_date_expr_eval.py::test_today_is_tenant_calendar",
    "tests/unit/test_cedar_row_filters.py::TestExtractConditionFiltersIR::test_ir_today_lt_does_not_invent_unbounded",
    "tests/unit/test_condition_to_predicate.py::test_today_lt_binds_tenant_calendar",
    "tests/unit/test_workspace_rendering.py::TestAttentionHighlighting::test_today_overdue_does_not_invent_on_time",
    # cycle 2175: list-region _emit_pagination hx-get drops include_closed / as_of
    "tests/unit/test_list_pagination_temporal_leftover.py",
    # cycle 2177: infinite-scroll sentinel _build_table_url_params drops include_closed / as_of
    "tests/unit/test_list_sentinel_temporal_leftover.py",
    # cycle 2178: list search chrome hx-get drops include_closed / as_of
    "tests/unit/test_list_search_temporal_leftover.py",
    # cycle 2179: FilterBar _emit_filter_bar hx-get drops include_closed / as_of
    "tests/unit/test_filter_bar_temporal_leftover.py",
    # cycle 2180: DateRangePicker hx-get drops include_closed / as_of
    "tests/unit/test_date_range_temporal_leftover.py",
    # cycle 2181: kanban overflow Load all hx-get drops include_closed / as_of
    "tests/unit/test_kanban_load_all_temporal_leftover.py",
    # cycle 2182: cohort-strip lens hx-get drops include_closed / as_of
    "tests/unit/test_cohort_strip_lens_temporal_leftover.py",
    # cycle 2184: leftover-honest lens catalog (?lens=ghost must not invent first)
    "tests/unit/test_cohort_strip_lens_catalog_leftover.py",
    # cycle 2185: leftover-honest catalog siblings (tab / filter-enum)
    "tests/unit/test_catalog_sibling_leftover.py",
    # cycle 2186: leftover date_from / date_to must not invent empty window
    "tests/unit/test_date_window_leftover.py",
    # cycle 2187: leftover ?context_id= must not invent current_context
    "tests/unit/test_context_id_leftover.py",
    # cycle 2189: leftover ?id= must not invent empty DETAIL (oral #71 close)
    "tests/unit/test_item_id_leftover.py",
    # cycle 2190: leftover filter_<enum> must not invent empty via fetch
    "tests/unit/test_filter_enum_fetch_leftover.py",
    # cycle 2191: leftover workspace/REST ?sort= must not invent empty via fail-closed
    "tests/unit/test_region_sort_leftover.py",
    # cycle 2192: REST list leftover-honest sort must still ride known fields
    # (2191 pack missed TestListHandlerSort mocks without entity_spec)
    "tests/unit/test_datatable_handler.py::TestListHandlerSort",
    # cycle 2193: leftover REST ?filter[zzz]= must not invent empty via fail-closed
    "tests/unit/test_rest_list_filter_leftover.py",
    "tests/unit/test_datatable_handler.py::TestListHandlerFilter",
    # cycle 2194: leftover REST ?filter[status]=zzz (known key, leftover VALUE)
    "tests/unit/test_rest_list_filter_value_leftover.py",
    # cycle 2195: leftover REST ?filter[id]=zzz (known key, leftover UUID VALUE)
    "tests/unit/test_rest_list_filter_id_leftover.py",
    # cycle 2196: leftover REST ?filter[created_at]=zzz (known key, leftover DATE VALUE)
    "tests/unit/test_rest_list_filter_date_leftover.py",
    # cycle 2197: leftover REST ?filter[is_active]=zzz (known key, leftover BOOL VALUE)
    "tests/unit/test_rest_list_filter_bool_leftover.py",
    # cycle 2198: leftover REST ?filter[amount]=zzz (known key, leftover INT VALUE)
    "tests/unit/test_rest_list_filter_int_leftover.py",
    # cycle 2199: leftover REST ?filter[email]=zzz (known key, leftover EMAIL VALUE)
    "tests/unit/test_rest_list_filter_email_leftover.py",
    # cycle 2200: leftover REST ?filter[preview_url]=zzz (known key, leftover URL VALUE)
    "tests/unit/test_rest_list_filter_url_leftover.py",
    # cycle 2201: leftover REST ?filter[slug]=ab (known key, leftover SLUG VALUE)
    "tests/unit/test_rest_list_filter_slug_leftover.py",
    # cycle 2202: leftover REST ?filter[file]=zzz (known key, leftover FILE VALUE)
    "tests/unit/test_rest_list_filter_file_leftover.py",
    # cycle 2203: leftover REST ?filter[preferences]=zzz (known key, leftover JSON VALUE)
    "tests/unit/test_rest_list_filter_json_leftover.py",
    # cycle 2206: leftover bulk echo filter VALUE must not invent empty mutation
    "tests/unit/test_bulk_filter_value_echo_leftover.py",
    # cycle 2207: leftover experience ?event=zzz must not invent terminal
    "tests/unit/test_experience_event_leftover.py",
    # cycle 2208: leftover onboarding guide/step must not invent completed
    "tests/unit/test_onboarding_step_leftover.py",
    # cycle 2209: leftover membership/invite roles must not invent personas
    "tests/unit/test_persona_role_leftover.py",
    # cycle 2210: leftover consent tokens must not invent granted
    "tests/unit/test_consent_bool_leftover.py",
    # cycle 2212: leftover join-policy tokens must not invent admin_approval
    "tests/unit/test_join_policy_leftover.py",
    # cycle 2215: leftover 2FA ?mode=zzz must not invent totp
    "tests/unit/test_2fa_mode_leftover.py",
    # cycle 2218: leftover 2FA ?sent=zzz must not invent code-sent theater
    "tests/unit/test_2fa_sent_leftover.py",
    # cycle 2221: leftover auth ?error=zzz must not invent a clean page
    "tests/unit/test_auth_error_leftover.py",
    # cycle 2222: leftover auth ?next=zzz must not invent the default landing
    "tests/unit/test_auth_next_leftover.py",
    # cycle 2223: leftover connections ?new=zzz must not invent a clean list
    "tests/unit/test_connection_new_leftover.py",
    # cycle 2224: leftover auth ?token= / ?session= must not invent form theater
    "tests/unit/test_auth_token_leftover.py",
    # cycle 2227: leftover SCIM ?filter= must not invent the unfiltered list
    "tests/unit/test_scim_filter_leftover.py",
    # cycle 2228: leftover SCIM active must not invent inactive / a 200 no-op
    "tests/unit/test_scim_active_leftover.py",
    # cycle 2229: leftover SCIM members must not invent a wipe / empty group
    "tests/unit/test_scim_members_leftover.py",
    # cycle 2230: leftover SCIM userName / emails must not invent a 500 / provision
    "tests/unit/test_scim_username_leftover.py",
    # cycle 2231: leftover SCIM PATCH Operations must not invent a 500 / 200 no-op
    "tests/unit/test_scim_operations_leftover.py",
    # cycle 2232: leftover SCIM displayName must not invent a group / str() rename
    "tests/unit/test_scim_displayname_leftover.py",
    # cycle 2233: leftover auth email must not invent sent theater / persist / default IdP
    "tests/unit/test_auth_email_leftover.py",
    # cycle 2235: leftover mailbox regex was py/polynomial-redos #227
    "tests/unit/test_mailbox_shape.py",
    # cycle 2237: leftover org membership_id must not invent invalid_org theater
    "tests/unit/test_membership_id_leftover.py",
    # cycle 2238: leftover 2FA code must not invent invalid_code theater
    "tests/unit/test_2fa_code_leftover.py",
    # cycle 2239: leftover consume token must not invent invalid theater
    "tests/unit/test_auth_consume_token_leftover.py",
    # cycle 2240: leftover SSO connection id must not invent sso_no_connection
    "tests/unit/test_connection_id_leftover.py",
    # cycle 2241: leftover SCIM externalId must not invent a 500 / persist
    "tests/unit/test_scim_external_id_leftover.py",
    # cycle 2242: leftover SSO provider slug must not invent sso_provider_unknown
    "tests/unit/test_sso_provider_leftover.py",
    # cycle 2243: leftover OAuth code/state must not invent sso_failed
    "tests/unit/test_oauth_code_leftover.py",
    # cycle 2244: leftover SCIM schemas must not invent a provision
    "tests/unit/test_scim_schemas_leftover.py",
    # cycle 2245: leftover SCIM User.groups must not invent a 500 / provision
    "tests/unit/test_scim_groups_leftover.py",
    # cycle 2246: leftover SCIM PatchOp op must not invent a 200 no-op
    "tests/unit/test_scim_patch_op_leftover.py",
    # cycle 2247: leftover search ?entity= must not invent the fleet
    "tests/unit/test_search_entity_leftover.py",
    # cycle 2248: leftover fragment ?source= must not invent 200 empty-result theater
    "tests/unit/test_fragment_source_leftover.py",
    # cycle 2249: leftover connection group_map must not invent a persist
    "tests/unit/test_group_map_leftover.py",
    # cycle 2250: leftover file ?entity= must not invent a persist
    "tests/unit/test_file_entity_leftover.py",
    "tests/unit/test_connection_create_form.py",
    "tests/integration/test_sso_routes.py::test_callback_leftover_code_stays_put",
    "tests/integration/test_sso_routes.py::test_initiate_unknown_provider_stays_put",
    "tests/integration/test_sso_routes.py::test_callback_unknown_provider_stays_put",
    "tests/integration/test_sso_routes.py::test_initiate_when_no_providers_configured_redirects_with_error",
    # cycle 2234: 2233 pack missed chrome-gate 303 vs leftover 400 (×3 Pythons)
    "tests/integration/test_auth_password_mode_chrome_gate.py::test_post_signup_password_leftover_email_stays_put",
    "tests/integration/test_auth_password_mode_chrome_gate.py::test_post_signup_password_blank_email_redirects_with_error",
    "tests/integration/test_auth_signup_magic_link_chrome_gate.py::test_post_signup_malformed_email_stays_put_no_user_no_mail",
    "tests/integration/test_auth_signup_magic_link_chrome_gate.py::test_post_signup_empty_email_redirects_no_user_no_mail",
    # cycle 2225: 2224 pack missed sibling GETs that still used leftover tokens
    "tests/integration/test_auth_password_reset_chrome_gate.py::test_get_reset_password_chrome_on_renders_typed_view_with_token",
    "tests/integration/test_auth_password_reset_chrome_gate.py::test_get_reset_password_renders_mismatch_error",
    "tests/unit/test_2fa_page_routes.py::TestTwoFactorRoutesWithoutAuth::test_challenge_route_returns_200",
    "tests/unit/test_2fa_page_routes.py::TestTwoFactorAuthGuards::test_challenge_is_public_even_with_auth_wired",
    # cycle 2216: leftover-honest form 400 used Response(content=) — #1551
    # byte-route proof red ×3 Pythons. GET already used HTMLResponse.
    "tests/unit/test_byte_route_proof.py",
    # cycle 2183: dashboard-card + master-detail leftover temporal (class close)
    "tests/unit/test_dashboard_card_temporal_leftover.py",
    "tests/unit/test_dual_pane_master_detail.py::test_master_detail_list_echoes_leftover_honest_temporal",
    "tests/unit/test_dual_pane_master_detail.py::test_workspace_typed_threads_temporal_onto_master_detail",
    "tests/unit/test_list_fragment_rows_present_gate.py::test_number_column_is_inline_editable_kind_number",
    "tests/unit/test_grid_edit_ingest.py::test_number_kind_is_a_first_class_seam",
    # cycle 2151: PDF leftover page junk must not invent a page
    "tests/unit/test_form_widget_showcase_phase3.py::test_pdf_controller_leftover_page_does_not_invent",
    # cycle 2152: PDF leftover zoom junk must not invent a scale
    "tests/unit/test_form_widget_showcase_phase3.py::test_pdf_controller_leftover_zoom_does_not_invent",
    # cycle 2156: leftover-zoom prove must not use 1.25 (fit collision)
    "tests/unit/test_form_widget_showcase_phase3.py::test_pdf_leftover_zoom_behaviour_does_not_use_fit_colliding_scale",
    # cycle 2171: setup-uv v8.2.0 still fetched uv.ndjson (GUIDE_WALK flake)
    "tests/unit/test_setup_dazzle_action.py",
    # cycle 2142/2147: stale-red hunt + wait-reset + CI --wait floor
    "tests/unit/test_hm_standalone_ci_status.py",
    # cycle 2146: darwin leftover-honesty must land matching linux visual PNGs
    "tests/unit/test_hm_visual_baseline_pairs.py",
    # cycle 2141: Page chrome #hm-detached-q must not trip no-user-form pins
    "tests/unit/test_error_views.py::test_404_view_renders_no_form",
    "tests/unit/test_error_views.py::test_403_view_renders_no_form",
    "tests/unit/test_error_views.py::test_500_view_renders_no_form",
    "tests/unit/test_auth_views_password_reset.py::test_reset_password_done_view_no_form",
    "tests/unit/test_auth_views_password_reset.py::test_forgot_password_sent_view_does_not_render_form",
    "tests/unit/test_app_error_views.py::test_app_500_no_form_no_inline_script",
    "tests/unit/test_join_request_view.py::test_join_requested_no_form",
    "tests/unit/test_widget_contract.py::test_bridge_kind_allowlist_matches_registry_handlers",
    # AUD-014 list actuators must not crash load_receipt (cycle 2113)
    "tests/unit/test_improve_dig_contracts.py::test_load_receipt_coerces_actuator_name_list",
    "tests/unit/test_improve_dig_contracts.py::TestLiveGreen::test_zero_live_run_is_not_green",
    # #1603 open_via dual-open pins (CI red 2026-08-03 after Goal B document
    # depth on contact_manager — display_field + home region rename ×3 Pythons)
    "tests/unit/test_open_via_1603.py::test_contact_manager_engagement_letter_list_dual_open",
    # open_via + Goal B conversation (CI red 2026-08-03 after llm_ticket
    # display_field→suggested_response — pin must ship with product, not lag)
    "tests/unit/test_open_via_1603.py::test_llm_classification_list_dual_open",
    "tests/unit/test_llm_classifier_conversation_goal_b.py",
    # llm_ticket_classifier Goal B command_density (high severity + open attention)
    "tests/unit/test_llm_classifier_command_density_goal_b.py",
    # llm_ticket_classifier Goal B empty_region_honesty (cycle 1800 prune twin boards/charts)
    "tests/unit/test_llm_classifier_empty_region_goal_b.py",
    # llm_ticket_classifier Goal B org_structure (cycle 1869 team title+dept boards)
    "tests/unit/test_llm_classifier_org_structure_goal_b.py",
    # llm_ticket_classifier Goal B document (cycle 1876 TicketDocument composition)
    "tests/unit/test_llm_classifier_document_goal_b.py",
    "tests/unit/test_design_studio_conversation_goal_b.py",
    # design_studio Goal B media (cycle 1734 asset_catalog thumbs before palette)
    "tests/unit/test_design_studio_media_goal_b.py",
    # design_studio Goal B media home (cycle 1792 studio_dashboard media_shelf)
    "tests/unit/test_design_studio_media_home_goal_b.py",
    # design_studio Goal B media campaign creatives wall (cycle 1803)
    "tests/unit/test_design_studio_campaign_media_goal_b.py",
    # design_studio Goal B command_density (cycle 1836 dual attention before trail)
    "tests/unit/test_design_studio_command_density_goal_b.py",
    # design_studio Goal B document (cycle 1841 DesignDocument composition on Studio/Review)
    "tests/unit/test_design_studio_document_goal_b.py",
    # design_studio Goal B empty_region_honesty (cycle 1856 secondary desk prune)
    "tests/unit/test_design_studio_empty_region_goal_b.py",
    # design_studio Goal B org_structure (cycle 1865 team title+dept boards)
    "tests/unit/test_design_studio_org_structure_goal_b.py",
    # simple_task Goal B document (cycle 1656 TaskBrief composition + dual-open)
    "tests/unit/test_simple_task_document_goal_b.py",
    "tests/unit/test_open_via_1603.py::test_simple_task_brief_list_dual_open",
    # project_tracker Goal B conversation (cycle 1658 Comment display_field + live trail)
    "tests/unit/test_project_tracker_conversation_goal_b.py",
    # project_tracker Goal B org_structure (cycle 1730 people_desk by dept + owners)
    "tests/unit/test_project_tracker_org_structure_goal_b.py",
    # project_tracker Goal B empty_region_honesty (cycle 1815 prune bar charts / twin dumps)
    "tests/unit/test_project_tracker_empty_region_goal_b.py",
    # project_tracker Goal B command_density (cycle 1833 dual attention before trail)
    "tests/unit/test_project_tracker_command_density_goal_b.py",
    # project_tracker Goal B document (cycle 1840 ProjectDocument composition on Dashboard)
    "tests/unit/test_project_tracker_document_goal_b.py",
    # cycle 1714 — person chip + non-person ref Link open discovery (leaf open_discovery)
    "tests/unit/test_ref_link_open_discovery_1714.py",
    # cycle 1719 — create CTA open discovery (CreateButton + empty + related)
    "tests/unit/test_create_cta_open_discovery_1719.py",
    # cycle 1721 — row edit pencil open discovery (VIEW/create parity)
    "tests/unit/test_edit_action_open_discovery_1721.py",
    # cycle 1723 — detail chrome Edit/Create Link open discovery (not VIEW ref)
    "tests/unit/test_detail_edit_link_open_discovery_1723.py",
    # cycle 1805 — ConfirmGate + workspace primary action open discovery
    "tests/unit/test_confirm_gate_open_discovery_1805.py",
    # cycle 1806 — breadcrumb trail open discovery (parent list/detail crumbs)
    "tests/unit/test_breadcrumb_open_discovery_1806.py",
    # cycle 1826 — bare /app/workspaces namespace redirect + crumb not linked
    "tests/unit/test_workspaces_namespace_redirect_1826.py",
    "tests/unit/test_breadcrumbs.py",
    # cycle 1811 — conversation Message open discovery (detail_url_template hub)
    "tests/unit/test_message_open_discovery_1811.py",
    # cycle 1816 — menubar + navigation-menu open discovery (chrome /app hops)
    "tests/unit/test_menubar_nav_menu_open_discovery_1816.py",
    # cycle 1818 — sidebar NavItem open discovery (primary chrome /app hops)
    "tests/unit/test_sidebar_nav_open_discovery_1818.py",
    # cycle 1735 — #1646 detail money _minor/_currency + related tab finger budget
    "tests/unit/test_detail_money_related_budget_1646.py",
    # cycle 1712 — presentation residual delta_theater honesty under 100%
    "tests/unit/test_presentation_residual_1626.py",
    # ops_dashboard Goal B conversation (cycle 1660 IncidentNote + command_center trail)
    "tests/unit/test_ops_dashboard_conversation_goal_b.py",
    # ops_dashboard Goal B command_density (cycle 1728 dual attention before trail)
    "tests/unit/test_ops_dashboard_command_density_goal_b.py",
    # ops_dashboard Goal B document (cycle 1839 OpsDocument composition on command_center)
    "tests/unit/test_ops_dashboard_document_goal_b.py",
    # ops_dashboard Goal B org_structure (cycle 1859 systems_desk service/status boards)
    "tests/unit/test_ops_dashboard_org_structure_goal_b.py",
    # invoice_ops Goal B conversation (cycle 1662 InvoiceNote + finance desks)
    "tests/unit/test_invoice_ops_conversation_goal_b.py",
    # invoice_ops Goal B document (cycle 1724 composition on finance_ops/my_invoices)
    "tests/unit/test_invoice_ops_document_goal_b.py",
    # invoice_ops Goal B command_density (cycle 1793 pay_desk dual attention)
    "tests/unit/test_invoice_ops_command_density_goal_b.py",
    # cycle 1820 — Goal B empty_region honesty @invoice_ops primary desks
    "tests/unit/test_invoice_ops_empty_region_goal_b.py",
    # invoice_ops Goal B media (cycle 1884 concurrent)
    "tests/unit/test_invoice_ops_media_goal_b.py",
    # invoice_ops Goal B org_structure (cycle 1863 team title+dept + suppliers region boards)
    "tests/unit/test_invoice_ops_org_structure_goal_b.py",
    # contact_manager Goal B conversation (cycle 1664 ContactNote + home trail)
    "tests/unit/test_contact_manager_conversation_goal_b.py",
    # contact_manager Goal B command_density (cycle 1830 dual attention before trail)
    "tests/unit/test_contact_manager_command_density_goal_b.py",
    # contact_manager Goal B empty_region_honesty (cycle 1742 Home/Contacts/Companies prune)
    "tests/unit/test_contact_manager_empty_region_goal_b.py",
    # contact_manager Goal B document (cycle 1845 EngagementLetter composition pin)
    "tests/unit/test_contact_manager_document_goal_b.py",
    # contact_manager Goal B org_structure (cycle 1861 companies title board + multi-person accounts)
    "tests/unit/test_contact_manager_org_structure_goal_b.py",
    # domain_join_co Goal B conversation (cycle 1666 AnnouncementNote + home/board)
    "tests/unit/test_domain_join_conversation_goal_b.py",
    # domain_join_co Goal B command_density (cycle 1831 dual attention before trail)
    "tests/unit/test_domain_join_command_density_goal_b.py",
    # domain_join_co Goal B empty_region_honesty (cycle 1733 Team Board prune)
    "tests/unit/test_domain_join_empty_region_goal_b.py",
    # domain_join_co Goal B document (cycle 1844 WorkspaceDocument composition)
    "tests/unit/test_domain_join_document_goal_b.py",
    # domain_join_co Goal B org_structure (cycle 1869 team title+dept boards)
    "tests/unit/test_domain_join_org_structure_goal_b.py",
    # hr_records Goal B conversation (cycle 1668 PersonNote + staff trail)
    "tests/unit/test_hr_records_conversation_goal_b.py",
    # hr_records Goal B org_structure (cycle 1731 my_team level/dept boards)
    "tests/unit/test_hr_records_org_structure_goal_b.py",
    # hr_records Goal B media (cycle 1879 staff_directory media_shelf headshots)
    "tests/unit/test_hr_records_media_goal_b.py",
    # hr_records Goal B empty_region_honesty (cycle 1819 staff + my_team prune)
    "tests/unit/test_hr_records_empty_region_goal_b.py",
    # hr_records Goal B command_density (cycle 1837 dual attention before trail)
    "tests/unit/test_hr_records_command_density_goal_b.py",
    "tests/unit/test_hr_records_document_goal_b.py",
    # fieldtest_hub Goal B conversation (cycle 1671 IssueNote + ops/triage trail)
    "tests/unit/test_fieldtest_conversation_goal_b.py",
    # fieldtest_hub Goal B command_density (cycle 1726 manager_ops dual attention)
    "tests/unit/test_fieldtest_command_density_goal_b.py",
    # fieldtest_hub Goal B document (cycle 1843 TestDocument composition on eng/ops)
    "tests/unit/test_fieldtest_document_goal_b.py",
    # fieldtest_hub Goal B org_structure (cycle 1848 tester_roster skill+region)
    "tests/unit/test_fieldtest_org_structure_goal_b.py",
    # fieldtest_hub Goal B empty_region_honesty (cycle 1855 secondary desk prune)
    "tests/unit/test_fieldtest_empty_region_goal_b.py",
    # simple_task Goal B conversation (cycle 1674 TaskComment live trail)
    "tests/unit/test_simple_task_conversation_goal_b.py",
    # simple_task Goal B command_density (cycle 1835 dual attention before trail)
    "tests/unit/test_simple_task_command_density_goal_b.py",
    # simple_task Goal B org_structure (cycle 1732 people_desk by role + dept)
    "tests/unit/test_simple_task_org_structure_goal_b.py",
    # simple_task Goal B empty_region_honesty (cycle 1817 prune charts/twin dumps)
    "tests/unit/test_simple_task_empty_region_goal_b.py",
    # simple_task Goal B media (cycle 1884 admin/team media_shelf headshots)
    "tests/unit/test_simple_task_media_goal_b.py",
    # framework null-default / null-filter (cycle 1884)
    "tests/unit/test_scope_filters_null_ne.py",
    # framework null-default / null-filter (cycle 1884)
    "tests/unit/test_repository_null_bool_default.py",
    # acme_billing Goal B conversation (InvoiceNote live trail on billing desks)
    "tests/unit/test_acme_billing_conversation_goal_b.py",
    # acme_billing Goal B document (LineItem composition + line_kind_density)
    "tests/unit/test_acme_billing_document_goal_b.py",
    # acme_billing Goal B command_density (open+sensitive dual attention)
    "tests/unit/test_acme_billing_command_density_goal_b.py",
    # acme_billing Goal B empty_region_honesty (cycle 1828 primary desks prune)
    "tests/unit/test_acme_billing_empty_region_goal_b.py",
    # acme_billing Goal B org_structure (cycle 1867 team title+dept boards)
    "tests/unit/test_acme_billing_org_structure_goal_b.py",
    # Goal B coat freeze (conversation/rail/focus/metric ratchet — must not grow)
    "tests/unit/test_goal_b_coat.py",
    "tests/unit/test_interesting_product_portfolio.py",
    # support_tickets Goal B conversation (Comment display_field + manager_ops trail)
    "tests/unit/test_support_tickets_conversation_goal_b.py",
    # support_tickets Goal B command_density (cycle 1727 manager_ops dual attention)
    "tests/unit/test_support_tickets_command_density_goal_b.py",
    # support_tickets Goal B org_structure (cycle 1847 people_desk role+dept)
    "tests/unit/test_support_tickets_org_structure_goal_b.py",
    # support_tickets Goal B document (cycle 1798 SlaWaiver composition + dual-open)
    "tests/unit/test_support_tickets_document_goal_b.py",
    "tests/unit/test_open_via_1603.py::test_support_tickets_sla_waiver_list_dual_open",
    # support_tickets Goal B empty_region (cycle 1812 agent_dashboard + my_tickets prune)
    "tests/unit/test_support_tickets_empty_region_goal_b.py",
    # cycle 2087: context_selector.filter emptied INTERACTION_WALK + PG e2e
    # when UX User fixtures skipped department/support_tier (NULL != External).
    "tests/unit/test_ux_fixtures.py::TestFixtureGeneration::test_support_tickets_user_fixtures_pass_staff_selector_filter",
    # cycle 2089: INTERACTION_WALK must seed (same as --contracts) or
    # context_selector.filter sees only the login User and stays empty.
    "tests/unit/test_cli_ux_interactions.py::TestSeedInteractionApp::test_sets_secret_and_delegates_to_reset_and_seed",
    # support_tickets Goal B media (cycle 1883 headshot shelf; cycle 2044 pin lag
    # after priority_awaiting_customer focus strip ×3 Pythons — conversation/
    # command_density/empty_region were already in ship-surface; media was not)
    "tests/unit/test_support_tickets_media_goal_b.py",
    # acme_billing reference drift (CI red 2026-08-03 after Goal B LineItem —
    # compliance auditspec dsl_hash / RBAC matrix ×3 Pythons; ship-surface
    # previously green while main matrix red)
    "tests/unit/test_acme_billing_reference_drift.py",
    # cycle 2378 cimonitor: example_hub supervisor `from registry` shadowed
    # by packages/hatchi-maxchi/site/registry.py under pytest-xdist
    "tests/unit/test_example_eval_hub.py::TestSupervisorOurs::test_load_survives_hm_registry_shadow",
)

REMEDIATION = """
╔══════════════════════════════════════════════════════════════════════╗
║  SHIP-SURFACE FAILED — recurrent badge-red class                     ║
║  Do NOT ship or tag until this is green.                             ║
╚══════════════════════════════════════════════════════════════════════╝

Remediation by class (run from repo root):

  Bandit (B3xx / medium severity on src/)
    uv pip install 'bandit[toml]'
    bandit -c pyproject.toml -r src/ --severity-level medium
    # fix finding (e.g. hashlib.sha1(..., usedforsecurity=False) for non-crypto)

  Example SPECIFICATION.md stale / structure
    # DSL changed → refresh footer fingerprints (and add ## sections if needed):
    .venv/bin/python -c "from dazzle.spec_narrative.brief import build_brief, brief_fingerprint; ..."
    # or re-run /spec-narrate for prose; footer must match:
    #   dazzle spec brief -p examples/<app> --fingerprint
    pytest tests/unit/test_example_spec_bar.py -q

  Product maturity residual (example fleet warehouse-shaped)
    python scripts/example_product_maturity.py --strict
    # Fix: job workspaces + persona default_workspace (not more entity lists).
    # Docs: docs/reference/product-maturity.md
    # Improve: /improve example-apps product_maturity
    pytest tests/unit/test_example_product_maturity.py -q

  Demo fleet residual (#1626 nav/seed/stills floors)
    python scripts/demo_fleet_bar.py --strict
    # Fix: product nav isolation, blueprint mins, product stills (not only platform).
    # Improve: /improve example-apps demo_fleet
    pytest tests/unit/test_demo_fleet_bar.py -q

  Unified example probes (product + demo + journey for /improve OBSERVE)
    python scripts/improve_example_probes.py --status
    python scripts/improve_example_probes.py --strict
    pytest tests/unit/test_improve_example_probes.py -q

  simple_task brief golden
    dazzle spec brief -p examples/simple_task -f json \\
      > tests/unit/baselines/spec_brief_simple_task.json
    # review diff + CHANGELOG if public shape changed

  IR golden snapshot
    pytest tests/integration/test_golden_master.py::test_simple_dsl_to_ir_snapshot \\
      --snapshot-update -q
    # review tests/integration/__snapshots__/

  patterns.toml pattern_count
    # set [meta].pattern_count to the actual [patterns.X] entry count

  IR reader orphan baseline
    # remove resolved orphans from tests/unit/fixtures/ir_reader_baseline.json
    # (message lists the field paths)

  Viewport DRAWER_PATTERN freshness
    # selector must match AppShell chrome (chrome + rail toggles when open).
    # See tests/unit/test_viewport.py::_render_app_shell_chrome
    pytest tests/unit/test_viewport.py::test_drawer_pattern_selectors_match_current_markup -q

  HM CONTRACT_SURFACE.md stale (KanbanCard / model field adds)
    uv run python packages/hatchi-maxchi/tools/contract_surface.py --write
    # review packages/hatchi-maxchi/CONTRACT_SURFACE.md; commit with the field ship
    pytest tests/unit/test_contract_surface_tool.py::test_committed_contract_surface_matches_generator -q

  HM CONSUMER_MAP.md / DUAL_LOCK_COVERAGE.md stale (new controller or guidance)
    uv run python packages/hatchi-maxchi/tools/consumer_map.py --write
    uv run python packages/hatchi-maxchi/tools/dual_lock_coverage.py --write
    # commit regenerated maps with the registry/controller ship
    pytest tests/unit/test_consumer_map_tool.py::test_committed_consumer_map_matches_generator -q
    pytest tests/unit/test_dual_lock_coverage_tool.py::test_committed_coverage_matches_generator -q

  Generated surfaces dirty (catalogue md/css + CONTRACT_SURFACE)
    .venv/bin/python scripts/gen_surface_check.py   # diagnose
    .venv/bin/python scripts/gen_ux_catalogue.py
    uv run python packages/hatchi-maxchi/tools/contract_surface.py --write
    # commit regenerated files; do not ship with dirty gen outputs

  open_via dual-open pin (Goal B display_field / home region renames)
    # Goal B depth may change display_field / home region names — update
    # tests/unit/test_open_via_1603.py pins with the product ship (same commit).
    pytest tests/unit/test_open_via_1603.py::test_contact_manager_engagement_letter_list_dual_open -q
    pytest tests/unit/test_open_via_1603.py::test_llm_classification_list_dual_open -q
    pytest tests/unit/test_llm_classifier_conversation_goal_b.py tests/unit/test_design_studio_conversation_goal_b.py -q

  acme_billing RBAC matrix / compliance auditspec drift
    # After DSL entity/permit/scope changes on examples/acme_billing:
    cd examples/acme_billing
    python -m dazzle rbac matrix --format json > expected/rbac-matrix.json
    dazzle compliance compile
    python3 -c "import json; from pathlib import Path; d=json.loads(Path('.dazzle/compliance/output/iso27001/auditspec.json').read_text()); d.pop('generated_at', None); d.pop('dsl_source', None); Path('expected/compliance-auditspec.json').write_text(json.dumps(d, indent=2)+chr(10))"
    # CHANGELOG under Changed/Fixed; then:
    pytest tests/unit/test_acme_billing_reference_drift.py -q

Re-run:
  make ship-surface
  # then: make ci-fast

See: docs/contributing/local-ci-concordance.md (Tier 0.5 ship-surface)
After a GitHub CI repair, **promote new recurrent classes into this pack**
(or preflight-surface) — do not fix-only (cimonitor close-the-loop).
"""


def _python() -> str:
    venv_py = REPO / ".venv" / "bin" / "python"
    if venv_py.is_file():
        return str(venv_py)
    return sys.executable


def _bandit_cmd() -> list[str] | None:
    """Return bandit argv or None if bandit cannot be invoked."""
    py = _python()
    # Prefer module form so venv-only installs work without a script on PATH.
    return [py, "-m", "bandit", "-c", "pyproject.toml", "-r", "src/", "--severity-level", "medium"]


def run_bandit(*, quiet: bool = False) -> int:
    cmd = _bandit_cmd()
    if cmd is None:
        print("ship-surface: bandit not available", file=sys.stderr)
        return 2
    if not quiet:
        print("==> ship-surface: bandit (medium, src/)")
    # Ensure bandit is importable; CI installs bandit[toml] on the fly.
    probe = subprocess.run(
        [_python(), "-c", "import bandit"],
        cwd=REPO,
        check=False,
        capture_output=True,
    )
    if probe.returncode != 0:
        # Match ci_local.sh / CI: uv pip install when missing.
        uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
        if Path(uv).is_file() or shutil.which("uv"):
            uv_bin = uv if Path(uv).is_file() else "uv"
            if not quiet:
                print("    installing bandit[toml] via uv pip …")
            inst = subprocess.run(
                [uv_bin, "pip", "install", "bandit[toml]"],
                cwd=REPO,
                check=False,
            )
            if inst.returncode != 0:
                print(
                    "ship-surface: failed to install bandit[toml] — "
                    "run: uv pip install 'bandit[toml]'",
                    file=sys.stderr,
                )
                return 2
        else:
            print(
                "ship-surface: bandit not installed and uv not found — "
                "run: uv pip install 'bandit[toml]'",
                file=sys.stderr,
            )
            return 2
    proc = subprocess.run(cmd, cwd=REPO, check=False)
    return proc.returncode


def run_ship_tests(*, quiet: bool = False) -> int:
    missing = []
    for node in SHIP_TESTS:
        path = node.split("::", 1)[0]
        if not (REPO / path).is_file():
            missing.append(path)
    if missing:
        print("ship-surface: missing test modules:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 2

    py = _python()
    cmd = [py, "-m", "pytest", *SHIP_TESTS, "-q", "--tb=line"]
    if not quiet:
        print("==> ship-surface: recurrent unit pack")
        for t in SHIP_TESTS:
            print(f"    {t}")
        print(f"    interpreter: {py}")
    return subprocess.run(cmd, cwd=REPO, check=False).returncode


def run_gen_surface(*, quiet: bool = False) -> int:
    """Committed catalogue + CONTRACT_SURFACE must match generators (no write)."""
    py = _python()
    script = REPO / "scripts" / "gen_surface_check.py"
    if not script.is_file():
        print("ship-surface: missing scripts/gen_surface_check.py", file=sys.stderr)
        return 2
    if not quiet:
        print("==> ship-surface: gen-surface-check (catalogue + CONTRACT_SURFACE)")
    return subprocess.run(
        [py, str(script), *(["--quiet"] if quiet else [])],
        cwd=REPO,
        check=False,
    ).returncode


def run_ship_surface(*, quiet: bool = False, skip_bandit: bool = False) -> int:
    if not skip_bandit:
        brc = run_bandit(quiet=quiet)
        if brc != 0:
            print(REMEDIATION, file=sys.stderr)
            return 1
    trc = run_ship_tests(quiet=quiet)
    if trc != 0:
        print(REMEDIATION, file=sys.stderr)
        return 1
    # Post-gen dirty check — closes "feature tests green, generated artifacts stale"
    # (24h CI autopsy 2026-07-28). Contract nodeid is also in SHIP_TESTS; this
    # adds catalogue --mode=ci + unified remediation for both.
    grc = run_gen_surface(quiet=quiet)
    if grc != 0:
        print(REMEDIATION, file=sys.stderr)
        return 1
    if not quiet:
        print("OK ship-surface clean")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fail on recurrent badge-red classes (bandit + SPEC/IR/viewport pack). "
            "Part of Tier 0 / make ci-fast after preflight-surface."
        )
    )
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print ship test nodeids and exit 0",
    )
    parser.add_argument(
        "--skip-bandit",
        action="store_true",
        help="Run only the pytest pack (bandit already ran elsewhere)",
    )
    args = parser.parse_args(argv)
    if args.list:
        print("bandit -c pyproject.toml -r src/ --severity-level medium")
        for p in SHIP_TESTS:
            print(p)
        return 0
    return run_ship_surface(quiet=args.quiet, skip_bandit=args.skip_bandit)


if __name__ == "__main__":
    raise SystemExit(main())
