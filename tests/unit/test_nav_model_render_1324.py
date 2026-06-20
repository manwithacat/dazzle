"""#1324 slice 3b: render the sidebar from the precomputed per-persona NavModel.

Three seams under test:

1. ``_sidebar_from_nav_model`` — maps a ``NavModel`` to a typed ``Sidebar``:
   flat (empty-label) groups become top-level ``Sidebar.items``; curated
   (titled) groups become collapsible ``Sidebar.groups``; ``current_route``
   drives ``active``.
2. ``_build_sidebar_from_ctx`` branches on ``ctx.nav_model`` BEFORE the legacy
   ``nav_items``/``nav_groups`` path — proving the cutover and the anti-drift
   invariant (the same NavModel yields the same Sidebar regardless of which
   page-type's PageContext carries it).
3. ``_resolve_nav_model`` + ``_inject_auth_context`` — the request hook sets
   ``ctx.nav_model`` to the matching persona's nav (or the anon nav).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dazzle.http.runtime.page_routes import _inject_auth_context, _resolve_nav_model
from dazzle.page.converters.nav_builder import NavGroup, NavLink, NavModel
from dazzle.render.context import NavItemContext, PageContext
from dazzle.render.dispatch import _build_sidebar_from_ctx, _sidebar_from_nav_model

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# A curated persona nav: one titled group (collapsible) + one flat group.
_PERSONA_NAV = NavModel(
    groups=(
        NavGroup(
            label="Operations",
            icon="cog",
            collapsed=False,
            links=(
                NavLink(label="Tickets", route="/list/Ticket", icon="ticket"),
                NavLink(label="Incidents", route="/list/Incident"),
            ),
        ),
        # Flat (empty-label) group → top-level items.
        NavGroup(
            label="",
            icon=None,
            collapsed=False,
            links=(NavLink(label="Home", route="/workspaces/home"),),
        ),
    ),
    auto_discovered=False,
)

# An anon nav: a single flat group (the auto-discover shape).
_ANON_NAV = NavModel(
    groups=(
        NavGroup(
            label="",
            icon=None,
            collapsed=False,
            links=(NavLink(label="Public", route="/workspaces/public"),),
        ),
    ),
    auto_discovered=True,
)


# ---------------------------------------------------------------------------
# 1. _sidebar_from_nav_model mapping
# ---------------------------------------------------------------------------


def test_flat_group_becomes_sidebar_items() -> None:
    ctx = PageContext(page_title="x", current_route="/workspaces/home")
    sidebar = _sidebar_from_nav_model(_PERSONA_NAV, ctx)

    item_routes = {i.href.value for i in sidebar.items}
    assert item_routes == {"/workspaces/home"}
    # The flat link matching current_route is marked active.
    assert sidebar.items[0].active is True


def test_titled_group_becomes_collapsible_nav_group() -> None:
    ctx = PageContext(page_title="x", current_route="/list/Ticket")
    sidebar = _sidebar_from_nav_model(_PERSONA_NAV, ctx)

    assert len(sidebar.groups) == 1
    grp = sidebar.groups[0]
    assert grp.label == "Operations"
    assert grp.icon == "cog"
    child_routes = [c.href.value for c in grp.items]
    assert child_routes == ["/list/Ticket", "/list/Incident"]
    # Active state propagates inside groups too.
    assert grp.items[0].active is True
    assert grp.items[1].active is False


def test_link_icon_threads_through() -> None:
    ctx = PageContext(page_title="x")
    sidebar = _sidebar_from_nav_model(_PERSONA_NAV, ctx)
    tickets = sidebar.groups[0].items[0]
    assert tickets.icon == "ticket"


def test_header_carries_app_name() -> None:
    ctx = PageContext(page_title="x", app_name="My App")
    sidebar = _sidebar_from_nav_model(_PERSONA_NAV, ctx)
    # header is a Text primitive carrying the app name.
    assert getattr(sidebar.header, "body", None) == "My App"


def test_empty_nav_model_yields_empty_sidebar() -> None:
    ctx = PageContext(page_title="x")
    sidebar = _sidebar_from_nav_model(NavModel(groups=(), auto_discovered=True), ctx)
    assert sidebar.items == ()
    assert sidebar.groups == ()


# ---------------------------------------------------------------------------
# 2. _build_sidebar_from_ctx branches on nav_model + anti-drift invariant
# ---------------------------------------------------------------------------


def test_nav_model_takes_precedence_over_legacy_nav_items() -> None:
    """When nav_model is set, the legacy nav_items path is NOT consulted."""
    ctx = PageContext(
        page_title="x",
        current_route="/list/Ticket",
        # Legacy producers populated with DIFFERENT data — must be ignored.
        nav_items=[NavItemContext(label="Legacy", route="/legacy")],
        nav_model=_PERSONA_NAV,
    )
    sidebar = _build_sidebar_from_ctx(ctx)
    item_routes = {i.href.value for i in sidebar.items}
    # Only the nav_model's flat link, never the legacy "/legacy".
    assert "/legacy" not in item_routes
    assert item_routes == {"/workspaces/home"}
    assert sidebar.groups[0].label == "Operations"


def test_legacy_path_used_when_nav_model_absent() -> None:
    """No nav_model → fall back to the legacy nav_items producer (dead-code
    fallback that stays until a later removal task)."""
    ctx = PageContext(
        page_title="x",
        nav_items=[NavItemContext(label="Legacy", route="/legacy")],
    )
    assert ctx.nav_model is None
    sidebar = _build_sidebar_from_ctx(ctx)
    assert {i.href.value for i in sidebar.items} == {"/legacy"}


def test_workspace_and_entity_pages_render_identical_sidebar_from_same_nav_model() -> None:
    """The anti-drift invariant (#1324): both page types render the SAME
    sidebar because both source it from the persona's precomputed NavModel.

    We model the two page types as two distinct PageContexts (a workspace
    page and an entity-list page) that carry the SAME nav_model + route, and
    assert their built Sidebars are equal — frozen dataclasses compare by
    value, so equality is exact structural identity.
    """
    workspace_ctx = PageContext(
        page_title="Home",
        app_name="App",
        current_route="/list/Ticket",
        view_name="home",
        nav_model=_PERSONA_NAV,
    )
    entity_ctx = PageContext(
        page_title="Tickets",
        app_name="App",
        current_route="/list/Ticket",
        view_name="ticket_list",
        # Legacy producers differ between the two paths historically — this is
        # exactly the drift the cutover removes. nav_model is the shared source.
        nav_items=[NavItemContext(label="Drifted", route="/drifted")],
        nav_model=_PERSONA_NAV,
    )
    ws_sidebar = _build_sidebar_from_ctx(workspace_ctx)
    entity_sidebar = _build_sidebar_from_ctx(entity_ctx)

    assert ws_sidebar.items == entity_sidebar.items
    assert ws_sidebar.groups == entity_sidebar.groups


# ---------------------------------------------------------------------------
# 3. _resolve_nav_model + request-hook wiring
# ---------------------------------------------------------------------------


def _deps(persona_navs: dict[str, NavModel], anon_nav: NavModel | None) -> SimpleNamespace:
    return SimpleNamespace(persona_navs=persona_navs, anon_nav=anon_nav)


# ---------------------------------------------------------------------------
# 2b. boot-time route reconciliation (placeholder routes → runtime routes)
# ---------------------------------------------------------------------------


def test_reconcile_maps_entity_and_workspace_routes_to_runtime_shape() -> None:
    """#1324 slice 3b: nav_builder emits placeholder routes (/list/<Entity>,
    /workspaces/<name>); the renderer reconciles them to the real runtime
    routes (<app_prefix>/<slug>, <app_prefix>/workspaces/<name>) so active-
    state highlighting (current_route == href) works."""
    from dazzle.core import ir
    from dazzle.core.ir.workspaces import WorkspaceSpec
    from dazzle.http.runtime.page_routes import _reconcile_nav_model

    appspec = ir.AppSpec(
        name="app",
        title="App",
        version="0.1.0",
        domain=ir.DomainSpec(entities=[]),
        surfaces=[],
        workspaces=[WorkspaceSpec(name="ops_home", title="Ops")],
        personas=[],
    )
    model = NavModel(
        groups=(
            NavGroup(
                label="",
                icon=None,
                collapsed=False,
                links=(
                    # entity target (snake_case → kebab slug)
                    NavLink(
                        label="System Health", route="/list/SystemHealth", entity="SystemHealth"
                    ),
                    # workspace target
                    NavLink(label="Ops", route="/workspaces/ops_home", entity="ops_home"),
                ),
            ),
        ),
        auto_discovered=True,
    )
    reconciled = _reconcile_nav_model(appspec, "/app", model)
    routes = {link.route for link in reconciled.groups[0].links}
    assert routes == {"/app/systemhealth", "/app/workspaces/ops_home"}


def test_resolve_nav_model_matches_persona_by_role() -> None:
    deps = _deps({"engineer": _PERSONA_NAV}, _ANON_NAV)
    assert _resolve_nav_model(deps, ["role_engineer"], authenticated=True) is _PERSONA_NAV


def test_resolve_nav_model_authed_unmatched_role_returns_none() -> None:
    """#1324 regression fix: an AUTHENTICATED user whose roles match no persona
    must fall through to the legacy curated nav (return None), NOT collapse to
    the anon nav. ``admin``/``super_admin`` are role NAMES, not persona entries,
    so the admin platform workspace has no persona_navs key — pre-fix it got the
    anon visitor's nav, hiding the curated admin nav_groups."""
    deps = _deps({"engineer": _PERSONA_NAV}, _ANON_NAV)
    assert _resolve_nav_model(deps, ["role_admin"], authenticated=True) is None
    assert _resolve_nav_model(deps, ["role_unknown"], authenticated=True) is None


