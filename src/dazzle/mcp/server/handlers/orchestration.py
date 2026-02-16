"""
Shared quality pipeline orchestration infrastructure.

Provides the common step execution, result aggregation, and detail-level
filtering used by both ``pipeline`` (sequential) and ``nightly`` (parallel).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("dazzle.mcp.handlers.orchestration")


# ---------------------------------------------------------------------------
# Step dataclass
# ---------------------------------------------------------------------------


@dataclass
class QualityStep:
    """A single step in a quality pipeline run."""

    name: str
    handler: Any  # callable
    handler_args: tuple[Any, ...] = ()
    handler_kwargs: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    optional: bool = False


# ---------------------------------------------------------------------------
# Step execution
# ---------------------------------------------------------------------------


def run_step(
    step: QualityStep,
    *,
    activity_store: Any | None = None,
    activity_prefix: str = "",
) -> dict[str, Any]:
    """Execute a single quality step and return a structured result dict.

    Args:
        step: The step to execute.
        activity_store: Optional activity store for logging start/end events.
        activity_prefix: Prefix for activity event names (e.g. "nightly:").

    Returns:
        dict with keys: operation, status, duration_ms, and either result or error.
    """
    namespaced = f"{activity_prefix}{step.name}" if activity_prefix else step.name

    if activity_store is not None:
        try:
            activity_store.log_event("tool_start", namespaced, None, source="cli")
        except Exception:
            logger.debug("Failed to log step start", exc_info=True)

    t0 = time.monotonic()
    result: dict[str, Any] = {"operation": step.name}
    ok = True
    error_msg: str | None = None

    try:
        raw = step.handler(*step.handler_args, **step.handler_kwargs)
        duration_ms = (time.monotonic() - t0) * 1000
        result["duration_ms"] = round(duration_ms, 1)

        try:
            data = json.loads(raw)
            if "error" in data:
                result["status"] = "error"
                result["error"] = data["error"]
                ok = False
                error_msg = data["error"]
            else:
                result["status"] = "passed"
                result["result"] = data
        except (json.JSONDecodeError, TypeError):
            result["status"] = "passed"
            result["result"] = str(raw)[:500]

    except Exception as e:
        duration_ms = (time.monotonic() - t0) * 1000
        result["duration_ms"] = round(duration_ms, 1)
        result["status"] = "error"
        result["error"] = str(e)
        ok = False
        error_msg = str(e)
        logger.warning("Quality step %s failed: %s", step.name, e)

    if activity_store is not None:
        try:
            activity_store.log_event(
                "tool_end",
                namespaced,
                None,
                success=ok,
                duration_ms=result.get("duration_ms", 0),
                error=error_msg,
                source="cli",
            )
        except Exception:
            logger.debug("Failed to log step end", exc_info=True)

    return result


def run_steps_sequential(
    steps: list[QualityStep],
    *,
    stop_on_error: bool = False,
    progress: Any | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Run quality steps sequentially, collecting results and errors.

    Args:
        steps: Ordered list of steps to execute.
        stop_on_error: If True, stop after the first error.
        progress: Optional progress reporter with advance_sync(step, total, name).

    Returns:
        (step_results, error_messages)
    """
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    total = len(steps)

    for idx, step in enumerate(steps, 1):
        if progress is not None:
            progress.advance_sync(idx, total, step.name)

        step_result = run_step(step)
        step_result["step"] = idx
        results.append(step_result)

        if step_result["status"] == "error":
            errors.append(f"{step.name}: {step_result.get('error', 'unknown')}")
            if stop_on_error:
                break

    return results, errors


# ---------------------------------------------------------------------------
# Metrics extractors — one per pipeline operation
# ---------------------------------------------------------------------------


def _extract_validate_metrics(step_output: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": step_output.get("status", "unknown"),
        "modules": step_output.get("module_count", step_output.get("modules", 0)),
        "entities": step_output.get("entity_count", step_output.get("entities", 0)),
        "surfaces": step_output.get("surface_count", step_output.get("surfaces", 0)),
    }


def _extract_lint_metrics(step_output: dict[str, Any]) -> dict[str, Any]:
    errs = step_output.get("errors", [])
    warns = step_output.get("warnings", [])
    return {
        "errors": len(errs) if isinstance(errs, list) else errs,
        "warnings": len(warns) if isinstance(warns, list) else warns,
    }


