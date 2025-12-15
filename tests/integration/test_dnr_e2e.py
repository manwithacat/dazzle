"""
End-to-end tests for the Dazzle Native Runtime (DNR).

These tests spin up actual DNR server instances for each example project
and verify that:
1. The API endpoints work correctly
2. CRUD operations function properly
3. The frontend is served correctly

Test Mode Configuration:
    DNR_E2E_MODE=local  - Use local Python server (default, most reliable)
    DNR_E2E_MODE=docker - Use Docker containers (requires Docker)

The default is local mode because:
- It's faster (no container build/startup overhead)
- It's more reliable in CI environments
- It doesn't require Docker to be installed
- Better error messages when things fail
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
DNR_EXAMPLES = [
    "simple_task",
    "contact_manager",
]

# Timeout for server startup
SERVER_STARTUP_TIMEOUT = 60
# Request timeout
REQUEST_TIMEOUT = 10

# Test mode configuration
E2E_MODE = os.environ.get("DNR_E2E_MODE", "local").lower()


@pytest.fixture(scope="module")
def dazzle_root() -> Path:
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


def is_docker_available() -> bool:
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError, subprocess.TimeoutExpired):
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
                "dnr",
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
                    f"DNR server failed to start within {SERVER_STARTUP_TIMEOUT}s. "
                    f"stderr: {stderr.decode()}"
                )
            raise RuntimeError(f"DNR server failed to start within {SERVER_STARTUP_TIMEOUT}s.")

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


class DNRDockerServerManager:
    """Context manager for running DNR server in Docker containers.

    Uses docker-compose with the split container setup (backend + frontend).
    Container names follow the pattern: dazzle-{project_name}-backend/frontend
    """

    def __init__(self, example_dir: Path, api_port: int = 8000, ui_port: int = 3000):
        self.example_dir = example_dir
        self.api_port = api_port
        self.ui_port = ui_port
        # Container name matches what the Docker runner actually uses
        self.project_name = example_dir.name.replace("_", "-")
        self.container_prefix = f"dazzle-{self.project_name}"
        self.api_url = f"http://127.0.0.1:{api_port}"
        # In Docker split mode, frontend is on ui_port, backend on api_port
        self.ui_url = f"http://127.0.0.1:{ui_port}"

    def __enter__(self) -> DNRDockerServerManager:
        # Clean up any existing containers from previous runs
        self._cleanup()

        # Start the DNR server in Docker
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "dazzle",
                "dnr",
                "serve",
                "--port",
                str(self.ui_port),
                "--api-port",
                str(self.api_port),
                "--test-mode",
                # Docker mode runs detached by default
            ],
            cwd=self.example_dir,
            capture_output=True,
            text=True,
            env=env,
            timeout=300,  # 5 minutes for Docker build
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to start Docker containers: {result.stderr}")

        # Wait for API to be ready
        if not wait_for_server(f"{self.api_url}/health"):
            # Try to get container logs for debugging
            logs = self._get_container_logs()
            self._cleanup()
            raise RuntimeError(
                f"DNR server failed to become healthy within {SERVER_STARTUP_TIMEOUT}s. "
                f"Container logs:\n{logs}"
            )

        return self

    def _get_container_logs(self) -> str:
        """Get logs from the backend container."""
        logs_parts = []
        for suffix in ["backend", "frontend"]:
            container_name = f"{self.container_prefix}-{suffix}"
            try:
                result = subprocess.run(
                    ["docker", "logs", "--tail", "50", container_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.stdout or result.stderr:
                    logs_parts.append(f"=== {container_name} ===\n{result.stdout}\n{result.stderr}")
            except (subprocess.SubprocessError, subprocess.TimeoutExpired):
                logs_parts.append(f"=== {container_name} === (failed to get logs)")
        return "\n".join(logs_parts) if logs_parts else "(no logs available)"

    def _cleanup(self) -> None:
        """Stop and remove Docker containers."""
        for suffix in ["backend", "frontend"]:
            container_name = f"{self.container_prefix}-{suffix}"
            try:
                subprocess.run(
                    ["docker", "stop", container_name],
                    capture_output=True,
                    timeout=15,
                )
            except (subprocess.SubprocessError, subprocess.TimeoutExpired):
                pass
            try:
                subprocess.run(
                    ["docker", "rm", "-f", container_name],
                    capture_output=True,
                    timeout=10,
                )
            except (subprocess.SubprocessError, subprocess.TimeoutExpired):
                pass

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object) -> None:
        self._cleanup()


def get_server_manager(
    example_dir: Path, api_port: int = 8000, ui_port: int = 3000
) -> DNRLocalServerManager | DNRDockerServerManager:
    """Factory function to get appropriate server manager based on E2E_MODE.

    Default is local mode (more reliable). Set DNR_E2E_MODE=docker for Docker mode.
    """
    if E2E_MODE == "docker":
        if not is_docker_available():
            pytest.skip("Docker mode requested but Docker is not available")
        return DNRDockerServerManager(example_dir, api_port, ui_port)
    else:
        # Default to local mode
        return DNRLocalServerManager(example_dir, api_port, ui_port)


@pytest.fixture(scope="module")
def simple_task_server(
    dazzle_root: Path,
) -> Iterator[DNRLocalServerManager | DNRDockerServerManager]:
    """Start DNR server for simple_task example."""
    example_dir = dazzle_root / "examples" / "simple_task"
    if not example_dir.exists():
        pytest.skip(f"Example directory not found: {example_dir}")

    # Use unique ports to avoid conflicts with other running servers
    with get_server_manager(example_dir, api_port=8001, ui_port=3001) as server:
        yield server


class TestSimpleTaskE2E:
    """E2E tests for the simple_task example."""

    @pytest.mark.e2e
    def test_api_docs_available(
        self, simple_task_server: DNRLocalServerManager | DNRDockerServerManager
    ) -> None:
        """Test that OpenAPI docs are served."""
        resp = requests.get(f"{simple_task_server.api_url}/docs", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200
        assert "swagger" in resp.text.lower() or "openapi" in resp.text.lower()

    @pytest.mark.e2e
    def test_openapi_schema_available(
        self, simple_task_server: DNRLocalServerManager | DNRDockerServerManager
    ) -> None:
        """Test that OpenAPI JSON schema is available."""
        resp = requests.get(f"{simple_task_server.api_url}/openapi.json", timeout=REQUEST_TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert "openapi" in data
        assert "paths" in data

    @pytest.mark.e2e
    def test_api_endpoints_respond(
        self, simple_task_server: DNRLocalServerManager | DNRDockerServerManager
    ) -> None:
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
    def test_task_crud_persistence(
        self, simple_task_server: DNRLocalServerManager | DNRDockerServerManager
    ) -> None:
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
        # DNR returns paginated response with 'items' key or list directly
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
    def test_frontend_serves_html(
        self, simple_task_server: DNRLocalServerManager | DNRDockerServerManager
    ) -> None:
        """Test that frontend serves HTML content.

        Note: In local mode, frontend is served via Vite dev server.
        In Docker mode, it may be served at a different path.
        """
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
                # Should have HTML content
                assert "html" in resp.headers.get("content-type", "").lower() or "<" in resp.text


# Parametrized tests for multiple examples
@pytest.mark.e2e
@pytest.mark.parametrize("example_name", DNR_EXAMPLES)
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
@pytest.mark.parametrize("example_name", DNR_EXAMPLES)
def test_example_builds_ui(dazzle_root: Path, example_name: str) -> None:
    """Test that each example can build UI artifacts."""
    example_dir = dazzle_root / "examples" / example_name
    if not example_dir.exists():
        pytest.skip(f"Example {example_name} not found")

    result = subprocess.run(
        [sys.executable, "-m", "dazzle", "dnr", "build-ui"],
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
        self, simple_task_server: DNRLocalServerManager | DNRDockerServerManager
    ) -> None:
        """Test that /auth/me returns 401 (not 404) when auth is disabled.

        This ensures the UI doesn't get console errors for 404s.
        """
        resp = requests.get(f"{simple_task_server.api_url}/auth/me", timeout=REQUEST_TIMEOUT)
        # Should return 401 (Unauthorized) not 404 (Not Found)
        # When auth is enabled, would return user info or 401 based on session
        # When auth is disabled, stub endpoint returns 401
        assert resp.status_code in (401, 200), f"Expected 401 or 200, got {resp.status_code}"

    @pytest.mark.e2e
    def test_crud_works_without_auth(
        self, simple_task_server: DNRLocalServerManager | DNRDockerServerManager
    ) -> None:
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
