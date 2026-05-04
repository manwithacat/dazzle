# Test Redundancy Report — Pass 2 (coarse)

Clusters where ≥3 tests in the same file/class share the same assertion-shape signature. Strong candidates for `@pytest.mark.parametrize` consolidation.

## Headline numbers

- **Clusters of ≥3**: 1,047
- **Tests inside those clusters**: 4,304
- **Theoretical saving** if every cluster collapsed to one parametrised test: **3,257 tests** (≈ 22.8% of the suite)

Caveats: not every cluster *should* collapse — sometimes independent test names carry intentional documentation value. The report below is ranked by size; larger clusters are more likely to genuinely benefit from consolidation.

## Cluster size distribution

| Size | Clusters |
|---|---:|
| 20+ | 3 |
| 10-19 | 24 |
| 5-9 | 227 |
| 3-4 | 793 |

## Top 30 largest clusters

| File | Class | Size | Sample test names |
|---|---|---:|---|
| `tests/unit/test_expression_lang.py` | `TestTypeInference` | 22 | test_int_literal, test_float_literal, test_string_literal… |
| `tests/unit/test_ref_display.py` | `TestRefDisplayName` | 22 | test_name_field, test_company_name_field, test_first_last_name… |
| `tests/unit/test_access_control.py` | `TestAccessRuleEvaluate` | 20 | test_public_rule, test_authenticated_rule_no_user, test_authenticated_rule_with_user… |
| `tests/unit/test_pipeline_detail.py` | `TestStepHasIssues` | 19 | test_lint_with_errors, test_lint_with_warnings_only, test_lint_with_errors_and_warnings… |
| `tests/unit/test_failure_classifier.py` | `TestClassifyFailure` | 15 | test_rbac_denied_401, test_rbac_denied_403, test_rbac_denied_permission… |
| `tests/unit/test_asset_manifest.py` | `TestCollectRequiredAssets` | 13 | test_no_widgets_returns_empty, test_rich_text_requires_no_vendor_asset, test_combobox_requires_tom_select… |
| `tests/unit/test_cedar_row_filters.py` | `TestExtractCedarRowFilters` | 12 | test_owner_equals_current_user, test_read_rule_also_applies, test_non_list_read_rules_ignored… |
| `tests/unit/test_expression_lang.py` | `TestEvalArithmetic` | 12 | test_addition, test_subtraction, test_multiplication… |
| `tests/unit/test_resolve_display_name.py` | `TestResolveDisplayName` | 12 | test_string_passthrough, test_int_passthrough, test_none_returns_empty… |
| `tests/unit/test_rhythm_mcp.py` | `(module)` | 12 | test_get_rhythm_includes_phase_kind, test_get_rhythm_includes_phase_cadence, test_gaps_unmapped_scene… |
| `tests/unit/test_template_overrides.py` | `TestSemanticBlocks` | 12 | test_app_shell_has_navbar_block, test_app_shell_has_sidebar_block, test_app_shell_has_sidebar_brand_block… |
| `tests/unit/test_analytics_disable_modes.py` | `TestAnalyticsGloballyDisabled` | 11 | test_default_environment_enabled, test_dev_env_disables, test_development_env_disables… |
| `tests/unit/test_anti_turing.py` | `TestAntiTuringValidator` | 11 | test_valid_entity_declaration, test_valid_surface_declaration, test_valid_workspace_with_filter… |
| `tests/unit/test_blueprint_generator_heuristic.py` | `TestStrategyValueWrong` | 11 | test_date_relative_on_date_field_is_ok, test_date_relative_on_ref_field_is_wrong, test_date_relative_on_numeric_field_is_wrong… |
| `tests/unit/test_expression_lang.py` | `TestEvalFunctions` | 11 | test_concat, test_concat_with_null, test_len… |
| `tests/unit/test_lsp_completion.py` | `TestDetectCompletionContext` | 11 | test_top_level, test_mode_value, test_ref_target… |
| `tests/unit/test_workspace_routes.py` | `TestAttentionAccentMacro` | 11 | test_border_critical_destructive, test_border_warning_warning, test_border_notice_primary… |
| `tests/unit/test_anti_turing.py` | `TestAntiTuringValidator` | 10 | test_banned_if_keyword, test_banned_for_keyword, test_banned_while_keyword… |
| `tests/unit/test_composition_audit.py` | `TestComputeAttentionWeight` | 10 | test_h1_weight_matches_spec, test_h2_weight_matches_spec, test_h3_weight_matches_spec… |
| `tests/unit/test_e2e_harness.py` | `TestAuthLocatorMapping` | 10 | test_get_auth_locator_login_button, test_get_auth_locator_logout_button, test_get_auth_locator_modal… |
| `tests/unit/test_fidelity_scorer.py` | `TestMoneyFieldExpansion` | 10 | test_expand_field_names_helper, test_expand_money_field_in_form, test_money_widget_data_attribute_match… |
| `tests/unit/test_fidelity_scorer.py` | `TestWidgetRenderedInputTypes` | 10 | test_datepicker_on_date_field, test_datepicker_on_datetime_field, test_range_slider_on_int_field… |
| `tests/unit/test_graph_semantics.py` | `TestGraphValidationErrors` | 10 | test_source_field_not_found, test_target_field_not_found, test_source_not_ref_type… |
| `tests/unit/test_invariant_evaluator.py` | `TestComparison` | 10 | test_eq_true, test_eq_false, test_ne… |
| `tests/unit/test_manifest_database.py` | `TestResolveDatabaseUrl` | 10 | test_explicit_wins, test_env_wins_over_manifest, test_manifest_direct_url… |
| `tests/unit/test_url_consistency.py` | `TestResolveBackendUrl` | 10 | test_local_dev_uses_fallback, test_local_dev_uses_base_url, test_single_dyno_uses_port… |
| `tests/unit/test_viewport_suggestions.py` | `TestSuggestFix` | 10 | test_display_grid_tablet, test_display_grid_desktop, test_display_grid_wide… |
| `tests/unit/test_api_packs.py` | `TestFormatDuration` | 9 | test_days, test_hours, test_24_hours… |
| `tests/unit/test_compliance_matching.py` | `TestNeutralizingContext` | 9 | test_ip_address_rejected, test_mac_address_rejected, test_wallet_address_rejected… |
| `tests/unit/test_computed_evaluator.py` | `TestAggregateExpression` | 9 | test_count, test_count_empty, test_sum… |

