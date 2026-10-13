# Test Cross-File Audit — Pass 3

Three structural views the per-file Pass-2 redundancy report doesn't capture.

## View 1 — Cross-file shape clusters

Tests sharing the same `(class_name, assertion_shape, public_target)` across multiple files — same assert shape AND the same deduped set of public dazzle callables. A cluster here is a genuinely copy-pasted pattern that one shared parametrised helper could replace. (Pre-#1530 this view keyed on shape alone, which matched hundreds of unrelated files; the target discriminator makes the numbers actionable.)

- **Clusters of size ≥4 across ≥2 files**: 21
- **Tests inside cross-file clusters**: 205
- **Theoretical saving**: ~184 if each cluster collapses to one parametric test
- **Skipped (no attributable public target)**: 1,255 tests — shape matches without a shared target are not actionable

### Top 25 cross-file clusters

| Class | Size | Target | Files | Sample tests |
|---|---:|---|---|---|
| `(module)` | 31 | PythonAuditAgent | `test_python_audit_enum_dispatch_1274.py`, `test_python_audit_exceptions.py`, `test_python_audit_magic_string_typing.py` (+3 more) | test_fires_on_four_branch_chain, test_fires_when_literal_on_left_side… |
| `(module)` | 29 | TYPED_SECTION_TYPES, render_typed_section | `test_site_section_final_builders.py`, `test_site_section_hero_builder.py`, `test_site_section_medium_builders.py` (+2 more) | test_three_new_section_types_in_typed_set, test_render_typed_section_dispatches_each_new_type… |
| `(module)` | 23 | TYPED_SECTION_TYPES, render_typed_section | `test_site_section_final_builders.py`, `test_site_section_hero_builder.py`, `test_site_section_medium_builders.py` (+1 more) | test_features_emits_section_class_and_grid, test_features_renders_section_header_when_provided… |
| `(module)` | 16 | parse_dsl, ParseError | `test_cohort_strip_composite_parser_1144.py`, `test_cohort_strip_config_parser.py`, `test_day_timeline_config_parser.py` (+3 more) | test_default_separator_when_omitted, test_parses_quoted_label_with_spaces_and_punctuation… |
| `(module)` | 13 | DayTimelineConfig | `test_day_timeline_as_of_1146.py`, `test_day_timeline_card_body_1146.py`, `test_day_timeline_data_resolution.py` | test_as_of_field_composes_with_per_row_date, test_as_of_accepts_time_objects… |
| `(module)` | 11 | TYPED_SECTION_TYPES, render_typed_section | `test_site_section_final_builders.py`, `test_site_section_hero_builder.py`, `test_site_section_medium_builders.py` (+2 more) | test_features_omits_icon_when_absent, test_faq_handles_empty_items… |
| `(module)` | 11 | TYPED_SECTION_TYPES, render_typed_section | `test_site_section_final_builders.py`, `test_site_section_hero_builder.py`, `test_site_section_medium_builders.py` (+1 more) | test_pricing_omits_cta_when_absent, test_hero_omits_subhead_p_when_absent… |
| `(module)` | 10 | app | `test_cli.py`, `test_cli_inspect.py`, `test_inspect_rls.py` (+2 more) | test_validate_command_success, test_inspect_help_lists_all_subcommands… |
| `(module)` | 7 | load_manifest | `test_manifest_admin_capabilities.py`, `test_manifest_app_scripts.py`, `test_manifest_capabilities.py` (+1 more) | test_admin_capabilities_default_empty, test_admin_capabilities_parsed… |
| `(module)` | 5 | create_magic_link_routes, create_auth_page_routes | `test_auth_login_magic_link_chrome_gate.py`, `test_auth_signup_magic_link_chrome_gate.py` | test_get_login_chrome_off_now_also_renders_typed_view, test_get_login_threads_next_param… |
| `(module)` | 5 | create_magic_link_routes, create_auth_page_routes | `test_auth_login_magic_link_chrome_gate.py`, `test_auth_signup_magic_link_chrome_gate.py` | test_post_magic_link_threads_next_param_through_redirect, test_post_magic_link_normalises_email_case… |
| `(module)` | 5 | SurfaceMode, FragmentSurfaceAdapter, ColumnContext | `test_dispatch_ctx_list_empty_state.py`, `test_dispatch_ctx_list_search_filter.py` | test_dispatch_ctx_defaults_empty_kind_to_collection, test_pick_empty_state_falls_back_to_empty_message_when_typed_unset… |
| `(module)` | 5 | FragmentRenderer | `test_form_field_parity_phase3b.py`, `test_raw_data_honesty_1d.py` | test_number_default_seeds_value_on_create, test_enum_default_selects_option_on_create… |
| `(module)` | 5 | PythonAuditAgent | `test_python_audit_exceptions.py`, `test_python_audit_magic_string_typing.py`, `test_python_audit_n_plus_one.py` (+2 more) | test_heuristic_yields_finding_with_catalogue_entry, test_heuristic_yields_finding_with_catalogue_entry… |
| `(module)` | 5 | TYPED_SECTION_TYPES, render_typed_section | `test_site_section_final_builders.py`, `test_site_section_hero_builder.py`, `test_site_section_medium_builders.py` (+2 more) | test_pricing_cta_variant_override_wins_over_default_1263, test_hero_cta_falls_back_to_default_href_and_label… |
| `(module)` | 4 | load_project_appspec, create_page_routes, register_default_renderers | `test_simple_task_chrome_smoke.py`, `test_simple_task_no_jinja_when_chrome_on.py` | test_simple_task_chrome_workspace_routes_dont_crash, test_primary_surface_routes_render_zero_jinja_templates… |
| `(module)` | 4 | app | `test_cli_inspect.py`, `test_perf_cli_trace.py` | test_inspect_renderers_exits_2_when_no_dazzle_toml, test_traceable_page_urls_filters_to_getable_pages… |
| `(module)` | 4 | FragmentRenderer | `test_form_field_parity_phase3b.py`, `test_raw_data_honesty_1d.py` | test_required_enum_has_disabled_placeholder_selected, test_edit_value_wins_over_default… |
| `(module)` | 4 | FragmentRenderer | `test_form_field_parity_phase3b.py`, `test_raw_data_honesty_1d.py` | test_enum_with_value_does_not_select_placeholder, test_help_renders_hint_paragraph_and_describedby… |
| `(module)` | 4 | ir | `test_ir.py`, `test_repository_temporal_retry.py`, `test_rhythm_ir_integration.py` | test_api, test_end_date_fallback_resolves_after_rollback… |
| `(module)` | 4 | TokenType, tokenize | `test_lexer_grant_schema.py`, `test_rhythm_lexer.py` | test_grant_schema_keyword_tokenized, test_rhythm_keyword_tokenized… |

## View 2 — Implementation-mirror file candidates

Files dominated by tests that pin internal call shapes (high mocks, short body, low public-import diversity). Strategy doc tags these as the highest-leverage *deletion* targets — replace with one canonical behavior test per shape.

- **Files flagged**: 11
- **Tests in flagged files**: 150

### Top 30 candidates (by test count)

| File | Tests | Mirror share | Avg mocks | Avg body | Avg asserts | Priv imports/test |
|---|---:|---:|---:|---:|---:|---:|
| `tests/unit/test_cli_db_ops.py` | 24 | 0.0 | 2.5 | 16.7 | 2.2 | 0.4 |
| `tests/unit/test_qa/test_cli_signing_wiring.py` | 22 | 0.23 | 2.4 | 17.0 | 2.6 | 1.0 |
| `tests/unit/test_playwright_executor_enrichment.py` | 17 | 0.0 | 2.9 | 14.1 | 2.9 | 0.1 |
| `tests/unit/test_domain_user_attributes.py` | 14 | 0.5 | 1.7 | 18.9 | 2.5 | 0.5 |
| `tests/unit/test_email_verification_routes.py` | 12 | 0.0 | 2.2 | 12.8 | 2.0 | 0.2 |
| `tests/unit/test_mapping_executor_cache.py` | 12 | 0.0 | 2.4 | 17.2 | 1.9 | 0.0 |
| `tests/unit/test_cli_tenant.py` | 11 | 0.0 | 4.2 | 14.9 | 2.7 | 0.0 |
| `tests/unit/test_tenant_registry.py` | 11 | 0.0 | 2.6 | 18.5 | 1.7 | 0.1 |
| `tests/unit/test_auth_subsystem_jwt_wiring.py` | 10 | 0.0 | 2.2 | 20.6 | 2.6 | 0.0 |
| `tests/unit/test_interaction_server_fixture.py` | 9 | 0.0 | 2.7 | 16.3 | 1.3 | 0.2 |
| `tests/unit/test_custom_mode_dispatch.py` | 8 | 0.0 | 2.0 | 18.2 | 2.9 | 1.0 |

## View 3 — Twin file pairs (body-shape multiset overlap ≥70%)

Pairs of files whose tests' assertion-shape distributions match. One may supersede the other; or they're testing the same shape on two entities (consolidate).

- **Twin pairs**: 12815

### Top 30 twin pairs

| File A | File B | A | B | Shared | Overlap |
|---|---|---:|---:|---:|---:|
| `test_query_builder.py` | `test_parser.py` | 55 | 132 | 41 | 0.75 |
| `test_pdf_viewer_component.py` | `test_region_adapter.py` | 52 | 121 | 38 | 0.73 |
| `test_mapping_executor.py` | `test_parser.py` | 49 | 132 | 36 | 0.73 |
| `test_parser.py` | `test_rbac_verifier.py` | 132 | 43 | 36 | 0.84 |
| `test_data_primitives.py` | `test_parser.py` | 37 | 132 | 34 | 0.92 |
| `test_fidelity_scorer.py` | `test_parser.py` | 39 | 132 | 34 | 0.87 |
| `test_region_adapter.py` | `test_two_factor_views.py` | 121 | 35 | 31 | 0.89 |
| `test_fidelity_scorer.py` | `test_rbac_verifier.py` | 39 | 43 | 29 | 0.74 |
| `test_parser.py` | `test_workspace_layout_prefs.py` | 132 | 31 | 29 | 0.94 |
| `test_datatable_handler.py` | `test_parser.py` | 30 | 132 | 28 | 0.93 |
| `test_parser.py` | `test_structured_content.py` | 132 | 32 | 28 | 0.88 |
| `test_query_builder.py` | `test_data_primitives.py` | 55 | 37 | 27 | 0.73 |
| `test_auth.py` | `test_access_control.py` | 80 | 35 | 26 | 0.74 |
| `test_data_primitives.py` | `test_expression_lang.py` | 37 | 83 | 26 | 0.7 |
| `test_agent_performance_resource.py` | `test_persona_journey.py` | 33 | 56 | 26 | 0.79 |
| `test_datatable_handler.py` | `test_expression_lang.py` | 30 | 83 | 26 | 0.87 |
| `test_datatable_handler.py` | `test_mapping_executor.py` | 30 | 49 | 26 | 0.87 |
| `test_events.py` | `test_parser.py` | 36 | 132 | 26 | 0.72 |
| `test_expression_lang.py` | `test_org_activation.py` | 83 | 36 | 26 | 0.72 |
| `test_expression_lang.py` | `test_rbac_ui_fixes.py` | 83 | 30 | 26 | 0.87 |
| `test_persona_journey.py` | `test_ux_contract_checker.py` | 56 | 36 | 26 | 0.72 |
| `test_scim_routes.py` | `test_parser.py` | 33 | 132 | 25 | 0.76 |
| `test_agent_auth.py` | `test_persona_journey.py` | 26 | 56 | 25 | 0.96 |
| `test_agent_performance_resource.py` | `test_ux_contract_checker.py` | 33 | 36 | 25 | 0.76 |
| `test_datatable_handler.py` | `test_rbac_verifier.py` | 30 | 43 | 25 | 0.83 |
| `test_parser.py` | `test_rbac_ui_fixes.py` | 132 | 30 | 25 | 0.83 |
| `test_predicate_compiler.py` | `test_region_adapter.py` | 34 | 121 | 25 | 0.74 |
| `test_auth.py` | `test_rbac_ui_fixes.py` | 80 | 30 | 24 | 0.8 |
| `test_auth.py` | `test_structured_content.py` | 80 | 32 | 24 | 0.75 |
| `test_query_builder.py` | `test_workspace_layout_prefs.py` | 55 | 31 | 24 | 0.77 |
