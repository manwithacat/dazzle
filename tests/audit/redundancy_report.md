# Test Redundancy Report — Pass 2 (coarse)

Clusters where ≥3 tests in the same file/class share the same assertion-shape signature. Strong candidates for `@pytest.mark.parametrize` consolidation.

## Headline numbers

- **Clusters of ≥3**: 925
- **Tests inside those clusters**: 3,370
- **Theoretical saving** if every cluster collapsed to one parametrised test: **2,445 tests** (≈ 17.1% of the suite)

Caveats: not every cluster *should* collapse — sometimes independent test names carry intentional documentation value. The report below is ranked by size; larger clusters are more likely to genuinely benefit from consolidation.

## Cluster size distribution

| Size | Clusters |
|---|---:|
| 20+ | 0 |
| 10-19 | 5 |
| 5-9 | 122 |
| 3-4 | 798 |

## Top 30 largest clusters

| File | Class | Size | Sample test names |
|---|---|---:|---|
| `tests/unit/test_cedar_row_filters.py` | `TestExtractCedarRowFilters` | 12 | test_owner_equals_current_user, test_read_rule_also_applies, test_non_list_read_rules_ignored… |
| `tests/unit/test_rhythm_mcp.py` | `(module)` | 12 | test_get_rhythm_includes_phase_kind, test_get_rhythm_includes_phase_cadence, test_gaps_unmapped_scene… |
| `tests/unit/test_anti_turing.py` | `TestAntiTuringValidator` | 11 | test_valid_entity_declaration, test_valid_surface_declaration, test_valid_workspace_with_filter… |
| `tests/unit/test_workspace_routes.py` | `TestAttentionAccentMacro` | 11 | test_border_critical_destructive, test_border_warning_warning, test_border_notice_primary… |
| `tests/unit/test_anti_turing.py` | `TestAntiTuringValidator` | 10 | test_banned_if_keyword, test_banned_for_keyword, test_banned_while_keyword… |
| `tests/unit/test_cedar_row_filters.py` | `TestExtractConditionFilters` | 8 | test_simple_comparison_equals, test_not_equals_comparison, test_literal_value_equals… |
| `tests/unit/test_cedar_row_filters.py` | `TestExtractConditionFiltersIR` | 8 | test_ir_current_user_equals, test_ir_literal_value, test_ir_boolean_value… |
| `tests/unit/test_anti_turing.py` | `TestAntiTuringCycle998` | 7 | test_role_call_allowed, test_persona_call_allowed, test_via_entity_call_allowed… |
| `tests/unit/test_compliance_matching.py` | `TestUKGovernmentIdentifiers` | 7 | test_ni_number_matches, test_nino_matches, test_national_insurance_prefix_matches… |
| `tests/unit/test_condition_evaluator_role_check.py` | `TestEvaluateConditionRoleCheck` | 7 | test_role_check_true_when_user_has_role, test_role_check_false_when_user_lacks_role, test_role_check_false_with_empty_roles_list… |
| `tests/unit/test_persona_journey.py` | `TestNavigationScope` | 7 | test_no_over_exposure_when_workspace_covers_all, test_out_of_workspace_entities_not_over_exposed, test_policy_access_prevents_over_exposure… |
| `tests/unit/test_rhythm_mcp.py` | `(module)` | 7 | test_list_rhythms_includes_ambient_phases, test_lifecycle_current_focus_is_first_incomplete, test_lifecycle_evaluating_maturity… |
| `tests/unit/test_search_fields.py` | `TestBuildEntitySearchFields` | 7 | test_extracts_search_fields, test_no_search_fields_excluded, test_multiple_entities… |
| `tests/unit/test_template_rendering.py` | `TestJinjaFilters` | 7 | test_status_badge_macro_tone_override, test_status_badge_macro_size_sm, test_status_badge_macro_display_override… |
| `tests/unit/test_validator.py` | `TestValidateEntities` | 7 | test_duplicate_field_names, test_decimal_scale_greater_than_precision, test_string_very_large_max_length_warning… |
| `tests/integration/test_template_pages.py` | `TestDazzleAttributes` | 6 | test_list_page_has_dazzle_view, test_list_page_has_dazzle_table, test_list_page_has_dazzle_view_on_root… |
| `tests/quality_gates/test_dashboard_gates.py` | `TestDashboardQualityGates` | 6 | test_gate1_drag_threshold, test_gate2_drag_uses_transform, test_gate3_save_lifecycle… |
| `tests/unit/test_composition_audit.py` | `TestScoring` | 6 | test_no_violations_scores_100, test_one_high_deducts_15, test_one_medium_deducts_5… |
| `tests/unit/test_content_negotiation.py` | `TestIsHtmxRequest` | 6 | test_htmx_header, test_accept_text_html_is_not_htmx, test_browser_accept_is_not_htmx… |
| `tests/unit/test_expression_lang.py` | `TestTokenizer` | 6 | test_integer, test_float, test_string_double_quotes… |
| `tests/unit/test_expression_lang.py` | `TestTokenizer` | 6 | test_string_escape, test_keywords, test_operators… |
| `tests/unit/test_fidelity_scorer.py` | `TestCreateModeStoryGapSuppression` | 6 | test_create_skips_precondition_when_default_matches, test_create_still_flags_precondition_when_default_differs, test_edit_still_flags_precondition_even_when_default_matches… |
| `tests/unit/test_heading_scale_tokens.py` | `(module)` | 6 | test_app_heading_token_present, test_marketing_heading_token_present, test_cta_headline_canonically_defined… |
| `tests/unit/test_journey_reporter.py` | `TestRenderReport` | 6 | test_contains_persona_names, test_contains_verdict_counts, test_contains_cross_persona_patterns… |
| `tests/unit/test_layout_engine.py` | `TestArchetypeSelection` | 6 | test_select_focus_metric_single_kpi, test_select_scanner_table_single_table, test_select_monitor_wall_multiple_signals… |
| `tests/unit/test_locale_middleware.py` | `TestParseAcceptLanguage` | 6 | test_single_locale, test_multiple_with_quality, test_quality_zero_excluded… |
| `tests/unit/test_null_event_bus.py` | `(module)` | 6 | test_null_bus_replay_yields_nothing, test_null_bus_list_topics, test_null_bus_list_consumer_groups… |
| `tests/unit/test_parser.py` | `TestBusinessPriority` | 6 | test_surface_priority_critical, test_surface_priority_low, test_surface_priority_defaults_to_medium… |
| `tests/unit/test_persona_journey.py` | `TestExperienceReachability` | 6 | test_reachable_experience_no_gap, test_experience_for_other_persona_ignored, test_access_spec_allows_persona_no_gap… |
| `tests/unit/test_predicate_builder.py` | `(module)` | 6 | test_simple_field_equals_literal, test_field_equals_current_user, test_field_equals_current_user_dot_attr… |

