# Test Cross-File Audit — Pass 3

Three structural views the per-file Pass-2 redundancy report doesn't capture.

## View 1 — Cross-file shape clusters

Tests sharing the same `(class_name, assertion_shape)` across multiple files. Often means a test pattern was copy-pasted across handler/parser files; one parametric test could replace many.

- **Clusters of size ≥4 across ≥2 files**: 134
- **Tests inside cross-file clusters**: 4,396
- **Theoretical saving**: ~4,262 if each cluster collapses to one parametric test

### Top 25 cross-file clusters

| Class | Size | Files | Sample tests |
|---|---:|---|---|
| `(module)` | 990 | `test_acme_billing_rbac.py`, `test_auth_orgprovision_pg.py`, `test_connection_admin_routes.py` (+344 more) | test_idor_foreign_org_invoice_returns_404, test_bulk_action_denied_for_unpermitted_role… |
| `(module)` | 355 | `test_acme_billing_rbac.py`, `test_auth_activation_pg.py`, `test_auth_login_magic_link_chrome_gate.py` (+178 more) | test_sensitive_invoice_denied_to_contractor, test_password_login_no_membership_redirects_to_no_orgs_when_required… |
| `(module)` | 345 | `test_auth_password_reset_chrome_gate.py`, `test_connection_admin_routes.py`, `test_connections_pg.py` (+138 more) | test_post_forgot_password_logs_reset_link_for_dev_pickup, test_create_path_is_csrf_protected… |
| `(module)` | 234 | `test_auth_activation_pg.py`, `test_auth_orgprovision_pg.py`, `test_connections_pg.py` (+119 more) | test_set_session_active_membership_rejects_suspended, test_server_config_defaults_auto_provision_off… |
| `(module)` | 229 | `test_auth_login_magic_link_chrome_gate.py`, `test_auth_signup_magic_link_chrome_gate.py`, `test_connections_pg.py` (+106 more) | test_post_magic_link_logs_link_url_for_dev_pickup, test_login_falls_back_to_log_mailer_when_unregistered… |
| `(module)` | 134 | `test_app_shell_primitive.py`, `test_error_page_primitive.py`, `test_insight_narrative.py` (+65 more) | test_app_shell_sanitises_invalid_sidebar_state, test_error_page_home_label_customisable… |
| `(module)` | 130 | `test_connection_admin_routes.py`, `test_connections_pg.py`, `test_enterprise_routes.py` (+54 more) | test_page_only_shows_active_orgs_connections, test_page_shows_rotation_history… |
| `(module)` | 118 | `test_access_review_pg.py`, `test_acme_billing_rbac.py`, `test_auth_login_magic_link_chrome_gate.py` (+72 more) | test_cli_access_review_rejects_bad_as_of, test_org_owner_create_is_scoped_to_own_org… |
| `(module)` | 115 | `test_app_shell_primitive.py`, `test_error_page_primitive.py`, `test_insight_narrative.py` (+66 more) | test_app_shell_omits_sidebar_aside_when_no_sidebar, test_error_page_omits_home_link_when_no_href… |
| `(module)` | 101 | `test_mode_a_integration.py`, `test_simple_task_chrome_smoke.py`, `test_container_primitives.py` (+62 more) | test_mode_a_stale_lock_recovery, test_simple_task_chrome_smoke_no_route_returns_5xx… |
| `(module)` | 93 | `test_access_review_pg.py`, `test_auth_login_magic_link_chrome_gate.py`, `test_auth_orgprovision_pg.py` (+60 more) | test_access_review_as_of_excludes_later_changes, test_post_magic_link_unknown_email_redirects_same_no_token… |
| `(module)` | 85 | `test_auth_activation_pg.py`, `test_connections_pg.py`, `test_comparator.py` (+62 more) | test_cross_tenant_guard_fails_closed_without_membership, test_grace_expiry_rejects_old_bearer… |
| `(module)` | 85 | `test_examples_fragment_http.py`, `test_render_clause_linking.py`, `test_tools.py` (+56 more) | test_simple_task_create_form_text_field_renders_as_textarea, test_simple_task_create_form_enum_field_renders_as_select… |
| `(module)` | 85 | `test_sentinel_findings_mcp_catalogue.py`, `test_archetype_profile.py`, `test_atomic_flow_invariants.py` (+25 more) | test_catalogue_url_in_remediation_references, test_profile_without_shared_schema_is_a_validation_error… |
| `(module)` | 66 | `test_auth_orgprovision_pg.py`, `test_auth_password_reset_chrome_gate.py`, `test_auth_signup_magic_link_chrome_gate.py` (+49 more) | test_ensure_single_org_membership_first_and_second_user, test_post_reset_password_mismatched_redirects_back_with_error… |
| `(module)` | 46 | `test_fidelity_integration.py`, `test_error_page_primitive.py`, `test_navigation_primitives.py` (+32 more) | test_mcp_handler_returns_valid_json, test_error_page_emits_section_with_code_and_message… |
| `(module)` | 41 | `test_auth_password_mode_chrome_gate.py`, `test_auth_password_reset_chrome_gate.py`, `test_engine_baseline_parity_pg.py` (+23 more) | test_get_login_password_mode_renders_invalid_credentials_error, test_get_signup_renders_mismatch_error… |
| `(module)` | 39 | `test_auth_activation_pg.py`, `test_connections_pg.py`, `test_dispatch_render.py` (+25 more) | test_set_session_active_membership_rejects_foreign_membership, test_delete_connection… |
| `(module)` | 39 | `test_auth_password_reset_chrome_gate.py`, `test_examples_fragment_http.py`, `test_member_admin_pg.py` (+26 more) | test_get_forgot_password_sent_chrome_on_renders_typed_view, test_get_forgot_password_sent_chrome_off_also_renders_typed_view… |
| `(module)` | 36 | `test_tenant_rls_constraints_pg.py`, `test_attempted.py`, `test_context.py` (+21 more) | test_composite_fk_rejects_cross_tenant_reference, test_uniqueness_is_tenant_scoped… |
| `(module)` | 30 | `test_auth_password_reset_chrome_gate.py`, `test_org_invitations_pg.py`, `test_scim_routes.py` (+21 more) | test_post_reset_password_success_updates_password_and_redirects, test_invite_route_authz_gate… |
| `(module)` | 29 | `test_auth_activation_pg.py`, `test_qa_auth_containment_pg.py`, `test_qa_trial_signing.py` (+24 more) | test_password_login_multi_membership_redirects_to_picker, test_password_login_no_membership_proceeds_by_default… |
| `(module)` | 29 | `test_create_time_tenant_injection_pg.py`, `test_member_admin_pg.py`, `test_runner.py` (+23 more) | test_scoped_insert_omitting_tenant_id_autofills_from_bound_guc, test_cross_org_target_is_rejected… |
| `(module)` | 29 | `test_examples_fragment_http.py`, `test_insight_narrative.py`, `test_renderer_containers.py` (+21 more) | test_fragment_chrome_default_assets_when_state_unset, test_non_additive_skips_total_and_pct… |
| `(module)` | 27 | `test_auth_activation_pg.py`, `test_fragment_surface_adapter.py`, `test_condition_to_predicate.py` (+12 more) | test_host_pin_uuid_discriminator_round_trips, test_form_widget_kind_mapping… |

