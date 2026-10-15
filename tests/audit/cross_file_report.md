# Test Cross-File Audit — Pass 3

Three structural views the per-file Pass-2 redundancy report doesn't capture.

## View 1 — Cross-file shape clusters

Tests sharing the same `(class_name, assertion_shape, public_target)` across multiple files — same assert shape AND the same deduped set of public dazzle callables. A cluster here is a genuinely copy-pasted pattern that one shared parametrised helper could replace. (Pre-#1530 this view keyed on shape alone, which matched hundreds of unrelated files; the target discriminator makes the numbers actionable.)

- **Clusters of size ≥4 across ≥2 files**: 2
- **Tests inside cross-file clusters**: 12
- **Theoretical saving**: ~10 if each cluster collapses to one parametric test
- **Skipped (no attributable public target)**: 1,192 tests — shape matches without a shared target are not actionable

### Top 25 cross-file clusters

| Class | Size | Target | Files | Sample tests |
|---|---:|---|---|---|
| `(module)` | 8 | ParseError | `test_cohort_strip_composite_parser_1144.py`, `test_day_timeline_config_parser.py`, `test_entity_card_config_parser.py` (+2 more) | test_default_separator_when_omitted, test_parses_minimal_config… |
| `(module)` | 4 | ir | `test_ir.py`, `test_repository_temporal_retry.py`, `test_rhythm_ir_integration.py` | test_api, test_end_date_fallback_resolves_after_rollback… |

## View 2 — Implementation-mirror file candidates

Files dominated by tests that pin internal call shapes (high mocks, short body, low public-import diversity). Strategy doc tags these as the highest-leverage *deletion* targets — replace with one canonical behavior test per shape.

- **Files flagged**: 9
- **Tests in flagged files**: 114

### Top 30 candidates (by test count)

| File | Tests | Mirror share | Avg mocks | Avg body | Avg asserts | Priv imports/test |
|---|---:|---:|---:|---:|---:|---:|
| `tests/unit/test_cli_db_ops.py` | 24 | 0.0 | 2.5 | 16.7 | 2.2 | 0.4 |
| `tests/unit/test_playwright_executor_enrichment.py` | 17 | 0.0 | 2.9 | 14.1 | 2.9 | 0.1 |
| `tests/unit/test_email_verification_routes.py` | 12 | 0.0 | 2.2 | 12.8 | 2.0 | 0.2 |
| `tests/unit/test_mapping_executor_cache.py` | 12 | 0.0 | 2.4 | 17.2 | 1.9 | 0.0 |
| `tests/unit/test_cli_tenant.py` | 11 | 0.0 | 4.2 | 14.9 | 2.7 | 0.0 |
| `tests/unit/test_tenant_registry.py` | 11 | 0.0 | 2.6 | 18.5 | 1.7 | 0.1 |
| `tests/unit/test_auth_subsystem_jwt_wiring.py` | 10 | 0.0 | 2.2 | 20.6 | 2.6 | 0.0 |
| `tests/unit/test_interaction_server_fixture.py` | 9 | 0.0 | 2.7 | 16.3 | 1.3 | 0.2 |
| `tests/unit/test_custom_mode_dispatch.py` | 8 | 0.0 | 2.0 | 18.2 | 2.9 | 1.0 |

## View 3 — Twin file pairs (body-shape multiset overlap ≥70%)

Pairs of files whose tests' assertion-shape distributions match. One may supersede the other; or they're testing the same shape on two entities (consolidate).

- **Twin pairs**: 7602

### Top 30 twin pairs

| File A | File B | A | B | Shared | Overlap |
|---|---|---:|---:|---:|---:|
| `test_fidelity_scorer.py` | `test_rbac_verifier.py` | 39 | 43 | 29 | 0.74 |
| `test_expression_lang.py` | `test_org_activation.py` | 82 | 36 | 26 | 0.72 |
| `test_expression_lang.py` | `test_rbac_ui_fixes.py` | 82 | 30 | 26 | 0.87 |
| `test_persona_journey.py` | `test_ux_contract_checker.py` | 55 | 36 | 26 | 0.72 |
| `test_expression_lang.py` | `test_sla_manager.py` | 82 | 32 | 23 | 0.72 |
| `test_workspace_layout_prefs.py` | `test_workspace_rendering.py` | 31 | 42 | 23 | 0.74 |
| `test_curl_test_generator.py` | `test_pdf_viewer_component.py` | 28 | 52 | 22 | 0.79 |
| `test_expression_lang.py` | `test_workspace_layout_prefs.py` | 82 | 31 | 22 | 0.71 |
| `test_onboarding_renderer.py` | `test_pdf_viewer_component.py` | 25 | 52 | 22 | 0.88 |
| `test_demo_data_loader.py` | `test_persona_journey.py` | 27 | 55 | 21 | 0.78 |
| `test_demo_data_loader.py` | `test_schema_diff.py` | 27 | 40 | 21 | 0.78 |
| `test_expression_lang.py` | `test_rbac_enforcement.py` | 82 | 30 | 21 | 0.7 |
| `test_expression_lang.py` | `test_vendor_mock_generator.py` | 82 | 27 | 21 | 0.78 |
| `test_rbac_enforcement.py` | `test_scope_rules.py` | 30 | 49 | 21 | 0.7 |
| `test_rbac_enforcement.py` | `test_sla_manager.py` | 30 | 32 | 21 | 0.7 |
| `test_rbac_enforcement.py` | `test_structured_content.py` | 30 | 32 | 21 | 0.7 |
| `test_css_clip_check.py` | `test_expression_lang.py` | 21 | 82 | 20 | 0.95 |
| `test_css_clip_check.py` | `test_persona_journey.py` | 21 | 55 | 20 | 0.95 |
| `test_css_clip_check.py` | `test_workspace_layout_prefs.py` | 21 | 31 | 20 | 0.95 |
| `test_css_clip_check.py` | `test_workspace_rendering.py` | 21 | 42 | 20 | 0.95 |
| `test_curl_test_generator.py` | `test_list_chrome_parity_phase1.py` | 28 | 33 | 20 | 0.71 |
| `test_parser.py` | `test_workspace_layout_prefs.py` | 25 | 31 | 20 | 0.8 |
| `test_parser.py` | `test_workspace_rendering.py` | 25 | 42 | 20 | 0.8 |
| `test_persona_journey.py` | `test_python_audit_agent.py` | 55 | 27 | 20 | 0.74 |
| `test_persona_journey.py` | `test_vendor_mock_generator.py` | 55 | 27 | 20 | 0.74 |
| `test_predicate_policy_mode.py` | `test_workspace_rendering.py` | 28 | 42 | 20 | 0.71 |
| `test_rbac_enforcement.py` | `test_vendor_mock_generator.py` | 30 | 27 | 20 | 0.74 |
| `test_sla_manager.py` | `test_vendor_mock_generator.py` | 32 | 27 | 20 | 0.74 |
| `test_vendor_mock_generator.py` | `test_workspace_rendering.py` | 27 | 42 | 20 | 0.74 |
| `test_computed_evaluator.py` | `test_expression_lang.py` | 21 | 82 | 19 | 0.9 |
