# Test Redundancy Report — Pass 2 (coarse)

Clusters where ≥3 tests in the same file/class share the same assertion-shape signature. Strong candidates for `@pytest.mark.parametrize` consolidation.

## Headline numbers

- **Clusters of ≥3**: 650
- **Tests inside those clusters**: 2,429
- **Theoretical saving** if every cluster collapsed to one parametrised test: **1,779 tests** (≈ 12.4% of the suite)

Caveats: not every cluster *should* collapse — sometimes independent test names carry intentional documentation value. The report below is ranked by size; larger clusters are more likely to genuinely benefit from consolidation.

## Cluster size distribution

| Size | Clusters |
|---|---:|
| 20+ | 0 |
| 10-19 | 3 |
| 5-9 | 102 |
| 3-4 | 545 |

## Top 30 largest clusters

| File | Class | Size | Sample test names |
|---|---|---:|---|
| `tests/unit/test_hm_contract_dom_conformance.py` | `(module)` | 15 | test_money_field_fixed_conforms_to_money_contract, test_search_result_row_conforms_to_result_contract, test_metric_tile_emission_conforms_to_metrics_contract… |
| `tests/unit/test_dedup_footgun_gates.py` | `(module)` | 11 | test_no_inline_entity_slug, test_no_inline_404_guard, test_logger_uses_dunder_name_not_string_bucket… |
| `tests/unit/test_goal_b_coat.py` | `(module)` | 10 | test_stamp_pair_grids_saturate_media, test_note_kind_chrome_saturates_conversation, test_tree_people_org_saturates… |
| `tests/unit/test_auth_views_password_reset.py` | `(module)` | 9 | test_forgot_password_view_posts_to_submit_endpoint, test_forgot_password_view_uses_product_name_in_brand, test_forgot_password_view_links_back_to_login… |
| `tests/unit/test_onboarding_renderer.py` | `(module)` | 9 | test_popover_cta_href_when_target_set, test_popover_placement_threads_into_data_attr, test_every_supported_kind_emits_htmx_complete… |
| `tests/unit/test_scope_create_eval.py` | `(module)` | 9 | test_user_attr_check_passes_when_field_equals_user_id, test_user_attr_check_rejects_when_field_does_not_equal_user_id, test_user_attr_check_missing_attr_rejects… |
| `tests/unit/test_session_manager.py` | `TestSessionTokenFromLoginResponse` | 9 | test_legacy_dazzle_session, test_host_cookie, test_apex_cookie… |
| `tests/integration/test_examples_fragment_http.py` | `(module)` | 8 | test_simple_task_create_form_str_field_renders_as_text_input, test_fragment_chrome_emits_dz_page_body_class, test_fragment_chrome_default_off_unchanged_behaviour… |
| `tests/unit/test_cohort_strip_tone_bands_1144.py` | `(module)` | 8 | test_value_clears_highest_band_takes_that_tone, test_value_falls_to_middle_band, test_value_below_all_bands_stays_neutral… |
| `tests/unit/test_csrf_disposition_phase3.py` | `TestCsrfDisposition` | 8 | test_bearer_is_na_bearer, test_webhook_is_na_signature, test_sign_route_is_na_signature… |
| `tests/unit/test_csrf_disposition_phase3.py` | `TestProtectedPathOverrides` | 8 | test_switch_org_is_protected_session, test_select_org_is_protected_session, test_logout_is_protected_session… |
| `tests/unit/test_landing_resolver.py` | `(module)` | 8 | test_infers_first_active_scene_workspace, test_kind_unset_uses_first_phase, test_explicit_active_preferred_over_earlier_unmarked_phase… |
| `tests/unit/test_list_index_emission.py` | `(module)` | 8 | test_no_list_surface_no_extra_index, test_surface_without_ux_sort_is_skipped, test_non_list_surface_skipped… |
| `tests/unit/test_llm_driver.py` | `TestResolveLlmDriver` | 8 | test_explicit_wins_over_everything, test_env_var_beats_manifest, test_manifest_drives_resolution… |
| `tests/unit/test_result.py` | `(module)` | 8 | test_ok_carries_value, test_err_carries_error, test_ok_unwrap_returns_value… |
| `tests/unit/test_task_inbox_data_resolution.py` | `(module)` | 8 | test_returns_empty_when_no_items_and_no_chips, test_returns_empty_when_config_missing, test_chips_only_config_emits_chips_no_items… |
| `tests/unit/test_tenant_host_validator.py` | `(module)` | 8 | test_validator_rejects_slug_field_pointing_at_non_slug_field, test_validator_rejects_unknown_history_entity, test_validator_requires_order_when_two_entities_share_domain… |
| `tests/unit/test_tenant_middleware.py` | `(module)` | 8 | test_canonical_host_passes_through_with_no_tenant, test_demo_host_tenant_slug_binds_on_canonical_host, test_demo_host_tenant_slug_skips_test_seed_path… |
| `tests/unit/test_anti_turing.py` | `TestAntiTuringCycle998` | 7 | test_role_call_allowed, test_persona_call_allowed, test_via_entity_call_allowed… |
| `tests/unit/test_apex_discovery.py` | `TestResolveApexRedirect` | 7 | test_apex_topology_does_not_bounce_even_with_apex_cookies, test_leftover_topology_does_not_invent_a_bounce, test_single_membership_stays_on_apex_when_host_cookies… |
| `tests/unit/test_audit_integrity_config_loading.py` | `(module)` | 7 | test_manifest_default_audit_integrity_is_none, test_manifest_parses_hash_chain, test_build_server_config_threads_audit_integrity… |
| `tests/unit/test_auth_views_password_mode.py` | `(module)` | 7 | test_login_password_view_posts_to_password_endpoint, test_login_password_view_threads_next_param, test_login_password_view_links_forgot_password… |
| `tests/unit/test_badge_wcag_icon_1493.py` | `TestSMTerminalInference` | 7 | test_unrecognised_terminal_inferred_success, test_name_guess_terminals_are_skipped, test_none_machine_is_empty… |
| `tests/unit/test_cli_spec_strict_guard.py` | `(module)` | 7 | test_extract_domain_map_finds_entities_in_rows, test_extract_domain_map_ignores_placeholder_row, test_extract_domain_map_returns_empty_when_no_heading… |
| `tests/unit/test_dispatch_ctx_list_row_links.py` | `(module)` | 7 | test_dispatch_ctx_threads_detail_url_template, test_dispatch_ctx_omits_detail_url_template_when_unset, test_resolve_row_links_substitutes_named_placeholders… |
| `tests/unit/test_error_views.py` | `(module)` | 7 | test_404_view_announces_404, test_404_view_custom_message_overrides_default, test_404_view_renders_product_name… |
| `tests/unit/test_pending_document_route.py` | `(module)` | 7 | test_uploader_gets_pending_file, test_non_uploader_denied_404, test_attached_file_not_servable_via_pending… |
| `tests/unit/test_persona_journey.py` | `TestNavigationScope` | 7 | test_no_over_exposure_when_workspace_covers_all, test_out_of_workspace_entities_not_over_exposed, test_policy_access_prevents_over_exposure… |
| `tests/unit/test_pip_audit.py` | `(module)` | 7 | test_parse_findings_reads_the_id_column_not_the_whole_line, test_parse_findings_keeps_only_three_columns, test_parse_findings_dedupes_the_alias_rows_pip_audit_repeats… |
| `tests/unit/test_rate_limit_key_1296.py` | `(module)` | 7 | test_default_zero_trusted_proxies_uses_client_host_ignoring_xff, test_one_trusted_proxy_takes_rightmost_xff, test_two_trusted_proxies_takes_second_from_right… |

