# Phase 0 — Reclassify pra / component_showcase / custom_renderer → fixtures/ (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move three framework-artifact apps out of `examples/` into `fixtures/` so that "an example is a kayfabe business that carries per-persona guides" becomes an exception-free rule — without breaking any build gate.

**Architecture:** Pure relocation + reference hygiene. Move 3 tracked directories with `git mv`, then update only the **live** references (framework docstrings/error-messages, asserting tests, list-membership gates, one MCP registry entry, CLAUDE.md's two drift-gated lists, one benchmark script, a few CI/command comments). Frozen history (CHANGELOG, `docs/history/`, `docs/plans/`, dated `docs/superpowers/specs/`, agent-upgrade guides) is left untouched. CI/test globs that scan `examples/*/ fixtures/*/` auto-adjust. Ships as **one coherent commit** (ADR-0003 clean break) — intermediate states are intentionally red, so **do not commit until the final task.**

**Tech Stack:** Python 3.12+, `uv` toolchain, pytest, ruff/mypy, BSD sed (macOS).

**Scope guard — what does NOT move:** `src/dazzle/http/pra/` is a framework performance-harness module and **stays put**; only the `examples/pra/` *project corpus* moves. `tests/unit/test_pra_cli.py`, `test_pra_harness.py`, `test_pra_load_generator.py` test that framework module — **do not touch them.**

---

## File map

**Directories moved (git mv):**
- `examples/pra/` → `fixtures/pra/` (18 tracked files)
- `examples/custom_renderer/` → `fixtures/custom_renderer/` (7 tracked files)
- `examples/component_showcase/` → `fixtures/component_showcase/` (3 tracked files)

**Live files edited:**
- `.claude/CLAUDE.md` — move 3 names from the examples list (L225) to the fixtures list (L227)
- `src/dazzle/mcp/examples.py` — delete the `"pra"` registry block (L127–165)
- `scripts/bench_interp.py` — `examples/pra` → `fixtures/pra` (live code, L29)
- Framework docstrings/error-messages referencing `examples/custom_renderer` (manifest, linker, renderer_registry, services, renderers `__init__`, render/dispatch)
- Asserting tests: `tests/unit/test_runtime_services_doc.py`, `tests/unit/test_dispatch_ctx_detail_view.py`, `tests/unit/core/test_render_clause_linking.py`
- List-membership gates: `tests/unit/test_cli_sweep.py`, `tests/unit/test_examples_rbac_lint_clean.py`, `tests/unit/test_example_index.py`
- Comments: `.github/workflows/ci.yml`, `tests/unit/test_dazzle_validate_drift.py`, `src/dazzle/core/validation/flows.py`
- `docs/reference/htmx-templates.md` — text + GitHub link
- `.claude/commands/fuzz.md` — one example path (L123)

**Frozen — DO NOT EDIT:** `CHANGELOG.md`, `docs/history/**`, `docs/plans/**`, `docs/superpowers/specs/**` (dated), `docs/guides/agent-upgrade-guide-*.md`, `.claude/worktrees/**`.

---

### Task 1: Pre-flight — capture baseline & rule out boot-time coupling

**Files:** none (read-only)

- [ ] **Step 1: Confirm the three apps have no tracked local state and are clean to move**

Run:
```bash
cd /Volumes/SSD/Dazzle
git ls-files examples/pra examples/custom_renderer examples/component_showcase | wc -l
git status --short    # must be clean before starting
```
Expected: a non-zero file count (~28), and a clean status (no uncommitted changes).

- [ ] **Step 2: Prove no test BOOTS these apps by path (only doc/string refs, which we handle)**

Run:
```bash
grep -rnE "examples/(pra|custom_renderer|component_showcase)" tests/ --include=*.py \
  | grep -vE "assert .* in (doc|msg|stdout)|#|\"\"\"" || echo "NO_RUNTIME_LOAD"
```
Expected: every hit is a string assertion or comment (handled in later tasks), OR `NO_RUNTIME_LOAD`. If a test constructs one of these paths and loads it as a project (e.g. `build_appspec`, `DazzleServer`, `serve`), STOP and add a redirect task — but per the migration map none exist.

- [ ] **Step 3: Record the green baseline** (so a later failure is attributable to this change)

Run:
```bash
uv run pytest tests/unit/test_docs_drift.py tests/unit/test_cli_sweep.py \
  tests/unit/test_examples_rbac_lint_clean.py tests/unit/test_example_index.py \
  tests/unit/test_runtime_services_doc.py tests/unit/test_dispatch_ctx_detail_view.py \
  tests/unit/core/test_render_clause_linking.py tests/unit/test_dazzle_validate_drift.py -q
```
Expected: all PASS (this is the set most affected by the move).

*(No commit — read-only task.)*

---

### Task 2: Move the three directories

**Files:** `examples/{pra,custom_renderer,component_showcase}/` → `fixtures/`

- [ ] **Step 1: git mv each directory**

Run:
```bash
cd /Volumes/SSD/Dazzle
git mv examples/pra fixtures/pra
git mv examples/custom_renderer fixtures/custom_renderer
git mv examples/component_showcase fixtures/component_showcase
```

- [ ] **Step 2: Verify the moves registered as renames and the trees are right**

Run:
```bash
git status --short | grep -E "^R" | grep -E "pra|custom_renderer|component_showcase" | head
ls -d fixtures/pra fixtures/custom_renderer fixtures/component_showcase
test ! -d examples/pra && test ! -d examples/custom_renderer && test ! -d examples/component_showcase && echo "GONE_FROM_EXAMPLES"
```
Expected: rename (`R`) entries listed, the three `fixtures/` dirs exist, and `GONE_FROM_EXAMPLES`.

- [ ] **Step 3: Confirm each moved app still validates at its new path**

Run:
```bash
for app in pra custom_renderer component_showcase; do
  echo "=== $app ==="; (cd fixtures/$app && dazzle validate 2>&1 | tail -2)
done
```
Expected: `custom_renderer` and `component_showcase` validate clean. **`pra` is the parser-conformance corpus and is EXPECTED to report validation-failing shapes** — that's its purpose; a non-zero/diagnostic output for `pra` is correct, not a regression.

*(No commit yet — the drift test is now red until Task 3.)*

---

### Task 3: Update CLAUDE.md's two drift-gated lists

**Files:** Modify `.claude/CLAUDE.md:225` (examples list) and `.claude/CLAUDE.md:227` (fixtures list)

The drift test (`tests/unit/test_docs_drift.py::test_claude_md_examples_and_fixtures_lists_match_disk`) reads the directory trees directly, so the lists must now exactly match disk.

- [ ] **Step 1: Remove the 3 names from the examples list (L225)**

Replace (old):
```
Working Dazzle apps in `examples/`: `simple_task`, `contact_manager`, `support_tickets`, `ops_dashboard`, `fieldtest_hub`, `custom_renderer`, `pra`, `component_showcase`, `project_tracker`, `design_studio`, `llm_ticket_classifier`, `acme_billing`, `hr_records`, `invoice_ops`
```
with (new):
```
Working Dazzle apps in `examples/`: `simple_task`, `contact_manager`, `support_tickets`, `ops_dashboard`, `fieldtest_hub`, `project_tracker`, `design_studio`, `llm_ticket_classifier`, `acme_billing`, `hr_records`, `invoice_ops`
```

- [ ] **Step 2: Add the 3 names to the fixtures list (L227)**

In the line beginning ``Framework-validation fixtures in `fixtures/` ``, insert the three names into the backticked list (order doesn't matter to the test — it compares as a set). Change the existing tail
```
..., `transition_atomic`, `scope_runtime` (FK-path/EXISTS create-scope #1311 ...
```
to
```
..., `transition_atomic`, `scope_runtime`, `pra`, `custom_renderer`, `component_showcase` (FK-path/EXISTS create-scope #1311 ...
```
(Keep the trailing parenthetical about `scope_runtime` intact — the test strips path-bearing/parenthetical tokens; only backticked dir-names are compared.)

- [ ] **Step 2b: Update the Examples-section prose count if present**

Run:
```bash
grep -nE "14 (example|app)|fourteen example" .claude/CLAUDE.md || echo "NO_COUNT_PROSE"
```
If a "14 examples" phrase exists in the surrounding prose, change it to `11 examples`. If `NO_COUNT_PROSE`, skip.

- [ ] **Step 3: Verify the drift gate is green again**

Run:
```bash
uv run pytest tests/unit/test_docs_drift.py::test_claude_md_examples_and_fixtures_lists_match_disk -q
```
Expected: PASS.

*(No commit yet.)*

---

### Task 4: Mechanical path-swap across LIVE files (guarded, frozen-safe)

**Files:** every LIVE file containing `examples/custom_renderer`, plus `examples/pra` in `scripts/bench_interp.py`, `src/dazzle/core/validation/flows.py`, `.github/workflows/ci.yml`, `tests/unit/test_dazzle_validate_drift.py`, and `examples/component_showcase` in `.claude/commands/fuzz.md`. The MCP registry entry is handled separately in Task 5 (deletion, not swap).

- [ ] **Step 1: List every live hit first (sanity check before editing)**

Run:
```bash
cd /Volumes/SSD/Dazzle
grep -rlnE "examples/(pra|custom_renderer|component_showcase)" \
  src/ tests/ scripts/ docs/reference/ .claude/commands/ .github/ \
  --include=*.py --include=*.md --include=*.yml --include=*.yaml \
  | grep -vE "docs/(history|plans)/|docs/superpowers/specs/|docs/guides/agent-upgrade" \
  | sort
```
Expected (the editable allowlist): the six framework source files, the three asserting tests, `tests/unit/test_dazzle_validate_drift.py`, `scripts/bench_interp.py`, `src/dazzle/core/validation/flows.py`, `docs/reference/htmx-templates.md`, `.claude/commands/fuzz.md`, `.github/workflows/ci.yml`. (`tests/unit/test_cli_sweep.py` and `tests/unit/test_examples_rbac_lint_clean.py` reference by **name** not path — handled in Task 6. `src/dazzle/mcp/examples.py` is handled in Task 5.)

- [ ] **Step 2: Apply the three path swaps over exactly that allowlist**

Run (BSD sed; the file list is the grep output above, minus `mcp/examples.py`):
```bash
cd /Volumes/SSD/Dazzle
FILES=$(grep -rlnE "examples/(pra|custom_renderer|component_showcase)" \
  src/ tests/ scripts/ docs/reference/ .claude/commands/ .github/ \
  --include=*.py --include=*.md --include=*.yml --include=*.yaml \
  | grep -vE "docs/(history|plans)/|docs/superpowers/specs/|docs/guides/agent-upgrade" \
  | grep -v "src/dazzle/mcp/examples.py")
for f in $FILES; do
  sed -i '' \
    -e 's|examples/pra|fixtures/pra|g' \
    -e 's|examples/custom_renderer|fixtures/custom_renderer|g' \
    -e 's|examples/component_showcase|fixtures/component_showcase|g' \
    "$f"
done
```

- [ ] **Step 3: Verify no LIVE file retains an old path, and frozen history is untouched**

Run:
```bash
# LIVE must be clean (mcp/examples.py still has pra path — removed in Task 5 — so allow it):
grep -rnE "examples/(pra|custom_renderer|component_showcase)" \
  src/ tests/ scripts/ docs/reference/ .claude/commands/ .github/ \
  --include=*.py --include=*.md --include=*.yml --include=*.yaml \
  | grep -vE "docs/(history|plans)/|docs/superpowers/specs/|docs/guides/agent-upgrade" \
  | grep -v "src/dazzle/mcp/examples.py" \
  && echo "!!! STILL HAS OLD PATHS — investigate" || echo "LIVE_PATHS_CLEAN"
# Frozen must be UNCHANGED:
git diff --name-only | grep -E "CHANGELOG.md|docs/history/|docs/plans/|docs/superpowers/specs/|docs/guides/agent-upgrade" \
  && echo "!!! TOUCHED FROZEN HISTORY — revert those files" || echo "FROZEN_UNTOUCHED"
```
Expected: `LIVE_PATHS_CLEAN` and `FROZEN_UNTOUCHED`.

- [ ] **Step 4: Run the asserting tests that pin those strings**

Run:
```bash
uv run pytest tests/unit/test_runtime_services_doc.py tests/unit/test_dispatch_ctx_detail_view.py \
  tests/unit/core/test_render_clause_linking.py tests/unit/test_dazzle_validate_drift.py -q
```
Expected: all PASS (they now assert `fixtures/custom_renderer` / `fixtures/pra`).

*(No commit yet.)*

---

### Task 5: Remove the `pra` entry from the MCP example registry

**Files:** Modify `src/dazzle/mcp/examples.py` (delete lines 127–165, the `"pra": { ... },` block)

`pra` is a conformance corpus, not a discoverable tutorial app; fixtures are not registered here. The block sits between the `fieldtest_hub` entry (ends `},` ~L126) and the `ops_dashboard` entry (`"ops_dashboard": {` ~L166).

- [ ] **Step 1: Delete the entire `"pra"` dict block**

Remove this exact block (open `src/dazzle/mcp/examples.py`, delete from the `"pra": {` line through its matching `},`):
```python
        "pra": {
            "name": "pra",
            "path": "examples/pra",
            "title": "PRA Reference App",
            "description": "Comprehensive reference app demonstrating experiences (wizards), "
            "processes, services, state machines, and advanced DSL features",
            "demonstrates": [
                "entities",
                "relationships",
                "surfaces",
                "workspace",
                "persona",
                "experience",
                "wizard",
                "multi_step_flow",
                "integration_steps",
                "services",
                "state_machines",
                "computed_fields",
                "access_control",
                "processes",
                "foreign_model",
            ],
            "complexity": "advanced",
            "entities": [
                "User",
                "Project",
                "Task",
                "Comment",
                "Notification",
            ],
            "experiences": [
                "checkout_flow",
                "payment_processing",
                "user_onboarding",
                "purchase_approval",
            ],
            "ci_status": "P1",
        },
```

- [ ] **Step 2: Verify the registry still parses and `pra` is gone**

Run:
```bash
uv run python -c "from dazzle.mcp.examples import get_example_metadata; m=get_example_metadata(); assert 'pra' not in m, 'pra still registered'; print('OK, examples:', sorted(m))"
```
Expected: `OK, examples: [...]` with no `pra`.

- [ ] **Step 3: Run any tests that assert on the registry contents**

Run:
```bash
uv run pytest tests/ -k "example_metadata or examples_registry or mcp_examples" -q 2>&1 | tail -5
```
Expected: PASS (or "no tests ran" if none target the registry directly — acceptable; Step 2 already proved it).

*(No commit yet.)*

---

### Task 6: Fix list-membership gates & counts

**Files:** Modify `tests/unit/test_cli_sweep.py`, `tests/unit/test_examples_rbac_lint_clean.py`, `tests/unit/test_example_index.py`

These reference the apps by **name** (membership/count), not path, so they don't change with Task 4.

- [ ] **Step 1: `test_cli_sweep.py` — drop `custom_renderer` from the asserted tuple (L117–124)**

Remove the `"custom_renderer",` line so the tuple reads:
```python
        for name in (
            "contact_manager",
            "fieldtest_hub",
            "ops_dashboard",
            "simple_task",
            "support_tickets",
        ):
```

- [ ] **Step 2: `test_cli_sweep.py` — change the app count 14 → 11 and refresh the comment (L132–140)**

Replace the comment block + assertion with:
```python
        # 11 examples (kayfabe business apps only; pra, custom_renderer,
        # component_showcase were reclassified to fixtures/ in the
        # 2026-06-13 example-guides Phase 0): contact_manager, fieldtest_hub,
        # ops_dashboard, simple_task, support_tickets, design_studio,
        # llm_ticket_classifier, project_tracker, acme_billing, invoice_ops,
        # hr_records.
        assert len(payload["apps"]) == 11
```

- [ ] **Step 3: `test_examples_rbac_lint_clean.py` — remove `custom_renderer` from `_KNOWN_EXAMPLES` (L42)**

Delete the `"custom_renderer",` entry from the `_KNOWN_EXAMPLES` list (L33–…). It is parametrized (L86) and would otherwise try to validate the now-missing `examples/custom_renderer`.

- [ ] **Step 4: `test_examples_rbac_lint_clean.py` — remove the stale `pra` / `component_showcase` entries from `_DOGFOOD_EXEMPT` (L62–…)**

Delete the `"pra": "...",` (L67) and `"component_showcase": "...",` (L70) entries. They are no longer under `examples/`, so the auto-discovery loop (L118) will never surface them; leaving them is dead config.

- [ ] **Step 5: `test_example_index.py` — point `COMPONENT_SHOWCASE` at fixtures (L13–17)**

Add a fixtures dir constant and redirect:
```python
EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"
FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"
COMPONENT_SHOWCASE = FIXTURES_DIR / "component_showcase"
```
Then change the index build call(s) in the component_showcase tests (L29/37/45/55) from `build_example_index(EXAMPLES_DIR)` to `build_example_index(FIXTURES_DIR)` so the gallery is still validated at its new home. (The `skipif` on L26 keeps the suite green even if the index builder is examples-only — but redirecting keeps the coverage.)

- [ ] **Step 6: Verify all three gates pass**

Run:
```bash
uv run pytest tests/unit/test_cli_sweep.py tests/unit/test_examples_rbac_lint_clean.py \
  tests/unit/test_example_index.py -q
```
Expected: all PASS (note: `test_cli_sweep` boots the sweep over `examples/` — it must now see exactly 11 apps).

*(No commit yet.)*

---

### Task 7: Full verification, single commit, bump & ship

**Files:** all staged changes from Tasks 2–6, plus version-bump files.

- [ ] **Step 1: Format + lint + type-check the touched source**

Run:
```bash
cd /Volumes/SSD/Dazzle
uv run ruff format src/ tests/ scripts/
uv run ruff check src/ tests/ scripts/ --fix
uv run mypy src/dazzle
```
Expected: ruff clean; mypy `Success: no issues found`.

- [ ] **Step 2: Re-validate every moved app at its new path**

Run:
```bash
for app in custom_renderer component_showcase; do (cd fixtures/$app && dazzle validate 2>&1 | tail -1); done
(cd fixtures/pra && dazzle validate 2>&1 | tail -1)   # pra: validation-failing shapes EXPECTED
```
Expected: the two real apps clean; `pra` reports its intentional conformance diagnostics (not a regression).

- [ ] **Step 3: Run the full fast suite (pre-ship gate)**

Run:
```bash
set -o pipefail
uv run pytest tests/ -m "not e2e" -q 2>&1 | tail -8
```
Expected: all pass (matches the prior 18102-passing baseline ± the renamed assertions). If anything fails, it names a reference this plan missed — fix it in the relevant task before committing.

- [ ] **Step 4: Bump the patch version**

Run the `/bump patch` skill steps (edits the 6 canonical version lines + moves the CHANGELOG Unreleased section). Add this CHANGELOG entry under the new version:
```markdown
### Changed
- **Reclassified `pra`, `component_showcase`, `custom_renderer` from `examples/` to
  `fixtures/`** (example-guides Phase 0). An *example* is now exclusively a kayfabe
  business app demonstrating Dazzle as an app factory (and will carry per-persona
  onboarding guides); framework artifacts — a parser-conformance corpus, a component
  gallery, and a renderer-extension demo — live under `fixtures/`. Examples: 14 → 11.
  Removed `pra` from the MCP example registry. Frozen history left untouched.

### Agent Guidance
- New apps that demonstrate a *framework capability* (not a fictional business) belong
  in `fixtures/`, not `examples/`. Every `examples/` app must be a kayfabe product and
  (from later phases) carry per-persona guides. `src/dazzle/http/pra/` is the framework
  perf-harness module and is unrelated to `fixtures/pra/` (the corpus).
```

- [ ] **Step 5: Single coherent commit + tag + push**

Run (substitute the bumped version for `X.Y.Z`):
```bash
cd /Volumes/SSD/Dazzle
git add -A
git commit -m "$(cat <<'EOF'
refactor(examples): reclassify pra/component_showcase/custom_renderer → fixtures (guides Phase 0)

An example is now exclusively a kayfabe business app (and will carry per-persona
guides); framework artifacts move to fixtures/. Moves 3 dirs + updates live refs
(framework docstrings/error-messages, asserting tests, list/count gates, MCP
registry pra removal, CLAUDE.md drift lists, bench script, CI/command comments,
htmx-templates doc). src/dazzle/http/pra/ (perf harness) unchanged. Frozen history
untouched. Examples 14 → 11.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
git tag vX.Y.Z
git push && git push --tags
git status --short && echo "CLEAN"
```
Expected: push succeeds, `CLEAN` worktree, tag pushed.

- [ ] **Step 6: Confirm CI green**

After push, watch the run (or `/cimonitor`). Expected: the `examples/*/ fixtures/*/` glob jobs (AsyncAPI, e2e-smoke, Sentinel audit) auto-discover the moved apps at their new paths; `pra` is still skipped by the conformance-corpus condition. If red, the failing job names the missed reference.

---

## Self-review notes (author)

- **Spec coverage:** This plan covers Strand 0 / Phase 0 of `docs/superpowers/specs/2026-06-13-example-app-guides-design.md` in full (taxonomy move + every live-reference category enumerated in §2's blast-radius). Phases 1–4 (quality bar, authoring, e2e walk, docs) are out of scope here and get their own plans.
- **No placeholders:** every edit shows exact old/new text or an exact guarded command + verification.
- **Type/name consistency:** `FIXTURES_DIR` introduced in Task 6 Step 5 matches its use in the same step; counts (14→11) are consistent across CLAUDE.md prose, `test_cli_sweep`, and the CHANGELOG.
- **Frozen-history safety** is asserted mechanically (Task 4 Step 3) so the migration can't silently rewrite the record.
- **Single-commit discipline:** no task commits before Task 7; each task ends with a targeted gate so failures localize.
