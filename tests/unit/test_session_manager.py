"""Tests for the per-persona session manager."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle.testing.session_manager import (
    PersonaSession,
    SessionManager,
    SessionManifest,
)

# =============================================================================
# PersonaSession model tests
# =============================================================================


class TestPersonaSession:
    def test_create_session(self) -> None:
        session = PersonaSession(
            persona_id="admin",
            user_id="uuid-123",
            email="admin@test.local",
            role="admin",
            session_token="tok_abc",
            base_url="http://localhost:8000",
        )
        assert session.persona_id == "admin"
        assert session.session_token == "tok_abc"

    def test_serialization(self) -> None:
        session = PersonaSession(
            persona_id="agent",
            user_id="uuid-456",
            email="agent@test.local",
            role="agent",
            session_token="tok_def",
        )
        data = json.loads(session.model_dump_json())
        assert data["persona_id"] == "agent"
        assert data["session_token"] == "tok_def"


# =============================================================================
# SessionManifest model tests
# =============================================================================


class TestSessionManifest:
    def test_empty_manifest(self) -> None:
        manifest = SessionManifest(project_name="test", base_url="http://localhost:8000")
        assert manifest.persona_ids == []
        assert manifest.is_stale is False

    def test_manifest_with_sessions(self) -> None:
        session = PersonaSession(
            persona_id="admin",
            user_id="uuid-123",
            email="admin@test.local",
            role="admin",
            session_token="tok_abc",
        )
        manifest = SessionManifest(
            project_name="test",
            base_url="http://localhost:8000",
            sessions={"admin": session},
        )
        assert manifest.persona_ids == ["admin"]

    def test_stale_manifest(self) -> None:
        session = PersonaSession(
            persona_id="admin",
            user_id="uuid-123",
            email="admin@test.local",
            role="admin",
            session_token="tok_abc",
            created_at="2020-01-01T00:00:00+00:00",  # very old
        )
        manifest = SessionManifest(
            project_name="test",
            base_url="http://localhost:8000",
            sessions={"admin": session},
        )
        assert manifest.is_stale is True


# =============================================================================
# SessionManager tests
# =============================================================================


class TestSessionManager:
    @pytest.fixture()
    def tmp_project(self, tmp_path: Path) -> Path:
        """Create a minimal project directory."""
        (tmp_path / "dazzle.toml").write_text("[project]\nname = 'test'\n")
        return tmp_path

    def test_init(self, tmp_project: Path) -> None:
        manager = SessionManager(tmp_project, base_url="http://localhost:8000")
        assert manager.base_url == "http://localhost:8000"
        assert manager.sessions_dir == tmp_project / ".dazzle" / "test_sessions"

    def test_list_sessions_empty(self, tmp_project: Path) -> None:
        manager = SessionManager(tmp_project)
        assert manager.list_sessions() == []

    def test_load_session_not_found(self, tmp_project: Path) -> None:
        manager = SessionManager(tmp_project)
        assert manager.load_session("nonexistent") is None

    def test_save_and_load_session(self, tmp_project: Path) -> None:
        manager = SessionManager(tmp_project)
        session = PersonaSession(
            persona_id="admin",
            user_id="uuid-123",
            email="admin@test.local",
            role="admin",
            session_token="tok_abc",
        )
        manager._save_session(session)

        loaded = manager.load_session("admin")
        assert loaded is not None
        assert loaded.persona_id == "admin"
        assert loaded.session_token == "tok_abc"

    def test_get_cookies(self, tmp_project: Path) -> None:
        manager = SessionManager(tmp_project)
        session = PersonaSession(
            persona_id="agent",
            user_id="uuid-456",
            email="agent@test.local",
            role="agent",
            session_token="tok_xyz",
        )
        manager._save_session(session)

        cookies = manager.get_cookies("agent")
        assert cookies == {"dazzle_session": "tok_xyz"}

    def test_get_cookies_no_session(self, tmp_project: Path) -> None:
        manager = SessionManager(tmp_project)
        cookies = manager.get_cookies("nonexistent")
        assert cookies == {}

    def test_get_httpx_cookies(self, tmp_project: Path) -> None:
        manager = SessionManager(tmp_project)
        session = PersonaSession(
            persona_id="admin",
            user_id="uuid-123",
            email="admin@test.local",
            role="admin",
            session_token="tok_abc",
        )
        manager._save_session(session)

        cookies = manager.get_httpx_cookies("admin")
        assert cookies.get("dazzle_session") == "tok_abc"

    def test_list_sessions(self, tmp_project: Path) -> None:
        manager = SessionManager(tmp_project)
        for pid in ["admin", "agent", "customer"]:
            session = PersonaSession(
                persona_id=pid,
                user_id=f"uuid-{pid}",
                email=f"{pid}@test.local",
                role=pid,
                session_token=f"tok_{pid}",
            )
            manager._save_session(session)

        sessions = manager.list_sessions()
        assert sorted(sessions) == ["admin", "agent", "customer"]

    def test_save_and_load_manifest(self, tmp_project: Path) -> None:
        manager = SessionManager(tmp_project)
        session = PersonaSession(
            persona_id="admin",
            user_id="uuid-123",
            email="admin@test.local",
            role="admin",
            session_token="tok_abc",
        )
        manifest = SessionManifest(
            project_name="test",
            base_url="http://localhost:8000",
            sessions={"admin": session},
        )
        manager._save_manifest(manifest)

        loaded = manager.load_manifest()
        assert loaded is not None
        assert loaded.project_name == "test"
        assert "admin" in loaded.sessions

    def test_cleanup(self, tmp_project: Path) -> None:
        manager = SessionManager(tmp_project)
        for pid in ["admin", "agent"]:
            session = PersonaSession(
                persona_id=pid,
                user_id=f"uuid-{pid}",
                email=f"{pid}@test.local",
                role=pid,
                session_token=f"tok_{pid}",
            )
            manager._save_session(session)

        manifest = SessionManifest(
            project_name="test",
            base_url="http://localhost:8000",
        )
        manager._save_manifest(manifest)

        count = manager.cleanup()
        assert count == 3  # 2 sessions + 1 manifest
        assert manager.list_sessions() == []


# =============================================================================
# Async tests
# =============================================================================


class TestSessionManagerAsync:
    @pytest.fixture()
    def tmp_project(self, tmp_path: Path) -> Path:
        (tmp_path / "dazzle.toml").write_text("[project]\nname = 'test'\n")
        return tmp_path

    @pytest.mark.asyncio()
    async def test_create_session_via_test_endpoint(self, tmp_project: Path) -> None:
        manager = SessionManager(tmp_project, base_url="http://localhost:8000")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "user_id": "uuid-admin",
            "username": "admin",
            "role": "admin",
            "session_token": "tok_from_test",
            "token": "tok_from_test",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        session = await manager.create_session("admin", client=mock_client)
        assert session.persona_id == "admin"
        assert session.session_token == "tok_from_test"

        # Session should be saved to disk
        loaded = manager.load_session("admin")
        assert loaded is not None
        assert loaded.session_token == "tok_from_test"

    @pytest.mark.asyncio()
    async def test_create_session_fallback_to_login(self, tmp_project: Path) -> None:
        manager = SessionManager(tmp_project, base_url="http://localhost:8000")

        # First call (test endpoint) returns 404, second (login) returns 200
        test_response = MagicMock()
        test_response.status_code = 404

        login_response = MagicMock()
        login_response.status_code = 200
        login_response.headers = MagicMock()
        login_response.headers.get_list = MagicMock(
            return_value=["dazzle_session=tok_login; Path=/; HttpOnly"]
        )
        login_response.json.return_value = {
            "user": {"id": "uuid-admin", "email": "admin@test.local", "roles": ["admin"]},
            "message": "Login successful",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[test_response, login_response])

        session = await manager.create_session("admin", client=mock_client)
        assert session.persona_id == "admin"
        assert session.session_token == "tok_login"

    @pytest.mark.asyncio()
    async def test_create_session_both_fail(self, tmp_project: Path) -> None:
        manager = SessionManager(tmp_project, base_url="http://localhost:8000")

        fail_response = MagicMock()
        fail_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=fail_response)

        with pytest.raises(RuntimeError, match="Could not authenticate persona"):
            await manager.create_session("admin", client=mock_client)

    @pytest.mark.asyncio()
    async def test_create_all_sessions(self, tmp_project: Path) -> None:
        manager = SessionManager(tmp_project, base_url="http://localhost:8000")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "user_id": "uuid-test",
            "username": "test",
            "role": "test",
            "session_token": "tok_test",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        # Create a mock appspec with personas
        persona1 = MagicMock()
        persona1.id = "admin"
        persona2 = MagicMock()
        persona2.id = "agent"
        appspec = MagicMock()
        appspec.name = "test_app"
        appspec.personas = [persona1, persona2]

        with patch(
            "dazzle.testing.session_manager.httpx.AsyncClient",
            return_value=mock_client,
        ):
            manifest = await manager.create_all_sessions(appspec, force=True)

        assert len(manifest.sessions) == 2
        assert "admin" in manifest.sessions
        assert "agent" in manifest.sessions

    @pytest.mark.asyncio()
    async def test_validate_session_valid(self, tmp_project: Path) -> None:
        manager = SessionManager(tmp_project, base_url="http://localhost:8000")

        # Save a session
        session = PersonaSession(
            persona_id="admin",
            user_id="uuid-123",
            email="admin@test.local",
            role="admin",
            session_token="tok_valid",
        )
        manager._save_session(session)

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()

        result = await manager.validate_session("admin", client=mock_client)
        assert result is True

    @pytest.mark.asyncio()
    async def test_validate_session_expired(self, tmp_project: Path) -> None:
        manager = SessionManager(tmp_project, base_url="http://localhost:8000")

        session = PersonaSession(
            persona_id="admin",
            user_id="uuid-123",
            email="admin@test.local",
            role="admin",
            session_token="tok_expired",
        )
        manager._save_session(session)

        mock_response = MagicMock()
        mock_response.status_code = 401

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()

        result = await manager.validate_session("admin", client=mock_client)
        assert result is False


# =============================================================================
# Diff tests
# =============================================================================


class TestDiffRoute:
    @pytest.fixture()
    def tmp_project(self, tmp_path: Path) -> Path:
        (tmp_path / "dazzle.toml").write_text("[project]\nname = 'test'\n")
        return tmp_path

    @pytest.mark.asyncio()
    async def test_diff_route_no_sessions(self, tmp_project: Path) -> None:
        manager = SessionManager(tmp_project, base_url="http://localhost:8000")
        result = await manager.diff_route("/contacts")
        assert "error" in result

    @pytest.mark.asyncio()
    async def test_diff_route(self, tmp_project: Path) -> None:
        manager = SessionManager(tmp_project, base_url="http://localhost:8000")

        # Create sessions for two personas
        for pid, token in [("admin", "tok_admin"), ("agent", "tok_agent")]:
            session = PersonaSession(
                persona_id=pid,
                user_id=f"uuid-{pid}",
                email=f"{pid}@test.local",
                role=pid,
                session_token=token,
            )
            manager._save_session(session)

        # Mock httpx responses
        admin_response = MagicMock()
        admin_response.status_code = 200
        admin_response.text = "<html><table><tr><th>Name</th></tr><tr><td>Alice</td></tr><tr><td>Bob</td></tr></table></html>"
        admin_response.url = "http://localhost:8000/contacts"

        agent_response = MagicMock()
        agent_response.status_code = 403
        agent_response.text = "Forbidden"
        agent_response.url = "http://localhost:8000/contacts"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[admin_response, agent_response])
        mock_client.aclose = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await manager.diff_route("/contacts", ["admin", "agent"])

        assert result["route"] == "/contacts"
        assert result["personas"]["admin"]["status"] == 200
        assert result["personas"]["admin"]["table_rows"] == 2
        assert result["personas"]["agent"]["status"] == 403


# =============================================================================
# Client factory tests
# =============================================================================


class TestClientFactory:
    def test_create_persona_client_no_persona(self, tmp_path: Path) -> None:
        import httpx as httpx_mod

        from dazzle.agent.client_factory import create_persona_client

        client = create_persona_client(tmp_path, "http://localhost:8000")
        assert isinstance(client, httpx_mod.AsyncClient)
        # No cookies should be set
        assert len(client.cookies) == 0

    def test_create_persona_client_with_session(self, tmp_path: Path) -> None:
        import httpx as httpx_mod

        from dazzle.agent.client_factory import create_persona_client

        # Create a stored session
        sessions_dir = tmp_path / ".dazzle" / "test_sessions"
        sessions_dir.mkdir(parents=True)
        session = PersonaSession(
            persona_id="admin",
            user_id="uuid-123",
            email="admin@test.local",
            role="admin",
            session_token="tok_client_test",
        )
        (sessions_dir / "admin.json").write_text(session.model_dump_json())

        client = create_persona_client(tmp_path, "http://localhost:8000", persona="admin")
        assert isinstance(client, httpx_mod.AsyncClient)
        assert client.cookies.get("dazzle_session") == "tok_client_test"

    def test_create_persona_client_no_stored_session(self, tmp_path: Path) -> None:
        import httpx as httpx_mod

        from dazzle.agent.client_factory import create_persona_client

        client = create_persona_client(tmp_path, "http://localhost:8000", persona="nonexistent")
        assert isinstance(client, httpx_mod.AsyncClient)
        # Should not crash, just return plain client
        assert len(client.cookies) == 0


# =============================================================================
# Handler tests
# =============================================================================


class TestDslTestHandlers:
    async def test_create_sessions_handler(self, tmp_path: Path) -> None:
        """Test the MCP create_sessions handler."""
        from dazzle.mcp.server.handlers.dsl_test import create_sessions_handler

        # Will fail because no server is running, but should not crash
        result_str = await create_sessions_handler(tmp_path, {"base_url": "http://localhost:99999"})
        result = json.loads(result_str)
        # Should return an error about failing to load project or connect
        assert "error" in result

    async def test_diff_personas_handler_no_route(self, tmp_path: Path) -> None:
        """Test diff_personas_handler requires a route."""
        from dazzle.mcp.server.handlers.dsl_test import diff_personas_handler

        result_str = await diff_personas_handler(tmp_path, {"base_url": "http://localhost:8000"})
        result = json.loads(result_str)
        assert "error" in result
        assert "route" in result["error"]
