Cross-app integration fuzz sweep — find bugs that `dazzle validate` doesn't catch, file them as GitHub issues, hand off to `/issues` to drain.

**This command uses parallel subagents** — one per app — to scrape boot stderr / lint output for known-bug signatures across every example + fixture.

## Why this exists

Lint and validate catch DSL-shape errors. They miss runtime regressions that only surface when the runtime actually boots — duplicate route registrations, FTS-shape mismatches, undefined refs, template undefined-var errors. The first run of this skill (2026-05-04) caught three real bugs that had been silently shipping for cycles:

| Caught | Fix |
|---|---|
| `GET /` registered twice on every boot (3 apps) | v0.64.5 — dedupe page-router registration |
| `not a text-shaped column` rejected every search field (2 apps) | v0.64.6 — backend FieldType shape mismatch in FTS |
| Unresolved `source=<pack>.<op>` ref (false positive, but the gap was real) | v0.64.7 — validator gate |

The fuzz pattern that surfaced them: scrape **boot stderr** for known-bug signatures, not just `dazzle validate` exit code.

## Loop: Fuzz → File → Hand off → Repeat

### Step 1: Discover apps

```bash
ls -d examples/*/ fixtures/*/ 2>/dev/null
```

Skip `examples/README.md` (not an app). Note: each app has `dsl/app.dsl` (or similar) and is bootable via `dazzle serve --local` from its own directory.

### Step 2: Dispatch parallel fuzz agents

For every discovered app, dispatch one `Explore` subagent with `run_in_background: true` and `model: "sonnet"`. **All in a single message.**

Each subagent prompt (substitute `<APP_PATH>` and `<APP_NAME>`):

```
Fuzz the Dazzle app at <APP_PATH>. Find INTEGRATION BUGS — things `dazzle validate` doesn't catch.

Run these checks. Use Bash. Report ONLY problems.

1. `cd <APP_PATH> && dazzle validate 2>&1 | tail -5` — must pass.
2. `cd <APP_PATH> && dazzle lint 2>&1 | grep -iE "ERROR|FAILED" | head -10` — flag errors only, ignore soft suggestions ("missing display_field", "no fitness.repr_fields", "no command palette" etc.).
3. **Boot-stderr scrape** (the high-yield check):
   `cd <APP_PATH> && timeout 8 dazzle serve --local 2>&1 | grep -iE "registered twice|duplicate|not a text-shaped|TypeError|Traceback|ImportError|ValueError|AttributeError|jinja2\\.exceptions|unresolved|UndefinedError" | head -15`
   Each line that matches IS a bug.
4. Search the DSL for uses of recently-shipped primitives (rich_text, x-optimistic, x-pull-to-refresh, x-swipe, x-flip, notification, search on, i18n.) and flag any USAGE (not just absence) that looks broken.

Report format (terse, under 200 words):

```
APP: <APP_NAME>
STATUS: OK | <N> issues
BUGS:
- <severity: HIGH|MEDIUM|LOW> — <one-line description with file:line if known>
- ...
SOFT (informational, not for issue-filing):
- <list of lint suggestions>
```

If clean, just `STATUS: OK` and stop.
```

### Step 3: Aggregate findings

Wait for all agents to complete. From the reports, build a deduped table:

| Bug signature | Apps affected | Severity | Already filed? |
|---|---|---|---|

For each unique bug:
- Run `gh issue list --state open --search "in:title <signature>"` to check it isn't already filed.
- Run `gh issue list --state closed --limit 30 --search "<signature>"` to check it wasn't recently fixed (avoid filing duplicates of just-shipped fixes).

### Step 4: File new issues

For each unfiled HIGH or MEDIUM bug, **write the body to a file first**, then pass it via `--body-file`. Inline heredocs mangle markdown — single-quoted ones preserve backslashes (so `\`backticks\`` show literally), double-quoted ones interpret them. Caught the hard way on #1000 (had to be re-edited).

