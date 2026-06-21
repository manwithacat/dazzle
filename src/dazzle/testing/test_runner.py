"""
DAZZLE Test Runner - Execute test designs against a running the Dazzle runtime app.

This module provides a test harness that:
1. Loads test designs from dsl/tests/designs.json
2. Starts the the Dazzle runtime server (if needed)
3. Executes test steps via API calls
4. Reports pass/fail results

Usage:
    python -m dazzle.testing.test_runner [project_path]
    python -m dazzle.testing.test_runner --all-examples
"""

from __future__ import annotations  # required: forward reference

import json
import logging
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from dazzle.testing.field_value_gen import generate_field_value_from_str

logger = logging.getLogger(__name__)


class TestResult(StrEnum):
    """Result of a single test."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class StepResult:
    """Result of executing a single test step."""

    action: str
    target: str
    result: TestResult
    message: str = ""
    duration_ms: float = 0.0


@dataclass
class UICheckResult:
    """#1135: structured result from ``DazzleClient.check_ui_loads``.

    Pre-#1135, ``check_ui_loads`` returned a bare ``bool`` and the
    ``assert_visible`` step surfaced only "UI check failed" — no
    URL, no HTTP status, no body excerpt. Triage of 18 simultaneous
    ``WS_*_NAV`` failures across AegisMark cost ~an hour before
    the operator deduced the no-op ``navigate_to`` from source.

    Attributes:
        ok: True iff the page loaded (200 + ``<title>`` present).
        status: HTTP status code, or ``None`` if the request raised
            before getting a response.
        url: The URL actually fetched. Distinguishes the
            workspace-specific case (``navigate_to`` route resolved)
            from the bare ``ui_url`` fallback.
        excerpt: First 200 chars of the response body, OR
            ``repr(exception)`` if the request raised before a body
            was available.
    """

    ok: bool
    status: int | None
    url: str
    excerpt: str


@dataclass
class CleanupReport:
    """#1307: outcome of ``DazzleClient.cleanup_created_entities``.

    Pre-#1307 cleanup returned a bare ``(deleted, failed)`` tuple and counted
    every HTTP 404 at teardown as a *failure* — producing the alarming
    ``"N failed"`` line even though a 404 means the row is already gone (cleanup
    succeeded). The three-way split makes the report honest:

    - ``deleted`` — rows actually removed (200/204).
    - ``absent``  — rows already gone (404). Success for cleanup's purpose.
    - ``failed``  — genuine failures (auth/server/network); the row may persist.

    ``created_types`` is the set of entity types this run created, captured
    before the tracking list is cleared, so the caller can run the post-cleanup
    residue scan (``detect_residue``) over exactly those types.
    """

    deleted: int = 0
    absent: int = 0
    failed: int = 0
    created_types: list[str] = field(default_factory=list)


@dataclass
class TestCaseResult:
    """Result of executing a complete test case."""

    test_id: str
    title: str
    result: TestResult
    steps: list[StepResult] = field(default_factory=list)
    duration_ms: float = 0.0
    error_message: str = ""


@dataclass
class TestRunResult:
    """Result of a complete test run."""

    project_name: str
    started_at: datetime
    completed_at: datetime | None = None
    tests: list[TestCaseResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for t in self.tests if t.result == TestResult.PASSED)

    @property
    def failed(self) -> int:
        return sum(1 for t in self.tests if t.result == TestResult.FAILED)

    @property
    def skipped(self) -> int:
        return sum(1 for t in self.tests if t.result == TestResult.SKIPPED)

    @property
    def errors(self) -> int:
        return sum(1 for t in self.tests if t.result == TestResult.ERROR)

    @property
    def total(self) -> int:
        return len(self.tests)

    @property
    def runnable(self) -> int:
        """Number of tests that were actually run (not skipped)."""
        return self.passed + self.failed + self.errors

    @property
    def success_rate(self) -> float:
        """Success rate based on tests that were actually run."""
        if self.runnable == 0:
            return 100.0 if self.total == 0 else 0.0
        return (self.passed / self.runnable) * 100


class DazzleClient:
    """HTTP client for interacting with a the Dazzle runtime server."""

    MAX_RETRIES = 3
    BACKOFF_SECONDS = (1.0, 2.0, 4.0)

    def __init__(self, api_url: str, ui_url: str, timeout: float = 10.0):
        self.api_url = api_url.rstrip("/")
        self.ui_url = ui_url.rstrip("/")
        headers: dict[str, str] = {}
        test_secret = os.environ.get("DAZZLE_TEST_SECRET", "")
        if test_secret:
            headers["X-Test-Secret"] = test_secret
        self.client = httpx.Client(timeout=timeout, headers=headers)
        self._auth_token: str | None = None
        self._test_routes_available: bool | None = None  # None = unknown
        self._created_entities: list[tuple[str, str]] = []  # (entity_name, entity_id)

    def _ensure_csrf_token(self) -> None:
        """Acquire a CSRF token by making a GET request if we don't have one.

        Real latent bug fixed in today's debt-sweep: previously used
        ``self.base_url`` which doesn't exist on DazzleClient (fields
        are ``api_url`` and ``ui_url``). An AttributeError here would
        surface at test-run time whenever the CSRF cookie was absent
        and we ever reached the except-block branch. ``api_url`` is
        the correct target — `/health` is an API endpoint.
        """
        if self.client.cookies.get("dazzle_csrf"):
            return
        # Best-effort — server may not be ready yet (#smells-1.1).
        try:
            self.client.get(f"{self.api_url}/health")
        except Exception:
            logger.debug("CSRF priming health-check failed", exc_info=True)

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """HTTP request with automatic retry on timeout.

        Retries up to MAX_RETRIES times with exponential backoff (1s, 2s, 4s)
        when a request times out. Non-timeout errors are raised immediately.

        For mutation methods (POST/PUT/DELETE/PATCH), automatically injects
        the CSRF token from the dazzle_csrf cookie.
        """
        # Inject CSRF token for mutation requests
        if method.upper() in ("POST", "PUT", "DELETE", "PATCH"):
            self._ensure_csrf_token()
            csrf_token = self.client.cookies.get("dazzle_csrf")
            if csrf_token:
                headers = dict(kwargs.get("headers") or {})
                headers.setdefault("X-CSRF-Token", csrf_token)
                kwargs["headers"] = headers

        from dazzle.core.http_client import retrying_request

        return retrying_request(
            self.client,
            method,
            url,
            max_retries=self.MAX_RETRIES,
            backoff=self.BACKOFF_SECONDS,
            **kwargs,
        )

    def close(self) -> None:
        self.client.close()

    def health_check(self) -> bool:
        """Check if the server is healthy."""
        try:
            resp = self.client.get(f"{self.api_url}/health")
            return resp.status_code == 200
        except Exception:
            logger.debug("ignored exception in test_runner.py:184", exc_info=True)
            return False

    def wait_for_ready(self, max_wait: float = 30.0) -> bool:
        """Wait for server to become ready."""
        start = time.time()
        while time.time() - start < max_wait:
            if self.health_check():
                return True
            time.sleep(0.5)
        return False

    def reset_database(self) -> bool:
        """Reset the database to a clean state.

        Calls ``/__test__/reset`` when available (DAZZLE_ENV=test).
        Gracefully skips when test routes are not available (e.g. live sites).
        """
        if self._test_routes_available is False:
            return False
        try:
            resp = self._request("POST", f"{self.api_url}/__test__/reset")
            if resp.status_code == 404:
                self._test_routes_available = False
                return False
            self._test_routes_available = True
            return resp.status_code == 200
        except Exception:
            logger.debug("ignored exception in test_runner.py:211", exc_info=True)
            return False

    def seed_data(self, scenario: str | None = None) -> bool:
        """Seed the database with test data."""
        from datetime import timedelta

        try:
            # Create basic fixture data
            fixtures = []
            now = datetime.now()

            # Add some default entities based on common scenarios
            if scenario == "Active Sprint":
                fixtures.append(
                    {
                        "id": "task-1",
                        "entity": "Task",
                        "data": {"title": "Test Task 1", "status": "todo", "priority": "high"},
                    }
                )
                fixtures.append(
                    {
                        "id": "task-2",
                        "entity": "Task",
                        "data": {
                            "title": "Test Task 2",
                            "status": "in_progress",
                            "priority": "medium",
                        },
                    }
                )
            elif scenario == "Overdue Tasks":
                # Create tasks with past due dates
                past_date = (now - timedelta(days=5)).strftime("%Y-%m-%d")
                fixtures.append(
                    {
                        "id": "overdue-task-1",
                        "entity": "Task",
                        "data": {
                            "title": "Overdue Task 1",
                            "status": "todo",
                            "priority": "high",
                            "due_date": past_date,
                        },
                    }
                )
                fixtures.append(
                    {
                        "id": "overdue-task-2",
                        "entity": "Task",
                        "data": {
                            "title": "Overdue Task 2",
                            "status": "in_progress",
                            "priority": "urgent",
                            "due_date": past_date,
                        },
                    }
                )

            if not fixtures:
                return True  # Nothing to seed

            resp = self._request(
                "POST", f"{self.api_url}/__test__/seed", json={"fixtures": fixtures}
            )
            return resp.status_code == 200
        except Exception:
            logger.debug("ignored exception in test_runner.py:278", exc_info=True)
            return False

    def authenticate(self, persona: str) -> bool:
        """Authenticate as a persona for testing.

        Tries (in order):
        1. ``/__test__/authenticate`` — fast path when DAZZLE_ENV=test
        2. ``/auth/login`` with credentials from DAZZLE_TEST_EMAIL /
           DAZZLE_TEST_PASSWORD environment variables — works on live sites
        """
        # Try test endpoint first (unless we know it's unavailable)
        if self._test_routes_available is not False:
            try:
                resp = self._request(
                    "POST",
                    f"{self.api_url}/__test__/authenticate",
                    json={"role": persona, "username": f"test_{persona}"},
                )
                if resp.status_code == 200:
                    self._test_routes_available = True
                    data = resp.json()
                    token = data.get("token") or data.get("session_token")
                    self._auth_token = token
                    if token:
                        self.client.cookies.set("dazzle_session", token)
                    return True
                if resp.status_code == 404:
                    self._test_routes_available = False
            except Exception:
                logger.debug("Test login endpoint not available", exc_info=True)

        # Fallback: real auth via /auth/login
        return self._login_with_credentials(persona)

    def _login_with_credentials(self, persona: str = "admin") -> bool:
        """Authenticate using real credentials for a specific persona.

        Uses credentials from (in priority order):
        1. DAZZLE_TEST_EMAIL / DAZZLE_TEST_PASSWORD environment variables (admin only)
        2. .dazzle/test_credentials.json personas.<persona> section
        3. .dazzle/test_credentials.json top-level email/password (admin fallback)
        """
        email: str | None = None
        password: str | None = None

        # Env vars only apply to admin persona
        if persona == "admin":
            email = os.environ.get("DAZZLE_TEST_EMAIL")
            password = os.environ.get("DAZZLE_TEST_PASSWORD")

        if not email or not password:
            # Try credentials file
            creds_path = Path(".dazzle/test_credentials.json")
            if creds_path.exists():
                try:
                    creds = json.loads(creds_path.read_text(encoding="utf-8"))
                    personas = creds.get("personas", {})
                    persona_creds = personas.get(persona, {})
                    email = email or persona_creds.get("email")
                    password = password or persona_creds.get("password")
                    # Top-level fallback only for admin
                    if persona == "admin":
                        email = email or creds.get("email")
                        password = password or creds.get("password")
                except Exception:
                    logger.warning("Failed to load test credentials", exc_info=True)

        if not email or not password:
            return False

        try:
            resp = self._request(
                "POST",
                f"{self.api_url}/auth/login",
                json={"email": email, "password": password},
            )
            if resp.status_code == 200:
                # Session cookie is auto-captured by httpx from Set-Cookie
                data = resp.json()
                token = data.get("token") or data.get("session_token")
                self._auth_token = token
                if token:
                    self.client.cookies.set("dazzle_session", token)
                return True
            return False
        except Exception:
            logger.debug("ignored exception in test_runner.py:364", exc_info=True)
            return False

    def get_entities(self, entity_name: str) -> list[dict[str, Any]]:
        """Get all entities of a type."""
        try:
            # Prefer test endpoint (returns raw JSON)
            if self._test_routes_available is not False:
                resp = self._request(
                    "GET",
                    f"{self.api_url}/__test__/entity/{entity_name}",
                    headers=self._auth_headers(),
                )
                if resp.status_code == 200:
                    return list(resp.json())
                if resp.status_code == 404:
                    self._test_routes_available = False

            # Fallback to standard list endpoint
            endpoint = self._entity_endpoint(entity_name)
            resp = self._request(
                "GET",
                f"{self.api_url}{endpoint}",
                headers=self._auth_headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                # List endpoint may return {items: [...]} or [...] directly
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "items" in data:
                    return list(data["items"])
            return []
        except Exception:
            logger.debug("ignored exception in test_runner.py:397", exc_info=True)
            return []

    def create_entity(self, entity_name: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new entity, preferring ``/__test__/seed`` then standard CRUD."""
        try:
            # Use __test__/seed when available (bypasses auth)
            if self._test_routes_available is not False:
                # #1210: uuid4 hex (not int(time.time())) — two entities
                # created in the same second previously collided on
                # fixture_id, silently dropping one from
                # ``_created_entities`` and leaking it past --cleanup.
                fixture_id = f"test-{entity_name.lower()}-{uuid4().hex}"
                fixtures = [{"id": fixture_id, "entity": entity_name, "data": data}]
                resp = self._request(
                    "POST", f"{self.api_url}/__test__/seed", json={"fixtures": fixtures}
                )
                if resp.status_code == 200:
                    result: dict[str, Any] = resp.json()
                    created: dict[str, Any] = result.get("created", {})
                    created_entity = created.get(fixture_id)
                    if created_entity and "id" in created_entity:
                        self._created_entities.append((entity_name, str(created_entity["id"])))
                    return created_entity
                if resp.status_code == 404:
                    self._test_routes_available = False

            # Standard CRUD endpoint with auth
            endpoint = self._entity_endpoint(entity_name)
            resp = self._request(
                "POST", f"{self.api_url}{endpoint}", json=data, headers=self._auth_headers()
            )
            if resp.status_code in (200, 201):
                result_data = dict(resp.json())
                if "id" in result_data:
                    self._created_entities.append((entity_name, str(result_data["id"])))
                return result_data
            return None
        except Exception as e:
            print(f"    Create error: {e}")
            return None

    def _entity_endpoint(self, entity_name: str) -> str:
        """Derive the REST endpoint for an entity name.

        Uses to_api_plural for proper English pluralization:
        Contact -> /contacts, Company -> /companies, Address -> /addresses
        """
        from dazzle.core.strings import to_api_plural

        return f"/{to_api_plural(entity_name)}"

    def update_entity(
        self, entity_name: str, entity_id: str, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update an entity."""
        try:
            endpoint = f"{self._entity_endpoint(entity_name)}/{entity_id}"
            resp = self._request(
                "PUT", f"{self.api_url}{endpoint}", json=data, headers=self._auth_headers()
            )
            if resp.status_code == 200:
                return dict(resp.json())
            return None
        except Exception:
            logger.debug("ignored exception in test_runner.py:457", exc_info=True)
            return None

    def delete_entity(self, entity_name: str, entity_id: str) -> str:
        """Delete an entity by ID. Tries __test__ route first, then standard REST.

        Returns a three-state outcome (#1307):

        - ``"deleted"`` — the row was removed (HTTP 200/204).
        - ``"absent"``  — the row was already gone (HTTP 404). For *cleanup*
          this is success, not failure: a 404 means the target id does not
          exist, so there is nothing to clean up. Counting it as a failure
          produced the misleading ``"N failed"`` teardown alarm.
        - ``"failed"``  — a genuine failure (auth/permission/server error/
          network) where the row may still exist.
        """
        try:
            if self._test_routes_available is not False:
                resp = self._request(
                    "DELETE", self.api_url + "/__test__/entity/" + entity_name + "/" + entity_id
                )
                if resp.status_code == 200:
                    return "deleted"
                if resp.status_code == 403:
                    # Missing X-Test-Secret — don't fall through to REST
                    return "failed"
                if resp.status_code == 404 and "Unknown entity" not in resp.text:
                    # Ambiguous: either the test route is unavailable OR the id
                    # is already gone. Preserve the established behaviour — mark
                    # test routes unavailable and fall through to REST, which
                    # disambiguates (a REST 404 → genuinely absent).
                    self._test_routes_available = False
                elif resp.status_code >= 500:
                    # Server error — don't waste time on REST fallback
                    return "failed"

            endpoint = self._entity_endpoint(entity_name)
            resp = self._request(
                "DELETE",
                self.api_url + endpoint + "/" + entity_id,
                headers=self._auth_headers(),
            )
            if resp.status_code in (200, 204):
                return "deleted"
            if resp.status_code == 404:
                # Row already gone — for cleanup this is success, not failure.
                return "absent"
            return "failed"
        except Exception:
            logger.debug("ignored exception in test_runner.py:485", exc_info=True)
            return "failed"

    def _build_fk_reverse_map(self) -> dict[str, list[tuple[str, str]]]:
        """Build a map of parent_entity → [(child_entity, fk_field), ...] from the app spec.

        Used by cleanup to cascade-delete child records before parents.
        """
        result: dict[str, list[tuple[str, str]]] = {}
        spec = self.get_spec()
        if not spec:
            return result
        entities = spec.get("entities") or []
        if not entities:
            # Try domain.entities (full spec format)
            domain = spec.get("domain") or {}
            entities = domain.get("entities") or []
        for entity in entities:
            entity_name = entity.get("name", "")
            for fld in entity.get("fields", []):
                ftype = fld.get("type") or {}
                if ftype.get("kind") == "ref" and ftype.get("ref_entity"):
                    parent = ftype["ref_entity"]
                    result.setdefault(parent, []).append((entity_name, fld["name"]))
        return result

    def _topo_sort_for_delete(
        self,
        fk_map: dict[str, list[tuple[str, str]]],
    ) -> list[tuple[str, str]]:
        """Sort tracked entities so children come before parents.

        Uses the FK reverse map to determine entity-type ordering:
        if entity B has a FK to entity A, B must be deleted first.
        Within each type-level, entities keep their LIFO order.
        """
        tracked_types: set[str] = {name for name, _id in self._created_entities}

        # Build adjacency list: child → parent (child must be deleted first).
        # Kahn's algorithm processes nodes with in_degree 0 first, so children
        # (no incoming edges) get the lowest order indices.
        successors: dict[str, set[str]] = {t: set() for t in tracked_types}
        in_degree: dict[str, int] = dict.fromkeys(tracked_types, 0)
        for parent_type, children in fk_map.items():
            if parent_type not in tracked_types:
                continue
            for child_type, _fk_field in children:
                if child_type in tracked_types and parent_type not in successors[child_type]:
                    successors[child_type].add(parent_type)
                    in_degree[parent_type] += 1

        # Deterministic LIFO ordering for tie-breaking (preserves LIFO for
        # unrelated types that all have in_degree 0).
        lifo_types = list(dict.fromkeys(name for name, _id in reversed(self._created_entities)))
        queue = [t for t in lifo_types if in_degree[t] == 0]

        type_order: dict[str, int] = {}
        order_idx = 0
        while queue:
            t = queue.pop(0)
            type_order[t] = order_idx
            order_idx += 1
            for succ in successors.get(t, set()):
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

        # Types not in type_order (cycles) get highest index (delete last)
        max_order = order_idx
        for t in tracked_types:
            if t not in type_order:
                type_order[t] = max_order

        # Stable sort: primary by type_order (children=low, parents=high),
        # secondary preserves LIFO within same type-level.
        reversed_entities = list(reversed(self._created_entities))
        reversed_entities.sort(key=lambda pair: type_order.get(pair[0], max_order))
        return reversed_entities

    def cleanup_created_entities(self) -> CleanupReport:
        """Delete all tracked entities in dependency-safe order.

        Uses the FK graph to topologically sort tracked entities so children
        are deleted before parents. Only deletes entities that were created
        during this test run — **no API queries for untracked records** (the
        #410 invariant; the residue scan is a *separate* phase, see
        ``detect_residue``). Uses multi-pass for remaining FK constraint
        failures.

        Returns a :class:`CleanupReport` (#1307) splitting deleted / absent
        (404 → already gone) / failed, plus the set of created entity types.
        """
        created_types = sorted({name for name, _id in self._created_entities})
        if not self._created_entities:
            return CleanupReport(created_types=created_types)

        # Build FK graph and sort tracked entities
        fk_map = self._build_fk_reverse_map()
        pending = self._topo_sort_for_delete(fk_map)

        # Deduplicate (same entity may be tracked multiple times)
        seen: set[tuple[str, str]] = set()
        unique_pending: list[tuple[str, str]] = []
        for pair in pending:
            if pair not in seen:
                seen.add(pair)
                unique_pending.append(pair)
        pending = unique_pending

        deleted = 0
        absent = 0
        max_passes = 3

        for pass_num in range(max_passes):
            still_pending: list[tuple[str, str]] = []
            pass_progress = 0
            for entity_name, entity_id in pending:
                outcome = self.delete_entity(entity_name, entity_id)
                if outcome == "deleted":
                    deleted += 1
                    pass_progress += 1
                elif outcome == "absent":
                    # Already gone — success for cleanup. Don't retry (a 404
                    # won't become a 200 on a later pass).
                    absent += 1
                    pass_progress += 1
                else:
                    still_pending.append((entity_name, entity_id))
            pending = still_pending
            if not pending:
                break
            # Bail if no progress after first pass — retrying won't help
            if pass_num > 0 and pass_progress == 0:
                break

        self._created_entities.clear()
        return CleanupReport(
            deleted=deleted,
            absent=absent,
            failed=len(pending),
            created_types=created_types,
        )

    def detect_residue(self, entity_types: list[str]) -> dict[str, int]:
        """Count test-data rows still present after cleanup (#1307).

        A SEPARATE phase from ``cleanup_created_entities`` (which is delete-only,
        per the #410 invariant) — this one *does* query the API. For each given
        entity type it lists the rows and counts those bearing this run's
        test-data signature (``is_generated_test_value`` — every runner-created
        row carries at least one generated string field). A nonzero count means
        cleanup left rows behind: rows the runner created but whose ids it never
        tracked (e.g. cascade-created children, or an id the create response
        didn't surface), which tracked-id deletion can't reach.

        Returns ``{entity_type: leftover_count}`` for types with residue > 0.
        Best-effort: a per-type query failure is skipped, not fatal.
        """
        from dazzle.core.field_values import is_generated_test_value

        residue: dict[str, int] = {}
        for entity_name in sorted(set(entity_types)):
            try:
                rows = self.get_entities(entity_name)
            except Exception:
                logger.debug("residue scan: get_entities(%s) failed", entity_name, exc_info=True)
                continue
            count = sum(
                1
                for row in rows
                if isinstance(row, dict) and any(is_generated_test_value(v) for v in row.values())
            )
            if count:
                residue[entity_name] = count
        return residue

    def get_spec(self) -> dict[str, Any] | None:
        """Get the app spec."""
        try:
            # Use /spec endpoint which returns full spec including workspaces
            resp = self._request("GET", f"{self.api_url}/spec")
            if resp.status_code == 200:
                return dict(resp.json())
            return None
        except Exception:
            logger.debug("ignored exception in test_runner.py:619", exc_info=True)
            return None

    def get_entity_schema(self, entity_name: str) -> dict[str, Any] | None:
        """Get entity schema including required fields."""
        try:
            resp = self._request("GET", f"{self.api_url}/_dazzle/entity/{entity_name}")
            if resp.status_code == 200:
                return dict(resp.json())
            return None
        except Exception:
            logger.debug("ignored exception in test_runner.py:629", exc_info=True)
            return None

    def generate_entity_data(
        self,
        entity_name: str,
        overrides: dict[str, Any] | None = None,
        create_refs: bool = True,
        _ref_depth: int = 0,
    ) -> dict[str, Any]:
        """Generate valid test data for an entity based on its schema.

        Args:
            entity_name: The entity type to generate data for
            overrides: Field values to override the generated ones
            create_refs: If True, create referenced entities and include their IDs
            _ref_depth: Internal recursion depth counter (max 3 levels)
        """
        import re

        schema = self.get_entity_schema(entity_name)
        if not schema:
            return overrides or {}

        data = {}
        for fld in schema.get("fields", []):
            name = fld.get("name", "")
            field_type_orig = fld.get("type", "")  # Preserve original case
            field_type = field_type_orig.lower()
            required = fld.get("required", False)
            unique = fld.get("unique", False)
            max_length = fld.get("max_length")
            # Fallback: parse max_length from type string like "str(8)"
            if max_length is None and "str" in field_type:
                ml_match = re.search(r"str\((\d+)\)", field_type)
                if ml_match:
                    max_length = int(ml_match.group(1))

            # Skip auto-generated fields
            if name in ("id", "created_at", "updated_at"):
                continue

            # Handle reference fields
            if "ref" in field_type:
                if required and create_refs and _ref_depth < 3:
                    # Extract the referenced entity name from "ref(EntityName)"
                    # Use original case field_type to preserve entity name case
                    ref_match = re.search(r"ref\((\w+)\)", field_type_orig)
                    if ref_match:
                        ref_entity = ref_match.group(1)
                        # Create the referenced entity (with depth-limited recursion)
                        ref_data = self.generate_entity_data(
                            ref_entity, create_refs=True, _ref_depth=_ref_depth + 1
                        )
                        ref_result = self.create_entity(ref_entity, ref_data)
                        if ref_result and "id" in ref_result:
                            # Use the field name directly (the ref stores the ID)
                            data[name] = ref_result["id"]
                continue

            if required:
                data[name] = self._generate_field_value(name, field_type, unique, max_length)

        # Apply overrides
        if overrides:
            data.update(overrides)

        # Regenerate unique fields after overrides — design-time values
        # from test JSON files are generated once and become stale across
        # runs, causing unique-constraint collisions in the database.
        # Skip ref fields: their override values are $ref:-resolved UUIDs
        # pointing to real parent entities, not stale strings.
        if overrides:
            for fld in schema.get("fields", []):
                fname = fld.get("name", "")
                ftype = fld.get("type", "").lower()
                if fld.get("unique", False) and fname in overrides and fname not in ("id",):
                    if "ref" in ftype:
                        continue
                    ml = fld.get("max_length")
                    if ml is None and "str" in ftype:
                        ml_m = re.search(r"str\((\d+)\)", ftype)
                        if ml_m:
                            ml = int(ml_m.group(1))
                    data[fname] = self._generate_field_value(
                        fname, ftype, unique=True, max_length=ml
                    )

        return data

    def _generate_field_value(
        self, name: str, field_type: str, unique: bool = False, max_length: int | None = None
    ) -> Any:
        """Generate a test value for a field type, respecting max_length."""
        return generate_field_value_from_str(name, field_type, unique=unique, max_length=max_length)

    def check_ui_loads(self, url: str | None = None) -> UICheckResult:
        """Check if the UI loads successfully (#1135).

        Returns a ``UICheckResult`` with the URL fetched, HTTP status,
        and body excerpt — enough for the operator to diagnose a
        failure without reading framework source. Pre-#1135, returned
        a bare ``bool`` and the caller had no way to surface context.

        Args:
            url: URL to fetch. Defaults to ``self.ui_url`` — the
                workspace-aware caller (``_execute_assert_visible_step``)
                resolves a per-step URL from the preceding
                ``navigate_to`` step and passes it here.
        """
        target = url or self.ui_url
        try:
            resp = self._request("GET", target)
        except Exception as exc:
            logger.debug("check_ui_loads: GET %s raised %r", target, exc, exc_info=True)
            return UICheckResult(ok=False, status=None, url=target, excerpt=repr(exc))
        body = resp.text or ""
        ok = resp.status_code == 200 and "<title>" in body
        return UICheckResult(
            ok=ok,
            status=resp.status_code,
            url=target,
            excerpt=body[:200],
        )

    def _auth_headers(self) -> dict[str, str]:
        """Get authentication headers."""
        if self._auth_token:
            return {"Authorization": f"Bearer {self._auth_token}"}
        return {}


class TestRunner:
    """Execute test designs against a the Dazzle runtime app."""

    def __init__(
        self,
        project_path: Path,
        api_port: int = 8000,
        ui_port: int = 3000,
        api_url: str | None = None,
        ui_url: str | None = None,
        persona: str | None = None,
        cleanup: bool = False,
    ):
        self.project_path = project_path
        self.api_port = api_port
        self.ui_port = ui_port
        self.api_url = api_url or f"http://localhost:{api_port}"
        self.ui_url = ui_url or f"http://localhost:{ui_port}"
        self.designs_path = project_path / "dsl" / "tests" / "designs.json"
        self.client: DazzleClient | None = None
        self._server_process: subprocess.Popen[str] | None = None
        self._persona = persona
        self._cleanup = cleanup
        # #1224: map of surface/workspace name → relative URL path. Built
        # lazily on first lookup so we don't pay parse cost when running
        # API-only tests. Replaces the previous hardcoded
        # `/app/workspaces/{name}` template that 17 nightly tests on
        # v0.71.161 failed against.
        self._surface_url_map: dict[str, str] | None = None

    def _inject_persona_session(self) -> None:
        """Inject stored persona session cookie into the client."""
        if not self._persona or not self.client:
            return
        try:
            from .session_manager import SessionManager

            manager = SessionManager(self.project_path, base_url=self.api_url)
            cookies = manager.get_cookies(self._persona)
            if cookies:
                for key, value in cookies.items():
                    self.client.client.cookies.set(key, value)
                print(f"    Authenticated as persona '{self._persona}' (stored session)")
            else:
                # Fall back to /__test__/authenticate
                if self.client.authenticate(self._persona):
                    print(f"    Authenticated as persona '{self._persona}' (test endpoint)")
                else:
                    print(f"    WARNING: Could not authenticate as persona '{self._persona}'")
        except ImportError:
            # Session manager not available, use test endpoint
            if self.client.authenticate(self._persona):
                print(f"    Authenticated as persona '{self._persona}' (test endpoint)")

    def load_designs(self) -> list[dict[str, Any]]:
        """Load test designs from JSON file."""
        if not self.designs_path.exists():
            return []

        with open(self.designs_path, encoding="utf-8") as f:
            data = json.load(f)
            return list(data.get("designs", []))

    def start_server(self) -> bool:
        """Start the the Dazzle runtime server."""
        # Kill any existing server
        subprocess.run(["pkill", "-f", "dazzle serve"], capture_output=True)
        time.sleep(1)

        # Start new server
        env = os.environ.copy()
        self._server_process = subprocess.Popen(
            [sys.executable, "-m", "dazzle", "dazzle", "serve", "--local"],
            cwd=self.project_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Wait for startup and extract ports
        start_time = time.time()
        stdout = self._server_process.stdout
        while time.time() - start_time < 15:
            if self._server_process.poll() is not None:
                # Process exited
                return False

            assert stdout is not None
            line = stdout.readline()
            if "UI:" in line:
                # Extract port
                try:
                    self.ui_port = int(line.split()[-1])
                except ValueError:
                    pass
            elif "API:" in line:
                try:
                    self.api_port = int(line.split()[-1])
                except ValueError:
                    pass
            elif "Press Ctrl+C" in line or "Frontend:" in line:
                # Server is ready
                break
            time.sleep(0.1)

        return True

    def stop_server(self) -> None:
        """Stop the the Dazzle runtime server."""
        if self._server_process:
            self._server_process.terminate()
            try:
                self._server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._server_process.kill()
            self._server_process = None

        # Also kill any orphaned processes
        subprocess.run(["pkill", "-f", "dazzle serve"], capture_output=True)

    def run_tests(self, accepted_only: bool = True) -> TestRunResult:
        """Run all test designs."""
        project_name = self.project_path.name
        result = TestRunResult(project_name=project_name, started_at=datetime.now())

        # Load designs
        designs = self.load_designs()
        if not designs:
            print(f"  No test designs found in {self.designs_path}")
            result.completed_at = datetime.now()
            return result

        if accepted_only:
            designs = [d for d in designs if d.get("status") == "accepted"]

        print(f"  Found {len(designs)} test designs")

        # Initialize client
        self.client = DazzleClient(api_url=self.api_url, ui_url=self.ui_url)

        # Wait for server
        if not self.client.wait_for_ready(max_wait=20):
            print("  ERROR: Server did not become ready")
            for design in designs:
                result.tests.append(
                    TestCaseResult(
                        test_id=design["test_id"],
                        title=design["title"],
                        result=TestResult.ERROR,
                        error_message="Server not ready",
                    )
                )
            result.completed_at = datetime.now()
            return result

        # Run each test
        for design in designs:
            test_result = self.run_single_test(design)
            result.tests.append(test_result)

            # Print progress
            status_icon = {
                TestResult.PASSED: "✓",
                TestResult.FAILED: "✗",
                TestResult.SKIPPED: "○",
                TestResult.ERROR: "!",
            }[test_result.result]
            print(f"    {status_icon} {design['test_id']}: {design['title']}")

        # Cleanup
        self.client.close()
        result.completed_at = datetime.now()

        return result

    def run_tests_from_designs(
        self,
        designs: list[dict[str, Any]],
        skip_e2e: bool = True,
        on_progress: Callable[[str], None] | None = None,
    ) -> TestRunResult:
        """Run tests from a provided list of designs (used by unified runner).

        Args:
            designs: List of test design dictionaries
            skip_e2e: If True, skip tests tagged with 'e2e' (they need Playwright)
        """
        project_name = self.project_path.name
        result = TestRunResult(project_name=project_name, started_at=datetime.now())

        if not designs:
            result.completed_at = datetime.now()
            return result

        # Filter out E2E tests if requested (they need Playwright)
        if skip_e2e:
            api_designs = []
            e2e_count = 0
            for d in designs:
                tags = d.get("tags", [])
                if "e2e" in tags:
                    e2e_count += 1
                    # Add skipped result for E2E tests
                    result.tests.append(
                        TestCaseResult(
                            test_id=d["test_id"],
                            title=d["title"],
                            result=TestResult.SKIPPED,
                            error_message="E2E test requires Playwright (run with --e2e)",
                        )
                    )
                else:
                    api_designs.append(d)
            if e2e_count > 0:
                print(f"    Skipping {e2e_count} E2E tests (run with Playwright for browser tests)")
            designs = api_designs

        if not designs:
            result.completed_at = datetime.now()
            return result

        # #1133 preflight: scan every design's steps for action types the
        # runner can't dispatch and surface them as a single ERROR-level
        # line. Pre-fix, each unknown action emitted a per-step WARNING
        # that flooded logs (hundreds per run) and silently degraded
        # tests whose setup depended on the skipped step. Failing loud
        # at the design boundary is the fix the issue asks for —
        # "either add a handler or stop emitting it".
        unknown_actions = self._scan_unknown_actions(designs)
        if unknown_actions:
            logger.error(
                "DSL test runner: %d unknown action type(s) found in %d design(s) — "
                "add a handler in test_runner._STEP_DISPATCH_* or update the "
                "designer to stop emitting them: %s",
                len(unknown_actions),
                len(designs),
                ", ".join(sorted(unknown_actions)),
            )

        # Initialize client
        self.client = DazzleClient(api_url=self.api_url, ui_url=self.ui_url)

        # Inject persona session cookie if configured
        if self._persona:
            self._inject_persona_session()

        # Wait for server
        if not self.client.wait_for_ready(max_wait=20):
            print("  ERROR: Server did not become ready")
            for design in designs:
                result.tests.append(
                    TestCaseResult(
                        test_id=design["test_id"],
                        title=design["title"],
                        result=TestResult.ERROR,
                        error_message="Server not ready",
                    )
                )
            result.completed_at = datetime.now()
            return result

        # Run each test
        total = len(designs)
        for idx, design in enumerate(designs, 1):
            test_result = self.run_single_test(design)
            result.tests.append(test_result)

            # Print progress
            status_icon = {
                TestResult.PASSED: "✓",
                TestResult.FAILED: "✗",
                TestResult.SKIPPED: "○",
                TestResult.ERROR: "!",
            }[test_result.result]
            msg = f"{status_icon} [{idx}/{total}] {design['test_id']}: {design['title']}"
            print(f"    {msg}")
            if on_progress is not None:
                on_progress(msg)

        # Cleanup created entities (#1307: honest deleted/absent/failed split +
        # a separate residue scan so an incomplete cleanup is loud, not silent).
        if self._cleanup and self.client:
            report = self.client.cleanup_created_entities()
            parts: list[str] = []
            if report.deleted:
                parts.append(f"{report.deleted} deleted")
            if report.absent:
                parts.append(f"{report.absent} already absent (404)")
            if report.failed:
                parts.append(f"{report.failed} failed")
            if parts:
                msg = "Cleanup: " + ", ".join(parts)
                print(f"    {msg}")
                if on_progress is not None:
                    on_progress(msg)

            # Residue scan (separate phase — queries the API). Catches rows the
            # runner created but never tracked (cascade children / untracked
            # ids), which tracked-id deletion can't reach — so cleanup that
            # reports success doesn't silently orphan rows.
            residue = self.client.detect_residue(report.created_types)
            if residue:
                total_residue = sum(residue.values())
                top = sorted(residue.items(), key=lambda kv: (-kv[1], kv[0]))
                breakdown = ", ".join(f"{name}={n}" for name, n in top[:8])
                more = "" if len(top) <= 8 else f", +{len(top) - 8} more"
                rmsg = (
                    f"Cleanup residue: {total_residue} test-data rows still present "
                    f"after teardown (tracking missed them — likely cascade-created "
                    f"or untracked ids): {breakdown}{more}"
                )
                print(f"    {rmsg}")
                if on_progress is not None:
                    on_progress(rmsg)

        self.client.close()
        result.completed_at = datetime.now()

        return result

    def run_single_test(self, design: dict[str, Any]) -> TestCaseResult:
        """Run a single test design."""
        assert self.client is not None
        test_id = design.get("test_id", "UNKNOWN")
        title = design.get("title", "Untitled")
        scenario = design.get("scenario")

        start_time = time.time()
        step_results: list[StepResult] = []

        # Context for storing step results (e.g., created entity IDs)
        context: dict[str, Any] = {
            "_persona": design.get("persona", "admin"),
            # #1211: stash design's surfaces so assert_visible can
            # auto-synthesise a URL when no navigate_to has run.
            "_design_surfaces": design.get("surfaces", []) or [],
        }

        try:
            # Reset database before each test
            self.client.reset_database()

            # Auto-authenticate for CRUD tests that lack an explicit login_as step.
            # When the server has auth enabled, unauthenticated requests return 401.
            steps = design.get("steps", [])
            has_login_step = any(s.get("action") == "login_as" for s in steps)
            tags = design.get("tags", [])
            is_crud = any(t in tags for t in ("crud", "validation"))

            if not has_login_step and is_crud:
                self.client.authenticate("admin")

            # Seed data if this is a scenario test that needs it
            if scenario and scenario not in ("Empty State",):
                self.client.seed_data(scenario)
            for step in steps:
                step_result = self.execute_step(step, design, context)
                step_results.append(step_result)

                # Stop on failure
                if step_result.result == TestResult.FAILED:
                    duration = (time.time() - start_time) * 1000
                    return TestCaseResult(
                        test_id=test_id,
                        title=title,
                        result=TestResult.FAILED,
                        steps=step_results,
                        duration_ms=duration,
                        error_message=step_result.message,
                    )

            # All steps passed
            duration = (time.time() - start_time) * 1000
            return TestCaseResult(
                test_id=test_id,
                title=title,
                result=TestResult.PASSED,
                steps=step_results,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return TestCaseResult(
                test_id=test_id,
                title=title,
                result=TestResult.ERROR,
                steps=step_results,
                duration_ms=duration,
                error_message=str(e),
            )

    # ── Per-action execute helpers ───────────────────────────────────────

    def _execute_login_as_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        success = self.client.authenticate(target)
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if success else TestResult.SKIPPED,
            message="" if success else "Auth not required or failed",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _resolve_surface_url(self, name: str) -> str | None:
        """#1224: resolve a surface/workspace name to its URL path.

        Returns ``None`` for unknown names or for kinds that need a
        record id (view / edit) — callers should fall through to a
        clear error rather than constructing a wrong URL.

        Pre-#1224, the test runner hardcoded ``/app/workspaces/{name}``
        for every surface kind, causing 17 TD-* tests to 404 on
        v0.71.161 because list / create surfaces have different URL
        templates that the route generator already knows but the
        runner did not.
        """
        if self._surface_url_map is None:
            self._surface_url_map = self._build_surface_url_map()
        return self._surface_url_map.get(name)

    def _build_surface_url_map(self) -> dict[str, str]:
        """Parse the project's DSL and build a surface-name → URL map (#1224).

        Templates mirror ``template_compiler.py``'s authoritative ``route_map``
        (``/app/{entity_slug}`` for LIST, ``/app/{entity_slug}/create`` for
        CREATE) — #1230 fixed a v0.71.x divergence where the resolver picked
        ``/{plural}`` (which Dazzle does not mount for UI surfaces, only the
        JSON API), producing 404s on CREATE walks and wrong-content checks on
        LIST walks.
        """
        from dazzle.core.ir import SurfaceMode
        from dazzle.core.linker import build_appspec
        from dazzle.core.parser import parse_modules

        out: dict[str, str] = {}
        dsl_dir = self.project_path / "dsl"
        if not dsl_dir.is_dir():
            return out
        try:
            modules = parse_modules(sorted(dsl_dir.glob("*.dsl")))
            if not modules:
                return out
            # build_appspec needs the *module* name (e.g. 'tinyapp.core'),
            # not the project directory name. Pick the first module —
            # dazzle apps conventionally have one root module per project.
            appspec = build_appspec(modules, modules[0].name)
        except Exception:  # noqa: BLE001 — best-effort URL resolution
            return out

        from dazzle.core.strings import entity_slug

        for ws in getattr(appspec, "workspaces", None) or []:
            out[ws.name] = f"/app/workspaces/{ws.name}"

        for surface in getattr(appspec, "surfaces", None) or []:
            entity = getattr(surface, "entity_ref", None)
            if entity is None:
                continue
            slug = entity_slug(entity)
            mode = getattr(surface, "mode", None)
            if mode == SurfaceMode.LIST:
                out[surface.name] = f"/app/{slug}"
            elif mode == SurfaceMode.CREATE:
                out[surface.name] = f"/app/{slug}/create"
            # view / edit need a record id — skip; callers see None and
            # fall through to a clear error rather than a wrong URL.
        return out

    def _execute_navigate_to_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        """#1135: stash the resolved route into the step context so a
        subsequent ``assert_visible`` actually checks the navigated
        workspace, not the bare ``ui_url``.

        Pre-#1135 this was a no-op stub — comment said "navigation is
        conceptual in API tests" — but the test design **does** carry
        the workspace route in ``data.route`` and the operator expects
        the next ``assert_visible`` to inspect that page. The no-op
        meant every ``WS_*_NAV`` test smoke-tested the same base URL
        with different cookies; failures couldn't be diagnosed because
        the message didn't say which URL was checked.
        """
        from urllib.parse import urljoin

        assert self.client is not None
        route = resolved_data.get("route") if resolved_data else None
        if not route:
            # #1224: when data.route is missing, resolve from the step's
            # target (surface or workspace name) via the route generator
            # templates. Previously the design's route was the only path
            # into _current_ui_url; assert_visible then fell back to a
            # hardcoded /app/workspaces/{surfaces[0]} template that 404'd
            # for any list/create surface or wrong-position dashboard.
            stripped_target = target.split(":", 1)[-1] if target else ""
            if stripped_target:
                route = self._resolve_surface_url(stripped_target)
        if route:
            # Resolve relative to the client's ui_url. urljoin handles
            # both absolute (``http://...``) and relative (``/app/x``)
            # forms; ``ui_url + "/"`` ensures the base is treated as a
            # directory so ``/app/x`` overrides cleanly.
            context["_current_ui_url"] = urljoin(self.client.ui_url + "/", route.lstrip("/"))
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED,
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_create_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        entity_name = target.replace("entity:", "")
        entity_data = self.client.generate_entity_data(entity_name, resolved_data)
        result = self.client.create_entity(entity_name, entity_data)
        success = result is not None
        if success and store_result and result:
            context[store_result] = result
        if success:
            # #1139: stash the actually-sent payload so a following
            # create_expect_error step can reproduce the unique-field
            # collision. generate_entity_data regenerates unique fields
            # whose literal values from the test design would otherwise
            # diverge between the two POSTs.
            context[f"_last_created_data:{entity_name}"] = entity_data
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if success else TestResult.FAILED,
            message="" if success else f"Create failed for {entity_name}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_update_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        return StepResult(
            action=action,
            target=target,
            result=TestResult.SKIPPED,
            message="Update requires entity ID context",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_visible_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        """#1135 / #1149: include URL + HTTP status + body excerpt in
        the failure message, plus a fix hint when the failure shape
        matches a known design omission (missing login_as or
        navigate_to).

        Pre-#1135 the message was the literal "UI check failed" —
        no URL, no status, no body. #1135 added the URL + status +
        excerpt. #1149 adds the fix hint: when the check hit the
        base UI URL (no preceding ``navigate_to``) AND got a 30x
        redirect, the design almost certainly needs ``login_as`` +
        ``navigate_to`` before this step. Rather than make the
        operator guess, the failure message names the missing
        steps explicitly.
        """
        assert self.client is not None
        # The preceding navigate_to step stashes the workspace URL in
        # context; fall back to the client's base ui_url when no
        # navigate happened.
        check_url = context.get("_current_ui_url")
        if not check_url:
            # #1211 fallback (revised in #1224): synthesise URL from the
            # design's first surface when no navigate_to has stashed
            # one. #1224 fix: dispatch by SurfaceKind via the route
            # generator's actual templates, not the hardcoded
            # /app/workspaces/{name} template that 404'd for every
            # list/create surface. surfaces[0] is still the source —
            # tests that emit bare assert_visible against multi-surface
            # designs are themselves ambiguous; the design author should
            # add an explicit navigate_to.
            surfaces = context.get("_design_surfaces") or []
            if surfaces:
                from urllib.parse import urljoin

                first = surfaces[0]
                first_name = first if isinstance(first, str) else first.get("name", "")
                resolved = self._resolve_surface_url(first_name) if first_name else None
                if resolved:
                    check_url = urljoin(self.client.ui_url + "/", resolved.lstrip("/"))
                    context["_current_ui_url"] = check_url
        result = self.client.check_ui_loads(url=check_url)
        # #1149: synthesise a fix hint from the failure shape.
        hint = ""
        if not result.ok:
            had_navigate = check_url is not None
            had_login = self.client._auth_token is not None or bool(
                self.client.client.cookies.get("dazzle_session")
            )
            hints: list[str] = []
            if result.status in (301, 302, 303, 307, 308) and not had_login:
                hints.append(
                    "GET → 3xx + no auth session: design is probably missing a "
                    "`login_as <persona>` step before this `assert_visible`."
                )
            if not had_navigate:
                hints.append(
                    "No preceding `navigate_to` — check hit the base UI url, not a "
                    "specific surface. Add `{action: navigate_to, target: workspace:<name>, "
                    "data: {route: '/app/...'}}` before this step."
                )
            if hints:
                hint = " | hint: " + " ".join(hints)
        message = (
            ""
            if result.ok
            else f"UI check failed: GET {result.url} → {result.status} | {result.excerpt!r}{hint}"
        )
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if result.ok else TestResult.FAILED,
            message=message,
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_count_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        data: dict[str, Any],
    ) -> StepResult:
        assert self.client is not None
        entity_name = target.replace("entity:", "")
        if entity_name.endswith("-card"):
            entity_name = entity_name[:-5]
        elif entity_name.endswith("-row"):
            entity_name = entity_name[:-4]
        entity_mapping = {
            "overdue-task": "Task",
            "task-card": "Task",
            "task-row": "Task",
            "user-row": "User",
            "device-row": "Device",
        }
        if entity_name in entity_mapping:
            entity_name = entity_mapping[entity_name]
        elif "-" in entity_name:
            entity_name = entity_name.replace("-", " ").title().replace(" ", "")
        elif entity_name.islower():
            entity_name = entity_name.capitalize()
        entities = self.client.get_entities(entity_name)
        min_count = data.get("min", 0)
        success = len(entities) >= min_count
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if success else TestResult.FAILED,
            message=f"Found {len(entities)} {entity_name} (min: {min_count})",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_ui_only_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        return StepResult(
            action=action,
            target=target,
            result=TestResult.SKIPPED,
            message="UI action skipped in API test",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_ui_assertion_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        return StepResult(
            action=action,
            target=target,
            result=TestResult.SKIPPED,
            message="UI assertion skipped",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_check_route_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        data: dict[str, Any],
    ) -> StepResult:
        assert self.client is not None
        if not target.startswith("workspace:"):
            return StepResult(
                action=action,
                target=target,
                result=TestResult.SKIPPED,
                message="Non-workspace route check skipped",
                duration_ms=(time.time() - start_time) * 1000,
            )
        workspace_name = target.replace("workspace:", "")
        route = data.get("route", f"/app/workspaces/{workspace_name}")
        try:
            resp = self.client._request(
                "GET", f"{self.client.ui_url}{route}", follow_redirects=True
            )
            if resp.status_code in (200, 304, 401):
                msg = f"Workspace '{workspace_name}' route exists"
                if resp.status_code == 401:
                    msg += " (protected)"
                return StepResult(
                    action=action,
                    target=target,
                    result=TestResult.PASSED,
                    message=msg,
                    duration_ms=(time.time() - start_time) * 1000,
                )
            return StepResult(
                action=action,
                target=target,
                result=TestResult.FAILED,
                message=f"Route {route} returned {resp.status_code}",
                duration_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            return StepResult(
                action=action,
                target=target,
                result=TestResult.FAILED,
                message=f"Route check failed: {e}",
                duration_ms=(time.time() - start_time) * 1000,
            )

    def _execute_e2e_only_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        return StepResult(
            action=action,
            target=target,
            result=TestResult.SKIPPED,
            message="E2E action skipped in API test",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_read_list_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        entity_name = target.replace("entity:", "")
        entities = self.client.get_entities(entity_name)
        context["last_response"] = type(
            "Response",
            (),
            {
                "status_code": 200,
                "cookies": {},
                "headers": {},
                "json": lambda: entities,
            },
        )()
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED,
            message=f"Retrieved {len(entities)} {entity_name} entities",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _track_post_cleanup(self, resp: Any, step: dict[str, Any] | None) -> None:
        """#1210: explicit-opt-in cleanup tracking for ``post`` / ``post_json``.

        If the step spec carries ``cleanup_entity: <EntityName>`` AND the
        response is 2xx with a JSON body containing an ``id``, append
        ``(EntityName, id)`` to the client's ``_created_entities`` list so
        the end-of-run ``--cleanup`` phase deletes it.

        Absent the hint, no tracking happens — this preserves existing
        behaviour for transition / auth / form POSTs that don't create
        entities (and would 404 on DELETE).
        """
        if step is None or self.client is None:
            return
        cleanup_entity = step.get("cleanup_entity")
        if not cleanup_entity:
            return
        status_code = getattr(resp, "status_code", None)
        if status_code is None or not (200 <= int(status_code) < 300):
            return
        try:
            body = resp.json()
        except Exception:
            logger.debug("post cleanup_entity: response body not JSON", exc_info=True)
            return
        if not isinstance(body, dict):
            return
        entity_id = body.get("id")
        if entity_id is None:
            return
        self.client._created_entities.append((str(cleanup_entity), str(entity_id)))

    def _execute_post_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        url = f"{self.client.ui_url}{target}"
        resp = self.client._request("POST", url, data=resolved_data, follow_redirects=False)
        context["last_response"] = resp
        self._track_post_cleanup(resp, _kw.get("step"))
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED,
            message=f"POST {target} → {resp.status_code}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_post_json_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        url = f"{self.client.api_url}{target}"
        resp = self.client._request("POST", url, json=resolved_data, follow_redirects=False)
        context["last_response"] = resp
        self._track_post_cleanup(resp, _kw.get("step"))
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED,
            message=f"POST(json) {target} → {resp.status_code}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_clear_cookies_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        self.client.client.cookies.clear()
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED,
            message="Cookies cleared",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_get_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        url = f"{self.client.ui_url}{target}"
        follow = resolved_data.get("follow_redirects", False)
        resp = self.client._request("GET", url, follow_redirects=follow)
        context["last_response"] = resp
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED,
            message=f"GET {target} → {resp.status_code}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_get_with_cookie_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        cookie_name = resolved_data.get("cookie", "dazzle_session")
        cookie_value = resolved_data.get("value", "invalid-token")
        follow = resolved_data.get("follow_redirects", False)
        url = f"{self.client.ui_url}{target}"
        resp = self.client._request(
            "GET",
            url,
            cookies={cookie_name: cookie_value},
            follow_redirects=follow,
        )
        context["last_response"] = resp
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED,
            message=f"GET {target} with {cookie_name}={cookie_value} → {resp.status_code}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_status_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        last_resp = context.get("last_response")
        if last_resp is None:
            return StepResult(
                action=action,
                target=target,
                result=TestResult.FAILED,
                message="No previous response to check",
                duration_ms=(time.time() - start_time) * 1000,
            )
        expected = resolved_data.get("status", 200)
        actual = last_resp.status_code
        success = actual == expected
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if success else TestResult.FAILED,
            message=f"Expected {expected}, got {actual}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_cookie_set_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        last_resp = context.get("last_response")
        cookie_name = resolved_data.get("cookie", "dazzle_session")
        has_cookie = (last_resp is not None and cookie_name in last_resp.cookies) or bool(
            self.client.client.cookies.get(cookie_name)
        )
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if has_cookie else TestResult.FAILED,
            message=f"Cookie '{cookie_name}' {'present' if has_cookie else 'missing'}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_no_cookie_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        last_resp = context.get("last_response")
        cookie_name = resolved_data.get("cookie", "dazzle_session")
        has_cookie = False
        if last_resp is not None and cookie_name in last_resp.cookies:
            cookie_val = last_resp.cookies.get(cookie_name)
            # Empty value or Max-Age=0 means the server is clearing, not setting
            if cookie_val and cookie_val != "":
                has_cookie = True
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if not has_cookie else TestResult.FAILED,
            message=f"Cookie '{cookie_name}' {'absent (good)' if not has_cookie else 'unexpectedly present'}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_cookie_cleared_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        last_resp = context.get("last_response")
        cookie_name = resolved_data.get("cookie", "dazzle_session")
        cleared = False
        if last_resp is not None:
            set_cookie_hdr = last_resp.headers.get("set-cookie", "")
            if cookie_name in set_cookie_hdr and "Max-Age=0" in set_cookie_hdr:
                cleared = True
            cookie_val = last_resp.cookies.get(cookie_name)
            if cookie_val is not None and (cookie_val == "" or cookie_val == '""'):
                cleared = True
        if not cleared:
            jar_val = self.client.client.cookies.get(cookie_name)
            if not jar_val or jar_val == "":
                cleared = True
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if cleared else TestResult.FAILED,
            message=f"Cookie '{cookie_name}' {'cleared' if cleared else 'still set'}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_redirect_url_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        last_resp = context.get("last_response")
        if last_resp is None:
            return StepResult(
                action=action,
                target=target,
                result=TestResult.FAILED,
                message="No previous response to check",
                duration_ms=(time.time() - start_time) * 1000,
            )
        expected_url = resolved_data.get("redirect_url", "/app")
        actual_url = last_resp.headers.get("location", "")
        if not actual_url:
            try:
                body = last_resp.json()
                actual_url = body.get("redirect_url", body.get("redirect", ""))
            except Exception:
                actual_url = ""
        if not actual_url:
            actual_url = last_resp.headers.get("hx-redirect", "")
        success = actual_url.rstrip("/").startswith(expected_url.rstrip("/"))
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if success else TestResult.FAILED,
            message=f"Expected redirect to '{expected_url}', got '{actual_url}'",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_unauthenticated_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        last_resp = context.get("last_response")
        if last_resp is None:
            return StepResult(
                action=action,
                target=target,
                result=TestResult.FAILED,
                message="No previous response to check",
                duration_ms=(time.time() - start_time) * 1000,
            )
        # 403 is included because workspace RBAC returns 403 for
        # unauthenticated users who lack the required persona role.
        expected_codes = resolved_data.get("expect", [401, 302, 403])
        actual = last_resp.status_code
        success = actual in expected_codes
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if success else TestResult.FAILED,
            message=f"Status {actual} {'matches' if success else 'not in'} {expected_codes}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_trigger_transition_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        return StepResult(
            action=action,
            target=target,
            result=TestResult.SKIPPED,
            message="Transition requires entity context",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_state_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        """#1138: SM_* state-machine assertion.

        Today the runner can't reliably resolve "which entity id" to
        re-fetch without a stable cross-step entity-context contract
        (see #1138 follow-up). Skipping cleanly here is strictly
        better than the pre-fix "Unknown test action — step skipped"
        warning + opaque downstream failure: a SKIP doesn't move the
        FAIL pile and surfaces a clear message in the run log.
        """
        return StepResult(
            action=action,
            target=target,
            result=TestResult.SKIPPED,
            message="assert_state requires entity-id context (not yet wired)",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_authenticated_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        """#1138 / #1142: assert the current session is authenticated.

        The canonical ACL test pattern emitted by ``dsl_test_generator``
        is ``login_as`` immediately followed by ``assert_authenticated``,
        so we cannot rely on ``context['last_response']`` — login_as
        doesn't populate it. Self-bootstrap with ``GET /auth/me``
        instead: a 2xx response with the auth headers in force means
        the session is valid; 401/403 means the server rejected it.
        Stash the response in ``context['last_response']`` so any
        following ``assert_error``-style step can introspect it too.

        Falls back to inspecting a pre-existing ``last_response`` when
        present, which keeps the alternative "login_as → probe → assert"
        pattern working.
        """
        assert self.client is not None
        last_resp = context.get("last_response")
        if last_resp is None:
            try:
                last_resp = self.client._request(
                    "GET",
                    f"{self.client.api_url}/auth/me",
                    headers=self.client._auth_headers(),
                )
            except Exception as e:
                return StepResult(
                    action=action,
                    target=target,
                    result=TestResult.FAILED,
                    message=f"/auth/me probe failed: {e}",
                    duration_ms=(time.time() - start_time) * 1000,
                )
            context["last_response"] = last_resp
        expected_codes = resolved_data.get("expect", list(range(200, 300)))
        actual = last_resp.status_code
        success = actual in expected_codes
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if success else TestResult.FAILED,
            message=f"Status {actual} {'matches' if success else 'not in'} {expected_codes}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_transition_expect_error_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        """#1138: sibling of ``create_expect_error`` for invalid state
        transitions. Currently SKIP — like ``trigger_transition``,
        the entity-id context contract isn't standardised yet, so a
        real PATCH-and-expect-4xx implementation would have a
        higher-than-acceptable false-fail rate. Stub clears the
        unknown-action warning."""
        return StepResult(
            action=action,
            target=target,
            result=TestResult.SKIPPED,
            message="transition_expect_error requires entity-id context (not yet wired)",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_create_expect_error_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        """#1133: POST to the entity create endpoint expecting a 4xx response.

        Validation tests emit this action to assert that an entity
        creation request with missing/invalid data is rejected. The
        complementary ``assert_error`` step then introspects
        ``context['last_response']`` to verify the error shape.

        Stores the response in ``context['last_response']`` regardless
        of outcome so downstream steps can introspect it. PASSES iff
        the server returns 4xx; FAILS on 2xx/3xx (a request that
        succeeded was supposed to be rejected) and on 5xx (a server
        crash is not the same as a validation error).
        """
        assert self.client is not None
        entity_name = target.replace("entity:", "")
        endpoint = self.client._entity_endpoint(entity_name)
        # #1139: prefer the payload actually sent by the preceding
        # create step (which has post-generation unique-field values)
        # over the raw resolved_data literal — otherwise a "duplicate
        # email" scenario sends two different emails and never trips
        # the unique constraint.
        payload = context.get(f"_last_created_data:{entity_name}", resolved_data)
        try:
            resp = self.client._request(
                "POST",
                f"{self.client.api_url}{endpoint}",
                json=payload,
                headers=self.client._auth_headers(),
            )
        except Exception as e:
            return StepResult(
                action=action,
                target=target,
                result=TestResult.FAILED,
                message=f"Request failed: {e}",
                duration_ms=(time.time() - start_time) * 1000,
            )
        context["last_response"] = resp
        is_client_error = 400 <= resp.status_code < 500
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if is_client_error else TestResult.FAILED,
            message=f"Expected 4xx, got {resp.status_code}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_error_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        """#1133: assert the previous response carries an error indicator.

        Accepts either a 4xx status OR a JSON body containing a
        ``detail`` / ``errors`` / ``error`` field — the union of
        FastAPI's default validation-error shape (`{detail: [...]}`)
        and common project-side custom error payloads.

        When ``resolved_data`` contains ``field``, the body is also
        checked for a reference to that field name (matches the
        FastAPI ``detail[].loc`` convention).
        """
        last_resp = context.get("last_response")
        if last_resp is None:
            return StepResult(
                action=action,
                target=target,
                result=TestResult.FAILED,
                message="No previous response to inspect for error",
                duration_ms=(time.time() - start_time) * 1000,
            )
        is_client_error = 400 <= last_resp.status_code < 500
        body_has_error_key = False
        body_repr = ""
        try:
            body = last_resp.json()
            if isinstance(body, dict):
                body_has_error_key = any(k in body for k in ("detail", "errors", "error"))
                body_repr = json.dumps(body)[:200]
        except Exception:
            body_repr = (last_resp.text or "")[:200]

        success = is_client_error or body_has_error_key
        expected_field = resolved_data.get("field")
        if success and expected_field:
            success = expected_field in body_repr

        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if success else TestResult.FAILED,
            message=(
                f"status={last_resp.status_code} has_error_key={body_has_error_key} "
                f"body={body_repr!r}"
            ),
            duration_ms=(time.time() - start_time) * 1000,
        )

    # Dispatch table mapping action names to handler methods.
    # Multi-action entries (tuples) are expanded in _get_step_handler().
    _STEP_DISPATCH_SINGLE: dict[str, str] = {
        "login_as": "_execute_login_as_step",
        "navigate_to": "_execute_navigate_to_step",
        "create": "_execute_create_step",
        "update": "_execute_update_step",
        "assert_visible": "_execute_assert_visible_step",
        "assert_count": "_execute_assert_count_step",
        "trigger_transition": "_execute_trigger_transition_step",
        # #1138: alias — designs emit `transition` as the shorter form of
        # `trigger_transition`. Routes to the same SKIP stub.
        "transition": "_execute_trigger_transition_step",
        "transition_expect_error": "_execute_transition_expect_error_step",
        "assert_state": "_execute_assert_state_step",
        "assert_authenticated": "_execute_assert_authenticated_step",
        "check_route": "_execute_check_route_step",
        "read_list": "_execute_read_list_step",
        "post": "_execute_post_step",
        "post_json": "_execute_post_json_step",
        "clear_cookies": "_execute_clear_cookies_step",
        "get": "_execute_get_step",
        "get_with_cookie": "_execute_get_with_cookie_step",
        "assert_status": "_execute_assert_status_step",
        "assert_cookie_set": "_execute_assert_cookie_set_step",
        "assert_no_cookie": "_execute_assert_no_cookie_step",
        "assert_cookie_cleared": "_execute_assert_cookie_cleared_step",
        "assert_redirect_url": "_execute_assert_redirect_url_step",
        "assert_unauthenticated": "_execute_assert_unauthenticated_step",
        # #1133: validation-test actions emitted by ValidationTestBuilder.
        # Previously fell through to the "Unknown test action" warning
        # branch and skipped silently — the most common cause of TD-*
        # tests failing with "UI check failed" and no further detail.
        "create_expect_error": "_execute_create_expect_error_step",
        "assert_error": "_execute_assert_error_step",
    }
    _STEP_DISPATCH_MULTI: dict[str, str] = {
        "click": "_execute_ui_only_step",
        "fill": "_execute_ui_only_step",
        "select": "_execute_ui_only_step",
        "wait_for": "_execute_ui_only_step",
        # #1133: UI-only form actions emitted by user-authored / LLM-generated
        # designs. They require a browser; in API-only test mode they skip
        # cleanly rather than emitting an "Unknown test action" warning.
        "fill_form": "_execute_ui_only_step",
        "submit_form": "_execute_ui_only_step",
        # #1138: persona goal recipes are inherently multi-step UI flows;
        # API-only mode SKIPs cleanly rather than emitting "Unknown
        # test action".
        "achieve_goal": "_execute_ui_only_step",
        "assert_not_visible": "_execute_ui_assertion_step",
        "assert_text": "_execute_ui_assertion_step",
        "wait_for_load": "_execute_e2e_only_step",
        "assert_no_errors": "_execute_e2e_only_step",
    }

    def _get_step_handler(self, action: str) -> Callable[..., StepResult] | None:
        """Look up the handler for an action name."""
        method_name = self._STEP_DISPATCH_SINGLE.get(action) or self._STEP_DISPATCH_MULTI.get(
            action
        )
        if method_name is None:
            return None
        handler: Callable[..., StepResult] = getattr(self, method_name)
        return handler

    def _scan_unknown_actions(self, designs: list[dict[str, Any]]) -> set[str]:
        """#1133: collect every action name referenced by ``designs`` that
        has no entry in ``_STEP_DISPATCH_SINGLE`` / ``_STEP_DISPATCH_MULTI``.

        Pure introspection — no side effects. The runner's main entry
        point uses this to log one ERROR-level line up front instead
        of per-step WARNING-level skip noise.
        """
        known = set(self._STEP_DISPATCH_SINGLE) | set(self._STEP_DISPATCH_MULTI)
        unknown: set[str] = set()
        for design in designs:
            for step in design.get("steps", []) or []:
                action = step.get("action")
                if action and action not in known:
                    unknown.add(action)
        return unknown

    def execute_step(
        self, step: dict[str, Any], design: dict[str, Any], context: dict[str, Any] | None = None
    ) -> StepResult:
        """Execute a single test step.

        Args:
            step: The step definition from the test design
            design: The full test design (for context)
            context: Shared context for storing step results (e.g., created entity IDs)
        """
        assert self.client is not None
        action = step.get("action", "unknown")
        target = step.get("target", "")
        data = step.get("data", {}) or {}
        store_result = step.get("store_result")

        if context is None:
            context = {}

        resolved_data = self._resolve_refs(data, context)
        start_time = time.time()

        kwargs: dict[str, Any] = {
            "action": action,
            "target": target,
            "resolved_data": resolved_data,
            "context": context,
            "store_result": store_result,
            "start_time": start_time,
            "data": data,
            # #1210: pass the raw step so handlers can read optional
            # fields like ``cleanup_entity`` without widening the kwargs
            # contract for every existing handler.
            "step": step,
        }

        try:
            handler = self._get_step_handler(action)
            if handler is not None:
                return handler(**kwargs)

            logger.warning("Unknown test action '%s' — step skipped", action)
            return StepResult(
                action=action,
                target=target,
                result=TestResult.SKIPPED,
                message=f"Unknown action: {action}",
                duration_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            return StepResult(
                action=action,
                target=target,
                result=TestResult.ERROR,
                message=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )

    def _resolve_credential(self, persona: str, field: str) -> str:
        """Resolve a persona credential (email or password) from test config.

        Looks up credentials from (in priority order):
        1. DAZZLE_TEST_EMAIL / DAZZLE_TEST_PASSWORD env vars (admin only)
        2. .dazzle/test_credentials.json personas.<persona> section
        3. .dazzle/test_credentials.json top-level (admin fallback)
        """
        # Admin: prefer env vars
        if persona == "admin" and field == "email":
            val = os.environ.get("DAZZLE_TEST_EMAIL")
            if val:
                return val
        if persona == "admin" and field == "password":
            val = os.environ.get("DAZZLE_TEST_PASSWORD")
            if val:
                return val

        # Credentials file
        creds_path = Path(".dazzle/test_credentials.json")
        if creds_path.exists():
            try:
                creds = json.loads(creds_path.read_text(encoding="utf-8"))
                personas = creds.get("personas", {})
                persona_creds = personas.get(persona, {})
                val = persona_creds.get(field)
                if val:
                    return str(val)
                # Admin fallback to top-level
                if persona == "admin":
                    val = creds.get(field)
                    if val:
                        return str(val)
            except Exception:
                logger.warning(
                    "Failed to read test auth field '%s' for persona '%s'",
                    field,
                    persona,
                    exc_info=True,
                )

        return f"__PERSONA_{field.upper()}__"  # unresolved

    def _resolve_refs(self, data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Resolve $ref: placeholders and __PERSONA_*__ markers in data.

        Placeholders have the format: $ref:stored_name.field_name
        For example: $ref:parent_task.id -> context["parent_task"]["id"]

        Credential markers: __PERSONA_EMAIL__ and __PERSONA_PASSWORD__
        are resolved from test_credentials.json using the test's persona.

        Args:
            data: Dictionary potentially containing $ref: placeholders
            context: Dictionary of stored step results

        Returns:
            New dictionary with placeholders resolved
        """
        import re

        resolved = {}
        ref_pattern = re.compile(r"^\$ref:(\w+)\.(\w+)$")
        persona = context.get("_persona", "admin")

        for key, value in data.items():
            if isinstance(value, str) and value.startswith("$ref:"):
                match = ref_pattern.match(value)
                if match:
                    stored_name = match.group(1)
                    field_name = match.group(2)
                    if stored_name in context:
                        stored_data = context[stored_name]
                        if isinstance(stored_data, dict) and field_name in stored_data:
                            resolved[key] = stored_data[field_name]
                        else:
                            # Couldn't resolve, keep original
                            resolved[key] = value
                    else:
                        # Stored name not found, keep original
                        resolved[key] = value
                else:
                    # Pattern didn't match, keep original
                    resolved[key] = value
            elif isinstance(value, str) and value == "__PERSONA_EMAIL__":
                resolved[key] = self._resolve_credential(persona, "email")
            elif isinstance(value, str) and value == "__PERSONA_PASSWORD__":
                resolved[key] = self._resolve_credential(persona, "password")
            elif isinstance(value, dict):
                # Recursively resolve nested dicts
                resolved[key] = self._resolve_refs(value, context)
            else:
                resolved[key] = value

        return resolved


def format_report(results: list[TestRunResult]) -> str:
    """Format test results as a report."""
    lines = []
    lines.append("=" * 70)
    lines.append("DAZZLE TEST REPORT")
    lines.append("=" * 70)
    lines.append("")

    total_passed = 0
    total_failed = 0
    total_skipped = 0
    total_errors = 0

    for result in results:
        lines.append(f"Project: {result.project_name}")
        lines.append("-" * 40)
        lines.append(f"  Tests: {result.total}")
        lines.append(f"  Passed: {result.passed}")
        lines.append(f"  Failed: {result.failed}")
        lines.append(f"  Skipped: {result.skipped}")
        lines.append(f"  Errors: {result.errors}")
        lines.append(f"  Success Rate: {result.success_rate:.1f}%")
        lines.append("")

        # Show failed tests
        failed_tests = [t for t in result.tests if t.result == TestResult.FAILED]
        if failed_tests:
            lines.append("  Failed Tests:")
            for test in failed_tests:
                lines.append(f"    - {test.test_id}: {test.error_message}")
            lines.append("")

        total_passed += result.passed
        total_failed += result.failed
        total_skipped += result.skipped
        total_errors += result.errors

    # Summary
    lines.append("=" * 70)
    lines.append("SUMMARY")
    lines.append("=" * 70)
    total = total_passed + total_failed + total_skipped + total_errors
    overall_rate = (total_passed / total * 100) if total > 0 else 0
    lines.append(f"Total Tests: {total}")
    lines.append(f"Passed: {total_passed}")
    lines.append(f"Failed: {total_failed}")
    lines.append(f"Skipped: {total_skipped}")
    lines.append(f"Errors: {total_errors}")
    lines.append(f"Overall Success Rate: {overall_rate:.1f}%")
    lines.append("")

    return "\n".join(lines)


def run_project_tests(project_path: Path) -> TestRunResult:
    """Run tests for a single project."""
    print(f"\nTesting: {project_path.name}")
    print("-" * 40)

    runner = TestRunner(project_path)

    # Start server
    print("  Starting server...")
    if not runner.start_server():
        print("  ERROR: Failed to start server")
        return TestRunResult(
            project_name=project_path.name, started_at=datetime.now(), completed_at=datetime.now()
        )

    try:
        # Wait a bit for server to stabilize
        time.sleep(3)

        # Run tests
        result = runner.run_tests()
        return result
    finally:
        # Stop server
        print("  Stopping server...")
        runner.stop_server()


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="DAZZLE Test Runner")
    parser.add_argument(
        "project_path",
        nargs="?",
        default=".",
        help="Path to the project (default: current directory)",
    )
    parser.add_argument(
        "--all-examples", action="store_true", help="Run tests on all example projects"
    )
    parser.add_argument("--output", "-o", help="Output file for test report")

    args = parser.parse_args()

    results: list[TestRunResult] = []

    if args.all_examples:
        # Find examples directory
        script_dir = Path(__file__).parent
        examples_dir = script_dir.parent.parent.parent / "examples"

        if not examples_dir.exists():
            print(f"Examples directory not found: {examples_dir}")
            sys.exit(1)

        # Run tests on each example
        for project_dir in sorted(examples_dir.iterdir()):
            if project_dir.is_dir() and not project_dir.name.startswith((".", "_")):
                designs_path = project_dir / "dsl" / "tests" / "designs.json"
                if designs_path.exists():
                    result = run_project_tests(project_dir)
                    results.append(result)
    else:
        # Single project
        project_path = Path(args.project_path).resolve()
        if not project_path.exists():
            print(f"Project not found: {project_path}")
            sys.exit(1)

        result = run_project_tests(project_path)
        results.append(result)

    # Generate report
    report = format_report(results)
    print(report)

    # Write to file if specified
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\nReport written to: {args.output}")

    # Exit with error code if any tests failed
    total_failed = sum(r.failed + r.errors for r in results)
    sys.exit(1 if total_failed > 0 else 0)


if __name__ == "__main__":
    main()
