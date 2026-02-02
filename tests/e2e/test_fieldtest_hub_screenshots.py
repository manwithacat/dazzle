"""
Screenshot generation tests for fieldtest_hub example.

This module takes screenshots of all 22+ surfaces in fieldtest_hub,
providing comprehensive visual coverage of the most complex example.

Usage:
    pytest tests/e2e/test_fieldtest_hub_screenshots.py -v
    pytest tests/e2e/test_fieldtest_hub_screenshots.py -v -k "screenshot"

Screenshots are saved to: examples/fieldtest_hub/screenshots/
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

# Try to import Playwright
try:
    from playwright.sync_api import Page, sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    sync_playwright = None
    Page = None

# Skip if DNR is not available
pytest.importorskip("dazzle_back")
pytest.importorskip("dazzle_ui")

# Configuration
SERVER_STARTUP_TIMEOUT = 60

# All fieldtest_hub surfaces and their routes
FIELDTEST_HUB_ROUTES = [
    # Device surfaces
    ("/device/list", "device_list", "Device Dashboard"),
    ("/device/create", "device_create", "Register Device"),
    # Tester surfaces
    ("/tester/list", "tester_list", "Tester Directory"),
    ("/tester/create", "tester_create", "Register Tester"),
    # Issue Report surfaces
    ("/issuereport/list", "issue_report_list", "Issue Board"),
    ("/issuereport/create", "issue_report_create", "Report Issue"),
    # Test Session surfaces
    ("/testsession/list", "test_session_list", "Test Sessions"),
    ("/testsession/create", "test_session_create", "Log Test Session"),
    # Firmware Release surfaces
    ("/firmwarerelease/list", "firmware_release_list", "Firmware Releases"),
    ("/firmwarerelease/create", "firmware_release_create", "Create Firmware"),
    # Task surfaces
    ("/task/list", "task_list", "Tasks"),
    ("/task/create", "task_create", "Create Task"),
    # Workspaces (dashboard routes)
    ("/", "home", "Home/Dashboard"),
]


class FieldtestHubServer:
    """Context manager for running fieldtest_hub server."""

    def __init__(self, example_dir: Path):
        self.example_dir = example_dir
        self.process: subprocess.Popen | None = None
        self.api_url: str = ""
        self.ui_url: str = ""
        self.screenshot_dir = example_dir / "screenshots"

    def __enter__(self) -> FieldtestHubServer:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        # Clear runtime file
        dazzle_dir = self.example_dir / ".dazzle"
        runtime_file = dazzle_dir / "runtime.json"
        if runtime_file.exists():
            runtime_file.unlink()

        # Platform-specific handling
        kwargs: dict = {}
        if sys.platform != "win32":
            kwargs["preexec_fn"] = os.setsid
        else:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "dazzle",
                "serve",
                "--local",
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

        # Wait for runtime file
        for _ in range(SERVER_STARTUP_TIMEOUT * 2):
            if runtime_file.exists():
                try:
                    data = json.loads(runtime_file.read_text())
                    self.api_url = f"http://127.0.0.1:{data['api_port']}"
                    self.ui_url = f"http://127.0.0.1:{data['ui_port']}"
                    break
                except (json.JSONDecodeError, KeyError):
                    pass
            time.sleep(0.5)

        # Wait for API health
        if not self._wait_for_health():
            self._cleanup()
            raise RuntimeError("fieldtest_hub server failed to start")

        # Create screenshot directory
        self.screenshot_dir.mkdir(exist_ok=True)

        return self

    def _wait_for_health(self, timeout: int = SERVER_STARTUP_TIMEOUT) -> bool:
        import requests

        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = requests.get(f"{self.api_url}/health", timeout=2)
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def _cleanup(self) -> None:
        if self.process:
            try:
                if sys.platform != "win32":
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                else:
                    self.process.terminate()
            except (ProcessLookupError, OSError):
                pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._cleanup()


@pytest.fixture(scope="module")
def dazzle_root() -> Path:
    """Get the dazzle project root directory."""
    return Path(__file__).parent.parent.parent


@pytest.fixture(scope="module")
def browser():
    """Create a browser instance for the test module."""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not installed")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture(scope="module")
def server(dazzle_root: Path) -> Iterator[FieldtestHubServer]:
    """Start fieldtest_hub server for the test module."""
    example_dir = dazzle_root / "examples" / "fieldtest_hub"
    if not example_dir.exists():
        pytest.skip("fieldtest_hub example not found")

    with FieldtestHubServer(example_dir) as srv:
        yield srv


@pytest.fixture
def page(browser, server) -> Iterator[Page]:
    """Create a new page for each test."""
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    yield page
    page.close()
    context.close()


def take_screenshot(page: Page, server: FieldtestHubServer, name: str) -> Path:
    """Take a screenshot and save it to the example's screenshot directory."""
    path = server.screenshot_dir / f"{name}.png"
    page.screenshot(path=str(path))
    return path


