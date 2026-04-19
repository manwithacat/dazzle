# Framework Gap — Error-Page Navigation Dead-End (v0.55.31 #776 Regression)

**Status:** RESOLVED (cycle 225 + cycle 258 retrospective confirmation)
**Synthesized:** Cycle 224 (framework_gap_analysis)
**Contributing cycles:** 223 (observation), 225 (fix shipped), 258 (retrospective)
**Evidence weight:** 1 observation that pointed at a shipped-fix regression. The hypothesised mechanism (HTMX boost intercept) turned out to be wrong — the actual cause was a DSL parser bug. This is exactly the class of wrong-hypothesis rescue Heuristic 1 was promoted to mandatory over in cycles 228-234.

## Retrospective verdict (cycle 258 review)

- **Hypothesis 1 (HTMX boost intercept)** — ruled out. Cycle 225 found the raw cause was elsewhere.
- **Hypothesis 2 (server-side redirect loop)** — close but not quite. Cycle 225 found the loop existed but its root was upstream of route resolution.
- **Hypothesis 3 (Alpine handler)** — ruled out.
- **Real root cause** — DSL parser bug at `scenario.py:407`. `_parse_string_list` only handled inline comma-separated form; multi-line indented form silently returned empty list AND left MINUS tokens unconsumed. The cascade: tester's `goals` list parsed as empty → the unknown-field loop in `parse_persona` consumed `default_workspace` as if it were another goal entry → tester's `default_workspace` declaration was silently dropped → `_root_redirect` fell back to `workspaces[0]` = engineering_dashboard (engineer's workspace) → 403 for tester → "Go to Dashboard" retriggered the same fallback → dead-end loop.
- **Cycle 225 fix**: rewrote `_parse_string_list` to handle both inline and multi-line indented forms. 2 new regression tests pin the parser.

The gap doc's hypothesis framing was a teaching moment. Every candidate was "too close to the observed symptom" — all three looked for a template/template-consumer mechanism. The actual defect lived two layers up, in the parser that produced the AppSpec that the template/templates read from. This is why Heuristic 1 (reproduce at the lowest layer that can exhibit the defect) exists. Without cycle 225's raw-layer reproduction, we'd have shipped template changes that didn't address the real bug.

## Subsequent work (not part of the original observation but worth noting)

The 404 and 403 templates have been substantively evolved since cycle 225:
- **v0.57.79 (#808)** — 403 page renders a role-disclosure panel (entity, operation, allowed-for, current-roles) instead of a bare "Forbidden".
- **v0.57.85 (#811)** — 404 page renders a "Did you mean:" suggestion card for plural/singular/typo/dashboard-alias drift.
- **v0.57.88 (#815)** — `/app/<plural>` 301-redirects to `/app/<singular>` so plural URLs never produce a 404 in the first place.
- **v0.57.89 (#816)** — `_page_handler` emits `HX-Trigger-After-Swap: dz:titleUpdate` on every hx-boost partial so the browser tab title tracks the destination page.
- **Cycle 257 (UX-050)** — formalised the 404 page as a governed component contract at `~/.claude/skills/ux-architect/components/app-404.md`.

None of these invalidate the cycle 225 fix; they build on it. The navigation-dead-end gap is fully resolved. The error-page UX surface continues to evolve but no new defect class has emerged in 33 cycles.

## Original problem statement (preserved for reference)

---

## Problem statement

The v0.55.31 fix for #776 introduced in-app error shell templates (`src/dazzle_ui/templates/app/404.html` and `app/403.html`) that extend the authenticated app layout and include back-to-list affordances. The templates render correctly — the 403 page displayed during cycle 223's tester run shows "Back to Dashboard" and "Go to Dashboard" links with `href="/app"`, exactly as intended.

**But the links do not navigate.** When the subagent clicked them, the helper returned `state_changed: false` and the browser stayed on the 403 page. The affordances look clickable but produce no navigation.

This is a regression in the user-visible sense: before #776, error pages rendered the marketing chrome and a "Go Home" button that at least navigated (to the wrong place, but it navigated). After #776, the error pages render in-app chrome with "Back to Dashboard" buttons that don't navigate at all. The previous failure mode was *wrong destination*; the current failure mode is *no destination*, which is worse because it reads as "the app is frozen".

## Evidence

| Row | Cycle | App / Persona | Observation |
|---|---|---|---|
| **EX-035** | 223 | fieldtest_hub/tester | On `/app/workspaces/engineering_dashboard` (403 for tester), both "Back to Dashboard" and "Go to Dashboard" links point at `/app`. Clicking either produces `state_changed: false`. Multiple attempts confirmed. The in-app error shell renders correctly but the anchors are inert. |

## Root cause hypothesis

Three candidate mechanisms, ranked by likelihood:

### 1. HTMX boost intercept (most likely)

The app shell layout `src/dazzle_ui/templates/layouts/app_shell.html` very likely has `hx-boost="true"` set at the `<body>` or a wrapping container level, so all `<a>` tags inside it are intercepted by HTMX and converted to `hx-get` ajax requests. When the user is on a 403 error page *inside* the app shell, clicking the back-affordance triggers an HTMX ajax GET to `/app`. The backend responds with the `/app` workspace redirect (HTMX-aware or not), but something in the response pipeline prevents the browser from actually swapping in the new content — possibly:

- The response uses `HX-Redirect` header but HTMX's redirect handling is broken on error-state pages
- The response body is HTML but HTMX's swap strategy defaults to innerHTML of the wrong target element
- The 403 handler itself returns with an HX-specific header that confuses follow-up navigations

**Verify by:** add `hx-boost="false"` to the error template's back-link and re-run. If the click navigates, HTMX boost is the culprit.

### 2. Server-side redirect loop

If the user hits `/app` and the server returns a redirect back to the default workspace `/app/workspaces/<whatever>`, and that workspace is the same 403'd workspace (`engineering_dashboard` for tester — whose real default is `tester_dashboard` but which 403'd because the redirect resolver used the *wrong* default), then the click produces a 302→403→redirect loop that HTMX follows silently and the browser ends up back on the same page.

**Verify by:** hit `/app` with curl + the tester session cookie and inspect the redirect chain. If it loops, the fix is in the `_resolve_persona_default_workspace` logic, not the error template.

### 3. Template-level link handler

Extremely unlikely but possible: an Alpine controller attached to the app shell is listening for click events on anchors and preventing default for links that don't start with a recognised prefix. If the anchor has `href="/app"` but the controller expects `href="/app/workspaces/..."`, the handler swallows the click.

**Verify by:** grep Alpine controllers in `src/dazzle_ui/runtime/static/js/dz-alpine.js` for anchor click handlers.

### Likelihood ranking

Candidate 1 (HTMX boost intercept) is by far the most likely — the framework defaults to HTMX-boosted navigation, and error-state pages are exactly the kind of "unusual response shape" where HTMX handling often goes wrong.

## Fix sketch (minimum change under hypothesis 1)

In `src/dazzle_ui/templates/app/404.html` and `app/403.html`, mark the back-affordance links as **opted out of HTMX boost** so they behave as plain browser navigations:

```html
<!-- Before -->
<a href="/app" class="btn btn-primary">Back to Dashboard</a>

<!-- After -->
<a href="/app" hx-boost="false" class="btn btn-primary">Back to Dashboard</a>
```

This is a two-line template edit (one per file). It does not require any framework code changes. It does require verification via reproduction — which is exactly what the next `finding_investigation` cycle should do.

**If hypothesis 2 turns out to be the real cause**, the fix is in `src/dazzle_back/runtime/exception_handlers.py` or wherever the in-app 403/404 handler routes through — specifically, in how it computes the "back to dashboard" URL. The current template hardcodes `/app`, but the fix might need to compute the persona's actual default workspace URL and use that.

## Blast radius

**Confirmed affected apps:** fieldtest_hub (EX-035)
**Likely affected:** every Dazzle app with authenticated error routes — that's all 5 example apps.
**Severity upgrade rationale:** any persona who hits a 403/404 while logged in is **stuck on the error page** until they manually re-type a URL. For a tester persona with `default_workspace = tester_dashboard`, that's a usability cliff; for any persona that encounters a stale link or fat-fingered URL, the recovery path is "close tab, reopen app" — the worst UX outcome outside actual data loss.

This is the kind of defect that's invisible in automated tests (contract verification doesn't click back-affordances) and rare in manual testing (who deliberately lands on a 403 page?) but immediately painful when a real user hits it.

## Open questions

1. Is `hx-boost` set at the app-shell level? Grep `src/dazzle_ui/templates/layouts/app_shell.html` and `base.html`.
2. What does `/app` GET actually return with a valid session cookie? Is it a 302 to the persona's default workspace, or does it render a routing page? If the former, does HTMX handle the 302 correctly?
3. How do **other** anchor links in the app shell navigate successfully? What's the mechanism that distinguishes the sidebar links (which work) from the error-page back-links (which don't)?

## Recommended follow-up

- **Priority: HIGH.** This is a shipped-fix regression with a well-defined reproduction path. A single `finding_investigation` cycle can confirm/deny each hypothesis in well under 30 minutes.
- **Immediately:** Next cycle should be a `finding_investigation` targeting EX-035. Boot fieldtest_hub, log in as tester, navigate to `/app/workspaces/engineering_dashboard`, inspect the HTML + HTMX attributes on the error page, try clicking with and without `hx-boost="false"`.
- **If hypothesis 1 confirmed:** Two-line template edit + `/ship` as a patch release. Probably v0.55.36.
- **If hypothesis 2 or 3:** Follow the trace, write a new gap doc with the actual mechanism, file a GitHub issue.
- **After the fix:** Re-run cycles 217/218/223 to verify the original #776 shell still works AND the new fix doesn't break HTMX-boosted navigation elsewhere.

## Cross-gap signal

This gap intersects with the **persona-unaware-affordances** gap doc in one specific way: the tester persona is hitting a 403 on `engineering_dashboard` because the redirect logic *assumed* engineering_dashboard was the persona default (when the real default is `tester_dashboard`). That's a persona-default-workspace resolution bug — separate from the anchor-intercept bug that's the subject of this doc, but the two compound into a "tester lands on wrong workspace, gets 403, can't escape" experience. Fixing just one of the two leaves the composite defect only half-fixed.
