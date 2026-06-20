"""Tests for the onboarding complete/dismiss HTTP routes (v0.71.2)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.onboarding.routes import create_onboarding_routes


def _app(repo: MagicMock | None, *, user_id: str | None = "u1") -> FastAPI:
    """Wire a FastAPI app with the repository + current_user state the
    routes need. ``user_id=None`` simulates an anonymous request."""
    app = FastAPI()
    app.state.onboarding_state = repo
    app.include_router(create_onboarding_routes())

    @app.middleware("http")
    async def attach_user(request, call_next):  # type: ignore[no-untyped-def]
        if user_id is not None:
            request.state.current_user = SimpleNamespace(id=user_id)
        else:
            request.state.current_user = None
        return await call_next(request)

    return app


def test_complete_route_calls_mark_step_completed() -> None:
    repo = MagicMock()
    client = TestClient(_app(repo))
    resp = client.post("/api/onboarding/workspace_setup/welcome/complete")
    assert resp.status_code == 200
    assert resp.text == ""
    repo.mark_step_completed.assert_called_once()
    call = repo.mark_step_completed.call_args
    assert call.kwargs["user_id"] == "u1"
    assert call.kwargs["guide_name"] == "workspace_setup"
    assert call.kwargs["step_name"] == "welcome"
    assert call.kwargs["guide_version"] == 1


def test_dismiss_route_calls_mark_step_dismissed() -> None:
    repo = MagicMock()
    client = TestClient(_app(repo))
    resp = client.post("/api/onboarding/workspace_setup/welcome/dismiss")
    assert resp.status_code == 200
    repo.mark_step_dismissed.assert_called_once()


def test_complete_route_returns_401_without_authentication() -> None:
    repo = MagicMock()
    client = TestClient(_app(repo, user_id=None))
    resp = client.post("/api/onboarding/workspace_setup/welcome/complete")
    assert resp.status_code == 401


def test_routes_503_when_repository_not_configured() -> None:
    """Defensive: if the auth subsystem didn't wire up
    ``app.state.onboarding_state`` (DATABASE_URL missing) the routes
    should report unavailable, not crash."""
    client = TestClient(_app(repo=None))
    resp = client.post("/api/onboarding/g/s/complete")
    assert resp.status_code == 503
    assert "OnboardingStateRepository" in resp.text
