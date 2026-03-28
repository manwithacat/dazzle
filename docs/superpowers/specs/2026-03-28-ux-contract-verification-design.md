# UX Contract Verification — Design Spec

**Date:** 2026-03-28
**Status:** Approved
**Builds on:** [UX Verification Design (2026-03-27)](2026-03-27-ux-verification-design.md)

## Problem

The Dazzle frontend is server-rendered HTML driven by HTMX and Alpine.js. Bugs cluster at the integration seams: HTMX swap targets that don't match, missing form fields, state machine buttons with wrong `hx-vals`, permission-gated UI elements that leak through to unauthorized personas. These are deterministic bugs — they exist in the rendered HTML, not in JS runtime behavior — but we currently only catch them via slow Playwright browser tests (5+ minutes for 226 interactions on simple_task).

## Goal

A fast, deterministic verification system that derives DOM contracts from the AppSpec and verifies every rendered HTML fragment against them. No browser needed for 90%+ of assertions. The system must be operable by an AI agent in an autonomous fix loop: run contracts, read failures, fix templates/routes, re-run, converge to zero failures.

Secondary goal: the RBAC contract results serve as auditable compliance evidence — provable enforcement of the access control model at the presentation layer (SOC 2 / ISO 27001).

## Design Principles

1. **AppSpec is the contract source.** Every assertion is mechanically derived from the DSL. No hand-written test assertions.
2. **HTML is the test surface.** If the rendered HTML is correct (right `hx-*` attributes, right fields, right action buttons), the behavior follows deterministically because HTMX and Alpine.js are stable.
3. **Converge to zero.** Ratchet model: record a baseline, fix failures, re-run, baseline improves. Target is zero failures.
4. **Speed over fidelity for most checks.** httpx + HTMLParser (milliseconds) for structure and round-trips. Playwright (seconds) only for the few interactions that genuinely need JS execution.

## Architecture

Three verification modes, each building on the previous:

### Mode 1: Fragment Contracts

Fetch rendered pages via httpx. Parse HTML. Assert DOM structure matches what the AppSpec declares.

- **Input:** AppSpec + running server
- **Execution:** HTTP GET with session cookie, parse response with HTMLParser
- **Assertions:** Element presence, attribute values, field completeness
- **Speed:** ~50ms per page
- **Catches:** Wrong hx-* attributes, missing form fields, broken template rendering, missing columns

### Mode 2: Round-Trip Contracts

For each HTMX trigger found in Mode 1, simulate the request HTMX would send (with correct `HX-Request`, `HX-Target`, `HX-Trigger` headers). Verify the response fragment.

- **Input:** Triggers discovered in Mode 1 + running server
- **Execution:** HTTP request with HTMX headers, parse response fragment
- **Assertions:** Response status, valid HTML, expected fragment structure, correct HX-Trigger response headers
- **Speed:** ~100ms per round-trip
- **Catches:** Server returns wrong fragment, swap target mismatch, missing response triggers, broken detail/edit/create views

### Mode 3: RBAC Contracts

For each entity × persona × operation in the permission matrix, verify UI enforcement. Authenticate as each persona, fetch relevant pages, assert permitted actions are present and forbidden actions are absent.

- **Input:** AppSpec permission matrix + running server
- **Execution:** Authenticate per persona via `/__test__/authenticate`, fetch pages, assert element presence/absence
- **Assertions:** Permitted operations have UI elements; forbidden operations have no UI elements and return 403 on direct access
- **Speed:** ~50ms per assertion
- **Catches:** Permission leaks (delete button visible to unauthorized persona), missing access controls, scope rule enforcement at UI layer
- **Compliance:** Results map directly to the RBAC matrix for SOC 2 / ISO 27001 audit evidence

### Existing Layer A: Playwright Browser Tests

Retained for interactions that genuinely need JS execution:

- Drawer open/close (CSS transform animations)
- Keyboard shortcuts (Escape to close)
- Drag-and-drop reordering
- Toast notification appearance/dismissal

