# Framework Gap — Widget Selection for Ref and Typed Form Fields

!!! info "📜 Historical snapshot — not current docs"
    Captured **2026-04-15** during Dazzle's autonomous-improvement cycles. It records the
    framework as it was then and the gap being worked at the time; **it may not
    describe current behaviour.** Start from the [documentation home](../../index.md),
    or see [Project Evolution](../../architecture/evolution.md) for how these fit together.


**Status:** CLOSED (both halves shipped)
**Synthesized:** Cycle 230 (framework_gap_analysis v2)
**Contributing cycles:** 201, 213, 221, 223
**Closed by:** Cycle 232 (date half) + Cycle 236 (ref half)
**Evidence weight:** 4 observations across 3 apps and 3 personas, all pointing at the same framework path (form-field template compiler)

---

## ⚠️ Cycle 236 closure

Both halves of this gap are now fixed:

- **Date half** — Cycle 232 added a one-line `widget_hint = "picker"` default in `_build_form_fields` for DATE/DATETIME fields. Closed EX-009 date-half.
- **Ref half** — Cycle 236 added `ref_entity` + `ref_api` to `FieldContext`, auto-populated them in the compiler for plain `ref Entity` fields with no explicit `source:` override, and added a new `{% elif field.ref_entity %}` branch in `form_field.html` that renders an Alpine-hydrated `<select>` mirroring the existing filter_bar pattern. This took fix direction (2) from the original gap doc (new template branch) rather than (1) (FieldSourceContext extension) — the new branch is clean because it doesn't need debounced search or autofill; ref entity lists are small enough (≤100) to hydrate all options at page load. Closed EX-006, EX-009 (ref-half), widget half of EX-029 + EX-041.

The original problem statement and evidence tables below are preserved for historical context.

---

---

## Problem statement

Dazzle has ~13 form widget contracts (widget-datepicker, widget-search-select, widget-combobox, widget-multiselect, widget-money, widget-slider, etc.) plus their underlying vendored implementations (Flatpickr, Tom Select, Quill, Pickr, etc.). When a DSL entity field has a native type like `date`, `datetime`, `money`, or declares `ref <Entity>`, the generated create/update form SHOULD render the corresponding widget — that's the whole point of having them.

**But across multiple apps and personas, the form-field generator is emitting plain `<input type="text">` for fields that should use specialised widgets.** Cross-cycle evidence shows the widget layer is not being reached for at least:

- **`date` fields** → should use `widget-datepicker` (Flatpickr wrapper) — observed as plain text input on simple_task
- **`ref <UserSubtypeEntity>` fields** (e.g. `ref Tester`, `ref Person`, `ref User`) → should use `widget-search-select` (Tom Select wrapper) — observed as plain text input on 3 different apps
- (Suspected, not yet observed) `datetime`, `money`, `decimal` fields with format hints

The widget contracts exist. The vendored JS/CSS exists. The form-field template macro system exists. **Something in the widget-selection path is short-circuiting.** Since the form layer is the primary touchpoint for most user interactions, this gap has high blast radius: every create/update form in every app is potentially affected.

## Evidence

| Row | Cycle | App / Persona | Field type | Observation |
|---|---|---|---|---|
| **EX-006** | 201 | support_tickets/agent | `ref User` (Assigned To) | Ticket create form renders Assigned To as a bare `<input type="text">`, not a search-select. Agent is expected to type a free-form string, which means typos silently create orphan assignments. No autocomplete, no validation. The DSL clearly declares it as a ref User field. |
| **EX-009** | 213 | simple_task/member | `date` + `ref Person` | `/app/task/create` Due Date field is `<input id="field-due_date">` — no calendar picker. Assign To field is `<input id="field-assigned_to">` — no type-ahead search. Both widget contracts (widget-datepicker, widget-search-select) exist and are shipped. The form-field compiler is not reaching them for these field types in this example app. |
| **EX-029** | 221 | support_tickets/customer | `ref User` (Assigned To) | Create Ticket form exposes the Assigned To field to the customer persona as a plain text input — same mechanism as EX-006, different persona. Customer shouldn't see this field at all (persona-level gap, covered by gap doc #2), but even if they should, rendering as plain text is the same widget-selection defect. |
| **EX-041** | 223 | fieldtest_hub/tester | `ref Tester` | Log Test Session form includes a required Tester field rendered as `<input id="field-tester_id">`. Logged-in tester has to manually type their own UUID. Tester is a User-subtype entity. The `inject_current_user_refs` fix from #774 doesn't cascade to subtype entities (tracked separately), but even with the cascade this should render as a widget-search-select with the tester pre-selected. |

**Cross-cycle pattern**: 4 out of 4 concrete observations involve ref fields. EX-009 adds the date type as a second surface. The remaining typed-field cases (money, decimal, datetime, enum-with-format) haven't been observed yet because none of the probed apps exercise them in the right combinations — but the underlying framework path is the same, so they're likely affected too.

## Root cause hypothesis

The form-field template macro at `src/dazzle_page/templates/macros/form_field.html` is dispatched per-field by `src/dazzle_page/converters/template_compiler.py`'s form generation path. The dispatch uses some form of type-string → widget-name mapping. Three candidate mechanisms for the gap:

### 1. Widget dispatch table incomplete

