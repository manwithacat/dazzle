# Test Suite Taxonomy — Pass 1 (14,257 test functions)

Static classification per `docs/proposals/Suite Distillation Strategy.md`. No execution; AST + import-shape heuristics only. Confidence < 0.8 means the classifier could be wrong; see rationale field.

## Distribution

| Archetype | Count | % | High-confidence count |
|---|---:|---:|---:|
| contract | 12,314 | 86.4% | 0 |
| smoke | 1,633 | 11.5% | 537 |
| regression_pin | 180 | 1.3% | 180 |
| parametric_cluster | 60 | 0.4% | 60 |
| implementation_mirror | 52 | 0.4% | 0 |
| snapshot | 12 | 0.1% | 12 |
| belt_and_braces | 6 | 0.0% | 0 |

## Action thresholds

- **Definitely keep**: 12,566 (contract + regression_pin + parametric + snapshot)
- **Review for collapse/rewrite**: 58 (implementation_mirror + belt_and_braces)
- **Smoke tests** (canary; keep but never as sole coverage): 1,633

## Top 10 implementation-mirror files

- `tests/unit/test_pitch_generator.py` — 12 likely-mirror tests
- `tests/unit/test_domain_user_attributes.py` — 7 likely-mirror tests
- `tests/unit/test_narrative_compiler.py` — 7 likely-mirror tests
- `tests/unit/test_rbac_enforcement.py` — 4 likely-mirror tests
- `tests/unit/test_cli_coverage.py` — 3 likely-mirror tests
- `tests/unit/test_composition_report.py` — 3 likely-mirror tests
- `tests/unit/test_heatmap_regression.py` — 3 likely-mirror tests
- `tests/unit/test_scope_via.py` — 3 likely-mirror tests
- `tests/unit/fitness/test_fitness_strategy_integration.py` — 2 likely-mirror tests
- `tests/unit/test_audit_log.py` — 2 likely-mirror tests

## Top 10 smoke-test files

- `tests/unit/test_access_control.py` — 37 smoke tests
- `tests/unit/test_invariant_evaluator.py` — 34 smoke tests
- `tests/unit/test_composition_audit.py` — 26 smoke tests
- `tests/unit/test_expression_lang.py` — 24 smoke tests
- `tests/unit/test_pipeline_detail.py` — 20 smoke tests
- `tests/unit/test_app_theme_registry.py` — 16 smoke tests
- `tests/unit/test_compliance_matching.py` — 16 smoke tests
- `tests/unit/test_layout_ir.py` — 16 smoke tests
- `tests/unit/test_condition_evaluator_role_check.py` — 15 smoke tests
- `tests/unit/test_composition_references.py` — 14 smoke tests

## Notes on the classifier

- **smoke**: 0-1 trivial asserts (`is`, `is not`, `==`, truthy name)
- **implementation_mirror**: imports private (`_`-prefixed) callables AND ≥3 mocks, OR imports ≥2 private callables. May contain false positives — review the rationale field.
- **parametric_cluster**: already uses `@pytest.mark.parametrize` ≥2 cases — these are the **good** shape; included here for visibility, not for action.
- **regression_pin**: name/docstring references an issue or PR number (`#1234`, `closes #X`, `issue 42`).
- **belt_and_braces**: same test function name appears in tests/unit/ + tests/integration/ or tests/unit/ + tests/e2e/. May be intentional (testing different layers) — review.
- **snapshot**: uses syrupy `snapshot` fixture in an assert. One bit of signal each.
- **contract**: default; could be a real contract test OR a hidden mirror that the static classifier didn't catch. Pass 2 (redundancy clustering) and Pass 4 (contract extraction) refine this further.
