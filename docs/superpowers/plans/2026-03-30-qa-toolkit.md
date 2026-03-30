# QA Toolkit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `dazzle qa visual` — a visual quality evaluation pipeline that captures screenshots of Dazzle app workspaces per persona, evaluates them via Claude Vision against 8 quality categories, and integrates findings into the `/improve` loop.

**Architecture:** A `src/dazzle/qa/` library package with composable modules (server lifecycle, capture, evaluate, report), thin CLI wrappers in `src/dazzle/cli/qa.py`, and `/improve` integration via two new gap types (`visual_quality`, `story_failure`). The package treats the running app as a black box via HTTP + Playwright.

**Tech Stack:** Python 3.12+, Playwright (browser automation), Anthropic SDK (Claude Vision via `[llm]` extra), httpx (health polling), existing `SessionManager` for auth, existing `BrowserGate` for Playwright lifecycle.

**Spec:** `docs/superpowers/specs/2026-03-30-qa-toolkit-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle/qa/__init__.py` | Create | Package init, exports `run_visual_qa` |
| `src/dazzle/qa/models.py` | Create | `CapturedScreen`, `Finding`, `QAReport` dataclasses |
| `src/dazzle/qa/categories.py` | Create | 8 evaluation categories as structured data |
| `src/dazzle/qa/server.py` | Create | `serve_app()` async context manager for process lifecycle |
| `src/dazzle/qa/capture.py` | Create | Playwright screenshot capture per persona/workspace |
| `src/dazzle/qa/evaluate.py` | Create | `QAEvaluator` protocol + `ClaudeEvaluator` default |
| `src/dazzle/qa/report.py` | Create | Findings aggregation, dedup, severity ranking, output |
| `src/dazzle/cli/qa.py` | Create | `dazzle qa visual`, `dazzle qa capture` CLI commands |
| `src/dazzle/cli/__init__.py` | Modify | Register `qa` typer subcommand |
| `.claude/commands/improve.md` | Modify | Add `visual_quality` gap type + tiered OBSERVE |
| `tests/unit/test_qa_models.py` | Create | Model + category tests |
| `tests/unit/test_qa_evaluate.py` | Create | Evaluator tests (mock LLM) |
| `tests/unit/test_qa_report.py` | Create | Report aggregation tests |

## Key Existing Code to Reuse

- **`SessionManager`** (`src/dazzle/testing/session_manager.py`): `create_session(persona_id)` → `PersonaSession` with `.session_token`
- **`BrowserGate`** (`src/dazzle/testing/browser_gate.py`): `sync_browser()` context manager → headless Chromium
- **`load_project_appspec()`** (`src/dazzle/cli/utils.py`): loads AppSpec IR from project directory
- **Workspace URL pattern**: `/app/workspaces/{workspace_name}` (from `testing/ux/runner.py`)

---

## Task 1: Models + Categories

**Files:**
- Create: `src/dazzle/qa/__init__.py`
- Create: `src/dazzle/qa/models.py`
- Create: `src/dazzle/qa/categories.py`
- Test: `tests/unit/test_qa_models.py`

- [ ] **Step 1: Write failing tests for models and categories**

```python
# tests/unit/test_qa_models.py
"""Tests for QA toolkit data models and categories."""

from pathlib import Path
from dazzle.qa.models import CapturedScreen, Finding, QAReport
from dazzle.qa.categories import CATEGORIES, get_category


class TestModels:
    def test_captured_screen_fields(self):
        screen = CapturedScreen(
            persona="teacher",
            workspace="teacher_workspace",
            url="/app/workspaces/teacher_workspace",
            screenshot=Path(".dazzle/qa/screenshots/teacher_workspace_teacher.png"),
            viewport="desktop",
        )
        assert screen.persona == "teacher"
        assert screen.workspace == "teacher_workspace"

    def test_finding_fields(self):
        finding = Finding(
            category="data_quality",
            severity="high",
            location="teacher_workspace > Student column",
            description="UUID visible instead of student name",
            suggestion="Apply ref_display filter",
        )
        assert finding.category == "data_quality"
        assert finding.severity == "high"

    def test_qa_report_from_findings(self):
        findings = [
            Finding("data_quality", "high", "loc1", "desc1", "sug1"),
            Finding("alignment", "low", "loc2", "desc2", "sug2"),
        ]
        report = QAReport(app="project_tracker", findings=findings)
        assert report.app == "project_tracker"
        assert len(report.findings) == 2
        assert report.high_count == 1
        assert report.medium_count == 0
        assert report.low_count == 1


class TestCategories:
    def test_eight_categories_defined(self):
        assert len(CATEGORIES) == 8

    def test_each_category_has_required_fields(self):
        for cat in CATEGORIES:
            assert cat.id, f"Category missing id"
            assert cat.definition, f"{cat.id} missing definition"
            assert cat.example, f"{cat.id} missing example"
            assert cat.severity_default in ("high", "medium", "low")

    def test_get_category_by_id(self):
        cat = get_category("data_quality")
        assert cat is not None
        assert cat.id == "data_quality"

    def test_get_category_unknown_returns_none(self):
        assert get_category("nonexistent") is None

    def test_category_ids(self):
        ids = {c.id for c in CATEGORIES}
        expected = {
            "text_wrapping", "truncation", "title_formatting", "column_layout",
            "empty_state", "alignment", "readability", "data_quality",
        }
        assert ids == expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_qa_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.qa'`