class TestFieldtestHubScreenshots:
    """Take screenshots of all fieldtest_hub surfaces."""

    @pytest.mark.e2e
    @pytest.mark.parametrize(
        "route,name,title",
        FIELDTEST_HUB_ROUTES,
        ids=[r[1] for r in FIELDTEST_HUB_ROUTES],
    )
    def test_screenshot_surface(
        self, page: Page, server: FieldtestHubServer, route: str, name: str, title: str
    ) -> None:
        """Take a screenshot of each surface."""
        url = f"{server.ui_url}{route}"
        page.goto(url)
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1500)  # Extra time for JS rendering

        # Take screenshot
        screenshot_path = take_screenshot(page, server, name)
        assert screenshot_path.exists(), f"Screenshot not created: {screenshot_path}"

    @pytest.mark.e2e
    def test_screenshot_all_views_summary(self, server: FieldtestHubServer) -> None:
        """Verify all expected screenshots were created."""
        expected = [r[1] for r in FIELDTEST_HUB_ROUTES]
        missing = []
        for name in expected:
            path = server.screenshot_dir / f"{name}.png"
            if not path.exists():
                missing.append(name)

        if missing:
            pytest.fail(f"Missing screenshots: {missing}")


class TestFieldtestHubDetailViews:
    """Take screenshots of detail/edit views (require existing data)."""

    @pytest.fixture(autouse=True)
    def seed_data(self, server: FieldtestHubServer) -> None:
        """Seed some test data for detail views."""
        import requests

        api = server.api_url

        # Create a tester first
        tester_resp = requests.post(
            f"{api}/testers",
            json={
                "name": "Test Tester",
                "email": "test@example.com",
                "location": "Test Lab",
                "skill_level": "engineer",
                "active": True,
            },
            timeout=10,
        )
        if tester_resp.status_code in (200, 201):
            self.tester_id = tester_resp.json().get("id")
        else:
            self.tester_id = None

        # Create a device
        device_resp = requests.post(
            f"{api}/devices",
            json={
                "name": "Test Device Alpha",
                "model": "Model X",
                "batch_number": "BATCH-001",
                "serial_number": "SN-001",
                "firmware_version": "1.0.0",
                "status": "active",
            },
            timeout=10,
        )
        if device_resp.status_code in (200, 201):
            self.device_id = device_resp.json().get("id")
        else:
            self.device_id = None

        # Create a firmware release
        fw_resp = requests.post(
            f"{api}/firmwarereleases",
            json={
                "version": "1.0.0",
                "release_notes": "Initial release",
                "release_date": "2024-01-01T00:00:00Z",
                "status": "released",
            },
            timeout=10,
        )
        if fw_resp.status_code in (200, 201):
            self.firmware_id = fw_resp.json().get("id")
        else:
            self.firmware_id = None

        # Create an issue report
        if self.device_id and self.tester_id:
            issue_resp = requests.post(
                f"{api}/issuereports",
                json={
                    "device_id": self.device_id,
                    "reported_by_id": self.tester_id,
                    "category": "battery",
                    "severity": "high",
                    "description": "Battery drains quickly",
                    "status": "open",
                },
                timeout=10,
            )
            if issue_resp.status_code in (200, 201):
                self.issue_id = issue_resp.json().get("id")
            else:
                self.issue_id = None
        else:
            self.issue_id = None

        # Create a test session
        if self.device_id and self.tester_id:
            session_resp = requests.post(
                f"{api}/testsessions",
                json={
                    "device_id": self.device_id,
                    "tester_id": self.tester_id,
                    "duration_minutes": 60,
                    "environment": "indoor",
                    "notes": "Standard testing",
                },
                timeout=10,
            )
            if session_resp.status_code in (200, 201):
                self.session_id = session_resp.json().get("id")
            else:
                self.session_id = None
        else:
            self.session_id = None

        # Create a task
        if self.tester_id:
            task_resp = requests.post(
                f"{api}/tasks",
                json={
                    "type": "debugging",
                    "created_by_id": self.tester_id,
                    "status": "open",
                    "notes": "Investigate battery issue",
                },
                timeout=10,
            )
            if task_resp.status_code in (200, 201):
                self.task_id = task_resp.json().get("id")
            else:
                self.task_id = None
        else:
            self.task_id = None

    @pytest.mark.e2e
    def test_screenshot_device_detail(self, page: Page, server: FieldtestHubServer) -> None:
        """Screenshot of device detail view."""
        if not hasattr(self, "device_id") or not self.device_id:
            pytest.skip("No device created")

        page.goto(f"{server.ui_url}/device/{self.device_id}")
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1500)
        take_screenshot(page, server, "device_detail")

    @pytest.mark.e2e
    def test_screenshot_device_edit(self, page: Page, server: FieldtestHubServer) -> None:
        """Screenshot of device edit view."""
        if not hasattr(self, "device_id") or not self.device_id:
            pytest.skip("No device created")

        page.goto(f"{server.ui_url}/device/{self.device_id}/edit")
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1500)
        take_screenshot(page, server, "device_edit")

    @pytest.mark.e2e
    def test_screenshot_tester_detail(self, page: Page, server: FieldtestHubServer) -> None:
        """Screenshot of tester detail view."""
        if not hasattr(self, "tester_id") or not self.tester_id:
            pytest.skip("No tester created")

        page.goto(f"{server.ui_url}/tester/{self.tester_id}")
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1500)
        take_screenshot(page, server, "tester_detail")

    @pytest.mark.e2e
    def test_screenshot_tester_edit(self, page: Page, server: FieldtestHubServer) -> None:
        """Screenshot of tester edit view."""
        if not hasattr(self, "tester_id") or not self.tester_id:
            pytest.skip("No tester created")

        page.goto(f"{server.ui_url}/tester/{self.tester_id}/edit")
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1500)
        take_screenshot(page, server, "tester_edit")

    @pytest.mark.e2e
    def test_screenshot_issue_detail(self, page: Page, server: FieldtestHubServer) -> None:
        """Screenshot of issue report detail view."""
        if not hasattr(self, "issue_id") or not self.issue_id:
            pytest.skip("No issue created")

        page.goto(f"{server.ui_url}/issuereport/{self.issue_id}")
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1500)
        take_screenshot(page, server, "issue_report_detail")

    @pytest.mark.e2e
    def test_screenshot_issue_edit(self, page: Page, server: FieldtestHubServer) -> None:
        """Screenshot of issue report edit view."""
        if not hasattr(self, "issue_id") or not self.issue_id:
            pytest.skip("No issue created")

        page.goto(f"{server.ui_url}/issuereport/{self.issue_id}/edit")
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1500)
        take_screenshot(page, server, "issue_report_edit")

    @pytest.mark.e2e
    def test_screenshot_firmware_detail(self, page: Page, server: FieldtestHubServer) -> None:
        """Screenshot of firmware detail view."""
        if not hasattr(self, "firmware_id") or not self.firmware_id:
            pytest.skip("No firmware created")

        page.goto(f"{server.ui_url}/firmwarerelease/{self.firmware_id}")
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1500)
        take_screenshot(page, server, "firmware_release_detail")

    @pytest.mark.e2e
    def test_screenshot_firmware_edit(self, page: Page, server: FieldtestHubServer) -> None:
        """Screenshot of firmware edit view."""
        if not hasattr(self, "firmware_id") or not self.firmware_id:
            pytest.skip("No firmware created")

        page.goto(f"{server.ui_url}/firmwarerelease/{self.firmware_id}/edit")
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1500)
        take_screenshot(page, server, "firmware_release_edit")

    @pytest.mark.e2e
    def test_screenshot_task_detail(self, page: Page, server: FieldtestHubServer) -> None:
        """Screenshot of task detail view."""
        if not hasattr(self, "task_id") or not self.task_id:
            pytest.skip("No task created")

        page.goto(f"{server.ui_url}/task/{self.task_id}")
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1500)
        take_screenshot(page, server, "task_detail")

    @pytest.mark.e2e
    def test_screenshot_task_edit(self, page: Page, server: FieldtestHubServer) -> None:
        """Screenshot of task edit view."""
        if not hasattr(self, "task_id") or not self.task_id:
            pytest.skip("No task created")

        page.goto(f"{server.ui_url}/task/{self.task_id}/edit")
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1500)
        take_screenshot(page, server, "task_edit")


# Mark all tests as e2e
pytestmark = pytest.mark.e2e
