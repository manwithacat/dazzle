"""Conformance Role 2: HTTP execution engine.

Boots an in-process FastAPI app against PostgreSQL, seeds deterministic
fixture data, acquires per-persona auth tokens, and provides an async
HTTP client for conformance case assertions.

Requires:
- ``httpx`` with async support
- A PostgreSQL database (URL from ``CONFORMANCE_DATABASE_URL`` env var
  or ``database_url`` argument)
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .models import ConformanceCase, ConformanceFixtures

logger = logging.getLogger(__name__)


class ConformanceExecutor:
    """Manages the lifecycle of a conformance test session.

    Usage::

        executor = ConformanceExecutor(project_root, cases, fixtures)
        await executor.setup()
        try:
            results = await executor.run_all()
        finally:
            await executor.teardown()
    """

    def __init__(
        self,
        project_root: Any,
        cases: list[ConformanceCase],
        fixtures: ConformanceFixtures,
        database_url: str | None = None,
    ) -> None:
        self.project_root = project_root
        self.cases = cases
        self.fixtures = fixtures
        self.database_url = database_url or os.environ.get("CONFORMANCE_DATABASE_URL", "")
        self._client: Any | None = None
        self._app: Any | None = None
        self._auth_tokens: dict[str, str] = {}

    async def setup(self) -> None:
        """Boot the app, create tables, seed fixtures, acquire auth tokens."""
        import httpx

        from dazzle.core.appspec_loader import load_project_appspec
        from dazzle_back.runtime.app_factory import create_app

        if not self.database_url:
            raise RuntimeError(
                "No database URL for conformance testing. "
                "Set CONFORMANCE_DATABASE_URL or pass database_url."
            )

        appspec = load_project_appspec(self.project_root)

        # Boot the app with test mode enabled (mounts /__test__/* routes)
        self._app = create_app(
            appspec,
            database_url=self.database_url,
            enable_auth=True,
            enable_test_mode=True,
        )

        # Create async HTTP client against the in-process ASGI app
        transport = httpx.ASGITransport(app=self._app)
        self._client = httpx.AsyncClient(transport=transport, base_url="http://testserver")

        # Reset all entity tables via /__test__/reset
        resp = await self._client.post("/__test__/reset")
        if resp.status_code != 200:
            logger.warning("/__test__/reset returned %d: %s", resp.status_code, resp.text)

        # Seed fixture data via /__test__/seed
        await self._seed_fixtures()

        # Acquire auth tokens for each persona
        await self._acquire_tokens()

    async def _seed_fixtures(self) -> None:
        """Seed entity rows via the /__test__/seed endpoint."""
        assert self._client is not None

        seed_items: list[dict[str, Any]] = []
        for entity_name, rows in self.fixtures.entity_rows.items():
            for row in rows:
                # Build data dict excluding internal keys
                data = {k: v for k, v in row.items() if not k.startswith("_")}
                seed_items.append(
                    {
                        "id": data.pop("id"),
                        "entity": entity_name,
                        "data": data,
                    }
                )

        if not seed_items:
            logger.info("No fixture rows to seed")
            return

        resp = await self._client.post(
            "/__test__/seed",
            json={"fixtures": seed_items},
        )
        if resp.status_code != 200:
            logger.warning("/__test__/seed returned %d: %s", resp.status_code, resp.text)
        else:
            logger.info("Seeded %d fixture rows", len(seed_items))

    async def _acquire_tokens(self) -> None:
        """Get auth tokens for each unique persona in the case list."""
        assert self._client is not None

        personas = {c.persona for c in self.cases}
        # Skip synthetic personas that can't authenticate
        skip = {"unauthenticated", "unmatched_role"}

        for persona in sorted(personas - skip):
            resp = await self._client.post(
                "/__test__/authenticate",
                json={"username": persona, "password": f"conformance_{persona}", "role": persona},
            )
            if resp.status_code == 200:
                token = resp.json().get("session_token", "")
                self._auth_tokens[persona] = token
                logger.debug("Acquired token for persona %s", persona)
            else:
                logger.warning(
                    "Failed to authenticate persona %s: %d %s",
                    persona,
                    resp.status_code,
                    resp.text,
                )

    async def run_all(self) -> list[CaseResult]:
        """Execute all conformance cases and return results."""
        from .http_runner import run_case

        assert self._client is not None

        results: list[CaseResult] = []
        for case in self.cases:
            result = await run_case(self._client, case, self._auth_tokens, self.fixtures)
            results.append(result)

        return results

    async def teardown(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class CaseResult:
    """Result of executing a single ConformanceCase."""

    __slots__ = ("case", "passed", "actual_status", "actual_rows", "error")

    def __init__(
        self,
        case: ConformanceCase,
        passed: bool,
        actual_status: int,
        actual_rows: int | None = None,
        error: str | None = None,
    ) -> None:
        self.case = case
        self.passed = passed
        self.actual_status = actual_status
        self.actual_rows = actual_rows
        self.error = error

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"<CaseResult {status} {self.case.test_id} status={self.actual_status}>"