## Top 10 files by collapse-saving potential

| File | Tests that could collapse |
|---|---:|
| `tests/unit/test_workspace_routes.py` | 80 |
| `tests/unit/test_expression_lang.py` | 40 |
| `tests/unit/test_rhythm_mcp.py` | 29 |
| `tests/unit/test_anti_turing.py` | 27 |
| `tests/unit/test_cedar_row_filters.py` | 25 |
| `tests/unit/test_composition_audit.py` | 25 |
| `tests/unit/test_fidelity_scorer.py` | 22 |
| `tests/unit/test_parser.py` | 21 |
| `tests/unit/sentinel/test_agent_deployment_state.py` | 20 |
| `tests/unit/test_docker_generation.py` | 19 |

## How to act on this

1. Pick the largest cluster (top of the list above). Open the file. Read 3 of the cluster's member tests.
2. If they vary only on input data, collapse to one `@pytest.mark.parametrize` test. Each removed test removes a name + a fixture setup + a maintenance burden, but no protective signal (the parametric form runs the same N cases).
3. If they assert genuinely different things despite shared shape, tag the cluster as `keep_all` in `redundancy.json` so the next audit cycle skips it.
4. Re-run `python3 scripts/distill/classify.py` and `python3 scripts/distill/cluster.py` to confirm the cluster is gone.
