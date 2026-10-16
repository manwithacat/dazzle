"""finish_login_session: the single session-minting point for enterprise SSO (DD-013).

No ``from __future__ import annotations``: the test mounts a FastAPI route (ADR-0014).
"""

from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.sso_session import finish_login_session


class _Store:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.created_for: list[str] = []

    def create_session(self, user: object, *, active_membership_id: str) -> SimpleNamespace:
        self.created_for.append(active_membership_id)
        return SimpleNamespace(id="fresh-sid", csrf_secret="csrf-1")

    def delete_session(self, session_id: str) -> bool:
        self.deleted.append(session_id)
        return True


def test_finish_login_session_replaces_the_pre_auth_session() -> None:
    store = _Store()
    app = FastAPI()

    @app.get("/callback")
    def callback(request: Request):  # noqa: ANN202 — the redirect response
        return finish_login_session(
            request,
            store,
            SimpleNamespace(roles=["member"]),
            "membership-1",
            cookie_name="dazzle_session",
            safe_next="/app",
        )

    client = TestClient(app)
    client.cookies.set("dazzle_session", "pre-auth-sid")
    response = client.get("/callback", follow_redirects=False)

    assert response.status_code == 303 and response.headers["location"] == "/app"
    assert store.created_for == ["membership-1"]
    assert store.deleted == ["pre-auth-sid"]  # session-fixation defence
    assert response.cookies.get("dazzle_session") == "fresh-sid"
