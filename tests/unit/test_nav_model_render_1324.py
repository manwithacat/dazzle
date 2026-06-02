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

from dazzle.render.context import NavItemContext, PageContext
from dazzle.render.dispatch import _build_sidebar_from_ctx, _sidebar_from_nav_model
from dazzle.ui.converters.nav_builder import NavGroup, NavLink, NavModel
from dazzle.ui.runtime.page_routes import _inject_auth_context, _resolve_nav_model

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
    from dazzle.ui.runtime.page_routes import _reconcile_nav_model

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
    assert _resolve_nav_model(deps, ["role_engineer"]) is _PERSONA_NAV


def test_resolve_nav_model_unmatched_role_falls_back_to_anon() -> None:
    deps = _deps({"engineer": _PERSONA_NAV}, _ANON_NAV)
    assert _resolve_nav_model(deps, ["role_unknown"]) is _ANON_NAV


def test_resolve_nav_model_no_roles_falls_back_to_anon() -> None:
    deps = _deps({"engineer": _PERSONA_NAV}, _ANON_NAV)
    assert _resolve_nav_model(deps, []) is _ANON_NAV
    assert _resolve_nav_model(deps, None) is _ANON_NAV


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
async def test_inject_authenticated_unmatched_role_sets_anon_nav_model() -> None:
    user = SimpleNamespace(email="u@x", username="u", roles=["role_unknown"], is_superuser=False)
    auth_ctx = SimpleNamespace(is_authenticated=True, user=user, preferences={})

    def _resolver(_req: object) -> SimpleNamespace:
        return auth_ctx

    prc = _make_prc(
        get_auth_context=_resolver,
        persona_navs={"engineer": _PERSONA_NAV},
        anon_nav=_ANON_NAV,
    )
    await _inject_auth_context(prc)
    assert prc.ctx.nav_model is _ANON_NAV
