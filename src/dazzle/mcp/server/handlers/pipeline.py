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
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dazzle.mcp.server.progress import ProgressContext
from dazzle.mcp.server.progress import noop as _noop_progress

logger = logging.getLogger("dazzle.mcp.handlers.pipeline")


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
    progress: ProgressContext = args.get("_progress") or _noop_progress()

    stop_on_error = args.get("stop_on_error", False)
    base_url = args.get("base_url")
    # Adaptive detail levels: metrics (compact), issues (smart default), full
    detail = args.get("detail", "issues")
    # Backward compatibility: old summary param
    if "summary" in args and "detail" not in args:
        detail = "metrics" if args["summary"] else "full"

    total_steps = 12 if base_url else 11

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
        progress.advance_sync(step_num, total_steps, name)

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
        return _build_pipeline_response(steps, errors, pipeline_start, detail=detail)

    # -----------------------------------------------------------------------
    # Step 2: DSL Lint
    # -----------------------------------------------------------------------
    from .dsl import lint_project

    _run_step(2, "dsl(lint)", lint_project, project_path, {"extended": True})

    # -----------------------------------------------------------------------
    # Step 3: Fidelity
    # -----------------------------------------------------------------------
    from .fidelity import score_fidelity_handler

    _run_step(3, "dsl(fidelity)", score_fidelity_handler, project_path, {"gaps_only": True})

    # -----------------------------------------------------------------------
    # Step 4: Composition Audit
    # -----------------------------------------------------------------------
    from .composition import audit_composition_handler

    _run_step(4, "composition(audit)", audit_composition_handler, project_path, {})

    # -----------------------------------------------------------------------
    # Step 5: Test Generation
    # -----------------------------------------------------------------------
    from .dsl_test import generate_dsl_tests_handler

    _run_step(
        5,
        "dsl_test(generate)",
        generate_dsl_tests_handler,
        project_path,
        {"save": True},
    )

    # -----------------------------------------------------------------------
    # Step 6: Test Coverage
    # -----------------------------------------------------------------------
    from .dsl_test import get_dsl_test_coverage_handler

    _run_step(6, "dsl_test(coverage)", get_dsl_test_coverage_handler, project_path, {})

    # -----------------------------------------------------------------------
    # Step 7: Story Coverage
    # -----------------------------------------------------------------------
    from .process import stories_coverage_handler

    _run_step(7, "story(coverage)", stories_coverage_handler, project_path, {})

    # -----------------------------------------------------------------------
    # Step 8: Process Coverage
    # -----------------------------------------------------------------------
    _run_step(
        8,
        "process(coverage)",
        stories_coverage_handler,
        project_path,
        {"status_filter": "all"},
    )

    # -----------------------------------------------------------------------
    # Step 9: Test Design Gaps
    # -----------------------------------------------------------------------
    from .test_design import get_test_gaps_handler

    _run_step(9, "test_design(gaps)", get_test_gaps_handler, project_path, {})

    # -----------------------------------------------------------------------
    # Step 10: Semantics Extract
    # -----------------------------------------------------------------------
    try:
        from dazzle.mcp.event_first_tools import handle_extract_semantics

        _run_step(
            10,
            "semantics(extract)",
            handle_extract_semantics,
            {"compact": True},
            project_path,
        )
    except ImportError:
        steps.append(
            {
                "step": 10,
                "operation": "semantics(extract)",
                "status": "skipped",
                "reason": "event_first_tools not available",
            }
        )

    # -----------------------------------------------------------------------
    # Step 11: Semantics Validate Events
    # -----------------------------------------------------------------------
    try:
        from dazzle.mcp.event_first_tools import handle_validate_events

        _run_step(
            11,
            "semantics(validate_events)",
            handle_validate_events,
            {},
            project_path,
        )
    except ImportError:
        steps.append(
            {
                "step": 11,
                "operation": "semantics(validate_events)",
                "status": "skipped",
                "reason": "event_first_tools not available",
            }
        )

    # -----------------------------------------------------------------------
    # Optional Step 12: Run all tests (only if base_url provided)
    # -----------------------------------------------------------------------
    if base_url:
        from .preflight import check_server_reachable

        preflight_err = check_server_reachable(base_url)
        if preflight_err:
            steps.append(
                {
                    "step": 12,
                    "operation": "dsl_test(run_all)",
                    "status": "error",
                    "error": json.loads(preflight_err).get("error", "Server not reachable"),
                    "duration_ms": 0,
                }
            )
            errors.append(f"dsl_test(run_all): Server not reachable at {base_url}")
        else:
            from .dsl_test import run_all_dsl_tests_handler

            _run_step(
                12,
                "dsl_test(run_all)",
                run_all_dsl_tests_handler,
                project_path,
                {"base_url": base_url},
            )

    return _build_pipeline_response(steps, errors, pipeline_start, detail=detail)


