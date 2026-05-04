# Test Cross-File Audit — Pass 3

Three structural views the per-file Pass-2 redundancy report doesn't capture.

## View 1 — Cross-file shape clusters

Tests sharing the same `(class_name, assertion_shape)` across multiple files. Often means a test pattern was copy-pasted across handler/parser files; one parametric test could replace many.

- **Clusters of size ≥4 across ≥2 files**: 46
- **Tests inside cross-file clusters**: 593
- **Theoretical saving**: ~547 if each cluster collapses to one parametric test

### Top 25 cross-file clusters

| Class | Size | Files | Sample tests |
|---|---:|---|---|
| `(module)` | 117 | `test_golden_master.py`, `test_runtime_e2e.py`, `test_backlog_findings.py` (+47 more) | test_dsl_parsing_is_deterministic, test_example_validates… |
| `(module)` | 72 | `test_attempted.py`, `test_mission.py`, `test_tools.py` (+31 more) | test_mark_attempted_updates_entry, test_null_observer_returns_empty_state… |
| `(module)` | 56 | `test_end_to_end.py`, `test_e2e_handler.py`, `test_agent_commands_handler.py` (+22 more) | test_error_handling_invalid_reference, test_describe_mode_returns_error_on_unknown… |
| `(module)` | 39 | `test_case_file.py`, `test_tools.py`, `test_fitness_handler.py` (+20 more) | test_to_prompt_text_large_file_line_number_width, test_read_file_rejects_absolute_path… |
| `(module)` | 26 | `test_case_file.py`, `test_budget.py`, `test_contract_parser.py` (+13 more) | test_build_case_file_no_file_path_in_evidence_yields_none_locus, test_build_case_file_extracted_file_missing_yields_none_locus… |
| `(module)` | 22 | `test_proposal.py`, `test_config.py`, `test_models.py` (+9 more) | test_proposal_construction, test_load_config_honours_overrides… |
| `(module)` | 16 | `test_attempted.py`, `test_tools.py`, `test_cross_check.py` (+8 more) | test_save_load_round_trip, test_rebuild_from_blocked_artefact… |
| `(module)` | 16 | `test_tools.py`, `test_agent_command_models.py`, `test_agent_commands_handler.py` (+9 more) | test_read_file_missing_with_similar_suggestions, test_render_improve_skill… |
| `(module)` | 15 | `test_mode_a_integration.py`, `test_api_surface_drift.py`, `test_auth_schema_exclusion.py` (+8 more) | test_mode_a_stale_lock_recovery, test_surface_matches_baseline… |
| `(module)` | 14 | `test_bulk_count_via_data_attr.py`, `test_completeness_rules.py`, `test_component_rules.py` (+5 more) | test_bulk_actions_no_x_show_or_x_text, test_pagination_no_x_show_or_x_text… |
| `(module)` | 11 | `test_comparator.py`, `test_independence.py`, `test_interlock.py` (+5 more) | test_same_findings_no_regression, test_finding_cleared_with_no_new_findings… |
| `(module)` | 11 | `test_animation_tokens.py`, `test_heading_scale_tokens.py`, `test_optimistic_redo_reconcile.py` (+1 more) | test_animation_tokens_reference_existing_keyframes, test_workspace_title_uses_token… |
| `(module)` | 11 | `test_compliance_review.py`, `test_compliance_slicer.py`, `test_ir.py` (+4 more) | test_new_schema_review, test_summary_recalculated… |
| `TestEdgeCases` | 9 | `test_entity_list_projections.py`, `test_example_index.py`, `test_search_schema_ddl.py` (+1 more) | test_surface_without_view_ref_or_sections_not_projected, test_surface_with_missing_view_ignored… |
| `(module)` | 7 | `test_runner.py`, `test_api_kb_project_local.py`, `test_fitness_repr_parser.py` (+2 more) | test_walk_queue_top_n, test_project_local_overrides_builtin… |
| `(module)` | 7 | `test_fitness_strategy_integration.py`, `test_walker.py`, `test_constraint_errors.py` (+2 more) | test_fitness_strategy_calls_engine_run, test_walker_records_error_on_executor_failure… |
| `(module)` | 6 | `test_case_file.py`, `test_api_kb_project_local.py`, `test_compliance_citation.py` (+2 more) | test_build_case_file_empty_locus_file, test_locus_windowing_no_evidence_lines… |
| `(module)` | 6 | `test_triage_cli.py`, `test_agent_command_models.py`, `test_rhythm_ir.py` (+2 more) | test_queue_json_output, test_loop_config_fields… |
| `(module)` | 6 | `test_alpine_error_handler.py`, `test_htmx_preload_silence.py`, `test_idiomorph_alpine_patch.py` (+2 more) | test_handler_wraps_in_real_error, test_silence_calls_prevent_default… |
| `(module)` | 6 | `test_alpine_error_handler.py`, `test_cli.py`, `test_filter_ref_select_cancellation.py` (+2 more) | test_handler_includes_expression_in_message, test_handler_attaches_cause… |
| `(module)` | 6 | `test_completeness_rules.py`, `test_component_rules.py`, `test_notification_email_shape.py` (+2 more) | test_create_permit_no_create_surface_produces_create_relevance, test_entity_with_permissions_and_no_surfaces_is_unreachable… |
| `TestMoneyFieldExpansion` | 6 | `test_entity_list_projections.py`, `test_fidelity_scorer.py` | test_money_field_expands_to_minor_and_currency, test_multiple_money_fields_all_expand… |
| `(module)` | 6 | `test_fuzz_runtime_importable.py`, `test_openapi_importer.py`, `test_quick_wins.py` | test_richtext_battery_present, test_scaffold_blank_basic… |
| `TestUploadTicketRoute` | 6 | `test_storage_cycle3.py`, `test_storage_cycle5.py` | test_registers_route_for_storage_field, test_no_route_for_entity_without_storage_field… |
| `TestRegionContextWiring` | 6 | `test_workspace_reference_overlays.py`, `test_workspace_routes.py` | test_line_overlays_flatten_to_dicts, test_action_passed_through… |