- [ ] **Step 3: Create the package and models**

```python
# src/dazzle/qa/__init__.py
"""
QA toolkit for Dazzle applications.

Visual quality evaluation, screenshot capture, and findings reporting.
"""

from dazzle.qa.models import CapturedScreen, Finding, QAReport

__all__ = ["CapturedScreen", "Finding", "QAReport"]
```

```python
# src/dazzle/qa/models.py
"""Data models for the QA toolkit."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class CapturedScreen:
    """A screenshot captured from a running Dazzle app."""

    persona: str
    workspace: str
    url: str
    screenshot: Path
    viewport: str = "desktop"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Finding:
    """A single visual quality finding."""

    category: str
    severity: str  # "high", "medium", "low"
    location: str
    description: str
    suggestion: str


@dataclass
class QAReport:
    """Aggregated QA findings for an app."""

    app: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "high")

    @property
    def medium_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "medium")

    @property
    def low_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "low")

    @property
    def total(self) -> int:
        return len(self.findings)
```

```python
# src/dazzle/qa/categories.py
"""Visual quality evaluation categories.

Eight categories adapted from the AegisMark visual quality assessment,
battle-tested against real workspace UIs.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    """A visual quality evaluation category."""

    id: str
    definition: str
    example: str
    severity_default: str  # "high", "medium", "low"


CATEGORIES: list[Category] = [
    Category(
        id="text_wrapping",
        definition="Text that wraps awkwardly, breaking words or names across lines",
        example="Username 'Alexand-er' wraps mid-word in the card header",
        severity_default="medium",
    ),
    Category(
        id="truncation",
        definition="Content cut off or hidden by container boundaries",
        example="Assessment title truncated to 'Introduction to...' with no tooltip",
        severity_default="medium",
    ),
    Category(
        id="title_formatting",
        definition="Card/region titles that sit inline with content instead of above it, "
        "headings that lack visual weight or hierarchy",
        example="Region title 'Needs Review' sits alongside filter controls instead of above them",
        severity_default="high",
    ),
    Category(
        id="column_layout",
        definition="Columns too narrow, data cramped, poor use of horizontal space",
        example="Date column shows '2026-...' because column is 60px wide",
        severity_default="medium",
    ),
    Category(
        id="empty_state",
        definition="Regions showing no data without helpful messaging",
        example="Table body is blank — no 'No results' message",
        severity_default="low",
    ),
    Category(
        id="alignment",
        definition="Misaligned elements, uneven spacing, visual inconsistency",
        example="Card titles have 16px left margin except the third card (8px)",
        severity_default="low",
    ),
    Category(
        id="readability",
        definition="Font too small, poor contrast, information density too high",
        example="8px grey text on light grey background for status labels",
        severity_default="medium",
    ),
    Category(
        id="data_quality",
        definition="Raw UUIDs visible, 'None' values, internal field names shown to users, raw Python dicts",
        example="Student column shows 'a1b2c3d4-e5f6-...' instead of student name",
        severity_default="high",
    ),
]

_CATEGORY_MAP: dict[str, Category] = {c.id: c for c in CATEGORIES}


def get_category(category_id: str) -> Category | None:
    """Look up a category by ID."""
    return _CATEGORY_MAP.get(category_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_qa_models.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/qa/__init__.py src/dazzle/qa/models.py src/dazzle/qa/categories.py tests/unit/test_qa_models.py
git commit -m "feat(qa): add models and evaluation categories for visual QA toolkit"
```

---

## Task 2: Server Lifecycle (`server.py`)

**Files:**
- Create: `src/dazzle/qa/server.py`
- Test: `tests/unit/test_qa_server.py`

The server lifecycle module starts a Dazzle app as a subprocess, polls for health, and cleans up on exit. It also supports connecting to an already-running instance via URL.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_qa_server.py
"""Tests for QA server lifecycle management."""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

import pytest

from dazzle.qa.server import AppConnection, connect_app, _poll_health


class TestAppConnection:
    def test_connection_from_url(self):
        conn = AppConnection(
            site_url="http://localhost:3000",
            api_url="http://localhost:8000",
            process=None,
        )
        assert conn.site_url == "http://localhost:3000"
        assert conn.api_url == "http://localhost:8000"
        assert conn.is_external

    def test_connection_with_process(self):
        mock_proc = MagicMock()
        conn = AppConnection(
            site_url="http://localhost:3000",
            api_url="http://localhost:8000",
            process=mock_proc,
        )
        assert not conn.is_external