## Top 10 files by collapse-saving potential

| File | Tests that could collapse |
|---|---:|
| `tests/unit/test_expression_lang.py` | 88 |
| `tests/unit/test_workspace_routes.py` | 80 |
| `tests/unit/test_composition_audit.py` | 43 |
| `tests/unit/test_fidelity_scorer.py` | 38 |
| `tests/unit/test_access_control.py` | 33 |
| `tests/unit/test_rhythm_mcp.py` | 29 |
| `tests/unit/test_invariant_evaluator.py` | 28 |
| `tests/unit/test_anti_turing.py` | 27 |
| `tests/unit/sentinel/test_agent_performance_resource.py` | 27 |
| `tests/unit/test_workspace_rendering.py` | 26 |

## How to act on this

1. Pick the largest cluster (top of the list above). Open the file. Read 3 of the cluster's member tests.
2. If they vary only on input data, collapse to one `@pytest.mark.parametrize` test. Each removed test removes a name + a fixture setup + a maintenance burden, but no protective signal (the parametric form runs the same N cases).
3. If they assert genuinely different things despite shared shape, tag the cluster as `keep_all` in `redundancy.json` so the next audit cycle skips it.
4. Re-run `python3 scripts/distill/classify.py` and `python3 scripts/distill/cluster.py` to confirm the cluster is gone.
