# Layer 4 — Agent Action Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/ux-cycle` Step 6 EXPLORE reliably produce non-empty PROP-NNN findings across all 5 `examples/` Dazzle apps, by giving the agent loop action→consequence feedback and auto-picking business personas from the DSL.

**Architecture:** Four separable additive changes across four code boundaries. (1) `ActionResult` gains four optional fields for state-change + cognition signals. (2) `PlaywrightExecutor` captures before/after page state around every action and attaches a console listener. (3) `DazzleAgent._build_messages` renders the new fields in compressed history and appends a bail-nudge after 3 consecutive no-op actions. (4) `explore_strategy` gains a persona picker that auto-selects non-platform personas from the `AppSpec`, fans out across all business personas per cycle, and dedups proposals by `(example_app, component_name)`.

**Tech Stack:** Python 3.12, Playwright async API, Anthropic SDK (`use_tool_calls=True`), pytest + pytest-asyncio, ruff + mypy, PostgreSQL (test env), Redis (test env).

**Context:** Runs in-session on `main` branch (cycle 196 already committed the sticky-exhausted baseline; cycle 197 ships the fix). Spec at `docs/superpowers/specs/2026-04-14-layer-4-agent-action-feedback-design.md`.

---

## File Structure

### Files Created

| Path | Responsibility |
|---|---|
| `tests/unit/test_action_result.py` | Unit tests for `ActionResult` dataclass (default construction, explicit values, backward compat). |
| `tests/unit/test_playwright_executor_enrichment.py` | Unit tests for state capture, DOM hash, console listener, per-action-type population. |
| `tests/unit/test_agent_history_rendering.py` | Unit tests for `_build_messages` history line variants and bail-nudge trigger conditions. |
| `tests/e2e/test_explore_strategy_e2e.py` | E2E verification over the 5 examples (`@pytest.mark.e2e`, manual local run). |

### Files Modified

| Path | Change |
|---|---|
| `src/dazzle/agent/models.py` | Add 4 optional fields to `ActionResult`. |
| `src/dazzle/agent/executor.py` | Add console listener + state capture in `PlaywrightExecutor.__init__` and `execute`. |
| `src/dazzle/agent/core.py` | Refactor `_build_messages` history rendering + add bail-nudge; extract `_format_history_line` + `_is_stuck` helpers. |
| `src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py` | Add `pick_explore_personas`, `pick_start_path`, update `run_explore_strategy` signature and fan-out logic, update `ExploreOutcome` shape, add proposal dedup. |
| `tests/unit/test_explore_strategy.py` | Add 11 tests for persona picker, start-path picker, fan-out, dedup. Existing 6 tests must pass unchanged. |

### Files Left Untouched

- `src/dazzle/agent/observer.py` — observer is unchanged
- `src/dazzle/agent/missions/ux_explore.py` — mission builder is unchanged
- `src/dazzle/agent/missions/_shared.py` — stagnation criterion unchanged
- `src/dazzle/cli/runtime_impl/ux_cycle_impl/fitness_strategy.py` — unchanged; must keep working (23 existing tests pass unchanged)
- `src/dazzle_back/runtime/qa_routes.py` — unchanged
- `.claude/commands/ux-cycle.md` — runbook unchanged (signature change is documented in CHANGELOG Agent Guidance)

---

## Task 1: `ActionResult` shape extension

**Files:**
- Modify: `src/dazzle/agent/models.py:147-163`
- Create: `tests/unit/test_action_result.py`

**Goal:** Add 4 optional fields to `ActionResult` (3 state fields + 1 cognition field) with safe defaults so every existing caller continues to work unchanged.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_action_result.py`:

```python
"""Tests for ActionResult (cycle 197 — L1 action feedback extensions)."""

from dazzle.agent.models import ActionResult


class TestActionResultDefaults:
    def test_minimal_construction_sets_new_fields_to_none_or_empty(self) -> None:
        """ActionResult(message=...) leaves the new fields at safe defaults."""
        result = ActionResult(message="Clicked button")
        assert result.message == "Clicked button"
        assert result.error is None
        assert result.data == {}
        # Cycle 197 additions — all default to None / empty list
        assert result.from_url is None
        assert result.to_url is None
        assert result.state_changed is None
        assert result.console_errors_during_action == []

    def test_explicit_values_are_preserved(self) -> None:
        result = ActionResult(
            message="navigated",
            from_url="/a",
            to_url="/b",
            state_changed=True,
            console_errors_during_action=["TypeError: x is undefined"],
        )
        assert result.from_url == "/a"
        assert result.to_url == "/b"
        assert result.state_changed is True
        assert result.console_errors_during_action == ["TypeError: x is undefined"]

    def test_legacy_positional_construction_still_works(self) -> None:
        """Existing callers (fitness engine, tests) construct with only the old fields."""
        # These mirror real ActionResult(...) constructions found in the codebase
        r1 = ActionResult(message="Tool invocation: propose_component")
        r2 = ActionResult(message="", error="Selector not found")
        assert r1.state_changed is None
        assert r2.state_changed is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_action_result.py -v`

Expected: FAIL with `AttributeError: 'ActionResult' object has no attribute 'from_url'`

- [ ] **Step 3: Add the new fields to `ActionResult`**

Edit `src/dazzle/agent/models.py` — find the existing `@dataclass class ActionResult` (around line 157) and add the 4 new fields after `data`:

```python
@dataclass
class ActionResult:
    """Result of executing an action."""

    message: str
    error: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    # Cycle 197 — L1 action feedback
    from_url: str | None = None
    to_url: str | None = None
    state_changed: bool | None = None
    # Cycle 197 — cognition foothold (action-linked console errors)
    console_errors_during_action: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_action_result.py -v`

Expected: 3 passed.

- [ ] **Step 5: Regression check — existing consumers still work**

Run: `pytest tests/unit/fitness/test_fitness_strategy_integration.py tests/unit/test_agent_tool_use.py tests/integration/test_agent_investigator_tool_use.py -q`

Expected: `48 passed` (23 fitness + 23 agent tool-use + 2 investigator). No test that constructs `ActionResult` should fail.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/agent/models.py tests/unit/test_action_result.py
git commit -m "feat(agent): extend ActionResult with L1 feedback fields (cycle 197 task 1)

Adds 4 optional fields to ActionResult:
- from_url, to_url, state_changed — L1 action feedback
- console_errors_during_action — cognition foothold

All default to None / empty list so every existing caller continues
to work unchanged. Verified: 48 existing agent/fitness/investigator
tests still pass."
```

---

## Task 2: `PlaywrightExecutor` console listener

**Files:**
- Modify: `src/dazzle/agent/executor.py:58-75`
- Create: `tests/unit/test_playwright_executor_enrichment.py`

