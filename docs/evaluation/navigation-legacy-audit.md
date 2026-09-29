# Navigation fallback audit

**Date:** 2026-09-27 (audit revised after the clean break landed)
**Decision:** Remove the parallel app-sidebar model before 1.0, after giving
its remaining request states explicit `NavModel` behaviour. **Status: landed.**

**Implementation:** The app shell now consumes only `NavModel`. The page router
precomputes persona, anonymous, unrestricted, and admin-role models. Unknown
authenticated roles receive the anonymous-safe model. Surface, workspace, and
experience pages use that same representation; route override shells receive
an explicit empty model until they have page-router dependencies. The old
`PageContext` navigation lists, compiler and workspace list builders, and
render fallback were removed.

This change reduces the historical model-driven failure mode of opaque runtime
traceability: a sidebar link has one `NavLink.entity` target and a reconciled
route back to the AppSpec. The live detector is the navigation builder and
request-state test suite, including anonymous leakage and admin reachability.
The remaining limitation is that route override shells show an empty sidebar;
their handler lacks the page router's precomputed models. They do not fall back
to a second representation.

The ownership pilot that prompted this audit exposed a changing `PageContext.nav_items`
order while the actual persona and anonymous `NavModel` sidebars stayed equal. That did
not mean `nav_items` was dead. Reading the request paths showed where it still rendered
and why the fallback survived the #1324 cutover.

| Request state | Sidebar source | Finding |
|---|---|---|
| Authenticated user whose role matches a persona | Precomputed persona `NavModel` | Resolved in the page router before the handler runs. |
| Unauthenticated request with auth wired | Precomputed anonymous `NavModel` | Explicit model; no post-hoc mutation of a parallel list. |
| App without auth wiring | Precomputed unrestricted `NavModel` | Explicit model, so a no-auth app keeps its full declared nav. |
| Authenticated role with no persona match, including `admin` and `super_admin` | Role-aware `NavModel` including platform admin groups | No silent anonymous demotion. |
| Route override shell without page-router dependencies | Empty sidebar frame | Remaining gap — see below. |

`render.dispatch._build_sidebar_from_ctx` consumes `nav_model` only; when it is `None`
it renders an explicit empty sidebar rather than consulting a second representation.
The competing producers are gone: `PageContext` no longer carries `nav_items`,
`nav_by_persona`, `nav_items_anon`, or `nav_groups`, `_apply_anon_nav` no longer exists,
and the duplicate workspace list builder and legacy sidebar branch were deleted. What
remains in the tree is a separate concern — `SitePageContext.nav_items` and the
`SiteSpec` marketing model, plus `ws.nav_groups`, which is a *workspace declaration*
field feeding `nav_builder`, not the retired app `PageContext` lists.

The clean break that has since landed made `NavModel` the sole app-sidebar input for
every request state. The work that carried it out:

1. Gave no-auth apps an explicit unrestricted model and a role-aware model for
   authenticated users without a matching persona, including the platform admin
   groups, so an unmatched role never inherits an anonymous fallback. ✅
2. Resolved one model in the page router for surface and workspace routes and threaded
   it through route-override shells. A missing model is an explicit empty model, never
   an instruction to consult a second navigation representation. ✅ (shells still need
   the page-router dependency threaded — see below)
3. Deleted the old producers and fields, and replaced the fallback-precedence tests with
   tests for the explicit request states, including entity/workspace HTML parity, admin
   reachability, and no anonymous leakage. ✅

**Remaining limitation.** Route override shells still render an empty sidebar frame
because their handler has no access to the page router's precomputed models. This is a
host-context wiring gap, not a second navigation representation: the fix is to thread
`NavModel` into those shells, not to reintroduce a fallback.

`SitePageContext.nav_items` and `SiteSpec` marketing navigation are a separate site
model; this audit makes no claim that they are obsolete. Mentions of "legacy" in CSS or
typed-fragment code often document historical markup parity rather than an active
alternate producer. Such comments are not a reason by themselves to remove a working
API.
