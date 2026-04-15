# Framework Gap — Silent Form Submit

**Status:** Open
**Synthesized:** Cycle 224 (framework_gap_analysis)
**Contributing cycles:** 201, 217, 222, 223
**Evidence weight:** 5 observations across 4 apps, 1 partially-fixed (#774)

---

## Problem statement

When a create form submits and the backend rejects the payload for **any reason other than a missing `created_by` ref User**, the rejection is completely invisible to the user. The form stays on the same URL, shows no inline validation, no toast, no field highlighting, and no state-changed signal. The user's typed content survives or disappears non-deterministically (at least one subagent run saw a `-999` numeric value vanish without a trace).

The v0.55.33 fix for #774 (`inject_current_user_refs` in `src/dazzle_back/runtime/route_generator.py`) closed **one specific cause** — missing FK values for required `ref User` fields where the current user is a legitimate default. But the broader "silent submit" class is a framework-wide gap in **error response surfacing** from FastAPI 422 responses back to the HTMX form. The issue recurs across apps, personas, and entity types, with at least four distinct root causes.

## Evidence

| Row | Cycle | App / Persona | Page | Observation |
|---|---|---|---|---|
| **EX-007** (→#774) | 201 | support_tickets/agent | `/app/ticket/create` | Empty-submit silent fail. **Root cause:** missing `created_by: ref User` FK injection. Fixed in v0.55.33 via `inject_current_user_refs`. |
| **EX-018** | 217 | fieldtest_hub/engineer | `/app/device/create` | 1000-character device name. **Root cause (suspected):** server rejects on `str(N)` max_length validation; the rejection is a 422 that never reaches the form template. |
| **EX-034** | 222 | ops_dashboard/admin | `/app/system/create` | Typed name, submit silent. **Root cause:** unverified; either #778 User-bridge recurrence or same 422-not-surfaced mechanism as EX-018. |
| **EX-039** | 223 | fieldtest_hub/tester | `/app/issuereport/create` + `/app/testsession/create` | Empty required fields + negative numeric. No inline markers, no toast. **Root cause:** Pydantic `field_required` + `greater_than_equal` validators raise 422 but the form never re-renders with field-level error indicators. |
| **EX-041** | 223 | fieldtest_hub/tester | `/app/testsession/create` | Required 'Tester' FK rendered as plain text input requiring user to type their own UUID. **Root cause:** `inject_current_user_refs` (from #774) only targets `ref User`; it doesn't cascade to User-subtype entities like `Tester`. |

## Root cause hypothesis

Three framework-layer mechanisms are missing or incomplete:

### 1. Systematic 422 error surfacing for HTMX form submits

FastAPI's `Request Validation Error` handler returns a 422 JSON body by default. Dazzle's HTMX integration at `src/dazzle_back/runtime/route_generator.py` has partial wiring for `hx-target-422` (the HTMX response-targets extension, cite needed) but the mechanism is **per-endpoint opt-in, not per-app default**. When the opt-in is missing, the HTMX client receives a 422 response with a JSON body it has no template for, and silently does nothing.

**Fix direction:** Make 422-error-surfacing the framework default. Every generated create/update route handler should register an exception handler that, when the request is HTMX, returns a rendered HTML fragment containing the form re-populated with its submitted values, with per-field error markers on each Pydantic validation error. The fragment targets the form container via `hx-reswap: outerHTML` or equivalent. This is a single change in `create_create_handler` / `create_update_handler` at `src/dazzle_back/runtime/route_generator.py` that cascades to every entity.

### 2. `inject_current_user_refs` cascade through User-subtype entities

EX-041 shows the #774 fix doesn't match `ref Tester` (Tester is a User-subtype entity in fieldtest_hub's DSL). The helper currently matches only literal `ref User`. When a DSL declares a domain-specific actor entity that has a `ref User` back-reference (e.g., `Tester` → `user: ref User`), the create form should still auto-inject the current user via the transitive relationship.

**Fix direction:** Extend `inject_current_user_refs` to follow the entity ref graph one hop — if the required field is `ref <Entity>` and `<Entity>` has a unique `ref User` field, resolve the current user to the matching `<Entity>` row and inject that instead. Falls back cleanly (if no such row exists, surface a proper error instead of silent failure).

### 3. Pre-submit validation mirroring

Pydantic validation runs server-side on submit. The client-side HTML5 `required` attribute catches *some* empty-field cases but not enum placeholders, `greater_than_equal`, or `max_length`. The form-field template compiler could emit client-side `pattern`, `minlength`, `maxlength`, `min`, `max` attributes matching the Pydantic schema's validators, surfacing most validation failures before submit hits the server at all.

**Fix direction:** In `src/dazzle_ui/converters/template_compiler.py`, when rendering a form field, consult the Pydantic model's field `FieldInfo` for `min_length`/`max_length`/`ge`/`le` metadata and emit matching HTML attributes. This is a pure additive change — doesn't replace server-side validation, just shifts easy rejections left.

## Fix sketch (one change addresses the most observations)

**Primary fix — (1) above.** A framework-default 422 handler for HTMX create/update routes that re-renders the form with Pydantic validation errors mapped to field markers. This alone closes EX-018, EX-034 (if not also a #778 recurrence), EX-039, and improves EX-041 from "silent" to "explicit error message even if the fix for the cascade is deferred".

```python
# src/dazzle_back/runtime/route_generator.py — inside create_create_handler
@route.exception_handler(RequestValidationError)
async def _htmx_validation_handler(request: Request, exc: RequestValidationError):
    if not _is_htmx_request(request):
        return JSONResponse({"detail": exc.errors()}, status_code=422)
    # Re-render form with submitted values + per-field errors
    field_errors = {e["loc"][-1]: e["msg"] for e in exc.errors() if len(e["loc"]) > 0}
    return render_fragment(
        "fragments/form_with_errors.html",
        form=input_schema,
        values=await request.form(),
        errors=field_errors,
        endpoint_url=str(request.url),
    )
```

Plus a new `src/dazzle_ui/templates/fragments/form_with_errors.html` that re-renders each field with its prior value and any `errors[field_name]` as an inline error marker.

## Blast radius

**Confirmed affected apps:** support_tickets (EX-007), fieldtest_hub (EX-018/039/041), ops_dashboard (EX-034)
**Likely affected:** contact_manager, simple_task (no observations yet because cycles 213/218 didn't stress create forms with deliberately-invalid inputs)
**Personas:** every persona that uses create forms — universal

Every Dazzle app that has a create surface is affected the moment a user types invalid input. That's every Dazzle app.

## Open questions

1. Is the `hx-target-422` response-targets wiring currently present in any form? A quick `grep -r "hx-target-422" src/dazzle_ui/templates/` will show the current state.
2. Does EX-034 (ops_dashboard/admin system create) have the same mechanism as EX-039, or is it a distinct #778 User-bridge recurrence? Needs a `finding_investigation` cycle to reproduce locally and trace.
3. What's the contract for client-side `pattern=` on enum selects? Does the framework already emit HTML5 `required` on required fields? Template compiler inspection needed.

## Recommended follow-up

- **Immediately:** File a GitHub issue titled "Framework-default 422 error surfacing for HTMX create/update forms" with this gap doc as the body. Tag as `framework-gap` and link all 5 contributing EX rows.
- **Next `finding_investigation` cycle:** Reproduce EX-034 on ops_dashboard to confirm whether it's a duplicate of EX-039 (suggesting the single fix closes both) or a new #778 recurrence (suggesting the QA auth-bridge gap needs independent attention).
- **After the primary fix lands:** Re-run cycles 217/221/223 against the fixed framework and move the contributing EX rows to `FIXED→v0.55.XX` or `VERIFIED_FIXED` depending on the result.
