# Test Redundancy Report — Pass 2 (coarse)

Clusters where ≥3 tests in the same file/class share the same assertion-shape signature. Strong candidates for `@pytest.mark.parametrize` consolidation.

## Headline numbers

- **Clusters of ≥3**: 853
- **Tests inside those clusters**: 3,028
- **Theoretical saving** if every cluster collapsed to one parametrised test: **2,175 tests** (≈ 15.2% of the suite)

Caveats: not every cluster *should* collapse — sometimes independent test names carry intentional documentation value. The report below is ranked by size; larger clusters are more likely to genuinely benefit from consolidation.

## Cluster size distribution

| Size | Clusters |
|---|---:|
| 20+ | 0 |
| 10-19 | 5 |
| 5-9 | 88 |
| 3-4 | 760 |

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
| `tests/unit/test_persona_journey.py` | `TestNavigationScope` | 7 | test_no_over_exposure_when_workspace_covers_all, test_out_of_workspace_entities_not_over_exposed, test_policy_access_prevents_over_exposure… |
| `tests/unit/test_rhythm_mcp.py` | `(module)` | 7 | test_list_rhythms_includes_ambient_phases, test_lifecycle_current_focus_is_first_incomplete, test_lifecycle_evaluating_maturity… |
| `tests/integration/test_template_pages.py` | `TestDazzleAttributes` | 6 | test_list_page_has_dazzle_view, test_list_page_has_dazzle_table, test_list_page_has_dazzle_view_on_root… |
| `tests/quality_gates/test_dashboard_gates.py` | `TestDashboardQualityGates` | 6 | test_gate1_drag_threshold, test_gate2_drag_uses_transform, test_gate3_save_lifecycle… |
| `tests/unit/test_expression_lang.py` | `TestTokenizer` | 6 | test_integer, test_float, test_string_double_quotes… |
| `tests/unit/test_expression_lang.py` | `TestTokenizer` | 6 | test_string_escape, test_keywords, test_operators… |
| `tests/unit/test_null_event_bus.py` | `(module)` | 6 | test_null_bus_replay_yields_nothing, test_null_bus_list_topics, test_null_bus_list_consumer_groups… |
| `tests/unit/test_persona_journey.py` | `TestExperienceReachability` | 6 | test_reachable_experience_no_gap, test_experience_for_other_persona_ignored, test_access_spec_allows_persona_no_gap… |
| `tests/unit/test_process_propose.py` | `TestDesignQuestions` | 6 | test_automated_trigger_question, test_multiple_actors_question, test_state_machine_question… |
| `tests/unit/test_rbac_verifier.py` | `TestCompareCellPermitFiltered` | 6 | test_filtered_200_partial_count_is_pass, test_filtered_200_count_equals_total_is_violation, test_filtered_200_count_zero_is_warning… |
| `tests/unit/test_rhythm_ir.py` | `(module)` | 6 | test_phase_spec, test_scene_dimension_score_creation, test_scene_evaluation_creation… |
| `tests/unit/test_rhythm_mcp.py` | `(module)` | 6 | test_list_rhythms, test_coverage_persona_deny_list, test_gaps_summary_counts… |
| `tests/unit/test_triples.py` | `TestGetPermittedPersonas` | 6 | test_open_permissions_all_personas, test_restricted_to_named_personas_only, test_no_access_spec_defaults_to_all_personas… |
| `tests/unit/test_ux_contract_checker.py` | `TestFindHiddenPrimaryActions` | 6 | test_focus_within_reveal_not_flagged, test_always_visible_not_flagged, test_alpine_modal_not_flagged… |
| `tests/unit/test_viewport.py` | `TestDerivePatterns` | 6 | test_drawer_on_root_with_workspaces, test_drawer_on_root_with_surfaces, test_dual_pane_flow_stage… |
| `tests/unit/test_widget_rules.py` | `TestWidgetRules` | 6 | test_ref_field_with_source_option_no_relevance, test_field_with_widget_annotation_returns_no_relevance, test_examples_list_is_empty… |
| `tests/unit/test_workspace_routes.py` | `TestAuth2FAFlow` | 6 | test_challenge_extends_site_base_and_uses_auth_page_card, test_challenge_email_otp_conditional, test_setup_qr_verify_and_recovery_initially_hidden… |
| `tests/unit/test_workspace_routes.py` | `TestAuth2FAFlow` | 6 | test_challenge_has_canonical_totp_input_attributes, test_challenge_sets_hx_history_false, test_challenge_has_use_recovery_link… |
| `tests/quality_gates/test_data_table_gates.py` | `TestDataTableUnitGates` | 5 | test_gate1_sort_cycle, test_gate2_column_resize, test_gate3_inline_edit_lifecycle… |
| `tests/quality_gates/test_pdf_viewer_gates.py` | `TestKeyboardShortcuts` | 5 | test_escape_navigates_to_back, test_j_key_navigates_to_prev, test_k_key_navigates_to_next… |
| `tests/unit/test_access_evaluator.py` | `TestComparisonConditions` | 5 | test_equals_current_user, test_equals_literal, test_not_equals… |
| `tests/unit/test_analytics_provider_rendering.py` | `TestResolveActiveProviders` | 5 | test_none_analytics_returns_empty, test_no_providers_returns_empty, test_unknown_provider_skipped… |

## Top 10 files by collapse-saving potential

| File | Tests that could collapse |
|---|---:|
| `tests/unit/test_workspace_routes.py` | 80 |
| `tests/unit/test_expression_lang.py` | 37 |
| `tests/unit/test_rhythm_mcp.py` | 29 |
| `tests/unit/test_anti_turing.py` | 27 |
| `tests/unit/test_cedar_row_filters.py` | 25 |
| `tests/unit/test_workspace_rendering.py` | 19 |
| `tests/unit/test_dz_richtext.py` | 18 |
| `tests/unit/sentinel/test_agent_integration_dependency.py` | 18 |
| `tests/unit/test_mapping_executor.py` | 18 |
| `tests/unit/test_parser.py` | 18 |

## How to act on this

1. Pick the largest cluster (top of the list above). Open the file. Read 3 of the cluster's member tests.
2. If they vary only on input data, collapse to one `@pytest.mark.parametrize` test. Each removed test removes a name + a fixture setup + a maintenance burden, but no protective signal (the parametric form runs the same N cases).
3. If they assert genuinely different things despite shared shape, tag the cluster as `keep_all` in `redundancy.json` so the next audit cycle skips it.
4. Re-run `python3 scripts/distill/classify.py` and `python3 scripts/distill/cluster.py` to confirm the cluster is gone.
