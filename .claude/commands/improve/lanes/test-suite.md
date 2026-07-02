# Lane: test-suite

Collapses test-suite redundancy clusters (#1530) — one cluster family per cycle.
The suite accretes parametrisable repetition (1,030 same-file clusters ≈ 22% of the
suite at the 2026-07-02 audit); this lane is the retrospective half of the
distillation feedback loop (the authoring-side half lives in CLAUDE.md
"Test Authoring — Distillation Feedback Loop").

**This is NOT a runtime play.** At ~7 ms/test the CPU cost is trivial. The payoff
is maintenance surface: attention-per-failure (one parametrised failure vs N
identical red lines), agent-context weight when extending a file, and stopping
the copy-paste growth curve.

## Targets

`tests/` redundancy clusters, driven by the committed audit artifacts:

- `tests/audit/redundancy_report.md` — same-file clusters (mechanical parametrize collapse)
- `tests/audit/cross_file_report.md` — cross-file clusters (need shared parametrised helpers or a corpus fixture, NOT mechanical merging — design-first rows)

**Not** test *coverage* gaps (that's the framework's own QA harnesses) and **not**
`tests/e2e` (leave e2e flows verbose and literal).

## State

- **Backlog section:** `## Lane: test-suite` in `dev_docs/improve-backlog.md`
- Row shape: `| id | target file | clusters | est_tests | status | attempts | last_cycle | notes |`

## Signals

| Direction | Kind | Notes |
|-----------|------|-------|
| Emit | — | none; collapses are internal maintenance, no cross-lane consumer |
| Consume | `fix-deployed` | a shipped fix may have touched a target file — re-check the row's cluster still exists before collapsing |

## actionable_count

Rows in `## Lane: test-suite` with status ∈ {`REGRESSION`, `PENDING`, `IN_PROGRESS`}.

## Playbook

### 1. PICK

Highest-`est_tests` row with status `PENDING` (or any `REGRESSION`/`IN_PROGRESS`
first). Mark `IN_PROGRESS`, increment `attempts`; `attempts > 3` → `BLOCKED`,
pick next. **One cluster family per cycle** — a family is all clusters in one
file (e.g. `test_region_adapter.py`'s four clusters are one row, one cycle).

### 2. JUDGE

Read the target file and the report's cluster membership. For each cluster decide:

- **collapse** — the cases genuinely share ONE behaviour contract and differ only
  in inputs/expected values → `@pytest.mark.parametrize` with readable `ids=`.
- **keep_all** — independent names document distinct contracts (a legitimate
  verdict; record it in the row's notes so the next audit doesn't re-file it).

Guardrails:
- Never merge tests carrying different marks (`gate`, `xdist_group`, `asyncio`,
  skips) unless the mark set is identical across the cluster.
- Preserve any `xdist_group` pins verbatim (subprocess-cohort tests).
- Don't chase cleverness: a parametrize table an agent can extend beats a
  fixture-generating metafunction nobody can read.
- Cross-file rows: design a shared helper/corpus fixture first, apply to 2-3
  files max per cycle, note the pattern for follow-up rows.

### 3. COLLAPSE

Apply the parametrize collapse. Assertion bodies must stay semantically identical —
this is a refactor, not a rewrite. If a case needs a different assertion, it is
not part of the cluster; leave it standalone.

### 4. VERIFY

```bash
pytest <target file> -q                                   # collapsed file green
pytest tests/ -n auto --dist loadgroup -m "not e2e" -q    # full suite green (~2 min)
```

Count discipline: record before/after collected-test counts for the file in the
row notes. **Success criterion (#1530): count goes down without reducing mutation
kill rate** — the nightly `dazzle sentinel mutate` floors are the backstop; if the
next nightly drops below floor on a module this lane touched, the row goes
`REGRESSION` and the collapse is revisited (the parametrised version lost a
distinguishing assertion).

### 5. REPORT

1. Update the row: `DONE` (with before/after counts + keep_all verdicts) or
   `BLOCKED` (why).
2. After a large collapse (>50 tests removed), regenerate the distillation
   artifacts so the report stops naming dead clusters:
   `python scripts/distill/classify.py && python scripts/distill/cluster.py && python scripts/distill/cross_file.py`
   (the 19 MB `classification.json` stays gitignored; commit the summary artifacts).
3. Return `{status: PASS|FAIL|BLOCKED, summary, signals_to_emit: [], budget_consumed: 0}`.

### 6. EXPLORE (no actionable rows)

**Parking check first:** if the `## Lane: test-suite` section header in the
backlog carries a `PARKED` marker, do NOT re-seed — return
`{status: HOUSEKEEPING, summary: "lane parked (<marker reason>)", signals_to_emit: [], budget_consumed: 0}`.
The marker states its own unpark condition; only an operator (or a signal
matching that condition) removes it.

Otherwise: regenerate the distillation artifacts (command above), then re-seed the section:
one row per top-10 same-file cluster family not already present (and not
previously verdicted keep_all), plus one design-first row per new top-3
cross-file cluster. `budget_consumed: 1`.

## Hard rules

- **One cluster family per cycle.** Don't chain files.
- **Full suite before ship** — a collapse that breaks an unrelated test is a FAIL,
  not a note. (IR-field lesson: `-k`-filtered runs give false confidence — run full.)
- **keep_all is a real outcome.** Forced collapses that erase documentation value
  are scope creep, not progress.
