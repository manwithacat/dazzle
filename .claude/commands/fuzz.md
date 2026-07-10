Cross-app integration fuzz sweep — find bugs that `dazzle validate` doesn't catch, file them as GitHub issues, hand off to `/issues` to drain.

**The static sweep runs as a Workflow** (`.claude/workflows/fuzz.js`) — one agent per example/fixture scrapes boot stderr + lint for known-bug signatures, in parallel, returning schema-validated findings. This main loop scouts the app list, passes it in, then keeps the **side effects** (gh dedup + issue filing) under its own control.

## Why this exists

Lint and validate catch DSL-shape errors. They miss runtime regressions that only surface when the runtime actually boots — duplicate route registrations, FTS-shape mismatches, undefined refs, template undefined-var errors. The first run of this skill (2026-05-04) caught three real bugs that had been silently shipping for cycles:

| Caught | Fix |
|---|---|
| `GET /` registered twice on every boot (3 apps) | v0.64.5 — dedupe page-router registration |
| `not a text-shaped column` rejected every search field (2 apps) | v0.64.6 — backend FieldType shape mismatch in FTS |
| Unresolved `source=<pack>.<op>` ref (false positive, but the gap was real) | v0.64.7 — validator gate |

The fuzz pattern that surfaced them: scrape **boot stderr** for known-bug signatures, not just `dazzle validate` exit code.

## Loop: Fuzz → File → Hand off → Repeat

### Step 1: Scout apps (main loop)

```bash
ls -d examples/*/ fixtures/*/ 2>/dev/null
```

Skip `examples/README.md` (not an app). Each app has `dsl/app.dsl` (or similar) and boots via `dazzle serve` from its own dir.

### Step 2: Run the sweep workflow

Invoke the **Workflow** tool with `name: "fuzz"` and `args:` set to the JSON array of app paths from step 1 (actual array, not a stringified one). Each agent is an `Explore` subagent inheriting the session model (signature-scrape + false-positive judgment — model-tiering, AGENTS.md Capability Mapping), and applies the soft-finding allowlist below before reporting.

It returns `{apps: [{app, status, bugs:[{severity, signature, detail, evidence}], soft:[...]}]}`.

### Step 3: Aggregate + dedup against GitHub (main loop)

From the returned `apps`, build a deduped table keyed by bug `signature`:

| Bug signature | Apps affected | Severity | Already filed? |
|---|---|---|---|

For each unique bug:
- `gh issue list --state open --search "in:title <signature>"` — skip if already open.
- `gh issue list --state closed --limit 30 --search "<signature>"` — skip if recently fixed (avoid dup of a just-shipped fix).

### Step 4: File new issues (main loop)

For each unfiled HIGH or MEDIUM bug, **write the body to a file first**, then pass it via `--body-file`. Inline heredocs mangle markdown — single-quoted ones preserve backslashes, double-quoted ones interpret them. (Caught the hard way on #1000.)

```bash
cat > /tmp/fuzz-issue-body.md <<'EOF'
Fuzz sweep (vX.Y.Z) found <symptom> in <apps affected>:

<verbatim evidence as a fenced code block>

**Repro:**
```bash
cd <affected app>
timeout 8 dazzle serve 2>&1 | grep <signature>
```

**Likely root cause:** <best hypothesis>

**Suggested fix path:** <one option>
EOF

gh issue create --title "<terse signature>" --label "needs-triage" --body-file /tmp/fuzz-issue-body.md
```

LOW bugs (single-app cosmetic) — list in the summary, don't auto-file. The workflow already demotes soft-allowlist items; if any slip through into `bugs`, demote them here.

### Step 5: Print fuzz summary

```
## Fuzz Sweep — <date>
### Apps scanned: <N>
### Bugs found: <N> (filed: <M>, soft: <K>)

| App | Status | Bugs |
|-----|--------|------|

### Filed issues
- #<num>: <title>

### Soft findings (not filed)
- <app>: <description>
```

### Step 6: Hand off to /issues

If any issues were filed:

> Filed N issue(s). Run `/loop /issues` to drain them, or `/issues` for one pass.

Then **stop**. If no new issues were filed: report clean and stop.

## Soft-finding allowlist

These warnings are informational and must NEVER be filed (the workflow finder prompt encodes the same list, but enforce it again on aggregation):

- `entity 'X' has permissions but no surfaces` — intentional in shape-coverage fixtures
- `no fitness.repr_fields` — fitness-evaluation hint, not a bug
- `no command palette fragment` / `no timeline workspace region` — capability suggestions
- `5 fields in a single section` — multi-section form hint
- `permit but no scope` on `pra` / `shapes_validation` fixtures — intentional shape coverage
- Sentinel `BL-XX` warnings — business-logic linker hints, not runtime bugs

## Interactive (runtime) fuzz — complement to the static sweep above

The static sweep is fast and good at the boot-stderr signature class. It cannot exercise JavaScript components — race conditions in dz-richtext, htmx swap timing, paste edge cases, contenteditable selection bugs.

For that, use the headless-Playwright runner at `src/dazzle/testing/fuzz_runtime/runner.py`. Per app it:

1. Boots the app with `--test-mode` (auto-publishes a test secret in `.dazzle/runtime.json`).
2. Authenticates as admin via `/__test__/authenticate`.
3. Drives each supported widget through a battery of known-tricky interactions (selection, paste from corpus, undo/redo, lifecycle remount).
4. Reports console errors, page errors, schema/structure assertions.

**Run it directly:**

```bash
python3 -c "
from pathlib import Path
from dazzle.testing.fuzz_runtime import run_app_fuzz
report = run_app_fuzz(Path('/Volumes/SSD/Dazzle/fixtures/component_showcase'))
print(f'{report.project}: {report.passed}/{report.total}')
for c in report.failures:
    print(f'  FAIL  {c.name} — {c.detail[:120]}')
"
```

**When to run interactive fuzz:** after shipping a JS-touching primitive (any new `widget=`, Alpine directive, htmx-bridge change); after a refactor of `dz-richtext.js`, `dz-alpine.js`, or `dz-widget-registry.js`; when something feels off but the static sweep is clean.

**Pattern the spike taught us** (see #1000): static tests prove the SHAPE of the JS is right (no `execCommand`, has `aria-pressed`, registers under `richtext`). They prove zero about its BEHAVIOUR. Real edge cases — like `<strong>` wrapping a block element when the selection spans a whole `<p>` — only surface in a real browser doing real interactions.

## When to run (static sweep)

- After shipping a non-trivial framework primitive (a new `widget=`, fragment, channel, scope-pattern) — verify it doesn't break existing apps.
- Before a 0.X → 0.(X+1) minor bump — sanity-check the upcoming release.
- On a recurring loop: `/loop 4h /fuzz` (once-an-overnight cadence).
- Manually when something feels off and `validate` says clean.
