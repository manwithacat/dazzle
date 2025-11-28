"""
End-to-end tests for the Dazzle Native Runtime (DNR).

These tests spin up actual DNR server instances for each example project
and verify that:
1. The API endpoints work correctly
2. CRUD operations function properly
3. The frontend is served correctly
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

# List of examples to test - these use the DNR stack
DNR_EXAMPLES = [
    "simple_task",
    "contact_manager",
]

# Timeout for server startup
SERVER_STARTUP_TIMEOUT = 30
# Request timeout
REQUEST_TIMEOUT = 10


@pytest.fixture(scope="module")
def dazzle_root():
    """Get the dazzle project root directory."""
    return Path(__file__).parent.parent.parent


def wait_for_server(url: str, timeout: int = SERVER_STARTUP_TIMEOUT) -> bool:
    """Wait for server to become available."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code < 500:
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(0.5)
    return False


class DNRServerManager:
    """Context manager for running DNR server in background."""

    def __init__(self, example_dir: Path, api_port: int = 8000, ui_port: int = 3000):
        self.example_dir = example_dir
        self.api_port = api_port
        self.ui_port = ui_port
        self.process = None
        self.api_url = f"http://127.0.0.1:{api_port}"
        self.ui_url = f"http://127.0.0.1:{ui_port}"

    def __enter__(self):
        # Start the DNR server
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        # Platform-specific process group handling
        kwargs = {}
        if sys.platform != "win32":
            kwargs["preexec_fn"] = os.setsid  # Create new process group (Unix)
        else:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        self.process = subprocess.Popen(
            [
                "dazzle",
                "dnr",
                "serve",
                "--port",
                str(self.ui_port),
                "--api-port",
                str(self.api_port),
                "--host",
                "127.0.0.1",
            ],
            cwd=self.example_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            **kwargs,
        )

        # Wait for API to be ready
        if not wait_for_server(f"{self.api_url}/docs"):
            # Get any error output
            self.process.terminate()
            _, stderr = self.process.communicate(timeout=5)
            raise RuntimeError(
                f"DNR server failed to start within {SERVER_STARTUP_TIMEOUT}s. "
                f"stderr: {stderr.decode()}"
            )

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
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
def simple_task_server(dazzle_root):
    """Start DNR server for simple_task example."""
    example_dir = dazzle_root / "examples" / "simple_task"
    if not example_dir.exists():
        pytest.skip(f"Example directory not found: {example_dir}")

    # Use unique ports to avoid conflicts
    with DNRServerManager(example_dir, api_port=8001, ui_port=3001) as server:
        yield server


class TestSimpleTaskE2E:
    """E2E tests for the simple_task example."""

    @pytest.mark.e2e
    def test_api_docs_available(self, simple_task_server):
        """Test that OpenAPI docs are served."""
        resp = requests.get(f"{simple_task_server.api_url}/docs", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200
        assert "swagger" in resp.text.lower() or "openapi" in resp.text.lower()

    @pytest.mark.e2e
    def test_openapi_schema_available(self, simple_task_server):
        """Test that OpenAPI JSON schema is available."""
        resp = requests.get(f"{simple_task_server.api_url}/openapi.json", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert "openapi" in data
        assert "paths" in data

    @pytest.mark.e2e
    def test_api_endpoints_respond(self, simple_task_server):
        """Test that API endpoints respond correctly."""
        api = simple_task_server.api_url

        # Test health endpoint
        resp = requests.get(f"{api}/health", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200, f"Health check failed: {resp.text}"

        # Test list endpoint returns paginated response
        resp = requests.get(f"{api}/api/tasks", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200, f"List failed: {resp.text}"
        data = resp.json()
        assert "items" in data or isinstance(data, list)

        # Test create endpoint accepts data (response validation only)
        task_data = {
            "title": "E2E Test Task",
            "status": "todo",
        }
        resp = requests.post(f"{api}/api/tasks", json=task_data, timeout=REQUEST_TIMEOUT)
        assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
        created = resp.json()
        assert "id" in created, "Response should have an ID"
        assert created["title"] == "E2E Test Task"

    @pytest.mark.e2e
    @pytest.mark.xfail(reason="CRUD persistence not fully implemented in DNR backend")
    def test_task_crud_full_cycle(self, simple_task_server):
        """Test full CRUD cycle for Task entity (xfail until backend fixed)."""
        api = simple_task_server.api_url

        # Create a task (POST to /api/tasks)
        task_data = {
            "title": "E2E Test Task",
            "description": "Created by E2E test",
            "status": "todo",
            "priority": "high",
        }
        resp = requests.post(f"{api}/api/tasks", json=task_data, timeout=REQUEST_TIMEOUT)
        assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
        created = resp.json()
        task_id = created.get("id")
        assert task_id is not None, "Created task should have an ID"

        # Read the task (GET /api/tasks/{id})
        resp = requests.get(f"{api}/api/tasks/{task_id}", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200, f"Read failed: {resp.text}"
        fetched = resp.json()
        assert fetched["title"] == "E2E Test Task"

        # Update the task (PUT /api/tasks/{id})
        update_data = {"title": "Updated E2E Task", "status": "in_progress"}
        resp = requests.put(f"{api}/api/tasks/{task_id}", json=update_data, timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200, f"Update failed: {resp.text}"
        updated = resp.json()
        assert updated["title"] == "Updated E2E Task"
        assert updated["status"] == "in_progress"

        # List tasks - should include our task (GET /api/tasks)
        resp = requests.get(f"{api}/api/tasks", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200, f"List failed: {resp.text}"
        data = resp.json()
        # DNR returns paginated response with 'items' key or list directly
        tasks = data.get("items", data) if isinstance(data, dict) else data
        assert isinstance(tasks, list)
        assert any(t["id"] == task_id for t in tasks)

        # Delete the task (DELETE /api/tasks/{id})
        resp = requests.delete(f"{api}/api/tasks/{task_id}", timeout=REQUEST_TIMEOUT)
        assert resp.status_code in (200, 204), f"Delete failed: {resp.text}"

        # Verify deletion
        resp = requests.get(f"{api}/api/tasks/{task_id}", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 404, "Task should be deleted"

    @pytest.mark.e2e
    def test_frontend_serves_html(self, simple_task_server):
        """Test that frontend serves HTML."""
        resp = requests.get(simple_task_server.ui_url, timeout=REQUEST_TIMEOUT)
        # Frontend might be served or proxied
        assert resp.status_code in (200, 302, 304), f"Frontend failed: {resp.status_code}"
        if resp.status_code == 200:
            # Should have HTML content
            assert "html" in resp.headers.get("content-type", "").lower() or "<" in resp.text


# Parametrized tests for multiple examples
@pytest.mark.e2e
@pytest.mark.parametrize("example_name", DNR_EXAMPLES)
def test_example_validates(dazzle_root, example_name):
    """Test that each example validates successfully."""
    example_dir = dazzle_root / "examples" / example_name
    if not example_dir.exists():
        pytest.skip(f"Example {example_name} not found")

    result = subprocess.run(
        ["dazzle", "validate"],
        cwd=example_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"Validation failed for {example_name}: {result.stderr}"


@pytest.mark.e2e
@pytest.mark.parametrize("example_name", DNR_EXAMPLES)
def test_example_builds_ui(dazzle_root, example_name):
    """Test that each example can build UI artifacts."""
    example_dir = dazzle_root / "examples" / example_name
    if not example_dir.exists():
        pytest.skip(f"Example {example_name} not found")

    result = subprocess.run(
        ["dazzle", "dnr", "build-ui"],
        cwd=example_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"UI build failed for {example_name}: {result.stderr}"