class TestConnectApp:
    def test_connect_with_url_returns_external(self):
        conn = connect_app(url="http://localhost:3000")
        assert conn.site_url == "http://localhost:3000"
        assert conn.is_external

    def test_connect_with_url_infers_api(self):
        conn = connect_app(url="http://localhost:3000")
        assert conn.api_url == "http://localhost:8000"

    def test_connect_with_explicit_api_url(self):
        conn = connect_app(url="http://localhost:3000", api_url="http://localhost:9000")
        assert conn.api_url == "http://localhost:9000"


class TestPollHealth:
    @pytest.mark.asyncio
    async def test_poll_health_success(self):
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        result = await _poll_health("http://localhost:8000", timeout=5, client=mock_client)
        assert result is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_qa_server.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement server.py**

```python
# src/dazzle/qa/server.py
"""Process lifecycle management for QA toolkit.

Starts a Dazzle app, polls for health, and cleans up on exit.
Supports connecting to already-running instances via URL.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_SITE_PORT = 3000
_DEFAULT_API_PORT = 8000
_HEALTH_POLL_INTERVAL = 0.5
_HEALTH_TIMEOUT = 30


@dataclass
class AppConnection:
    """Connection to a running Dazzle app."""

    site_url: str
    api_url: str
    process: subprocess.Popen[bytes] | None = None

    @property
    def is_external(self) -> bool:
        """True if connected to an external instance (not managed by us)."""
        return self.process is None

    def stop(self) -> None:
        """Stop the managed process if we own it."""
        if self.process is None:
            return
        logger.info("Stopping app server (pid %d)", self.process.pid)
        try:
            self.process.send_signal(signal.SIGTERM)
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("Server did not stop gracefully, sending SIGKILL")
            self.process.kill()
            self.process.wait(timeout=2)
        except Exception:
            logger.debug("Error stopping server", exc_info=True)


def connect_app(
    *,
    url: str | None = None,
    api_url: str | None = None,
    project_dir: Path | None = None,
) -> AppConnection:
    """Connect to a Dazzle app.

    If ``url`` is provided, connects to an existing instance.
    If ``project_dir`` is provided, starts the app as a subprocess.
    """
    if url:
        # External connection — infer API URL from site URL if not given
        if not api_url:
            # Default: site on 3000, API on 8000
            api_url = url.replace(":3000", ":8000")
            if api_url == url:
                api_url = url.rstrip("/") + ":8000"
        return AppConnection(site_url=url, api_url=api_url, process=None)

    if project_dir is None:
        raise ValueError("Either url or project_dir must be provided")

    return _start_app(project_dir)


def _start_app(project_dir: Path) -> AppConnection:
    """Start a Dazzle app as a subprocess."""
    env = {**os.environ, "DAZZLE_TEST_SECRET": "qa-toolkit"}
    cmd = [sys.executable, "-m", "dazzle", "serve", "--local"]

    logger.info("Starting app in %s", project_dir)
    proc = subprocess.Popen(
        cmd,
        cwd=project_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    site_url = f"http://localhost:{_DEFAULT_SITE_PORT}"
    api_url_str = f"http://localhost:{_DEFAULT_API_PORT}"

    return AppConnection(site_url=site_url, api_url=api_url_str, process=proc)


async def _poll_health(
    api_url: str,
    *,
    timeout: float = _HEALTH_TIMEOUT,
    client: object | None = None,
) -> bool:
    """Poll the health endpoint until ready or timeout."""
    import httpx

    deadline = asyncio.get_event_loop().time() + timeout
    url = f"{api_url.rstrip('/')}/docs"

    async def _check(http_client: httpx.AsyncClient) -> bool:
        while asyncio.get_event_loop().time() < deadline:
            try:
                resp = await http_client.get(url, timeout=2)
                if resp.status_code == 200:
                    return True
            except (httpx.ConnectError, httpx.ReadTimeout, OSError):
                pass
            await asyncio.sleep(_HEALTH_POLL_INTERVAL)
        return False

    if client is not None:
        return await _check(client)  # type: ignore[arg-type]

    async with httpx.AsyncClient() as http_client:
        return await _check(http_client)


async def wait_for_ready(conn: AppConnection, timeout: float = _HEALTH_TIMEOUT) -> bool:
    """Wait for the app to be ready to accept requests."""
    return await _poll_health(conn.api_url, timeout=timeout)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_qa_server.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/qa/server.py tests/unit/test_qa_server.py
git commit -m "feat(qa): add server lifecycle management for QA toolkit"
```

---

## Task 3: Capture (`capture.py`)

**Files:**
- Create: `src/dazzle/qa/capture.py`
- Test: `tests/unit/test_qa_capture.py`