**Goal:** Attach a `page.on("console", ...)` listener in `PlaywrightExecutor.__init__` that buffers console error messages for later diff-slicing by `execute()`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_playwright_executor_enrichment.py`:

```python
"""Tests for PlaywrightExecutor cycle-197 enrichment.

Covers:
- Console listener buffer accumulates errors during executor lifetime
- State capture before/after each action populates from_url/to_url/state_changed
- Per-action-type population (scroll optimistic True, assert optimistic False, tool None)
- Error path preserves new fields
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from typing import Any

import pytest

from dazzle.agent.executor import PlaywrightExecutor
from dazzle.agent.models import ActionType, AgentAction


def _make_mock_page(url: str = "http://localhost/", content: str = "<html></html>") -> MagicMock:
    """Build a MagicMock that looks like a Playwright Page."""
    page = MagicMock()
    page.url = url
    # Console listener machinery
    page._listeners: dict[str, list[Any]] = {}
    def _on(event: str, handler: Any) -> None:
        page._listeners.setdefault(event, []).append(handler)
    page.on = MagicMock(side_effect=_on)
    # content() is async
    page.content = AsyncMock(return_value=content)
    # wait_for_load_state is async
    page.wait_for_load_state = AsyncMock()
    return page


class TestConsoleListener:
    def test_init_attaches_console_listener(self) -> None:
        page = _make_mock_page()
        executor = PlaywrightExecutor(page=page)
        # Listener should be registered
        page.on.assert_called_once()
        assert page.on.call_args.args[0] == "console"

    def test_console_error_messages_accumulate_in_buffer(self) -> None:
        page = _make_mock_page()
        executor = PlaywrightExecutor(page=page)
        # Simulate the listener firing
        error_handler = page._listeners["console"][0]
        msg_error = MagicMock(type="error", text="TypeError: x is undefined")
        msg_log = MagicMock(type="log", text="plain log")
        error_handler(msg_error)
        error_handler(msg_log)
        error_handler(msg_error)
        # Only 'error' level is buffered
        assert executor._console_errors_buffer == [
            "TypeError: x is undefined",
            "TypeError: x is undefined",
        ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_playwright_executor_enrichment.py::TestConsoleListener -v`

Expected: FAIL — `PlaywrightExecutor.__init__()` doesn't call `page.on` and has no `_console_errors_buffer` attribute.

- [ ] **Step 3: Add console listener to PlaywrightExecutor**

Edit `src/dazzle/agent/executor.py` — find the `class PlaywrightExecutor` definition (around line 58) and replace its `__init__` with:

```python
class PlaywrightExecutor:
    """Execute actions via Playwright page object."""

    def __init__(self, page: Any) -> None:
        self._page = page
        # Cycle 197 — console error buffer for action-window attribution
        self._console_errors_buffer: list[str] = []
        page.on("console", self._on_console)

    def _on_console(self, msg: Any) -> None:
        """Buffer console error messages for action-window diff-slicing."""
        try:
            if msg.type == "error":
                self._console_errors_buffer.append(msg.text)
        except Exception:
            # Never let a malformed console message crash the executor
            pass
```

If there's existing `__init__` code beyond the `_page` assignment, preserve it.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_playwright_executor_enrichment.py::TestConsoleListener -v`

Expected: 2 passed.

- [ ] **Step 5: Regression check**

Run: `pytest tests/unit/fitness/test_fitness_strategy_integration.py -q`

Expected: `23 passed`. If any fitness test fails because of the new `page.on("console")` call, that means the mock Playwright `page` in those tests doesn't implement `on()`. If so, update those tests to supply a `page.on = MagicMock()` — but ONLY if the failure is in the mock setup, NOT in the executor behaviour.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/agent/executor.py tests/unit/test_playwright_executor_enrichment.py
git commit -m "feat(agent): PlaywrightExecutor buffers console errors (cycle 197 task 2)

Attach page.on('console') listener in __init__ to buffer error-level
messages. Buffer is diff-sliced by execute() to attribute console
errors to individual actions (see task 3)."
```

---

## Task 3: `PlaywrightExecutor.execute` state capture

**Files:**
- Modify: `src/dazzle/agent/executor.py` — the `execute` method
- Modify: `tests/unit/test_playwright_executor_enrichment.py`

**Goal:** Wrap the existing per-action-type dispatch with before/after state capture and diff-slice the console buffer, populating the new `ActionResult` fields per the per-action-type table.

- [ ] **Step 1: Write the failing tests (state capture cases)**

Append to `tests/unit/test_playwright_executor_enrichment.py`:

```python
import hashlib


def _dom_hash_of(html: str) -> str:
    return hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]


def _make_clicking_page(before_url: str, after_url: str, before_html: str, after_html: str) -> MagicMock:
    """Page whose url and content() change after the click fires."""
    page = _make_mock_page(url=before_url, content=before_html)
    calls = {"n": 0}

    async def _content_after() -> str:
        calls["n"] += 1
        return after_html if calls["n"] > 1 else before_html

    page.content = AsyncMock(side_effect=_content_after)
    locator = MagicMock()
    locator.click = AsyncMock(side_effect=lambda **kw: setattr(page, "url", after_url))
    page.locator = MagicMock(return_value=locator)
    return page


@pytest.mark.asyncio
class TestStateCapture:
    async def test_click_navigates_populates_from_and_to_url(self) -> None:
        page = _make_clicking_page(
            before_url="http://localhost/app",
            after_url="http://localhost/app/contacts/1",
            before_html="<html>before</html>",
            after_html="<html>after</html>",
        )
        executor = PlaywrightExecutor(page=page)
        action = AgentAction(type=ActionType.CLICK, target="button.x")
        result = await executor.execute(action)

        assert result.error is None
        assert result.from_url == "http://localhost/app"
        assert result.to_url == "http://localhost/app/contacts/1"
        assert result.state_changed is True

    async def test_click_no_op_detected(self) -> None:
        """Click fires but URL and DOM hash are unchanged → state_changed False."""
        page = _make_mock_page(url="http://localhost/app", content="<html>same</html>")
        locator = MagicMock()
        locator.click = AsyncMock()  # Does NOT change page.url
        page.locator = MagicMock(return_value=locator)

        executor = PlaywrightExecutor(page=page)
        action = AgentAction(type=ActionType.CLICK, target="a.broken")
        result = await executor.execute(action)

        assert result.from_url == "http://localhost/app"
        assert result.to_url == "http://localhost/app"
        assert result.state_changed is False

    async def test_scroll_is_optimistic_state_changed_true(self) -> None:
        page = _make_mock_page()
        page.evaluate = AsyncMock()  # scroll uses evaluate()
        executor = PlaywrightExecutor(page=page)
        action = AgentAction(type=ActionType.SCROLL)
        result = await executor.execute(action)
        assert result.state_changed is True  # optimistic

    async def test_assert_is_optimistic_state_changed_false(self) -> None:
        page = _make_mock_page()
        locator = MagicMock()
        locator.wait_for = AsyncMock()
        page.locator = MagicMock(return_value=locator)
        executor = PlaywrightExecutor(page=page)
        action = AgentAction(type=ActionType.ASSERT, target="some condition")
        result = await executor.execute(action)
        assert result.state_changed is False  # optimistic

    async def test_tool_action_has_none_state_fields(self) -> None:
        page = _make_mock_page()
        executor = PlaywrightExecutor(page=page)
        action = AgentAction(type=ActionType.TOOL, target="propose_component")
        result = await executor.execute(action)
        assert result.from_url is None
        assert result.to_url is None
        assert result.state_changed is None

    async def test_done_action_has_none_state_fields(self) -> None:
        page = _make_mock_page()
        executor = PlaywrightExecutor(page=page)
        action = AgentAction(type=ActionType.DONE, success=True)
        result = await executor.execute(action)
        assert result.state_changed is None

    async def test_exception_path_preserves_error_and_leaves_state_fields_safe(self) -> None:
        page = _make_mock_page()
        locator = MagicMock()
        locator.click = AsyncMock(side_effect=RuntimeError("selector not found"))
        page.locator = MagicMock(return_value=locator)
        executor = PlaywrightExecutor(page=page)
        action = AgentAction(type=ActionType.CLICK, target="button.missing")
        result = await executor.execute(action)
        assert result.error == "selector not found"
        assert result.state_changed is None  # undefined on error path

    async def test_console_errors_during_click_captured(self) -> None:
        """Errors emitted between the before-snapshot and after-snapshot are captured."""
        page = _make_mock_page()
        locator = MagicMock()

        async def _click(**kw) -> None:
            # Simulate a console error firing during the click
            handler = page._listeners["console"][0]
            handler(MagicMock(type="error", text="TypeError in handler"))

        locator.click = AsyncMock(side_effect=_click)
        page.locator = MagicMock(return_value=locator)
        executor = PlaywrightExecutor(page=page)

        # Add a pre-existing error that should NOT appear in the action's window
        preexisting_handler = page._listeners["console"][0]
        preexisting_handler(MagicMock(type="error", text="old error from page load"))

        action = AgentAction(type=ActionType.CLICK, target="button.x")
        result = await executor.execute(action)
        assert result.console_errors_during_action == ["TypeError in handler"]
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest tests/unit/test_playwright_executor_enrichment.py::TestStateCapture -v`

Expected: multiple FAIL with assertions about `result.from_url`, `result.state_changed`, etc. because `PlaywrightExecutor.execute` doesn't populate them yet.

- [ ] **Step 3: Add state capture to `execute`**

Edit `src/dazzle/agent/executor.py` — rewrite the `execute` method of `PlaywrightExecutor` as follows. Preserve the existing per-action dispatch (click, type, select, navigate, wait, assert, scroll, done, tool) but wrap it in state capture:

```python
import hashlib


def _dom_hash(html: str) -> str:
    """16-char SHA256 prefix of page content for cheap state-change detection."""
    return hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]


class PlaywrightExecutor:
    """Execute actions via Playwright page object."""

    def __init__(self, page: Any) -> None:
        self._page = page
        self._console_errors_buffer: list[str] = []
        page.on("console", self._on_console)

    def _on_console(self, msg: Any) -> None:
        try:
            if msg.type == "error":
                self._console_errors_buffer.append(msg.text)
        except Exception:
            pass

    async def execute(self, action: AgentAction) -> ActionResult:
        # Capture "before" state for actions that interact with the page.
        # TOOL / DONE bypass — they don't touch the page.
        capture_state = action.type not in (ActionType.TOOL, ActionType.DONE)
        from_url: str | None = None
        from_hash: str | None = None
        if capture_state:
            from_url = self._page.url
            from_hash = _dom_hash(await self._page.content())
        console_before = len(self._console_errors_buffer)

        try:
            if action.type == ActionType.CLICK:
                locator = self._resolve_locator(action.target or "")
                await locator.click(timeout=5000)
                try:
                    await self._page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass  # wait timeout is benign here
                base = ActionResult(message=f"Clicked {action.target}")

            elif action.type == ActionType.TYPE:
                locator = self._resolve_locator(action.target or "")
                await locator.fill(action.value or "", timeout=5000)
                base = ActionResult(
                    message=f"Typed '{action.value}' into {action.target}"
                )

            elif action.type == ActionType.SELECT:
                locator = self._resolve_locator(action.target or "")
                await locator.select_option(action.value, timeout=5000)
                base = ActionResult(
                    message=f"Selected '{action.value}' in {action.target}"
                )

            elif action.type == ActionType.NAVIGATE:
                target = action.target or "/"
                if not target.startswith("http"):
                    base_parts = self._page.url.split("/")[0:3]
                    target = "/".join(base_parts) + target
                await self._page.goto(target)
                try:
                    await self._page.wait_for_load_state("networkidle")
                except Exception:
                    pass
                base = ActionResult(message=f"Navigated to {target}")

            elif action.type == ActionType.WAIT:
                locator = self._resolve_locator(action.target or "")
                await locator.wait_for(timeout=10000)
                base = ActionResult(message=f"Found {action.target}")

            elif action.type == ActionType.ASSERT:
                try:
                    locator = self._resolve_locator(action.target or "")
                    await locator.wait_for(timeout=3000)
                    base = ActionResult(message=f"Assertion passed: {action.target} is visible")
                except Exception:
                    if await self._page.locator(f"text={action.target}").count() > 0:
                        base = ActionResult(message=f"Assertion passed: text '{action.target}' found")
                    else:
                        base = ActionResult(message="", error=f"Assertion failed: {action.target} not found")

            elif action.type == ActionType.SCROLL:
                await self._page.evaluate("window.scrollBy(0, 300)")
                base = ActionResult(message="Scrolled down")

            elif action.type == ActionType.DONE:
                base = ActionResult(message="Agent completed mission")

            elif action.type == ActionType.TOOL:
                base = ActionResult(message=f"Tool invocation: {action.target}")

            else:
                base = ActionResult(message="", error=f"Unknown action type: {action.type}")

        except Exception as e:
            # Error path: capture available state but leave state_changed=None
            return ActionResult(
                message="",
                error=str(e),
                from_url=from_url,
                to_url=self._page.url if capture_state else None,
                state_changed=None,
                console_errors_during_action=list(
                    self._console_errors_buffer[console_before:]
                ),
            )

        # Happy path: compute after state and populate the new fields
        if capture_state:
            to_url = self._page.url
            to_hash = _dom_hash(await self._page.content())
            base.from_url = from_url
            base.to_url = to_url
            if action.type == ActionType.SCROLL:
                base.state_changed = True  # optimistic
            elif action.type == ActionType.ASSERT:
                base.state_changed = False  # optimistic
            else:
                base.state_changed = (from_url != to_url) or (from_hash != to_hash)
        # else: TOOL / DONE leave state fields at None defaults

        base.console_errors_during_action = list(
            self._console_errors_buffer[console_before:]
        )
        return base
```

Note: `_resolve_locator` is an existing method — do not delete it. If your editor shows it was defined elsewhere in the class, leave that intact. The `import hashlib` goes at the top of the file alongside existing imports.

- [ ] **Step 4: Run all tests in the test file**

Run: `pytest tests/unit/test_playwright_executor_enrichment.py -v`

Expected: all TestConsoleListener (2) + TestStateCapture (8) = 10 passed.

- [ ] **Step 5: Regression check — fitness + agent tool-use**

Run: `pytest tests/unit/fitness/test_fitness_strategy_integration.py tests/unit/test_agent_tool_use.py tests/integration/test_agent_investigator_tool_use.py -q`

Expected: 48 passed. If a fitness test fails because `_resolve_locator` is now inside the `try:` block but previously wasn't, look at the exact failure and adjust (it shouldn't — the method is still called from the same per-action branches).

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/agent/executor.py tests/unit/test_playwright_executor_enrichment.py
git commit -m "feat(agent): capture action state + console errors in PlaywrightExecutor (cycle 197 task 3)

execute() wraps every action with before/after state capture:
- from_url, to_url from page.url
- state_changed via DOM hash comparison (optimistic for scroll/assert)
- console_errors_during_action via buffer diff-slice

TOOL and DONE bypass capture (don't touch the page). Error path
preserves new fields with state_changed=None. Existing fitness +
investigator tests unchanged."
```

---

## Task 4: `DazzleAgent._format_history_line` helper

**Files:**
- Modify: `src/dazzle/agent/core.py:771-812`
- Create: `tests/unit/test_agent_history_rendering.py`

**Goal:** Extract history-line formatting into a module-level helper that reads the new `ActionResult` fields, and unit-test each branch before wiring it into `_build_messages`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_agent_history_rendering.py`:

```python
"""Tests for DazzleAgent history rendering (cycle 197)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from dazzle.agent.core import _format_history_line, _is_stuck
from dazzle.agent.models import ActionResult, ActionType, AgentAction, PageState, Step


