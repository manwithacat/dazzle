"""Dazzle QA toolkit — AppConnection type and health polling.

AppConnection describes a live Dazzle server URL pair. It can be built two ways:
 - ``AppConnection.from_runtime_file(project_root)`` — read the deterministic
   ports from ``<project_root>/.dazzle/runtime.json`` that ``dazzle serve`` writes.
 - Direct construction by a runner (e.g., ``dazzle.e2e.runner.ModeRunner``),
   which owns the subprocess.

The old ``connect_app`` / ``_start_app`` helpers (which hardcoded :3000/:8000)
are deleted — ``dazzle.e2e.runner.ModeRunner`` is the launch primitive now.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AppConnection:
    """Represents a connection to a running Dazzle application.

    Externally managed (process is None, is_external=True) when read from
    runtime.json. Owned (process set, is_external=False) when launched by a
    runner that captures the Popen handle.
    """

    site_url: str
    api_url: str
    process: subprocess.Popen[bytes] | None = field(default=None)

    @property
    def is_external(self) -> bool:
        return self.process is None

    @classmethod
    def from_runtime_file(cls, project_root: Path) -> AppConnection:
        """Read ui_url/api_url from ``<project_root>/.dazzle/runtime.json``.

        ``dazzle serve`` writes this file on startup with the deterministic
        hashed port pair for the project. Raises ``FileNotFoundError`` if
        the file is absent (server not running, or still starting).
        """
        runtime_path = project_root / ".dazzle" / "runtime.json"
        if not runtime_path.exists():
            raise FileNotFoundError(f"{runtime_path} not found — dazzle serve may not be running")
        data = json.loads(runtime_path.read_text())
        return cls(site_url=data["ui_url"], api_url=data["api_url"], process=None)

    def stop(self) -> None:
        """Terminate the owned process. No-op for external connections."""
        if self.process is None:
            return
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


async def _poll_health(
    api_url: str,
    *,
    timeout: float = 30,
    client: object | None = None,
) -> bool:
    """Poll ``{api_url}/docs`` until 200 or timeout. Returns True on success."""
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
                if await _do_get(client) == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(interval)
            elapsed += interval
        return False

    try:
        import httpx
    except ImportError:
        return False

    async with httpx.AsyncClient() as http:
        while elapsed < timeout:
            try:
                if (await http.get(health_url)).status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(interval)
            elapsed += interval
    return False


async def wait_for_ready(api_url: str, *, timeout: float = 30) -> bool:
    """Wait until ``{api_url}/docs`` returns 200. True on success, False on timeout."""
    return await _poll_health(api_url, timeout=timeout)