def _extract_fidelity_metrics(step_output: dict[str, Any]) -> dict[str, Any]:
    surfaces = step_output.get("surfaces", [])
    return {
        "overall_fidelity": step_output.get("overall_fidelity"),
        "total_gaps": step_output.get("total_gaps", 0),
        "story_coverage": step_output.get("story_coverage"),
        "surfaces_with_gaps": len(surfaces),
    }


def _extract_composition_audit_metrics(step_output: dict[str, Any]) -> dict[str, Any]:
    pages = step_output.get("pages", [])
    total_violations: dict[str, int] = {}
    for page in pages if isinstance(pages, list) else []:
        if not isinstance(page, dict):
            continue
        for sev, count in page.get("violations_count", {}).items():
            total_violations[sev] = total_violations.get(sev, 0) + count
    return {
        "overall_score": step_output.get("overall_score", 100),
        "pages_audited": len(pages) if isinstance(pages, list) else 0,
        "violations": total_violations,
    }


def _extract_test_generate_metrics(step_output: dict[str, Any]) -> dict[str, Any]:
    tests = step_output.get("tests", [])
    categories: dict[str, int] = {}
    for t in tests if isinstance(tests, list) else []:
        cat = t.get("category", "unknown") if isinstance(t, dict) else "unknown"
        categories[cat] = categories.get(cat, 0) + 1
    return {
        "total_tests": step_output.get("total_tests", len(tests) if isinstance(tests, list) else 0),
        "categories": categories or step_output.get("categories", {}),
    }


def _extract_test_coverage_metrics(step_output: dict[str, Any]) -> dict[str, Any]:
    return {
        "overall_coverage": step_output.get("overall_coverage", step_output.get("coverage")),
        "total_constructs": step_output.get("total_constructs", 0),
        "tested_constructs": step_output.get("tested_constructs", 0),
    }


def _extract_story_coverage_metrics(step_output: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "total_stories": step_output.get("total_stories", step_output.get("total", 0)),
        "covered": step_output.get("covered", 0),
        "partial": step_output.get("partial", 0),
        "uncovered": step_output.get("uncovered", 0),
        "coverage_percent": step_output.get("coverage_percent", step_output.get("coverage", 0)),
    }
    eff = step_output.get("effective_coverage_percent")
    if eff is not None:
        metrics["effective_coverage_percent"] = eff
    return metrics


def _extract_test_design_gaps_metrics(step_output: dict[str, Any]) -> dict[str, Any]:
    gaps = step_output.get("gaps", [])
    by_severity: dict[str, int] = {}
    for g in gaps if isinstance(gaps, list) else []:
        sev = g.get("severity", "unknown") if isinstance(g, dict) else "unknown"
        by_severity[sev] = by_severity.get(sev, 0) + 1
    return {
        "coverage_score": step_output.get("coverage_score", step_output.get("coverage")),
        "gap_count": len(gaps) if isinstance(gaps, list) else step_output.get("gap_count", 0),
        "gaps_by_severity": by_severity,
    }


def _extract_semantics_extract_metrics(step_output: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_count": step_output.get("entity_count", len(step_output.get("entities", []))),
        "command_count": step_output.get("command_count", len(step_output.get("commands", []))),
        "event_count": step_output.get("event_count", len(step_output.get("events", []))),
        "tenancy_signal_count": step_output.get(
            "tenancy_signal_count", len(step_output.get("tenancy_signals", []))
        ),
        "compliance_signal_count": step_output.get(
            "compliance_signal_count", len(step_output.get("compliance_signals", []))
        ),
    }


def _extract_semantics_validate_metrics(step_output: dict[str, Any]) -> dict[str, Any]:
    return {
        "valid": step_output.get("valid", step_output.get("status") == "valid"),
        "error_count": step_output.get("error_count", len(step_output.get("errors", []))),
        "warning_count": step_output.get("warning_count", len(step_output.get("warnings", []))),
    }


def _extract_run_all_metrics(step_output: dict[str, Any]) -> dict[str, Any]:
    results = step_output.get("results", [])
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
        "total": step_output.get("total", len(results) if isinstance(results, list) else 0),
        "passed": step_output.get("passed", 0),
        "failed": step_output.get("failed", 0),
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


