"""Tests for viewport session/auth bridge."""

import json
from pathlib import Path

import pytest

from dazzle.testing.viewport_auth import ensure_session_exists, load_persona_cookies


def _write_session(tmp_path: Path, persona_id: str, token: str) -> None:
    """Helper to write a session file."""
    sessions_dir = tmp_path / ".dazzle" / "test_sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_file = sessions_dir / f"{persona_id}.json"
    session_file.write_text(
        json.dumps(
            {
                "persona_id": persona_id,
                "user_id": "u-1",
                "email": f"{persona_id}@test.com",
                "role": persona_id,
                "session_token": token,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )


class TestLoadPersonaCookies:
    """Tests for load_persona_cookies()."""

    def test_loads_cookies_from_session_file(self, tmp_path: Path) -> None:
        _write_session(tmp_path, "admin", "tok-abc123")
        cookies = load_persona_cookies(tmp_path, "admin", "http://localhost:3000")
        assert len(cookies) == 1
        assert cookies[0]["name"] == "dazzle_session"
        assert cookies[0]["value"] == "tok-abc123"

    def test_returns_empty_when_no_session(self, tmp_path: Path) -> None:
        cookies = load_persona_cookies(tmp_path, "admin", "http://localhost:3000")
        assert cookies == []

    @pytest.mark.parametrize(
        "request_url, attribute, expected",
        [
            ("http://myapp.example.com:3000", "domain", "myapp.example.com"),
            ("http://localhost:3000", "domain", "localhost"),
            ("http://localhost:3000", "path", "/"),
        ],
        ids=[
            "test_cookie_domain_from_base_url",
            "test_cookie_domain_defaults_to_localhost",
            "test_cookie_path_is_root",
        ],
    )
    def test_cookie_attributes(
        self, tmp_path: Path, request_url: str, attribute: str, expected: str
    ) -> None:
        # Note: param name is `request_url` not `base_url` to avoid clash
        # with pytest-base-url plugin's session-scoped `base_url` fixture.
        _write_session(tmp_path, "admin", "tok-123")
        cookies = load_persona_cookies(tmp_path, "admin", request_url)
        assert cookies[0][attribute] == expected

    def test_returns_empty_when_no_token_in_file(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / ".dazzle" / "test_sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "admin.json").write_text(json.dumps({"persona_id": "admin"}))
        cookies = load_persona_cookies(tmp_path, "admin", "http://localhost:3000")
        assert cookies == []

    def test_handles_corrupt_json(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / ".dazzle" / "test_sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "admin.json").write_text("{corrupt json")
        cookies = load_persona_cookies(tmp_path, "admin", "http://localhost:3000")
        assert cookies == []


class TestEnsureSessionExists:
    """Tests for ensure_session_exists()."""

    def test_returns_true_when_session_exists(self, tmp_path: Path) -> None:
        _write_session(tmp_path, "admin", "tok-abc123")
        assert ensure_session_exists(tmp_path, "admin", "http://localhost:8000") is True

    def test_returns_false_when_no_session(self, tmp_path: Path) -> None:
        assert ensure_session_exists(tmp_path, "admin", "http://localhost:8000") is False

    def test_returns_false_when_no_token(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / ".dazzle" / "test_sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "admin.json").write_text(json.dumps({"persona_id": "admin"}))
        assert ensure_session_exists(tmp_path, "admin", "http://localhost:8000") is False
