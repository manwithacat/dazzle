"""
Factory for creating persona-authenticated HTTP clients.

Creates httpx.AsyncClient instances pre-configured with persona session
cookies from the session manager. Used by discovery agents and test
runners to make authenticated requests as specific personas.
"""

from __future__ import annotations

from pathlib import Path

import httpx


def create_persona_client(
    project_path: Path,
    base_url: str,
    persona: str | None = None,
    timeout: float = 30.0,
) -> httpx.AsyncClient:
    """
    Create an httpx.AsyncClient with persona session cookies pre-loaded.

    If no persona is specified or no session is found, returns a plain client.

    Args:
        project_path: Path to the Dazzle project.
        base_url: Base URL of the running application.
        persona: Persona ID to authenticate as (e.g. "admin").
        timeout: HTTP timeout in seconds.

    Returns:
        An httpx.AsyncClient, possibly with session cookies set.

    Example::

        client = create_persona_client(Path("./my-app"), "http://localhost:3000", "admin")
        observer = HttpObserver(client, "http://localhost:3000")
        executor = HttpExecutor(client, "http://localhost:3000", observer)
        agent = DazzleAgent(observer, executor)
        transcript = await agent.run(mission)
    """
    cookies = httpx.Cookies()

    if persona:
        try:
            from dazzle.testing.session_manager import SessionManager

            manager = SessionManager(project_path, base_url=base_url)
            cookie_dict = manager.get_cookies(persona)
            for key, value in cookie_dict.items():
                cookies.set(key, value)
        except ImportError:
            pass

    return httpx.AsyncClient(timeout=timeout, cookies=cookies)
