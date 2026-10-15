# Test Suite Taxonomy — Pass 1 (15,793 test functions)

Static classification per `docs/proposals/Suite Distillation Strategy.md`. No execution; AST + import-shape heuristics only. Confidence < 0.8 means the classifier could be wrong; see rationale field.

## Distribution

| Archetype | Count | % | High-confidence count |
|---|---:|---:|---:|
| contract | 12,872 | 81.5% | 0 |
| smoke | 1,760 | 11.1% | 815 |
| parametric_cluster | 589 | 3.7% | 589 |
| regression_pin | 434 | 2.7% | 434 |
| implementation_mirror | 74 | 0.5% | 0 |
| property_based | 51 | 0.3% | 51 |
| snapshot | 9 | 0.1% | 9 |
| belt_and_braces | 4 | 0.0% | 0 |

## Action thresholds

- **Definitely keep**: 13,955 (contract + regression_pin + parametric + snapshot + property_based)
- **Property-based (fuzzable; the target archetype)**: 51
- **Review for collapse/rewrite**: 78 (implementation_mirror + belt_and_braces)
- **Smoke tests** (canary; keep but never as sole coverage): 1,760

## Top 10 implementation-mirror files

- `tests/unit/test_domain_user_attributes.py` — 7 likely-mirror tests
- `tests/unit/test_qa/test_cli_signing_wiring.py` — 5 likely-mirror tests
- `tests/unit/test_rbac_enforcement.py` — 5 likely-mirror tests
- `tests/unit/test_audit_log_hash_chain.py` — 4 likely-mirror tests
- `tests/unit/test_cli_coverage.py` — 4 likely-mirror tests
- `tests/integration/test_rbac_verifier_e2e.py` — 3 likely-mirror tests
- `tests/unit/test_audit_log.py` — 3 likely-mirror tests
- `tests/unit/test_rbac_login_json_1141.py` — 3 likely-mirror tests
- `tests/unit/test_scope_via.py` — 3 likely-mirror tests
- `tests/unit/test_cli_spec_status.py` — 2 likely-mirror tests

## Top 10 smoke-test files

- `tests/unit/test_csrf_disposition_phase3.py` — 21 smoke tests
- `tests/unit/test_parser.py` — 19 smoke tests
- `tests/unit/test_expression_lang.py` — 18 smoke tests
- `tests/unit/test_invariant_evaluator.py` — 18 smoke tests
- `tests/unit/test_csrf_origin_gate_phase2.py` — 17 smoke tests
- `tests/unit/test_aggregate_expression_l3.py` — 15 smoke tests
- `tests/unit/test_llm_driver.py` — 15 smoke tests
- `tests/unit/test_tenant_config.py` — 14 smoke tests
- `tests/unit/test_workspace_live_refresh_1391.py` — 14 smoke tests
- `tests/unit/test_grant_store.py` — 13 smoke tests

## Notes on the classifier

- **smoke**: 0-1 trivial asserts (`is`, `is not`, `==`, truthy name)
- **implementation_mirror**: imports private (`_`-prefixed) callables AND ≥3 mocks, OR imports ≥2 private callables. May contain false positives — review the rationale field.
- **parametric_cluster**: already uses `@pytest.mark.parametrize` ≥2 cases — these are the **good** shape; included here for visibility, not for action.
- **regression_pin**: name/docstring references an issue or PR number (`#1234`, `closes #X`, `issue 42`).
- **belt_and_braces**: same test function name appears in tests/unit/ + tests/integration/ or tests/unit/ + tests/e2e/. May be intentional (testing different layers) — review.
- **snapshot**: uses syrupy `snapshot` fixture in an assert. One bit of signal each.
- **contract**: default; could be a real contract test OR a hidden mirror that the static classifier didn't catch. Pass 2 (redundancy clustering) and Pass 4 (contract extraction) refine this further.