def test_resolve_nav_model_unauthenticated_falls_back_to_anon() -> None:
    """Genuinely-unauthenticated requests get the anon nav — never the full nav."""
    deps = _deps({"engineer": _PERSONA_NAV}, _ANON_NAV)
    assert _resolve_nav_model(deps, [], authenticated=False) is _ANON_NAV
    assert _resolve_nav_model(deps, None, authenticated=False) is _ANON_NAV


def test_resolve_nav_model_no_anon_precomputed_returns_none() -> None:
    """Older config without a precomputed anon nav → None (legacy path builds it)."""
    deps = _deps({"engineer": _PERSONA_NAV}, None)
    assert _resolve_nav_model(deps, [], authenticated=False) is None


def _make_prc(
    *,
    get_auth_context: object | None,
    persona_navs: dict[str, NavModel],
    anon_nav: NavModel | None,
) -> SimpleNamespace:
    ctx = PageContext(page_title="x")
    deps = SimpleNamespace(
        get_auth_context=get_auth_context,
        entity_cedar_specs=None,
        route_entity=None,
        persona_navs=persona_navs,
        anon_nav=anon_nav,
    )
    return SimpleNamespace(ctx=ctx, deps=deps, request=MagicMock(), auth_ctx=None)


@pytest.mark.asyncio
async def test_inject_authenticated_persona_sets_persona_nav_model() -> None:
    user = SimpleNamespace(email="e@x", username="e", roles=["role_engineer"], is_superuser=False)
    auth_ctx = SimpleNamespace(is_authenticated=True, user=user, preferences={})

    def _resolver(_req: object) -> SimpleNamespace:
        return auth_ctx

    prc = _make_prc(
        get_auth_context=_resolver,
        persona_navs={"engineer": _PERSONA_NAV},
        anon_nav=_ANON_NAV,
    )
    await _inject_auth_context(prc)
    assert prc.ctx.nav_model is _PERSONA_NAV