def _make_step(
    step_number: int,
    action_type: ActionType,
    target: str = "",
    result_kwargs: dict = None,
) -> Step:
    result_kwargs = result_kwargs or {}
    return Step(
        state=PageState(url="http://localhost/", title="t"),
        action=AgentAction(type=action_type, target=target),
        result=ActionResult(message="", **result_kwargs),
        step_number=step_number,
        duration_ms=10.0,
        prompt_text="",
        response_text="",
        tokens_used=0,
    )


class TestFormatHistoryLine:
    def test_no_state_change_is_explicit_and_loud(self) -> None:
        step = _make_step(
            3, ActionType.CLICK, target="a.stuck",
            result_kwargs={
                "from_url": "http://localhost/app",
                "to_url": "http://localhost/app",
                "state_changed": False,
            },
        )
        line = _format_history_line(step)
        assert "NO state change" in line
        assert "still at http://localhost/app" in line

    def test_url_transition_shown_on_navigate(self) -> None:
        step = _make_step(
            4, ActionType.CLICK, target="a.good",
            result_kwargs={
                "from_url": "http://localhost/app",
                "to_url": "http://localhost/app/contacts/1",
                "state_changed": True,
            },
        )
        line = _format_history_line(step)
        assert "http://localhost/app" in line
        assert "http://localhost/app/contacts/1" in line
        assert "→" in line or "->" in line  # arrow between urls

    def test_state_changed_same_url_shows_state_changed(self) -> None:
        """Type into a field doesn't change URL but changes DOM — generic signal."""
        step = _make_step(
            5, ActionType.TYPE, target="#field-email",
            result_kwargs={
                "from_url": "http://localhost/app/form",
                "to_url": "http://localhost/app/form",
                "state_changed": True,
            },
        )
        line = _format_history_line(step)
        assert "state changed" in line
        assert "NO state change" not in line

    def test_console_errors_appended(self) -> None:
        step = _make_step(
            6, ActionType.CLICK, target="button.broken",
            result_kwargs={
                "from_url": "/a", "to_url": "/b", "state_changed": True,
                "console_errors_during_action": [
                    "TypeError: undefined property at line 42",
                    "ReferenceError: foo is not defined",
                ],
            },
        )
        line = _format_history_line(step)
        assert "[+2 console errors:" in line
        assert "TypeError: undefined property" in line

    def test_single_console_error_singular(self) -> None:
        step = _make_step(
            7, ActionType.CLICK, target="button.x",
            result_kwargs={
                "from_url": "/a", "to_url": "/b", "state_changed": True,
                "console_errors_during_action": ["Uncaught Error"],
            },
        )
        line = _format_history_line(step)
        assert "[+1 console error:" in line
        assert "errors" not in line  # singular form

    def test_error_path_shows_error_not_state(self) -> None:
        step = _make_step(
            8, ActionType.CLICK, target="button.missing",
            result_kwargs={"error": "Selector not found", "state_changed": None},
        )
        line = _format_history_line(step)
        assert "ERROR" in line
        assert "Selector not found" in line

    def test_legacy_rendering_when_state_fields_none(self) -> None:
        """Tool invocations come through with state_changed=None + message set."""
        step = _make_step(
            9, ActionType.TOOL, target="propose_component",
            result_kwargs={"state_changed": None},
        )
        # Override the default empty message
        step.result.message = "Proposed: contact-card"
        line = _format_history_line(step)
        assert "Proposed: contact-card" in line
        assert "NO state change" not in line


class TestIsStuck:
    def test_empty_history_not_stuck(self) -> None:
        assert _is_stuck([], window=3) is False

    def test_fewer_than_window_not_stuck(self) -> None:
        steps = [
            _make_step(1, ActionType.CLICK, result_kwargs={"state_changed": False}),
            _make_step(2, ActionType.CLICK, result_kwargs={"state_changed": False}),
        ]
        assert _is_stuck(steps, window=3) is False

    def test_three_consecutive_no_ops_is_stuck(self) -> None:
        steps = [
            _make_step(i, ActionType.CLICK, result_kwargs={"state_changed": False})
            for i in (1, 2, 3)
        ]
        assert _is_stuck(steps, window=3) is True

    def test_mixed_history_not_stuck(self) -> None:
        steps = [
            _make_step(1, ActionType.CLICK, result_kwargs={"state_changed": False}),
            _make_step(2, ActionType.CLICK, result_kwargs={"state_changed": True}),
            _make_step(3, ActionType.CLICK, result_kwargs={"state_changed": False}),
        ]
        assert _is_stuck(steps, window=3) is False

    def test_state_changed_none_does_not_count_as_noop(self) -> None:
        """Tool actions have state_changed=None and should NOT trigger stuck."""
        steps = [
            _make_step(1, ActionType.CLICK, result_kwargs={"state_changed": False}),
            _make_step(2, ActionType.TOOL, result_kwargs={"state_changed": None}),
            _make_step(3, ActionType.CLICK, result_kwargs={"state_changed": False}),
        ]
        assert _is_stuck(steps, window=3) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_agent_history_rendering.py -v`

Expected: FAIL — `ImportError: cannot import name '_format_history_line' from 'dazzle.agent.core'`.

- [ ] **Step 3: Add the helpers to `dazzle.agent.core`**

Edit `src/dazzle/agent/core.py` — add these two module-level functions after the existing `_tool_use_to_action` function (around line 300; any location above the `DazzleAgent` class works):

```python
def _format_history_line(step: Step) -> str:
    """Render one history step for the LLM's compressed history (cycle 197).

    Reads the cycle-197 ActionResult fields (from_url, to_url,
    state_changed, console_errors_during_action) and renders a line
    that makes state-change status unmissable. Falls back to the legacy
    message format when state_changed is None (tool/HTTP/anonymous paths).
    """
    s = f"{step.step_number}. {step.action.type.value}"
    if step.action.target:
        s += f": {step.action.target[:40]}"
    r = step.result
    if r.error:
        s += f" (ERROR: {r.error[:60]})"
    elif r.state_changed is False:
        loc = f"still at {r.to_url}" if r.to_url else "no state change"
        s += f" -> NO state change ({loc})"
    elif r.state_changed is True and r.from_url and r.to_url and r.from_url != r.to_url:
        s += f" -> navigated {r.from_url} → {r.to_url}"
    elif r.state_changed is True:
        s += " -> state changed"
    elif r.message:
        s += f" -> {r.message[:60]}"
    if r.console_errors_during_action:
        n = len(r.console_errors_during_action)
        first = r.console_errors_during_action[0][:60]
        suffix = "s" if n > 1 else ""
        s += f" [+{n} console error{suffix}: {first}]"
    return s


