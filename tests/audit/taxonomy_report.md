# Test Suite Taxonomy — Pass 1 (17,093 test functions)

Static classification per `docs/proposals/Suite Distillation Strategy.md`. No execution; AST + import-shape heuristics only. Confidence < 0.8 means the classifier could be wrong; see rationale field.

## Distribution

| Archetype | Count | % | High-confidence count |
|---|---:|---:|---:|
| contract | 14,067 | 82.3% | 0 |
| smoke | 2,059 | 12.0% | 958 |
| parametric_cluster | 439 | 2.6% | 439 |
| regression_pin | 346 | 2.0% | 346 |
| implementation_mirror | 84 | 0.5% | 0 |
| property_based | 67 | 0.4% | 67 |
| belt_and_braces | 18 | 0.1% | 0 |
| snapshot | 13 | 0.1% | 13 |

## Action thresholds

- **Definitely keep**: 14,932 (contract + regression_pin + parametric + snapshot + property_based)
- **Property-based (fuzzable; the target archetype)**: 67
- **Review for collapse/rewrite**: 102 (implementation_mirror + belt_and_braces)
- **Smoke tests** (canary; keep but never as sole coverage): 2,059

## Top 10 implementation-mirror files

- `tests/unit/test_pitch_generator.py` — 12 likely-mirror tests
- `tests/unit/test_domain_user_attributes.py` — 7 likely-mirror tests
- `tests/unit/test_narrative_compiler.py` — 7 likely-mirror tests
- `tests/unit/test_rbac_enforcement.py` — 5 likely-mirror tests
- `tests/unit/test_audit_log_hash_chain.py` — 4 likely-mirror tests
- `tests/unit/test_qa/test_cli_signing_wiring.py` — 4 likely-mirror tests
- `tests/integration/test_rbac_verifier_e2e.py` — 3 likely-mirror tests
- `tests/unit/test_audit_log.py` — 3 likely-mirror tests
- `tests/unit/test_cli_coverage.py` — 3 likely-mirror tests
- `tests/unit/test_composition_report.py` — 3 likely-mirror tests

## Top 10 smoke-test files

- `tests/unit/render/fragment/test_data_primitives.py` — 50 smoke tests
- `tests/unit/test_csrf_disposition_phase3.py` — 18 smoke tests
- `tests/unit/test_expression_lang.py` — 18 smoke tests
- `tests/unit/test_invariant_evaluator.py` — 18 smoke tests
- `tests/unit/test_access_control.py` — 17 smoke tests
- `tests/unit/test_csrf_origin_gate_phase2.py` — 17 smoke tests
- `tests/unit/test_parser.py` — 17 smoke tests
- `tests/unit/test_aggregate_expression_l3.py` — 15 smoke tests
- `tests/unit/test_composition_audit.py` — 14 smoke tests
- `tests/unit/test_onboarding_resolver.py` — 14 smoke tests

## Notes on the classifier

- **smoke**: 0-1 trivial asserts (`is`, `is not`, `==`, truthy name)
- **implementation_mirror**: imports private (`_`-prefixed) callables AND ≥3 mocks, OR imports ≥2 private callables. May contain false positives — review the rationale field.
- **parametric_cluster**: already uses `@pytest.mark.parametrize` ≥2 cases — these are the **good** shape; included here for visibility, not for action.
- **regression_pin**: name/docstring references an issue or PR number (`#1234`, `closes #X`, `issue 42`).
- **belt_and_braces**: same test function name appears in tests/unit/ + tests/integration/ or tests/unit/ + tests/e2e/. May be intentional (testing different layers) — review.
- **snapshot**: uses syrupy `snapshot` fixture in an assert. One bit of signal each.
- **contract**: default; could be a real contract test OR a hidden mirror that the static classifier didn't catch. Pass 2 (redundancy clustering) and Pass 4 (contract extraction) refine this further.