## View 2 — Implementation-mirror file candidates

Files dominated by tests that pin internal call shapes (high mocks, short body, low public-import diversity). Strategy doc tags these as the highest-leverage *deletion* targets — replace with one canonical behavior test per shape.

- **Files flagged**: 13
- **Tests in flagged files**: 168

### Top 30 candidates (by test count)

| File | Tests | Mirror share | Avg mocks | Avg body | Avg asserts | Priv imports/test |
|---|---:|---:|---:|---:|---:|---:|
| `tests/unit/test_agent_core.py` | 29 | 0.0 | 2.0 | 19.0 | 2.4 | 0.0 |
| `tests/unit/test_cli_db_ops.py` | 23 | 0.0 | 2.4 | 16.2 | 2.1 | 0.4 |
| `tests/unit/test_domain_user_attributes.py` | 14 | 0.5 | 1.7 | 18.9 | 2.5 | 0.5 |
| `tests/unit/test_composition_styles.py` | 12 | 0.0 | 4.9 | 19.0 | 2.1 | 0.0 |
| `tests/unit/test_email_verification_routes.py` | 12 | 0.0 | 2.2 | 12.7 | 2.0 | 0.2 |
| `tests/unit/test_mapping_executor_cache.py` | 12 | 0.0 | 2.4 | 17.2 | 1.9 | 0.0 |
| `tests/unit/test_tenant_registry.py` | 11 | 0.0 | 2.6 | 18.5 | 1.7 | 0.1 |
| `tests/unit/test_auth_subsystem_jwt_wiring.py` | 10 | 0.0 | 2.2 | 20.4 | 2.6 | 0.0 |
| `tests/unit/test_worker_postgres_wiring.py` | 10 | 0.1 | 2.0 | 23.8 | 1.7 | 0.4 |
| `tests/unit/test_cli_tenant.py` | 9 | 0.0 | 4.2 | 12.3 | 2.4 | 0.0 |
| `tests/unit/test_github_issues.py` | 9 | 0.0 | 2.4 | 11.3 | 2.0 | 0.4 |
| `tests/unit/test_interaction_server_fixture.py` | 9 | 0.0 | 2.7 | 16.3 | 1.3 | 0.2 |
| `tests/unit/test_custom_mode_dispatch.py` | 8 | 0.0 | 2.0 | 18.2 | 2.9 | 1.0 |