def extract_step_metrics(operation: str, data: Any) -> dict[str, Any]:
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


def collect_top_issues(
    steps: list[dict[str, Any]],
    max_issues: int = 5,
) -> list[dict[str, Any]]:
    """Scan full step results for actionable issues, return top N by severity."""
    severity_rank = {"critical": 0, "major": 1, "error": 1, "minor": 2, "warning": 3, "info": 4}
    issues: list[dict[str, Any]] = []

    for step in steps:
        result = step.get("result")
        if not isinstance(result, dict):
            continue
        op = step.get("operation", "")

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

        if op == "composition(audit)":
            for page in result.get("pages", []) if isinstance(result.get("pages"), list) else []:
                if not isinstance(page, dict):
                    continue
                route = page.get("route", "/")
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

    issues.sort(key=lambda i: severity_rank.get(i.get("severity", "info"), 5))
    return issues[:max_issues]


# ---------------------------------------------------------------------------
# Issue detection — used by 'issues' detail level
# ---------------------------------------------------------------------------


def step_has_issues(operation: str, step_result: Any) -> bool:
    """Check whether a step result contains actionable issues."""
    if not isinstance(step_result, dict):
        return False

    if operation == "dsl(lint)":
        errs = step_result.get("errors", [])
        return bool(errs)

    if operation == "dsl(fidelity)":
        total_gaps: int = step_result.get("total_gaps", 0) or 0
        return total_gaps > 0

    if operation == "composition(audit)":
        score: int = step_result.get("overall_score", 100) or 100
        return score < 100

    if operation in ("dsl_test(coverage)", "story(coverage)", "process(coverage)"):
        cov: float | str = step_result.get("coverage_percent") or step_result.get("coverage") or 100
        if isinstance(cov, str):
            try:
                cov = float(cov.rstrip("%"))
            except (ValueError, AttributeError):
                return False
        if cov is None:
            return False
        return float(cov) < 100

    if operation == "test_design(gaps)":
        gaps = step_result.get("gaps", [])
        return len(gaps) > 0

    if operation == "dsl_test(run_all)":
        failed: int = step_result.get("failed", 0) or 0
        return failed > 0

    if operation == "semantics(validate_events)":
        err_count: int = step_result.get("error_count", 0) or 0
        warn_count: int = step_result.get("warning_count", 0) or 0
        return err_count > 0 or warn_count > 0

    return False


# ---------------------------------------------------------------------------
# Result filtering — trim expanded results for 'issues' mode
# ---------------------------------------------------------------------------


def filter_issues_result(operation: str, step_result: Any) -> Any:
    """Trim expanded step results to only the actionable parts."""
    if not isinstance(step_result, dict):
        return step_result

    if operation in ("story(coverage)", "process(coverage)"):
        stories = step_result.get("stories", [])
        if isinstance(stories, list):
            filtered = [
                s
                for s in stories
                if isinstance(s, dict) and s.get("status") in ("partial", "uncovered")
            ]
            step_result = {**step_result, "stories": filtered}
            step_result.pop("showing", None)
            step_result.pop("offset", None)
            step_result.pop("has_more", None)
            step_result.pop("guidance", None)
        return step_result

    if operation == "composition(audit)":
        step_result = {k: v for k, v in step_result.items() if k != "markdown"}
        return step_result

    return step_result


# ---------------------------------------------------------------------------
# Result aggregation and response building
# ---------------------------------------------------------------------------


def aggregate_results(
    steps: list[dict[str, Any]],
    errors: list[str],
    start_time: float,
    *,
    detail: str = "issues",
) -> str:
    """Build the final pipeline/nightly response JSON.

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

                if detail == "issues" and step_has_issues(op, result_data):
                    compact["result"] = filter_issues_result(op, result_data)
                else:
                    metrics = extract_step_metrics(op, result_data)
                    if metrics:
                        compact["metrics"] = metrics

            summarized_steps.append(compact)

        top_issues = collect_top_issues(steps)

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

    response["_meta"] = {
        "wall_time_ms": round(total_ms, 1),
        "steps_executed": len(steps),
        "detail_level": detail,
    }

    return json.dumps(response, indent=2)
