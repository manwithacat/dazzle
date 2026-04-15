# Framework Gap — Silent Form Submit

**Status:** SUPERSEDED (cycle 229 investigation)
**Synthesized:** Cycle 224 (framework_gap_analysis)
**Superseded:** Cycle 229 (finding_investigation on EX-039)
**Contributing cycles:** 201, 217, 222, 223
**Evidence weight:** originally 5 observations; post-investigation, 3 of 5 are substrate artifacts, 1 was a real framework bug already fixed by #774, 1 is a distinct class (#774 cascade, tracked as EX-041)

---

## ⚠️ SUPERSEDED — cycle 229 investigation invalidated most of this gap doc

Cycle 229's end-to-end investigation of EX-039 revealed that **the framework's 422 HTML error-surfacing system already exists and works correctly**. At the HTTP layer, POSTing an invalid payload to any entity create endpoint returns a proper `422 Unprocessable Entity` response with a `[data-dazzle-error]` HTML fragment containing "Validation Error" + per-field messages ("device_id: Field required", etc.). The form template's `hx-target-422="#form-errors"` wiring is correct; HTMX's `response-targets` extension is loaded at `base.html:105`; the exception handler at the backend renders the right fragment.

**What actually caused the "silent submit" observations was a substrate bug**, not a framework gap:

1. The subagent's `action_type` / `action_click` multi-call pattern launches a fresh Playwright subprocess for each action. `storage_state` persists cookies but NOT in-page form state, so values filled in a prior `action_type` subprocess evaporate by the time the next `action_click` subprocess fires.
2. Consequently, every `action_click` submitted an **empty form**. HTML5 `required` attributes on the form's device_id/description inputs blocked empty submits entirely — **no POST ever reached the server**, `state_changed=false` was correctly reported, and no error appeared because no error was requested.
3. Even in non-required-field cases (EX-018's 1000-char device name, EX-039's -999 negative number), the test values evaporated the same way, so the server saw them as empty and the outcome was the same.
4. `action_observe` made it worse: it also launches a fresh subprocess and does `page.goto(last_url)`, which means any HTMX-swapped error content from an in-place swap is **discarded** on the next observe. Even if the framework had rendered an error in-place, observing it would have destroyed it.

**Framework-side, nothing was broken**. The gap this doc proposed to build (framework-default 422 handler re-rendering forms with field errors) already exists. The `inject_current_user_refs` fix for #774 remains real and correct — it addresses a specific FK auto-population gap that's orthogonal to the error-surfacing question.

### Post-investigation evidence classification

| Row | Original status | Cycle 229 verdict |
|---|---|---|
| EX-007 (→#774) | Real framework bug | **Still real** — #774 closed it. Specific cause (missing created_by ref User), fixed in v0.55.33. |
| EX-018 | Concerning | **SUSPECTED_FALSE_POSITIVE** — substrate artifact; needs re-verification with new `form_submit` action |
| EX-034 | Notable | **SUSPECTED_FALSE_POSITIVE** — same substrate class |
| EX-039 | Notable | **VERIFIED_FALSE_POSITIVE** — cycle 229 reproduced the real mechanism end-to-end |
| EX-041 | Notable | **Still real** — distinct class. The form exposes `ref Tester` (User-subtype) without auto-injecting; this is a cascade extension of #774 and should be closed by extending `inject_current_user_refs` to walk the ref graph. |

So the true residual "silent-form-submit"-like gaps are:
1. **EX-041** — `inject_current_user_refs` cascade to User-subtype entities (Tester → User back-ref). Small, well-scoped framework fix worth 15 min in a future cycle.
2. **Client-side validation mirroring** (proposed as Fix #3 in the original doc below) — still a latent UX improvement, but no longer motivated by a real defect. Hold until a fresh observation surfaces the need.

### Substrate fix shipped in cycle 229

Added new `form_submit` action to `src/dazzle/agent/playwright_helper.py`: navigates, fills all fields, clicks submit, and harvests error banner text — all in **one subprocess lifetime**, with a 250ms post-networkidle wait for HTMX to run its swap handler. This unblocks all future subagent form exploration, which was previously unable to observe form validation errors at all. Filed as **EX-043** with full trace.

### Takeaway for the /ux-cycle loop

This gap doc is a useful illustration of why the **synthesis cycle must be followed by at least one investigation cycle before a fix is attempted**. Cycle 224's gap analysis saw 5 observations pointing at the same symptom class and synthesized them into a framework-wide theme. That was a reasonable inference from the data — but the data itself was poisoned by a substrate bug that faked the symptom. A naïve implementation cycle following cycle 224 would have built the "framework-default 422 handler" that already existed, and then wondered why the observations kept recurring.

**Updated /ux-cycle skill heuristic for gap-analysis follow-through**: when a gap doc would require new framework infrastructure (vs. a helper swap or single-file edit), spend at least one investigation cycle **reproducing the defect end-to-end at the HTTP layer** (bypassing any subagent tooling) before committing to the infrastructure build. The "try the real thing" pattern from cycle 228 is the right general discipline.

---

## Original problem statement (retained for historical reference)

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
