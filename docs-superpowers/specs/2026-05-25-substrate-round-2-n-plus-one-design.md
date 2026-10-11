# Agent Code Quality Substrate — Round 2: `PA-LLM-08 n_plus_one_in_user_code`

**Status:** Draft
**Author:** James Barlow (idea), Claude (design)
**Date:** 2026-05-25
**Related issue:** #1257
**Round 1:** `docs/superpowers/specs/2026-05-25-agent-code-quality-substrate-design.md` (shipped v0.75.0)

## 1. Why this design exists

Round 1 of the agent code quality substrate (v0.75.0) closed the `exceptions-as-control-flow` gap end-to-end and established the reusable pipeline: catalogue entry → `@heuristic` on `PythonAuditAgent` → `detectors:` frontmatter wiring → bidirectional drift test → CI gate. Round 2 validates that the pipeline is genuinely reusable at low cost by closing the next gap from the substrate audit (#5-#8): N+1 queries in user `app/` Python.

The pilot question round 1 set out to answer was "is the substrate the right shape?" Round 2 answers "is the substrate cheap to extend?" If round 2 fits in a single small slice, the substrate is paying its rent.

## 2. What already exists

A blunt audit of round-1 infrastructure now reusable by round 2:

- **Counter-prior catalogue entry** at `docs/counter-priors/n-plus-one-in-user-code.md`. Rich content already in place: corpus prior section, two-shape wrong/right examples, three `triggers_code` regexes. The `detectors:` frontmatter field is empty — round 2 fills it.
- **`PythonAuditAgent`** at `src/dazzle/sentinel/agents/python_audit.py`. The `@heuristic` decorator pattern, the `_get_python_files()` helper, the `app/`-only scoping, the `# noqa: PA-LLM-XX` suppression idiom — all reused without modification.
- **Bidirectional drift test** at `tests/unit/test_counter_priors_drift.py:_python_audit_heuristic_ids`. Every declared `PA-*` detector resolves to a `@heuristic` decorator on `PythonAuditAgent`. Adding `PA-LLM-08` to the catalogue frontmatter automatically activates this gate.
- **`Finding.catalogue_entry`** + **`Remediation.references`** — the agent feedback fields. Already integration-tested end-to-end via #1260 (`tests/integration/test_sentinel_findings_mcp_catalogue.py`).
- **CI gate** — `.github/workflows/ci.yml` already runs `dazzle sentinel scan --agent PA --severity high` per example. PA-LLM-08 inherits the same gate at MEDIUM severity (informational until backfill audit promotes — same disposition as PA-LLM-07, tracked in #1256).
- **Scaffolding** — strict Ruff/Pyright/pre-commit ship with `dazzle init`; existing projects use `dazzle quality bootstrap`. No change.

## 3. What's actually new in round 2

Exactly three artefacts:

1. **`PA-LLM-08` heuristic** on `PythonAuditAgent` — one new `@heuristic` method `check_n_plus_one_in_user_code`, one helper `_detect_n_plus_one(tree, path)`, plus two new module-level constants. ~80 lines.
2. **Frontmatter update** on `docs/counter-priors/n-plus-one-in-user-code.md` — add the `detectors:` block.
3. **Unit tests** — new `tests/unit/test_python_audit_n_plus_one.py`. ~150 lines.

CHANGELOG entry and version bump per ship discipline. No new modules, no new packages, no CLI surface, no scaffolding changes.

## 4. Detector shape

**Mode:** Standard — canonical shapes from the catalogue plus common variants. Conservative on method names (curated denylist), permissive on attribute-chain depth.

**Scope:** `<project>/app/` only. Framework code (`src/dazzle/`) and tests/scripts have their own discipline.

**Severity:** MEDIUM (matches PA-LLM-07). Confidence LIKELY — pre-fetched relations and non-DB methods that share queryset method names look identical at AST level, so false positives are plausible and the human reader is the disambiguator.

### Detection logic

For each `ast.For` node in a scanned file:

1. Identify the loop target name(s). Handle the common cases: single `Name` target (`for x in xs:`), tuple unpacking (`for x, y in items.items():`). For tuple unpacking, treat both names as loop variables.
2. Walk the loop body. For each `ast.Call` node, decide whether it matches one of the three wrong shapes:

   **Shape 1: queryset-method chain rooted at loop variable.**
   `<loopvar>.<attr>...<attr>.<method>(...)` where `<method>` is in `_QUERYSET_METHODS`. The attribute chain may be one or more levels deep (`order.lines.all()`, `order.customer.contacts.first()`). Detection: walk the `func` AST until we hit either an `ast.Name` (check if its `id` is a loop variable) or a non-Attribute/non-Name (stop, no match).

   **Shape 2: `<x>_repo.<method>(...)` inside a loop, where any argument references a loop variable.**
   `<name>_repo` is the canonical Dazzle Repository naming pattern. Detection: `func` is `ast.Attribute`, `func.value` is `ast.Name` matching `*_repo`, `func.attr` is in `_REPO_METHODS`, and at least one of the call's args (or arg subexpressions) is an `ast.Name` with id in the loop variables.

   **Shape 3: `len(<loopvar>.<attr>.all())` (or `.list()` etc.).**
   The outer call is `len(...)` (or `sum`, `list`, `set`, `any`, `all` as comprehension/iterable consumers — start narrow with `len`, expand if backfill shows we miss). Inner expression matches Shape 1. Detection: if outer call's `func` is `ast.Name` with id in `_LEN_LIKE_BUILTINS`, recurse into the first arg looking for a Shape-1 match.

3. For each match: emit a `Finding` with severity MEDIUM, confidence LIKELY, `catalogue_entry="n-plus-one-in-user-code"`, `remediation.references` containing the catalogue URL.

### Constants

```python
_QUERYSET_METHODS = frozenset({
    "all",       # Django queryset terminator
    "list",      # generic list materialiser
    "first",     # first-row fetch
    "last",      # last-row fetch
    "filter",    # queryset narrowing (chains into terminator inside loop = still N+1)
    "order_by",  # ordered fetch
    "count",     # SQL count
    "exists",    # SQL EXISTS
})
# Deliberately excluded: `get` — too generic, collides with dict.get(). Covered via _REPO_METHODS below.

_REPO_METHODS = frozenset({
    "list",          # Repository.list(scope=...)
    "fetch",         # Repository.fetch(id) / fetch(scope=...)
    "fetch_by_id",   # explicit by-id variant
    "get",           # Repository.get(id) — safe to include here because the qualifier `<x>_repo.` is unambiguous
    "find",          # find_one / find variants
})

_LEN_LIKE_BUILTINS = frozenset({"len"})
# Conservative start. Backfill audit may add: sum, list, set, sorted, max, min, any, all.
```

### Suppression

`# noqa: PA-LLM-08` on the `for` statement line OR the offending call line. Same idiom as PA-LLM-07. Reason text is encouraged but not enforced (matches the noqa-reason guidance softened in PA-LLM-07's CHANGELOG).

Canonical suppression case: pre-fetched relations using framework idioms the detector can't see at AST level. Author adds `# noqa: PA-LLM-08 — prefetched via Repository.aggregate above`.

### Deliberate non-goals

- **Pre-fetch auto-detection.** Detecting `for x in qs.select_related("lines"): ...` AND propagating "lines is pre-fetched" through the loop body is a small static-analysis project on its own. Dazzle's Repository doesn't use Django's `select_related` naming, so the obvious signal isn't there anyway. Manual `# noqa` is honest and cheap.
- **Comprehension support.** `[render(x.lines.all()) for x in xs]` is morally identical N+1 but the AST node is `ast.ListComp`/`ast.GeneratorExp`/`ast.DictComp`, not `ast.For`. Defer to a follow-up after backfill confirms PA-LLM-08 on `For` is well-tuned. Filed implicitly as a round-2.5 follow-up.
- **Async-iterator loops.** `async for x in qs: ...` follows the same shape but is rare in current Dazzle apps. Add support only if backfill surfaces real instances.

## 5. Testing surface

`tests/unit/test_python_audit_n_plus_one.py`. Following the round-1 pattern:

**Positive cases (one per sub-shape):**
- `test_queryset_chain_all` — `for order in orders: x = order.lines.all()`
- `test_queryset_chain_first` — `for order in orders: x = order.payments.order_by("at").first()`
- `test_queryset_chain_filter_terminator` — `for order in orders: x = order.lines.filter(state="paid").all()`
- `test_repo_call_with_loopvar_arg` — `for oid in order_ids: x = order_repo.fetch(oid)`
- `test_repo_call_with_loopvar_attr_arg` — `for order in orders: x = line_repo.list(order_id=order.id)`
- `test_len_wrapped_queryset` — `for order in orders: c = len(order.lines.all())`

**Negative cases (false-positive guards):**
- `test_negative_attribute_access_no_call` — `for order in orders: x = order.id` (no method call)
- `test_negative_method_outside_queryset_set` — `for s in strings: x = s.upper()` (`.upper()` not in `_QUERYSET_METHODS`)
- `test_negative_call_no_loopvar_reference` — `for i in range(10): x = order_repo.fetch(static_id)` (repo call doesn't reference loop var)
- `test_negative_repo_call_outside_loop` — `result = repo.list(...)` at module/function scope
- `test_negative_noqa_suppression_for_line` — `for x in xs:  # noqa: PA-LLM-08 — prefetched\n    y = x.lines.all()`
- `test_negative_noqa_suppression_call_line` — `for x in xs:\n    y = x.lines.all()  # noqa: PA-LLM-08`

**Integration:**
- `test_heuristic_yields_finding_with_catalogue_entry` — end-to-end, same pattern as PA-LLM-07's equivalent. Asserts `heuristic_id == "PA-LLM-08"`, `catalogue_entry == "n-plus-one-in-user-code"`, `remediation.references` contains the catalogue URL.
- `test_heuristic_skips_tests_and_scripts` — only `app/` is scanned.

Total: ~13 tests. No drift-test changes — the existing bidirectional drift test (round 1) automatically picks up the new heuristic via the frontmatter declaration.

## 6. Frontmatter wiring

Add to `docs/counter-priors/n-plus-one-in-user-code.md` immediately after the existing `refs:` block, before the closing `---`:

```yaml
detectors:
  - id: PA-LLM-08
    agent: PA
    note: covers queryset chains on loop-variable attribute access, *_repo calls with loop-variable args, and len() wrapping. Does not detect prefetched-relation suppression at AST level — author adds `# noqa: PA-LLM-08 — prefetched` when the relation is materialised in advance.
```

Bump `SEED_SCHEMA_VERSION` in `src/dazzle/mcp/knowledge_graph/seed.py` by 1 so the KG re-ingests.

## 7. CHANGELOG + version

Bump `0.75.0 → 0.76.0` (minor, feature addition). CHANGELOG section under a new `## [0.76.0] - YYYY-MM-DD`:

```markdown
### Added — agent code quality substrate round 2 (PA-LLM-08 pilot)

- **Sentinel heuristic `PA-LLM-08`** (`n_plus_one_in_user_code`) detects three canonical shapes of N+1 query patterns in user `app/` Python: queryset chains on loop-variable attribute access (`order.lines.all()` inside a for-loop), `*_repo.<method>(...)` calls with loop-variable args, and `len()` wrapping a queryset chain. Severity MEDIUM, confidence LIKELY (false-positive risk from prefetched relations and identically-named non-DB methods). Suppress via `# noqa: PA-LLM-08 — <reason>` on the `for` or call line.
- **Counter-prior `n-plus-one-in-user-code.md` frontmatter** declares `PA-LLM-08`. Existing bidirectional drift test (#1255) automatically enforces the contract.

### Agent Guidance

- When writing loops in `app/` that touch related rows, reach for `Repository.aggregate(group_by=..., count="...")` or batched fetch helpers. Don't enumerate. See `docs/counter-priors/n-plus-one-in-user-code.md` for the right shapes.
- Prefetched relations are legitimate: when the relation is materialised upstream of the loop, document the suppression with `# noqa: PA-LLM-08 — prefetched via <upstream-call>`.
- PA-LLM-08 doesn't detect comprehension N+1 yet (`[x.lines.all() for x in xs]`). Treat that shape with the same discipline manually until a follow-up extends the detector.
```

CI gate already in place from round 1; PA-LLM-08 inherits the same threshold (`--severity high` informational until backfill audit on #1256 promotes).

## 8. Implementation order

Four steps. Each ends in a commit. Estimated total: 1 day of focused work.

1. **Frontmatter wiring** — extend `n-plus-one-in-user-code.md`, bump `SEED_SCHEMA_VERSION`. Run drift test to confirm it fails (heuristic not implemented yet). This step deliberately leaves the drift test red until step 2.
2. **Heuristic implementation** — add `_QUERYSET_METHODS`, `_REPO_METHODS`, `_LEN_LIKE_BUILTINS` constants; add `_detect_n_plus_one` helper; add `check_n_plus_one_in_user_code` `@heuristic` method on `PythonAuditAgent`. Run unit tests (which don't exist yet — TDD means writing them first; this step is "implementation + tests together" per the round-1 pattern).
3. **Unit tests** — `tests/unit/test_python_audit_n_plus_one.py`. ~13 tests covering the cases in §5. (TDD-wise this is step 2 in disguise — tests first, watch fail, implement, watch pass; the order is interleaved.)
4. **CHANGELOG + version bump + smoke test** — confirm `dazzle sentinel scan --agent PA --severity medium examples/` returns zero PA-LLM-08 findings across all 13 example apps before committing CI inclusion (the CI step already exists; we just verify it stays green).

Wider gates (pytest -m "not e2e", ruff, mypy, mkdocs --strict, drift gates) run as part of the pre-ship pipeline.

## 9. Risks + open questions

1. **False positives from non-DB methods sharing names.** `obj.list()` could mean "return the items" on a non-DB object. The `_QUERYSET_METHODS` set is curated to favour DB-bound names (`all`, `first`, `exists`) but `list` and `filter` are plausibly general. **Mitigation:** start with the full set, run against all example apps + framework code (out-of-scope but exercise as smoke), watch what fires. If `app/` codebases produce false positives, narrow the set or split into "high confidence" (`all`, `first`, `exists`) vs "medium confidence" (`list`, `filter`).
2. **Repo-naming brittleness.** `_REPO_METHODS` only fires when the attribute is `<something>_repo`. If a project uses a different naming convention (`<X>Repository`, `<X>DAO`, plain `<x>s` collection name) we miss it. **Mitigation:** the convention is documented in `docs/reference/project-layout.md` as the recommended shape. We accept the brittleness in v1; backfill audit may surface project conventions that need broader matching.
3. **Comprehension gap is real.** Not a risk of this slice but worth flagging in the CHANGELOG so agents reading the guidance know the comprehension case exists.

## 10. Success criteria

The slice ships successfully if:

- Frontmatter declares `PA-LLM-08`; bidirectional drift test passes.
- 13 unit tests pass; wider sentinel + python_audit suite stays green.
- `dazzle sentinel scan --agent PA --severity medium examples/` returns zero findings across all 13 example apps (i.e. our own example code doesn't trigger the new heuristic).
- CHANGELOG entry under `[0.76.0]` documents the new heuristic + agent guidance.
- Total diff < 250 LOC including tests. **If the diff exceeds 400 LOC, the design has missed something — stop and re-scope.**

The slice succeeds if it demonstrably costs less than round 1 — that is the substrate's value claim.
