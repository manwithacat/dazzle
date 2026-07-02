# Test Redundancy Report — Pass 2 (coarse)

Clusters where ≥3 tests in the same file/class share the same assertion-shape signature. Strong candidates for `@pytest.mark.parametrize` consolidation.

## Headline numbers

- **Clusters of ≥3**: 1,030
- **Tests inside those clusters**: 4,180
- **Theoretical saving** if every cluster collapsed to one parametrised test: **3,150 tests** (≈ 22.0% of the suite)

Caveats: not every cluster *should* collapse — sometimes independent test names carry intentional documentation value. The report below is ranked by size; larger clusters are more likely to genuinely benefit from consolidation.

## Cluster size distribution

| Size | Clusters |
|---|---:|
| 20+ | 6 |
| 10-19 | 28 |
| 5-9 | 146 |
| 3-4 | 850 |

## Top 30 largest clusters

| File | Class | Size | Sample test names |
|---|---|---:|---|
| `tests/unit/test_region_adapter.py` | `(module)` | 48 | test_timeline_no_items_renders_empty_state, test_list_empty_renders_empty_state, test_list_csv_export_filename_override… |
| `tests/unit/test_auth_connection_cli.py` | `(module)` | 29 | test_delete_missing, test_add_domain_missing_connection, test_verify_domain_not_found_prints_record… |
| `tests/unit/render/fragment/test_data_primitives.py` | `(module)` | 25 | test_table_columns_and_rows, test_kpi_basic, test_bar_chart_buckets… |
| `tests/unit/test_cohort_strip_data_resolution.py` | `(module)` | 25 | test_returns_empty_when_no_items, test_returns_empty_when_config_missing, test_resolves_member_name_from_fk_display_dict… |
| `tests/unit/test_card_template_transforms_1145.py` | `(module)` | 20 | test_minutes_until_future_minutes, test_minutes_until_one_minute_singular, test_minutes_until_now_when_within_a_minute… |
| `tests/unit/test_python_audit_magic_string_typing.py` | `(module)` | 20 | test_tenant_uuid_str_param_fires, test_bare_id_param_fires, test_key_suffix_fires… |
| `tests/unit/test_python_audit_n_plus_one.py` | `(module)` | 19 | test_queryset_chain_all, test_queryset_chain_first, test_queryset_chain_filter_terminator… |
| `tests/unit/test_region_adapter.py` | `(module)` | 17 | test_grid_uses_label_field_override, test_metrics_invalid_tone_coerced_to_default, test_metrics_no_delta_omits_delta_block… |
| `tests/unit/test_region_adapter.py` | `(module)` | 16 | test_timeline_overflow_line_renders_when_total_exceeds_items, test_list_with_csv_export_renders_button, test_metrics_falls_back_to_aggregates_dict… |
| `tests/unit/test_auto_display_1492.py` | `(module)` | 14 | test_scalar_aggregate_to_summary, test_single_dim_aggregate_to_bar_chart, test_multi_dim_aggregate_to_pivot_table… |
| `tests/unit/test_onboarding_renderer.py` | `(module)` | 14 | test_popover_default_cta_label_when_unset, test_popover_custom_cta_label_when_set, test_popover_cta_href_when_target_set… |
| `tests/unit/test_onboarding_resolver.py` | `(module)` | 14 | test_audience_matches_when_persona_clause_includes_user, test_audience_with_or_clauses_matches_any, test_audience_excludes_when_user_persona_not_listed… |
| `tests/unit/test_python_audit_exceptions.py` | `(module)` | 13 | test_silent_swallow_except_exception_pass, test_silent_swallow_negative_specific_recovery, test_fallback_control_flow_literal_default… |
| `tests/unit/test_python_audit_optional_instead_of_result.py` | `(module)` | 13 | test_three_return_none_fires_once, test_optional_legacy_syntax, test_pipe_none_left_position… |
| `tests/unit/test_region_adapter.py` | `(module)` | 13 | test_kanban_renders_to_html_with_dz_kanban_marker, test_list_renders_with_table, test_list_with_date_range_renders_picker… |
| `tests/unit/test_site_section_medium_builders.py` | `(module)` | 13 | test_stats_emits_section_class_and_stats_wrapper, test_steps_emits_section_class, test_comparison_emits_section_class_and_table… |
| `tests/unit/test_auth_cookie_name.py` | `(module)` | 12 | test_select_write_name_legacy_app_returns_dazzle_session, test_select_write_name_tenant_host_request_returns_host_cookie, test_select_write_name_canonical_host_non_admin_returns_host_cookie… |
| `tests/unit/test_cedar_row_filters.py` | `TestExtractCedarRowFilters` | 12 | test_owner_equals_current_user, test_read_rule_also_applies, test_non_list_read_rules_ignored… |
| `tests/unit/test_enum_semantics_1493.py` | `(module)` | 12 | test_canonical_palette_is_the_five_css_tones, test_positive_aliases_success, test_normalize_is_case_insensitive… |
| `tests/unit/test_onboarding_page_wiring.py` | `(module)` | 12 | test_page_context_active_guide_html_defaults_empty, test_page_context_active_guide_html_is_settable, test_render_typed_body_prepends_active_guide_html… |
| `tests/unit/test_rhythm_mcp.py` | `(module)` | 12 | test_get_rhythm_includes_phase_kind, test_get_rhythm_includes_phase_cadence, test_gaps_unmapped_scene… |
| `tests/integration/test_scim_routes.py` | `(module)` | 11 | test_no_bearer_is_401, test_bad_bearer_is_401, test_create_user_unverified_domain_is_400… |
| `tests/unit/test_anti_turing.py` | `TestAntiTuringValidator` | 11 | test_valid_entity_declaration, test_valid_surface_declaration, test_valid_workspace_with_filter… |
| `tests/unit/test_atomic_flow_parser.py` | `TestAtomicFlowValidator` | 11 | test_valid_flow_no_errors, test_unknown_create_target_errors, test_unknown_assignment_field_errors… |
| `tests/unit/test_day_timeline_data_resolution.py` | `(module)` | 11 | test_returns_empty_when_no_items, test_returns_empty_when_config_missing, test_skips_rows_with_missing_starts_at… |
| `tests/unit/test_guide_concordance.py` | `(module)` | 11 | test_target_must_start_with_surface, test_target_unknown_surface_errors, test_target_unknown_action_errors… |
| `tests/unit/test_partition_root_1463.py` | `(module)` | 11 | test_resolve_leaf_walks_to_root, test_resolve_mid_walks_to_root, test_resolve_root_id_returns_itself… |
| `tests/unit/test_schema_render.py` | `(module)` | 11 | test_add_table_renders_create_table, test_add_column_renders_add_and_inverse_drop, test_drop_table_renders_drop_and_inverse_create… |
| `tests/integration/test_saml_routes.py` | `(module)` | 10 | test_login_redirects_to_idp, test_login_resolves_by_verified_email_domain, test_sls_kills_only_the_connections_org_sessions… |
| `tests/unit/render/fragment/test_data_primitives.py` | `(module)` | 10 | test_profile_card_holds_stats_and_facts_immutably, test_metric_tile_full_delta_block, test_stage_bar_minimal… |

