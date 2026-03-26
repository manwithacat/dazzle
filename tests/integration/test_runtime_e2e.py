"""
End-to-end tests for the Dazzle Runtime.

These tests spin up actual Dazzle server instances for each example project
and verify that:
1. The API endpoints work correctly
2. CRUD operations function properly
3. The frontend is served correctly

Uses a local Python server (no Docker required).
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import requests

if TYPE_CHECKING:
    from collections.abc import Iterator

# List of examples to test - these use the Dazzle stack
DAZZLE_EXAMPLES = [
    "simple_task",
    "contact_manager",
]

# Timeout for server startup (120s for slow CI runners)
SERVER_STARTUP_TIMEOUT = 120
# Request timeout (30s for CI under load)
REQUEST_TIMEOUT = 30
# Number of retries for transient request failures
REQUEST_RETRIES = 3


@pytest.fixture(scope="module")
def dazzle_root() -> Path:
    """Get the dazzle project root directory."""
    return Path(__file__).parent.parent.parent


def wait_for_server(url: str, timeout: int = SERVER_STARTUP_TIMEOUT) -> bool:
    """Wait for server to become available with exponential backoff."""
    start = time.time()
    delay = 0.5
    while time.time() - start < timeout:
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code < 500:
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(delay)
        delay = min(delay * 2, 4.0)  # 0.5 → 1 → 2 → 4 (cap)
    return False


# Shared session to persist CSRF cookies across requests
_session = requests.Session()


def _request_with_retry(
    method: str,
    url: str,
    retries: int = REQUEST_RETRIES,
    timeout: int = REQUEST_TIMEOUT,
    **kwargs: object,
) -> requests.Response:
    """Make an HTTP request with retry on timeout/connection errors.

    Uses a shared session to persist cookies (including the dazzle_csrf
    cookie set by the CSRF middleware on GET responses). For state-changing
    methods, the CSRF token from the cookie is sent as X-CSRF-Token header.
    """
    # Inject CSRF token header for mutation requests
    if method.upper() in ("POST", "PUT", "DELETE", "PATCH"):
        csrf_token = _session.cookies.get("dazzle_csrf")
        if csrf_token:
            headers = dict(kwargs.pop("headers", {}) or {})  # type: ignore[arg-type]
            headers.setdefault("X-CSRF-Token", csrf_token)
            kwargs["headers"] = headers

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = _session.request(method, url, timeout=timeout, **kwargs)
            return resp
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exc = e
            if attempt < retries - 1:
                time.sleep(1)
    raise last_exc  # type: ignore[misc]


class DazzleLocalServerManager:
    """Context manager for running Dazzle server locally.

    Redirects stdout/stderr to temp files instead of pipes to avoid
    pipe buffer deadlock (64KB limit blocks the server's event loop).
    """

    def __init__(self, example_dir: Path, port: int = 3000):
        self.example_dir = example_dir
        self.port = port
        self.process: subprocess.Popen | None = None
        self._stdout_file: tempfile._TemporaryFileWrapper | None = None
        self._stderr_file: tempfile._TemporaryFileWrapper | None = None
        # Unified server: API and UI on the same port
        self.api_url = f"http://127.0.0.1:{port}"
        self.ui_url = f"http://127.0.0.1:{port}"

    def __enter__(self) -> DazzleLocalServerManager:
        # Start the Dazzle server locally
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        # Forward DATABASE_URL to subprocess (PostgreSQL-first)
        database_url = os.environ.get("DATABASE_URL", "")
        if database_url:
            env["DATABASE_URL"] = database_url

        # Clear any existing runtime file from previous runs
        dazzle_dir = self.example_dir / ".dazzle"
        runtime_file = dazzle_dir / "runtime.json"
        if runtime_file.exists():
            runtime_file.unlink()

        # Platform-specific process group handling
        kwargs: dict = {}
        if sys.platform != "win32":
            kwargs["preexec_fn"] = os.setsid  # Create new process group (Unix)
        else:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        # Redirect to temp files instead of pipes to avoid pipe buffer
        # deadlock. Pipes have a 64KB buffer; when full, the server's
        # write() blocks, freezing the uvicorn event loop.
        self._stdout_file = tempfile.NamedTemporaryFile(
            mode="w", prefix="dazzle-e2e-stdout-", suffix=".log", delete=False
        )
        self._stderr_file = tempfile.NamedTemporaryFile(
            mode="w", prefix="dazzle-e2e-stderr-", suffix=".log", delete=False
        )

        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "dazzle",
                "serve",
                "--local",  # Explicitly use local mode
                "--port",
                str(self.port),
                "--host",
                "127.0.0.1",
                "--test-mode",
            ],
            cwd=self.example_dir,
            stdout=self._stdout_file,
            stderr=self._stderr_file,
            env=env,
            **kwargs,
        )

        # Wait for runtime file to be written (contains actual ports)
        runtime_file = self.example_dir / ".dazzle" / "runtime.json"
        for _ in range(SERVER_STARTUP_TIMEOUT * 2):
            if runtime_file.exists():
                try:
                    import json

                    data = json.loads(runtime_file.read_text())
                    # Update URLs to use actual allocated port (unified server)
                    self.port = data.get("ui_port", data.get("port", self.port))
                    self.api_url = f"http://127.0.0.1:{self.port}"
                    self.ui_url = f"http://127.0.0.1:{self.port}"
                    break
                except (json.JSONDecodeError, KeyError):
                    pass
            time.sleep(0.5)

        # Wait for API to be ready
        if not wait_for_server(f"{self.api_url}/health"):
            stderr_log = self._read_log(self._stderr_file)
            self._terminate()
            raise RuntimeError(
                f"Dazzle server failed to start within {SERVER_STARTUP_TIMEOUT}s.\n"
                f"stderr:\n{stderr_log}"
            )

        return self

    def _read_log(self, f: tempfile._TemporaryFileWrapper | None) -> str:
        """Read contents of a log temp file."""
        if f is None:
            return "(no log file)"
        try:
            f.flush()
            return Path(f.name).read_text(errors="replace")[-4096:]
        except OSError:
            return "(could not read log)"

    def get_server_logs(self) -> str:
        """Get combined server logs for debugging."""
        stdout = self._read_log(self._stdout_file)
        stderr = self._read_log(self._stderr_file)
        parts = []
        if stdout.strip():
            parts.append(f"=== stdout ===\n{stdout}")
        if stderr.strip():
            parts.append(f"=== stderr ===\n{stderr}")
        return "\n".join(parts) if parts else "(no output)"

    def _terminate(self) -> None:
        """Terminate the server process and clean up log files."""
        if self.process:
            try:
                if sys.platform != "win32":
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                else:
                    self.process.terminate()
            except (ProcessLookupError, OSError):
                pass  # Already dead
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)

        # Clean up temp files
        for f in (self._stdout_file, self._stderr_file):
            if f is not None:
                try:
                    f.close()
                    os.unlink(f.name)
                except OSError:
                    pass

    def get_server_stderr(self, tail: int = 100) -> str:
        """Read the last N lines of server stderr for diagnostics."""
        if self._stderr_file is None:
            return ""
        try:
            with open(self._stderr_file.name) as f:
                lines = f.readlines()
                return "".join(lines[-tail:])
        except OSError:
            return ""

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object) -> None:
        self._terminate()


def _ensure_authenticated(api_url: str) -> None:
    """Register + login a test user on the shared session.

    Idempotent: safe to call multiple times (registration may return 400
    if the user already exists from a prior run).
    """
    # Seed CSRF cookie
    _session.get(f"{api_url}/health", timeout=10)

    # Register (ignore 400/409 — already exists)
    _session.post(
        f"{api_url}/auth/register",
        json={"email": "e2e@example.com", "password": "Test1234!", "name": "E2E User"},
        timeout=10,
    )

    # Login
    resp = _session.post(
        f"{api_url}/auth/login",
        json={"email": "e2e@example.com", "password": "Test1234!"},
        timeout=10,
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"


@pytest.fixture(scope="module")
def simple_task_server(
    dazzle_root: Path,
) -> Iterator[DazzleLocalServerManager]:
    """Start Dazzle server for simple_task example."""
    example_dir = dazzle_root / "examples" / "simple_task"
    if not example_dir.exists():
        pytest.skip(f"Example directory not found: {example_dir}")

    # Use unique port to avoid conflicts with other running servers
    with DazzleLocalServerManager(example_dir, port=3001) as server:
        # Auth is enabled on simple_task — register + login for CRUD tests
        _ensure_authenticated(server.api_url)
        yield server


class TestSimpleTaskE2E:
    """E2E tests for the simple_task example."""

    @pytest.mark.e2e
    def test_api_docs_available(self, simple_task_server: DazzleLocalServerManager) -> None:
        """Test that OpenAPI docs are served."""
        resp = _request_with_retry("GET", f"{simple_task_server.api_url}/docs")
        assert resp.status_code == 200
        assert "swagger" in resp.text.lower() or "openapi" in resp.text.lower()

    @pytest.mark.e2e
    def test_openapi_schema_available(self, simple_task_server: DazzleLocalServerManager) -> None:
        """Test that OpenAPI JSON schema is available."""
        resp = _request_with_retry("GET", f"{simple_task_server.api_url}/openapi.json")
        assert resp.status_code == 200, (
            f"OpenAPI returned {resp.status_code}: {resp.text[:200]}\n"
            f"--- Server stderr (last 50 lines) ---\n"
            f"{simple_task_server.get_server_stderr(50)}"
        )
        data = resp.json()
        assert "openapi" in data
        assert "paths" in data

    @pytest.mark.e2e
    def test_api_endpoints_respond(self, simple_task_server: DazzleLocalServerManager) -> None:
        """Test that API endpoints respond correctly."""
        api = simple_task_server.api_url

        # Test health endpoint
        resp = _request_with_retry("GET", f"{api}/health")
        assert resp.status_code == 200, f"Health check failed: {resp.text}"

        # Test list endpoint returns paginated response
        resp = _request_with_retry("GET", f"{api}/tasks")
        assert resp.status_code == 200, f"List failed: {resp.text}"
        data = resp.json()
        assert "items" in data or isinstance(data, list)

        # Test create endpoint accepts data (response validation only)
        # Note: simple_task has an invariant that urgent tasks require a due_date
        # Use minimal data and let defaults apply
        task_data = {
            "title": "E2E Test Task",
        }
        resp = _request_with_retry("POST", f"{api}/tasks", json=task_data)
        assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
        created = resp.json()
        assert "id" in created, "Response should have an ID"
        assert created["title"] == "E2E Test Task"

    @pytest.mark.e2e
    def test_task_crud_persistence(self, simple_task_server: DazzleLocalServerManager) -> None:
        """Test Create, Read, Update, List operations with persistence."""
        api = simple_task_server.api_url

        # Create a task (POST to /tasks)
        task_data = {
            "title": "E2E Test Task",
            "description": "Created by E2E test",
            "status": "todo",
            "priority": "high",
        }
        resp = _request_with_retry("POST", f"{api}/tasks", json=task_data)
        assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
        created = resp.json()
        task_id = created.get("id")
        assert task_id is not None, "Created task should have an ID"

        # Read the task (GET /tasks/{id})
        resp = _request_with_retry("GET", f"{api}/tasks/{task_id}")
        assert resp.status_code == 200, f"Read failed: {resp.text}"
        fetched = resp.json()
        assert fetched["title"] == "E2E Test Task"

        # Update the task (PUT /tasks/{id})
        update_data = {"title": "Updated E2E Task", "priority": "medium"}
        resp = _request_with_retry("PUT", f"{api}/tasks/{task_id}", json=update_data)
        assert resp.status_code == 200, f"Update failed: {resp.text}"
        updated = resp.json()
        assert updated["title"] == "Updated E2E Task"
        assert updated["priority"] == "medium"

        # List tasks - should include our task (GET /tasks)
        resp = _request_with_retry("GET", f"{api}/tasks")
        assert resp.status_code == 200, f"List failed: {resp.text}"
        data = resp.json()
        # Runtime returns paginated response with 'items' key or list directly
        tasks = data.get("items", data) if isinstance(data, dict) else data
        assert isinstance(tasks, list)
        assert any(t["id"] == task_id for t in tasks)

        # Verify persistence: read again to confirm data persisted
        resp = _request_with_retry("GET", f"{api}/tasks/{task_id}")
        assert resp.status_code == 200, f"Re-read failed: {resp.text}"
        persisted = resp.json()
        assert persisted["title"] == "Updated E2E Task"
        assert persisted["priority"] == "medium"

    @pytest.mark.e2e
    def test_frontend_serves_html(self, simple_task_server: DazzleLocalServerManager) -> None:
        """Test that frontend serves server-rendered HTMX HTML content."""
        resp = _request_with_retry("GET", simple_task_server.ui_url)
        # Frontend might be served at root, or at a subpath
        if resp.status_code == 404:
            # Try common fallback paths
            for path in ["/index.html", "/static/", "/app/"]:
                resp = _request_with_retry("GET", f"{simple_task_server.ui_url}{path}")
                if resp.status_code in (200, 302, 304):
                    break
            # If still 404, skip - UI serving varies by mode
            if resp.status_code == 404:
                pytest.skip("UI not served at root or common paths")
        else:
            assert resp.status_code in (200, 302, 304), f"Frontend failed: {resp.status_code}"
            if resp.status_code == 200:
                # Should have server-rendered HTML with HTMX/template content
                content_type = resp.headers.get("content-type", "").lower()
                assert "html" in content_type, f"Expected HTML content-type, got: {content_type}"
                body = resp.text
                # Check for server-rendered template markers
                assert any(
                    marker in body
                    for marker in [
                        "hx-get",
                        "hx-post",
                        "<table",
                        "daisyui",
                        "<!DOCTYPE",
                        "<!doctype",
                    ]
                ), "Expected HTMX attributes or server-rendered template markers in response"


# Parametrized tests for multiple examples
@pytest.mark.e2e
@pytest.mark.parametrize("example_name", DAZZLE_EXAMPLES)
def test_example_validates(dazzle_root: Path, example_name: str) -> None:
    """Test that each example validates successfully."""
    example_dir = dazzle_root / "examples" / example_name
    if not example_dir.exists():
        pytest.skip(f"Example {example_name} not found")

    result = subprocess.run(
        [sys.executable, "-m", "dazzle", "validate"],
        cwd=example_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"Validation failed for {example_name}: {result.stderr}"


@pytest.mark.e2e
@pytest.mark.parametrize("example_name", DAZZLE_EXAMPLES)
def test_example_builds_ui(dazzle_root: Path, example_name: str) -> None:
    """Test that each example can build UI artifacts."""
    example_dir = dazzle_root / "examples" / example_name
    if not example_dir.exists():
        pytest.skip(f"Example {example_name} not found")

    result = subprocess.run(
        [sys.executable, "-m", "dazzle", "build-ui"],
        cwd=example_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"UI build failed for {example_name}: {result.stderr}"


class TestAuth:
    """Tests for auth endpoints (auth enabled on simple_task)."""

    @pytest.mark.e2e
    def test_auth_me_returns_user(self, simple_task_server: DazzleLocalServerManager) -> None:
        """Authenticated session can retrieve current user info."""
        resp = _request_with_retry("GET", f"{simple_task_server.api_url}/auth/me")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("email") == "e2e@example.com"

    @pytest.mark.e2e
    def test_crud_works_with_auth(self, simple_task_server: DazzleLocalServerManager) -> None:
        """Authenticated CRUD operations work end-to-end."""
        api = simple_task_server.api_url

        # Create
        task_data = {"title": "Auth CRUD Test Task", "status": "todo"}
        resp = _request_with_retry("POST", f"{api}/tasks", json=task_data)
        assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
        created = resp.json()
        task_id = created["id"]

        # Read
        resp = _request_with_retry("GET", f"{api}/tasks/{task_id}")
        assert resp.status_code == 200, f"Read failed: {resp.text}"

        # List
        resp = _request_with_retry("GET", f"{api}/tasks")
        assert resp.status_code == 200, f"List failed: {resp.text}"


class TestFeedbackWidget:
    """Feedback widget CRUD via synthetic surfaces (#685)."""

    @pytest.mark.e2e
    def test_post_creates_feedback(self, simple_task_server: DazzleLocalServerManager) -> None:
        """POST /feedbackreports creates a FeedbackReport record."""
        api = simple_task_server.api_url
        resp = _request_with_retry(
            "POST",
            f"{api}/feedbackreports",
            json={
                "category": "bug",
                "severity": "annoying",
                "description": "Button alignment off on mobile",
                "page_url": f"{api}/app",
                "reported_by": "e2e@example.com",
            },
        )
        assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
        data = resp.json()
        assert data["category"] == "bug"
        assert data["severity"] == "annoying"
        assert data["description"] == "Button alignment off on mobile"
        assert "id" in data

    @pytest.mark.e2e
    def test_list_returns_feedback(self, simple_task_server: DazzleLocalServerManager) -> None:
        """GET /feedbackreports returns paginated list with submitted feedback."""
        api = simple_task_server.api_url

        # Ensure at least one record
        _request_with_retry(
            "POST",
            f"{api}/feedbackreports",
            json={
                "category": "ux",
                "severity": "minor",
                "description": "List test feedback",
                "reported_by": "e2e@example.com",
            },
        )

        resp = _request_with_retry("GET", f"{api}/feedbackreports")
        assert resp.status_code == 200, f"List failed: {resp.text}"
        data = resp.json()
        assert "items" in data
        assert data["total"] >= 1
        item = data["items"][0]
        assert "category" in item
        assert "severity" in item
        assert "status" in item

    @pytest.mark.e2e
    def test_unauthenticated_post_rejected(
        self, simple_task_server: DazzleLocalServerManager
    ) -> None:
        """POST /feedbackreports without auth session is rejected."""
        api = simple_task_server.api_url
        # Use a fresh session with no cookies
        resp = requests.post(
            f"{api}/feedbackreports",
            json={
                "category": "bug",
                "severity": "minor",
                "description": "Unauthenticated attempt",
                "reported_by": "anon@example.com",
            },
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code in (401, 403), (
            f"Expected auth rejection, got {resp.status_code}: {resp.text}"
        )

    @pytest.mark.e2e
    def test_put_updates_feedback_status(
        self, simple_task_server: DazzleLocalServerManager
    ) -> None:
        """PUT /feedbackreports/{id} transitions status via state machine."""
        api = simple_task_server.api_url

        # Create a feedback report
        resp = _request_with_retry(
            "POST",
            f"{api}/feedbackreports",
            json={
                "category": "bug",
                "severity": "minor",
                "description": "PUT test feedback",
                "reported_by": "e2e@example.com",
            },
        )
        assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
        report_id = resp.json()["id"]

        # Triage it (new → triaged)
        resp = _request_with_retry(
            "PUT",
            f"{api}/feedbackreports/{report_id}",
            json={"status": "triaged", "agent_notes": "Looks like a CSS issue"},
        )
        assert resp.status_code == 200, f"PUT failed: {resp.text}"
        assert resp.json()["status"] == "triaged"

    @pytest.mark.e2e
    def test_delete_removes_feedback(self, simple_task_server: DazzleLocalServerManager) -> None:
        """DELETE /feedbackreports/{id} removes the record."""
        api = simple_task_server.api_url

        # Create a feedback report
        resp = _request_with_retry(
            "POST",
            f"{api}/feedbackreports",
            json={
                "category": "ux",
                "severity": "minor",
                "description": "Delete test feedback",
                "reported_by": "e2e@example.com",
            },
        )
        assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
        report_id = resp.json()["id"]

        # Delete it
        resp = _request_with_retry("DELETE", f"{api}/feedbackreports/{report_id}")
        assert resp.status_code in (200, 204), f"Delete failed: {resp.text}"

        # Verify it's gone
        resp = _request_with_retry("GET", f"{api}/feedbackreports/{report_id}")
        assert resp.status_code == 404

    @pytest.mark.e2e
    def test_triage_resolve_lifecycle(self, simple_task_server: DazzleLocalServerManager) -> None:
        """Full lifecycle: create → triage → resolve."""
        api = simple_task_server.api_url

        # Create
        resp = _request_with_retry(
            "POST",
            f"{api}/feedbackreports",
            json={
                "category": "bug",
                "severity": "annoying",
                "description": "Lifecycle test feedback",
                "reported_by": "e2e@example.com",
            },
        )
        assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
        report_id = resp.json()["id"]

        # Triage (new → triaged)
        resp = _request_with_retry(
            "PUT",
            f"{api}/feedbackreports/{report_id}",
            json={"status": "triaged"},
        )
        assert resp.json()["status"] == "triaged"

        # Resolve (triaged → resolved, shortcut)
        resp = _request_with_retry(
            "PUT",
            f"{api}/feedbackreports/{report_id}",
            json={"status": "resolved", "agent_notes": "Fixed in commit abc123"},
        )
        assert resp.status_code == 200, f"Resolve failed: {resp.text}"
        assert resp.json()["status"] == "resolved"
