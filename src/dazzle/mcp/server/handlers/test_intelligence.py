"""Test intelligence handlers — query persisted test history.

Provides 5 operations:
- summary: recent runs overview
- failures: failure patterns, flaky tests, persistent failures
- regression: tests that regressed (pass→fail) between last two runs
- coverage: trend across recent runs
- context: single-call AI-ready snapshot combining all above
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .common import wrap_handler_errors

logger = logging.getLogger("dazzle.mcp")


def _get_graph() -> Any:
    """Get the knowledge graph, or None."""
    from ..state import get_knowledge_graph

    return get_knowledge_graph()


def _project_name_from_root(project_root: Path) -> str:
    """Derive project name from project root."""
    try:
        from dazzle.core.manifest import load_manifest

        manifest = load_manifest(project_root / "dazzle.toml")
        return manifest.name or project_root.name
    except Exception:
        return project_root.name


@wrap_handler_errors
def test_summary_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Recent runs overview."""
    graph = _get_graph()
    if graph is None:
        return json.dumps({"error": "Knowledge graph not initialized"})

    project_name = _project_name_from_root(project_root)
    limit = args.get("limit", 10)
    runs = graph.get_test_runs(project_name=project_name, limit=limit)

    summary = []
    for run in runs:
        summary.append(
            {
                "run_id": run["id"],
                "started_at": run["started_at"],
                "dsl_hash": run["dsl_hash"],
                "total": run["total_tests"],
                "passed": run["passed"],
                "failed": run["failed"],
                "success_rate": run["success_rate"],
                "trigger": run.get("trigger", "manual"),
            }
        )

    return json.dumps(
        {
            "project": project_name,
            "runs": summary,
            "total_runs": len(summary),
        },
        indent=2,
    )


@wrap_handler_errors
def test_failures_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Failure patterns across recent runs."""
    graph = _get_graph()
    if graph is None:
        return json.dumps({"error": "Knowledge graph not initialized"})

    project_name = _project_name_from_root(project_root)
    limit_runs = args.get("limit", 10)
    failure_type = args.get("failure_type")
    category = args.get("category")

    summary = graph.get_failure_summary(limit_runs=limit_runs, project_name=project_name)

    # Optionally filter
    result: dict[str, Any] = {"project": project_name}

    if failure_type:
        filtered = {k: v for k, v in summary["by_failure_type"].items() if k == failure_type}
        result["by_failure_type"] = filtered
    else:
        result["by_failure_type"] = summary["by_failure_type"]

    if category:
        filtered_cat = {k: v for k, v in summary["by_category"].items() if k == category}
        result["by_category"] = filtered_cat
    else:
        result["by_category"] = summary["by_category"]

    result["flaky_tests"] = summary["flaky_tests"]
    result["persistent_failures"] = summary["persistent_failures"]
    result["runs_analyzed"] = summary["runs_analyzed"]

    return json.dumps(result, indent=2)


@wrap_handler_errors
def test_regression_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Detect regressions between two most recent runs."""
    graph = _get_graph()
    if graph is None:
        return json.dumps({"error": "Knowledge graph not initialized"})

    project_name = _project_name_from_root(project_root)
    result = graph.detect_regressions(project_name=project_name)
    result["project"] = project_name

    return json.dumps(result, indent=2)


@wrap_handler_errors
def test_coverage_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Coverage trend across recent runs."""
    graph = _get_graph()
    if graph is None:
        return json.dumps({"error": "Knowledge graph not initialized"})

    project_name = _project_name_from_root(project_root)
    limit_runs = args.get("limit", 10)
    trend = graph.get_test_coverage_trend(project_name=project_name, limit_runs=limit_runs)

    return json.dumps(
        {"project": project_name, "trend": trend, "runs": len(trend)},
        indent=2,
    )


@wrap_handler_errors
def test_context_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Single-call AI-ready snapshot combining all test intelligence."""
    graph = _get_graph()
    if graph is None:
        return json.dumps({"error": "Knowledge graph not initialized"})

    project_name = _project_name_from_root(project_root)
    limit = args.get("limit", 5)

    runs = graph.get_test_runs(project_name=project_name, limit=limit)
    failures = graph.get_failure_summary(limit_runs=limit, project_name=project_name)
    regressions = graph.detect_regressions(project_name=project_name)
    trend = graph.get_test_coverage_trend(project_name=project_name, limit_runs=limit)

    # Build compact context
    context: dict[str, Any] = {
        "project": project_name,
        "latest_run": None,
        "runs_total": len(runs),
        "failure_patterns": {
            "by_type": failures["by_failure_type"],
            "by_category": failures["by_category"],
            "flaky_count": len(failures["flaky_tests"]),
            "persistent_count": len(failures["persistent_failures"]),
        },
        "regressions": regressions.get("regressions", []),
        "trend": trend,
    }

    if runs:
        latest = runs[0]
        context["latest_run"] = {
            "run_id": latest["id"],
            "started_at": latest["started_at"],
            "total": latest["total_tests"],
            "passed": latest["passed"],
            "failed": latest["failed"],
            "success_rate": latest["success_rate"],
            "dsl_hash": latest["dsl_hash"],
        }

    # If there are persistent failures, include them for actionability
    if failures["persistent_failures"]:
        context["persistent_failures"] = failures["persistent_failures"][:10]

    if failures["flaky_tests"]:
        context["flaky_tests"] = failures["flaky_tests"][:10]

    return json.dumps(context, indent=2)
