"""Tests for user preference persistence (v0.38.0)."""

from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

pytest.importorskip("fastapi", reason="FastAPI required for preference route tests")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from dazzle_back.runtime.auth.models import AuthContext, UserRecord  # noqa: E402

# ---------------------------------------------------------------------------
# AuthContext.preferences field
# ---------------------------------------------------------------------------


class TestAuthContextPreferences:
    def test_default_empty(self) -> None:
        ctx = AuthContext()
        assert ctx.preferences == {}

    def test_populated(self) -> None:
        ctx = AuthContext(preferences={"last_workspace": "dashboard"})
        assert ctx.preferences["last_workspace"] == "dashboard"


# ---------------------------------------------------------------------------
# Preference routes
# ---------------------------------------------------------------------------


def _make_app_with_prefs(
    prefs: dict[str, str] | None = None,
    user_id: UUID | None = None,
) -> tuple[FastAPI, MagicMock]:
    """Create a FastAPI app with preference routes wired to a mock store."""
    from dazzle_back.runtime.auth.routes import create_auth_routes

    uid = user_id or uuid4()
    mock_store = MagicMock()

    # Simulate validate_session returning authenticated user with prefs
    user = UserRecord(
        id=uid,
        email="test@example.com",
        password_hash="hashed",
    )
    mock_store.validate_session.return_value = AuthContext(
        user=user,
        is_authenticated=True,
        roles=["admin"],
        preferences=prefs or {},
    )
    mock_store.get_preferences.return_value = prefs or {}

    router = create_auth_routes(mock_store)
    app = FastAPI()
    app.include_router(router)
    return app, mock_store


class TestPreferenceRoutes:
    def test_get_preferences(self) -> None:
        app, _ = _make_app_with_prefs({"last_workspace": "dashboard", "theme": "dark"})
        client = TestClient(app)
        resp = client.get("/auth/preferences", cookies={"dazzle_session": "valid"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["preferences"]["last_workspace"] == "dashboard"
        assert data["preferences"]["theme"] == "dark"

    def test_get_preferences_unauthenticated(self) -> None:
        from dazzle_back.runtime.auth.routes import create_auth_routes

        mock_store = MagicMock()
        mock_store.validate_session.return_value = AuthContext()
        router = create_auth_routes(mock_store)
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.get("/auth/preferences")
        assert resp.status_code == 401

    def test_set_preferences_bulk(self) -> None:
        uid = uuid4()
        app, mock_store = _make_app_with_prefs(user_id=uid)
        client = TestClient(app)
        resp = client.put(
            "/auth/preferences",
            json={"preferences": {"sort.tasks": "date_desc", "filter.status": "active"}},
            cookies={"dazzle_session": "valid"},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 2
        mock_store.set_preferences.assert_called_once()
        call_args = mock_store.set_preferences.call_args
        assert call_args[0][0] == uid
        assert call_args[0][1] == {"sort.tasks": "date_desc", "filter.status": "active"}

    def test_set_single_preference(self) -> None:
        uid = uuid4()
        app, mock_store = _make_app_with_prefs(user_id=uid)
        client = TestClient(app)
        resp = client.put(
            "/auth/preferences/last_workspace",
            json={"value": "school_dashboard"},
            cookies={"dazzle_session": "valid"},
        )
        assert resp.status_code == 200
        assert resp.json()["key"] == "last_workspace"
        assert resp.json()["value"] == "school_dashboard"
        mock_store.set_preference.assert_called_once_with(uid, "last_workspace", "school_dashboard")

    def test_delete_preference(self) -> None:
        # DELETE is idempotent per RFC 7231 §4.3.5 — always returns 204 (#971).
        uid = uuid4()
        app, mock_store = _make_app_with_prefs(user_id=uid)
        mock_store.delete_preference.return_value = True
        client = TestClient(app)
        resp = client.delete(
            "/auth/preferences/old_key",
            cookies={"dazzle_session": "valid"},
        )
        assert resp.status_code == 204
        mock_store.delete_preference.assert_called_once_with(uid, "old_key")

    def test_delete_preference_not_found(self) -> None:
        # DELETE on a missing key still returns 204 (idempotent — RFC 7231 §4.3.5).
        app, mock_store = _make_app_with_prefs()
        mock_store.delete_preference.return_value = False
        client = TestClient(app)
        resp = client.delete(
            "/auth/preferences/nonexistent",
            cookies={"dazzle_session": "valid"},
        )
        assert resp.status_code == 204

    def test_set_preferences_invalid_body(self) -> None:
        app, _ = _make_app_with_prefs()
        client = TestClient(app)
        resp = client.put(
            "/auth/preferences",
            json={"preferences": "not_a_dict"},
            cookies={"dazzle_session": "valid"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# PageContext.user_preferences field
# ---------------------------------------------------------------------------


class TestPageContextPreferences:
    def test_default_empty(self) -> None:
        from dazzle_ui.runtime.template_context import PageContext

        ctx = PageContext(page_title="Test")
        assert ctx.user_preferences == {}

    def test_populated(self) -> None:
        from dazzle_ui.runtime.template_context import PageContext

        ctx = PageContext(
            page_title="Test",
            user_preferences={"last_workspace": "dashboard"},
        )
        assert ctx.user_preferences["last_workspace"] == "dashboard"
