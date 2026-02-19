"""Tests for the nightly parallel quality runner."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok_result(data: dict[str, Any] | None = None) -> str:
    return json.dumps(data or {"status": "ok"})


def _error_result(msg: str = "fail") -> str:
    return json.dumps({"error": msg})


# ---------------------------------------------------------------------------
# Step Definitions
# ---------------------------------------------------------------------------


class TestQualityStepDefinitions:
    """Tests for _build_steps()."""

    def test_build_steps_count(self) -> None:
        from dazzle.mcp.server.handlers.nightly import _build_steps

        steps = _build_steps(Path("/fake"))
        # 9 base steps + potentially 2 semantics (if importable)
        assert len(steps) >= 9

    def test_build_steps_deps_valid(self) -> None:
        from dazzle.mcp.server.handlers.nightly import _build_steps

        steps = _build_steps(Path("/fake"))
        names = {s.name for s in steps}
        for s in steps:
            for dep in s.depends_on:
                assert dep in names, f"{s.name} depends on unknown step {dep}"

    def test_gate_has_no_deps(self) -> None:
        from dazzle.mcp.server.handlers.nightly import _build_steps

        steps = _build_steps(Path("/fake"))
        gate = next(s for s in steps if s.name == "dsl(validate)")
        assert gate.depends_on == []

    def test_all_non_gate_depend_on_validate(self) -> None:
        from dazzle.mcp.server.handlers.nightly import _build_steps

        steps = _build_steps(Path("/fake"))
        for s in steps:
            if s.name == "dsl(validate)":
                continue
            # Every step should transitively depend on the gate
            visited: set[str] = set()
            queue = list(s.depends_on)
            while queue:
                dep = queue.pop()
                if dep in visited:
                    continue
                visited.add(dep)
                dep_step = next((x for x in steps if x.name == dep), None)
                if dep_step:
                    queue.extend(dep_step.depends_on)
            assert "dsl(validate)" in visited, f"{s.name} does not transitively depend on gate"


# ---------------------------------------------------------------------------
# Parallel Execution
# ---------------------------------------------------------------------------


class TestNightlyParallelExecution:
    """Verify steps actually run concurrently."""

    def _make_handler(self, delay: float = 0.05) -> MagicMock:
        def _fn(*_a: Any, **_kw: Any) -> str:
            time.sleep(delay)
            return _ok_result()

        return MagicMock(side_effect=_fn)

    @patch("dazzle.mcp.server.handlers.nightly._build_steps")
    def test_parallel_faster_than_sequential(self, mock_build: MagicMock) -> None:
        from dazzle.mcp.server.handlers.nightly import run_nightly_handler
        from dazzle.mcp.server.handlers.orchestration import QualityStep

        delay = 0.05
        h = self._make_handler(delay)

        mock_build.return_value = [
            QualityStep(name="gate", handler=h),
            QualityStep(name="a", handler=h, depends_on=["gate"]),
            QualityStep(name="b", handler=h, depends_on=["gate"]),
            QualityStep(name="c", handler=h, depends_on=["gate"]),
        ]

        t0 = time.monotonic()
        raw = run_nightly_handler(Path("/fake"), {"workers": 4})
        elapsed = time.monotonic() - t0

        data = json.loads(raw)
        assert data["status"] == "passed"
        # Sequential would take 4 * delay; parallel should be ~2 * delay
        sequential_time = 4 * delay
        assert elapsed < sequential_time, (
            f"Took {elapsed:.3f}s, sequential would be {sequential_time:.3f}s"
        )


# ---------------------------------------------------------------------------
# Dependency Graph
# ---------------------------------------------------------------------------


class TestNightlyDependencyGraph:
    """Test that dependency failures propagate correctly."""

    @patch("dazzle.mcp.server.handlers.nightly._build_steps")
    def test_gate_failure_skips_all(self, mock_build: MagicMock) -> None:
        from dazzle.mcp.server.handlers.nightly import run_nightly_handler
        from dazzle.mcp.server.handlers.orchestration import QualityStep

        mock_build.return_value = [
            QualityStep(
                name="gate",
                handler=MagicMock(return_value=_error_result("parse error")),
            ),
            QualityStep(
                name="lint",
                handler=MagicMock(return_value=_ok_result()),
                depends_on=["gate"],
            ),
            QualityStep(
                name="fidelity",
                handler=MagicMock(return_value=_ok_result()),
                depends_on=["gate"],
            ),
        ]

        raw = run_nightly_handler(Path("/fake"), {})
        data = json.loads(raw)

        assert data["status"] == "failed"
        steps = data["steps"]
        assert steps[0]["status"] == "error"
        assert steps[1]["status"] == "skipped"
        assert steps[2]["status"] == "skipped"

    @patch("dazzle.mcp.server.handlers.nightly._build_steps")
    def test_mid_chain_failure_skips_dependent(self, mock_build: MagicMock) -> None:
        from dazzle.mcp.server.handlers.nightly import run_nightly_handler
        from dazzle.mcp.server.handlers.orchestration import QualityStep

        mock_build.return_value = [
            QualityStep(
                name="gate",
                handler=MagicMock(return_value=_ok_result()),
            ),
            QualityStep(
                name="gen",
                handler=MagicMock(return_value=_error_result()),
                depends_on=["gate"],
            ),
            QualityStep(
                name="cov",
                handler=MagicMock(return_value=_ok_result()),
                depends_on=["gen"],
            ),
            QualityStep(
                name="lint",
                handler=MagicMock(return_value=_ok_result()),
                depends_on=["gate"],
            ),
        ]

        raw = run_nightly_handler(Path("/fake"), {})
        data = json.loads(raw)

        by_name = {s["operation"]: s for s in data["steps"]}
        assert by_name["gate"]["status"] == "passed"
        assert by_name["gen"]["status"] == "error"
        assert by_name["cov"]["status"] == "skipped"
        assert by_name["lint"]["status"] == "passed"


# ---------------------------------------------------------------------------
# Stop on Error
# ---------------------------------------------------------------------------


class TestNightlyStopOnError:
    """Test stop_on_error cancels remaining steps."""

    @patch("dazzle.mcp.server.handlers.nightly._build_steps")
    def test_stop_on_error(self, mock_build: MagicMock) -> None:
        from dazzle.mcp.server.handlers.nightly import run_nightly_handler
        from dazzle.mcp.server.handlers.orchestration import QualityStep

        mock_build.return_value = [
            QualityStep(
                name="gate",
                handler=MagicMock(return_value=_error_result("bad")),
            ),
            QualityStep(
                name="a",
                handler=MagicMock(return_value=_ok_result()),
                depends_on=["gate"],
            ),
        ]

        raw = run_nightly_handler(Path("/fake"), {"stop_on_error": True})
        data = json.loads(raw)

        assert data["status"] == "failed"
        assert any(s["status"] == "skipped" for s in data["steps"])


# ---------------------------------------------------------------------------
# Activity Logging
# ---------------------------------------------------------------------------


class TestNightlyActivityLogging:
    """Test per-step activity events are logged."""

    @patch("dazzle.mcp.server.handlers.nightly._build_steps")
    def test_activity_events_logged(self, mock_build: MagicMock) -> None:
        from dazzle.mcp.server.handlers.nightly import run_nightly_handler
        from dazzle.mcp.server.handlers.orchestration import QualityStep

        mock_build.return_value = [
            QualityStep(
                name="gate",
                handler=MagicMock(return_value=_ok_result()),
            ),
            QualityStep(
                name="lint",
                handler=MagicMock(return_value=_ok_result()),
                depends_on=["gate"],
            ),
        ]

        store = MagicMock()
        run_nightly_handler(Path("/fake"), {"_activity_store": store})

        calls = list(store.log_event.call_args_list)
        tool_names = [c[0][1] for c in calls]
        assert "nightly:gate" in tool_names
        assert "nightly:lint" in tool_names

        starts = [c for c in calls if c[0][0] == "tool_start"]
        ends = [c for c in calls if c[0][0] == "tool_end"]
        assert len(starts) == 2
        assert len(ends) == 2


# ---------------------------------------------------------------------------
# Response Format
# ---------------------------------------------------------------------------


class TestNightlyResponseFormat:
    """Test output matches pipeline format with parallel metadata."""

    @patch("dazzle.mcp.server.handlers.nightly._build_steps")
    def test_response_has_parallel_meta(self, mock_build: MagicMock) -> None:
        from dazzle.mcp.server.handlers.nightly import run_nightly_handler
        from dazzle.mcp.server.handlers.orchestration import QualityStep

        mock_build.return_value = [
            QualityStep(
                name="gate",
                handler=MagicMock(return_value=_ok_result()),
            ),
        ]

        raw = run_nightly_handler(Path("/fake"), {"workers": 6})
        data = json.loads(raw)

        assert data["_meta"]["parallel"] is True
        assert data["_meta"]["workers"] == 6
        assert "status" in data
        assert "summary" in data
        assert "steps" in data

    @patch("dazzle.mcp.server.handlers.nightly._build_steps")
    def test_detail_levels(self, mock_build: MagicMock) -> None:
        from dazzle.mcp.server.handlers.nightly import run_nightly_handler
        from dazzle.mcp.server.handlers.orchestration import QualityStep

        mock_build.return_value = [
            QualityStep(
                name="gate",
                handler=MagicMock(return_value=_ok_result()),
            ),
        ]

        for detail in ("metrics", "issues", "full"):
            raw = run_nightly_handler(Path("/fake"), {"detail": detail})
            data = json.loads(raw)
            assert data["_meta"]["detail_level"] == detail

    @patch("dazzle.mcp.server.handlers.nightly._build_steps")
    def test_step_numbering_matches_order(self, mock_build: MagicMock) -> None:
        from dazzle.mcp.server.handlers.nightly import run_nightly_handler
        from dazzle.mcp.server.handlers.orchestration import QualityStep

        mock_build.return_value = [
            QualityStep(name="gate", handler=MagicMock(return_value=_ok_result())),
            QualityStep(
                name="a",
                handler=MagicMock(return_value=_ok_result()),
                depends_on=["gate"],
            ),
            QualityStep(
                name="b",
                handler=MagicMock(return_value=_ok_result()),
                depends_on=["gate"],
            ),
        ]

        raw = run_nightly_handler(Path("/fake"), {})
        data = json.loads(raw)
        for i, step in enumerate(data["steps"], 1):
            assert step["step"] == i


# ---------------------------------------------------------------------------
# CLI Tests — test function directly (not via CliRunner for sub-apps)
# ---------------------------------------------------------------------------


class TestNightlyCLI:
    """Test CLI output rendering."""

    def test_print_nightly_table_passed(self, capsys: pytest.CaptureFixture[str]) -> None:
        from dazzle.cli.nightly import _print_nightly_table

        data = {
            "status": "passed",
            "total_duration_ms": 200,
            "summary": {
                "total_steps": 2,
                "passed": 2,
                "failed": 0,
                "skipped": 0,
            },
            "steps": [
                {
                    "step": 1,
                    "operation": "dsl(validate)",
                    "status": "passed",
                    "duration_ms": 50,
                },
                {
                    "step": 2,
                    "operation": "dsl(lint)",
                    "status": "passed",
                    "duration_ms": 30,
                },
            ],
            "_meta": {"parallel": True, "workers": 4},
        }

        _print_nightly_table(data)
        captured = capsys.readouterr()
        assert "Nightly Quality Report" in captured.out
        assert "2/2 passed" in captured.out
        assert "4 workers" in captured.out

    def test_print_nightly_table_with_errors(self, capsys: pytest.CaptureFixture[str]) -> None:
        from dazzle.cli.nightly import _print_nightly_table

        data = {
            "status": "failed",
            "total_duration_ms": 100,
            "summary": {
                "total_steps": 2,
                "passed": 1,
                "failed": 1,
                "skipped": 0,
            },
            "steps": [
                {
                    "step": 1,
                    "operation": "dsl(validate)",
                    "status": "error",
                    "duration_ms": 50,
                    "error": "parse failed",
                },
                {
                    "step": 2,
                    "operation": "dsl(lint)",
                    "status": "passed",
                    "duration_ms": 30,
                },
            ],
            "_meta": {"parallel": True, "workers": 4},
        }

        _print_nightly_table(data)
        captured = capsys.readouterr()
        assert "1 failed" in captured.out
        assert "parse failed" in captured.out

    def test_print_nightly_table_with_skipped(self, capsys: pytest.CaptureFixture[str]) -> None:
        from dazzle.cli.nightly import _print_nightly_table

        data = {
            "status": "failed",
            "total_duration_ms": 50,
            "summary": {
                "total_steps": 2,
                "passed": 0,
                "failed": 1,
                "skipped": 1,
            },
            "steps": [
                {
                    "step": 1,
                    "operation": "dsl(validate)",
                    "status": "error",
                    "duration_ms": 50,
                    "error": "bad",
                },
                {
                    "step": 2,
                    "operation": "dsl(lint)",
                    "status": "skipped",
                },
            ],
            "_meta": {"parallel": True, "workers": 2},
        }

        _print_nightly_table(data)
        captured = capsys.readouterr()
        assert "1 skipped" in captured.out


# ---------------------------------------------------------------------------
# Handler consolidated dispatch
# ---------------------------------------------------------------------------


class TestNightlyConsolidated:
    """Test MCP handler registration."""

    def test_handler_in_dispatch_map(self) -> None:
        from dazzle.mcp.server.handlers_consolidated import CONSOLIDATED_TOOL_HANDLERS

        assert "nightly" in CONSOLIDATED_TOOL_HANDLERS

    def test_tool_schema_registered(self) -> None:
        from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

        tools = get_consolidated_tools()
        names = [t.name for t in tools]
        assert "nightly" in names

    def test_tool_schema_has_run_operation(self) -> None:
        from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

        tools = get_consolidated_tools()
        nightly = next(t for t in tools if t.name == "nightly")
        ops = nightly.inputSchema["properties"]["operation"]["enum"]
        assert "run" in ops
