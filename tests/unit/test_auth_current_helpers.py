"""Tests for the project-route auth helpers (issue #933)."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

pytest.importorskip("dazzle_back.runtime.auth.current")

from dazzle_back.runtime.auth import (  # noqa: E402
    current_auth,
    current_user,
    current_user_id,
    register_auth_store,
    require_auth,
)
from dazzle_back.runtime.auth.models import AuthContext, UserRecord  # noqa: E402


def _make_authed_context(
    user_id: UUID | None = None, roles: list[str] | None = None
) -> AuthContext:
    user = UserRecord(
        id=user_id or uuid4(),
        email="alice@example.com",
        password_hash="$2b$12$test-hash-not-real-just-fixture-padding-here-ok",
    )
    return AuthContext(
        user=user,
        is_authenticated=True,
        roles=roles or ["role_teacher"],
        preferences={"school": "oakwood"},
    )


def _make_request(cookies: dict[str, str] | None = None) -> MagicMock:
    req = MagicMock()
    req.cookies = cookies or {}
    return req


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Each test starts with a clean module-level state."""
    register_auth_store(None)
    yield
    register_auth_store(None)


class TestCurrentUserId:
    def test_returns_user_id_when_session_valid(self) -> None:
        target_uuid = uuid4()
        store = MagicMock()
        store.validate_session.return_value = _make_authed_context(target_uuid)
        register_auth_store(store)

        request = _make_request({"dazzle_session": "valid-session-id"})
        assert current_user_id(request) == str(target_uuid)
        store.validate_session.assert_called_once_with("valid-session-id")

    def test_returns_none_when_no_cookie(self) -> None:
        store = MagicMock()
        register_auth_store(store)

        assert current_user_id(_make_request({})) is None
        # Validate must NOT be called when no cookie is present.
        store.validate_session.assert_not_called()

    def test_returns_none_when_session_invalid(self) -> None:
        store = MagicMock()
        store.validate_session.return_value = AuthContext()  # is_authenticated=False
        register_auth_store(store)

        request = _make_request({"dazzle_session": "expired"})
        assert current_user_id(request) is None

    def test_returns_none_when_no_auth_store_registered(self) -> None:
        register_auth_store(None)
        request = _make_request({"dazzle_session": "anything"})
        assert current_user_id(request) is None

    def test_swallows_validate_session_exceptions(self) -> None:
        """If AuthStore raises on a malformed session id, the helper
        must still return None — projects shouldn't have to wrap every
        call in a try/except."""
        store = MagicMock()
        store.validate_session.side_effect = ValueError("malformed")
        register_auth_store(store)

        request = _make_request({"dazzle_session": "garbage"})
        assert current_user_id(request) is None


class TestCurrentUser:
    def test_returns_dict_with_id_email_roles(self) -> None:
        target_uuid = uuid4()
        ctx = _make_authed_context(target_uuid, roles=["role_teacher", "role_admin"])
        store = MagicMock()
        store.validate_session.return_value = ctx
        register_auth_store(store)

        request = _make_request({"dazzle_session": "ok"})
        user = current_user(request)
        assert user is not None
        assert user["id"] == str(target_uuid)
        assert user["email"] == "alice@example.com"
        assert user["roles"] == ["role_teacher", "role_admin"]
        assert user["preferences"] == {"school": "oakwood"}

    def test_returns_none_when_unauthenticated(self) -> None:
        store = MagicMock()
        store.validate_session.return_value = AuthContext()
        register_auth_store(store)

        assert current_user(_make_request({"dazzle_session": "x"})) is None


class TestCurrentAuth:
    def test_returns_empty_context_when_not_authed(self) -> None:
        register_auth_store(None)
        ctx = current_auth(_make_request())
        assert ctx.is_authenticated is False
        assert ctx.user is None

    def test_returns_full_context_when_authed(self) -> None:
        ctx_in = _make_authed_context()
        store = MagicMock()
        store.validate_session.return_value = ctx_in
        register_auth_store(store)

        ctx_out = current_auth(_make_request({"dazzle_session": "ok"}))
        assert ctx_out is ctx_in


class TestRequireAuthDecorator:
    @pytest.mark.asyncio
    async def test_passes_auth_to_handler_when_authed(self) -> None:
        ctx = _make_authed_context()
        store = MagicMock()
        store.validate_session.return_value = ctx
        register_auth_store(store)

        @require_auth()
        async def handler(request, auth):
            return {"user": str(auth.user.id)}

        result = await handler(_make_request({"dazzle_session": "ok"}))
        assert result == {"user": str(ctx.user.id)}

    @pytest.mark.asyncio
    async def test_returns_401_when_unauthenticated(self) -> None:
        register_auth_store(None)

        @require_auth()
        async def handler(request, auth):
            raise AssertionError("should not be reached")

        response = await handler(_make_request({}))
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_returns_403_when_role_missing(self) -> None:
        ctx = _make_authed_context(roles=["role_student"])
        store = MagicMock()
        store.validate_session.return_value = ctx
        register_auth_store(store)

        @require_auth(roles=["teacher"])
        async def handler(request, auth):
            raise AssertionError("should not be reached")

        response = await handler(_make_request({"dazzle_session": "ok"}))
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_passes_when_any_required_role_matches(self) -> None:
        """`roles=[a, b]` is OR semantics — user holding either passes."""
        ctx = _make_authed_context(roles=["role_admin"])
        store = MagicMock()
        store.validate_session.return_value = ctx
        register_auth_store(store)

        @require_auth(roles=["teacher", "admin"])
        async def handler(request, auth):
            return "ok"

        result = await handler(_make_request({"dazzle_session": "ok"}))
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_role_prefix_normalised_both_sides(self) -> None:
        """User roles can be `role_teacher` (DB-style) or `teacher`
        (persona-id-style); decorator must accept either."""
        ctx_db = _make_authed_context(roles=["role_teacher"])
        store = MagicMock()
        store.validate_session.return_value = ctx_db
        register_auth_store(store)

        @require_auth(roles=["role_teacher"])  # required spec uses prefix
        async def handler_a(request, auth):
            return "a"

        @require_auth(roles=["teacher"])  # required spec without prefix
        async def handler_b(request, auth):
            return "b"

        assert await handler_a(_make_request({"dazzle_session": "ok"})) == "a"
        assert await handler_b(_make_request({"dazzle_session": "ok"})) == "b"
