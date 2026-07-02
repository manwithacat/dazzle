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

import httpx

from dazzle.core.http_client import retrying_request
from dazzle.testing.cleanup_manager import CleanupManager
from dazzle.testing.entity_client import EntityClient

logger = logging.getLogger(__name__)


class TestResult(StrEnum):
    """Result of a single test."""

    __test__ = False  # not a pytest test class, despite the Test* name

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
        # #1446: collaborators split out of the former god class. cleanup must be
        # composed before entities — EntityClient.create_entity records created
        # rows via self.cleanup.track().
        self.cleanup = CleanupManager(self)
        self.entities = EntityClient(self)

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

    __test__ = False  # not a pytest test class, despite the Test* name

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
        # #1446: step execution (the ~28 `_execute_*_step` handlers + dispatch +
        # step helpers, incl. the lazy surface-url map) lives in StepExecutor.
        # Deferred import breaks the test_runner ↔ step_executor cycle (StepExecutor
        # imports the result types defined in this module).
        from dazzle.testing.step_executor import StepExecutor

        self.steps = StepExecutor(self)

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
        unknown_actions = self.steps._scan_unknown_actions(designs)
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
            report = self.client.cleanup.cleanup_created_entities()
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
            residue = self.client.cleanup.detect_residue(report.created_types)
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

    def execute_step(
        self, step: dict[str, Any], design: dict[str, Any], context: dict[str, Any] | None = None
    ) -> StepResult:
        """Execute a single test step. Delegates to the StepExecutor collaborator (#1446)."""
        return self.steps.execute_step(step, design, context)


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
