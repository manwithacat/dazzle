"""The runtime's introspection routes take the app's auth posture.

``/_dazzle/{stats,spec,entity/*,tables}``, the integrations retries explorer
and (through the system-routes subsystem) ``/spec``, ``/db-info``,
``/_dazzle/services*`` and ``/_diagnostics`` expose the parsed spec, the
schema, the service stubs and the retry log. Flense ship AR found the event
explorer mounted with no auth dependency in every environment; this pins the
shared gate the rest of that surface now uses: anonymous → 401, authenticated
non-admin → 403, superuser or admin role → 200, liveness probes untouched.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI, HTTPException
from starlette.testclient import TestClient

from dazzle.core.ir.integrations import IntegrationSpec
from dazzle.http.runtime.auth.dependencies import create_admin_dependency, is_admin_context
from dazzle.http.runtime.auth.models import AuthContext, UserRecord
from dazzle.http.runtime.debug_routes import create_debug_routes
from dazzle.http.runtime.integrations_retries import create_integrations_retries_routes
from dazzle.http.runtime.retry_accumulator import RetryAccumulator

pytestmark = pytest.mark.gate


def _user(**kw: Any) -> UserRecord:
    base: dict[str, Any] = {"id": uuid4(), "email": "u@example.com", "password_hash": "x"}
    base.update(kw)
    return UserRecord(**base)


ANON = AuthContext(is_authenticated=False)
MEMBER = AuthContext(user=_user(roles=["member"]), is_authenticated=True, roles=["member"])
ADMIN_ROLE = AuthContext(user=_user(roles=["admin"]), is_authenticated=True, roles=["admin"])
SUPERUSER = AuthContext(user=_user(is_superuser=True), is_authenticated=True, roles=["member"])


def _auth_dep_for(ctx: AuthContext) -> Any:
    """Mimic ``create_auth_dependency``: 401 for anonymous, else the context."""

    async def dep() -> AuthContext:
        if not ctx.is_authenticated:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return ctx

    return dep


@pytest.mark.parametrize(
    ("ctx", "admin"),
    [(ANON, False), (MEMBER, False), (ADMIN_ROLE, True), (SUPERUSER, True)],
    ids=["anonymous", "member", "admin-role", "superuser"],
)
def test_is_admin_context(ctx: AuthContext, admin: bool) -> None:
    assert is_admin_context(ctx) is admin


def _app_with(ctx: AuthContext, *, with_auth: bool = True) -> TestClient:
    auth_dep = _auth_dep_for(ctx) if with_auth else None
    app = FastAPI()
    app.include_router(
        create_debug_routes(
            appspec=None, db_manager=None, entities=[], start_time=datetime.now(), auth_dep=auth_dep
        )
    )
    app.include_router(
        create_integrations_retries_routes(
            RetryAccumulator(), [IntegrationSpec(name="pp")], auth_dep=auth_dep
        )
    )

    gate = [] if auth_dep is None else [Depends(create_admin_dependency(auth_dep))]

    @app.get("/gated", dependencies=gate)
    async def gated() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("ctx", "status"),
    [(ANON, 401), (MEMBER, 403), (ADMIN_ROLE, 200), (SUPERUSER, 200)],
    ids=["anonymous-401", "member-403", "admin-role-200", "superuser-200"],
)
def test_admin_dependency_verdict(ctx: AuthContext, status: int) -> None:
    assert _app_with(ctx).get("/gated").status_code == status


@pytest.mark.parametrize(
    "path",
    ["/_dazzle/stats", "/_dazzle/spec", "/_dazzle/entity/Task", "/_dazzle/tables"],
)
def test_debug_inspection_routes_are_gated(path: str) -> None:
    assert _app_with(ANON).get(path).status_code == 401
    assert _app_with(MEMBER).get(path).status_code == 403


def test_retries_explorer_is_gated() -> None:
    assert _app_with(ANON).get("/_dazzle/integrations/x/retries").status_code == 401
    assert _app_with(MEMBER).get("/_dazzle/integrations/x/retries").status_code == 403
    # Admin reaches the handler (404: `x` is not a declared integration).
    assert _app_with(ADMIN_ROLE).get("/_dazzle/integrations/x/retries").status_code == 404


@pytest.mark.parametrize("path", ["/_dazzle/live", "/_dazzle/ready"])
def test_probes_stay_open(path: str) -> None:
    """Orchestrator probes carry no session; they never see 401."""
    assert _app_with(ANON).get(path).status_code != 401


def test_without_auth_nothing_is_gated() -> None:
    """A dev server without an auth store keeps the routes open, like every other route."""
    client = _app_with(ANON, with_auth=False)
    assert client.get("/_dazzle/integrations/x/retries").status_code == 404
    assert client.get("/gated").status_code == 200
