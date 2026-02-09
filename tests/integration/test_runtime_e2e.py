"""
End-to-end tests for the Dazzle Runtime.

These tests spin up actual DNR server instances for each example project
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
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import requests

if TYPE_CHECKING:
    from collections.abc import Iterator

# List of examples to test - these use the DNR stack
DAZZLE_EXAMPLES = [
    "simple_task",
    "contact_manager",
]

# Timeout for server startup (120s for slow CI runners)
SERVER_STARTUP_TIMEOUT = 120
# Request timeout
REQUEST_TIMEOUT = 10


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


class DNRLocalServerManager:
    """Context manager for running DNR server locally.

    This is the default and most reliable mode for E2E tests.
    """

    def __init__(self, example_dir: Path, api_port: int = 8000, ui_port: int = 3000):
        self.example_dir = example_dir
        self.api_port = api_port
        self.ui_port = ui_port
        self.process: subprocess.Popen | None = None
        self.api_url = f"http://127.0.0.1:{api_port}"
        self.ui_url = f"http://127.0.0.1:{ui_port}"

    def __enter__(self) -> DNRLocalServerManager:
        # Start the DNR server locally
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        # Clear any existing runtime file and database from previous runs
        dazzle_dir = self.example_dir / ".dazzle"
        runtime_file = dazzle_dir / "runtime.json"
        if runtime_file.exists():
            runtime_file.unlink()
        # Clear database for clean test state
        data_db = dazzle_dir / "data.db"
        if data_db.exists():
            data_db.unlink()

        # Platform-specific process group handling
        kwargs: dict = {}
        if sys.platform != "win32":
            kwargs["preexec_fn"] = os.setsid  # Create new process group (Unix)
        else:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "dazzle",
                "serve",
                "--local",  # Explicitly use local mode
                "--port",
                str(self.ui_port),
                "--api-port",
                str(self.api_port),
                "--host",
                "127.0.0.1",
                "--test-mode",
            ],
            cwd=self.example_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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
                    # Update URLs to use actual allocated ports
                    self.api_port = data["api_port"]
                    self.ui_port = data["ui_port"]
                    self.api_url = f"http://127.0.0.1:{self.api_port}"
                    self.ui_url = f"http://127.0.0.1:{self.ui_port}"
                    break
                except (json.JSONDecodeError, KeyError):
                    pass
            time.sleep(0.5)

        # Wait for API to be ready
        if not wait_for_server(f"{self.api_url}/health"):
            # Get any error output
            if self.process:
                self.process.terminate()
                _, stderr = self.process.communicate(timeout=5)
                raise RuntimeError(
                    f"Dazzle server failed to start within {SERVER_STARTUP_TIMEOUT}s. "
                    f"stderr: {stderr.decode()}"
                )
            raise RuntimeError(f"Dazzle server failed to start within {SERVER_STARTUP_TIMEOUT}s.")

        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object) -> None:
        if self.process:
            # Kill the process and its children
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


@pytest.fixture(scope="module")
def simple_task_server(
    dazzle_root: Path,
) -> Iterator[DNRLocalServerManager]:
    """Start DNR server for simple_task example."""
    example_dir = dazzle_root / "examples" / "simple_task"
    if not example_dir.exists():
        pytest.skip(f"Example directory not found: {example_dir}")

    # Use unique ports to avoid conflicts with other running servers
    with DNRLocalServerManager(example_dir, api_port=8001, ui_port=3001) as server:
        yield server


class TestSimpleTaskE2E:
    """E2E tests for the simple_task example."""

    @pytest.mark.e2e
    def test_api_docs_available(self, simple_task_server: DNRLocalServerManager) -> None:
        """Test that OpenAPI docs are served."""
        resp = requests.get(f"{simple_task_server.api_url}/docs", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200
        assert "swagger" in resp.text.lower() or "openapi" in resp.text.lower()

    @pytest.mark.e2e
    def test_openapi_schema_available(self, simple_task_server: DNRLocalServerManager) -> None:
        """Test that OpenAPI JSON schema is available."""
        resp = requests.get(f"{simple_task_server.api_url}/openapi.json", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert "openapi" in data
        assert "paths" in data

    @pytest.mark.e2e
    def test_api_endpoints_respond(self, simple_task_server: DNRLocalServerManager) -> None:
        """Test that API endpoints respond correctly."""
        api = simple_task_server.api_url

        # Test health endpoint
        resp = requests.get(f"{api}/health", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200, f"Health check failed: {resp.text}"

        # Test list endpoint returns paginated response
        resp = requests.get(f"{api}/tasks", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200, f"List failed: {resp.text}"
        data = resp.json()
        assert "items" in data or isinstance(data, list)

        # Test create endpoint accepts data (response validation only)
        # Note: simple_task has an invariant that urgent tasks require a due_date
        # Use minimal data and let defaults apply
        task_data = {
            "title": "E2E Test Task",
        }
        resp = requests.post(f"{api}/tasks", json=task_data, timeout=REQUEST_TIMEOUT)
        assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
        created = resp.json()
        assert "id" in created, "Response should have an ID"
        assert created["title"] == "E2E Test Task"

    @pytest.mark.e2e
    def test_task_crud_persistence(self, simple_task_server: DNRLocalServerManager) -> None:
        """Test Create, Read, Update, List operations with persistence."""
        api = simple_task_server.api_url

        # Create a task (POST to /tasks)
        task_data = {
            "title": "E2E Test Task",
            "description": "Created by E2E test",
            "status": "todo",
            "priority": "high",
        }
        resp = requests.post(f"{api}/tasks", json=task_data, timeout=REQUEST_TIMEOUT)
        assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
        created = resp.json()
        task_id = created.get("id")
        assert task_id is not None, "Created task should have an ID"

        # Read the task (GET /tasks/{id})
        resp = requests.get(f"{api}/tasks/{task_id}", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200, f"Read failed: {resp.text}"
        fetched = resp.json()
        assert fetched["title"] == "E2E Test Task"

        # Update the task (PUT /tasks/{id})
        update_data = {"title": "Updated E2E Task", "priority": "medium"}
        resp = requests.put(f"{api}/tasks/{task_id}", json=update_data, timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200, f"Update failed: {resp.text}"
        updated = resp.json()
        assert updated["title"] == "Updated E2E Task"
        assert updated["priority"] == "medium"

        # List tasks - should include our task (GET /tasks)
        resp = requests.get(f"{api}/tasks", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200, f"List failed: {resp.text}"
        data = resp.json()
        # Runtime returns paginated response with 'items' key or list directly
        tasks = data.get("items", data) if isinstance(data, dict) else data
        assert isinstance(tasks, list)
        assert any(t["id"] == task_id for t in tasks)

        # Verify persistence: read again to confirm data persisted
        resp = requests.get(f"{api}/tasks/{task_id}", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200, f"Re-read failed: {resp.text}"
        persisted = resp.json()
        assert persisted["title"] == "Updated E2E Task"
        assert persisted["priority"] == "medium"

    @pytest.mark.e2e
    def test_frontend_serves_html(self, simple_task_server: DNRLocalServerManager) -> None:
        """Test that frontend serves server-rendered HTMX HTML content."""
        resp = requests.get(simple_task_server.ui_url, timeout=REQUEST_TIMEOUT)
        # Frontend might be served at root, or at a subpath
        if resp.status_code == 404:
            # Try common fallback paths
            for path in ["/index.html", "/static/", "/app/"]:
                resp = requests.get(f"{simple_task_server.ui_url}{path}", timeout=REQUEST_TIMEOUT)
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
        self, simple_task_server: DNRLocalServerManager
    ) -> None:
        """Test that /auth/me returns a valid response when auth is disabled.

        Acceptable responses: 401 (unauthorized), 200 (stub user), or 404 (no auth routes).
        """
        resp = requests.get(f"{simple_task_server.api_url}/auth/me", timeout=REQUEST_TIMEOUT)
        # When auth is enabled: returns user info (200) or requires login (401)
        # When auth is disabled: endpoint may not exist (404) or stub returns 401
        # All of these are acceptable - just not 500 errors
        assert resp.status_code in (401, 200, 404), (
            f"Expected 401, 200, or 404, got {resp.status_code}"
        )

    @pytest.mark.e2e
    def test_crud_works_without_auth(self, simple_task_server: DNRLocalServerManager) -> None:
        """Test that CRUD operations work without authentication.

        Even with auth enabled by default, the API should allow CRUD
        operations (for now - future versions may require auth for write ops).
        """
        api = simple_task_server.api_url

        # Create should work
        task_data = {"title": "No Auth Test Task", "status": "todo"}
        resp = requests.post(f"{api}/tasks", json=task_data, timeout=REQUEST_TIMEOUT)
        assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
        created = resp.json()
        task_id = created["id"]

        # Read should work
        resp = requests.get(f"{api}/tasks/{task_id}", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200, f"Read failed: {resp.text}"

        # List should work
        resp = requests.get(f"{api}/tasks", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200, f"List failed: {resp.text}"
