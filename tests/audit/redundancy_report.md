# Test Redundancy Report — Pass 2 (coarse)

Clusters where ≥3 tests in the same file/class share the same assertion-shape signature. Strong candidates for `@pytest.mark.parametrize` consolidation.

## Headline numbers

- **Clusters of ≥3**: 1,029
- **Tests inside those clusters**: 4,066
- **Theoretical saving** if every cluster collapsed to one parametrised test: **3,037 tests** (≈ 21.2% of the suite)

Caveats: not every cluster *should* collapse — sometimes independent test names carry intentional documentation value. The report below is ranked by size; larger clusters are more likely to genuinely benefit from consolidation.

## Cluster size distribution

| Size | Clusters |
|---|---:|
| 20+ | 0 |
| 10-19 | 10 |
| 5-9 | 225 |
| 3-4 | 794 |

## Top 30 largest clusters

| File | Class | Size | Sample test names |
|---|---|---:|---|
| `tests/unit/test_cedar_row_filters.py` | `TestExtractCedarRowFilters` | 12 | test_owner_equals_current_user, test_read_rule_also_applies, test_non_list_read_rules_ignored… |
| `tests/unit/test_rhythm_mcp.py` | `(module)` | 12 | test_get_rhythm_includes_phase_kind, test_get_rhythm_includes_phase_cadence, test_gaps_unmapped_scene… |
| `tests/unit/test_anti_turing.py` | `TestAntiTuringValidator` | 11 | test_valid_entity_declaration, test_valid_surface_declaration, test_valid_workspace_with_filter… |
| `tests/unit/test_workspace_routes.py` | `TestAttentionAccentMacro` | 11 | test_border_critical_destructive, test_border_warning_warning, test_border_notice_primary… |
| `tests/unit/test_anti_turing.py` | `TestAntiTuringValidator` | 10 | test_banned_if_keyword, test_banned_for_keyword, test_banned_while_keyword… |
| `tests/unit/test_fidelity_scorer.py` | `TestMoneyFieldExpansion` | 10 | test_expand_field_names_helper, test_expand_money_field_in_form, test_money_widget_data_attribute_match… |
| `tests/unit/test_fidelity_scorer.py` | `TestWidgetRenderedInputTypes` | 10 | test_datepicker_on_date_field, test_datepicker_on_datetime_field, test_range_slider_on_int_field… |
| `tests/unit/test_graph_semantics.py` | `TestGraphValidationErrors` | 10 | test_source_field_not_found, test_target_field_not_found, test_source_not_ref_type… |
| `tests/unit/test_url_consistency.py` | `TestResolveBackendUrl` | 10 | test_local_dev_uses_fallback, test_local_dev_uses_base_url, test_single_dyno_uses_port… |
| `tests/unit/test_viewport_suggestions.py` | `TestSuggestFix` | 10 | test_display_grid_tablet, test_display_grid_desktop, test_display_grid_wide… |
| `tests/unit/test_api_packs.py` | `TestFormatDuration` | 9 | test_days, test_hours, test_24_hours… |
| `tests/unit/test_compliance_matching.py` | `TestNeutralizingContext` | 9 | test_ip_address_rejected, test_mac_address_rejected, test_wallet_address_rejected… |
| `tests/unit/test_computed_evaluator.py` | `TestAggregateExpression` | 9 | test_count, test_count_empty, test_sum… |
| `tests/unit/test_condition_evaluator_grant_check.py` | `TestGrantCheckEvaluation` | 9 | test_grant_check_true, test_grant_check_false_wrong_relation, test_grant_check_false_wrong_scope… |
| `tests/unit/test_qa_trial.py` | `TestBuildTrialMission` | 9 | test_mission_name_incorporates_scenario, test_start_url_points_at_app, test_starting_url_relative_path_is_resolved_against_base… |
| `tests/unit/test_sa_schema.py` | `TestScalarTypeMapping` | 9 | test_str_maps_to_text, test_int_maps_to_integer, test_decimal_maps_to_float… |
| `tests/unit/test_ux_contract_checker.py` | `TestFindNestedChromes` | 9 | test_detects_rounded_plus_border_nested, test_ignores_rounded_without_surface, test_ignores_bg_only_rounded… |
| `tests/unit/test_validator.py` | `TestDeadConstructDetection` | 9 | test_entity_used_by_surface_is_not_dead, test_entity_used_by_field_ref_is_not_dead, test_entity_used_by_workspace_source_is_not_dead… |
| `tests/unit/test_viewport.py` | `TestExpectedMatching` | 9 | test_exact_match_passes, test_exact_match_fails, test_list_match_first… |
| `tests/unit/sentinel/test_agent_performance_resource.py` | `TestPR01NPlusOneListSurface` | 8 | test_ref_only_entity_not_flagged, test_mixed_refs_and_has_many_only_counts_non_ref, test_passes_entity_with_fewer_than_3_refs… |
| `tests/unit/test_agent_parser.py` | `TestBracketCounter` | 8 | test_extract_simple_object, test_extract_with_prose_before, test_extract_with_prose_after… |
| `tests/unit/test_cedar_row_filters.py` | `TestExtractConditionFilters` | 8 | test_simple_comparison_equals, test_not_equals_comparison, test_literal_value_equals… |
| `tests/unit/test_cedar_row_filters.py` | `TestExtractConditionFiltersIR` | 8 | test_ir_current_user_equals, test_ir_literal_value, test_ir_boolean_value… |
| `tests/unit/test_composition_audit.py` | `TestEvaluateRule` | 8 | test_ratio_pass, test_ratio_skips_missing_element, test_ordering_pass… |
| `tests/unit/test_condition_evaluator_role_check.py` | `TestEvaluateConditionRoleCheckCompound` | 8 | test_and_role_and_comparison_both_pass, test_and_role_passes_comparison_fails, test_and_role_fails_comparison_passes… |
| `tests/unit/test_content_negotiation.py` | `TestWantsHtml` | 8 | test_htmx_header, test_exact_text_html, test_browser_accept_header… |
| `tests/unit/test_dazzle_adapter_urls.py` | `TestResolveViewUrl` | 8 | test_simple_entity_list, test_compound_entity_list, test_compound_entity_create… |
| `tests/unit/test_e2e_harness.py` | `TestSemanticTargetParsing` | 8 | test_parse_view_target, test_parse_field_target, test_parse_action_target… |
| `tests/unit/test_manifest_database.py` | `TestResolveDatabaseUrlWithEnv` | 8 | test_explicit_url_beats_env_profile, test_env_profile_direct_url, test_env_profile_env_var_indirection… |
| `tests/unit/test_money_expansion.py` | `TestCurrencyFilter` | 8 | test_minor_units_default, test_minor_false, test_usd_symbol… |