def _is_stuck(history: list[Step], window: int = 3) -> bool:
    """True iff the last `window` steps all have state_changed=False.

    state_changed=None (tool actions, HTTP path) does NOT count as a
    no-op — tool invocations are legitimate progress even though they
    don't touch the page.
    """
    if len(history) < window:
        return False
    recent = history[-window:]
    return all(s.result.state_changed is False for s in recent)
```

Ensure `from dazzle.agent.models import ... Step ...` is in the imports at the top of the file (it should already be — `Step` is used elsewhere in core.py).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_agent_history_rendering.py -v`

Expected: 12 passed (7 format + 5 stuck).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/agent/core.py tests/unit/test_agent_history_rendering.py
git commit -m "feat(agent): extract _format_history_line + _is_stuck helpers (cycle 197 task 4)

Pure functions that will be wired into _build_messages in task 5.
_format_history_line reads the cycle-197 ActionResult fields and makes
no-state-change explicit. _is_stuck detects 3 consecutive no-op
actions (state_changed=False) for the bail-nudge trigger."
```

---

## Task 5: Wire `_format_history_line` + bail-nudge into `_build_messages`

**Files:**
- Modify: `src/dazzle/agent/core.py:771-812` (the `_build_messages` method)
- Modify: `tests/unit/test_agent_history_rendering.py` (add integration-ish tests)

**Goal:** Replace the inline history-line formatting in `_build_messages` with a call to `_format_history_line`, and conditionally append the bail-nudge block when `_is_stuck` returns True.

- [ ] **Step 1: Write the failing integration tests**

Append to `tests/unit/test_agent_history_rendering.py`:

```python
from dazzle.agent.core import DazzleAgent, Mission


def _make_agent() -> DazzleAgent:
    from unittest.mock import AsyncMock, MagicMock
    observer = AsyncMock()
    executor = AsyncMock()
    return DazzleAgent(observer=observer, executor=executor, api_key="test")


class TestBuildMessagesIntegration:
    def test_history_uses_new_format_line(self) -> None:
        """_build_messages renders each history step via _format_history_line."""
        agent = _make_agent()
        agent._history = [
            _make_step(
                1, ActionType.CLICK, target="a.x",
                result_kwargs={"from_url": "/a", "to_url": "/a", "state_changed": False},
            ),
        ]
        state = PageState(url="/a", title="t")
        messages = agent._build_messages(state)
        # The history text is the first user message
        history_text = messages[0]["content"]
        assert "NO state change" in history_text

    def test_bail_nudge_fires_at_three_consecutive_no_ops(self) -> None:
        agent = _make_agent()
        agent._history = [
            _make_step(
                i, ActionType.CLICK, target="a.stuck",
                result_kwargs={
                    "from_url": "/app", "to_url": "/app", "state_changed": False,
                },
            )
            for i in (1, 2, 3)
        ]
        state = PageState(url="/app", title="t")
        messages = agent._build_messages(state)
        history_text = messages[0]["content"]
        assert "You appear to be stuck" in history_text
        assert "done" in history_text  # escape hatch mentioned

    def test_bail_nudge_does_not_fire_below_threshold(self) -> None:
        agent = _make_agent()
        agent._history = [
            _make_step(
                i, ActionType.CLICK,
                result_kwargs={"state_changed": False},
            )
            for i in (1, 2)  # only 2 no-ops
        ]
        state = PageState(url="/", title="t")
        messages = agent._build_messages(state)
        assert "You appear to be stuck" not in messages[0]["content"]

    def test_bail_nudge_continues_firing_past_three(self) -> None:
        """Every step after the 3rd still sees the nudge."""
        agent = _make_agent()
        agent._history = [
            _make_step(
                i, ActionType.CLICK,
                result_kwargs={"state_changed": False},
            )
            for i in range(1, 6)  # 5 no-ops
        ]
        state = PageState(url="/", title="t")
        messages = agent._build_messages(state)
        assert "You appear to be stuck" in messages[0]["content"]

    def test_empty_history_no_nudge_no_crash(self) -> None:
        agent = _make_agent()
        agent._history = []
        state = PageState(url="/", title="t")
        messages = agent._build_messages(state)
        # Empty history means messages[0] is the current state, not a history block
        # Just assert we don't crash and the nudge text isn't present
        for m in messages:
            content = m["content"]
            if isinstance(content, str):
                assert "You appear to be stuck" not in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_agent_history_rendering.py::TestBuildMessagesIntegration -v`

Expected: FAIL — `_build_messages` still uses the inline format, so the history text won't contain "NO state change" or "You appear to be stuck".

- [ ] **Step 3: Rewrite `_build_messages` to use the helpers**

Edit `src/dazzle/agent/core.py` — replace the `_build_messages` method (around line 771) with:

```python
def _build_messages(self, state: PageState) -> list[dict[str, Any]]:
    """Build conversation messages from history + current state."""
    messages: list[dict[str, Any]] = []

    # Add compressed history
    if self._history:
        history_text = "## Previous Actions\n"
        # Show last 5 steps
        for step in self._history[-5:]:
            history_text += _format_history_line(step) + "\n"

        # Cycle 197 — bail-nudge: if the last 3 steps all produced no state
        # change, tell the LLM explicitly and give it an escape to `done`.
        if _is_stuck(self._history, window=3):
            history_text += (
                "\n## ⚠️ You appear to be stuck\n"
                "Your last 3 actions produced NO state change. The page "
                "hasn't moved and the selectors aren't firing anything "
                "useful. STOP repeating the same action. Try one of:\n"
                "- navigate to a different URL\n"
                "- click a different kind of element (button, link in a "
                "different section)\n"
                "- if you cannot find any new way to make progress, call "
                "the `done` tool so we can stop wasting steps\n"
            )

        messages.append({"role": "user", "content": history_text})
        messages.append(
            {"role": "assistant", "content": "I understand. What's the current state?"}
        )

    # Add current state
    content: list[dict[str, Any]] = []

    if state.screenshot_b64:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": state.screenshot_b64,
                },
            }
        )

    content.append({"type": "text", "text": state.to_prompt()})
    messages.append({"role": "user", "content": content})

    return messages
```

- [ ] **Step 4: Run all history tests**

Run: `pytest tests/unit/test_agent_history_rendering.py -v`

Expected: 17 passed (7 format + 5 stuck + 5 integration).

- [ ] **Step 5: Regression check — all agent tests**

Run: `pytest tests/unit/test_agent_tool_use.py tests/integration/test_agent_investigator_tool_use.py -q`

Expected: 25 passed (23 + 2).

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/agent/core.py tests/unit/test_agent_history_rendering.py
git commit -m "feat(agent): wire _format_history_line + bail-nudge into _build_messages (cycle 197 task 5)

_build_messages now renders each history step via _format_history_line
and conditionally appends a bail-nudge block when _is_stuck fires
(3 consecutive state_changed=False steps). The bail-nudge tells the
LLM explicitly to try something different or call done.

Experimental: verification run checks the nudge fires AND produces a
subsequent state-changing action. Tunable from that data in cycle 198."
```

---

## Task 6: `pick_explore_personas` helper

**Files:**
- Modify: `src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py`
- Modify: `tests/unit/test_explore_strategy.py`

**Goal:** Add a pure helper function that filters framework-scoped personas out of an `AppSpec` and returns the sorted list of business personas. Also supports an explicit override list.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_explore_strategy.py` (below the existing tests):

```python
from dazzle.core.ir.personas import PersonaSpec


def _make_app_spec_with_personas(personas_list: list[PersonaSpec]) -> MagicMock:
    spec = MagicMock()
    spec.personas = personas_list
    return spec


