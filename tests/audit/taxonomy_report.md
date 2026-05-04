# Test Suite Taxonomy — Pass 1 (12,639 test functions)

Static classification per `docs/proposals/Suite Distillation Strategy.md`. No execution; AST + import-shape heuristics only. Confidence < 0.8 means the classifier could be wrong; see rationale field.

## Distribution

| Archetype | Count | % | High-confidence count |
|---|---:|---:|---:|
| contract | 10,686 | 84.5% | 0 |
| smoke | 1,301 | 10.3% | 523 |
| parametric_cluster | 422 | 3.3% | 422 |
| regression_pin | 158 | 1.3% | 158 |
| implementation_mirror | 54 | 0.4% | 0 |
| snapshot | 12 | 0.1% | 12 |
| belt_and_braces | 6 | 0.0% | 0 |

## Action thresholds

- **Definitely keep**: 11,278 (contract + regression_pin + parametric + snapshot)
- **Review for collapse/rewrite**: 60 (implementation_mirror + belt_and_braces)
- **Smoke tests** (canary; keep but never as sole coverage): 1,301

## Top 10 implementation-mirror files

- `tests/unit/test_pitch_generator.py` — 12 likely-mirror tests
- `tests/unit/test_domain_user_attributes.py` — 7 likely-mirror tests
- `tests/unit/test_narrative_compiler.py` — 7 likely-mirror tests
- `tests/unit/test_rbac_enforcement.py` — 5 likely-mirror tests
- `tests/unit/test_cli_coverage.py` — 3 likely-mirror tests
- `tests/unit/test_composition_report.py` — 3 likely-mirror tests
- `tests/unit/test_heatmap_regression.py` — 3 likely-mirror tests
- `tests/unit/test_scope_via.py` — 3 likely-mirror tests
- `tests/unit/fitness/test_fitness_strategy_integration.py` — 2 likely-mirror tests
- `tests/unit/test_audit_log.py` — 2 likely-mirror tests

## Top 10 smoke-test files

- `tests/unit/test_expression_lang.py` — 18 smoke tests
- `tests/unit/test_invariant_evaluator.py` — 18 smoke tests
- `tests/unit/test_access_control.py` — 17 smoke tests
- `tests/unit/test_layout_ir.py` — 16 smoke tests
- `tests/unit/test_composition_audit.py` — 14 smoke tests
- `tests/unit/test_grant_store.py` — 13 smoke tests
- `tests/unit/test_job_queue.py` — 13 smoke tests
- `tests/unit/test_notification_providers_ses_sendgrid.py` — 13 smoke tests
- `tests/e2e/test_fieldtest_hub_screenshots.py` — 11 smoke tests
- `tests/unit/fitness/investigator/test_proposal.py` — 11 smoke tests

## Notes on the classifier

- **smoke**: 0-1 trivial asserts (`is`, `is not`, `==`, truthy name)
- **implementation_mirror**: imports private (`_`-prefixed) callables AND ≥3 mocks, OR imports ≥2 private callables. May contain false positives — review the rationale field.
- **parametric_cluster**: already uses `@pytest.mark.parametrize` ≥2 cases — these are the **good** shape; included here for visibility, not for action.
- **regression_pin**: name/docstring references an issue or PR number (`#1234`, `closes #X`, `issue 42`).
- **belt_and_braces**: same test function name appears in tests/unit/ + tests/integration/ or tests/unit/ + tests/e2e/. May be intentional (testing different layers) — review.
- **snapshot**: uses syrupy `snapshot` fixture in an assert. One bit of signal each.
- **contract**: default; could be a real contract test OR a hidden mirror that the static classifier didn't catch. Pass 2 (redundancy clustering) and Pass 4 (contract extraction) refine this further.
