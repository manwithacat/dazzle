# Test Redundancy Report — Pass 2 (coarse)

Clusters where ≥3 tests in the same file/class share the same assertion-shape signature. Strong candidates for `@pytest.mark.parametrize` consolidation.

## Headline numbers

- **Clusters of ≥3**: 1,001
- **Tests inside those clusters**: 3,823
- **Theoretical saving** if every cluster collapsed to one parametrised test: **2,822 tests** (≈ 19.7% of the suite)

Caveats: not every cluster *should* collapse — sometimes independent test names carry intentional documentation value. The report below is ranked by size; larger clusters are more likely to genuinely benefit from consolidation.

## Cluster size distribution

| Size | Clusters |
|---|---:|
| 20+ | 0 |
| 10-19 | 5 |
| 5-9 | 201 |
| 3-4 | 795 |

## Top 30 largest clusters

| File | Class | Size | Sample test names |
|---|---|---:|---|
| `tests/unit/test_cedar_row_filters.py` | `TestExtractCedarRowFilters` | 12 | test_owner_equals_current_user, test_read_rule_also_applies, test_non_list_read_rules_ignored… |
| `tests/unit/test_rhythm_mcp.py` | `(module)` | 12 | test_get_rhythm_includes_phase_kind, test_get_rhythm_includes_phase_cadence, test_gaps_unmapped_scene… |
| `tests/unit/test_anti_turing.py` | `TestAntiTuringValidator` | 11 | test_valid_entity_declaration, test_valid_surface_declaration, test_valid_workspace_with_filter… |
| `tests/unit/test_workspace_routes.py` | `TestAttentionAccentMacro` | 11 | test_border_critical_destructive, test_border_warning_warning, test_border_notice_primary… |
| `tests/unit/test_anti_turing.py` | `TestAntiTuringValidator` | 10 | test_banned_if_keyword, test_banned_for_keyword, test_banned_while_keyword… |
| `tests/unit/sentinel/test_agent_performance_resource.py` | `TestPR01NPlusOneListSurface` | 8 | test_ref_only_entity_not_flagged, test_mixed_refs_and_has_many_only_counts_non_ref, test_passes_entity_with_fewer_than_3_refs… |
| `tests/unit/test_cedar_row_filters.py` | `TestExtractConditionFilters` | 8 | test_simple_comparison_equals, test_not_equals_comparison, test_literal_value_equals… |
| `tests/unit/test_cedar_row_filters.py` | `TestExtractConditionFiltersIR` | 8 | test_ir_current_user_equals, test_ir_literal_value, test_ir_boolean_value… |
| `tests/unit/test_pitch_ir.py` | `TestSpeakerNotes` | 8 | test_company_speaker_notes, test_problem_speaker_notes, test_solution_speaker_notes… |
| `tests/unit/test_policy_handler.py` | `TestEvaluateCondition` | 8 | test_none_condition_returns_true, test_role_check_matches, test_role_check_no_match… |
| `tests/unit/test_pull_to_refresh_directive.py` | `(module)` | 8 | test_directive_registered, test_touch_only_via_pointer_coarse, test_threshold_constant_present… |
| `tests/unit/test_validate_scope_predicates.py` | `TestValidPredicates` | 8 | test_tautology_produces_no_errors, test_column_check_valid_field, test_user_attr_check_valid_field… |
| `tests/unit/test_widget_rules.py` | `TestWidgetRules` | 8 | test_ref_field_with_source_option_no_relevance, test_field_with_widget_annotation_returns_no_relevance, test_list_mode_surface_returns_no_relevance… |
| `tests/unit/test_workspace_profile_card.py` | `TestInterpolateCardTemplate` | 8 | test_simple_field, test_dotted_path, test_multiple_fields… |
| `tests/unit/sentinel/test_agent_performance_resource.py` | `TestPR05LargeEntityListSurface` | 7 | test_passes_entity_with_fewer_than_10_fields, test_ignores_non_list_surface, test_no_surfaces… |
| `tests/unit/test_anti_turing.py` | `TestAntiTuringCycle998` | 7 | test_role_call_allowed, test_persona_call_allowed, test_via_entity_call_allowed… |
| `tests/unit/test_asset_bundle.py` | `TestShouldBundleAssets` | 7 | test_default_mode_default_env_returns_false, test_auto_in_production_env_returns_true, test_auto_in_staging_env_returns_true… |
| `tests/unit/test_compliance_matching.py` | `TestUKGovernmentIdentifiers` | 7 | test_ni_number_matches, test_nino_matches, test_national_insurance_prefix_matches… |
| `tests/unit/test_compliance_slicer.py` | `(module)` | 7 | test_slice_by_status, test_slice_by_extract, test_slice_by_tier… |
| `tests/unit/test_condition_evaluator_role_check.py` | `TestEvaluateConditionRoleCheck` | 7 | test_role_check_true_when_user_has_role, test_role_check_false_when_user_lacks_role, test_role_check_false_with_empty_roles_list… |
| `tests/unit/test_cron.py` | `TestDueJobs` | 7 | test_empty_jobs_returns_empty, test_matching_job_due, test_non_matching_job_skipped… |
| `tests/unit/test_file_upload_form.py` | `TestBasenameOrUrlFilter` | 7 | test_url_extracts_filename, test_url_with_query_string, test_full_url… |
| `tests/unit/test_governance_parser.py` | `TestInterfacesParser` | 7 | test_api_format_defaults_to_rest, test_api_auth_oauth2, test_api_auth_jwt… |
| `tests/unit/test_lifecycle_validation.py` | `TestValidateLifecycles` | 7 | test_status_field_must_exist_on_entity, test_status_field_must_be_enum, test_state_names_must_match_enum_values… |
| `tests/unit/test_persona_journey.py` | `TestNavigationScope` | 7 | test_no_over_exposure_when_workspace_covers_all, test_out_of_workspace_entities_not_over_exposed, test_policy_access_prevents_over_exposure… |
| `tests/unit/test_rhythm_mcp.py` | `(module)` | 7 | test_list_rhythms_includes_ambient_phases, test_lifecycle_current_focus_is_first_incomplete, test_lifecycle_evaluating_maturity… |
| `tests/unit/test_route_overrides.py` | `TestLoadExtensionRouters` | 7 | test_empty_spec_list_returns_empty, test_rejects_path_traversal_in_module, test_skips_missing_module… |
| `tests/unit/test_search_fields.py` | `TestBuildEntitySearchFields` | 7 | test_extracts_search_fields, test_no_search_fields_excluded, test_multiple_entities… |
| `tests/unit/test_swipe_directive.py` | `(module)` | 7 | test_directive_registered, test_touch_only_via_pointer_coarse, test_horizontal_threshold_constant… |
| `tests/unit/test_template_rendering.py` | `TestJinjaFilters` | 7 | test_status_badge_macro_tone_override, test_status_badge_macro_size_sm, test_status_badge_macro_display_override… |