# ---------------------------------------------------------------------------
# Metrics extractors — one per pipeline operation
# ---------------------------------------------------------------------------


def _extract_validate_metrics(data: dict[str, Any]) -> dict[str, Any]:
    """Extract key metrics from dsl(validate) result."""
    return {
        "status": data.get("status", "unknown"),
        "modules": data.get("module_count", data.get("modules", 0)),
        "entities": data.get("entity_count", data.get("entities", 0)),
        "surfaces": data.get("surface_count", data.get("surfaces", 0)),
    }


def _extract_lint_metrics(data: dict[str, Any]) -> dict[str, Any]:
    """Extract key metrics from dsl(lint) result."""
    errs = data.get("errors", [])
    warns = data.get("warnings", [])
    return {
        "errors": len(errs) if isinstance(errs, list) else errs,
        "warnings": len(warns) if isinstance(warns, list) else warns,
    }


def _extract_fidelity_metrics(data: dict[str, Any]) -> dict[str, Any]:
    """Extract key metrics from dsl(fidelity) result."""
    surfaces = data.get("surfaces", [])
    return {
        "overall_fidelity": data.get("overall_fidelity"),
        "total_gaps": data.get("total_gaps", 0),
        "story_coverage": data.get("story_coverage"),
        "surfaces_with_gaps": len(surfaces),
    }


def _extract_composition_audit_metrics(data: dict[str, Any]) -> dict[str, Any]:
    """Extract key metrics from composition(audit) result."""
    pages = data.get("pages", [])
    total_violations: dict[str, int] = {}
    for page in pages if isinstance(pages, list) else []:
        if not isinstance(page, dict):
            continue
        for sev, count in page.get("violations_count", {}).items():
            total_violations[sev] = total_violations.get(sev, 0) + count
    return {
        "overall_score": data.get("overall_score", 100),
        "pages_audited": len(pages) if isinstance(pages, list) else 0,
        "violations": total_violations,
    }


def _extract_test_generate_metrics(data: dict[str, Any]) -> dict[str, Any]:
    """Extract key metrics from dsl_test(generate) result."""
    tests = data.get("tests", [])
    categories: dict[str, int] = {}
    for t in tests if isinstance(tests, list) else []:
        cat = t.get("category", "unknown") if isinstance(t, dict) else "unknown"
        categories[cat] = categories.get(cat, 0) + 1
    return {
        "total_tests": data.get("total_tests", len(tests) if isinstance(tests, list) else 0),
        "categories": categories or data.get("categories", {}),
    }


def _extract_test_coverage_metrics(data: dict[str, Any]) -> dict[str, Any]:
    """Extract key metrics from dsl_test(coverage) result."""
    return {
        "overall_coverage": data.get("overall_coverage", data.get("coverage")),
        "total_constructs": data.get("total_constructs", 0),
        "tested_constructs": data.get("tested_constructs", 0),
    }


def _extract_story_coverage_metrics(data: dict[str, Any]) -> dict[str, Any]:
    """Extract key metrics from story(coverage) or process(coverage) result."""
    metrics: dict[str, Any] = {
        "total_stories": data.get("total_stories", data.get("total", 0)),
        "covered": data.get("covered", 0),
        "partial": data.get("partial", 0),
        "uncovered": data.get("uncovered", 0),
        "coverage_percent": data.get("coverage_percent", data.get("coverage", 0)),
    }
    # Include effective coverage when available (accounts for irreducible partials)
    eff = data.get("effective_coverage_percent")
    if eff is not None:
        metrics["effective_coverage_percent"] = eff
    return metrics