## Top 10 files by collapse-saving potential

| File | Tests that could collapse |
|---|---:|
| `tests/unit/test_workspace_routes.py` | 80 |
| `tests/unit/test_expression_lang.py` | 40 |
| `tests/unit/test_fidelity_scorer.py` | 38 |
| `tests/unit/test_composition_audit.py` | 32 |
| `tests/unit/test_rhythm_mcp.py` | 29 |
| `tests/unit/test_anti_turing.py` | 27 |
| `tests/unit/sentinel/test_agent_performance_resource.py` | 27 |
| `tests/unit/test_workspace_rendering.py` | 26 |
| `tests/unit/test_cedar_row_filters.py` | 25 |
| `tests/unit/sentinel/test_agent_operational_hygiene.py` | 24 |

## How to act on this

1. Pick the largest cluster (top of the list above). Open the file. Read 3 of the cluster's member tests.
2. If they vary only on input data, collapse to one `@pytest.mark.parametrize` test. Each removed test removes a name + a fixture setup + a maintenance burden, but no protective signal (the parametric form runs the same N cases).
3. If they assert genuinely different things despite shared shape, tag the cluster as `keep_all` in `redundancy.json` so the next audit cycle skips it.
4. Re-run `python3 scripts/distill/classify.py` and `python3 scripts/distill/cluster.py` to confirm the cluster is gone.
