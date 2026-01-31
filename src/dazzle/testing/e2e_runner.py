"""
E2E Test Runner with Server Lifecycle Management.

Provides unified E2E test execution that:
1. Ensures Playwright is installed
2. Starts the DNR server automatically
3. Runs Playwright-based E2E tests
4. Cleans up server after tests complete
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class E2ERunOptions:
    """Options for E2E test execution."""

    headless: bool = True
    priority: str | None = None
    tag: str | None = None
    flow_id: str | None = None
    timeout: int = 30000
    base_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"


@dataclass
class E2EFlowResult:
    """Result of a single E2E flow execution."""

    flow_id: str
    status: str  # "passed", "failed", "skipped"
    error: str | None = None
    duration_ms: float = 0


@dataclass
class E2ERunResult:
    """Result of E2E test run."""

    project_name: str
    started_at: datetime
    completed_at: datetime | None = None
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    flows: list[E2EFlowResult] = field(default_factory=list)
    error: str | None = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "project_name": self.project_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "success_rate": self.success_rate,
            "flows": [
                {
                    "flow_id": f.flow_id,
                    "status": f.status,
                    "error": f.error,
                    "duration_ms": f.duration_ms,
                }
                for f in self.flows
            ],
            "error": self.error,
        }


class E2ERunner:
    """
    Unified E2E test runner with server lifecycle management.

    This class provides a complete E2E testing solution that:
    1. Checks for Playwright installation
    2. Generates E2ETestSpec from DSL
    3. Starts the DNR server automatically
    4. Runs Playwright-based E2E tests
    5. Stops the server after tests complete

    Usage:
        runner = E2ERunner(Path("./my-project"))
        result = runner.run_all(E2ERunOptions(headless=True))
        print(f"Passed: {result.passed}/{result.total}")
    """

    def __init__(self, project_path: Path):
        """
        Initialize E2E runner.

        Args:
            project_path: Path to the Dazzle project directory
        """
        self.project_path = project_path.resolve()
        self._server_process: subprocess.Popen[bytes] | None = None
        self.api_port = 8000
        self.ui_port = 3000

    def ensure_playwright(self) -> tuple[bool, str]:
        """
        Check if Playwright and browsers are installed.

        Returns:
            Tuple of (is_installed, message)
        """
        # Check if playwright package is installed
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return False, (
                "Playwright is not installed. Install with:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

        # Check if browsers are installed
        try:
            with sync_playwright() as p:
                # Try to get chromium executable path
                browser_path = p.chromium.executable_path
                if not Path(browser_path).exists():
                    return False, (
                        "Playwright browser not installed. Run:\n  playwright install chromium"
                    )
        except Exception as e:
            error_msg = str(e).lower()
            if "executable" in error_msg or "browser" in error_msg:
                return False, (
                    "Playwright browser not installed. Run:\n  playwright install chromium"
                )
            return False, f"Error checking Playwright: {e}"

        return True, "Playwright is installed and ready"

    def _find_port(self, start: int) -> int:
        """Find an available port starting from the given port."""
        for port in range(start, start + 100):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("localhost", port)) != 0:
                    return port
        return start

    def start_server(self, timeout: int = 30) -> bool:
        """
        Start the DNR server.

        Args:
            timeout: Maximum seconds to wait for server to start

        Returns:
            True if server started successfully, False otherwise
        """
        print(f"Starting server for {self.project_path.name}...")

        # Find available ports
        self.api_port = self._find_port(8000)
        self.ui_port = self._find_port(3000)

        # Set up environment
        env = os.environ.copy()
        # Add src to PYTHONPATH if we're in the Dazzle development environment
        src_path = self.project_path.parent.parent / "src"
        if src_path.exists():
            env["PYTHONPATH"] = str(src_path)

        # Start the server
        try:
            self._server_process = subprocess.Popen(
                [sys.executable, "-m", "dazzle", "dnr", "serve", "--local"],
                cwd=self.project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
            )
        except Exception as e:
            print(f"Failed to start server: {e}")
            return False

        # Wait for server to be ready
        import re

        start_time = time.time()
        backend_ready = False
        frontend_ready = False

        while time.time() - start_time < timeout:
            if self._server_process.poll() is not None:
                # Server exited prematurely
                return False

            try:
                if self._server_process.stdout:
                    line = self._server_process.stdout.readline().decode()

                    # Parse port allocation message: "  UI:  3393"
                    if "UI:" in line and "http" not in line:
                        match = re.search(r"UI:\s*(\d+)", line)
                        if match:
                            self.ui_port = int(match.group(1))
                    elif "API:" in line and "http" not in line:
                        match = re.search(r"API:\s*(\d+)", line)
                        if match:
                            self.api_port = int(match.group(1))

                    # Also check the [DNR] output lines
                    if "Backend:" in line and "http://" in line:
                        match = re.search(r":(\d+)", line)
                        if match:
                            self.api_port = int(match.group(1))
                        backend_ready = True
                    elif "Frontend:" in line and "http://" in line:
                        match = re.search(r":(\d+)", line)
                        if match:
                            self.ui_port = int(match.group(1))
                        frontend_ready = True

                    # Server is ready when we see the Ctrl+C message or both backend/frontend
                    if "Press Ctrl+C" in line or (backend_ready and frontend_ready):
                        time.sleep(1)  # Give it a moment to fully initialize
                        return True
            except Exception:
                pass

            time.sleep(0.1)

        # Timed out but server might still be running
        return True

    def stop_server(self) -> None:
        """Stop the DNR server gracefully."""
        if self._server_process:
            self._server_process.terminate()
            try:
                self._server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._server_process.kill()
            self._server_process = None

        # Kill any orphaned processes (macOS/Linux only)
        try:
            subprocess.run(
                ["pkill", "-f", "dazzle dnr serve"],
                capture_output=True,
                check=False,
            )
        except FileNotFoundError:
            # pkill not available (e.g., on Windows)
            pass

    def generate_testspec(self) -> Any:
        """
        Generate E2ETestSpec from the project's DSL.

        Returns:
            E2ETestSpec object
        """
        from dazzle.core.fileset import discover_dsl_files
        from dazzle.core.linker import build_appspec
        from dazzle.core.manifest import load_manifest
        from dazzle.core.parser import parse_modules
        from dazzle.testing.testspec_generator import generate_e2e_testspec

        manifest_path = self.project_path / "dazzle.toml"
        manifest = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(self.project_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, manifest.project_root)

        return generate_e2e_testspec(appspec, manifest)

    def run_tests(
        self,
        testspec: Any,
        options: E2ERunOptions,
    ) -> E2ERunResult:
        """
        Run E2E tests with Playwright.

        Args:
            testspec: E2ETestSpec with flows to run
            options: E2E run options

        Returns:
            E2ERunResult with test outcomes
        """
        from playwright.sync_api import sync_playwright

        result = E2ERunResult(
            project_name=self.project_path.name,
            started_at=datetime.now(),
        )

        # Filter flows
        flows = testspec.flows

        if options.flow_id:
            flows = [f for f in flows if f.id == options.flow_id]
        if options.priority:
            from dazzle.core.ir import FlowPriority

            try:
                priority_enum = FlowPriority(options.priority)
                flows = [f for f in flows if f.priority == priority_enum]
            except ValueError:
                result.error = f"Invalid priority: {options.priority}"
                result.completed_at = datetime.now()
                return result
        if options.tag:
            flows = [f for f in flows if options.tag in f.tags]

        result.total = len(flows)

        if not flows:
            result.error = "No flows match the specified filters"
            result.completed_at = datetime.now()
            return result

        # Build fixtures dict for test execution
        fixtures = {f.id: f for f in testspec.fixtures}

        # Import the step execution helper
        from dazzle.cli.testing import _execute_step_sync

        # Create a simple adapter for URL resolution
        class SimpleAdapter:
            def __init__(self, base_url: str, api_url: str):
                self.base_url = base_url
                self.api_url = api_url

            def reset_sync(self) -> None:
                """Reset test data by calling /__test__/reset endpoint."""
                import urllib.request

                try:
                    url = f"{self.api_url}/__test__/reset"
                    req = urllib.request.Request(url, method="POST", data=b"")
                    with urllib.request.urlopen(req, timeout=10) as response:
                        response.read()
                except Exception as e:
                    # Log but don't fail - test mode might not be enabled
                    print(f"Warning: Could not reset test data: {e}")

            def seed_sync(self, fixtures: list) -> None:
                """Seed fixtures by calling /__test__/seed endpoint."""
                import urllib.request

                if not fixtures:
                    return

                try:
                    seed_data = {
                        "fixtures": [
                            {
                                "id": f.id,
                                "entity": f.entity,
                                "data": dict(f.data),
                            }
                            for f in fixtures
                        ]
                    }
                    url = f"{self.api_url}/__test__/seed"
                    req = urllib.request.Request(
                        url,
                        method="POST",
                        data=json.dumps(seed_data).encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(req, timeout=10) as response:
                        response.read()
                except Exception as e:
                    # Log but don't fail - test mode might not be enabled
                    print(f"Warning: Could not seed fixtures: {e}")

            def authenticate_sync(self, role: str | None = None) -> None:
                """Authenticate (no-op for now)."""
                pass

            def resolve_view_url(self, view_id: str) -> str:
                """Convert view ID to URL matching HTMX template routes."""
                parts = view_id.split("_")
                if len(parts) >= 2:
                    mode = parts[-1]
                    entity = "_".join(parts[:-1]).replace("_", "-")
                    mode_routes = {
                        "list": f"{self.base_url}/{entity}",
                        "create": f"{self.base_url}/{entity}/create",
                        "view": f"{self.base_url}/{entity}/test-id",
                        "detail": f"{self.base_url}/{entity}/test-id",
                        "edit": f"{self.base_url}/{entity}/test-id/edit",
                    }
                    if mode in mode_routes:
                        return mode_routes[mode]
                return f"{self.base_url}/{view_id}"

            def get_entity_count_sync(self, entity_name: str) -> int:
                """Get entity count via API."""
                import urllib.request

                try:
                    # DNR API routes are at /{entity}s, not /api/{entity}s
                    url = f"{self.api_url}/{entity_name.lower()}s"
                    with urllib.request.urlopen(url, timeout=5) as response:
                        data = json.loads(response.read().decode())
                        if isinstance(data, list):
                            return len(data)
                        # Paginated response: {"items": [...], "total": N, ...}
                        if isinstance(data, dict):
                            if "total" in data:
                                return data["total"]
                            if "items" in data:
                                return len(data["items"])
                            return data.get("count", 0)
                        return 0
                except Exception:
                    return 0

        adapter = SimpleAdapter(
            f"http://localhost:{self.ui_port}",
            f"http://localhost:{self.api_port}",
        )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=options.headless)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(options.timeout)

            for flow in flows:
                flow_start = time.time()
                flow_result = E2EFlowResult(flow_id=flow.id, status="passed")

                try:
                    # Reset database before each flow for isolation
                    adapter.reset_sync()

                    # Apply preconditions
                    if flow.preconditions:
                        if flow.preconditions.fixtures:
                            fixtures_to_seed = [
                                fixtures[fid]
                                for fid in flow.preconditions.fixtures
                                if fid in fixtures
                            ]
                            if fixtures_to_seed:
                                adapter.seed_sync(fixtures_to_seed)

                        if flow.preconditions.authenticated:
                            adapter.authenticate_sync(role=flow.preconditions.user_role)

                        if flow.preconditions.view:
                            url = adapter.resolve_view_url(flow.preconditions.view)
                            page.goto(url)

                    # Execute steps
                    for step in flow.steps:
                        try:
                            _execute_step_sync(page, step, adapter, fixtures, options.timeout)
                        except Exception as e:
                            flow_result.status = "failed"
                            flow_result.error = f"Step {step.kind.value}: {e}"
                            break

                except Exception as e:
                    flow_result.status = "failed"
                    flow_result.error = str(e)

                flow_result.duration_ms = (time.time() - flow_start) * 1000

                if flow_result.status == "passed":
                    result.passed += 1
                else:
                    result.failed += 1

                result.flows.append(flow_result)

            browser.close()

        result.completed_at = datetime.now()
        return result

    def run_all(self, options: E2ERunOptions | None = None) -> E2ERunResult:
        """
        Run full E2E test lifecycle.

        This method:
        1. Checks Playwright installation
        2. Generates E2ETestSpec from DSL
        3. Starts the DNR server
        4. Runs all E2E tests
        5. Stops the server

        Args:
            options: E2E run options (uses defaults if None)

        Returns:
            E2ERunResult with test outcomes
        """
        if options is None:
            options = E2ERunOptions()

        result = E2ERunResult(
            project_name=self.project_path.name,
            started_at=datetime.now(),
        )

        # Check Playwright
        playwright_ok, playwright_msg = self.ensure_playwright()
        if not playwright_ok:
            result.error = playwright_msg
            result.completed_at = datetime.now()
            return result

        # Generate testspec
        try:
            testspec = self.generate_testspec()
        except Exception as e:
            result.error = f"Failed to generate testspec: {e}"
            result.completed_at = datetime.now()
            return result

        # Start server
        try:
            if not self.start_server():
                result.error = "Failed to start DNR server"
                result.completed_at = datetime.now()
                return result

            # Update options with actual ports
            options.base_url = f"http://localhost:{self.ui_port}"
            options.api_url = f"http://localhost:{self.api_port}"

            # Run tests
            result = self.run_tests(testspec, options)

        finally:
            self.stop_server()

        return result


def format_e2e_report(result: E2ERunResult) -> str:
    """Format E2E test results as a human-readable report."""
    lines = []
    lines.append("=" * 60)
    lines.append("E2E TEST REPORT")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Project: {result.project_name}")
    lines.append(f"Started: {result.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
    if result.completed_at:
        duration = (result.completed_at - result.started_at).total_seconds()
        lines.append(f"Duration: {duration:.1f}s")
    lines.append("")

    if result.error:
        lines.append(f"ERROR: {result.error}")
        lines.append("")
    else:
        lines.append(f"Total: {result.total}")
        lines.append(f"Passed: {result.passed}")
        lines.append(f"Failed: {result.failed}")
        lines.append(f"Success Rate: {result.success_rate:.1f}%")
        lines.append("")

        if result.failed > 0:
            lines.append("-" * 40)
            lines.append("Failed Flows:")
            for flow in result.flows:
                if flow.status == "failed":
                    lines.append(f"  - {flow.flow_id}: {flow.error}")
            lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)
