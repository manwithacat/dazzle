# Framework Gap — Persona-Unaware Affordances

**Status:** Open
**Synthesized:** Cycle 224 (framework_gap_analysis)
**Contributing cycles:** 201, 216, 221, 223
**Evidence weight:** 8 observations across 4 apps, 1 partially-fixed (#775), 1 contradicts the fix

---

## Problem statement

The framework renders UI affordances — navigation links, bulk action buttons, empty-state CTAs, form fields — **without consulting whether the current persona is permitted to use them**. The result is a consistent cross-cycle defect pattern: personas see buttons they can't click, links that return 403/404, empty states advertising actions they can't perform, and create forms exposing ref fields they can't populate.

The v0.55.34 fix for #775 (`workspace_allowed_personas` helper in `src/dazzle_ui/converters/workspace_converter.py`) introduced a **single-source-of-truth** for workspace-level navigation filtering. It's the right pattern — but only one axis. The same approach needs to generalise to entity-level destructive actions, empty-state CTAs, create form field visibility, and (apparently) the workspace-access fallback case itself.

## Evidence

| Row | Cycle | App / Persona | Affordance type | Observation |
|---|---|---|---|---|
| **EX-002** (→#775) | 201 | support_tickets/agent | Workspace nav link | Sidebar shows agent_dashboard + my_tickets → 403 on click. Closed v0.55.34. |
| **EX-010** | 216 | ops_dashboard/ops_engineer | Entity list nav link | Sidebar shows 'Alerts' and 'Systems' → 403. Workspace itself accessible; the contained entity-list surfaces aren't. |
| **EX-011** | 216 | ops_dashboard/ops_engineer | Empty-state CTA | Three dashboard regions show empty-state copy inviting actions (`register system`, etc.) the persona cannot perform. |
| **EX-019** | 217 | fieldtest_hub/engineer | Bulk-action bar | "Delete items" button visible when zero rows selected. Polish issue — but same mechanism (visibility unrelated to state). |
| **EX-028** | 221 | support_tickets/customer | Workspace nav link | Sidebar STILL shows ticket_queue + agent_dashboard → 403. **Contradicts the #775 fix** because `workspace_allowed_personas` falls through to "no filter" when no persona claims the workspace via `default_workspace`, and no explicit `access:` block exists. |
| **EX-029** | 221 | support_tickets/customer | Create form field | Ticket create form exposes 'Assigned To' (ref User) to customer. Customer cannot meaningfully populate this — and from a business-rules POV, probably shouldn't be able to. |
| **EX-037** | 223 | fieldtest_hub/tester | Empty-state CTA | Tester dashboard "My Devices" empty state says "Add your first device" — but device creation is engineer-only. Same class as EX-011. |
| **EX-040** | 223 | fieldtest_hub/tester | Bulk-action bar | "Delete X items" destructive button rendered on **all 4 entity list pages** (Device, IssueReport, TestSession, Task) for tester. Delete is engineer-only on all four. **4 cross-entity hits in a single app**. |

## Root cause hypothesis

The v0.55.34 `workspace_allowed_personas` helper establishes the right pattern for **one** axis (workspace-level nav filtering). The framework has at least **four more independent paths** that render persona-gated UI without consulting persona access:

### 1. Bulk-action bar (highest blast radius)

`src/dazzle_ui/templates/components/bulk_action_bar.html` (or wherever the `<div>` with the "Delete X items" button lives) renders the destructive action **unconditionally** when an entity list view has a `delete` operation declared in the DSL. It does not consult whether the current persona is permitted to perform that delete on that entity.

**Fix location:** the template needs a guard — either an `{% if persona_can_delete %}` wrapper, or the context variable itself needs filtering by the template compiler. The cleanest shape: `src/dazzle_ui/converters/template_compiler.py` computes `persona_permitted_actions = [op for op in entity.ops if access_rules_permit(persona, entity, op)]` and the template iterates only over that.

### 2. Empty-state CTAs

Empty-state templates (`region.empty_state` for workspace regions; `list.empty_state` for standalone entity lists) hardcode copy like "Add your first device" without consulting whether the current persona can create. The copy is DSL-authored or convention-derived but is rendered without persona filtering.

**Fix location:** `src/dazzle_ui/converters/template_compiler.py` should compute `persona_can_create = entity_access(persona, entity, 'create')` and pass it to the empty-state template. The template then branches: if `persona_can_create`, show the CTA; otherwise, show a read-only-friendly message ("No items yet" with no action).

### 3. Create form field visibility

When a create form is generated for entity E, the template compiler iterates all fields in `E.input_schema` and renders form controls for each. It does not consult persona access on individual fields. Customer sees `assigned_to` on Ticket create (EX-029) because no field-level filter is applied.

**Fix location:** form generation in `src/dazzle_ui/converters/template_compiler.py` should filter out fields where the persona is not permitted to write. This needs a DSL extension (field-level access rules, or an inferred default like "ref User fields are writable only by personas that can list User"). The simplest starting point: omit any field declared as `ref <Entity>` if the current persona cannot list `<Entity>`.

### 4. Workspace access fallback — the `workspace_allowed_personas` bug EX-028 surfaced

The v0.55.34 helper has this resolution order:
1. Explicit `access.allow_personas` → return verbatim
2. Explicit `access.deny_personas` → inverted
3. Implicit `persona.default_workspace = ws.name` → personas claiming via default_workspace
4. **Fallback:** return `None` meaning "no filter — visible to everyone"

The fallback (rule 4) is the bug. Cycle 221 confirmed it: support_tickets declares no explicit `access:` on `ticket_queue` or `agent_dashboard`, and the `customer` persona doesn't have those as their `default_workspace`, but the fallback makes them visible anyway. The fix is to **invert the fallback**: when no explicit access and no implicit claimant exists, return an **empty list** (no one sees it) rather than `None`. That forces DSL authors to be explicit, which is the whole point of a non-Turing DSL.

But this is a breaking change for any app that relies on the current permissive default. It needs cross-app triage — specifically, run the existing Phase A contract verification against all 5 examples after the change and see which workspaces newly disappear.

## Fix sketch (unified helper)

Extract a general **`affordance_visible(persona, action, target)`** helper in a new file `src/dazzle_ui/converters/persona_visibility.py`, with specialisations:

```python
def workspace_visible(persona: PersonaSpec, workspace: WorkspaceSpec) -> bool: ...
def entity_action_visible(persona: PersonaSpec, entity: EntitySpec, op: str) -> bool: ...
def create_field_visible(persona: PersonaSpec, entity: EntitySpec, field: FieldSpec) -> bool: ...
def empty_state_cta_visible(persona: PersonaSpec, entity: EntitySpec) -> bool: ...
```

Each calls into the same underlying access-rule evaluator, just with different input shapes. The template compiler populates a `persona_visibility` context dict with these precomputed booleans and the templates (`bulk_action_bar.html`, `region_empty.html`, `list_empty.html`, `form_generated.html`) branch on them.

**Migration path for the fallback fix (rule 4):**
1. Add a DSL-level `default_access: permissive | strict` flag on the app declaration, defaulting to `permissive` (current behaviour) for backward compatibility.
2. When `strict`, `workspace_allowed_personas` falls through to `[]` instead of `None`, and all other visibility helpers default-deny.
3. Switch `strict` to the default for new projects in v0.56.0.
4. Migrate the 5 example apps one at a time, verifying Phase A still passes after each.

## Blast radius

**Confirmed affected apps:** support_tickets (EX-002, EX-028, EX-029), ops_dashboard (EX-010, EX-011), fieldtest_hub (EX-019, EX-037, EX-040)
**Likely affected:** contact_manager and simple_task (no observations yet, but the template mechanism is framework-wide so both apps are affected wherever their DSL declares delete-able entities or multi-persona workspaces)
**Blast radius for EX-040 alone:** 4 cross-entity destructive affordances in a single persona walk → this is not a per-app defect, it's a per-template defect that hits every entity list across every app.

## Open questions

1. Does the framework currently have any access-rule evaluator that takes `(persona, action, entity)` and returns a boolean? If yes, the gap is template-side only (connect it to the templates). If no, the evaluator has to be built first from the existing rbac/scope code in `src/dazzle/rbac/`.
2. Does `entity_access(persona, entity, 'delete')` differ from `entity_access(persona, entity, 'update')`? Most Dazzle DSLs use role-based declarations that conflate update and delete; a distinction may need to be added.
3. For EX-028 (the workspace fallback bug), how many example app workspaces rely on the permissive fallback? Counting via a quick grep of `ws.access` in each app's DSL would scope the migration cost.

## Recommended follow-up

- **Immediately:** File a GitHub issue for the framework-wide persona-unaware-affordances pattern with this gap doc as the body. Tag as `framework-gap`, link all 8 EX rows, label **priority:high** because EX-040 alone represents 4 destructive-action defects in a single walk.
- **Next `finding_investigation` cycle:** Reproduce EX-028 (the #775 fallback-bug) on support_tickets/customer. Needed to confirm the mechanism before the migration can be planned. Also file a follow-up GitHub issue under #775 since this contradicts a closed fix.
- **Preparatory work for the fix:** A small `finding_investigation` cycle can confirm whether `src/dazzle/rbac/` already has the evaluator needed, or whether a new helper must be built. This unblocks the primary fix.
