"""Tests for explicit password support in user_management MCP handlers."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _mock_dazzle_back():
    """Provide a mock dazzle_back so handler imports don't fail."""
    mock_auth = MagicMock()
    mock_runtime = MagicMock()
    mock_runtime.auth = mock_auth

    fake_user = MagicMock()
    fake_user.id = "00000000-0000-0000-0000-000000000001"
    fake_user.email = "bob@example.com"
    fake_user.username = None
    fake_user.is_active = True
    fake_user.is_superuser = False
    fake_user.roles = []
    fake_user.password_hash = "salt$hash"
    fake_user.created_at.isoformat.return_value = "2026-01-01T00:00:00"
    fake_user.updated_at.isoformat.return_value = "2026-01-01T00:00:00"

    store = MagicMock()
    store.get_user_by_email.return_value = None
    store.create_user.return_value = fake_user
    store.get_user_by_id.return_value = fake_user
    store.update_password.return_value = True
    store.delete_user_sessions.return_value = 1
    mock_auth.AuthStore.return_value = store

    saved = {}
    for mod_name in ["dazzle_back", "dazzle_back.runtime", "dazzle_back.runtime.auth"]:
        saved[mod_name] = sys.modules.get(mod_name)
        sys.modules[mod_name] = (
            mock_runtime
            if "runtime" in mod_name and "auth" not in mod_name
            else mock_auth
            if mod_name.endswith(".auth")
            else MagicMock()
        )

    # Fix: make dazzle_back.runtime.auth.AuthStore resolve correctly
    sys.modules["dazzle_back.runtime.auth"] = mock_auth
    sys.modules["dazzle_back.runtime"] = mock_runtime
    sys.modules["dazzle_back"] = MagicMock()

    yield store, fake_user

    for mod_name, orig in saved.items():
        if orig is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = orig


class TestCreateUserHandlerPassword:
    @pytest.mark.asyncio
    async def test_explicit_password_used(self, _mock_dazzle_back):
        store, fake_user = _mock_dazzle_back
        from dazzle.mcp.server.handlers.user_management import create_user_handler

        with MagicMock() as _:
            from unittest.mock import patch

            with patch(
                "dazzle.mcp.server.handlers.user_management._get_auth_store",
                return_value=store,
            ):
                result = await create_user_handler(
                    email="bob@example.com",
                    password="ExplicitPass123",
                )

        assert result["success"] is True
        store.create_user.assert_called_once()
        assert store.create_user.call_args[1]["password"] == "ExplicitPass123"
        # Should not expose the password back
        assert "temporary_password" not in result

    @pytest.mark.asyncio
    async def test_generated_password_returned(self, _mock_dazzle_back):
        store, fake_user = _mock_dazzle_back
        from unittest.mock import patch

        from dazzle.mcp.server.handlers.user_management import create_user_handler

        with patch(
            "dazzle.mcp.server.handlers.user_management._get_auth_store",
            return_value=store,
        ):
            result = await create_user_handler(email="bob@example.com")

        assert result["success"] is True
        assert "temporary_password" in result

    @pytest.mark.asyncio
    async def test_short_password_rejected(self, _mock_dazzle_back):
        store, fake_user = _mock_dazzle_back
        from unittest.mock import patch

        from dazzle.mcp.server.handlers.user_management import create_user_handler

        with patch(
            "dazzle.mcp.server.handlers.user_management._get_auth_store",
            return_value=store,
        ):
            result = await create_user_handler(
                email="bob@example.com",
                password="short",
            )

        assert result["success"] is False
        assert "at least 8 characters" in result["error"]
        store.create_user.assert_not_called()


class TestResetPasswordHandlerPassword:
    @pytest.mark.asyncio
    async def test_explicit_password_used(self, _mock_dazzle_back):
        store, fake_user = _mock_dazzle_back
        from unittest.mock import patch

        from dazzle.mcp.server.handlers.user_management import reset_password_handler

        with patch(
            "dazzle.mcp.server.handlers.user_management._get_auth_store",
            return_value=store,
        ):
            result = await reset_password_handler(
                user_id="00000000-0000-0000-0000-000000000001",
                password="NewExplicitPass1",
            )

        assert result["success"] is True
        assert "temporary_password" not in result
        store.update_password.assert_called_once()

    @pytest.mark.asyncio
    async def test_generated_password_returned(self, _mock_dazzle_back):
        store, fake_user = _mock_dazzle_back
        from unittest.mock import patch

        from dazzle.mcp.server.handlers.user_management import reset_password_handler

        with patch(
            "dazzle.mcp.server.handlers.user_management._get_auth_store",
            return_value=store,
        ):
            result = await reset_password_handler(
                user_id="00000000-0000-0000-0000-000000000001",
            )

        assert result["success"] is True
        assert "temporary_password" in result

    @pytest.mark.asyncio
    async def test_short_password_rejected(self, _mock_dazzle_back):
        store, fake_user = _mock_dazzle_back
        from unittest.mock import patch

        from dazzle.mcp.server.handlers.user_management import reset_password_handler

        with patch(
            "dazzle.mcp.server.handlers.user_management._get_auth_store",
            return_value=store,
        ):
            result = await reset_password_handler(
                user_id="00000000-0000-0000-0000-000000000001",
                password="short",
            )

        assert result["success"] is False
        assert "at least 8 characters" in result["error"]
        store.update_password.assert_not_called()