class TestPickExplorePersonas:
    def test_filters_platform_personas_out(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            pick_explore_personas,
        )
        spec = _make_app_spec_with_personas(
            [
                PersonaSpec(id="admin", label="Admin", default_workspace="_platform_admin"),
                PersonaSpec(id="user", label="User", default_workspace="contacts"),
            ]
        )
        result = pick_explore_personas(spec)
        assert len(result) == 1
        assert result[0].id == "user"

    def test_sorts_business_personas_alphabetically(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            pick_explore_personas,
        )
        spec = _make_app_spec_with_personas(
            [
                PersonaSpec(id="manager", label="M", default_workspace="my_work"),
                PersonaSpec(id="admin", label="A", default_workspace="admin_dashboard"),
                PersonaSpec(id="user", label="U", default_workspace="my_work"),
            ]
        )
        result = pick_explore_personas(spec)
        assert [p.id for p in result] == ["admin", "manager", "user"]

    def test_override_returns_in_caller_order(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            pick_explore_personas,
        )
        spec = _make_app_spec_with_personas(
            [
                PersonaSpec(id="admin", label="A", default_workspace="_platform_admin"),
                PersonaSpec(id="customer", label="C", default_workspace="store"),
                PersonaSpec(id="agent", label="Ag", default_workspace="support"),
            ]
        )
        result = pick_explore_personas(spec, override=["customer", "admin"])
        assert [p.id for p in result] == ["customer", "admin"]

    def test_override_unknown_id_raises_value_error(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            pick_explore_personas,
        )
        spec = _make_app_spec_with_personas(
            [PersonaSpec(id="user", label="U", default_workspace="x")]
        )
        with pytest.raises(ValueError, match="persona 'nobody' not found"):
            pick_explore_personas(spec, override=["nobody"])

    def test_all_platform_personas_returns_empty_list(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            pick_explore_personas,
        )
        spec = _make_app_spec_with_personas(
            [
                PersonaSpec(id="admin", label="A", default_workspace="_platform_admin"),
                PersonaSpec(id="sys", label="S", default_workspace="_system"),
            ]
        )
        result = pick_explore_personas(spec)
        assert result == []

    def test_persona_with_no_default_workspace_is_kept(self) -> None:
        """Personas without default_workspace are not framework-scoped."""
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            pick_explore_personas,
        )
        spec = _make_app_spec_with_personas(
            [PersonaSpec(id="visitor", label="V", default_workspace=None)]
        )
        result = pick_explore_personas(spec)
        assert len(result) == 1
        assert result[0].id == "visitor"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_explore_strategy.py::TestPickExplorePersonas -v`

Expected: FAIL with `ImportError: cannot import name 'pick_explore_personas'`.

- [ ] **Step 3: Add the helper to `explore_strategy.py`**

Edit `src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py` — add this function near the other pure helpers (above `run_explore_strategy`):

```python
def pick_explore_personas(
    app_spec: Any,
    override: list[str] | None = None,
) -> list[PersonaSpec]:
    """Pick persona(s) for an explore run.

    Auto-pick (override is None): return ALL personas whose
    default_workspace is not framework-scoped (i.e. doesn't start with
    an underscore), sorted alphabetically by id for determinism.
    Returns [] if no business personas exist.

    Override (list of ids): return those personas in caller order,
    looked up from app_spec.personas. Raises ValueError if any id is
    unknown — noisy failure is better than silently dropping a persona
    the caller explicitly requested.
    """
    by_id: dict[str, PersonaSpec] = {p.id: p for p in app_spec.personas}

    if override is not None:
        missing = [pid for pid in override if pid not in by_id]
        if missing:
            raise ValueError(
                f"persona '{missing[0]}' not found in app_spec.personas "
                f"(available: {sorted(by_id.keys())})"
            )
        return [by_id[pid] for pid in override]

    # Auto-pick: filter out framework-scoped personas
    business = [
        p for p in app_spec.personas
        if p.default_workspace is None or not p.default_workspace.startswith("_")
    ]
    business.sort(key=lambda p: p.id)
    return business
```

Ensure `from dazzle.core.ir.personas import PersonaSpec` is imported at the top of the file (it already is — the file uses `PersonaSpec` in `_run_one_persona`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_explore_strategy.py::TestPickExplorePersonas -v`

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py tests/unit/test_explore_strategy.py
git commit -m "feat(explore): pick_explore_personas auto-picks business personas (cycle 197 task 6)

New pure helper that filters out framework-scoped personas (those with
default_workspace starting with underscore) and returns the remaining
sorted alphabetically. Supports an explicit override list for
adversarial / multi-persona runs.

Verified filter mapping across 5 examples/:
  simple_task: admin, manager, user
  contact_manager: user (admin excluded)
  support_tickets: agent, customer, manager (admin excluded)
  ops_dashboard: ops_engineer (admin excluded)
  fieldtest_hub: engineer, manager, tester (admin excluded)"
```

---

## Task 7: `pick_start_path` helper

**Files:**
- Modify: `src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py`
- Modify: `tests/unit/test_explore_strategy.py`

**Goal:** Add a thin wrapper around `compute_persona_default_routes` that returns one start URL path for a given persona, falling back to `/app`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_explore_strategy.py`:

```python
class TestPickStartPath:
    def test_uses_explicit_default_route(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            pick_start_path,
        )
        persona = PersonaSpec(
            id="user", label="U",
            default_workspace="contacts",
            default_route="/app/workspaces/contacts",
        )
        spec = MagicMock()
        spec.workspaces = []

        with patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.compute_persona_default_routes",
            return_value={"user": "/app/workspaces/contacts"},
        ):
            result = pick_start_path(persona, spec)
        assert result == "/app/workspaces/contacts"

    def test_falls_back_to_app_when_no_route(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            pick_start_path,
        )
        persona = PersonaSpec(id="nobody", label="N")
        spec = MagicMock()
        spec.workspaces = []

        with patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.compute_persona_default_routes",
            return_value={},  # helper found nothing
        ):
            result = pick_start_path(persona, spec)
        assert result == "/app"

    def test_delegates_to_compute_persona_default_routes(self) -> None:
        """Verify we call into the shared helper with the right shape."""
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            pick_start_path,
        )
        persona = PersonaSpec(id="user", label="U", default_workspace="contacts")
        spec = MagicMock()
        spec.workspaces = ["ws-sentinel"]

        with patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.compute_persona_default_routes",
            return_value={"user": "/app/contacts"},
        ) as mock_compute:
            result = pick_start_path(persona, spec)

        mock_compute.assert_called_once_with(personas=[persona], workspaces=["ws-sentinel"])
        assert result == "/app/contacts"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_explore_strategy.py::TestPickStartPath -v`

Expected: FAIL with `ImportError: cannot import name 'pick_start_path'`.

- [ ] **Step 3: Add the helper**

Edit `src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py` — add the import near the top (alongside existing imports):

```python
from dazzle_ui.converters.workspace_converter import compute_persona_default_routes
```

And add the function below `pick_explore_personas`:

```python
def pick_start_path(persona_spec: PersonaSpec, app_spec: Any) -> str:
    """Compute the start URL path for exploring as persona_spec.

    Delegates to compute_persona_default_routes for the full 5-step
    resolution chain (default_route → default_workspace → persona-access
    workspace → AUTHENTICATED workspace → first workspace). Falls back
    to '/app' if the helper returns no route (pathological DSL with no
    workspaces).
    """
    routes = compute_persona_default_routes(
        personas=[persona_spec],
        workspaces=app_spec.workspaces,
    )
    return routes.get(persona_spec.id) or "/app"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_explore_strategy.py::TestPickStartPath -v`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py tests/unit/test_explore_strategy.py
git commit -m "feat(explore): pick_start_path delegates to compute_persona_default_routes (cycle 197 task 7)

Thin wrapper so explore uses the same route resolution logic as the
FastAPI login flow and the persona switcher. Falls back to '/app' if
the shared helper returns nothing."
```

---

## Task 8: `ExploreOutcome` shape + proposal dedup

**Files:**
- Modify: `src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py` — `ExploreOutcome` dataclass + aggregation
- Modify: `tests/unit/test_explore_strategy.py`

**Goal:** Add `raw_proposals_by_persona` field to `ExploreOutcome`, and implement dedup logic that merges proposals with the same `(example_app, component_name.lower())` into one entry with `contributing_personas` list.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_explore_strategy.py`:

```python
class TestProposalDedup:
    def test_same_component_across_personas_merges(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            _dedup_proposals,
        )
        raw = [
            {
                "component_name": "contact-card",
                "description": "A card showing a contact.",
                "example_app": "contact_manager",
                "persona_id": "user",
            },
            {
                "component_name": "contact-card",
                "description": "A different description.",
                "example_app": "contact_manager",
                "persona_id": "manager",
            },
        ]
        deduped = _dedup_proposals(raw)
        assert len(deduped) == 1
        assert deduped[0]["component_name"] == "contact-card"
        # First description wins
        assert deduped[0]["description"] == "A card showing a contact."
        assert deduped[0]["contributing_personas"] == ["user", "manager"]

    def test_dedup_is_case_insensitive(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            _dedup_proposals,
        )
        raw = [
            {"component_name": "Contact-Card", "description": "x", "example_app": "a", "persona_id": "u1"},
            {"component_name": "contact-card", "description": "y", "example_app": "a", "persona_id": "u2"},
        ]
        deduped = _dedup_proposals(raw)
        assert len(deduped) == 1
        assert deduped[0]["contributing_personas"] == ["u1", "u2"]

    def test_different_apps_do_not_dedup(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            _dedup_proposals,
        )
        raw = [
            {"component_name": "card", "description": "x", "example_app": "a", "persona_id": "u1"},
            {"component_name": "card", "description": "y", "example_app": "b", "persona_id": "u2"},
        ]
        deduped = _dedup_proposals(raw)
        assert len(deduped) == 2

    def test_single_persona_contributing_list(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            _dedup_proposals,
        )
        raw = [
            {"component_name": "card", "description": "x", "example_app": "a", "persona_id": "u1"},
        ]
        deduped = _dedup_proposals(raw)
        assert deduped[0]["contributing_personas"] == ["u1"]


class TestExploreOutcomeShape:
    def test_has_raw_proposals_by_persona_field(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            ExploreOutcome,
        )
        outcome = ExploreOutcome(
            strategy="EXPLORE/missing_contracts",
            summary="test",
            degraded=False,
        )
        assert outcome.raw_proposals_by_persona == {}

    def test_raw_proposals_by_persona_populated(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            ExploreOutcome,
        )
        outcome = ExploreOutcome(
            strategy="EXPLORE/missing_contracts",
            summary="test",
            degraded=False,
            raw_proposals_by_persona={"user": 3, "manager": 2},
        )
        assert outcome.raw_proposals_by_persona == {"user": 3, "manager": 2}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_explore_strategy.py::TestProposalDedup tests/unit/test_explore_strategy.py::TestExploreOutcomeShape -v`

Expected: FAIL with `ImportError: cannot import name '_dedup_proposals'` and `TypeError: __init__() got unexpected keyword 'raw_proposals_by_persona'`.

- [ ] **Step 3: Add `_dedup_proposals` helper and extend `ExploreOutcome`**