Estimated 10-20 interactions per app, not hundreds.

## Contract Schema

### Contract Types

**ListPageContract** — one per list-mode surface:
- Table exists with `data-dazzle-table="{entity}"`
- Table rows have `hx-get` pointing to `/app/{entity_slug}/{id}`
- Create link exists with `href=/app/{entity_slug}/create`
- For each DSL field in the surface's section blocks: column header with `data-dz-col="{field}"`
- Search input with `hx-get` targeting the table body
- Sort headers with `hx-get` and sort params

**CreateFormContract** — one per entity (not per surface):
- Form exists with `hx-post` targeting `/{entity_slug_plural}`
- For each DSL required field: input exists with `name="{field}"`
- Submit button with `type="submit"`
- No extraneous fields outside the DSL entity definition

**EditFormContract** — one per entity:
- Form exists with `hx-post` targeting `/{entity_slug_plural}/{id}`
- All editable DSL fields present with pre-filled values
- Submit button exists

**DetailViewContract** — one per entity:
- Heading exists
- For each DSL field: field value displayed
- Edit link with `href=/app/{entity_slug}/{id}/edit` (if any persona has UPDATE)
- Delete button with `hx-delete` (if any persona has DELETE)
- For each state machine transition: button with `hx-put` and `hx-vals` containing the target state

**WorkspaceContract** — one per workspace:
- For each region: `div` with `data-region-name="{name}"`
- For each region: `hx-get` pointing to the region data endpoint
- Drawer element with `id="dz-detail-drawer"`
- Above-fold regions have `hx-trigger="load"`, below-fold have `hx-trigger="intersect once"`

**RoundTripContract** — one per HTMX trigger discovered in Mode 1:
- Response status 200 (or 3xx redirect)
- Response is valid HTML fragment (no unclosed tags in critical elements)
- Fragment contains expected elements based on target (drawer → detail fields; table body → rows)
- Response headers include expected `HX-Trigger` events where applicable

**RBACContract** — one per entity × persona × operation:
- For permitted operations: the UI element exists (create link, edit link, delete button, transition button)
- For forbidden operations: the UI element is absent
- For forbidden LIST: page returns 403 or redirects to login
- For forbidden API access: direct HTTP request returns 403

### Contract Identity

Each contract has a deterministic ID: `sha256(type:entity:persona:surface:operation)[:12]`. This enables stable baseline tracking across runs.

## Contract Generation

**Entry point:**
```python
def generate_contracts(appspec: AppSpec) -> list[Contract]
```

**Derivation rules:**

| AppSpec element | Contract type | Key |
|----------------|--------------|-----|
| Entity with list-mode surface | ListPageContract | entity × surface |
| Entity with any surface | CreateFormContract | entity (deduplicated) |
| Entity with any surface | EditFormContract | entity (deduplicated) |
| Entity with any surface | DetailViewContract | entity (deduplicated) |
| Workspace | WorkspaceContract | workspace |
| hx-* trigger in Mode 1 HTML | RoundTripContract | url × target |
| permit/forbid rule | RBACContract | entity × persona × operation |

**AppSpec → URL mapping** (universal Dazzle conventions):
- Entity name → URL slug: `Task` → `task`, `TaskComment` → `taskcomment`
- List page: `/app/{slug}`
- Detail page: `/app/{slug}/{id}`
- Create page: `/app/{slug}/create`
- Edit page: `/app/{slug}/{id}/edit`
- API collection: `/{slug_plural}`
- API item: `/{slug_plural}/{id}`
- Workspace: `/app/workspaces/{workspace_name}`

**AppSpec → DOM mapping** (universal template conventions):
- DELETE permission → `[hx-delete]` button on detail page
- CREATE permission → `a[href*=create]` link on list page
- UPDATE permission → `a[href*=edit]` link on detail page
- State transition → `button[hx-put]` with `hx-vals` containing target state
- Field in list surface → `[data-dz-col="{field}"]` column header

## Execution Model