Screenshot capture using Playwright. Reuses `SessionManager` for auth and `BrowserGate` for browser lifecycle.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_qa_capture.py
"""Tests for QA screenshot capture."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from dazzle.qa.capture import build_capture_plan, CaptureTarget
from dazzle.qa.models import CapturedScreen


class TestCaptureTarget:
    def test_target_fields(self):
        target = CaptureTarget(
            persona="teacher",
            workspace="teacher_workspace",
            url="/app/workspaces/teacher_workspace",
        )
        assert target.persona == "teacher"
        assert target.workspace == "teacher_workspace"


class TestBuildCapturePlan:
    def test_plan_from_appspec(self):
        """Build capture plan from a mock AppSpec."""
        mock_appspec = MagicMock()
        mock_workspace = MagicMock()
        mock_workspace.name = "admin_dashboard"
        mock_workspace.access = None
        mock_appspec.workspaces = [mock_workspace]

        mock_persona = MagicMock()
        mock_persona.name = "admin"
        mock_appspec.archetypes = [mock_persona]

        targets = build_capture_plan(mock_appspec)
        assert len(targets) >= 1
        assert any(t.workspace == "admin_dashboard" for t in targets)

    def test_plan_empty_workspaces(self):
        mock_appspec = MagicMock()
        mock_appspec.workspaces = []
        mock_appspec.archetypes = []
        targets = build_capture_plan(mock_appspec)
        assert targets == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_qa_capture.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement capture.py**

```python
# src/dazzle/qa/capture.py
"""Playwright-based screenshot capture for QA toolkit.

Captures screenshots of each workspace per persona using headless Playwright.
Reuses SessionManager for auth and BrowserGate for browser lifecycle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dazzle.qa.models import CapturedScreen

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = ".dazzle/qa/screenshots"
DEFAULT_VIEWPORT = {"width": 1280, "height": 800}


@dataclass
class CaptureTarget:
    """A single screenshot target."""

    persona: str
    workspace: str
    url: str


def build_capture_plan(appspec: Any) -> list[CaptureTarget]:
    """Build a list of capture targets from an AppSpec.

    Creates one target per (persona, workspace) combination.
    """
    workspaces = list(appspec.workspaces) if appspec.workspaces else []
    personas = list(appspec.archetypes) if appspec.archetypes else []

    if not workspaces or not personas:
        return []

    targets: list[CaptureTarget] = []
    for ws in workspaces:
        for persona in personas:
            persona_name = getattr(persona, "name", None) or getattr(persona, "id", "unknown")
            targets.append(CaptureTarget(
                persona=persona_name,
                workspace=ws.name,
                url=f"/app/workspaces/{ws.name}",
            ))

    return targets


async def capture_screenshots(
    targets: list[CaptureTarget],
    site_url: str,
    api_url: str,
    project_dir: Path,
    *,
    output_dir: Path | None = None,
) -> list[CapturedScreen]:
    """Capture screenshots for all targets.

    Authenticates as each persona, navigates to the workspace,
    and takes a full-page screenshot.
    """
    from dazzle.testing.browser_gate import BrowserGate
    from dazzle.testing.session_manager import SessionManager

    out = output_dir or (project_dir / SCREENSHOTS_DIR)
    out.mkdir(parents=True, exist_ok=True)

    session_mgr = SessionManager(project_dir, base_url=api_url)
    gate = BrowserGate(max_concurrent=1, headless=True)

    results: list[CapturedScreen] = []

    with gate.sync_browser() as browser:
        for target in targets:
            try:
                screen = _capture_one(
                    browser, target, site_url, api_url, session_mgr, out,
                )
                if screen:
                    results.append(screen)
            except Exception:
                logger.warning(
                    "Failed to capture %s/%s",
                    target.workspace, target.persona,
                    exc_info=True,
                )

    return results


