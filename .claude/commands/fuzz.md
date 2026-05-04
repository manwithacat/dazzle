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

For each unfiled HIGH or MEDIUM bug:

```bash
gh issue create --title "<terse signature>" --label "needs-triage" --body "$(cat <<'EOF'
Fuzz sweep (vX.Y.Z) found <symptom> in <apps affected>:

<verbatim error output, indented as a code block>

**Repro:**
\`\`\`bash
cd <one of the affected apps>
timeout 8 dazzle serve --local 2>&1 | grep <signature>
\`\`\`

**Likely root cause:** <best hypothesis from the symptom>

**Suggested fix path:** <one option>
EOF
)"
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

## When to run

- After shipping a non-trivial framework primitive (a new `widget=`, fragment, channel, scope-pattern, etc.) — verify it doesn't break existing apps.
- Before a 0.X → 0.(X+1) minor bump — sanity-check the upcoming release.
- On a recurring loop: `/loop 4h /fuzz` (or longer; 4h is once-an-overnight cadence).
- Manually when something feels off and `validate` says clean.