Edit `src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py` — update the `ExploreOutcome` dataclass:

```python
@dataclass
class ExploreOutcome:
    """Aggregated outcome from one /ux-cycle EXPLORE run."""

    strategy: str
    summary: str
    degraded: bool
    proposals: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    blocked_personas: list[tuple[str | None, str]] = field(default_factory=list)
    steps_run: int = 0
    tokens_used: int = 0
    # Cycle 197 — pre-dedup counts per persona, for logging and cross-persona analysis
    raw_proposals_by_persona: dict[str, int] = field(default_factory=dict)
```

And add the dedup helper near the other pure helpers:

```python
def _dedup_proposals(raw_proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge proposals with the same (example_app, component_name) key.

    First-seen ordering is preserved. Each merged entry gains a
    'contributing_personas' field listing every persona_id that proposed
    the same component. Comparison on component_name is case-insensitive
    to catch trivial casing variation from LLM output.
    """
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []

    for p in raw_proposals:
        key = (p.get("example_app", ""), p.get("component_name", "").lower())
        persona_id = p.get("persona_id")
        if key not in merged:
            entry = dict(p)  # shallow copy
            entry["contributing_personas"] = [persona_id] if persona_id else []
            merged[key] = entry
            order.append(key)
        else:
            if persona_id and persona_id not in merged[key]["contributing_personas"]:
                merged[key]["contributing_personas"].append(persona_id)

    return [merged[k] for k in order]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_explore_strategy.py::TestProposalDedup tests/unit/test_explore_strategy.py::TestExploreOutcomeShape -v`

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py tests/unit/test_explore_strategy.py
git commit -m "feat(explore): _dedup_proposals + ExploreOutcome.raw_proposals_by_persona (cycle 197 task 8)

Merges proposals with the same (example_app, component_name) key into
one entry with a contributing_personas list. ExploreOutcome gains a
raw_proposals_by_persona field for pre-dedup stats.

Dedup is case-insensitive on component_name to catch trivial LLM
casing variation."
```

---

## Task 9: `run_explore_strategy` signature change + fan-out integration

**Files:**
- Modify: `src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py` — `run_explore_strategy`
- Modify: `tests/unit/test_explore_strategy.py`

**Goal:** Change `run_explore_strategy` so `personas=None` triggers auto-pick (instead of anonymous), route all proposals through `_dedup_proposals`, and populate `raw_proposals_by_persona`. Preserve `personas=[]` as the anonymous escape hatch.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_explore_strategy.py`:

```python
class TestRunExploreStrategyFanOut:
    @pytest.mark.asyncio
    async def test_personas_none_triggers_auto_pick(self, tmp_path: Path) -> None:
        """personas=None runs once per auto-picked business persona."""
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            run_explore_strategy,
        )
        from dazzle.agent.missions.ux_explore import Strategy

        bundle, connection = _fake_bundle_and_connection()
        # AppSpec with 2 business personas + 1 platform persona
        fake_spec = MagicMock()
        fake_spec.personas = [
            PersonaSpec(id="admin", label="A", default_workspace="_platform_admin"),
            PersonaSpec(id="manager", label="M", default_workspace="my_work"),
            PersonaSpec(id="user", label="U", default_workspace="my_work"),
        ]
        fake_spec.workspaces = []

        with (
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.setup_playwright",
                new=AsyncMock(return_value=bundle),
            ),
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.load_project_appspec",
                return_value=fake_spec,
            ),
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.login_as_persona",
                new=AsyncMock(),
            ) as mock_login,
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.compute_persona_default_routes",
                return_value={"manager": "/app/m", "user": "/app/u"},
            ),
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.DazzleAgent",
                new=_FakeAgent,
            ),
        ):
            outcome = await run_explore_strategy(
                connection,
                example_root=tmp_path / "example",
                strategy=Strategy.MISSING_CONTRACTS,
                personas=None,  # auto-pick
            )

        # Should have run once per business persona (2 total)
        assert mock_login.await_count == 2
        assert len(_FakeAgent.instances) == 2

    @pytest.mark.asyncio
    async def test_personas_empty_list_runs_anonymously(self, tmp_path: Path) -> None:
        """personas=[] still means anonymous (backwards compat escape hatch)."""
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            run_explore_strategy,
        )
        from dazzle.agent.missions.ux_explore import Strategy

        bundle, connection = _fake_bundle_and_connection()
        fake_spec = MagicMock()
        fake_spec.personas = [
            PersonaSpec(id="user", label="U", default_workspace="my_work"),
        ]
        fake_spec.workspaces = []

        with (
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.setup_playwright",
                new=AsyncMock(return_value=bundle),
            ),
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.load_project_appspec",
                return_value=fake_spec,
            ),
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.login_as_persona",
                new=AsyncMock(),
            ) as mock_login,
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.DazzleAgent",
                new=_FakeAgent,
            ),
        ):
            outcome = await run_explore_strategy(
                connection,
                example_root=tmp_path / "example",
                strategy=Strategy.MISSING_CONTRACTS,
                personas=[],  # explicit empty = anonymous
            )

        # No login call — anonymous path
        assert mock_login.await_count == 0
        assert len(_FakeAgent.instances) == 1  # one anonymous run

    @pytest.mark.asyncio
    async def test_fan_out_dedups_proposals_across_personas(self, tmp_path: Path) -> None:
        """Same proposal from multiple personas merges into one contributing_personas entry."""
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            run_explore_strategy,
        )
        from dazzle.agent.missions.ux_explore import Strategy

        bundle, connection = _fake_bundle_and_connection()
        fake_spec = MagicMock()
        fake_spec.personas = [
            PersonaSpec(id="manager", label="M", default_workspace="my_work"),
            PersonaSpec(id="user", label="U", default_workspace="my_work"),
        ]
        fake_spec.workspaces = []

        with (
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.setup_playwright",
                new=AsyncMock(return_value=bundle),
            ),
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.load_project_appspec",
                return_value=fake_spec,
            ),
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.login_as_persona",
                new=AsyncMock(),
            ),
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.compute_persona_default_routes",
                return_value={"manager": "/app", "user": "/app"},
            ),
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.DazzleAgent",
                new=_FakeAgent,
            ),
        ):
            outcome = await run_explore_strategy(
                connection,
                example_root=tmp_path / "example",
                strategy=Strategy.MISSING_CONTRACTS,
                personas=None,
            )

        # _FakeAgent produces one proposal per persona with component_name=f"proposed-{persona_id}"
        # With our two personas the deduped list still has 2 entries (different names)
        assert len(outcome.proposals) == 2
        # But raw_proposals_by_persona tracks the pre-dedup counts
        assert outcome.raw_proposals_by_persona == {"manager": 1, "user": 1}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_explore_strategy.py::TestRunExploreStrategyFanOut -v`

Expected: FAIL — `run_explore_strategy` still treats `personas=None` as anonymous, and/or `raw_proposals_by_persona` is not populated.

- [ ] **Step 3: Rewrite `run_explore_strategy`**

Edit `src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py` — replace `run_explore_strategy` with:

```python
async def run_explore_strategy(
    connection: AppConnection,
    *,
    example_root: Path,
    strategy: Strategy,
    personas: list[str] | None = None,
    start_path: str | None = None,
) -> ExploreOutcome:
    """Run one EXPLORE cycle per persona and return the aggregated outcome.

    ``personas`` semantics (cycle 197 change):
        None       → auto-pick business personas from the DSL
        []         → anonymous (no login, single run)
        ["admin"]  → explicit override, single persona
        ["a","b"]  → explicit multi-persona fan-out

    ``start_path`` overrides the per-persona computed start path for
    all runs. Defaults to None (each persona uses its DSL default).
    """
    app_spec = load_project_appspec(example_root)

    # Persona resolution
    if personas is None:
        # Auto-pick business personas
        persona_specs = pick_explore_personas(app_spec)
        personas_to_run: list[str | None] = [p.id for p in persona_specs] if persona_specs else [None]
        if not persona_specs:
            logger.warning(
                "explore: no business personas found in %s; running anonymously",
                example_root.name,
            )
    elif personas == []:
        # Anonymous escape hatch
        persona_specs = []
        personas_to_run = [None]
    else:
        # Explicit override — resolve and validate
        persona_specs = pick_explore_personas(app_spec, override=personas)
        personas_to_run = [p.id for p in persona_specs]

    persona_lookup: dict[str, PersonaSpec] = {p.id: p for p in app_spec.personas}

    # Resolve start paths per persona if the caller didn't override
    persona_start_paths: dict[str | None, str] = {}
    for pid in personas_to_run:
        if start_path is not None:
            persona_start_paths[pid] = start_path
        elif pid is None:
            persona_start_paths[pid] = "/app"
        else:
            ps = persona_lookup.get(pid)
            persona_start_paths[pid] = (
                pick_start_path(ps, app_spec) if ps is not None else "/app"
            )

    logger.info(
        "[explore] %s: running %d persona(s): %s",
        example_root.name,
        len(personas_to_run),
        [p or "anonymous" for p in personas_to_run],
    )

    bundle: PlaywrightBundle | None = None
    results: list[_PersonaRunResult] = []
    raw_by_persona: dict[str, int] = {}

    try:
        bundle = await setup_playwright(base_url=connection.site_url)

        for persona_id in personas_to_run:
            persona_context: Any = None
            try:
                if persona_id is None:
                    persona_page = bundle.page
                    persona_label = "anonymous"
                else:
                    persona_context = await bundle.browser.new_context(base_url=connection.site_url)
                    persona_page = await persona_context.new_page()
                    await login_as_persona(
                        page=persona_page,
                        persona_id=persona_id,
                        api_url=connection.api_url,
                    )
                    ps = persona_lookup.get(persona_id)
                    persona_label = ps.label if ps is not None else persona_id

                start = persona_start_paths[persona_id]
                result = await _run_one_persona(
                    strategy=strategy,
                    persona_id=persona_id,
                    persona_label=persona_label,
                    page=persona_page,
                    base_url=connection.site_url,
                    start_path=start,
                    example_app=example_root.name,
                    persona_lookup=persona_lookup,
                )
                results.append(result)
                if persona_id is not None:
                    raw_by_persona[persona_id] = len(result.proposals)

            except Exception as e:  # noqa: BLE001
                results.append(
                    _PersonaRunResult(
                        persona_id=persona_id,
                        proposals=[],
                        findings=[],
                        outcome="blocked",
                        steps=0,
                        tokens=0,
                        error=str(e),
                    )
                )
            finally:
                if persona_context is not None:
                    await persona_context.close()

    finally:
        if bundle is not None:
            await bundle.close()

    if not results or all(r.outcome == "blocked" for r in results):
        blocked_summary = "; ".join(
            f"{r.persona_id or 'anon'}: {r.error}" for r in results if r.error
        )
        raise RuntimeError(
            f"explore strategy: all personas blocked ({blocked_summary or 'no results'})"
        )

    outcome = _aggregate(strategy=strategy, results=results)
    # Cycle 197 — dedup proposals across fan-out, attach raw counts
    outcome.proposals = _dedup_proposals(outcome.proposals)
    outcome.raw_proposals_by_persona = raw_by_persona
    return outcome
```