## Top 10 files by collapse-saving potential

| File | Tests that could collapse |
|---|---:|
| `tests/unit/test_region_adapter.py` | 122 |
| `tests/unit/test_auth_connection_cli.py` | 36 |
| `tests/unit/render/fragment/test_data_primitives.py` | 33 |
| `tests/unit/test_rhythm_mcp.py` | 29 |
| `tests/unit/test_anti_turing.py` | 27 |
| `tests/unit/test_expression_lang.py` | 27 |
| `tests/unit/test_cedar_row_filters.py` | 25 |
| `tests/unit/test_schema_diff.py` | 25 |
| `tests/unit/test_rbac_verifier.py` | 25 |
| `tests/unit/test_cohort_strip_data_resolution.py` | 24 |

## Fuzz-target worklist (property/fuzz-candidate clusters)

Clusters whose subject is an input-boundary surface (parser/validator/crypto/…). Each is a candidate to collapse into ONE property test (input space → invariant) — which then becomes a fuzz target — rather than a fixed `@pytest.mark.parametrize` list. Path-based hint; confirm by reading the cluster. (#1342)

- **Property/fuzz-candidate clusters**: 119

| File | Class | Size | Form | Why |
|---|---|---:|---|---|
| `tests/integration/test_scim_routes.py` | `(module)` | 11 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_atomic_flow_parser.py` | `TestAtomicFlowValidator` | 11 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/integration/test_saml_routes.py` | `(module)` | 10 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_saml_metadata.py` | `(module)` | 9 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_scope_create_eval.py` | `(module)` | 9 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/integration/test_scim_routes.py` | `(module)` | 8 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_scope_create_eval.py` | `(module)` | 7 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/integration/test_saml_routes.py` | `(module)` | 6 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/integration/test_scope_runtime_pg.py` | `(module)` | 6 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/render/fragment/test_renderer_asset_url_1137.py` | `(module)` | 6 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_predicate_policy_mode.py` | `TestInlineLiteral` | 6 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_validator.py` | `TestValidateNavCuration` | 6 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/integration/test_scope_runtime_pg.py` | `(module)` | 5 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_comparison_validation.py` | `(module)` | 5 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_descendants_of_parser.py` | `TestDescendantsOfValidator` | 5 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_format_validation.py` | `(module)` | 5 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_scim_provisioning.py` | `(module)` | 5 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_scim_provisioning.py` | `(module)` | 5 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_tenant_host_validator.py` | `(module)` | 5 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_validator.py` | `TestValidateNavCuration` | 5 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_action_url_surface_resolution.py` | `(module)` | 4 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_agent_parser.py` | `TestParseActionTier2` | 4 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_atomic_flow_parser.py` | `TestAtomicFlowParser` | 4 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_auth_identity_validation.py` | `TestAuthIdentityValidation` | 4 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_copy_parser.py` | `TestParseCopyFile` | 4 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_copy_parser.py` | `TestMergeCopyIntoSitespec` | 4 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_day_timeline_config_parser.py` | `(module)` | 4 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_db_url.py` | `TestNormalisePostgresScheme` | 4 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_db_url.py` | `TestAddPsycopgDriver` | 4 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_entity_card_config_parser.py` | `(module)` | 4 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |

## How to act on this

1. Pick the largest cluster (top of the list above). Open the file. Read 3 of the cluster's member tests.
2. If they vary only on input data, collapse to one `@pytest.mark.parametrize` test. Each removed test removes a name + a fixture setup + a maintenance burden, but no protective signal (the parametric form runs the same N cases).
3. If they assert genuinely different things despite shared shape, tag the cluster as `keep_all` in `redundancy.json` so the next audit cycle skips it.
4. Re-run `python3 scripts/distill/classify.py` and `python3 scripts/distill/cluster.py` to confirm the cluster is gone.
