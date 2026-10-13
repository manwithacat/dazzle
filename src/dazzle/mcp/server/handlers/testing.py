"""
MCP Server handlers for E2E testing.

Provides tools for LLM agents to run and analyze E2E tests.
"""

import logging
import shutil
from pathlib import Path
from typing import Any

from dazzle.core.manifest import load_manifest

from .common import (
    load_project_appspec,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# check_infra
# ---------------------------------------------------------------------------


def check_test_infrastructure_impl() -> dict[str, Any]:
    """Check test infrastructure requirements.

    Returns a dict with ready status, component details, and setup instructions.
    """
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

    return result


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------


def get_e2e_test_coverage_impl(project_path: Path) -> dict[str, Any]:
    """Analyze E2E test coverage for the project. Returns coverage dict."""
    from dazzle.testing.testspec_generator import generate_e2e_testspec

    appspec = load_project_appspec(project_path)
    manifest_path = project_path / "dazzle.toml"
    manifest = load_manifest(manifest_path)
    testspec = generate_e2e_testspec(appspec, manifest)

    entities_in_spec = {e.name for e in appspec.domain.entities}
    surfaces_in_spec = {s.name for s in appspec.surfaces}

    entities_covered: set[str] = set()
    surfaces_covered: set[str] = set()
    priority_counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    tag_counts: dict[str, int] = {}

    for flow in testspec.flows:
        if flow.entity:
            entities_covered.add(flow.entity)
        for tag in flow.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            if tag in surfaces_in_spec:
                surfaces_covered.add(tag)
        priority_counts[flow.priority.value] = priority_counts.get(flow.priority.value, 0) + 1

    return {
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


# ---------------------------------------------------------------------------
# list_flows
# ---------------------------------------------------------------------------


def list_e2e_flows_impl(
    project_path: Path,
    priority: str | None,
    tag: str | None,
    limit: int,
) -> dict[str, Any]:
    """List available E2E test flows. Returns flow list dict."""
    from dazzle.testing.testspec_generator import generate_e2e_testspec

    appspec = load_project_appspec(project_path)
    manifest_path = project_path / "dazzle.toml"
    manifest = load_manifest(manifest_path)
    testspec = generate_e2e_testspec(appspec, manifest)

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

    flow_list = [
        {
            "id": f.id,
            "description": f.description,
            "priority": f.priority.value,
            "tags": f.tags[:5],
            "steps": len(f.steps),
            "entity": f.entity,
        }
        for f in flows[:limit]
    ]

    return {
        "project": appspec.name,
        "total": len(testspec.flows),
        "filtered": len(flows),
        "shown": len(flow_list),
        "flows": flow_list,
    }


# ---------------------------------------------------------------------------
# run_agent
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# tier_guidance
# ---------------------------------------------------------------------------


def get_test_tier_guidance_impl(scenario: str) -> dict[str, Any]:
    """Provide guidance on which test tier to use for a scenario. Returns guidance dict."""
    scenario_lower = scenario.lower()

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

    tier1_score = sum(1 for kw in tier1_keywords if kw in scenario_lower)
    tier2_score = sum(1 for kw in tier2_keywords if kw in scenario_lower)
    tier3_score = sum(1 for kw in tier3_keywords if kw in scenario_lower)

    if tier3_score > tier2_score and tier3_score > tier1_score:
        recommendation = "tier3"
        reason = (
            "This scenario requires visual judgment, adaptive behavior, or exploratory testing."
        )
        tags: list[str] = ["tier3", "agent"]
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

    return {
        "scenario": scenario,
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
    }
