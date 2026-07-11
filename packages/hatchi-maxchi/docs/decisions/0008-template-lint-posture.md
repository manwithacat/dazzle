# 0008 — Template lint posture

**Status:** Accepted
**Date:** 2026-07-11
**Stem:** `stems/morph-safe-hypermedia.md`

## Context

HM is optimised for **disciplined, inspectable, agent-maintained** surfaces, not
unrestricted template freestyle. Many morph/Alpine/identity failures are
detectable from **rendered HTML** before a browser test runs. Soft documentation
alone is not enough for agents that optimise for “make it work once.”

## Decision

**Strict template validation is part of the product.** The framework should make
the correct path obvious and the dangerous path noisy — fail early in
development/CI (and optionally at startup on representative fixtures) when
templates violate architectural invariants from decisions 0005–0007.

### Lint goals (normative categories)

| Category | Severity | Gate (in `tests/test_morph_template_gates.py`) |
|----------|----------|-----------------------------------------------|
| Duplicate IDs | **Fail** | `test_no_duplicate_ids_within_a_partial` |
| Unstable IDs (index/random/time) | **Fail** | `test_no_unstable_id_patterns_in_partials` |
| Morph-target identity | **Fail** | `test_morph_swap_elements_have_identity` |
| Alpine attributes in core | **Fail** | `test_no_alpine_*` (+ controllers) |
| JS expression interpolation in bindings | **Fail** | `test_no_template_interpolation_in_js_bindings` |
| DOM state duplication (markup + JSON) | **Fail** | `test_no_json_config_duplicating_dom_structure` |
| ARIA id refs + accessible names | **Fail** | `test_aria_id_references_*`, `test_dialog_and_listbox_*`, `test_aria_expanded_*` |
| `hx-target` validity / brittle ancestry | **Fail** | `test_hx_target_hash_ids_*`, `test_hx_target_not_brittle_*` |
| Morph vs replace policy | **Fail** (clear cases) | `test_swap_policy_*` (no morph on flash; grid-body prefers Morph; exchange toast morph) |
| Third-party island boundary | **Fail** | `test_third_party_patterns_declare_island_boundary` |

Island markers accepted: `data-dz-island` / `data-hm-island`, `data-*-morph-skip`,
`data-*-preserve-boundary`, `data-dz-widget`, or known roots (`data-dz-pdf`).

Exact attribute names for islands and HM markers may evolve; the **categories**
are the decision, not a frozen linter CLI.

### What we do not wait for

- “Only Playwright will catch it” is insufficient for identity/Alpine/morph
  classes that fixtures can assert.
- Agents adding Hyperparts should expect fixture-level DOM invariant tests, not
  only interaction demos.

## Consequences

- New Hyperparts ship with fixtures that encode identity and state contracts.
- **Ratcheted** via `tools/template_lint.py` (pytest:
  `tests/test_morph_template_gates.py`; monorepo `test_hm_package_suite_gate`;
  CLI below). Categories in the table hard-fail on registry + blueprint
  partials and controllers. Gallery mocks that approximate Morph with
  `innerHTML` must document Morph in notes or exchanges.
- **Cross-partial ARIA/targets** use built-in **composition fixtures**
  (`grid` = host+rows+OOB footer; `command` = host+results) — union id
  universe, not a full HTML5 parser.
- **CLI (agents):**
  `python packages/hatchi-maxchi/tools/template_lint.py`
  (`--file`, `--compose grid|command`, `--list-compositions`, default = registry
  + compositions).
- Startup validation of apps remains optional; extract reuse is ready for a
  future `dazzle serve --strict-hm` flag without a new decision.
- **Full HTML parser deferred** — composition fixtures + regex rules match
  author-controlled partials; revisit only if structural bugs cannot be
  expressed as compositions.
- Opinionation is intentional: agent-safe extension beats open-ended customisation.

## See also

- `stems/morph-safe-hypermedia.md`
- `docs/decisions/0005-morphing-policy.md` … `0007-no-alpine-in-core.md`
- `tests/test_morph_template_gates.py`
- Existing contract/DOM tests under `tests/` and dual-lock gates