## Top 10 files by collapse-saving potential

| File | Tests that could collapse |
|---|---:|
| `tests/unit/test_hm_contract_dom_conformance.py` | 24 |
| `tests/unit/test_csrf_disposition_phase3.py` | 18 |
| `tests/unit/test_scope_create_eval.py` | 14 |
| `tests/unit/test_task_inbox_data_resolution.py` | 14 |
| `tests/unit/test_onboarding_renderer.py` | 13 |
| `tests/unit/test_persona_journey.py` | 13 |
| `tests/unit/test_goal_b_coat.py` | 12 |
| `tests/unit/test_landing_resolver.py` | 12 |
| `tests/unit/test_tenant_middleware.py` | 12 |
| `tests/integration/test_auth_password_mode_chrome_gate.py` | 12 |

## Fuzz-target worklist (property/fuzz-candidate clusters)

Clusters whose subject is an input-boundary surface (parser/validator/crypto/…). Each is a candidate to collapse into ONE property test (input space → invariant) — which then becomes a fuzz target — rather than a fixed `@pytest.mark.parametrize` list. Path-based hint; confirm by reading the cluster. (#1342)

- **Property/fuzz-candidate clusters**: 55

| File | Class | Size | Form | Why |
|---|---|---:|---|---|
| `tests/unit/test_scope_create_eval.py` | `(module)` | 9 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_tenant_host_validator.py` | `(module)` | 8 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_scope_create_eval.py` | `(module)` | 7 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_parser.py` | `(module)` | 6 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_predicate_policy_mode.py` | `TestInlineLiteral` | 6 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_comparison_validation.py` | `(module)` | 5 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_descendants_of_parser.py` | `TestDescendantsOfValidator` | 5 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_format_validation.py` | `(module)` | 5 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_scope_default_deny_returns.py` | `(module)` | 5 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_agent_parser.py` | `TestParseActionTier2` | 4 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_auth_identity_validation.py` | `TestAuthIdentityValidation` | 4 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_copy_parser.py` | `TestParseCopyFile` | 4 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_copy_parser.py` | `TestMergeCopyIntoSitespec` | 4 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_db_url.py` | `TestNormalisePostgresScheme` | 4 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_db_url.py` | `TestAddPsycopgDriver` | 4 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_format_validation.py` | `(module)` | 4 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_jwt_security.py` | `TestAlgorithmSecurity` | 4 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_latest_one_parser.py` | `TestLatestOneValidator` | 4 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_parser.py` | `(module)` | 4 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_predicate_builder.py` | `(module)` | 4 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_predicate_policy_mode.py` | `TestCollectUserAttrRefs` | 4 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_validate_app_links.py` | `(module)` | 4 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_validate_scope_predicates.py` | `TestInvalidPredicates` | 4 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_workspace_scope_enforcement.py` | `TestApplyWorkspaceScopeFilters` | 4 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/integration/test_scope_runtime_pg.py` | `(module)` | 3 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_action_url_surface_resolution.py` | `(module)` | 3 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_aggregate_parser.py` | `(module)` | 3 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_aggregate_parser.py` | `(module)` | 3 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_audit_dsl.py` | `TestRetention` | 3 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_auth_consume_token_leftover.py` | `(module)` | 3 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |

## How to act on this

1. Pick the largest cluster (top of the list above). Open the file. Read 3 of the cluster's member tests.
2. If they vary only on input data, collapse to one `@pytest.mark.parametrize` test. Each removed test removes a name + a fixture setup + a maintenance burden, but no protective signal (the parametric form runs the same N cases).
3. If they assert genuinely different things despite shared shape, tag the cluster as `keep_all` in `redundancy.json` so the next audit cycle skips it.
4. Re-run `python3 scripts/distill/classify.py` and `python3 scripts/distill/cluster.py` to confirm the cluster is gone.
