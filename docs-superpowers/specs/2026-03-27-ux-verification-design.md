# UX Verification — Design Spec

**Issue**: Dazzle apps should have world-class UX out of the box. The framework controls the entire browser session — HTMX partials, Alpine.js reactivity, server-rendered templates — making every interaction enumerable from the DSL and deterministically testable.
**Date**: 2026-03-27

## Problem

UX bugs in Dazzle apps are currently found by human testers filing issues. The Back button saga (#744, #745), the columns-2 fragmentation (#741), the kanban width (#739) — all caught by clicking. The framework generates every route, every button, every drawer from the DSL. These failures are preventable with automated verification.

Users should focus on domain-specific problems (custom islands, business logic). The framework should catch every routine interaction failure before a human sees it.

## Scope: Layer A — Deterministic CRUD Verification

This spec covers the first layer: given a known database state, verify every framework-generated interaction works correctly. Purely deterministic — no LLM, no heuristics. Known inputs, expected outputs.

**Layer B (follow-on):** Interaction contracts — drawer open/close, form validation, navigation context, state machine transitions.

**Layer C (follow-on):** Adversarial testing — double-clicks, race conditions, rapid navigation, concurrent modifications.

## Architecture

```
AppSpec → Interaction Inventory → [ Structural Assertions (no browser) ]
                                → [ Playwright Runner (real browser)   ]
                                → UX Report (coverage %, failures, screenshots)
```

### 1. Interaction Inventory

The inventory is a canonical list of every testable interaction point, derived from the AppSpec. It is the denominator in UX coverage.

**Interaction classes:**

| Class | Derived from | Assertion |
|-------|-------------|-----------|
| `page_load` | entity x surface x persona | HTTP 200, no JS console errors, expected heading/table present |
| `detail_view` | entity x persona | Detail fields render, Back element present |
| `create_submit` | entity x persona (create permission) | Form renders required fields, submit succeeds, entity in list |
| `edit_submit` | entity x persona (update permission) | Form pre-filled, submit succeeds, changes reflected |
| `delete_confirm` | entity x persona (delete permission) | Confirm fires, entity removed from list |
| `drawer_open` | workspace x region | Drawer slides in, content loads (not skeleton) |
| `drawer_close` | workspace x region | Drawer hidden, workspace visible, URL unchanged |
| `state_transition` | entity x transition x persona | Transition button present, state changes post-click |
| `access_denied` | entity x persona (no permission) | 403 or action button absent |
| `workspace_render` | workspace x persona | All regions render with data |

Each interaction is a `(class, entity, persona, action)` tuple. The generator walks the AppSpec and emits the full list.

**Coverage metric:** `interactions_tested / interactions_enumerated`. Every interaction gets pass/fail/skip.

**File:** `src/dazzle/testing/ux/inventory.py`

### 2. Postgres Test Harness

UX verification needs a live app with real data. The harness manages the database lifecycle.

**Lifecycle:**

1. Connect to local Postgres (default `postgresql://localhost:5432`, override via `DAZZLE_TEST_DB_URL`)
2. Detect Postgres availability — check `pg_isready` or attempt connection. Clear error if unavailable (with macOS-specific hints for Homebrew/Postgres.app)
3. `CREATE DATABASE dazzle_ux_test_{project}` (or reuse if exists)
4. `dazzle db baseline --apply` (schema from DSL)
5. Boot app via `dazzle serve --local` as subprocess, wait for `/health` 200
6. `POST /__test__/reset` (clean slate + demo auth users from personas)
7. `POST /__test__/seed` (fixture data — 5-10 rows per entity with relationships)
8. Hand off to test layers
9. Kill app subprocess
10. `DROP DATABASE` (or keep with `--keep-db`)

**Fixture generation:** Use the existing `dazzle demo propose` infrastructure to generate realistic seed data from the DSL. Each entity gets enough rows to exercise list rendering, pagination thresholds, and relationship traversal.

**File:** `src/dazzle/testing/ux/harness.py`

### 3. Structural Assertions (Layer 1 — No Browser)

Fast HTML-level checks by rendering templates server-side with test data and parsing the output. Runs in milliseconds. Catches "forgot the button" class of bugs.

**Checks:**
- Every detail view has a Back element
- Every form has a submit button with `type="submit"`
- Every drawer has a close mechanism (X button or backdrop)
- ARIA attributes present on interactive elements (`aria-label`, `role`, required field marking)
- No broken `href="#"` or empty `action=""` on forms
- HTMX attributes well-formed (`hx-get`/`hx-post` point to routes that exist in the AppSpec)
- No duplicate `id` attributes within a page
- All `<img>` tags have `alt` attributes

**Integration:** Can wire into `dazzle validate` as an extension — so `dazzle validate` catches DSL errors AND structural UX errors in one pass.

**File:** `src/dazzle/testing/ux/structural.py`

### 4. Playwright Runner (Layer 2 — Real Browser)

For each interaction in the inventory, authenticate as the persona, navigate, execute, assert outcomes.

**Per-interaction flow:**
1. Authenticate via `POST /__test__/authenticate` with persona role
2. Set session cookie from response
3. Navigate to target page
4. Wait for HTMX settle (`htmx:afterSettle` event or network idle)
5. Execute interaction (click, fill form, submit)
6. Assert outcome (page content, URL, element visibility, console errors)
7. Capture screenshot on failure

**Assertions per interaction class:**

- `page_load`: Status 200, page title or heading matches surface label, no JS console errors, table/list has rows
- `create_submit`: Form action points to valid endpoint, required fields have `required` attribute, submission returns 200/302, redirected page contains new entity
- `edit_submit`: Form fields pre-populated with entity data, submission updates the record
- `delete_confirm`: Confirm mechanism fires (dialog or hx-confirm), entity absent from list after deletion
- `drawer_open`: Drawer container visible, content swap complete (no skeleton), entity data present
- `drawer_close`: Drawer container hidden after Back/X/backdrop click, workspace content unchanged
- `access_denied`: Navigation to unpermitted surface returns 403 or redirect to login
- `workspace_render`: Each region container present, data loaded (row count > 0 for seeded entities)

**Concurrency:** Use the existing `BrowserGate` (semaphore-bounded Playwright instances) for parallel execution. One browser per persona to avoid session conflicts.

**File:** `src/dazzle/testing/ux/runner.py`

### 5. CLI + Report

```bash
# Full verification (structural + browser)
dazzle ux verify

# Structural only (fast, no browser)
dazzle ux verify --structural

# Filter scope
dazzle ux verify --persona teacher --entity Task

# Database control
dazzle ux verify --keep-db
dazzle ux verify --db-url postgresql://localhost:5432/mytest

# Output
dazzle ux verify --format json > report.json
dazzle ux verify --format markdown
```

**Report format:**

```
UX Verification Report — simple_task
=====================================
Structural: 38 checked, 38 passed, 0 failed
Interactions: 42 tested, 40 passed, 2 failed, 0 skipped
Coverage: 100% (42/42 enumerated)

FAILURES:
  x create_submit(Task, admin) — form submit returned 422
    Expected: 200/302 after POST /api/task
    Got: 422 {"detail": "title field required"}
    Screenshot: .dazzle/ux-verify/screenshots/create_submit_task_admin.png

  x drawer_close(task_board, user) — drawer still visible
    Expected: #dz-detail-drawer hidden after Back click
    Got: element still has display:block
    Screenshot: .dazzle/ux-verify/screenshots/drawer_close_task_board_user.png
```

**Output locations:**
- Screenshots: `.dazzle/ux-verify/screenshots/`
- JSON report: `.dazzle/ux-verify/report.json`
- Console log captures: `.dazzle/ux-verify/console/`

**MCP integration:** New `ux` tool with `verify` and `report` operations for agent-driven verification.

**File:** `src/dazzle/cli/ux.py`, `src/dazzle/testing/ux/report.py`

### 6. File Layout

```
src/dazzle/testing/ux/
    __init__.py          # Public API: verify(), UXReport, UXCoverage
    inventory.py         # AppSpec -> interaction list
    structural.py        # HTML assertion checks (no browser)
    runner.py            # Playwright interaction executor
    harness.py           # Postgres + app lifecycle management
    fixtures.py          # Demo data generation for test seeding
    report.py            # JSON/markdown report generation

src/dazzle/cli/ux.py     # CLI: dazzle ux verify
```

## Test Targets

Initial verification targets are the internal examples:
- `examples/simple_task` — smallest app, smoke test for the harness
- `examples/contact_manager` — relationships, multiple surfaces
- `examples/pra` — complex: experiences, state machines, multiple workspaces, 12 personas

Fixing verification failures in these examples improves them as reference implementations for all users.

## Layer B Roadmap (Follow-On)

After Layer A is passing on all examples:

**Interaction contracts** — deeper behavioral assertions:
- Drawer: open via row click, close via Back/X/backdrop/Escape, content loads within 2s
- Forms: validation fires on blur, error messages appear inline, submit disabled while loading
- Navigation: breadcrumb accuracy, active nav state, URL reflects current view
- Filters: narrowing results updates count, clearing filter restores full list
- Pagination: next/prev work, page count accurate, deep-linking to page N

**Visual regression** — screenshot baseline comparison:
- Golden screenshots per interaction at each viewport size
- Pixel diff with configurable threshold
- Automatic baseline updates on intentional changes

## Layer C Roadmap (Follow-On)

**Adversarial UX fuzzing:**
- Double-click submit buttons (form should not create duplicate entities)
- Navigate mid-HTMX-swap (page should recover gracefully)
- Rapid drawer open/close (no orphaned event listeners or stale state)
- Submit forms with boundary values (max-length strings, empty optionals, unicode)
- Concurrent modifications (two personas editing same entity)
- Network interruption during HTMX request (loading state should recover)

Goal: find bugs in HTMX and Alpine.js that we can report and offer fixes upstream.

## Non-Goals

- No LLM involvement in Layer A — purely deterministic
- No visual design scoring (that's the composition audit tool's job)
- No performance benchmarking (separate concern)
- No testing of custom islands or user-written code (framework-generated interactions only)
- No managing Postgres server lifecycle — assume it's running, verify it's reachable
