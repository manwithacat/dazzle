# Principle → gate registry

**Rendered from `tests/unit/fixtures/principle_gates.json`** by
`tests/unit/test_principle_gate_registry.py` — edit the fixture, not this page.

The repo's standard, from #1749: *a claim nothing checks is a hope.* This page
answers one question per doctrine rule in `AGENTS.md`, for an agent that has
never seen this repo: **what stops me from breaking this?**

14 of 27 rules are mechanically enforced. The rest are review
conventions — real, but nothing turns them red, and knowing which is which is
the difference between a rule you can lean on and one you have to remember.

| Rule | Enforced by | Kind |
|---|---|---|
| **Type hints required** | `make type-check` | `gate` |
| **Pydantic models** | — | `review` |
| **Explicit dependencies** | `tests/unit/test_no_new_mutable_globals_1445.py` | `gate` |
| **No backward compat shims** | `tests/unit/test_no_compat_shims.py`<br>`tests/unit/test_no_shims.py`<br>`tests/unit/test_no_fastapi_compat.py` | `gate` |
| **No new singletons** | `tests/unit/test_no_new_mutable_globals_1445.py` | `gate` |
| **No SQLite in the app runtime** | `tests/unit/test_import_contracts.py` | `gate` |
| **No SPA frameworks** | `tests/unit/test_typed_runtime_no_jinja.py` | `partial` |
| **No field conditions in `permit:`** | `tests/unit/test_scope_rules.py` | `test` |
| **No `from __future__ import annotations`** | `tests/unit/test_no_future_annotations_in_routes.py` | `gate` |
| **All schema changes via Alembic** | — | `review` |
| **DB artifacts have one registry** | `tests/unit/test_db_artifact_contract.py` | `gate` |
| **Clean worktree** | `make push-gate` | `gate` |
| **Bump on human-initiated ships, not on `/improve` cycles** | — | `review` |
| **Local CI tiers (concordance)** | `tests/unit/test_ci_changed_packs.py`<br>`tests/unit/test_preflight_surface.py`<br>`tests/unit/test_push_gate.py` | `gate` |
| **Agent Guidance in CHANGELOG** | — | `review` |
| **Commit attribution (read before `git commit`)** | `Verify AI Co-Authorship` | `ci` |
| **Alpine.js is deprecated for new code** | — | `review` |
| **Taste (HaTchi-MaXchi)** | `tests/unit/test_taste_doc_drift.py`<br>`HaTchi-MaXchi standalone CI (mirror)` | `partial` |
| **Card safety** | `tests/unit/test_component_hygiene.py`<br>`tests/unit/test_widget_contract.py`<br>`tests/unit/test_htmx_undefined_guards.py` | `gate` |
| **`redundancy_report.md`** | `tests/unit/test_clone_ratchet.py`<br>`tests/unit/test_dead_definition_ratchet.py`<br>`tests/unit/test_complexity_ratchet.py` | `partial` |
| **`taxonomy_report.md`** | — | `review` |
| **MCP test isolation** | — | `review` |
| **PersonaSpec identity** | `tests/unit/test_dedup_footgun_gates.py` | `gate` |
| **State machine states** | `tests/unit/test_dedup_footgun_gates.py` | `gate` |
| **KG re-seeding** | — | `review` |
| **Author / Committer** | — | `review` |
| **Agent recognition** | — | `review` |

## Notes