## Top 10 files by collapse-saving potential

| File | Tests that could collapse |
|---|---:|
| `tests/unit/test_workspace_routes.py` | 80 |
| `tests/unit/test_expression_lang.py` | 40 |
| `tests/unit/test_rhythm_mcp.py` | 29 |
| `tests/unit/test_anti_turing.py` | 27 |
| `tests/unit/sentinel/test_agent_performance_resource.py` | 27 |
| `tests/unit/test_cedar_row_filters.py` | 25 |
| `tests/unit/test_composition_audit.py` | 25 |
| `tests/unit/sentinel/test_agent_operational_hygiene.py` | 24 |
| `tests/unit/sentinel/test_agent_integration_dependency.py` | 24 |
| `tests/unit/sentinel/test_agent_deployment_state.py` | 22 |

## How to act on this

1. Pick the largest cluster (top of the list above). Open the file. Read 3 of the cluster's member tests.
2. If they vary only on input data, collapse to one `@pytest.mark.parametrize` test. Each removed test removes a name + a fixture setup + a maintenance burden, but no protective signal (the parametric form runs the same N cases).
3. If they assert genuinely different things despite shared shape, tag the cluster as `keep_all` in `redundancy.json` so the next audit cycle skips it.
4. Re-run `python3 scripts/distill/classify.py` and `python3 scripts/distill/cluster.py` to confirm the cluster is gone.
