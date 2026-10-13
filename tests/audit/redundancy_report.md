# Test Redundancy Report — Pass 2 (coarse)

Clusters where ≥3 tests in the same file/class share the same assertion-shape signature. Strong candidates for `@pytest.mark.parametrize` consolidation.

## Headline numbers

- **Clusters of ≥3**: 1,030
- **Tests inside those clusters**: 4,037
- **Theoretical saving** if every cluster collapsed to one parametrised test: **3,007 tests** (≈ 21.0% of the suite)

Caveats: not every cluster *should* collapse — sometimes independent test names carry intentional documentation value. The report below is ranked by size; larger clusters are more likely to genuinely benefit from consolidation.

## Cluster size distribution

| Size | Clusters |
|---|---:|
| 20+ | 3 |
| 10-19 | 13 |
| 5-9 | 176 |
| 3-4 | 838 |

## Top 30 largest clusters

| File | Class | Size | Sample test names |
|---|---|---:|---|
| `tests/unit/test_region_adapter.py` | `(module)` | 28 | test_list_csv_export_filename_override, test_grid_clamps_column_count_to_valid_range, test_metrics_summary_alias_dispatches_same_path… |
| `tests/unit/test_datatable_handler.py` | `TestListHandlerFilter` | 21 | test_handler_leftover_filter_does_not_invent, test_handler_leftover_filter_value_does_not_invent, test_handler_valid_filter_enum_value_rides… |
| `tests/unit/test_auth_connection_cli.py` | `(module)` | 20 | test_verify_domain_not_found_prints_record, test_show_verification, test_doctor_ready_exit_0… |
| `tests/unit/render/fragment/test_data_primitives.py` | `(module)` | 17 | test_table_columns_and_rows, test_kpi_basic, test_bar_chart_buckets… |
| `tests/unit/test_hm_contract_dom_conformance.py` | `(module)` | 15 | test_money_field_fixed_conforms_to_money_contract, test_search_result_row_conforms_to_result_contract, test_metric_tile_emission_conforms_to_metrics_contract… |
| `tests/unit/test_region_adapter.py` | `(module)` | 14 | test_grid_uses_label_field_override, test_metrics_invalid_tone_coerced_to_default, test_metrics_no_delta_omits_delta_block… |
| `tests/unit/test_auth_error_leftover.py` | `(module)` | 12 | test_valid_login_error_still_renders_banner, test_declared_sso_no_connection_rides, test_declared_sso_unavailable_rides… |
| `tests/unit/test_form_widget_showcase_phase3.py` | `(module)` | 12 | test_combobox_controller_leftover_does_not_invent, test_grid_controller_rejects_whitespace_query, test_search_box_controller_rejects_empty_query… |
| `tests/integration/test_scim_routes.py` | `(module)` | 11 | test_no_bearer_is_401, test_bad_bearer_is_401, test_create_user_unverified_domain_is_400… |
| `tests/unit/http_runtime/test_query_builder.py` | `TestFilterCondition` | 11 | test_parse_gt_operator, test_parse_gte_operator, test_parse_lt_operator… |
| `tests/unit/test_dedup_footgun_gates.py` | `(module)` | 11 | test_no_inline_entity_slug, test_no_inline_404_guard, test_logger_uses_dunder_name_not_string_bucket… |
| `tests/unit/test_document_routes.py` | `(module)` | 11 | test_unknown_entity_is_opaque_404, test_missing_record_is_opaque_404, test_invalid_entity_id_is_404… |
| `tests/integration/test_saml_routes.py` | `(module)` | 10 | test_login_redirects_to_idp, test_login_resolves_by_verified_email_domain, test_sls_kills_only_the_connections_org_sessions… |
| `tests/unit/render/fragment/test_htmx_types.py` | `(module)` | 10 | test_url_accepts_relative_path, test_target_selector_id_form, test_hx_trigger_simple_event… |
| `tests/unit/test_goal_b_coat.py` | `(module)` | 10 | test_stamp_pair_grids_saturate_media, test_note_kind_chrome_saturates_conversation, test_tree_people_org_saturates… |
| `tests/unit/test_region_adapter.py` | `(module)` | 10 | test_timeline_overflow_line_renders_when_total_exceeds_items, test_kanban_display_sibling_still_emits_avatar, test_list_with_csv_export_renders_button… |
| `tests/integration/test_scim_routes.py` | `(module)` | 9 | test_service_provider_config_requires_bearer, test_leftover_users_filter_is_invalid_filter, test_delete_user… |
| `tests/unit/http_runtime/test_query_builder.py` | `TestFilterCondition` | 9 | test_to_sql_equality, test_to_sql_contains, test_to_sql_startswith… |
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

## Top 10 files by collapse-saving potential

| File | Tests that could collapse |
|---|---:|
| `tests/unit/test_region_adapter.py` | 72 |
| `tests/unit/http_runtime/test_query_builder.py` | 32 |
| `tests/unit/test_auth_connection_cli.py` | 27 |
| `tests/unit/render/fragment/test_data_primitives.py` | 27 |
| `tests/unit/test_expression_lang.py` | 27 |
| `tests/unit/test_schema_diff.py` | 25 |
| `tests/unit/test_two_factor_views.py` | 25 |
| `tests/unit/test_hm_contract_dom_conformance.py` | 24 |
| `tests/integration/test_connection_admin_routes.py` | 23 |
| `tests/unit/test_datatable_handler.py` | 20 |

## Fuzz-target worklist (property/fuzz-candidate clusters)

Clusters whose subject is an input-boundary surface (parser/validator/crypto/…). Each is a candidate to collapse into ONE property test (input space → invariant) — which then becomes a fuzz target — rather than a fixed `@pytest.mark.parametrize` list. Path-based hint; confirm by reading the cluster. (#1342)

- **Property/fuzz-candidate clusters**: 130

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
| `tests/unit/render/fragment/test_renderer_asset_url_1137.py` | `(module)` | 6 | property | input-boundary surface — collapse to a Hypothesis property (input space → invariant) |
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

## How to act on this

1. Pick the largest cluster (top of the list above). Open the file. Read 3 of the cluster's member tests.
2. If they vary only on input data, collapse to one `@pytest.mark.parametrize` test. Each removed test removes a name + a fixture setup + a maintenance burden, but no protective signal (the parametric form runs the same N cases).
3. If they assert genuinely different things despite shared shape, tag the cluster as `keep_all` in `redundancy.json` so the next audit cycle skips it.
4. Re-run `python3 scripts/distill/classify.py` and `python3 scripts/distill/cluster.py` to confirm the cluster is gone.