The most likely cause: there's a `FIELD_TYPE_TO_WIDGET` mapping (or equivalent switch) somewhere in the compiler that covers some types but not others. If `ref` isn't in that table — or is mapped to a fallback `<input type="text">` instead of `widget-search-select` — every ref field silently degrades. Same for `date` if there's no `date → widget-datepicker` entry.

**Verify by**: `grep -rn 'widget-search-select\|widget-datepicker\|FIELD_TYPE_TO_WIDGET' src/dazzle_page/converters/template_compiler.py src/dazzle_page/templates/macros/form_field.html` and walk the switch.

### 2. Widget requires an `ir.FieldSpec` attribute that isn't being populated

The widget contract for `widget-search-select` likely needs the target entity name (to know what to fetch options from) and a display-field hint (to know what to show in the dropdown). If the compiler has the dispatch but the context passed to the widget macro is missing these fields, the widget might silently fall back to a plain input.

**Verify by**: inspecting what's actually emitted in the page HTML for a known ref field — if the `<input>` carries data-attributes that look widget-targeted (e.g. `data-widget="search-select"` but no `data-entity-ref`), that's this case.

### 3. DSL-level `widget:` override missing

If the DSL requires explicit `widget: search-select` annotations to activate the widget, and most example apps don't declare them, then the defect is DSL-level: the framework has the machinery but no default-on behaviour. The fix then is a default widget mapping in the compiler: `ref` → `widget-search-select`, `date` → `widget-datepicker`, etc.

**Verify by**: grep example app DSLs for `widget:` annotations. If none of them declare widgets but the ones that DO work (via some other path) suggest the default is "plain input unless overridden", the fix is to change the default.

### Likelihood ranking

Most likely: candidate **#1** (dispatch table incomplete / no default). Easy to verify with a single grep. If that's wrong, walk to #2 (context gap), then #3 (DSL default).

## Fix sketch

**Step 1 — verify the dispatch**. Grep the compiler for the widget dispatch logic. Find the switch/mapping.

**Step 2 — add missing mappings**. Likely one-line additions per field type:

```python
# src/dazzle_page/converters/template_compiler.py (or wherever the dispatch lives)
FIELD_TYPE_TO_WIDGET = {
    FieldTypeKind.DATE: "widget-datepicker",
    FieldTypeKind.DATETIME: "widget-datepicker",
    FieldTypeKind.MONEY: "widget-money",
    FieldTypeKind.DECIMAL: "widget-number",
    FieldTypeKind.REF: "widget-search-select",  # context: ref_entity, display_field
    ...
}
```

**Step 3 — propagate the context**. For ref widgets, the template macro needs `ref_entity` (to know what collection to fetch) and ideally a display-field hint. If the compiler already has this on the FieldSpec, wire it through to the widget's data attributes.

**Step 4 — regression tests**. One test per widget class: a generated entity with each field type, verify the rendered HTML contains the widget's distinctive element (e.g. `<input data-widget="search-select" data-entity-ref="User">`) rather than a plain `<input type="text">`.

**Step 5 — cross-app verification**. Boot each of the 5 example apps, hit their create/update pages, grep the rendered HTML for the 4 cases that observations flagged. All 4 should now render as widgets.

## Blast radius

**Directly affected** (cross-cycle observed): support_tickets, simple_task, fieldtest_hub — 3 of 5 example apps.

**Likely affected** (not yet observed but same code path): contact_manager, ops_dashboard, and every DSL app with ref or date fields.

**By field type**:
- `ref` — extremely common, used wherever one entity links to another. Every DSL in the example fleet has multiple ref fields.
- `date`, `datetime` — common in any workflow-heavy app.
- `money`, `decimal` — common in finance/commerce shapes.
- `enum` — may already work (needs verification). Selects are simpler to generate.

**By blast radius class**: high. A form-generation defect affects every user interaction with form surfaces, which is the primary touchpoint for most SaaS apps.

## Open questions

1. Where is the widget dispatch actually implemented? `template_compiler.py` is the obvious starting point, but it may delegate to a macro system or helper module.
2. Does the widget system require any runtime JS registration beyond the vendored library bundles? If so, is that registration per-field or global?
3. Are there DSL-level `widget:` annotations in any of the example apps that DO work correctly? If yes, that's the "working" baseline to compare against.
4. Does the `form-field` ux-architect contract (UX-017) specify the widget-dispatch behaviour, or is it silent on this question? Worth re-reading the contract doc before fixing.

## Recommended follow-up

- **Next `finding_investigation` cycle** — target EX-009 (simple_task date + ref field). Small scope, clear symptom, two widget types in one investigation. Apply the cycle 229 "try the real thing" heuristic: inspect the rendered HTML at the HTTP layer first, then trace the compiler dispatch from there. Expected duration: 30-45 minutes.
- **After the first widget-dispatch fix lands**, re-run cycles 213/221/223 (or equivalently, use `form_submit` from cycle 229 against the affected create forms) to verify widgets now render. Close EX-006, EX-009, EX-029, EX-041 as FIXED.
- **EX-041 has a secondary defect** that the widget-selection fix alone doesn't address: the `inject_current_user_refs` cascade from #774 should walk from `ref Tester` → `Tester.user: ref User` and pre-fill the widget value with the current user's Tester record. That's a small extension to the existing `inject_current_user_refs` helper. Best done in the same cycle as the widget-selection fix.
