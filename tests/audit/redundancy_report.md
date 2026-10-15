# Test Redundancy Report — Pass 2 (coarse)

Clusters where ≥3 tests in the same file/class share the same assertion-shape signature. Strong candidates for `@pytest.mark.parametrize` consolidation.

## Headline numbers

- **Clusters of ≥3**: 877
- **Tests inside those clusters**: 3,361
- **Theoretical saving** if every cluster collapsed to one parametrised test: **2,484 tests** (≈ 17.4% of the suite)

Caveats: not every cluster *should* collapse — sometimes independent test names carry intentional documentation value. The report below is ranked by size; larger clusters are more likely to genuinely benefit from consolidation.

## Cluster size distribution

| Size | Clusters |
|---|---:|
| 20+ | 1 |
| 10-19 | 5 |
| 5-9 | 152 |
| 3-4 | 719 |

## Top 30 largest clusters

| File | Class | Size | Sample test names |
|---|---|---:|---|
| `tests/unit/test_auth_connection_cli.py` | `(module)` | 20 | test_verify_domain_not_found_prints_record, test_show_verification, test_doctor_ready_exit_0… |
| `tests/unit/test_hm_contract_dom_conformance.py` | `(module)` | 15 | test_money_field_fixed_conforms_to_money_contract, test_search_result_row_conforms_to_result_contract, test_metric_tile_emission_conforms_to_metrics_contract… |
| `tests/integration/test_scim_routes.py` | `(module)` | 11 | test_no_bearer_is_401, test_bad_bearer_is_401, test_create_user_unverified_domain_is_400… |
| `tests/unit/test_dedup_footgun_gates.py` | `(module)` | 11 | test_no_inline_entity_slug, test_no_inline_404_guard, test_logger_uses_dunder_name_not_string_bucket… |
| `tests/integration/test_saml_routes.py` | `(module)` | 10 | test_login_redirects_to_idp, test_login_resolves_by_verified_email_domain, test_sls_kills_only_the_connections_org_sessions… |
| `tests/unit/test_goal_b_coat.py` | `(module)` | 10 | test_stamp_pair_grids_saturate_media, test_note_kind_chrome_saturates_conversation, test_tree_people_org_saturates… |
| `tests/integration/test_scim_routes.py` | `(module)` | 9 | test_service_provider_config_requires_bearer, test_leftover_users_filter_is_invalid_filter, test_delete_user… |
| `tests/unit/test_auth_views_password_reset.py` | `(module)` | 9 | test_forgot_password_view_posts_to_submit_endpoint, test_forgot_password_view_uses_product_name_in_brand, test_forgot_password_view_links_back_to_login… |
| `tests/unit/test_enterprise_login.py` | `(module)` | 9 | test_no_verified_domains_refuses_everyone, test_empty_email_refuses, test_unsigned_fallback_without_email_verified_refuses… |
| `tests/unit/test_entity_card_data_resolution.py` | `(module)` | 9 | test_halo_section_omitted_when_no_record, test_section_omitted_when_record_has_no_field_values, test_quick_actions_omits_section_when_no_actions_declared… |
| `tests/unit/test_onboarding_renderer.py` | `(module)` | 9 | test_popover_cta_href_when_target_set, test_popover_placement_threads_into_data_attr, test_every_supported_kind_emits_htmx_complete… |
| `tests/unit/test_python_audit_enum_dispatch_1274.py` | `(module)` | 9 | test_fires_on_four_branch_chain, test_fires_when_literal_on_left_side, test_does_not_fire_on_two_branch_chain… |
| `tests/unit/test_python_audit_raw_sql_string_building.py` | `(module)` | 9 | test_fires_on_format_method_execute, test_fires_on_scripts_subdir, test_fires_on_session_execute_not_just_cursor… |
| `tests/unit/test_saml_metadata.py` | `(module)` | 9 | test_validate_rejects_non_https, test_validate_rejects_private_ip, test_validate_unresolvable… |
| `tests/unit/test_schema_diff.py` | `(module)` | 9 | test_added_column, test_dropped_column, test_no_change_empty_delta… |
| `tests/unit/test_scope_create_eval.py` | `(module)` | 9 | test_user_attr_check_passes_when_field_equals_user_id, test_user_attr_check_rejects_when_field_does_not_equal_user_id, test_user_attr_check_missing_attr_rejects… |
| `tests/unit/test_session_manager.py` | `TestSessionTokenFromLoginResponse` | 9 | test_legacy_dazzle_session, test_host_cookie, test_apex_cookie… |
| `tests/unit/test_two_factor_views.py` | `(module)` | 9 | test_totp_mode_posts_to_verify_submit, test_totp_mode_default_subtitle, test_totp_mode_offers_email_otp_link_when_enabled… |
| `tests/integration/test_connection_admin_routes.py` | `(module)` | 8 | test_page_forbidden_without_session, test_page_forbidden_for_non_admin, test_page_forbidden_when_no_admin_roles_configured… |
| `tests/integration/test_connection_admin_routes.py` | `(module)` | 8 | test_page_only_shows_active_orgs_connections, test_page_shows_rotation_history, test_page_shows_grace_window_when_active… |
| `tests/integration/test_examples_fragment_http.py` | `(module)` | 8 | test_simple_task_create_form_str_field_renders_as_text_input, test_fragment_chrome_emits_dz_page_body_class, test_fragment_chrome_default_off_unchanged_behaviour… |
| `tests/unit/test_cohort_strip_tone_bands_1144.py` | `(module)` | 8 | test_value_clears_highest_band_takes_that_tone, test_value_falls_to_middle_band, test_value_below_all_bands_stays_neutral… |
| `tests/unit/test_csrf_disposition_phase3.py` | `TestCsrfDisposition` | 8 | test_bearer_is_na_bearer, test_webhook_is_na_signature, test_sign_route_is_na_signature… |
| `tests/unit/test_csrf_disposition_phase3.py` | `TestProtectedPathOverrides` | 8 | test_switch_org_is_protected_session, test_select_org_is_protected_session, test_logout_is_protected_session… |
| `tests/unit/test_enterprise_login.py` | `(module)` | 8 | test_verified_domain_match_is_case_insensitive, test_unsigned_fallback_with_email_verified_true_allowed, test_id_token_path_tolerates_missing_email_verified… |
| `tests/unit/test_landing_resolver.py` | `(module)` | 8 | test_infers_first_active_scene_workspace, test_kind_unset_uses_first_phase, test_explicit_active_preferred_over_earlier_unmarked_phase… |
| `tests/unit/test_list_index_emission.py` | `(module)` | 8 | test_no_list_surface_no_extra_index, test_surface_without_ux_sort_is_skipped, test_non_list_surface_skipped… |
| `tests/unit/test_llm_driver.py` | `TestResolveLlmDriver` | 8 | test_explicit_wins_over_everything, test_env_var_beats_manifest, test_manifest_drives_resolution… |
| `tests/unit/test_org_activation.py` | `TestDeriveMembershipsRequired` | 8 | test_tenant_host_implies_required_without_auto_provision, test_auto_provision_still_implies_required, test_neither_is_not_required… |
| `tests/unit/test_result.py` | `(module)` | 8 | test_ok_carries_value, test_err_carries_error, test_ok_unwrap_returns_value… |

