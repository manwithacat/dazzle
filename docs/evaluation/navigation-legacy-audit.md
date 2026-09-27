# Navigation fallback audit

**Date:** 2026-09-27
**Decision:** Remove the parallel app-sidebar model before 1.0, after giving
its remaining request states explicit `NavModel` behaviour.

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

The ownership pilot exposed a changing `PageContext.nav_items` order while the
actual persona and anonymous `NavModel` sidebars stayed equal. That did not
mean `nav_items` was dead. Reading the request paths shows where it still
renders and why the fallback survived the #1324 cutover.

| Request state | Current sidebar source | Finding |
|---|---|---|
| Authenticated user whose role matches a persona | Precomputed persona `NavModel` | The compiled `nav_items` and `nav_groups` copies are ignored for rendering. |
| Unauthenticated request with auth wired | Precomputed anonymous `NavModel` | The old anonymous lists are still constructed and mutated, despite the modern model winning. |
| App without auth wiring | Legacy `PageContext.nav_items` / `nav_groups` | `_inject_auth_context` deliberately leaves `nav_model` unset so the full declared nav remains visible. |
| Authenticated role with no persona match, including `admin` and `super_admin` | Legacy lists, including workspace curated groups | `_resolve_nav_model` returns `None`; using the anonymous model here previously hid admin navigation. |
| Route override shell without page-router dependencies | Empty sidebar frame | It has no precomputed nav models; this is a distinct host-context gap. |

The competing builders are `template_compiler.compile_appspec_to_templates`
for entity pages, `page_routes.create_page_routes` for workspace pages, and
`nav_builder` for the modern sidebar. `render.dispatch._build_sidebar_from_ctx`
still branches between the two representations. The `PageContext` carries
flat items, persona variants, anonymous variants, grouped variants, and a
`NavModel` simultaneously. This is actual maintenance and reasoning cost, not
just old naming. The pilot's module-order change was visible in the old lists
because they still derive from declaration order.

The clean break should make `NavModel` the sole app-sidebar input for every
request state. The work is:

1. Give no-auth apps an explicit unrestricted model. Define a role-aware model
   for authenticated users without a matching persona, including the platform
   admin groups; do not silently treat them as anonymous. Decide the access
   policy for any other unmatched role rather than inheriting a fallback.
2. Resolve one model in the page router for surface and workspace routes, and
   thread it through route-override shells where those shells need a sidebar.
   A missing model should be an explicit empty model or a configuration error,
   never an instruction to consult a second navigation representation.
3. Delete the old producers and fields (`nav_items`, `nav_by_persona`,
   `nav_items_anon`, `nav_groups`, and their variants) from app `PageContext`,
   the duplicate workspace builder, `_apply_anon_nav`, and the legacy branch of
   `_build_sidebar_from_ctx`. Replace tests that prove fallback precedence with
   tests for the four explicit request states above. Check entity and workspace
   HTML parity, admin reachability, and no anonymous leakage.

`SitePageContext.nav_items` and `SiteSpec` marketing navigation are a separate
site model; this audit makes no claim that they are obsolete. Mentions of
"legacy" in CSS or typed-fragment code often document historical markup
parity rather than an active alternate producer. Such comments are not a
reason by themselves to remove a working API. The live fallback described
above is the one that should be eliminated.
