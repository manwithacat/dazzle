"""Request-state navigation uses one NavModel without anonymous leakage."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dazzle.core import ir
from dazzle.core.ir.personas import PersonaSpec
from dazzle.core.ir.workspaces import WorkspaceAccessLevel, WorkspaceAccessSpec, WorkspaceSpec
from dazzle.http.runtime.page_routes import _inject_auth_context
from dazzle.page.converters.nav_builder import (
    build_anon_nav,
    build_role_nav,
    build_unrestricted_nav,
)
from dazzle.rbac.matrix import generate_access_matrix
from dazzle.render.context import PageContext


def _spec() -> ir.AppSpec:
    return ir.AppSpec(
        name="test_app",
        title="Test",
        version="0.1.0",
        domain=ir.DomainSpec(entities=[]),
        surfaces=[],
        workspaces=[
            WorkspaceSpec(name="public_dash", title="Public"),
            WorkspaceSpec(
                name="admin_dash",
                title="Admin",
                access=WorkspaceAccessSpec(
                    level=WorkspaceAccessLevel.PERSONA, allow_personas=["admin"]
                ),
            ),
        ],
        personas=[PersonaSpec(id="admin", label="Admin")],
    )


def _routes(model: object) -> set[str]:
    return {link.route for group in model.groups for link in group.links}


def test_anon_model_excludes_persona_gated_workspace() -> None:
    spec = _spec()
    routes = _routes(build_anon_nav(spec, generate_access_matrix(spec)))
    assert "/workspaces/public_dash" in routes
    assert "/workspaces/admin_dash" not in routes


def test_no_auth_model_exposes_declared_workspaces() -> None:
    routes = _routes(build_unrestricted_nav(_spec()))
    assert routes == {"/workspaces/public_dash", "/workspaces/admin_dash"}


def test_unknown_role_is_anon_safe_and_admin_role_is_explicit() -> None:
    spec = _spec()
    matrix = generate_access_matrix(spec)
    assert "/workspaces/admin_dash" not in _routes(build_role_nav(spec, "unknown", matrix))
    assert "/workspaces/admin_dash" in _routes(build_role_nav(spec, "admin", matrix))


@pytest.mark.asyncio
async def test_auth_resolution_failure_uses_anon_model() -> None:
    spec = _spec()
    anon = build_anon_nav(spec, generate_access_matrix(spec))

    def fail(_request: object) -> object:
        raise RuntimeError("auth unavailable")

    deps = SimpleNamespace(
        get_auth_context=fail,
        persona_navs={},
        anon_nav=anon,
        unmatched_role_navs={},
        unrestricted_nav=build_unrestricted_nav(spec),
    )
    prc = SimpleNamespace(
        ctx=PageContext(page_title="x"), deps=deps, request=MagicMock(), auth_ctx=None
    )
    await _inject_auth_context(prc)
    assert prc.ctx.nav_model is anon