## Top 10 files by collapse-saving potential

| File | Tests that could collapse |
|---|---:|
| `tests/unit/test_auth_connection_cli.py` | 27 |
| `tests/unit/test_expression_lang.py` | 27 |
| `tests/unit/test_schema_diff.py` | 25 |
| `tests/unit/test_two_factor_views.py` | 25 |
| `tests/unit/test_hm_contract_dom_conformance.py` | 24 |
| `tests/integration/test_connection_admin_routes.py` | 23 |
| `tests/integration/test_scim_routes.py` | 20 |
| `tests/unit/test_entity_card_data_resolution.py` | 20 |
| `tests/unit/test_rbac_verifier.py` | 20 |
| `tests/unit/test_validator.py` | 19 |

## Fuzz-target worklist (property/fuzz-candidate clusters)

Clusters whose subject is an input-boundary surface (parser/validator/crypto/…). Each is a candidate to collapse into ONE property test (input space → invariant) — which then becomes a fuzz target — rather than a fixed `@pytest.mark.parametrize` list. Path-based hint; confirm by reading the cluster. (#1342)

- **Property/fuzz-candidate clusters**: 123

| File | Class | Size | Form | Why |
|---|---|---:|---|---|
| `tests/integration/test_scim_routes.py` | `(module)` | 11 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/integration/test_saml_routes.py` | `(module)` | 10 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/integration/test_scim_routes.py` | `(module)` | 9 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_saml_metadata.py` | `(module)` | 9 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_scope_create_eval.py` | `(module)` | 9 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_tenant_host_validator.py` | `(module)` | 8 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_scope_create_eval.py` | `(module)` | 7 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/integration/test_saml_routes.py` | `(module)` | 6 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_predicate_policy_mode.py` | `TestInlineLiteral` | 6 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_validator.py` | `TestValidateNavCuration` | 6 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_comparison_validation.py` | `(module)` | 5 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_descendants_of_parser.py` | `TestDescendantsOfValidator` | 5 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_format_validation.py` | `(module)` | 5 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_scim_displayname_leftover.py` | `(module)` | 5 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_scim_external_id_leftover.py` | `(module)` | 5 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_scim_provisioning.py` | `(module)` | 5 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_scim_provisioning.py` | `(module)` | 5 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_scope_default_deny_returns.py` | `(module)` | 5 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_validator.py` | `TestValidateNavCuration` | 5 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_agent_parser.py` | `TestParseActionTier2` | 4 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_auth_identity_validation.py` | `TestAuthIdentityValidation` | 4 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_auth_token_leftover.py` | `(module)` | 4 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_copy_parser.py` | `TestParseCopyFile` | 4 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_copy_parser.py` | `TestMergeCopyIntoSitespec` | 4 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_day_timeline_config_parser.py` | `(module)` | 4 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_db_url.py` | `TestNormalisePostgresScheme` | 4 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_db_url.py` | `TestAddPsycopgDriver` | 4 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
| `tests/unit/test_entity_card_config_parser.py` | `(module)` | 4 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_expression_lang.py` | `TestParserFieldRef` | 4 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |
| `tests/unit/test_expression_lang.py` | `TestParserArithmetic` | 4 | fuzz | DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators) |

## How to act on this

1. Pick the largest cluster (top of the list above). Open the file. Read 3 of the cluster's member tests.
2. If they vary only on input data, collapse to one `@pytest.mark.parametrize` test. Each removed test removes a name + a fixture setup + a maintenance burden, but no protective signal (the parametric form runs the same N cases).
3. If they assert genuinely different things despite shared shape, tag the cluster as `keep_all` in `redundancy.json` so the next audit cycle skips it.
4. Re-run `python3 scripts/distill/classify.py` and `python3 scripts/distill/cluster.py` to confirm the cluster is gone.