@pytest.mark.asyncio
async def test_inject_unauthenticated_sets_anon_nav_model() -> None:
    def _resolver(_req: object) -> SimpleNamespace:
        return SimpleNamespace(is_authenticated=False, user=None)

    prc = _make_prc(
        get_auth_context=_resolver,
        persona_navs={"engineer": _PERSONA_NAV},
        anon_nav=_ANON_NAV,
    )
    await _inject_auth_context(prc)
    assert prc.ctx.nav_model is _ANON_NAV


@pytest.mark.asyncio
async def test_inject_no_auth_wiring_leaves_nav_model_unset() -> None:
    """No auth wiring = "developer opted out of access control". There's no
    session to resolve a persona from and no gates to enforce, so the hook
    leaves ``nav_model`` unset and the sidebar falls back to the full legacy
    declared nav — NOT the anon nav (a strict subset that would wrongly hide
    workspaces in an app with no auth fixture)."""
    prc = _make_prc(
        get_auth_context=None,
        persona_navs={"engineer": _PERSONA_NAV},
        anon_nav=_ANON_NAV,
    )
    await _inject_auth_context(prc)
    assert prc.ctx.nav_model is None


@pytest.mark.asyncio
async def test_inject_authenticated_unmatched_role_falls_back_to_legacy_nav() -> None:
    """#1324 regression fix (admin platform workspace): an AUTHENTICATED user
    whose role matches no persona (e.g. ``role_admin``) must leave nav_model
    unset (None) so the sidebar falls through to the legacy curated nav_groups
    — NOT collapse to the anon visitor's nav. Pre-fix slice 3b returned the anon
    nav here, collapsing the admin sidebar to the anonymous-visitor nav."""
    user = SimpleNamespace(email="u@x", username="u", roles=["role_admin"], is_superuser=False)
    auth_ctx = SimpleNamespace(is_authenticated=True, user=user, preferences={})

    def _resolver(_req: object) -> SimpleNamespace:
        return auth_ctx

    prc = _make_prc(
        get_auth_context=_resolver,
        persona_navs={"engineer": _PERSONA_NAV},
        anon_nav=_ANON_NAV,
    )
    await _inject_auth_context(prc)
    assert prc.ctx.nav_model is None


