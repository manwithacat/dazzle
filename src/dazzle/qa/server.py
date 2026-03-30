"""Process lifecycle management for the Dazzle QA toolkit.

Starts a Dazzle app, polls for health, and cleans up on exit.
Also supports connecting to already-running instances.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AppConnection:
    """Represents a connection to a running Dazzle application.

    May be externally managed (is_external=True) or owned by this process
    (is_external=False, process is set).
    """

    site_url: str
    api_url: str
    process: subprocess.Popen[bytes] | None = field(default=None)

    @property
    def is_external(self) -> bool:
        """True when we do not own the server process."""
        return self.process is None

    def stop(self) -> None:
        """Terminate the owned process.  No-op for external connections."""
        if self.process is None:
            return
        if self.process.poll() is not None:
            # Already exited.
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


def connect_app(
    *,
    url: str | None = None,
    api_url: str | None = None,
    project_dir: Path | None = None,
) -> AppConnection:
    """Return an AppConnection for an existing or new Dazzle server.

    Exactly one of *url* or *project_dir* must be supplied.

    - ``url``: Connect to an already-running instance.  ``api_url`` defaults to
      the same host with port 8000 (replacing :3000).
    - ``project_dir``: Launch ``dazzle serve --local`` from the given directory.
    """
    if url is None and project_dir is None:
        raise ValueError("Either url or project_dir must be provided")

    if url is not None:
        resolved_api_url = api_url if api_url is not None else _infer_api_url(url)
        return AppConnection(site_url=url, api_url=resolved_api_url)

    # project_dir path — start the server.
    return _start_app(project_dir=project_dir)  # type: ignore[arg-type]


def _infer_api_url(site_url: str) -> str:
    """Derive the API URL from the site URL by replacing port 3000 with 8000."""
    return site_url.replace(":3000", ":8000")


def _start_app(*, project_dir: Path) -> AppConnection:
    """Launch ``dazzle serve --local`` and return an AppConnection."""
    env = {**os.environ, "DAZZLE_TEST_SECRET": "qa-toolkit"}
    cmd = [sys.executable, "-m", "dazzle", "serve", "--local"]
    proc: subprocess.Popen[bytes] = subprocess.Popen(
        cmd,
        cwd=str(project_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    site_url = "http://localhost:3000"
    api_url = "http://localhost:8000"
    return AppConnection(site_url=site_url, api_url=api_url, process=proc)


async def _poll_health(
    api_url: str,
    *,
    timeout: float = 30,
    client: object | None = None,
) -> bool:
    """Poll ``{api_url}/docs`` until a 200 response or *timeout* seconds elapse.

    Returns True on success, False on timeout.

    An optional *client* may be injected for testing; it must expose an async
    ``get(url)`` method that returns an object with a ``status_code`` attribute.
    """
    import asyncio

    health_url = f"{api_url}/docs"
    elapsed = 0.0
    interval = 0.5

    async def _do_get(c: object) -> int:
        resp = await c.get(health_url)  # type: ignore[attr-defined]
        return int(resp.status_code)

    if client is not None:
        while elapsed < timeout:
            try:
                status = await _do_get(client)
                if status == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(interval)
            elapsed += interval
        return False

    # Default: use httpx
    try:
        import httpx
    except ImportError:
        return False

    async with httpx.AsyncClient() as http:
        while elapsed < timeout:
            try:
                resp = await http.get(health_url)
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(interval)
            elapsed += interval
    return False


async def wait_for_ready(
    api_url: str,
    *,
    timeout: float = 30,
) -> bool:
    """Wait until the API server is healthy.

    Returns True when ``{api_url}/docs`` responds with 200, False on timeout.
    """
    return await _poll_health(api_url, timeout=timeout)
