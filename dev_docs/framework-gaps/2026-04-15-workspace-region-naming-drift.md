# Framework Gap — Workspace Region Naming Drift

**Status:** SUBSTANTIALLY RESOLVED (2026-04-19 re-verification)
**Synthesized:** Cycle 224 (framework_gap_analysis)
**Contributing cycles:** 217, 220, 222
**Evidence weight:** 3 observations + 3 proposals across 3 apps, all converging on the same subsystem

## Resolution summary (2026-04-19)

Heuristic 1 re-reproduction against the current framework:

| Row | Original observation | Status | Mechanism |
|-----|---------------------|--------|-----------|
| **EX-013** | fieldtest_hub "Issue Board" sidebar href 404s | **RESOLVED** | Nav generator now emits `/app/issuereport` (matches route-generator's snake_case-collapsed slug). `curl -b cookie /app/issuereport` → 200 with title "Issue Board — FieldTest Hub". |
| **EX-025** | 4 `workspace:*` Phase A contracts FAIL because rendered HTML lacks `data-dz-region-name` attrs | **RESOLVED** | Issue #803 extended `contract_checker._check_workspace` to accept EITHER `data-dz-region-name` attrs OR the `dz-workspace-layout` JSON island. Dashboard workspaces use the JSON path; classic workspaces use the attr path. Both satisfy the contract. Verified: Phase A on simple_task now passes 27/2 with zero `workspace:*` failures. |
| **EX-033** | ops_dashboard Platform Admin nav 404s (Health → /app/health but surface is `/app/systemhealth`) | **DSL AUTHORING** | Marked `DEFERRED_APP_QUALITY` in the backlog — the ops_dashboard DSL declares surfaces the nav can't route to. Framework slugging is internally consistent; the example app's surface definitions are wrong. |
| **PROP-049** workspace-metrics-region | No contract | **PROMOTED** | `~/.claude/skills/ux-architect/components/metrics-region.md` exists. |
| **PROP-050** workspace-tree-region | No contract | Still PROPOSED | Routine `missing_contracts` → `contract_audit` path. |
| **PROP-051** workspace-diagram-region | No contract | Still PROPOSED | Routine `missing_contracts` → `contract_audit` path. |

The "three-way string drift" framing in the original problem statement is now obsolete. The route/nav/contract paths converge on the same slug rules; the remaining two uncontracted region templates are normal governance backlog, not a framework drift defect.

**Remaining action:** promote PROP-050 + PROP-051 in a future `contract_audit` cycle. That's it.

---

## Problem statement

The framework has **at least three independent code paths** that derive names, routes, and DOM markers for workspace regions. They don't agree. The divergence manifests as:

- Contract-verification tooling expects a DOM attribute the template compiler never emits
- Sidebar nav hrefs point at routes the route generator never registers
- An entire template directory (`src/dazzle_ui/templates/workspace/regions/`) has no ux-architect contracts because it was never systematically scanned

Each of these looks like a different defect on the surface. They share a root cause: **workspace regions are identified by at least three different strings in three different subsystems, and nothing enforces their consistency**.

## Evidence

| Row | Cycle | App | Subsystem | Observation |
|---|---|---|---|---|
| **EX-013** | 217 | fieldtest_hub | Nav generator | Sidebar 'Issue Board' link 404. Tried 4 slug variants (`issue_board`, `issue_report`, `issue_reports`, `issue_report_list`) — none resolve. DSL declares `surface issue_report_list "Issue Board"` but the runtime exposes no working URL. Nav href does not match route registration. |
| **EX-025** | 220 | simple_task | Contract generator ↔ template compiler | 4 `workspace:*` Phase A contracts FAIL because rendered workspace HTML does not emit `data-region-name="<name>"` on region wrappers. 15 region names affected across `task_board`, `admin_dashboard`, `team_overview`, `_platform_admin`. Contract generator expects an attribute the templates don't produce. |
| **EX-033** | 222 | ops_dashboard | Nav generator | Platform Admin workspace sidebar lists `Health` (`/app/health`), `Deploys` (`/app/deploys`), `App Map` (`/app/app-map`) — **all 404**. Real surfaces live at `/app/systemhealth` and `/app/deployhistory`. Slug mangling mismatch: `system_health` → `systemhealth` in routes, but nav generator emits `health`. |
| **PROP-047** | 222 | ops_dashboard | Template scan coverage | `workspace-metrics-region` — KPI grid responsive layout with attention-level row colouring. Lives in `src/dazzle_ui/templates/workspace/regions/metrics.html`. No contract. |
| **PROP-048** | 222 | ops_dashboard | Template scan coverage | `workspace-tree-region` — native `<details>/<summary>` recursive hierarchy with child-count badges, HTMX drawer-load on click. Lives in `workspace/regions/tree.html`. No contract. |
| **PROP-049** | 222 | ops_dashboard | Template scan coverage | `workspace-diagram-region` — Mermaid.js CDN lazy-load + overflow wrapper. Lives in `workspace/regions/diagram.html`. No contract. |

## Root cause hypothesis

The workspace-region subsystem has (at least) three string-derivation paths that must agree but don't:

### Path A — DSL → `WorkspaceSpec.regions[].name`

Canonical region identifier from the DSL source. Everything else should derive from this.

### Path B — Route generator → URL slug

`src/dazzle_back/runtime/route_generator.py` produces routes for entity surfaces at `/app/<entity_slug>` where `<entity_slug>` appears to be `entity.name.lower().replace('_', '')` — camelCase flattened. That's why `system_health` → `systemhealth`. This collapsing is irreversible without knowing the original.

### Path C — Nav generator → sidebar href

`src/dazzle_ui/converters/template_compiler.py` (or wherever sidebar nav is built) emits `/app/<surface_slug>` hrefs from the surface declarations — but **uses a different slug rule than Path B**. Some surfaces keep underscores (`_platform_admin` → `/app/workspaces/_platform_admin` works), some collapse (`issue_report_list` → tried multiple variants, none work), some get truncated (`system_health` → `/app/health`).

### Path D — Contract generator → DOM attribute expectation

`dazzle ux verify --contracts` generates contracts from the DSL (Path A) and writes assertions like `element[data-region-name="metrics"]`. The template compiler (Path C layer) renders workspace regions **without emitting `data-region-name` attributes at all**. This is EX-025 — the Path A→D assertion fires against a DOM that Path A→C never marks up.

### Path E — Template family coverage

The `missing_contracts` scan in cycle 17 read template files looking for DaisyUI class tokens and uncontracted patterns. It missed the `workspace/regions/` subdirectory (cycle 222 PROP-047..049 show this empirically). No framework test or audit surfaces uncovered template families — contract coverage is manually tracked.

## Fix sketch (single canonicalising helper + test)

Introduce a single **`workspace_region_identity(spec, region)`** function in `src/dazzle_ui/converters/workspace_converter.py` (alongside `workspace_allowed_personas`, continuing that "single source of truth" pattern):

```python
@dataclass(frozen=True)
class RegionIdentity:
    dsl_name: str            # the canonical name from the DSL
    url_slug: str            # used in routes and nav hrefs
    dom_name: str            # value for data-region-name attribute
    template_path: Path      # workspace/regions/<kind>.html
    entity_surface_url: str  # /app/<entity_surface_slug> if the region targets an entity list

def workspace_region_identity(
    workspace: WorkspaceSpec,
    region: RegionSpec,
    appspec: AppSpec,
) -> RegionIdentity:
    """Return the canonical string set for a workspace region.

    All three subsystems (route generator, nav generator, contract
    generator) MUST call this helper. A test (new file:
    tests/unit/test_workspace_region_identity.py) verifies round-trip
    consistency: for every region in every example app's DSL, the
    url_slug produced by this helper MUST match the registered route.
    """
```

Then:
1. **Route generator** uses `identity.entity_surface_url` instead of ad-hoc slugging.
2. **Nav generator** calls the helper and emits `identity.entity_surface_url` as the href.
3. **Contract generator** calls the helper and asserts `[data-region-name="{identity.dom_name}"]`.
4. **Template compiler** emits `data-region-name="{identity.dom_name}"` on the region wrapper via context injection.
5. **Regression test** iterates all `WorkspaceSpec.regions` in the 5 example apps and asserts that for each, (a) `identity.url_slug` is a registered route, (b) the rendered HTML contains `data-region-name="{identity.dom_name}"`, (c) the sidebar nav href matches the url_slug.

The single helper unifies Paths B, C, D at their source. The regression test prevents future drift.

**For the `workspace/regions/` coverage gap (Path E):** add a dedicated `missing_contracts` cycle with a template-family-specific scan scope. That's a simple tactical fix, separate from the identity helper.

## Blast radius

**Confirmed affected apps:** fieldtest_hub (EX-013), simple_task (EX-025), ops_dashboard (EX-033, PROP-047/48/49)
**Likely affected:** every Dazzle app with workspace regions declared — that's 4 of 5 example apps (all except `contact_manager`, which has no workspaces).
**Non-trivial migration cost:** the existing templates emit HTML without `data-region-name`. Adding the attribute is a one-line template edit, but confirming no existing CSS/JS relies on the absence requires a grep across Alpine controllers in `src/dazzle_ui/runtime/static/js/dz-alpine.js`.

## Open questions

1. What are the actual slug rules used by the route generator vs the nav generator? A grep for `lower().replace` or similar in both files will show the mismatch explicitly.
2. Is `data-region-name` already used anywhere in the template family? If so, it's partial — adding it to the remaining files is low-risk. If not, introducing it fresh requires the regression test first.
3. For EX-013 specifically (`issue_report_list` → no working URL), is the issue that the surface is declared but no route is generated, or that the route exists but the nav href uses the wrong slug? Needs reproduction — a `finding_investigation` cycle could answer in <10 minutes.
4. Is there a cross-region pattern where a surface is both a workspace region AND a standalone entity list page, and the two routes need to agree? If yes, the identity helper has two consumers with identical contracts — good. If no, one is a region-scoped API response (`/api/workspaces/<ws>/regions/<region>`) and the other is a page (`/app/<entity>`), and the helper needs to produce both.

## Recommended follow-up

- **Immediately:** File a GitHub issue titled "Workspace region naming drift — unify route/nav/contract/template under workspace_region_identity helper". Link all 6 EX/PROP rows as evidence.
- **Next `finding_investigation` cycle (high-leverage):** Reproduce EX-013 on fieldtest_hub to confirm the mechanism. Trace sidebar nav href → route-generator registration path in `src/dazzle_back/runtime/route_generator.py`. That single investigation will answer Open Question #1 and #3 simultaneously and unblock the helper design.
- **Parallel:** A dedicated `missing_contracts` cycle scanning **only** `src/dazzle_ui/templates/workspace/regions/` should pick up heatmap, funnel_chart, bar_chart, timeline, metrics (already proposed), and any other uncontracted region types. Budget 10 helper calls, proposals-only.
- **After the helper lands:** Re-run Phase A contract verification on all 4 workspace-having example apps. EX-025's 4 failing `workspace:*` contracts should flip to PASS.
