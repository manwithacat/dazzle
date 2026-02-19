"""
Nightly tool handler — parallel quality runner.

Runs the same quality steps as ``pipeline run`` but fans out independent
steps using a thread pool, cutting wall-clock time roughly in half.

Operations:
  run — Execute quality steps in parallel with topological scheduling
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .common import wrap_handler_errors
from .orchestration import QualityStep, aggregate_results, run_step

logger = logging.getLogger("dazzle.mcp.handlers.nightly")


# ---------------------------------------------------------------------------
# Step builder
# ---------------------------------------------------------------------------


def _build_steps(project_path: Path, base_url: str | None = None) -> list[QualityStep]:
    """Build the list of nightly steps with dependency edges."""
    from .composition import audit_composition_handler
    from .dsl import lint_project, validate_dsl
    from .dsl_test import generate_dsl_tests_handler, get_dsl_test_coverage_handler
    from .fidelity import score_fidelity_handler
    from .process import stories_coverage_handler
    from .test_design import get_test_gaps_handler

    steps: list[QualityStep] = [
        # Gate
        QualityStep(
            name="dsl(validate)",
            handler=validate_dsl,
            handler_args=(project_path,),
        ),
        # Track A — independent after gate
        QualityStep(
            name="dsl(lint)",
            handler=lint_project,
            handler_args=(project_path, {"extended": True}),
            depends_on=["dsl(validate)"],
        ),
        QualityStep(
            name="dsl(fidelity)",
            handler=score_fidelity_handler,
            handler_args=(project_path, {"gaps_only": True}),
            depends_on=["dsl(validate)"],
        ),
        QualityStep(
            name="composition(audit)",
            handler=audit_composition_handler,
            handler_args=(project_path, {}),
            depends_on=["dsl(validate)"],
        ),
        # Track B — sequential pair
        QualityStep(
            name="dsl_test(generate)",
            handler=generate_dsl_tests_handler,
            handler_args=(project_path, {"save": True}),
            depends_on=["dsl(validate)"],
        ),
        QualityStep(
            name="dsl_test(coverage)",
            handler=get_dsl_test_coverage_handler,
            handler_args=(project_path, {}),
            depends_on=["dsl_test(generate)"],
        ),
        # Track C — independent after gate
        QualityStep(
            name="story(coverage)",
            handler=stories_coverage_handler,
            handler_args=(project_path, {}),
            depends_on=["dsl(validate)"],
        ),
        QualityStep(
            name="process(coverage)",
            handler=stories_coverage_handler,
            handler_args=(project_path, {"status_filter": "all"}),
            depends_on=["dsl(validate)"],
        ),
        QualityStep(
            name="test_design(gaps)",
            handler=get_test_gaps_handler,
            handler_args=(project_path, {}),
            depends_on=["dsl(validate)"],
        ),
    ]

    # Track D — semantics (optional — module may not be available)
    try:
        from dazzle.mcp.event_first_tools import handle_extract_semantics, handle_validate_events

        steps.append(
            QualityStep(
                name="semantics(extract)",
                handler=handle_extract_semantics,
                handler_args=({"compact": True}, project_path),
                depends_on=["dsl(validate)"],
                optional=True,
            )
        )
        steps.append(
            QualityStep(
                name="semantics(validate_events)",
                handler=handle_validate_events,
                handler_args=({}, project_path),
                depends_on=["semantics(extract)"],
                optional=True,
            )
        )
    except ImportError:
        pass

    # Track E — optional live test step
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
                    depends_on=["dsl(validate)"],
                    optional=True,
                )
            )

    return steps


# ---------------------------------------------------------------------------
# Main handler — topological parallel scheduler
# ---------------------------------------------------------------------------


@wrap_handler_errors
def run_nightly_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Run quality steps in parallel with topological scheduling."""
    stop_on_error = args.get("stop_on_error", False)
    base_url = args.get("base_url")
    detail = args.get("detail", "issues")
    workers = args.get("workers", 4)

    # Backward compatibility with pipeline 'summary' param
    if "summary" in args and "detail" not in args:
        detail = "metrics" if args["summary"] else "full"

    activity_store = args.get("_activity_store")

    pipeline_start = time.monotonic()

    all_steps = _build_steps(project_path, base_url)

    # Track completed/failed/skipped
    completed: dict[str, dict[str, Any]] = {}
    failed_names: set[str] = set()
    skipped_names: set[str] = set()
    errors: list[str] = []
    stop_flag = False

    def _deps_satisfied(step: QualityStep) -> bool:
        for dep in step.depends_on:
            if dep in failed_names or dep in skipped_names:
                return False
            if dep not in completed:
                return False
        return True

    def _deps_failed(step: QualityStep) -> bool:
        for dep in step.depends_on:
            if dep in failed_names or dep in skipped_names:
                return True
        return False

    submitted: set[str] = set()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures: dict[Future[dict[str, Any]], str] = {}

        while len(completed) + len(failed_names) + len(skipped_names) < len(all_steps):
            if stop_flag:
                # Skip all remaining
                for s in all_steps:
                    if (
                        s.name not in completed
                        and s.name not in failed_names
                        and s.name not in skipped_names
                    ):
                        skipped_names.add(s.name)
                break

            # Skip steps whose dependencies failed
            for s in all_steps:
                if (
                    s.name in completed
                    or s.name in failed_names
                    or s.name in skipped_names
                    or s.name in submitted
                ):
                    continue
                if _deps_failed(s):
                    skipped_names.add(s.name)

            # Submit ready steps
            for s in all_steps:
                if (
                    s.name in completed
                    or s.name in failed_names
                    or s.name in skipped_names
                    or s.name in submitted
                ):
                    continue
                if _deps_satisfied(s):
                    fut = pool.submit(
                        run_step, s, activity_store=activity_store, activity_prefix="nightly:"
                    )
                    futures[fut] = s.name
                    submitted.add(s.name)

            if not futures:
                # Nothing in flight and nothing to submit — break to avoid deadlock
                break

            # Wait for at least one future to complete
            done_iter = as_completed(futures, timeout=600)
            try:
                done_fut = next(done_iter)
            except StopIteration:
                break

            step_name = futures.pop(done_fut)
            step_result = done_fut.result()
            completed[step_name] = step_result

            if step_result.get("status") == "error":
                failed_names.add(step_name)
                errors.append(f"{step_name}: {step_result.get('error', 'unknown')}")
                if stop_on_error:
                    stop_flag = True
                    # Cancel pending futures
                    for f in futures:
                        f.cancel()

    # Build ordered results matching original step order
    steps_output: list[dict[str, Any]] = []
    for idx, s in enumerate(all_steps, 1):
        if s.name in completed:
            entry = completed[s.name]
            entry["step"] = idx
            steps_output.append(entry)
        elif s.name in skipped_names:
            steps_output.append(
                {
                    "step": idx,
                    "operation": s.name,
                    "status": "skipped",
                    "reason": "dependency failed or stopped early",
                }
            )
        # Should not happen, but handle gracefully
        else:
            steps_output.append(
                {
                    "step": idx,
                    "operation": s.name,
                    "status": "skipped",
                    "reason": "not reached",
                }
            )

    response_json = aggregate_results(steps_output, errors, pipeline_start, detail=detail)

    # Inject parallel metadata
    data = json.loads(response_json)
    data["_meta"]["parallel"] = True
    data["_meta"]["workers"] = workers

    return json.dumps(data, indent=2)