- [ ] **Step 4: Run the new tests**

Run: `pytest tests/unit/test_explore_strategy.py::TestRunExploreStrategyFanOut -v`

Expected: 3 passed.

- [ ] **Step 5: Run ALL existing explore_strategy tests**

Run: `pytest tests/unit/test_explore_strategy.py -q`

Expected: all tests pass — existing 6 + task-6 (6) + task-7 (3) + task-8 (6) + task-9 (3) = **24 passed**.

Existing tests rely on `personas=None` behaviour — some may fail because they now get auto-pick instead of anonymous. Inspect any failures:
- If a test passes `personas=None` and expects anonymous behaviour, **update it to pass `personas=[]`** to preserve intent.
- If a test mocks `pick_explore_personas` or `compute_persona_default_routes`, it should already be future-proof.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py tests/unit/test_explore_strategy.py
git commit -m "feat(explore): run_explore_strategy auto-picks personas and fans out (cycle 197 task 9)

Signature change: personas=None now means 'auto-pick business personas
from the DSL' (was: anonymous). personas=[] is the new explicit
anonymous escape hatch. personas=[...] is unchanged.

Outcome integration: proposals are deduped across fan-out via
_dedup_proposals with (example_app, component_name) key.
raw_proposals_by_persona is populated from per-persona pre-dedup counts."
```

---

## Task 10: E2E verification test file

**Files:**
- Create: `tests/e2e/test_explore_strategy_e2e.py`
- Modify: `pyproject.toml` or `pytest.ini` (if needed to register `e2e` marker — check first)

**Goal:** Add a parametrised e2e test that runs `run_explore_strategy` against all 5 `examples/` apps and asserts D2's acceptance conditions. Marked `@pytest.mark.e2e` so it's excluded from default pytest runs and only runs locally.

- [ ] **Step 1: Check if `e2e` marker is already registered**

Run: `grep -n "e2e" pyproject.toml 2>/dev/null || grep -n "e2e" pytest.ini 2>/dev/null`

If the marker is already registered (you'll see `markers = [...]` or similar with `e2e` in the list), skip to Step 2. If not, add it.

**If needed** — edit `pyproject.toml` to add the marker under `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
markers = [
    "e2e: end-to-end tests requiring real Postgres + Redis + API key (manual local run only)",
]
```

- [ ] **Step 2: Write the test file**

Create `tests/e2e/test_explore_strategy_e2e.py`:

```python
"""E2E verification for cycle 197 Layer 4 work.

Runs run_explore_strategy against each of the 5 examples/ apps with
auto-picked business personas and asserts D2's acceptance bar.

Marked @pytest.mark.e2e — excluded from default pytest runs. Invoke
manually:

    pytest tests/e2e/test_explore_strategy_e2e.py -m e2e -v

Environment requirements (all must be present):
- DATABASE_URL and REDIS_URL reachable per-example .env files
- ANTHROPIC_API_KEY in the current shell
- Postgres running locally (pg_isready must succeed)
- Redis running locally (redis-cli ping must return PONG)

Cost: ~$0.50 per full sweep at sonnet-4-6 rates.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest


EXAMPLES = [
    "simple_task",
    "contact_manager",
    "support_tickets",
    "ops_dashboard",
    "fieldtest_hub",
]

DAZZLE_ROOT = Path(__file__).resolve().parents[2]
ARTEFACTS_DIR = DAZZLE_ROOT / "dev_docs" / "cycle_197_verification"


def _load_example_env(example_root: Path) -> None:
    """Load DATABASE_URL and REDIS_URL from the example's .env file into os.environ."""
    env_path = example_root / ".env"
    if not env_path.exists():
        pytest.skip(f"{env_path} not found — example not configured for e2e")
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition("=")
        os.environ[k] = v  # overwrite — each example has its own DB