## View 3 — Twin file pairs (body-shape multiset overlap ≥70%)

Pairs of files whose tests' assertion-shape distributions match. One may supersede the other; or they're testing the same shape on two entities (consolidate).

- **Twin pairs**: 14116

### Top 30 twin pairs

| File A | File B | A | B | Shared | Overlap |
|---|---|---:|---:|---:|---:|
| `test_parser.py` | `test_rbac_verifier.py` | 143 | 59 | 45 | 0.76 |
| `test_data_primitives.py` | `test_parser.py` | 46 | 143 | 42 | 0.91 |
| `test_fidelity_scorer.py` | `test_rbac_verifier.py` | 36 | 59 | 35 | 0.97 |
| `test_pdf_viewer_component.py` | `test_region_adapter.py` | 49 | 143 | 35 | 0.71 |
| `test_composition_audit.py` | `test_dsl_emitter.py` | 89 | 48 | 34 | 0.71 |
| `test_fidelity_scorer.py` | `test_parser.py` | 36 | 143 | 34 | 0.94 |
| `test_mapping_executor.py` | `test_parser.py` | 40 | 143 | 31 | 0.78 |
| `test_agent_business_logic.py` | `test_persona_journey.py` | 29 | 56 | 29 | 1.0 |
| `test_agent_performance_resource.py` | `test_parser.py` | 40 | 143 | 29 | 0.72 |
| `test_agent_performance_resource.py` | `test_rbac_verifier.py` | 40 | 59 | 29 | 0.72 |
| `test_region_adapter.py` | `test_site_section_medium_builders.py` | 143 | 38 | 29 | 0.76 |
| `test_region_adapter.py` | `test_two_factor_views.py` | 143 | 30 | 29 | 0.97 |
| `test_data_primitives.py` | `test_agent_business_logic.py` | 46 | 29 | 28 | 0.97 |
| `test_agent_business_logic.py` | `test_parser.py` | 29 | 143 | 28 | 0.97 |
| `test_agent_business_logic.py` | `test_rbac_verifier.py` | 29 | 59 | 28 | 0.97 |
| `test_agent_performance_resource.py` | `test_fidelity_scorer.py` | 40 | 36 | 28 | 0.78 |
| `test_cedar_row_filters.py` | `test_fidelity_scorer.py` | 28 | 36 | 28 | 1.0 |
| `test_cedar_row_filters.py` | `test_parser.py` | 28 | 143 | 28 | 1.0 |
| `test_cedar_row_filters.py` | `test_rbac_verifier.py` | 28 | 59 | 28 | 1.0 |
| `test_composition_audit.py` | `test_qa_trial.py` | 89 | 39 | 28 | 0.72 |
| `test_docker_generation.py` | `test_region_adapter.py` | 35 | 143 | 28 | 0.8 |
| `test_parser.py` | `test_structured_content.py` | 143 | 32 | 28 | 0.88 |
| `test_agent_auth.py` | `test_persona_journey.py` | 28 | 56 | 27 | 0.96 |
| `test_agent_business_logic.py` | `test_expression_lang.py` | 29 | 83 | 27 | 0.93 |
| `test_composition_audit.py` | `test_rbac_enforcement.py` | 89 | 36 | 27 | 0.75 |
| `test_docker_generation.py` | `test_pdf_viewer_component.py` | 35 | 49 | 27 | 0.77 |
| `test_data_primitives.py` | `test_fidelity_scorer.py` | 46 | 36 | 26 | 0.72 |
| `test_agent_business_logic.py` | `test_agent_performance_resource.py` | 29 | 40 | 26 | 0.9 |
| `test_agent_data_integrity.py` | `test_parser.py` | 29 | 143 | 26 | 0.9 |
| `test_agent_data_integrity.py` | `test_persona_journey.py` | 29 | 56 | 26 | 0.9 |
