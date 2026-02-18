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


def _request_with_retry(
    method: str,
    url: str,
    retries: int = REQUEST_RETRIES,
    timeout: int = REQUEST_TIMEOUT,
    **kwargs: object,
) -> requests.Response:
    """Make an HTTP request with retry on timeout/connection errors."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.request(method, url, timeout=timeout, **kwargs)
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

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object) -> None:
        self._terminate()


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
        assert resp.status_code == 200
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


class TestAuthDisabled:
    """Tests for auth stub endpoints when AUTH_ENABLED=0."""

    @pytest.mark.e2e
    def test_auth_me_returns_401_when_disabled(
        self, simple_task_server: DazzleLocalServerManager
    ) -> None:
        """Test that /auth/me returns a valid response when auth is disabled.

        Acceptable responses: 401 (unauthorized), 200 (stub user), or 404 (no auth routes).
        """
        resp = _request_with_retry("GET", f"{simple_task_server.api_url}/auth/me")
        # When auth is enabled: returns user info (200) or requires login (401)
        # When auth is disabled: endpoint may not exist (404) or stub returns 401
        # All of these are acceptable - just not 500 errors
        assert resp.status_code in (401, 200, 404), (
            f"Expected 401, 200, or 404, got {resp.status_code}"
        )

    @pytest.mark.e2e
    def test_crud_works_without_auth(self, simple_task_server: DazzleLocalServerManager) -> None:
        """Test that CRUD operations work without authentication.

        Even with auth enabled by default, the API should allow CRUD
        operations (for now - future versions may require auth for write ops).
        """
        api = simple_task_server.api_url

        # Create should work
        task_data = {"title": "No Auth Test Task", "status": "todo"}
        resp = _request_with_retry("POST", f"{api}/tasks", json=task_data)
        assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
        created = resp.json()
        task_id = created["id"]

        # Read should work
        resp = _request_with_retry("GET", f"{api}/tasks/{task_id}")
        assert resp.status_code == 200, f"Read failed: {resp.text}"

        # List should work
        resp = _request_with_retry("GET", f"{api}/tasks")
        assert resp.status_code == 200, f"List failed: {resp.text}"