### CLI

```bash
dazzle ux verify --contracts              # Modes 1+2+3 (no browser)
dazzle ux verify --contracts --mode 1     # Fragment contracts only
dazzle ux verify --contracts --mode 2     # + round-trip
dazzle ux verify --contracts --mode 3     # + RBAC
dazzle ux verify --browser                # Playwright only (Layer A)
dazzle ux verify                          # All modes
dazzle ux verify --contracts --strict     # Exit 1 on any failure
dazzle ux verify --contracts --update-baseline  # Update baseline after fixes
```

### Prerequisites

- Running server (`dazzle serve --local`)
- `.dazzle/runtime.json` for URL discovery
- Test data seeded via `/__test__/seed`

### Execution Flow

1. Load AppSpec → `generate_contracts(appspec)` → contract list
2. Authenticate as admin → session cookie
3. **Mode 1:** For each page contract, `httpx.get(url, cookies=session)`, parse HTML, assert structure
4. **Mode 2:** For each `hx-*` trigger found in Mode 1 HTML, simulate HTMX request with correct headers, assert response fragment
5. **Mode 3:** For each persona, authenticate, for each RBAC contract, fetch page, assert presence/absence of action elements
6. Compare against baseline → classify as regression/fixed/existing
7. Generate report (markdown + JSON, same format as existing)

### Ratchet Mechanism

Results are written to `.dazzle/ux-verify/baseline.json`:

```json
{
  "timestamp": "2026-03-28T12:00:00Z",
  "total": 350,
  "passed": 340,
  "failed": 10,
  "contracts": {
    "abc123def456": {"status": "passed", "type": "ListPageContract", "entity": "Task"},
    "789012345678": {"status": "failed", "type": "RBACContract", "entity": "User", "error": "..."}
  }
}
```

On each run:
- New failures (passed → failed): reported as **regressions** (prominent)
- Fixed failures (failed → passed): reported as **fixed** (positive)
- Existing failures (failed → failed): reported as **known** (informational)
- `--strict` mode: exit 1 on any failure (for CI after convergence)
- `--update-baseline`: overwrite baseline with current results

### Performance Budget

| Mode | Checks | Time per check | Total |
|------|--------|---------------|-------|
| Mode 1 (fragments) | ~50 pages | ~50ms | ~2.5s |
| Mode 2 (round-trips) | ~100 requests | ~100ms | ~10s |
| Mode 3 (RBAC) | ~200 assertions | ~50ms | ~10s |
| **Total** | **~350** | | **~25s** |

Compare: Playwright Layer A takes 5+ minutes for 226 interactions. Contract verification is 10× faster.

## Module Layout

```
src/dazzle/testing/ux/
├── __init__.py
├── inventory.py            # (existing) interaction enumeration
├── contracts.py            # (new) contract generation from AppSpec
├── contract_checker.py     # (new) httpx-based contract verification
├── htmx_client.py          # (new) HTMX request simulation
├── baseline.py             # (new) ratchet mechanism
├── runner.py               # (existing) Playwright browser tests
├── harness.py              # (existing) Postgres lifecycle
├── fixtures.py             # (existing) seed data generation
├── structural.py           # (existing → absorbed into contract_checker)
└── report.py               # (existing, extended for contract results)
```

Four new files. Existing code unchanged except CLI wiring and report extension.

## Scope Boundary

**In scope:** Everything generated by the DSL — entities, surfaces, workspaces, permissions, state machines, forms, tables, detail views.

**Out of scope:** Custom islands, user-written JS, third-party integrations. These are the user's responsibility, not the framework's verification surface.

## Compliance Integration

RBAC contract results map directly to the existing compliance pipeline in `src/dazzle/compliance/`:

- Each `RBACContract(entity, persona, operation, passed)` is a verifiable control assertion
- Export format compatible with the evidence extraction system
- The combination of static RBAC matrix verification (`src/dazzle/rbac/matrix.py`) + runtime UI contract verification provides two independent layers of access control evidence
