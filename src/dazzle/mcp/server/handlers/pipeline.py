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
import time
from pathlib import Path
from typing import Any

from .common import extract_progress, wrap_handler_errors
from .orchestration import (
    QualityStep,
    aggregate_results,
    collect_top_issues,
    extract_step_metrics,
    filter_issues_result,
    run_steps_sequential,
    step_has_issues,
)

# Backward-compat aliases — tests and nightly.py import these names
_build_pipeline_response = aggregate_results
_step_has_issues = step_has_issues
_filter_issues_result = filter_issues_result
_extract_step_metrics = extract_step_metrics
_collect_top_issues = collect_top_issues


@wrap_handler_errors
def run_pipeline_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Run the full deterministic quality pipeline.

    Chains these operations in order, collecting results:
      1. dsl(validate)
      2. dsl(lint)
      3. dsl(fidelity)
      4. composition(audit)
      5. dsl_test(generate)
      6. dsl_test(coverage)
      7. story(coverage)
      8. process(coverage)
      9. test_design(gaps)
     10. semantics(extract)
     11. semantics(validate_events)

    Each step runs regardless of prior failures (unless stop_on_error=True).
    Returns a structured JSON report with per-step results and overall summary.
    """
    progress = extract_progress(args)

    stop_on_error = args.get("stop_on_error", False)
    base_url = args.get("base_url")
    # Adaptive detail levels: metrics (compact), issues (smart default), full
    detail = args.get("detail", "issues")
    # Backward compatibility: old summary param
    if "summary" in args and "detail" not in args:
        detail = "metrics" if args["summary"] else "full"

    pipeline_start = time.monotonic()

    steps, synthetic = _build_quality_steps(project_path, base_url)

    step_results, errors = run_steps_sequential(
        steps,
        stop_on_error=stop_on_error,
        progress=progress,
    )

    # Append synthetic entries (skipped imports, preflight failures)
    next_step_num = len(step_results) + 1
    for entry in synthetic:
        entry["step"] = next_step_num
        step_results.append(entry)
        if entry.get("status") == "error":
            errors.append(f"{entry['operation']}: {entry.get('error', 'unknown')}")
        next_step_num += 1

    return aggregate_results(step_results, errors, pipeline_start, detail=detail)


def _build_quality_steps(
    project_path: Path, base_url: str | None = None
) -> tuple[list[QualityStep], list[dict[str, Any]]]:
    """Build the ordered list of quality pipeline steps.

    Returns:
        (steps, synthetic) — executable steps plus pre-built result entries
        for steps that can't run (import failures, preflight failures).
    """
    from .composition import audit_composition_handler
    from .dsl import lint_project, validate_dsl
    from .dsl_test import generate_dsl_tests_handler, get_dsl_test_coverage_handler
    from .fidelity import score_fidelity_handler
    from .process import stories_coverage_handler
    from .test_design import get_test_gaps_handler

    steps: list[QualityStep] = [
        QualityStep(
            name="dsl(validate)",
            handler=validate_dsl,
            handler_args=(project_path,),
        ),
        QualityStep(
            name="dsl(lint)",
            handler=lint_project,
            handler_args=(project_path, {"extended": True}),
        ),
        QualityStep(
            name="dsl(fidelity)",
            handler=score_fidelity_handler,
            handler_args=(project_path, {"gaps_only": True}),
        ),
        QualityStep(
            name="composition(audit)",
            handler=audit_composition_handler,
            handler_args=(project_path, {}),
        ),
        QualityStep(
            name="dsl_test(generate)",
            handler=generate_dsl_tests_handler,
            handler_args=(project_path, {"save": True}),
        ),
        QualityStep(
            name="dsl_test(coverage)",
            handler=get_dsl_test_coverage_handler,
            handler_args=(project_path, {}),
        ),
        QualityStep(
            name="story(coverage)",
            handler=stories_coverage_handler,
            handler_args=(project_path, {}),
        ),
        QualityStep(
            name="process(coverage)",
            handler=stories_coverage_handler,
            handler_args=(project_path, {"status_filter": "all"}),
        ),
        QualityStep(
            name="test_design(gaps)",
            handler=get_test_gaps_handler,
            handler_args=(project_path, {}),
        ),
    ]

    synthetic: list[dict[str, Any]] = []

    # Semantics steps (optional — module may not be available)
    try:
        from dazzle.mcp.event_first_tools import handle_extract_semantics, handle_validate_events

        steps.append(
            QualityStep(
                name="semantics(extract)",
                handler=handle_extract_semantics,
                handler_args=({"compact": True}, project_path),
                optional=True,
            )
        )
        steps.append(
            QualityStep(
                name="semantics(validate_events)",
                handler=handle_validate_events,
                handler_args=({}, project_path),
                optional=True,
            )
        )
    except ImportError:
        synthetic.append(
            {
                "operation": "semantics(extract)",
                "status": "skipped",
                "reason": "event_first_tools not available",
            }
        )
        synthetic.append(
            {
                "operation": "semantics(validate_events)",
                "status": "skipped",
                "reason": "event_first_tools not available",
            }
        )

    # Optional live test step
    if base_url:
        from .preflight import check_server_reachable

        preflight_err = check_server_reachable(base_url)
        if not preflight_err:
            from .dsl_test import run_all_dsl_tests_handler

            steps.append(
                QualityStep(
                    name="dsl_test(run_all)",
                    handler=run_all_dsl_tests_handler,
                    handler_args=(project_path, {"base_url": base_url}),
                    optional=True,
                )
            )
        else:
            synthetic.append(
                {
                    "operation": "dsl_test(run_all)",
                    "status": "error",
                    "error": json.loads(preflight_err).get("error", "Server not reachable"),
                    "duration_ms": 0,
                }
            )

    return steps, synthetic