# ---------------------------------------------------------------------------
# #1324 FR-4: conditional nav — `when` survives reconcile + filters at render
# ---------------------------------------------------------------------------

# A tenant_config gate (group) + a role gate (link), as model_dump'd dicts.
_TC_GATE = {
    "comparison": {
        "field": "tenant_config.beta_features",
        "operator": "=",
        "value": {"literal": True},
    },
}
_ROLE_GATE = {"role_check": {"role_name": "admin"}}

_WHEN_NAV = NavModel(
    groups=(
        NavGroup(
            label="Beta",
            icon=None,
            collapsed=False,
            links=(
                NavLink(label="Always", route="/list/Always"),
                NavLink(label="AdminOnly", route="/list/AdminOnly", when=_ROLE_GATE),
            ),
            when=_TC_GATE,
        ),
        NavGroup(
            label="Core",
            icon=None,
            collapsed=False,
            links=(NavLink(label="Home", route="/list/Home"),),
        ),
    ),
    auto_discovered=False,
)


def test_reconcile_preserves_when_on_groups_and_links() -> None:
    """FR-4 layer 2: `_reconcile_nav_model` must copy `when` through (the
    reconciler rebuilds NavGroup/NavLink and would otherwise drop it)."""
    from dazzle.core import ir
    from dazzle.http.runtime.page_routes import _reconcile_nav_model

    appspec = ir.AppSpec(
        name="app",
        title="App",
        version="0.1.0",
        domain=ir.DomainSpec(entities=[]),
        surfaces=[],
        workspaces=[],
        personas=[],
    )
    reconciled = _reconcile_nav_model(appspec, "/app", _WHEN_NAV)

    beta = reconciled.groups[0]
    assert beta.when == _TC_GATE
    admin_link = next(link for link in beta.links if link.label == "AdminOnly")
    assert admin_link.when == _ROLE_GATE
    # Ungated group/link keep None.
    assert reconciled.groups[1].when is None
    assert reconciled.groups[0].links[0].when is None