def _extract_test_design_gaps_metrics(data: dict[str, Any]) -> dict[str, Any]:
    """Extract key metrics from test_design(gaps) result."""
    gaps = data.get("gaps", [])
    by_severity: dict[str, int] = {}
    for g in gaps if isinstance(gaps, list) else []:
        sev = g.get("severity", "unknown") if isinstance(g, dict) else "unknown"
        by_severity[sev] = by_severity.get(sev, 0) + 1
    return {
        "coverage_score": data.get("coverage_score", data.get("coverage")),
        "gap_count": len(gaps) if isinstance(gaps, list) else data.get("gap_count", 0),
        "gaps_by_severity": by_severity,
    }


def _extract_semantics_extract_metrics(data: dict[str, Any]) -> dict[str, Any]:
    """Extract key metrics from semantics(extract) result."""
    return {
        "entity_count": data.get("entity_count", len(data.get("entities", []))),
        "command_count": data.get("command_count", len(data.get("commands", []))),
        "event_count": data.get("event_count", len(data.get("events", []))),
        "tenancy_signal_count": data.get(
            "tenancy_signal_count", len(data.get("tenancy_signals", []))
        ),
        "compliance_signal_count": data.get(
            "compliance_signal_count", len(data.get("compliance_signals", []))
        ),
    }


def _extract_semantics_validate_metrics(data: dict[str, Any]) -> dict[str, Any]:
    """Extract key metrics from semantics(validate_events) result."""
    return {
        "valid": data.get("valid", data.get("status") == "valid"),
        "error_count": data.get("error_count", len(data.get("errors", []))),
        "warning_count": data.get("warning_count", len(data.get("warnings", []))),
    }


def _extract_run_all_metrics(data: dict[str, Any]) -> dict[str, Any]:
    """Extract key metrics from dsl_test(run_all) result."""
    results = data.get("results", [])
    by_cat: dict[str, dict[str, int]] = {}
    for r in results if isinstance(results, list) else []:
        if not isinstance(r, dict):
            continue
        cat = r.get("category", "unknown")
        if cat not in by_cat:
            by_cat[cat] = {"passed": 0, "failed": 0}
        if r.get("status") == "passed" or r.get("passed"):
            by_cat[cat]["passed"] += 1
        else:
            by_cat[cat]["failed"] += 1
    return {
        "total": data.get("total", len(results) if isinstance(results, list) else 0),
        "passed": data.get("passed", 0),
        "failed": data.get("failed", 0),
        "by_category": by_cat,
    }


_METRICS_EXTRACTORS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "dsl(validate)": _extract_validate_metrics,
    "dsl(lint)": _extract_lint_metrics,
    "dsl(fidelity)": _extract_fidelity_metrics,
    "composition(audit)": _extract_composition_audit_metrics,
    "dsl_test(generate)": _extract_test_generate_metrics,
    "dsl_test(coverage)": _extract_test_coverage_metrics,
    "story(coverage)": _extract_story_coverage_metrics,
    "process(coverage)": _extract_story_coverage_metrics,
    "test_design(gaps)": _extract_test_design_gaps_metrics,
    "semantics(extract)": _extract_semantics_extract_metrics,
    "semantics(validate_events)": _extract_semantics_validate_metrics,
    "dsl_test(run_all)": _extract_run_all_metrics,
}


def _extract_step_metrics(operation: str, data: Any) -> dict[str, Any]:
    """Extract compact metrics from a step result.

    Returns an empty dict for unknown operations or non-dict data.
    """
    if not isinstance(data, dict):
        return {}
    extractor = _METRICS_EXTRACTORS.get(operation)
    if extractor is None:
        return {}
    try:
        return extractor(data)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Top issues collector
# ---------------------------------------------------------------------------


