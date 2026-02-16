"""
MCP Server handlers for E2E testing.

Provides tools for LLM agents to run and analyze E2E tests.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from ..state import get_active_project_path, get_project_root
from .common import async_handler_error_json, extract_progress, handler_error_json

logger = logging.getLogger("dazzle.mcp.testing")


def check_test_infrastructure_handler() -> str:
    """
    Check test infrastructure requirements.

    Returns status of required dependencies and install instructions.
    Use this BEFORE running E2E tests to ensure all dependencies are set up.

    Returns:
        JSON with infrastructure status and setup instructions
    """
    progress = extract_progress(None)
    progress.log_sync("Checking test infrastructure...")
    result: dict[str, Any] = {
        "ready": True,
        "components": {},
        "setup_instructions": [],
    }

    # Check Python availability
    result["components"]["python"] = {
        "installed": True,
        "version": None,
    }
    try:
        import sys

        result["components"]["python"]["version"] = (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        )
    except Exception:
        logger.debug("Failed to get Python version", exc_info=True)

    # Check Playwright
    playwright_installed = False
    playwright_browsers = False
    try:
        import playwright

        playwright_installed = True
        result["components"]["playwright"] = {
            "installed": True,
            "version": getattr(playwright, "__version__", "unknown"),
        }

        # Check if browsers are installed
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser_path = p.chromium.executable_path
                if Path(browser_path).exists():
                    playwright_browsers = True
        except Exception:
            logger.debug("Playwright browsers not available", exc_info=True)

        result["components"]["playwright"]["browsers_installed"] = playwright_browsers
    except ImportError:
        playwright_installed = False
        result["components"]["playwright"] = {
            "installed": False,
            "browsers_installed": False,
        }

    if not playwright_installed:
        result["ready"] = False
        result["setup_instructions"].append(
            {
                "step": 1,
                "description": "Install Playwright Python package",
                "command": "pip install playwright",
            }
        )
        result["setup_instructions"].append(
            {
                "step": 2,
                "description": "Install Chromium browser for Playwright",
                "command": "playwright install chromium",
            }
        )
    elif not playwright_browsers:
        result["ready"] = False
        result["setup_instructions"].append(
            {
                "step": 1,
                "description": "Install Chromium browser for Playwright",
                "command": "playwright install chromium",
            }
        )

    # Check httpx (needed for API tests)
    try:
        import httpx

        result["components"]["httpx"] = {
            "installed": True,
            "version": httpx.__version__,
        }
    except ImportError:
        result["components"]["httpx"] = {"installed": False}
        result["ready"] = False
        result["setup_instructions"].append(
            {
                "step": len(result["setup_instructions"]) + 1,
                "description": "Install httpx for API testing",
                "command": "pip install httpx",
            }
        )

    # Check uvicorn (needed for server)
    uvicorn_installed = shutil.which("uvicorn") is not None
    try:
        import uvicorn

        uvicorn_installed = True
        result["components"]["uvicorn"] = {
            "installed": True,
            "version": getattr(uvicorn, "__version__", "unknown"),
        }
    except ImportError:
        result["components"]["uvicorn"] = {"installed": False}
        if not uvicorn_installed:
            result["setup_instructions"].append(
                {
                    "step": len(result["setup_instructions"]) + 1,
                    "description": "Install uvicorn for running the test server",
                    "command": "pip install uvicorn",
                }
            )

    # Add summary
    if result["ready"]:
        result["message"] = "All test infrastructure is ready. You can run E2E tests."
    else:
        result["message"] = (
            "Test infrastructure is incomplete. "
            "Follow the setup_instructions to install missing components."
        )

    return json.dumps(result, indent=2)


@handler_error_json
def run_e2e_tests_handler(
    project_path: str | None = None,
    priority: str | None = None,
    tag: str | None = None,
    headless: bool = True,
) -> str:
    """
    Run E2E tests for the project.

    This handler starts the DNR server, runs Playwright-based E2E tests,
    and returns the results.

    Args:
        project_path: Optional path to project (uses active project if not specified)
        priority: Filter by priority (high, medium, low)
        tag: Filter by tag
        headless: Run browser in headless mode (default: True)

    Returns:
        JSON string with test results
    """
    progress = extract_progress(None)
    progress.log_sync("Running E2E tests...")
    # Resolve project path
    root: Path
    if project_path:
        root = Path(project_path)
    else:
        active = get_active_project_path()
        if active:
            root = active
        else:
            project = get_project_root()
            if project:
                root = project
            else:
                return json.dumps(
                    {
                        "error": "No project path specified and no active project set",
                        "status": "error",
                    }
                )

    # Import E2E runner
    from dazzle.testing.e2e_runner import E2ERunner, E2ERunOptions

    runner = E2ERunner(root)

    # Check Playwright
    playwright_ok, playwright_msg = runner.ensure_playwright()
    if not playwright_ok:
        return json.dumps(
            {
                "error": playwright_msg,
                "status": "error",
                "hint": "pip install playwright && playwright install chromium",
            }
        )

    # Run tests
    options = E2ERunOptions(
        headless=headless,
        priority=priority,
        tag=tag,
    )

    result = runner.run_all(options)

    # Format response
    if result.error:
        return json.dumps(
            {
                "status": "error",
                "error": result.error,
                "project": result.project_name,
            }
        )

    failures = [
        {"flow_id": f.flow_id, "error": f.error} for f in result.flows if f.status == "failed"
    ]

    return json.dumps(
        {
            "status": "passed" if result.failed == 0 else "failed",
            "project": result.project_name,
            "total": result.total,
            "passed": result.passed,
            "failed": result.failed,
            "success_rate": result.success_rate,
            "failures": failures,
            "duration_seconds": (result.completed_at - result.started_at).total_seconds()
            if result.completed_at
            else None,
        },
        indent=2,
    )


@handler_error_json
def get_e2e_test_coverage_handler(
    project_path: str | None = None,
) -> str:
    """
    Get E2E test coverage report for the project.

    Analyzes the generated E2ETestSpec to show what's covered.

    Args:
        project_path: Optional path to project (uses active project if not specified)

    Returns:
        JSON string with coverage report
    """
    progress = extract_progress(None)
    progress.log_sync("Analyzing E2E test coverage...")
    # Resolve project path
    root: Path
    if project_path:
        root = Path(project_path)
    else:
        active = get_active_project_path()
        if active:
            root = active
        else:
            project = get_project_root()
            if project:
                root = project
            else:
                return json.dumps(
                    {
                        "error": "No project path specified and no active project set",
                    }
                )

    # Load and generate testspec
    from dazzle.core.fileset import discover_dsl_files
    from dazzle.core.linker import build_appspec
    from dazzle.core.manifest import load_manifest
    from dazzle.core.parser import parse_modules
    from dazzle.testing.testspec_generator import generate_e2e_testspec

    manifest_path = root / "dazzle.toml"
    manifest = load_manifest(manifest_path)
    dsl_files = discover_dsl_files(root, manifest)
    modules = parse_modules(dsl_files)
    appspec = build_appspec(modules, manifest.project_root)
    testspec = generate_e2e_testspec(appspec, manifest)

    # Analyze coverage
    entities_in_spec = {e.name for e in appspec.domain.entities}
    surfaces_in_spec = {s.name for s in appspec.surfaces}

    entities_covered = set()
    surfaces_covered = set()
    priority_counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    tag_counts: dict[str, int] = {}

    for flow in testspec.flows:
        if flow.entity:
            entities_covered.add(flow.entity)
        for tag in flow.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            # Check if tag is a surface name
            if tag in surfaces_in_spec:
                surfaces_covered.add(tag)
        priority_counts[flow.priority.value] = priority_counts.get(flow.priority.value, 0) + 1

    # Build coverage report
    coverage = {
        "project": appspec.name,
        "total_flows": len(testspec.flows),
        "total_fixtures": len(testspec.fixtures),
        "entities": {
            "total": len(entities_in_spec),
            "covered": len(entities_covered),
            "coverage_pct": round(len(entities_covered) / len(entities_in_spec) * 100, 1)
            if entities_in_spec
            else 0,
            "covered_list": sorted(entities_covered),
            "uncovered_list": sorted(entities_in_spec - entities_covered),
        },
        "surfaces": {
            "total": len(surfaces_in_spec),
            "covered": len(surfaces_covered),
            "coverage_pct": round(len(surfaces_covered) / len(surfaces_in_spec) * 100, 1)
            if surfaces_in_spec
            else 0,
            "covered_list": sorted(surfaces_covered),
            "uncovered_list": sorted(surfaces_in_spec - surfaces_covered),
        },
        "by_priority": priority_counts,
        "by_tag": dict(sorted(tag_counts.items(), key=lambda x: -x[1])[:10]),
    }

    return json.dumps(coverage, indent=2)


@handler_error_json
def list_e2e_flows_handler(
    project_path: str | None = None,
    priority: str | None = None,
    tag: str | None = None,
    limit: int = 20,
) -> str:
    """
    List available E2E test flows.

    Args:
        project_path: Optional path to project
        priority: Filter by priority
        tag: Filter by tag
        limit: Maximum number of flows to return

    Returns:
        JSON string with flow list
    """
    progress = extract_progress(None)
    progress.log_sync("Listing E2E test flows...")
    # Resolve project path
    root: Path
    if project_path:
        root = Path(project_path)
    else:
        active = get_active_project_path()
        if active:
            root = active
        else:
            project = get_project_root()
            if project:
                root = project
            else:
                return json.dumps(
                    {
                        "error": "No project path specified and no active project set",
                    }
                )

    # Generate testspec
    from dazzle.core.fileset import discover_dsl_files
    from dazzle.core.linker import build_appspec
    from dazzle.core.manifest import load_manifest
    from dazzle.core.parser import parse_modules
    from dazzle.testing.testspec_generator import generate_e2e_testspec

    manifest_path = root / "dazzle.toml"
    manifest = load_manifest(manifest_path)
    dsl_files = discover_dsl_files(root, manifest)
    modules = parse_modules(dsl_files)
    appspec = build_appspec(modules, manifest.project_root)
    testspec = generate_e2e_testspec(appspec, manifest)

    # Filter flows
    flows = testspec.flows

    if priority:
        from dazzle.core.ir import FlowPriority

        try:
            priority_enum = FlowPriority(priority)
            flows = [f for f in flows if f.priority == priority_enum]
        except ValueError:
            pass

    if tag:
        flows = [f for f in flows if tag in f.tags]

    # Build response
    flow_list = [
        {
            "id": f.id,
            "description": f.description,
            "priority": f.priority.value,
            "tags": f.tags[:5],  # Limit tags for readability
            "steps": len(f.steps),
            "entity": f.entity,
        }
        for f in flows[:limit]
    ]

    return json.dumps(
        {
            "project": appspec.name,
            "total": len(testspec.flows),
            "filtered": len(flows),
            "shown": len(flow_list),
            "flows": flow_list,
        },
        indent=2,
    )


@async_handler_error_json
async def run_agent_e2e_tests_handler(
    project_path: str | None = None,
    test_id: str | None = None,
    headless: bool = True,
    model: str | None = None,
) -> str:
    """
    Run E2E tests using an LLM agent.

    The agent uses Claude to observe pages, decide actions, and verify outcomes.
    This enables testing of complex UI flows that require visual understanding.

    Args:
        project_path: Optional path to project (uses active project if not specified)
        test_id: Specific test ID to run (default: all E2E tests)
        headless: Run browser in headless mode (default: True)
        model: LLM model to use (default: claude-sonnet-4-20250514)

    Returns:
        JSON string with test results including:
        - status: overall pass/fail
        - results: list of test results with steps and reasoning
        - duration_seconds: total execution time
    """
    progress = extract_progress(None)
    progress.log_sync("Running agent E2E tests...")
    try:
        # Resolve project path
        root: Path
        if project_path:
            root = Path(project_path)
        else:
            active = get_active_project_path()
            if active:
                root = active
            else:
                project = get_project_root()
                if project:
                    root = project
                else:
                    return json.dumps(
                        {
                            "error": "No project path specified and no active project set",
                            "status": "error",
                        }
                    )

        # Import agent runner
        from dazzle.testing.agent_e2e import run_agent_tests

        test_ids = [test_id] if test_id else None

        # Run tests
        results = await run_agent_tests(
            project_path=root,
            test_ids=test_ids,
            headless=headless,
            model=model,
        )

        if not results:
            return json.dumps(
                {
                    "status": "skipped",
                    "message": "No E2E tests found to run",
                    "project": root.name,
                }
            )

        # Format response
        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed

        result_list = []
        for r in results:
            result_list.append(
                {
                    "test_id": r.test_id,
                    "passed": r.passed,
                    "steps": len(r.steps),
                    "duration_ms": r.duration_ms,
                    "reasoning": r.reasoning,
                    "error": r.error,
                }
            )

        return json.dumps(
            {
                "status": "passed" if failed == 0 else "failed",
                "project": root.name,
                "total": len(results),
                "passed": passed,
                "failed": failed,
                "success_rate": round(passed / len(results) * 100, 1) if results else 0,
                "results": result_list,
            },
            indent=2,
        )

    except ImportError as e:
        return json.dumps(
            {
                "status": "error",
                "error": str(e),
                "hint": "pip install playwright anthropic && playwright install chromium",
            }
        )


def get_test_tier_guidance_handler(arguments: dict[str, Any]) -> str:
    """Provide guidance on which test tier to use for a scenario."""
    progress = extract_progress(arguments)
    progress.log_sync("Analyzing test tier...")
    scenario = arguments.get("scenario", "").lower()

    # Keywords that suggest Tier 3 (agent) testing
    tier3_keywords = [
        "visual",
        "looks",
        "appearance",
        "layout",
        "design",
        "exploratory",
        "fuzz",
        "break",
        "edge case",
        "accessibility",
        "keyboard",
        "screen reader",
        "adaptive",
        "unexpected",
        "regression",
        "refactor",
    ]

    # Keywords that suggest Tier 2 (Playwright) testing
    tier2_keywords = [
        "navigation",
        "navigate",
        "click",
        "form",
        "submit",
        "fill",
        "ui",
        "browser",
        "page",
        "button",
        "modal",
        "dialog",
    ]

    # Keywords that suggest Tier 1 (API) testing
    tier1_keywords = [
        "crud",
        "create",
        "update",
        "delete",
        "list",
        "api",
        "validation",
        "required",
        "unique",
        "state machine",
        "transition",
        "permission",
        "access",
    ]

    # Score the scenario
    tier1_score = sum(1 for kw in tier1_keywords if kw in scenario)
    tier2_score = sum(1 for kw in tier2_keywords if kw in scenario)
    tier3_score = sum(1 for kw in tier3_keywords if kw in scenario)

    if tier3_score > tier2_score and tier3_score > tier1_score:
        recommendation = "tier3"
        reason = (
            "This scenario requires visual judgment, adaptive behavior, or exploratory testing."
        )
        tags = ["tier3", "agent"]
        run_command = "dazzle test agent"
        mcp_tool = "run_agent_e2e_tests"
    elif tier2_score > tier1_score:
        recommendation = "tier2"
        reason = "This scenario involves UI interaction with predictable, scriptable steps."
        tags = ["tier2", "playwright"]
        run_command = "dazzle test playwright"
        mcp_tool = "run_e2e_tests"
    else:
        recommendation = "tier1"
        reason = "This scenario can be tested via API without a browser."
        tags = ["tier1", "generated", "dsl-derived"]
        run_command = "dazzle test dsl-run"
        mcp_tool = "run_dsl_tests"

    return json.dumps(
        {
            "scenario": arguments.get("scenario", ""),
            "recommendation": recommendation,
            "reason": reason,
            "tags_to_use": tags,
            "run_command": run_command,
            "mcp_tool": mcp_tool,
            "tier_summary": {
                "tier1": {
                    "name": "API Tests",
                    "characteristics": ["Fast", "No browser", "Free"],
                    "best_for": [
                        "CRUD operations",
                        "Field validation",
                        "API response checks",
                        "State machine transitions",
                    ],
                },
                "tier2": {
                    "name": "Scripted E2E (Playwright)",
                    "characteristics": ["Deterministic", "Uses semantic selectors", "Free"],
                    "best_for": [
                        "Navigation verification",
                        "Form submission",
                        "UI interaction flows",
                        "Multi-step workflows",
                    ],
                },
                "tier3": {
                    "name": "Agent Tests (LLM-Driven)",
                    "characteristics": ["Adaptive", "Visual understanding", "Costs money"],
                    "best_for": [
                        "Visual verification",
                        "Exploratory testing",
                        "Accessibility audits",
                        "Testing after UI refactors",
                    ],
                },
            },
        },
        indent=2,
    )