## View 2 — Implementation-mirror file candidates

Files dominated by tests that pin internal call shapes (high mocks, short body, low public-import diversity). Strategy doc tags these as the highest-leverage *deletion* targets — replace with one canonical behavior test per shape.

- **Files flagged**: 10
- **Tests in flagged files**: 136

### Top 30 candidates (by test count)

| File | Tests | Mirror share | Avg mocks | Avg body | Avg asserts | Priv imports/test |
|---|---:|---:|---:|---:|---:|---:|
| `tests/unit/test_agent_core.py` | 33 | 0.0 | 2.0 | 17.5 | 2.1 | 0.0 |
| `tests/unit/test_composition_styles.py` | 17 | 0.0 | 4.3 | 15.7 | 1.9 | 0.0 |
| `tests/unit/test_domain_user_attributes.py` | 14 | 0.5 | 1.7 | 18.9 | 2.5 | 0.5 |
| `tests/unit/test_mapping_executor_cache.py` | 12 | 0.0 | 2.4 | 17.2 | 1.9 | 0.0 |
| `tests/unit/test_cli_tenant.py` | 11 | 0.0 | 4.1 | 10.6 | 2.4 | 0.0 |
| `tests/unit/test_github_issues.py` | 11 | 0.0 | 2.0 | 8.8 | 1.6 | 0.4 |
| `tests/unit/test_interaction_server_fixture.py` | 10 | 0.0 | 3.0 | 16.8 | 1.2 | 0.3 |
| `tests/unit/test_version_manager_pg.py` | 10 | 0.0 | 3.6 | 15.7 | 1.6 | 0.0 |
| `tests/unit/test_cli_db_ops.py` | 9 | 0.0 | 2.6 | 13.6 | 2.2 | 0.0 |
| `tests/unit/test_tenant_registry.py` | 9 | 0.0 | 2.4 | 16.0 | 1.7 | 0.0 |

