"""
Per-persona session management for testing and discovery.

Creates, stores, and retrieves authenticated sessions for each DSL-defined
persona. Sessions are stored as JSON in `.dazzle/test_sessions/` and can be
reused across test runs, discovery sessions, and differential analysis.

Usage:
    manager = SessionManager(project_path, base_url="http://localhost:8000")
    sessions = await manager.create_all_sessions(appspec)
    session = manager.load_session("admin")
    cookies = manager.get_cookies("admin")  # {"dazzle_session": "..."}
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger("dazzle.testing.session_manager")


# =============================================================================
# Models
# =============================================================================


class PersonaSession(BaseModel):
    """Stored session for a single persona."""

    persona_id: str
    user_id: str
    email: str
    role: str
    session_token: str
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    expires_at: str = ""
    base_url: str = ""


class SessionManifest(BaseModel):
    """Manifest tracking all persona sessions."""

    project_name: str = ""
    base_url: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    sessions: dict[str, PersonaSession] = Field(default_factory=dict)

    @property
    def persona_ids(self) -> list[str]:
        return list(self.sessions.keys())

    @property
    def is_stale(self) -> bool:
        """Check if any session is older than 24 hours."""
        threshold = datetime.now(UTC) - timedelta(hours=24)
        for session in self.sessions.values():
            try:
                created = datetime.fromisoformat(session.created_at)
                if created < threshold:
                    return True
            except (ValueError, TypeError):
                return True
        return False


# =============================================================================
# Session Manager
# =============================================================================


class SessionManager:
    """
    Manages per-persona authenticated sessions.

    Sessions are created via the app's ``/__test__/authenticate`` endpoint
    or ``/auth/login`` and stored in ``.dazzle/test_sessions/``.
    """

    def __init__(
        self,
        project_path: Path,
        base_url: str = "http://localhost:8000",
    ):
        self.project_path = Path(project_path)
        self.base_url = base_url.rstrip("/")
        self.sessions_dir = self.project_path / ".dazzle" / "test_sessions"
        self.manifest_path = self.sessions_dir / "manifest.json"

    # =========================================================================
    # Public API
    # =========================================================================

    async def create_session(
        self,
        persona_id: str,
        role: str | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> PersonaSession:
        """
        Create an authenticated session for a persona.

        Tries ``/__test__/authenticate`` first (works in test mode),
        then falls back to ``/auth/login``.

        Args:
            persona_id: The persona identifier (e.g. "admin", "agent")
            role: Role to assign. Defaults to persona_id.
            client: Optional httpx client. Creates one if not provided.

        Returns:
            The created PersonaSession.
        """
        role = role or persona_id
        close_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=30.0)

        try:
            session = await self._authenticate_via_test_endpoint(client, persona_id, role)
            if session is None:
                session = await self._authenticate_via_login(client, persona_id, role)
            if session is None:
                raise RuntimeError(
                    f"Could not authenticate persona '{persona_id}'. "
                    f"Ensure the app is running at {self.base_url} with "
                    f"test routes enabled or auth configured."
                )

            self._save_session(session)
            return session
        finally:
            if close_client:
                await client.aclose()

    async def create_all_sessions(
        self,
        appspec: Any,
        *,
        force: bool = False,
    ) -> SessionManifest:
        """
        Create sessions for all personas defined in the DSL.

        Args:
            appspec: Loaded AppSpec with personas.
            force: Recreate even if sessions exist and are fresh.

        Returns:
            SessionManifest with all created sessions.
        """
        # Check existing manifest
        if not force:
            manifest = self.load_manifest()
            if manifest and manifest.base_url == self.base_url and not manifest.is_stale:
                logger.info(
                    "Sessions are fresh (created %s), skipping recreation. "
                    "Use force=True to recreate.",
                    manifest.created_at,
                )
                return manifest

        personas = appspec.personas if hasattr(appspec, "personas") else []
        if not personas:
            logger.warning("No personas defined in DSL")
            return SessionManifest(
                project_name=getattr(appspec, "name", "unknown"),
                base_url=self.base_url,
            )

        manifest = SessionManifest(
            project_name=getattr(appspec, "name", "unknown"),
            base_url=self.base_url,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            for persona in personas:
                pid = str(getattr(persona, "id", None) or getattr(persona, "name", "unknown"))
                try:
                    session = await self.create_session(pid, client=client)
                    manifest.sessions[pid] = session
                    logger.info("Created session for persona '%s'", pid)
                except Exception as e:
                    logger.error("Failed to create session for '%s': %s", pid, e)

        self._save_manifest(manifest)
        return manifest

    def load_session(self, persona_id: str) -> PersonaSession | None:
        """Load a stored session for a persona."""
        session_file = self.sessions_dir / f"{persona_id}.json"
        if not session_file.exists():
            return None
        try:
            data = json.loads(session_file.read_text())
            return PersonaSession(**data)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Could not load session for '%s': %s", persona_id, e)
            return None

    def load_manifest(self) -> SessionManifest | None:
        """Load the session manifest."""
        if not self.manifest_path.exists():
            return None
        try:
            data = json.loads(self.manifest_path.read_text())
            return SessionManifest(**data)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Could not load manifest: %s", e)
            return None

    def get_cookies(self, persona_id: str) -> dict[str, str]:
        """
        Get cookie dict for a persona, suitable for httpx or requests.

        Returns:
            Dict like {"dazzle_session": "token..."} or empty dict.
        """
        session = self.load_session(persona_id)
        if session and session.session_token:
            return {"dazzle_session": session.session_token}
        return {}

    def get_httpx_cookies(self, persona_id: str) -> httpx.Cookies:
        """Get httpx.Cookies for a persona."""
        cookies = httpx.Cookies()
        session = self.load_session(persona_id)
        if session and session.session_token:
            cookies.set("dazzle_session", session.session_token)
        return cookies

    def list_sessions(self) -> list[str]:
        """List all persona IDs with stored sessions."""
        if not self.sessions_dir.exists():
            return []
        return [p.stem for p in self.sessions_dir.glob("*.json") if p.name != "manifest.json"]

    async def refresh_sessions(self, appspec: Any) -> SessionManifest:
        """Refresh all sessions (recreate expired ones)."""
        return await self.create_all_sessions(appspec, force=True)

    def cleanup(self) -> int:
        """Remove all stored sessions. Returns count of files removed."""
        if not self.sessions_dir.exists():
            return 0
        count = 0
        for f in self.sessions_dir.glob("*.json"):
            f.unlink()
            count += 1
        return count

    async def validate_session(
        self,
        persona_id: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> bool:
        """Check if a stored session is still valid by hitting /auth/me."""
        session = self.load_session(persona_id)
        if not session:
            return False

        close_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=10.0)

        try:
            resp = await client.get(
                f"{self.base_url}/auth/me",
                cookies={"dazzle_session": session.session_token},
            )
            return resp.status_code == 200
        except Exception:
            return False
        finally:
            if close_client:
                await client.aclose()

    # =========================================================================
    # Differential Analysis
    # =========================================================================

    async def diff_route(
        self,
        route: str,
        persona_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Fetch the same route as multiple personas and compare responses.

        Args:
            route: The route to fetch (e.g. "/contacts", "/workspaces/admin_dashboard")
            persona_ids: Personas to compare. Defaults to all stored sessions.

        Returns:
            Dict with per-persona response info (status, size, content hints).
        """
        if persona_ids is None:
            persona_ids = self.list_sessions()

        if not persona_ids:
            return {"error": "No persona sessions available"}

        url = route if route.startswith("http") else f"{self.base_url}{route}"
        results: dict[str, Any] = {}

        async with httpx.AsyncClient(timeout=30.0) as client:
            for pid in persona_ids:
                cookies = self.get_cookies(pid)
                try:
                    resp = await client.get(url, cookies=cookies, follow_redirects=True)
                    body = resp.text

                    # Count structural elements for comparison
                    row_count = body.count("<tr") - 1  # subtract header row
                    region_count = body.count("data-region=") or body.count("data-dazzle-view=")
                    line_count = len(body.splitlines())

                    results[pid] = {
                        "status": resp.status_code,
                        "content_length": len(body),
                        "line_count": line_count,
                        "table_rows": max(0, row_count),
                        "regions": region_count,
                        "final_url": str(resp.url),
                        "redirected": str(resp.url) != url,
                    }
                except Exception as e:
                    results[pid] = {"status": 0, "error": str(e)}

        return {
            "route": route,
            "url": url,
            "personas": results,
        }

    async def diff_routes(
        self,
        routes: list[str],
        persona_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Run diff_route for multiple routes."""
        results = []
        for route in routes:
            result = await self.diff_route(route, persona_ids)
            results.append(result)
        return results

    # =========================================================================
    # Private
    # =========================================================================

    async def _authenticate_via_test_endpoint(
        self,
        client: httpx.AsyncClient,
        persona_id: str,
        role: str,
    ) -> PersonaSession | None:
        """Try authenticating via /__test__/authenticate."""
        try:
            resp = await client.post(
                f"{self.base_url}/__test__/authenticate",
                json={"username": persona_id, "role": role},
            )
            if resp.status_code == 200:
                data = resp.json()
                return PersonaSession(
                    persona_id=persona_id,
                    user_id=data.get("user_id", ""),
                    email=f"{persona_id}@test.local",
                    role=role,
                    session_token=data.get("session_token", data.get("token", "")),
                    base_url=self.base_url,
                )
        except Exception as e:
            logger.debug("Test endpoint auth failed for '%s': %s", persona_id, e)
        return None

    async def _authenticate_via_login(
        self,
        client: httpx.AsyncClient,
        persona_id: str,
        role: str,
    ) -> PersonaSession | None:
        """Try authenticating via /auth/login.

        Uses credentials from (in priority order):
        1. DAZZLE_TEST_EMAIL / DAZZLE_TEST_PASSWORD environment variables
        2. .dazzle/test_credentials.json file
        3. Generated test credentials ({persona_id}@test.local / {persona_id}pass123)
        """
        import os

        email = os.environ.get("DAZZLE_TEST_EMAIL")
        password = os.environ.get("DAZZLE_TEST_PASSWORD")

        if not email or not password:
            # Try credentials file
            creds_path = self.project_path / ".dazzle" / "test_credentials.json"
            if creds_path.exists():
                try:
                    creds = json.loads(creds_path.read_text())
                    email = email or creds.get("email")
                    password = password or creds.get("password")
                except Exception:
                    pass

        if not email or not password:
            # Fall back to generated test credentials
            email = f"{persona_id}@test.local"
            password = f"{persona_id}pass123"  # nosec B105 - test-only credential

        try:
            resp = await client.post(
                f"{self.base_url}/auth/login",
                json={"email": email, "password": password},
            )
            if resp.status_code == 200:
                # Extract session token from Set-Cookie header
                session_token = ""  # nosec B105
                for cookie_header in resp.headers.get_list("set-cookie"):
                    if "dazzle_session=" in cookie_header:
                        session_token = cookie_header.split("dazzle_session=")[1].split(";")[0]
                        break

                data = resp.json()
                user_data = data.get("user", {})
                return PersonaSession(
                    persona_id=persona_id,
                    user_id=user_data.get("id", ""),
                    email=email,
                    role=role,
                    session_token=session_token,
                    base_url=self.base_url,
                )
        except Exception as e:
            logger.debug("Login auth failed for '%s': %s", persona_id, e)
        return None

    def _save_session(self, session: PersonaSession) -> None:
        """Save a session to disk."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        session_file = self.sessions_dir / f"{session.persona_id}.json"
        session_file.write_text(session.model_dump_json(indent=2))

    def _save_manifest(self, manifest: SessionManifest) -> None:
        """Save the manifest to disk."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(manifest.model_dump_json(indent=2))