| Rule | Why |
|---|---|
| **Type hints required** | mypy over src/dazzle; run by the CI lint job and by `make ci-fast`. |
| **Pydantic models** | No mechanical gate. A plain dataclass crossing a module boundary is a review finding, not a red test. |
| **Explicit dependencies** | Ratchet on module-level mutable state — the observable form of a hidden global. |
| **No backward compat shims** | Three shim detectors (generic, FastAPI-specific, deprecation-shaped). ADR-0003. |
| **No new singletons** | Same ratchet, ADR-0005 lens: an allowlist entry must be justified or removed. |
| **No SQLite in the app runtime** | import-linter contract: the backend layer is Postgres-only, no direct sqlite/aiosqlite (ADR-0008). |
| **No SPA frameworks** | The typed substrate gate keeps Jinja-era rendering out, which is what makes an SPA unnecessary — but nothing scans for a client framework. Review-only in practice. |
| **No field conditions in `permit:`** | Enforced by the parser — `_has_field_condition` raises 'Field condition in permit: block. Move to a scope: block' — and asserted in test_scope_rules.py, which is NOT a `-m gate` module, so a new parser path could widen it silently. Candidate for promotion. |
| **No `from __future__ import annotations`** | ADR-0014: FastAPI route files need real annotations. |
| **All schema changes via Alembic** | No gate detects a hand-written DDL. Review finding; the artefact registry below is the closest proxy. |
| **DB artifacts have one registry** | Registry completeness + boot-entry gating (the #1495 class). test_db_baseline_reconcile_1309 covers the baseline side but carries no gate marker, so it does not run under `make ci-fast` on its own. |
| **Clean worktree** | `scripts/push_gate.py` refuses a push without a fresh tier-0 stamp, a throttle window and green CI. |
| **Bump on human-initiated ships, not on `/improve` cycles** | Deliberately review-enforced: an agent that /bumps on its own cycle is a process error, not a code one. |
| **Local CI tiers (concordance)** | Path-aware packs, the preflight surface gate, and the push gate that ties them together. |
| **Agent Guidance in CHANGELOG** | Release-note discipline; no gate reads the changelog. |
| **Commit attribution (read before `git commit`)** | CI rejects a missing or malformed trailer. The 'never set local user.*' half is review-enforced — a harness identity in .git/config once made a harness the primary author of a human's commits. |
| **Alpine.js is deprecated for new code** | The vendored runtime is removed, so a violation is a new import — review-only today. Candidate for a gate. |
| **Taste (HaTchi-MaXchi)** | The rubric doc is drift-gated here and the package has its own CI (mirrored into Dazzle CI so a red HM plane fails the parent). The judgement itself is a panel, not a test. |
| **Card safety** | The 8 invariants are scanned by contract_checker and pinned by these gates. |
| **`redundancy_report.md`** | The ratchets enforce the 'do not add a standalone duplicate' half; 'extend the existing parametrize set' is review-enforced. |
| **`taxonomy_report.md`** | Implementation mirrors and tautological tests are judgement calls; the distillation audit is advisory. |
| **MCP test isolation** | The 3-phase conftest fixture is the mechanism; bypassing it is review-enforced. |
| **PersonaSpec identity** | Forbids re-inlining the identity footgun. |
| **State machine states** | Forbids re-inlining the plain-string-vs-object footgun. |
| **KG re-seeding** | `ensure_seeded()` version-key discipline — bump on data change, review-enforced. |
| **Author / Committer** | Author/Committer must be the human account owner, via **global** git config. Review-enforced on purpose: setting a local git identity is invisible to every gate, and a harness identity left in .git/config once made a harness the primary author of a human's commits. |
| **Agent recognition** | The acting harness claims the work via the `Co-Authored-By` trailer; the human stays Author. The CI check covers the trailer's presence, not which harness claimed it. |

## Reading the kinds

| Kind | Meaning |
|---|---|
| `gate` | A `-m gate` test module or make target. Break it and `make ci-fast` is red. |
| `test` | Enforced by behaviour (e.g. a parser error) and asserted by a test that is not itself gated. |
| `ci` | A CI check rather than a pytest gate. |
| `partial` | A gate defends part of the rule; the rest is review. |
| `review` | Nothing enforces it. Review convention. |

Part of the agent-cognition programme (W7, #1759): an alternate agent should
be able to read this page and know which rules will stop it.