def _capture_one(
    browser: Any,
    target: CaptureTarget,
    site_url: str,
    api_url: str,
    session_mgr: Any,
    output_dir: Path,
) -> CapturedScreen | None:
    """Capture a single screenshot."""
    import asyncio

    # Get session token for persona
    loop = asyncio.new_event_loop()
    try:
        session = loop.run_until_complete(
            session_mgr.create_session(target.persona)
        )
    finally:
        loop.close()

    # Create browser context with auth cookie
    context = browser.new_context(viewport=DEFAULT_VIEWPORT)
    context.add_cookies([{
        "name": "dazzle_session",
        "value": session.session_token,
        "domain": "localhost",
        "path": "/",
    }])

    page = context.new_page()
    full_url = f"{site_url}{target.url}"

    logger.info("Capturing %s as %s", target.workspace, target.persona)
    page.goto(full_url, wait_until="networkidle", timeout=15000)

    # Wait for content to settle
    page.wait_for_timeout(1000)

    filename = f"{target.workspace}_{target.persona}.png"
    screenshot_path = output_dir / filename
    page.screenshot(path=str(screenshot_path), full_page=True)

    context.close()

    return CapturedScreen(
        persona=target.persona,
        workspace=target.workspace,
        url=target.url,
        screenshot=screenshot_path,
        viewport="desktop",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_qa_capture.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/qa/capture.py tests/unit/test_qa_capture.py
git commit -m "feat(qa): add Playwright screenshot capture for visual QA"
```

---

## Task 4: Evaluator (`evaluate.py`)

**Files:**
- Create: `src/dazzle/qa/evaluate.py`
- Test: `tests/unit/test_qa_evaluate.py`

Pluggable LLM evaluator. Protocol interface with a Claude Vision default implementation. The prompt is adapted directly from AegisMark's battle-tested prompt.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_qa_evaluate.py
"""Tests for QA visual evaluator."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dazzle.qa.evaluate import (
    ClaudeEvaluator,
    build_evaluation_prompt,
    parse_findings,
)
from dazzle.qa.models import CapturedScreen, Finding


class TestBuildPrompt:
    def test_prompt_contains_all_categories(self):
        prompt = build_evaluation_prompt("admin_dashboard")
        assert "text_wrapping" in prompt
        assert "truncation" in prompt
        assert "title_formatting" in prompt
        assert "column_layout" in prompt
        assert "empty_state" in prompt
        assert "alignment" in prompt
        assert "readability" in prompt
        assert "data_quality" in prompt

    def test_prompt_contains_context(self):
        prompt = build_evaluation_prompt("teacher_workspace")
        assert "teacher_workspace" in prompt

    def test_prompt_requests_json_array(self):
        prompt = build_evaluation_prompt("dashboard")
        assert "JSON array" in prompt


class TestParseFindings:
    def test_parse_valid_json(self):
        raw = json.dumps([
            {
                "category": "data_quality",
                "severity": "high",
                "location": "Student column",
                "description": "UUID visible",
                "suggestion": "Use ref_display",
            }
        ])
        findings = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0].category == "data_quality"
        assert findings[0].severity == "high"

    def test_parse_empty_array(self):
        findings = parse_findings("[]")
        assert findings == []

    def test_parse_with_markdown_fences(self):
        raw = "```json\n[]\n```"
        findings = parse_findings(raw)
        assert findings == []

    def test_parse_invalid_json_returns_empty(self):
        findings = parse_findings("not json")
        assert findings == []

    def test_parse_skips_invalid_entries(self):
        raw = json.dumps([
            {"category": "data_quality", "severity": "high", "location": "x", "description": "y", "suggestion": "z"},
            {"invalid": "entry"},
        ])
        findings = parse_findings(raw)
        assert len(findings) == 1


class TestClaudeEvaluator:
    def test_evaluate_calls_anthropic(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='[]')]
        mock_client.messages.create.return_value = mock_response

        evaluator = ClaudeEvaluator(client=mock_client)
        screen = CapturedScreen(
            persona="admin",
            workspace="admin_dashboard",
            url="/app/workspaces/admin_dashboard",
            screenshot=Path("/dev/null"),
        )

        with patch("dazzle.qa.evaluate._read_screenshot_b64", return_value="fake_base64"):
            findings = evaluator.evaluate(screen)

        mock_client.messages.create.assert_called_once()
        assert findings == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_qa_evaluate.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement evaluate.py**

```python
# src/dazzle/qa/evaluate.py
"""Pluggable LLM evaluator for visual quality assessment.

Provides a Protocol interface and a Claude Vision default implementation.
The evaluation prompt is adapted from AegisMark's battle-tested approach.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, Protocol

from dazzle.qa.categories import CATEGORIES
from dazzle.qa.models import CapturedScreen, Finding

logger = logging.getLogger(__name__)


class QAEvaluator(Protocol):
    """Interface for visual quality evaluators."""

    def evaluate(self, screen: CapturedScreen, categories: list[str] | None = None) -> list[Finding]: ...


def build_evaluation_prompt(workspace_context: str) -> str:
    """Build the evaluation prompt with category definitions.

    Adapted from AegisMark's visual quality assessment prompt.
    """
    category_lines = []
    for cat in CATEGORIES:
        category_lines.append(f"- {cat.id}: {cat.definition}")

    categories_text = "\n".join(category_lines)

    return f"""\
You are a UX quality assessor for a web application built with the Dazzle framework.

Evaluate this screenshot for visual quality from the perspective of a user who \
uses this application daily. The page context is: {workspace_context}

For each issue you find, return a JSON object. Be specific about the location \
on screen and what is wrong. Only flag things a human would actually notice and \
find confusing or unprofessional.

Check EVERY card/section title on the page individually. Each card or region \
should have a clear heading ABOVE its content, visually distinct and separated.

Categories:
{categories_text}

Return ONLY a JSON array (no markdown fences). Each element:
{{
  "category": "<one of the categories above>",
  "severity": "high|medium|low",
  "location": "<which card/region/table on the page>",
  "description": "<what a human would see wrong>",
  "suggestion": "<specific fix>"
}}

If the page looks genuinely good, return an empty array: []"""


def parse_findings(raw: str) -> list[Finding]:
    """Parse LLM response text into Finding objects.

    Handles markdown fences, invalid JSON, and malformed entries gracefully.
    """
    text = raw.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse evaluator response as JSON")
        return []

    if not isinstance(data, list):
        return []

    findings: list[Finding] = []
    required_keys = {"category", "severity", "location", "description", "suggestion"}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if not required_keys.issubset(entry.keys()):
            logger.debug("Skipping malformed finding: %s", entry)
            continue
        findings.append(Finding(
            category=entry["category"],
            severity=entry["severity"],
            location=entry["location"],
            description=entry["description"],
            suggestion=entry["suggestion"],
        ))

    return findings


def _read_screenshot_b64(path: Path) -> str:
    """Read a screenshot file and return base64-encoded content."""
    return base64.b64encode(path.read_bytes()).decode("utf-8")


class ClaudeEvaluator:
    """Claude Vision-based visual quality evaluator.

    Requires the ``anthropic`` package (``pip install dazzle-dsl[llm]``).
    """

    def __init__(self, *, client: Any = None, model: str = "claude-sonnet-4-20250514") -> None:
        self._client = client
        self._model = model

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError:
            raise RuntimeError(
                "Claude evaluator requires the anthropic package. "
                "Install with: pip install dazzle-dsl[llm]"
            ) from None
        return anthropic.Anthropic()

    def evaluate(
        self,
        screen: CapturedScreen,
        categories: list[str] | None = None,
    ) -> list[Finding]:
        """Evaluate a screenshot for visual quality issues."""
        client = self._get_client()
        prompt = build_evaluation_prompt(
            f"{screen.workspace} (as {screen.persona})"
        )
        image_b64 = _read_screenshot_b64(screen.screenshot)

        response = client.messages.create(
            model=self._model,
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_b64,
                        },
                    },
                ],
            }],
        )

        raw_text = response.content[0].text
        return parse_findings(raw_text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_qa_evaluate.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/qa/evaluate.py tests/unit/test_qa_evaluate.py
git commit -m "feat(qa): add pluggable LLM evaluator with Claude Vision default"
```

---

## Task 5: Report (`report.py`)

**Files:**
- Create: `src/dazzle/qa/report.py`
- Test: `tests/unit/test_qa_report.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_qa_report.py
"""Tests for QA findings report aggregation."""

from dazzle.qa.models import Finding, QAReport
from dazzle.qa.report import deduplicate, sort_by_severity, format_table


class TestDeduplicate:
    def test_dedup_same_category_and_location(self):
        findings = [
            Finding("data_quality", "high", "Student column", "UUID visible", "fix"),
            Finding("data_quality", "high", "Student column", "UUID shown", "fix2"),
        ]
        result = deduplicate(findings)
        assert len(result) == 1

    def test_dedup_different_locations_kept(self):
        findings = [
            Finding("data_quality", "high", "Student column", "UUID visible", "fix"),
            Finding("data_quality", "high", "Teacher column", "UUID visible", "fix"),
        ]
        result = deduplicate(findings)
        assert len(result) == 2

    def test_dedup_different_categories_kept(self):
        findings = [
            Finding("data_quality", "high", "col1", "issue1", "fix1"),
            Finding("alignment", "low", "col1", "issue2", "fix2"),
        ]
        result = deduplicate(findings)
        assert len(result) == 2


class TestSortBySeverity:
    def test_high_before_medium_before_low(self):
        findings = [
            Finding("a", "low", "x", "x", "x"),
            Finding("b", "high", "x", "x", "x"),
            Finding("c", "medium", "x", "x", "x"),
        ]
        result = sort_by_severity(findings)
        assert [f.severity for f in result] == ["high", "medium", "low"]


class TestFormatTable:
    def test_empty_findings(self):
        report = QAReport(app="test_app", findings=[])
        output = format_table(report)
        assert "0 findings" in output

    def test_findings_in_table(self):
        findings = [Finding("data_quality", "high", "col1", "UUID visible", "fix")]
        report = QAReport(app="test_app", findings=findings)
        output = format_table(report)
        assert "data_quality" in output
        assert "high" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_qa_report.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement report.py**

```python
# src/dazzle/qa/report.py
"""Findings aggregation, deduplication, and output formatting."""

from __future__ import annotations

import json

from dazzle.qa.models import Finding, QAReport

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def deduplicate(findings: list[Finding]) -> list[Finding]:
    """Remove duplicate findings by (category, location)."""
    seen: set[tuple[str, str]] = set()
    result: list[Finding] = []
    for f in findings:
        key = (f.category, f.location)
        if key not in seen:
            seen.add(key)
            result.append(f)
    return result


def sort_by_severity(findings: list[Finding]) -> list[Finding]:
    """Sort findings: high → medium → low."""
    return sorted(findings, key=lambda f: _SEVERITY_ORDER.get(f.severity, 99))


def format_table(report: QAReport) -> str:
    """Format a QA report as a human-readable table."""
    lines = [f"\nVisual QA: {report.app} — {report.total} findings"]
    lines.append(f"  High: {report.high_count}  Medium: {report.medium_count}  Low: {report.low_count}")

    if not report.findings:
        lines.append("  No findings — page looks good.")
        return "\n".join(lines)

    lines.append("")
    lines.append(f"  {'Sev':<8} {'Category':<18} {'Location':<30} Description")
    lines.append(f"  {'---':<8} {'--------':<18} {'--------':<30} -----------")
    for f in sort_by_severity(report.findings):
        lines.append(f"  {f.severity:<8} {f.category:<18} {f.location:<30} {f.description}")

    return "\n".join(lines)


def format_json(report: QAReport) -> str:
    """Format a QA report as JSON."""
    return json.dumps({
        "app": report.app,
        "total": report.total,
        "high": report.high_count,
        "medium": report.medium_count,
        "low": report.low_count,
        "findings": [
            {
                "category": f.category,
                "severity": f.severity,
                "location": f.location,
                "description": f.description,
                "suggestion": f.suggestion,
            }
            for f in sort_by_severity(report.findings)
        ],
    }, indent=2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_qa_report.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/qa/report.py tests/unit/test_qa_report.py
git commit -m "feat(qa): add findings aggregation and report formatting"
```

---

## Task 6: CLI (`cli/qa.py`) + Registration

**Files:**
- Create: `src/dazzle/cli/qa.py`
- Modify: `src/dazzle/cli/__init__.py`

- [ ] **Step 1: Create the CLI module**

```python
# src/dazzle/cli/qa.py
"""CLI subcommands for QA toolkit.

Provides `dazzle qa visual` and `dazzle qa capture`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

qa_app = typer.Typer(
    help="QA toolkit — visual quality evaluation and screenshot capture.",
    no_args_is_help=True,
)


@qa_app.command("visual")
def qa_visual(
    url: str = typer.Option(None, "--url", "-u", help="URL of running app (skip auto-start)"),
    app: str = typer.Option(None, "--app", "-a", help="Example app name (e.g., project_tracker)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Run visual quality evaluation against a Dazzle app."""
    from dazzle.qa.capture import build_capture_plan, capture_screenshots
    from dazzle.qa.evaluate import ClaudeEvaluator
    from dazzle.qa.models import QAReport
    from dazzle.qa.report import deduplicate, format_json, format_table
    from dazzle.qa.server import connect_app, wait_for_ready

    project_dir = _resolve_project_dir(app)

    # Load AppSpec for capture planning
    from dazzle.cli.utils import load_project_appspec

    appspec = load_project_appspec(project_dir)
    targets = build_capture_plan(appspec)

    if not targets:
        typer.echo("No workspaces found to evaluate.")
        raise typer.Exit(code=0)

    # Connect to app
    conn = connect_app(url=url, project_dir=None if url else project_dir)

    try:
        if not conn.is_external:
            typer.echo("Starting app server...")
            ready = asyncio.run(wait_for_ready(conn))
            if not ready:
                typer.echo("App server did not become ready.", err=True)
                raise typer.Exit(code=1)

        typer.echo(f"Capturing {len(targets)} screenshots...")
        screens = asyncio.run(
            capture_screenshots(targets, conn.site_url, conn.api_url, project_dir)
        )

        if not screens:
            typer.echo("No screenshots captured.", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"Evaluating {len(screens)} screenshots via Claude Vision...")
        evaluator = ClaudeEvaluator()
        all_findings = []
        for screen in screens:
            findings = evaluator.evaluate(screen)
            all_findings.extend(findings)

        all_findings = deduplicate(all_findings)
        app_name = app or project_dir.name
        report = QAReport(app=app_name, findings=all_findings)

        if as_json:
            typer.echo(format_json(report))
        else:
            typer.echo(format_table(report))

        if report.high_count > 0:
            raise typer.Exit(code=1)

    finally:
        conn.stop()


@qa_app.command("capture")
def qa_capture(
    url: str = typer.Option(None, "--url", "-u", help="URL of running app"),
    app: str = typer.Option(None, "--app", "-a", help="Example app name"),
    persona: str = typer.Option(None, "--persona", "-p", help="Capture only this persona"),
) -> None:
    """Capture screenshots without evaluation (no LLM required)."""
    from dazzle.qa.capture import build_capture_plan, capture_screenshots
    from dazzle.qa.server import connect_app, wait_for_ready

    project_dir = _resolve_project_dir(app)

    from dazzle.cli.utils import load_project_appspec

    appspec = load_project_appspec(project_dir)
    targets = build_capture_plan(appspec)

    if persona:
        targets = [t for t in targets if t.persona == persona]

    if not targets:
        typer.echo("No capture targets found.")
        raise typer.Exit(code=0)

    conn = connect_app(url=url, project_dir=None if url else project_dir)

    try:
        if not conn.is_external:
            typer.echo("Starting app server...")
            ready = asyncio.run(wait_for_ready(conn))
            if not ready:
                typer.echo("App server did not become ready.", err=True)
                raise typer.Exit(code=1)

        typer.echo(f"Capturing {len(targets)} screenshots...")
        screens = asyncio.run(
            capture_screenshots(targets, conn.site_url, conn.api_url, project_dir)
        )

        for s in screens:
            typer.echo(f"  {s.workspace}/{s.persona} → {s.screenshot}")

        typer.echo(f"\n{len(screens)} screenshots saved.")

    finally:
        conn.stop()


def _resolve_project_dir(app: str | None) -> Path:
    """Resolve the project directory from --app flag or cwd."""
    if app:
        examples_dir = Path.cwd() / "examples" / app
        if examples_dir.exists():
            return examples_dir
        # Try relative to dazzle package
        import dazzle
        pkg_root = Path(dazzle.__file__).resolve().parents[1]
        examples_dir = pkg_root / "examples" / app
        if examples_dir.exists():
            return examples_dir
        raise typer.BadParameter(f"Example app '{app}' not found")
    return Path.cwd()
```

- [ ] **Step 2: Register in CLI __init__.py**

In `src/dazzle/cli/__init__.py`, find where subcommands are registered (around line 265-305 where `app.add_typer` calls are). Add:

```python
from dazzle.cli.qa import qa_app
app.add_typer(qa_app, name="qa")
```

- [ ] **Step 3: Verify CLI registration works**

Run: `python -m dazzle qa --help`
Expected: Shows "QA toolkit — visual quality evaluation and screenshot capture." with `visual` and `capture` subcommands.

- [ ] **Step 4: Run ruff + mypy**

Run: `ruff check src/dazzle/qa/ src/dazzle/cli/qa.py --fix && ruff format src/dazzle/qa/ src/dazzle/cli/qa.py && mypy src/dazzle/qa/ src/dazzle/cli/qa.py --ignore-missing-imports`

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/qa.py src/dazzle/cli/__init__.py
git commit -m "feat(qa): add dazzle qa visual and dazzle qa capture CLI commands"
```

---

## Task 7: `/improve` Integration

**Files:**
- Modify: `.claude/commands/improve.md`

- [ ] **Step 1: Update the OBSERVE phase**

Add the tiered check strategy after the existing gap scanning. In `.claude/commands/improve.md`, after the existing "pick next PENDING gap" logic in OBSERVE, add:

```markdown
### Tiered Gap Discovery

When all existing gaps are DONE or BLOCKED, discover new gaps in tiers:

**Tier 1 (every cycle, free):** Re-scan DSL
- `dazzle validate`, `dazzle lint`, conformance, fidelity

**Tier 2 (when Tier 1 exhausted, medium cost):** Visual QA
- Run `dazzle qa visual --app {app} --json` for each example app
- Parse findings, add to backlog as `visual_quality` gaps
- Severity mapping: high→critical, medium→warning, low→info

**Tier 3 (future):** Story verification
- Reserved for story sidecar integration (not yet implemented)
```

- [ ] **Step 2: Add new gap type handling to ENHANCE**

Add to the ENHANCE section:

```markdown
**Visual quality finding** → Determine fix type from the finding's category and suggestion:
- `data_quality` findings → Usually a template or filter fix in `src/dazzle_ui/`
- `title_formatting` findings → Template HTML structure fix
- `alignment`/`column_layout` findings → CSS or template fix
- `empty_state` findings → Add empty state messaging to templates
- If the fix requires a framework change (not app-specific), file a GitHub issue instead of fixing directly
```

- [ ] **Step 3: Add new verification for visual gaps**

Add to the VERIFY section:

```markdown
| Visual quality | Re-run `dazzle qa visual --app {app} --json` — finding should not reappear |
```

- [ ] **Step 4: Commit**

```bash
git add .claude/commands/improve.md
git commit -m "feat(improve): add visual_quality gap type with tiered discovery"
```

---

## Task 8: Final Verification

- [ ] **Step 1: Run all QA tests**

Run: `pytest tests/unit/test_qa_models.py tests/unit/test_qa_evaluate.py tests/unit/test_qa_report.py tests/unit/test_qa_server.py tests/unit/test_qa_capture.py -v`
Expected: ALL PASS

- [ ] **Step 2: Run ruff + mypy on entire QA package**

Run: `ruff check src/dazzle/qa/ --fix && ruff format src/dazzle/qa/ && mypy src/dazzle/qa/ --ignore-missing-imports`

- [ ] **Step 3: Verify CLI works end-to-end**

Run: `python -m dazzle qa --help && python -m dazzle qa visual --help && python -m dazzle qa capture --help`
Expected: All three show valid help text

- [ ] **Step 4: Run full test suite for regressions**

Run: `pytest tests/unit/ -x -q --timeout=60 -m "not e2e"`
Expected: ALL PASS, no regressions

- [ ] **Step 5: Commit any fixes**

```bash
git add -A && git commit -m "fix: resolve any issues from QA toolkit final verification"
```

---

## Summary

| Task | What it builds | Tests |
|------|---------------|-------|
| 1 | Models + Categories | 10 |
| 2 | Server Lifecycle | 5 |
| 3 | Capture | 3 |
| 4 | Evaluator (Claude Vision) | 8 |
| 5 | Report | 6 |
| 6 | CLI commands | — (integration) |
| 7 | /improve integration | — (skill update) |
| 8 | Final verification | Full suite |
| **Total** | **8 new files, 2 modified** | **~32 new tests** |

## Not in This Plan (Follow-up)

- **Story sidecar** (`qa/stories.py`) — separate plan after visual QA is working
- **`dazzle qa stories init`** scaffold command — depends on stories module
- **MCP read operations** for QA report data — add after CLI is proven