def _collect_top_issues(
    steps: list[dict[str, Any]],
    max_issues: int = 5,
) -> list[dict[str, Any]]:
    """Scan full step results for actionable issues, return top N by severity.

    Sources:
    - lint errors/warnings
    - fidelity recommendations
    - test failures
    - test design gaps
    """
    severity_rank = {"critical": 0, "major": 1, "error": 1, "minor": 2, "warning": 3, "info": 4}
    issues: list[dict[str, Any]] = []

    for step in steps:
        result = step.get("result")
        if not isinstance(result, dict):
            continue
        op = step.get("operation", "")

        # Lint errors
        if op == "dsl(lint)":
            for err in result.get("errors", []) if isinstance(result.get("errors"), list) else []:
                issues.append(
                    {
                        "source": "lint",
                        "severity": "error",
                        "message": err if isinstance(err, str) else str(err),
                    }
                )
            for warn in (
                result.get("warnings", []) if isinstance(result.get("warnings"), list) else []
            ):
                issues.append(
                    {
                        "source": "lint",
                        "severity": "warning",
                        "message": warn if isinstance(warn, str) else str(warn),
                    }
                )

        # Composition audit violations
        if op == "composition(audit)":
            for page in result.get("pages", []) if isinstance(result.get("pages"), list) else []:
                if not isinstance(page, dict):
                    continue
                route = page.get("route", "/")
                # Page-level violations
                for v in (
                    page.get("page_violations", [])
                    if isinstance(page.get("page_violations"), list)
                    else []
                ):
                    if isinstance(v, dict):
                        issues.append(
                            {
                                "source": "composition",
                                "severity": v.get("severity", "minor"),
                                "message": f"{route}: {v.get('message', str(v))}",
                            }
                        )
                # Section-level violations
                for sec in (
                    page.get("sections", []) if isinstance(page.get("sections"), list) else []
                ):
                    if not isinstance(sec, dict):
                        continue
                    for v in (
                        sec.get("violations", []) if isinstance(sec.get("violations"), list) else []
                    ):
                        if isinstance(v, dict):
                            issues.append(
                                {
                                    "source": "composition",
                                    "severity": v.get("severity", "minor"),
                                    "message": f"{route}: {v.get('message', str(v))}",
                                }
                            )

        # Fidelity recommendations
        if op == "dsl(fidelity)":
            for rec in result.get("top_recommendations", []):
                if isinstance(rec, dict):
                    issues.append(
                        {
                            "source": "fidelity",
                            "severity": rec.get("severity", "minor"),
                            "message": rec.get("recommendation", str(rec)),
                        }
                    )

        # Test failures
        if op == "dsl_test(run_all)":
            for r in result.get("results", []) if isinstance(result.get("results"), list) else []:
                if isinstance(r, dict) and (r.get("status") == "failed" or r.get("failed")):
                    issues.append(
                        {
                            "source": "test_failure",
                            "severity": "error",
                            "message": r.get("error", r.get("name", str(r))),
                        }
                    )

        # Test design gaps
        if op == "test_design(gaps)":
            for gap in result.get("gaps", []) if isinstance(result.get("gaps"), list) else []:
                if isinstance(gap, dict):
                    issues.append(
                        {
                            "source": "test_design",
                            "severity": gap.get("severity", "minor"),
                            "message": gap.get("description", gap.get("gap", str(gap))),
                        }
                    )

    # Sort by severity rank, then truncate
    issues.sort(key=lambda i: severity_rank.get(i.get("severity", "info"), 5))
    return issues[:max_issues]


# ---------------------------------------------------------------------------
# Issue detection — used by 'issues' detail level
# ---------------------------------------------------------------------------


def _step_has_issues(operation: str, result: Any) -> bool:
    """Check whether a step result contains actionable issues.

    Used by the 'issues' detail level to decide which steps get full expansion.
    """
    if not isinstance(result, dict):
        return False

    # Lint: expand only for errors (warnings are stable baseline noise)
    if operation == "dsl(lint)":
        errs = result.get("errors", [])
        return bool(errs)

    # Fidelity: any gaps
    if operation == "dsl(fidelity)":
        total_gaps: int = result.get("total_gaps", 0) or 0
        return total_gaps > 0

    # Composition audit: score < 100
    if operation == "composition(audit)":
        score: int = result.get("overall_score", 100) or 100
        return score < 100

    # Test coverage: below 100%
    if operation in ("dsl_test(coverage)", "story(coverage)", "process(coverage)"):
        cov: float | str = result.get("coverage_percent") or result.get("coverage") or 100
        if isinstance(cov, str):
            try:
                cov = float(cov.rstrip("%"))
            except (ValueError, AttributeError):
                return False
        if cov is None:
            return False
        return float(cov) < 100

    # Test design gaps: any gaps
    if operation == "test_design(gaps)":
        gaps = result.get("gaps", [])
        return len(gaps) > 0

    # Test run: any failures
    if operation == "dsl_test(run_all)":
        failed: int = result.get("failed", 0) or 0
        return failed > 0

    # Semantics validate: any errors or warnings
    if operation == "semantics(validate_events)":
        err_count: int = result.get("error_count", 0) or 0
        warn_count: int = result.get("warning_count", 0) or 0
        return err_count > 0 or warn_count > 0

    return False