@pytest.fixture(scope="module")
def artefacts_dir() -> Path:
    ARTEFACTS_DIR.mkdir(parents=True, exist_ok=True)
    return ARTEFACTS_DIR


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.parametrize("example_name", EXAMPLES)
async def test_explore_strategy_against_example(
    example_name: str, artefacts_dir: Path
) -> None:
    """run_explore_strategy produces non-degraded outcome against each example."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    example_root = DAZZLE_ROOT / "examples" / example_name
    _load_example_env(example_root)

    from dazzle.agent.missions.ux_explore import Strategy
    from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
        run_explore_strategy,
    )
    from dazzle.e2e.modes import get_mode
    from dazzle.e2e.runner import ModeRunner

    async with ModeRunner(
        mode_spec=get_mode("a"),
        project_root=example_root,
        personas=None,  # ModeRunner doesn't need explicit list; strategy picks
        db_policy="preserve",
    ) as conn:
        outcome = await run_explore_strategy(
            conn,
            example_root=example_root,
            strategy=Strategy.MISSING_CONTRACTS,
            personas=None,  # auto-pick business personas
        )

    # Record the outcome as an artefact for debugging / cross-cycle comparison
    artefact = artefacts_dir / f"{example_name}.json"
    artefact.write_text(
        json.dumps(
            {
                "strategy": outcome.strategy,
                "summary": outcome.summary,
                "degraded": outcome.degraded,
                "proposals": outcome.proposals,
                "findings": outcome.findings,
                "blocked_personas": [
                    {"persona_id": pid, "reason": r}
                    for (pid, r) in outcome.blocked_personas
                ],
                "steps_run": outcome.steps_run,
                "tokens_used": outcome.tokens_used,
                "raw_proposals_by_persona": outcome.raw_proposals_by_persona,
            },
            indent=2,
        )
    )

    # Primary assertion: the strategy ran cleanly
    assert outcome.degraded is False, (
        f"{example_name}: degraded=True indicates a per-persona failure "
        f"or infrastructure problem (see {artefact})"
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_sweep_has_three_apps_with_proposals(artefacts_dir: Path) -> None:
    """After running all 5 apps, at least 3 must have ≥1 proposal each.

    This test MUST run AFTER the parametrised test above — it reads the
    artefacts that test wrote. pytest orders tests lexically within a
    file, so this test's name ('test_sweep_has_...') comes after the
    parametrised ones alphabetically. If you reorder, check the ordering.
    """
    apps_with_proposals = 0
    missing: list[str] = []
    for example in EXAMPLES:
        artefact = artefacts_dir / f"{example}.json"
        if not artefact.exists():
            missing.append(example)
            continue
        data = json.loads(artefact.read_text())
        if len(data.get("proposals", [])) >= 1:
            apps_with_proposals += 1

    if missing:
        pytest.skip(
            f"sweep check requires parametrised test to run first; missing: {missing}"
        )

    assert apps_with_proposals >= 3, (
        f"D2 acceptance bar: ≥3 of 5 apps should have ≥1 proposal, "
        f"got {apps_with_proposals}. See artefacts in {artefacts_dir}"
    )


@pytest.mark.e2e
def test_bail_nudge_demonstrably_fires(artefacts_dir: Path) -> None:
    """At least one persona-cycle across the sweep shows the bail-nudge text.

    Since the current spec doesn't plumb transcript text into the outcome
    artefact, this test is currently a SKIP until we add transcript
    capture. Tracked as a cycle-198 item. For now, verify manually that
    some persona-run's transcript log contains 'You appear to be stuck'.
    """
    pytest.skip(
        "bail-nudge introspection needs transcript capture in outcome artefact "
        "(cycle 198 follow-up)"
    )
```

- [ ] **Step 3: Verify the test is collected but not run by default**

Run: `pytest tests/e2e/test_explore_strategy_e2e.py --collect-only -q 2>&1 | tail -10`

Expected: 7 tests collected (5 parametrised + 1 sweep + 1 bail-nudge skip).

Run: `pytest tests/e2e/test_explore_strategy_e2e.py -q`

Expected: all 7 either SKIPPED (no `-m e2e`) or deselected. NOT executed against live infra.

Run: `pytest tests/unit/ -q 2>&1 | tail -5`

Expected: unit tests still run cleanly. The e2e file doesn't interfere.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_explore_strategy_e2e.py pyproject.toml
git commit -m "test(e2e): Layer 4 verification sweep across 5 examples (cycle 197 task 10)

Parametrised e2e test that runs run_explore_strategy against each
example with auto-picked personas. Asserts D2's acceptance bar:
- degraded=False for every example
- at least 3 of 5 apps produce ≥1 proposal

Marked @pytest.mark.e2e, excluded from default pytest runs. Invoke
with: pytest tests/e2e/test_explore_strategy_e2e.py -m e2e -v

Bail-nudge introspection deferred to cycle 198 (needs transcript
capture in outcome artefacts)."
```

---

## Task 11: Run full regression check + lint + typecheck

**Files:** none modified — verification only

- [ ] **Step 1: Run ruff + mypy**

```bash
ruff check src/ tests/ --fix
ruff format src/ tests/
mypy src/dazzle/core src/dazzle/cli src/dazzle/mcp --ignore-missing-imports --exclude 'eject'
mypy src/dazzle_back/ --ignore-missing-imports
```

Expected: `All checks passed!` for ruff, `Success: no issues found in ...` for both mypy invocations.

If lint errors remain, fix them inline. If type errors appear in modified files, read them carefully — they usually indicate a real issue in the new code.

- [ ] **Step 2: Run all affected unit + integration tests**

```bash
pytest \
  tests/unit/test_action_result.py \
  tests/unit/test_playwright_executor_enrichment.py \
  tests/unit/test_agent_history_rendering.py \
  tests/unit/test_agent_tool_use.py \
  tests/unit/test_explore_strategy.py \
  tests/unit/fitness/test_fitness_strategy_integration.py \
  tests/integration/test_agent_investigator_tool_use.py \
  -q
```

Expected counts (approximate):
- test_action_result.py: 3
- test_playwright_executor_enrichment.py: 10
- test_agent_history_rendering.py: 17
- test_agent_tool_use.py: 23 (unchanged)
- test_explore_strategy.py: 24 (6 original + 18 new)
- test_fitness_strategy_integration.py: 23 (unchanged)
- test_agent_investigator_tool_use.py: 2 (unchanged)

**Total: ~102 tests should pass.**

- [ ] **Step 3: Run the e2e verification sweep locally**

**Precondition:** Postgres running (`pg_isready`), Redis running (`redis-cli ping` → PONG), `ANTHROPIC_API_KEY` set.

```bash
pytest tests/e2e/test_explore_strategy_e2e.py -m e2e -v --tb=short
```

Expected wall-clock: 5-10 minutes depending on per-persona step counts.

Expected outcome: at least 5/5 `degraded=False`, at least 3/5 with ≥1 proposal. Artefacts land at `dev_docs/cycle_197_verification/<example>.json`.

**If this fails:** the failure is the finding. Possible failure modes:

- **all 5 degraded** — something in the driver is broken; diagnose with one failing example and root-cause.
- **some degraded** — look at `blocked_personas` in the artefact; likely a login / persona provisioning issue.
- **all non-degraded but 0 proposals** — the LLM isn't identifying components; check whether the bail-nudge is firing and whether the history text looks right.

Do NOT proceed to Task 12 until this passes or you have explicitly decided to ship with known gaps documented in the cycle 197 log entry.

- [ ] **Step 4: (No commit)**

No commit in this task. It's a verification checkpoint.

---

## Task 12: Write cycle 197 log entry, bump version, ship

**Files:**
- Modify: `dev_docs/ux-log.md`
- Modify: `pyproject.toml`, `src/dazzle/mcp/semantics_kb/core.toml`, `.claude/CLAUDE.md`, `ROADMAP.md`, `homebrew/dazzle.rb`, `CHANGELOG.md` (via `/bump patch`)

**Goal:** Document cycle 197 in the ux-log, bump to 0.55.4, commit, tag, push.

- [ ] **Step 1: Write cycle 197 entry to ux-log.md**

Read `dev_docs/ux-log.md` first to see the current top entry (should be cycle 196). Then prepend a new entry above cycle 196 using the same format. Template:

```markdown
## 2026-04-14T??:??Z — Cycle 197 — **Layer 4 shipped: action feedback + persona fan-out**

**Outcome:** Six commits delivering the Layer 4 spec at
`docs/superpowers/specs/2026-04-14-layer-4-agent-action-feedback-design.md`.
All unit tests pass (~102 across the affected files). E2E verification
sweep ran against all 5 examples with these results:

| Example | Personas | Proposals (unique) | State |
|---|---|---|---|
| simple_task | admin, manager, user | <N> | <pass/fail> |
| contact_manager | user | <N> | <pass/fail> |
| support_tickets | agent, customer, manager | <N> | <pass/fail> |
| ops_dashboard | ops_engineer | <N> | <pass/fail> |
| fieldtest_hub | engineer, manager, tester | <N> | <pass/fail> |

Total tokens: <from artefacts>
Total wall-clock: <measured>
Apps with ≥1 proposal: <count> / 5 (bar is ≥3/5 for D2)

### Layer 4 deliverables shipped

1. `ActionResult` shape extension — 4 new optional fields
2. `PlaywrightExecutor` console listener + state capture
3. `_format_history_line` + `_is_stuck` helpers in DazzleAgent
4. `_build_messages` history rendering + bail-nudge
5. `pick_explore_personas` + `pick_start_path` auto-derivation
6. `run_explore_strategy` fan-out + dedup + `ExploreOutcome` extension
7. E2E verification test sweep

### Observations from verification run

<Fill in what actually happened — click loops? bail-nudge fired? specific
personas blocked? console errors caught? Leave honest notes.>

### Harness layer scorecard

| # | Layer | Status after cycle 197 |
|---|---|---|
| 1 | EXPLORE driver | ✓ |
| 2 | DazzleAgent text-protocol leak | ✓ |
| 3 | 5-cycle rule semantic gate | ✗ still broken |
| 4 | Agent click-loop on non-navigating actions | <✓ or partial depending on verification data> |
| 5 | Terminal ux-cycle-exhausted signal | ✗ still wrong |

### Next cycle candidates

Based on verification data: <infer which layer to tackle next>

---
```

Fill in the `<...>` placeholders from the verification run's actual output. Do NOT leave template placeholders in the final log entry.

- [ ] **Step 2: Run /bump patch**

```bash
# Bump via the /bump skill, NOT manually — it updates all 6 canonical locations
```

Invoke the `bump` skill with argument `patch`. This updates:
- `pyproject.toml` 0.55.3 → 0.55.4
- `src/dazzle/mcp/semantics_kb/core.toml`
- `.claude/CLAUDE.md`
- `ROADMAP.md`
- `homebrew/dazzle.rb` (version + url)
- `CHANGELOG.md` (new `[0.55.4]` section)

Write the CHANGELOG entry under `[0.55.4]` covering:
- **Fixed:** Layer 4 agent click-loop — action feedback + bail-nudge
- **Added:** `pick_explore_personas`, `pick_start_path`, fan-out in `run_explore_strategy`, `ActionResult` cognition fields
- **Changed:** `run_explore_strategy`'s `personas=None` semantics (now auto-picks, was: anonymous)
- **Agent Guidance:** mission tools must not name-collide with builtin actions; callers who want anonymous explore must explicitly pass `personas=[]`

- [ ] **Step 3: Commit the log entry and bump together**

```bash
git add dev_docs/ux-log.md pyproject.toml src/dazzle/mcp/semantics_kb/core.toml \
        .claude/CLAUDE.md ROADMAP.md homebrew/dazzle.rb CHANGELOG.md
git commit -m "ux: cycle 197 — Layer 4 shipped (action feedback + persona fan-out) + bump 0.55.4"
```

- [ ] **Step 4: Tag and push**

```bash
git tag v0.55.4
git push
git push origin v0.55.4
```

Expected: push succeeds, v0.55.4 tag created, release workflows trigger.

- [ ] **Step 5: Confirm clean worktree**

```bash
git status --short
```

Expected: empty output (clean worktree).

If dev_docs/cycle_197_verification/*.json artefacts are showing as untracked — that is correct. `dev_docs/` is gitignored, the verification artefacts stay local-only by design (see spec Section 6e).

---

## Self-review summary

**Spec coverage check:**

| Spec section | Implementing task(s) |
|---|---|
| ActionResult shape extension | Task 1 |
| PlaywrightExecutor enrichment (console + state capture) | Tasks 2, 3 |
| DazzleAgent history + bail-nudge | Tasks 4, 5 |
| pick_explore_personas | Task 6 |
| pick_start_path | Task 7 |
| Proposal dedup + ExploreOutcome shape | Task 8 |
| run_explore_strategy fan-out | Task 9 |
| E2E verification test | Task 10 |
| Regression check | Task 11 |
| Verification run + log + bump + push | Tasks 11, 12 |

No spec sections missing a task.

**Placeholder scan:** no TBD / TODO / "implement later" in any task. Every code step contains runnable code. Every test step contains the assertion text. Every commit step contains the exact git commands.

**Type / identifier consistency:**
- `_format_history_line` / `_is_stuck` named consistently in tasks 4 and 5
- `pick_explore_personas` / `pick_start_path` / `_dedup_proposals` named consistently in tasks 6-9
- `raw_proposals_by_persona` field name consistent across tasks 8 and 9
- `ExploreOutcome` fields consistent with the spec's dataclass definition

**Scope check:** single feature implementation plan covering one spec, one branch, one release. Task count (12) and code volume (~680 lines of tests + ~150 lines of production code) are within the normal range for a single-spec plan.

Ready for execution.