## View 3 — Twin file pairs (body-shape multiset overlap ≥70%)

Pairs of files whose tests' assertion-shape distributions match. One may supersede the other; or they're testing the same shape on two entities (consolidate).

- **Twin pairs**: 7144

### Top 30 twin pairs

| File A | File B | A | B | Shared | Overlap |
|---|---|---:|---:|---:|---:|
| `test_dz_richtext.py` | `test_workspace_routes.py` | 87 | 394 | 75 | 0.86 |
| `test_workspace_rendering.py` | `test_workspace_routes.py` | 61 | 394 | 52 | 0.85 |
| `test_pdf_viewer_component.py` | `test_workspace_routes.py` | 49 | 394 | 42 | 0.86 |
| `test_persona_journey.py` | `test_workspace_routes.py` | 56 | 394 | 41 | 0.73 |
| `test_agent_integration_dependency.py` | `test_agent_performance_resource.py` | 41 | 47 | 38 | 0.93 |
| `test_dsl_emitter.py` | `test_workspace_routes.py` | 51 | 394 | 38 | 0.75 |
| `test_agent_performance_resource.py` | `test_workspace_routes.py` | 47 | 394 | 37 | 0.79 |
| `test_composition_audit.py` | `test_dsl_emitter.py` | 89 | 51 | 37 | 0.73 |
| `test_aggregate_sql.py` | `test_workspace_routes.py` | 48 | 394 | 36 | 0.75 |
| `test_composition_visual.py` | `test_workspace_routes.py` | 51 | 394 | 36 | 0.71 |
| `test_fidelity_scorer.py` | `test_workspace_routes.py` | 36 | 394 | 36 | 1.0 |
| `test_mapping_executor.py` | `test_parser.py` | 46 | 131 | 35 | 0.76 |
| `test_dashboard_builder_triggers.py` | `test_workspace_routes.py` | 34 | 394 | 34 | 1.0 |
| `test_parser.py` | `test_rbac_enforcement.py` | 131 | 45 | 34 | 0.76 |
| `test_richtext_processor.py` | `test_workspace_routes.py` | 40 | 394 | 34 | 0.85 |
| `test_agent_deployment_state.py` | `test_agent_integration_dependency.py` | 45 | 41 | 33 | 0.8 |
| `test_agent_deployment_state.py` | `test_agent_performance_resource.py` | 45 | 47 | 33 | 0.73 |
| `test_agent_deployment_state.py` | `test_workspace_routes.py` | 45 | 394 | 33 | 0.73 |
| `test_agent_integration_dependency.py` | `test_workspace_routes.py` | 41 | 394 | 33 | 0.8 |
| `test_docker_generation.py` | `test_workspace_routes.py` | 36 | 394 | 33 | 0.92 |
| `test_fidelity_scorer.py` | `test_parser.py` | 36 | 131 | 33 | 0.92 |
| `test_parser.py` | `test_vendor_mock_generator.py` | 131 | 36 | 33 | 0.92 |
| `test_rbac_enforcement.py` | `test_workspace_routes.py` | 45 | 394 | 33 | 0.73 |
| `test_site_templates.py` | `test_workspace_routes.py` | 38 | 394 | 33 | 0.87 |
| `test_agent_integration_dependency.py` | `test_agent_operational_hygiene.py` | 41 | 34 | 32 | 0.94 |
| `test_expression_lang.py` | `test_vendor_mock_generator.py` | 83 | 36 | 32 | 0.89 |
| `test_vendor_mock_generator.py` | `test_workspace_routes.py` | 36 | 394 | 32 | 0.89 |
| `test_agent_data_integrity.py` | `test_workspace_routes.py` | 32 | 394 | 31 | 0.97 |
| `test_agent_integration_dependency.py` | `test_fidelity_scorer.py` | 41 | 36 | 31 | 0.86 |
| `test_agent_operational_hygiene.py` | `test_agent_performance_resource.py` | 34 | 47 | 31 | 0.91 |
