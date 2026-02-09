"""
Pipeline tool handler.

Chains multiple deterministic quality operations into a single call,
returning a structured report. Designed for autonomous agent loops
that need a full project health check in one MCP round-trip.

Operations:
  run — Execute the full quality pipeline
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("dazzle.mcp.handlers.pipeline")


def run_pipeline_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Run the full deterministic quality pipeline.

    Chains these operations in order, collecting results:
      1. dsl(validate)
      2. dsl(lint)
      3. dsl(fidelity)
      4. dsl_test(generate)
      5. dsl_test(coverage)
      6. story(coverage)
      7. process(coverage)
      8. test_design(gaps)
      9. semantics(extract)
     10. semantics(validate_events)

    Each step runs regardless of prior failures (unless stop_on_error=True).
    Returns a structured JSON report with per-step results and overall summary.
    """
    stop_on_error = args.get("stop_on_error", False)
    base_url = args.get("base_url")

    pipeline_start = time.monotonic()
    steps: list[dict[str, Any]] = []
    errors: list[str] = []

    def _run_step(
        step_num: int,
        name: str,
        func: Any,
        *func_args: Any,
        **func_kwargs: Any,
    ) -> dict[str, Any] | None:
        """Execute a single pipeline step and record the result."""
        t0 = time.monotonic()
        step_result: dict[str, Any] = {
            "step": step_num,
            "operation": name,
        }
        try:
            raw = func(*func_args, **func_kwargs)
            duration_ms = (time.monotonic() - t0) * 1000
            step_result["duration_ms"] = round(duration_ms, 1)

            # Parse JSON result if possible
            try:
                data = json.loads(raw)
                if "error" in data:
                    step_result["status"] = "error"
                    step_result["error"] = data["error"]
                    errors.append(f"{name}: {data['error']}")
                else:
                    step_result["status"] = "passed"
                    step_result["result"] = data
            except (json.JSONDecodeError, TypeError):
                step_result["status"] = "passed"
                step_result["result"] = str(raw)[:500]

        except Exception as e:
            duration_ms = (time.monotonic() - t0) * 1000
            step_result["duration_ms"] = round(duration_ms, 1)
            step_result["status"] = "error"
            step_result["error"] = str(e)
            errors.append(f"{name}: {e}")
            logger.warning("Pipeline step %s failed: %s", name, e)

        steps.append(step_result)
        return step_result

    # -----------------------------------------------------------------------
    # Step 1: DSL Validation
    # -----------------------------------------------------------------------
    from .dsl import validate_dsl

    result = _run_step(1, "dsl(validate)", validate_dsl, project_path)
    if stop_on_error and result and result["status"] == "error":
        return _build_pipeline_response(steps, errors, pipeline_start)

    # -----------------------------------------------------------------------
    # Step 2: DSL Lint
    # -----------------------------------------------------------------------
    from .dsl import lint_project

    _run_step(2, "dsl(lint)", lint_project, project_path, {"extended": True})

    # -----------------------------------------------------------------------
    # Step 3: Fidelity
    # -----------------------------------------------------------------------
    from .fidelity import score_fidelity_handler

    _run_step(3, "dsl(fidelity)", score_fidelity_handler, project_path, {})

    # -----------------------------------------------------------------------
    # Step 4: Test Generation
    # -----------------------------------------------------------------------
    from .dsl_test import generate_dsl_tests_handler

    _run_step(
        4,
        "dsl_test(generate)",
        generate_dsl_tests_handler,
        project_path,
        {"save": True},
    )

    # -----------------------------------------------------------------------
    # Step 5: Test Coverage
    # -----------------------------------------------------------------------
    from .dsl_test import get_dsl_test_coverage_handler

    _run_step(5, "dsl_test(coverage)", get_dsl_test_coverage_handler, project_path, {})

    # -----------------------------------------------------------------------
    # Step 6: Story Coverage
    # -----------------------------------------------------------------------
    from .process import stories_coverage_handler

    _run_step(6, "story(coverage)", stories_coverage_handler, project_path, {})

    # -----------------------------------------------------------------------
    # Step 7: Process Coverage
    # -----------------------------------------------------------------------
    _run_step(
        7,
        "process(coverage)",
        stories_coverage_handler,
        project_path,
        {"status_filter": "all"},
    )

    # -----------------------------------------------------------------------
    # Step 8: Test Design Gaps
    # -----------------------------------------------------------------------
    from .test_design import get_test_gaps_handler

    _run_step(8, "test_design(gaps)", get_test_gaps_handler, project_path, {})

    # -----------------------------------------------------------------------
    # Step 9: Semantics Extract
    # -----------------------------------------------------------------------
    try:
        from dazzle.mcp.event_first_tools import handle_extract_semantics

        _run_step(
            9,
            "semantics(extract)",
            handle_extract_semantics,
            {},
            project_path,
        )
    except ImportError:
        steps.append(
            {
                "step": 9,
                "operation": "semantics(extract)",
                "status": "skipped",
                "reason": "event_first_tools not available",
            }
        )

    # -----------------------------------------------------------------------
    # Step 10: Semantics Validate Events
    # -----------------------------------------------------------------------
    try:
        from dazzle.mcp.event_first_tools import handle_validate_events

        _run_step(
            10,
            "semantics(validate_events)",
            handle_validate_events,
            {},
            project_path,
        )
    except ImportError:
        steps.append(
            {
                "step": 10,
                "operation": "semantics(validate_events)",
                "status": "skipped",
                "reason": "event_first_tools not available",
            }
        )

    # -----------------------------------------------------------------------
    # Optional Step 11: Run all tests (only if base_url provided)
    # -----------------------------------------------------------------------
    if base_url:
        from .dsl_test import run_all_dsl_tests_handler

        _run_step(
            11,
            "dsl_test(run_all)",
            run_all_dsl_tests_handler,
            project_path,
            {"base_url": base_url},
        )

    return _build_pipeline_response(steps, errors, pipeline_start)


def _build_pipeline_response(
    steps: list[dict[str, Any]],
    errors: list[str],
    start_time: float,
) -> str:
    """Build the final pipeline response JSON."""
    total_ms = (time.monotonic() - start_time) * 1000

    passed = sum(1 for s in steps if s.get("status") == "passed")
    failed = sum(1 for s in steps if s.get("status") == "error")
    skipped = sum(1 for s in steps if s.get("status") == "skipped")

    status = "passed" if failed == 0 else "failed"

    response: dict[str, Any] = {
        "status": status,
        "total_duration_ms": round(total_ms, 1),
        "summary": {
            "total_steps": len(steps),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
        },
        "steps": steps,
    }

    if errors:
        response["errors"] = errors

    return json.dumps(response, indent=2)