```bash
cat > /tmp/fuzz-issue-body.md <<'EOF'
Fuzz sweep (vX.Y.Z) found <symptom> in <apps affected>:

<verbatim error output as a fenced code block — bare backticks, no escapes>

**Repro:**
```bash
cd <affected app>
timeout 8 dazzle serve --local 2>&1 | grep <signature>
```

**Likely root cause:** <best hypothesis>

**Suggested fix path:** <one option>
EOF

gh issue create --title "<terse signature>" --label "needs-triage" --body-file /tmp/fuzz-issue-body.md
```

LOW bugs (single-app cosmetic warnings) — list them in the summary but don't auto-file. The user can promote them if they want.

False positives — explicitly flag and don't file. The fuzz agent may overreach (e.g. assert "no api_pack declared" without checking `dazzle.api_kb`). Skip if a quick verification disproves the claim.

### Step 5: Print fuzz summary

```
## Fuzz Sweep — <date>

### Apps scanned: <N>
### Bugs found: <N> (filed: <M>, soft: <K>)

| App | Status | Bugs |
|-----|--------|------|
| ... | ... | ... |

### Filed issues
- #<num>: <title>
- ...

### Soft findings (not filed)
- <app>: <description>
```

### Step 6: Hand off to /issues

If any issues were filed:

> Filed N issue(s). Run `/loop /issues` to drain them, or `/issues` for one pass.

Then **stop**. The user (or the next `/issues` cycle) takes it from here.

If no new issues were filed: report clean and stop.

## Soft-finding allowlist

These warnings are informational and should NEVER be filed as issues by this command:

- `entity 'X' has permissions but no surfaces` — intentional in shape-coverage fixtures
- `no fitness.repr_fields` — fitness-evaluation hint, not a bug
- `no command palette fragment` — capability suggestion
- `no timeline workspace region` — capability suggestion
- `5 fields in a single section` — multi-section form hint
- `permit but no scope` warnings on `pra` and `shapes_validation` fixtures — intentional shape coverage
- Sentinel `BL-XX` warnings — they're business-logic linker hints, not runtime bugs

If a fuzz agent reports any of the above as a "bug", silently demote to "soft" and don't file.

## Interactive (runtime) fuzz — complement to the static sweep above

The static sweep above is fast and good at the boot-stderr signature class. It cannot exercise JavaScript components — race conditions in dz-richtext, htmx swap timing, paste edge cases, contenteditable selection bugs.

For that, use the headless-Playwright runner at `src/dazzle/testing/fuzz_runtime/runner.py`. Per app it:

1. Boots the app with `--test-mode` (auto-publishes a test secret in `.dazzle/runtime.json`).
2. Authenticates as admin via `/__test__/authenticate`.
3. Drives each supported widget through a battery of known-tricky interactions (selection, paste from corpus, undo/redo, lifecycle remount).
4. Reports console errors, page errors, schema/structure assertions.

Coverage matrix today:

| Widget | Battery |
|---|---|
| dz-richtext | type → hidden sync, Ctrl+B (incl. block-vs-inline nesting check #1000), paste javascript:/`<script>`/h1/h4/Word styles, htmx-style remount lifecycle |
| (more to come — combobox, picker, optimistic-UI form mid-mutation) | |

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

**When to run interactive fuzz:**

- After shipping a JS-touching primitive (any new `widget=`, Alpine directive, htmx-bridge change).
- After a refactor of `dz-richtext.js`, `dz-alpine.js`, or `dz-widget-registry.js`.
- When something feels off but the static sweep is clean.

**Pattern the spike taught us** (see #1000): static tests prove the SHAPE of the JS is right (no `execCommand`, has `aria-pressed`, registers under `richtext`). They prove zero about its BEHAVIOUR. Real edge cases — like `<strong>` wrapping a block element when the selection spans a whole `<p>` — only surface in a real browser doing real interactions.

## When to run (static sweep)

- After shipping a non-trivial framework primitive (a new `widget=`, fragment, channel, scope-pattern, etc.) — verify it doesn't break existing apps.
- Before a 0.X → 0.(X+1) minor bump — sanity-check the upcoming release.
- On a recurring loop: `/loop 4h /fuzz` (or longer; 4h is once-an-overnight cadence).
- Manually when something feels off and `validate` says clean.