# ---------------------------------------------------------------------------
# Result filtering — trim expanded results for 'issues' mode
# ---------------------------------------------------------------------------


def _filter_issues_result(operation: str, result: Any) -> Any:
    """Trim expanded step results to only the actionable parts.

    Called in 'issues' mode before attaching a full result to the response.
    Reduces token waste by stripping large, repetitive, or redundant fields.
    """
    if not isinstance(result, dict):
        return result

    # Story/process coverage: keep only partial/uncovered stories
    if operation in ("story(coverage)", "process(coverage)"):
        stories = result.get("stories", [])
        if isinstance(stories, list):
            filtered = [
                s
                for s in stories
                if isinstance(s, dict) and s.get("status") in ("partial", "uncovered")
            ]
            result = {**result, "stories": filtered}
            # Drop pagination fields that no longer apply
            result.pop("showing", None)
            result.pop("offset", None)
            result.pop("has_more", None)
            result.pop("guidance", None)
        return result

    # Composition audit: strip markdown (duplicates structured JSON)
    if operation == "composition(audit)":
        result = {k: v for k, v in result.items() if k != "markdown"}
        return result

    return result


# ---------------------------------------------------------------------------
# Response builder
# ---------------------------------------------------------------------------


def _build_pipeline_response(
    steps: list[dict[str, Any]],
    errors: list[str],
    start_time: float,
    *,
    detail: str = "issues",
) -> str:
    """Build the final pipeline response JSON.

    Detail levels:
    - ``"metrics"``: compact stats per step + top_issues (~1KB)
    - ``"issues"``: metrics for clean steps, full results for steps with issues (~5-20KB)
    - ``"full"``: complete results for every step (~200KB+)
    """
    total_ms = (time.monotonic() - start_time) * 1000

    passed = sum(1 for s in steps if s.get("status") == "passed")
    failed = sum(1 for s in steps if s.get("status") == "error")
    skipped = sum(1 for s in steps if s.get("status") == "skipped")

    status = "passed" if failed == 0 else "failed"

    if detail == "full":
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
    else:
        # Both "metrics" and "issues" use summarized steps
        summarized_steps: list[dict[str, Any]] = []
        for step in steps:
            compact: dict[str, Any] = {
                "step": step.get("step"),
                "operation": step.get("operation"),
                "status": step.get("status"),
                "duration_ms": step.get("duration_ms"),
            }
            if step.get("status") == "error":
                compact["error"] = step.get("error")
            elif step.get("status") == "skipped":
                compact["reason"] = step.get("reason")
            else:
                op = step.get("operation", "")
                result_data = step.get("result")

                # "issues" mode: expand steps that have problems
                if detail == "issues" and _step_has_issues(op, result_data):
                    compact["result"] = _filter_issues_result(op, result_data)
                else:
                    metrics = _extract_step_metrics(op, result_data)
                    if metrics:
                        compact["metrics"] = metrics

            summarized_steps.append(compact)

        top_issues = _collect_top_issues(steps)

        response = {
            "status": status,
            "total_duration_ms": round(total_ms, 1),
            "summary": {
                "total_steps": len(steps),
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
            },
            "steps": summarized_steps,
            "top_issues": top_issues,
        }

    if errors:
        response["errors"] = errors

    # _meta block
    response["_meta"] = {
        "wall_time_ms": round(total_ms, 1),
        "steps_executed": len(steps),
        "detail_level": detail,
    }

    return json.dumps(response, indent=2)
