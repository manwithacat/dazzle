"""#1794 — "who and what is this" in the app chrome and the renderer contract.

Each test drives the real page router (``create_page_routes`` over the
``fixtures/custom_renderer`` AppSpec) through a ``TestClient`` with a signed-in
user, so the chrome and the renderer context are the ones a request gets:

- U7: ``[ui] topbar_title`` picks the topbar title (app name / page title / none);
  the sidebar header keeps the app name.
- U8: the identity chip leads with the display name; the email is its ``title=``.
- U27: a custom renderer receives the signed-in ``Principal`` on its context.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.http.runtime.auth.models import AuthContext, MembershipRecord, UserRecord
from dazzle.http.runtime.page_routes import create_page_routes
from dazzle.http.runtime.renderers.init import register_default_renderers
from dazzle.http.runtime.services import RuntimeServices
from dazzle.render.context import CustomRenderCtx
from dazzle.render.principal import Principal

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "custom_renderer"
_USER = UserRecord(
    id=UUID("11111111-1111-1111-1111-111111111111"),
    email="patel@school.test",
    password_hash="x",
    username="Ms Patel",
    roles=["role_viewer"],
)
_MEMBERSHIP = MembershipRecord(
    id="m1", tenant_id="school-7", identity_id=str(_USER.id), roles=["role_teacher"]
)


class _CapturingRenderer:
    def __init__(self) -> None:
        self.ctx: Any = None

    def render(self, surface: Any, ctx: Any) -> str:
        self.ctx = ctx
        return "<section>cloud</section>"


@pytest.fixture(scope="module")
def appspec() -> Any:
    return load_project_appspec(_FIXTURE)


def _client(appspec: Any, *, topbar_title: str = "app") -> tuple[TestClient, _CapturingRenderer]:
    def get_auth_context(_request: Any) -> AuthContext:
        return AuthContext(
            user=_USER,
            is_authenticated=True,
            roles=list(_USER.roles),
            active_membership=_MEMBERSHIP,
        )

    services = RuntimeServices()
    register_default_renderers(services)
    word_cloud = _CapturingRenderer()
    services.renderer_registry.register(name="word_cloud", handler=word_cloud)
    app = FastAPI()
    app.include_router(
        create_page_routes(appspec, get_auth_context=get_auth_context, app_prefix="/app"),
        prefix="/app",
    )
    app.state.services = services
    app.state.fragment_chrome_topbar_title = topbar_title
    return TestClient(app), word_cloud


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        pytest.param("app", "Custom Renderer Example", id="app_name"),
        pytest.param("page", "Feedback word cloud", id="page_title"),
        pytest.param("none", None, id="no_title"),
    ],
)
def test_topbar_title_follows_ui_setting(appspec: Any, mode: str, expected: str | None) -> None:
    client, _ = _client(appspec, topbar_title=mode)
    html = client.get("/app/tag_cloud").text
    title = re.search(r'<div class="dz-topbar-title">(.*?)</div>', html)
    assert title is not None
    if expected is None:
        assert title.group(1) == ""
    else:
        assert title.group(1) == f'<span class="dz-topbar-title-text">{expected}</span>'
    # The sidebar header keeps the app name whatever the topbar shows.
    assert html.count("Custom Renderer Example") >= 2  # <title> + sidebar header


def test_identity_chip_shows_display_name_with_email_title(appspec: Any) -> None:
    client, _ = _client(appspec)
    html = client.get("/app/tag_cloud").text
    chip = re.search(r"<span [^>]*data-dz-account-identity[^>]*>([^<]*)</span>", html)
    assert chip is not None
    assert chip.group(1) == "Ms Patel · viewer"
    assert 'title="patel@school.test"' in chip.group(0)


def test_custom_renderer_receives_principal(appspec: Any) -> None:
    client, word_cloud = _client(appspec)
    assert client.get("/app/tag_cloud").status_code == 200
    assert isinstance(word_cloud.ctx, CustomRenderCtx)
    assert word_cloud.ctx.principal == Principal(
        user_id="11111111-1111-1111-1111-111111111111",
        roles=("teacher",),
        tenant_id="school-7",
        email="patel@school.test",
        display_name="Ms Patel",
    )