# --- render filter: tenant_config flag gates the whole group ----------------


def test_group_when_tenant_config_false_hides_group() -> None:
    ctx = PageContext(page_title="x", tenant_config={"beta_features": False})
    sidebar = _sidebar_from_nav_model(_WHEN_NAV, ctx)
    group_labels = {g.label for g in sidebar.groups}
    # The tenant_config-gated "Beta" group is hidden; "Core" survives.
    assert "Beta" not in group_labels
    assert "Core" in group_labels


def test_group_when_tenant_config_true_shows_group() -> None:
    ctx = PageContext(
        page_title="x",
        tenant_config={"beta_features": True},
        user_roles=["role_admin"],  # also satisfies the admin-only link inside
    )
    sidebar = _sidebar_from_nav_model(_WHEN_NAV, ctx)
    group_labels = {g.label for g in sidebar.groups}
    assert "Beta" in group_labels
    beta = next(g for g in sidebar.groups if g.label == "Beta")
    link_labels = {i.label for i in beta.items}
    # Both links present: "Always" (no gate) + "AdminOnly" (admin satisfied).
    assert link_labels == {"Always", "AdminOnly"}


# --- render filter: role gate on a single link ------------------------------


def test_link_when_role_hidden_for_non_admin() -> None:
    """Group passes (tenant_config true) but the admin-only link is dropped for
    a non-admin; the ungated link survives."""
    ctx = PageContext(
        page_title="x",
        tenant_config={"beta_features": True},
        user_roles=["role_viewer"],
    )
    sidebar = _sidebar_from_nav_model(_WHEN_NAV, ctx)
    beta = next(g for g in sidebar.groups if g.label == "Beta")
    link_labels = {i.label for i in beta.items}
    assert link_labels == {"Always"}
    assert "AdminOnly" not in link_labels


def test_link_when_role_shown_for_admin() -> None:
    ctx = PageContext(
        page_title="x",
        tenant_config={"beta_features": True},
        user_roles=["role_admin"],
    )
    sidebar = _sidebar_from_nav_model(_WHEN_NAV, ctx)
    beta = next(g for g in sidebar.groups if g.label == "Beta")
    assert "AdminOnly" in {i.label for i in beta.items}


def test_group_with_all_links_filtered_out_is_dropped() -> None:
    """A surviving group whose every link is filtered out → drop the group
    (mirrors the existing empty-group handling)."""
    model = NavModel(
        groups=(
            NavGroup(
                label="OnlyAdmin",
                icon=None,
                collapsed=False,
                links=(NavLink(label="AdminOnly", route="/list/AdminOnly", when=_ROLE_GATE),),
            ),
        ),
        auto_discovered=False,
    )
    ctx = PageContext(page_title="x", user_roles=["role_viewer"])
    sidebar = _sidebar_from_nav_model(model, ctx)
    # Group header would be a flat? No — it has a label, so it'd be a NavGroup,
    # but all its links are filtered → it must not appear at all.
    assert sidebar.groups == ()
    assert sidebar.items == ()


def test_no_when_conditions_unaffected() -> None:
    """Regression: a NavModel with no `when` anywhere renders identically
    regardless of roles/tenant_config (visibility-only, opt-in)."""
    ctx_plain = PageContext(page_title="x", current_route="/list/Ticket")
    ctx_roles = PageContext(
        page_title="x",
        current_route="/list/Ticket",
        user_roles=["role_admin"],
        tenant_config={"anything": True},
    )
    a = _sidebar_from_nav_model(_PERSONA_NAV, ctx_plain)
    b = _sidebar_from_nav_model(_PERSONA_NAV, ctx_roles)
    assert a.groups == b.groups
    assert a.items == b.items
