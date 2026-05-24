"""#1211: ``assert_visible`` auto-resolves a UI URL from the design's
``surfaces[0]`` when no preceding ``navigate_to`` has stashed one.

Pre-#1211 a design that emitted ``assert_visible`` without first
navigating (e.g. STATUS_CHANGED-trigger TD-* tests) hit the bare
``client.ui_url``, bounced 302 → /login, and failed identically on
every nightly. The runner now synthesises ``/app/workspaces/<surface>``
from the design's ``surfaces`` list as a backstop so those tests
exercise a real workspace instead.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from dazzle.testing.test_runner import TestResult, TestRunner, UICheckResult


def _runner_with_client(ok: bool = True, status: int = 200) -> TestRunner:
    runner = TestRunner(project_path=Path("/tmp/_test_1211"))
    client = MagicMock()
    client.ui_url = "http://stg.example"
    client._auth_token = "tok"
    client.client = MagicMock()
    cookies = MagicMock()
    cookies.get = MagicMock(return_value="sess")
    client.client.cookies = cookies
    client.check_ui_loads = MagicMock(
        return_value=UICheckResult(
            ok=ok,
            status=status,
            url="http://stg.example/app/workspaces/task_list",
            excerpt="<title>Tasks</title>" if ok else "",
        )
    )
    runner.client = client
    return runner


def test_fallback_resolves_via_appspec_when_project_has_dsl(tmp_path: Path) -> None:
    """#1224 update: when _current_ui_url is unset and the design has
    surfaces, the fallback now resolves via the route generator's
    actual URL templates (per SurfaceMode) — not the hardcoded
    ``/app/workspaces/{name}`` that 404'd for list/create surfaces.
    Requires a parseable project to find the surface kinds."""
    (tmp_path / "dsl").mkdir()
    (tmp_path / "dsl" / "app.dsl").write_text(
        "module tinytest.core\n"
        'app tinytest "Tiny"\n\n'
        'persona admin "Admin":\n'
        '  description: "test"\n\n'
        'entity Task "Task":\n'
        "  id: uuid pk\n"
        "  title: str(100) required\n\n"
        'surface task_list "Tasks":\n'
        "  uses entity Task\n"
        "  mode: list\n"
        "  section main:\n"
        '    field title "Title"\n'
    )
    runner = _runner_with_client(ok=True)
    runner.project_path = tmp_path  # rebind to the tmp project

    context: dict = {"_design_surfaces": ["task_list"]}
    result = runner.execute_step(
        {"action": "assert_visible", "target": "task"},
        design={"surfaces": ["task_list"]},
        context=context,
    )
    # #1230: task_list is a LIST surface → /app/task, NOT
    # /app/workspaces/task_list (and not the JSON-API plural /tasks).
    assert context["_current_ui_url"] == "http://stg.example/app/task"
    assert runner.client is not None
    runner.client.check_ui_loads.assert_called_once_with(  # type: ignore[attr-defined]
        url="http://stg.example/app/task"
    )
    assert result.result is TestResult.PASSED


def test_fallback_no_op_when_appspec_unavailable() -> None:
    """#1224: when the project has no parseable DSL, the resolver
    returns None — runner falls through to the bare ui_url rather
    than constructing a wrong URL."""
    runner = _runner_with_client(ok=True)
    context: dict = {"_design_surfaces": ["task_list"]}
    runner.execute_step(
        {"action": "assert_visible", "target": "task"},
        design={"surfaces": ["task_list"]},
        context=context,
    )
    assert "_current_ui_url" not in context


def test_fallback_does_not_override_existing_url() -> None:
    """When a preceding navigate_to already stashed a URL, the
    fallback is a no-op — the user-intent URL wins."""
    runner = _runner_with_client(ok=True)
    preset = "http://stg.example/app/task/create"
    context: dict = {
        "_design_surfaces": ["task_list"],
        "_current_ui_url": preset,
    }
    runner.execute_step(
        {"action": "assert_visible", "target": "task"},
        design={"surfaces": ["task_list"]},
        context=context,
    )
    assert context["_current_ui_url"] == preset
    assert runner.client is not None
    runner.client.check_ui_loads.assert_called_once_with(url=preset)  # type: ignore[attr-defined]


def test_no_surfaces_means_no_fallback() -> None:
    """A design with no surfaces (or empty list) gets the legacy
    behaviour — check_ui_loads called with url=None, hits the bare
    base URL. The fallback must not inject a phantom URL."""
    runner = _runner_with_client(ok=False, status=302)
    context: dict = {"_design_surfaces": []}
    runner.execute_step(
        {"action": "assert_visible", "target": "task"},
        design={"surfaces": []},
        context=context,
    )
    assert "_current_ui_url" not in context
    assert runner.client is not None
    runner.client.check_ui_loads.assert_called_once_with(url=None)  # type: ignore[attr-defined]


def test_fallback_missing_design_surfaces_key() -> None:
    """If _design_surfaces was never stashed (older callers of
    execute_step that don't go through run_single_test), the
    fallback is a no-op rather than crashing on a missing key."""
    runner = _runner_with_client(ok=False, status=302)
    context: dict = {}  # no _design_surfaces at all
    runner.execute_step(
        {"action": "assert_visible", "target": "task"},
        design={},
        context=context,
    )
    assert "_current_ui_url" not in context
    assert runner.client is not None
    runner.client.check_ui_loads.assert_called_once_with(url=None)  # type: ignore[attr-defined]
