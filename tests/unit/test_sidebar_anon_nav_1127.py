"""#1127: anon visitors must not see persona-gated workspaces in the sidebar.

Two surfaces under test:

1. ``compile_appspec_to_templates`` populates ``nav_items_anon`` /
   ``nav_groups_anon`` with only items from workspaces that declared
   no persona gate (``allowed is None`` per
   ``workspace_allowed_personas``).
2. ``_inject_auth_context`` swaps the page-level ``nav_items`` and
   ``nav_groups`` for the anon variants whenever the request has no
   auth context, no authenticated user, or no user role that matches
   any compiled persona.

Reproduced in production (penny_dreadful Heroku v25): anon GETs of
``/app/right`` saw 40 sidebar links while the same admin session saw
only 26 — the persona-gated workspaces (author, commercial) leaked
to anon because the auth-context resolver only filtered nav when a
non-empty role list was present.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dazzle.back.runtime.page_routes import _inject_auth_context
from dazzle.core import ir
from dazzle.core.ir.personas import PersonaSpec
from dazzle.core.ir.workspaces import (
    WorkspaceAccessLevel,
    WorkspaceAccessSpec,
    WorkspaceSpec,
)
from dazzle.render.context import NavItemContext, PageContext
from dazzle.ui.converters.template_compiler import compile_appspec_to_templates

# ---------------------------------------------------------------------------
# Compile-time: nav_items_anon / nav_groups_anon population
# ---------------------------------------------------------------------------


def _make_appspec_mixed_workspaces() -> ir.AppSpec:
    """Two workspaces: one open (no access), one persona-gated."""
    open_ws = WorkspaceSpec(name="public_dash", title="Public")
    gated_ws = WorkspaceSpec(
        name="admin_dash",
        title="Admin",
        access=WorkspaceAccessSpec(
            level=WorkspaceAccessLevel.PERSONA,
            allow_personas=["admin"],
        ),
    )
    surface = ir.SurfaceSpec(
        name="home",
        title="Home",
        entity_ref=None,
        mode=ir.SurfaceMode.LIST,
        sections=[],
        actions=[],
    )
    return ir.AppSpec(
        name="test_app",
        title="Test",
        version="0.1.0",
        domain=ir.DomainSpec(entities=[]),
        surfaces=[surface],
        workspaces=[open_ws, gated_ws],
        personas=[PersonaSpec(id="admin", label="Admin")],
    )


def test_compile_populates_nav_items_anon_with_open_workspaces_only() -> None:
    appspec = _make_appspec_mixed_workspaces()
    contexts = compile_appspec_to_templates(appspec, app_prefix="/app")

    ctx = next(iter(contexts.values()))
    anon_routes = {i.route for i in ctx.nav_items_anon}
    all_routes = {i.route for i in ctx.nav_items}

    # The open workspace appears in anon nav…
    assert "/app/workspaces/public_dash" in anon_routes
    # …but the persona-gated one does NOT.
    assert "/app/workspaces/admin_dash" not in anon_routes
    # The full nav still contains everything.
    assert "/app/workspaces/admin_dash" in all_routes
    assert "/app/workspaces/public_dash" in all_routes


def test_compile_anon_nav_empty_when_every_workspace_is_gated() -> None:
    """If every workspace has a persona gate, anon visitors see nothing."""
    gated_a = WorkspaceSpec(
        name="a",
        title="A",
        access=WorkspaceAccessSpec(level=WorkspaceAccessLevel.PERSONA, allow_personas=["admin"]),
    )
    gated_b = WorkspaceSpec(
        name="b",
        title="B",
        access=WorkspaceAccessSpec(level=WorkspaceAccessLevel.PERSONA, allow_personas=["staff"]),
    )
    surface = ir.SurfaceSpec(
        name="home",
        title="Home",
        entity_ref=None,
        mode=ir.SurfaceMode.LIST,
        sections=[],
        actions=[],
    )
    appspec = ir.AppSpec(
        name="test_app",
        title="Test",
        version="0.1.0",
        domain=ir.DomainSpec(entities=[]),
        surfaces=[surface],
        workspaces=[gated_a, gated_b],
        personas=[
            PersonaSpec(id="admin", label="Admin"),
            PersonaSpec(id="staff", label="Staff"),
        ],
    )
    contexts = compile_appspec_to_templates(appspec, app_prefix="/app")
    ctx = next(iter(contexts.values()))
    assert ctx.nav_items_anon == []
    assert ctx.nav_groups_anon == []


# ---------------------------------------------------------------------------
# Runtime: _inject_auth_context swap to anon variants
# ---------------------------------------------------------------------------


def _make_prc(
    *,
    get_auth_context: object | None,
    nav_items: list[NavItemContext] | None = None,
    nav_items_anon: list[NavItemContext] | None = None,
    nav_by_persona: dict[str, list[NavItemContext]] | None = None,
) -> SimpleNamespace:
    """Build the minimal _PageRequestContext shape _inject_auth_context reads."""
    ctx = PageContext(
        page_title="x",
        nav_items=nav_items or [],
        nav_items_anon=nav_items_anon or [],
        nav_by_persona=nav_by_persona or {},
    )
    deps = SimpleNamespace(
        get_auth_context=get_auth_context,
        entity_cedar_specs=None,
        route_entity=None,
        # #1324 slice 3b: _inject_auth_context now also resolves a precomputed
        # NavModel from deps.persona_navs/anon_nav. These tests exercise the
        # legacy nav_items/nav_groups path (which stays as fallback), so empty
        # precomputed navs are fine here — nav_model resolves to None/anon.
        persona_navs={},
        anon_nav=None,
    )
    return SimpleNamespace(ctx=ctx, deps=deps, request=MagicMock(), auth_ctx=None)


_NAV_PUBLIC = NavItemContext(label="Public", route="/app/workspaces/public_dash")
_NAV_GATED = NavItemContext(label="Admin", route="/app/workspaces/admin_dash")


@pytest.mark.asyncio
async def test_inject_no_auth_wiring_preserves_full_nav() -> None:
    """``get_auth_context is None`` is the "developer opted out of
    access control" mode — persona gates have no enforcement layer
    here, so the nav stays as declared rather than collapsing to an
    empty sidebar in example apps that have no auth fixture wired up.

    The anon-leak this issue closes is the production shape where
    auth IS configured but the request has no session — see the
    next three tests.
    """
    prc = _make_prc(
        get_auth_context=None,
        nav_items=[_NAV_PUBLIC, _NAV_GATED],
        nav_items_anon=[_NAV_PUBLIC],
    )
    await _inject_auth_context(prc)
    routes = {i.route for i in prc.ctx.nav_items}
    assert routes == {"/app/workspaces/public_dash", "/app/workspaces/admin_dash"}


@pytest.mark.asyncio
async def test_inject_unauthenticated_user_swaps_to_anon_nav() -> None:
    """Auth wiring is configured, but the request has no authenticated
    user — should still get the anon-safe sidebar."""

    def _resolver(_req: object) -> SimpleNamespace:
        return SimpleNamespace(is_authenticated=False, user=None)

    prc = _make_prc(
        get_auth_context=_resolver,
        nav_items=[_NAV_PUBLIC, _NAV_GATED],
        nav_items_anon=[_NAV_PUBLIC],
    )
    await _inject_auth_context(prc)
    routes = {i.route for i in prc.ctx.nav_items}
    assert routes == {"/app/workspaces/public_dash"}


@pytest.mark.asyncio
async def test_inject_authenticated_unmatched_role_swaps_to_anon_nav() -> None:
    """Authed user with a role that matches no compiled persona must not
    fall through to the unfiltered nav (this was the original leak)."""
    user = SimpleNamespace(email="x@y", username="x", roles=["role_unknown"], is_superuser=False)
    auth_ctx = SimpleNamespace(is_authenticated=True, user=user, preferences={})

    def _resolver(_req: object) -> SimpleNamespace:
        return auth_ctx

    prc = _make_prc(
        get_auth_context=_resolver,
        nav_items=[_NAV_PUBLIC, _NAV_GATED],
        nav_items_anon=[_NAV_PUBLIC],
        nav_by_persona={"admin": [_NAV_PUBLIC, _NAV_GATED]},
    )
    await _inject_auth_context(prc)
    routes = {i.route for i in prc.ctx.nav_items}
    assert routes == {"/app/workspaces/public_dash"}


@pytest.mark.asyncio
async def test_inject_authenticated_matched_role_uses_persona_nav() -> None:
    """Happy path — authed admin gets the admin persona's nav, not anon."""
    user = SimpleNamespace(email="a@b", username="admin", roles=["role_admin"], is_superuser=False)
    auth_ctx = SimpleNamespace(is_authenticated=True, user=user, preferences={})

    def _resolver(_req: object) -> SimpleNamespace:
        return auth_ctx

    prc = _make_prc(
        get_auth_context=_resolver,
        nav_items=[_NAV_PUBLIC, _NAV_GATED],
        nav_items_anon=[_NAV_PUBLIC],
        nav_by_persona={"admin": [_NAV_PUBLIC, _NAV_GATED]},
    )
    await _inject_auth_context(prc)
    routes = {i.route for i in prc.ctx.nav_items}
    assert routes == {"/app/workspaces/public_dash", "/app/workspaces/admin_dash"}


@pytest.mark.asyncio
async def test_inject_resolver_exception_falls_back_to_anon_nav() -> None:
    """A raising auth resolver must not leave the unfiltered nav exposed
    — fail-closed semantics for the security boundary."""

    def _resolver(_req: object) -> object:
        raise RuntimeError("auth subsystem down")

    prc = _make_prc(
        get_auth_context=_resolver,
        nav_items=[_NAV_PUBLIC, _NAV_GATED],
        nav_items_anon=[_NAV_PUBLIC],
    )
    await _inject_auth_context(prc)
    routes = {i.route for i in prc.ctx.nav_items}
    assert routes == {"/app/workspaces/public_dash"}
