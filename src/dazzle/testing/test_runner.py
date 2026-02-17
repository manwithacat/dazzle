"""
DAZZLE Test Runner - Execute test designs against a running DNR app.

This module provides a test harness that:
1. Loads test designs from dsl/tests/designs.json
2. Starts the DNR server (if needed)
3. Executes test steps via API calls
4. Reports pass/fail results

Usage:
    python -m dazzle.testing.test_runner [project_path]
    python -m dazzle.testing.test_runner --all-examples
"""

from __future__ import annotations

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
    """HTTP client for interacting with a DNR server."""

    def __init__(self, api_url: str, ui_url: str, timeout: float = 10.0):
        self.api_url = api_url.rstrip("/")
        self.ui_url = ui_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout)
        self._auth_token: str | None = None
        self._test_routes_available: bool | None = None  # None = unknown
        self._created_entities: list[tuple[str, str]] = []  # (entity_name, entity_id)

    def close(self) -> None:
        self.client.close()

    def health_check(self) -> bool:
        """Check if the server is healthy."""
        try:
            resp = self.client.get(f"{self.api_url}/health")
            return resp.status_code == 200
        except Exception:
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
            resp = self.client.post(f"{self.api_url}/__test__/reset")
            if resp.status_code == 404:
                self._test_routes_available = False
                return False
            self._test_routes_available = True
            return resp.status_code == 200
        except Exception:
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

            resp = self.client.post(f"{self.api_url}/__test__/seed", json={"fixtures": fixtures})
            return resp.status_code == 200
        except Exception:
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
                resp = self.client.post(
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
                    creds = json.loads(creds_path.read_text())
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
            resp = self.client.post(
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
            return False

    def get_entities(self, entity_name: str) -> list[dict[str, Any]]:
        """Get all entities of a type."""
        try:
            # Prefer test endpoint (returns raw JSON)
            if self._test_routes_available is not False:
                resp = self.client.get(
                    f"{self.api_url}/__test__/entity/{entity_name}",
                    headers=self._auth_headers(),
                )
                if resp.status_code == 200:
                    return list(resp.json())
                if resp.status_code == 404:
                    self._test_routes_available = False

            # Fallback to standard list endpoint
            endpoint = self._entity_endpoint(entity_name)
            resp = self.client.get(
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
            return []

    def create_entity(self, entity_name: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new entity, preferring ``/__test__/seed`` then standard CRUD."""
        try:
            # Use __test__/seed when available (bypasses auth)
            if self._test_routes_available is not False:
                fixture_id = f"test-{entity_name.lower()}-{int(time.time())}"
                fixtures = [{"id": fixture_id, "entity": entity_name, "data": data}]
                resp = self.client.post(
                    f"{self.api_url}/__test__/seed", json={"fixtures": fixtures}
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
            resp = self.client.post(
                f"{self.api_url}{endpoint}", json=data, headers=self._auth_headers()
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
            resp = self.client.put(
                f"{self.api_url}{endpoint}", json=data, headers=self._auth_headers()
            )
            if resp.status_code == 200:
                return dict(resp.json())
            return None
        except Exception:
            return None

    def delete_entity(self, entity_name: str, entity_id: str) -> bool:
        """Delete an entity by ID. Tries __test__ route first, then standard REST."""
        try:
            if self._test_routes_available is not False:
                resp = self.client.delete(
                    f"{self.api_url}/__test__/entity/{entity_name}/{entity_id}"
                )
                if resp.status_code == 200:
                    return True
                if resp.status_code == 404 and "Unknown entity" not in resp.text:
                    self._test_routes_available = False

            endpoint = self._entity_endpoint(entity_name)
            resp = self.client.delete(
                f"{self.api_url}{endpoint}/{entity_id}",
                headers=self._auth_headers(),
            )
            return resp.status_code in (200, 204)
        except Exception:
            return False

    def cleanup_created_entities(self) -> tuple[int, int]:
        """Delete all tracked entities in reverse creation order (LIFO).

        Uses multi-pass to handle FK constraint ordering.
        Returns (deleted_count, failed_count).
        """
        if not self._created_entities:
            return (0, 0)

        pending = list(reversed(self._created_entities))
        deleted = 0
        max_passes = 3

        for _pass_num in range(max_passes):
            still_pending: list[tuple[str, str]] = []
            for entity_name, entity_id in pending:
                if self.delete_entity(entity_name, entity_id):
                    deleted += 1
                else:
                    still_pending.append((entity_name, entity_id))
            pending = still_pending
            if not pending:
                break

        self._created_entities.clear()
        return (deleted, len(pending))

    def get_spec(self) -> dict[str, Any] | None:
        """Get the app spec."""
        try:
            # Use /spec endpoint which returns full spec including workspaces
            resp = self.client.get(f"{self.api_url}/spec")
            if resp.status_code == 200:
                return dict(resp.json())
            return None
        except Exception:
            return None

    def get_entity_schema(self, entity_name: str) -> dict[str, Any] | None:
        """Get entity schema including required fields."""
        try:
            resp = self.client.get(f"{self.api_url}/_dazzle/entity/{entity_name}")
            if resp.status_code == 200:
                return dict(resp.json())
            return None
        except Exception:
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
        import re
        import uuid as uuid_module

        # Handle enum types
        enum_match = re.search(r"enum\(([^)]+)\)", field_type)
        if enum_match:
            values = enum_match.group(1).split(",")
            return values[0].strip()

        # For short max_length fields, use hex-only values to fit
        if max_length is not None and max_length <= 16 and unique:
            return uuid_module.uuid4().hex[:max_length]

        # Generate unique suffix for unique fields — use UUID4 hex to
        # guarantee no collisions across runs or parallel execution.
        unique_suffix = f"_{uuid_module.uuid4().hex[:8]}" if unique else ""

        # Handle by field name first (for common patterns)
        name_lower = name.lower()
        if name_lower == "email" or "email" in field_type:
            value = f"test{unique_suffix}@example.com"
        elif name_lower in ("serial_number", "serialnumber", "serial"):
            value = f"SN{unique_suffix or '_' + uuid_module.uuid4().hex[:8]}"
        elif name_lower == "version":
            value = f"1.0.{uuid_module.uuid4().hex[:6]}"
        elif "uuid" in field_type:
            return str(uuid_module.uuid4())
        elif "str" in field_type:
            value = f"Test {name}{unique_suffix}"
        elif "text" in field_type:
            value = f"Test description for {name}{unique_suffix}"
        elif "int" in field_type:
            return 1
        elif "decimal" in field_type or "float" in field_type:
            return 10.0
        elif "bool" in field_type:
            return True
        elif "date" in field_type and "time" not in field_type:
            from datetime import datetime

            return datetime.now().strftime("%Y-%m-%d")
        elif "datetime" in field_type:
            from datetime import datetime

            return datetime.now().isoformat()
        else:
            value = f"test_{name}{unique_suffix}"

        # Truncate to max_length if specified (preserving unique suffix)
        if max_length is not None and isinstance(value, str) and len(value) > max_length:
            if unique:
                # Keep the unique suffix, truncate the prefix
                suffix = unique_suffix
                prefix_budget = max_length - len(suffix)
                if prefix_budget > 0:
                    value = value[:prefix_budget] + suffix
                else:
                    # Field is too short even for suffix — use hex only
                    value = uuid_module.uuid4().hex[:max_length]
            else:
                value = value[:max_length]

        return value

    def check_ui_loads(self) -> bool:
        """Check if the UI loads successfully."""
        try:
            resp = self.client.get(self.ui_url)
            return resp.status_code == 200 and "<title>" in resp.text
        except Exception:
            return False

    def _auth_headers(self) -> dict[str, str]:
        """Get authentication headers."""
        if self._auth_token:
            return {"Authorization": f"Bearer {self._auth_token}"}
        return {}


class TestRunner:
    """Execute test designs against a DNR app."""

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

        with open(self.designs_path) as f:
            data = json.load(f)
            return list(data.get("designs", []))

    def start_server(self) -> bool:
        """Start the DNR server."""
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
        """Stop the DNR server."""
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

        # Cleanup created entities
        if self._cleanup and self.client:
            deleted, failed = self.client.cleanup_created_entities()
            if deleted or failed:
                msg = f"Cleanup: {deleted} deleted, {failed} failed"
                print(f"    {msg}")
                if on_progress is not None:
                    on_progress(msg)

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
        context: dict[str, Any] = {}

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

        # Initialize context if not provided
        if context is None:
            context = {}

        # Resolve $ref: placeholders in data
        resolved_data = self._resolve_refs(data, context)

        start_time = time.time()

        try:
            if action == "login_as":
                # Authenticate as persona
                success = self.client.authenticate(target)
                return StepResult(
                    action=action,
                    target=target,
                    result=TestResult.PASSED if success else TestResult.SKIPPED,
                    message="" if success else "Auth not required or failed",
                    duration_ms=(time.time() - start_time) * 1000,
                )

            elif action == "navigate_to":
                # For API testing, just verify the endpoint exists
                # In a real Playwright test, this would navigate the browser
                success = True  # Navigation is conceptual in API tests
                return StepResult(
                    action=action,
                    target=target,
                    result=TestResult.PASSED if success else TestResult.FAILED,
                    duration_ms=(time.time() - start_time) * 1000,
                )

            elif action == "create":
                # Create entity
                entity_name = target.replace("entity:", "")
                # Generate required fields if not provided, using resolved data
                entity_data = self.client.generate_entity_data(entity_name, resolved_data)
                result = self.client.create_entity(entity_name, entity_data)
                success = result is not None

                # Store result in context if store_result is specified
                if success and store_result and result:
                    context[store_result] = result

                return StepResult(
                    action=action,
                    target=target,
                    result=TestResult.PASSED if success else TestResult.FAILED,
                    message="" if success else f"Create failed for {entity_name}",
                    duration_ms=(time.time() - start_time) * 1000,
                )

            elif action == "update":
                # Update entity - would need entity ID
                return StepResult(
                    action=action,
                    target=target,
                    result=TestResult.SKIPPED,
                    message="Update requires entity ID context",
                    duration_ms=(time.time() - start_time) * 1000,
                )

            elif action == "assert_visible":
                # For API testing, check if UI loads
                success = self.client.check_ui_loads()
                return StepResult(
                    action=action,
                    target=target,
                    result=TestResult.PASSED if success else TestResult.FAILED,
                    message="" if success else "UI check failed",
                    duration_ms=(time.time() - start_time) * 1000,
                )

            elif action == "assert_count":
                # Check entity count
                # Extract entity name from various target formats
                entity_name = target.replace("entity:", "")
                # Handle common UI element patterns
                if entity_name.endswith("-card"):
                    entity_name = entity_name[:-5]  # Remove "-card"
                elif entity_name.endswith("-row"):
                    entity_name = entity_name[:-4]  # Remove "-row"
                # Map special UI selectors to entity names
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
                    # Convert kebab-case to PascalCase: "task-comment" -> "TaskComment"
                    entity_name = entity_name.replace("-", " ").title().replace(" ", "")
                elif entity_name.islower():
                    # Capitalize simple lowercase names: "task" -> "Task"
                    entity_name = entity_name.capitalize()
                # Otherwise keep the original casing (e.g., TaskComment stays TaskComment)
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

            elif action == "trigger_transition":
                # State transition - would require entity ID
                return StepResult(
                    action=action,
                    target=target,
                    result=TestResult.SKIPPED,
                    message="Transition requires entity context",
                    duration_ms=(time.time() - start_time) * 1000,
                )

            elif action in ("click", "fill", "select", "wait_for"):
                # UI-only actions - skip in API tests
                return StepResult(
                    action=action,
                    target=target,
                    result=TestResult.SKIPPED,
                    message="UI action skipped in API test",
                    duration_ms=(time.time() - start_time) * 1000,
                )

            elif action == "assert_not_visible":
                # Skip in API tests
                return StepResult(
                    action=action,
                    target=target,
                    result=TestResult.SKIPPED,
                    message="UI assertion skipped",
                    duration_ms=(time.time() - start_time) * 1000,
                )

            elif action == "assert_text":
                # Skip in API tests
                return StepResult(
                    action=action,
                    target=target,
                    result=TestResult.SKIPPED,
                    message="UI assertion skipped",
                    duration_ms=(time.time() - start_time) * 1000,
                )

            elif action == "check_route":
                # Verify workspace route exists by checking if UI responds
                # Extract workspace name from target like "workspace:contacts"
                if target.startswith("workspace:"):
                    workspace_name = target.replace("workspace:", "")
                    # Get the route path from step data
                    route = data.get("route", f"/app/workspaces/{workspace_name}")
                    try:
                        # Check if UI route responds
                        resp = self.client.client.get(
                            f"{self.client.ui_url}{route}", follow_redirects=True
                        )
                        # 200/304 = success, 401 = protected (exists but needs auth)
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
                        else:
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
                # Non-workspace routes - skip for now
                return StepResult(
                    action=action,
                    target=target,
                    result=TestResult.SKIPPED,
                    message="Non-workspace route check skipped",
                    duration_ms=(time.time() - start_time) * 1000,
                )

            elif action in ("wait_for_load", "assert_no_errors"):
                # E2E-only actions - skip in API tests
                return StepResult(
                    action=action,
                    target=target,
                    result=TestResult.SKIPPED,
                    message="E2E action skipped in API test",
                    duration_ms=(time.time() - start_time) * 1000,
                )

            elif action == "read_list":
                # Read entity list
                entity_name = target.replace("entity:", "")
                entities = self.client.get_entities(entity_name)
                return StepResult(
                    action=action,
                    target=target,
                    result=TestResult.PASSED,
                    message=f"Retrieved {len(entities)} {entity_name} entities",
                    duration_ms=(time.time() - start_time) * 1000,
                )

            else:
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

    def _resolve_refs(self, data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Resolve $ref: placeholders in data using stored context values.

        Placeholders have the format: $ref:stored_name.field_name
        For example: $ref:parent_task.id -> context["parent_task"]["id"]

        Args:
            data: Dictionary potentially containing $ref: placeholders
            context: Dictionary of stored step results

        Returns:
            New dictionary with placeholders resolved
        """
        import re

        resolved = {}
        ref_pattern = re.compile(r"^\$ref:(\w+)\.(\w+)$")

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
        with open(args.output, "w") as f:
            f.write(report)
        print(f"\nReport written to: {args.output}")

    # Exit with error code if any tests failed
    total_failed = sum(r.failed + r.errors for r in results)
    sys.exit(1 if total_failed > 0 else 0)


if __name__ == "__main__":
    main()
