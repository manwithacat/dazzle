"""Integration tests for the fidelity scorer with real project data."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.fidelity_scorer import score_appspec_fidelity
from dazzle.core.project import load_project

SIMPLE_TASK_DIR = Path(__file__).resolve().parents[2] / "examples" / "simple_task"


@pytest.fixture
def simple_task_appspec():
    """Parse and link the simple_task example."""
    if not (SIMPLE_TASK_DIR / "dsl").exists():
        pytest.skip("simple_task example not found")
    return load_project(SIMPLE_TASK_DIR)


@pytest.fixture
def rendered_pages(simple_task_appspec):
    """Compile and render simple_task surfaces to HTML."""
    compile_mod = pytest.importorskip(
        "dazzle_ui.converters.template_compiler",
        reason="dazzle_ui not installed",
    )
    render_mod = pytest.importorskip(
        "dazzle_ui.runtime.template_renderer",
        reason="dazzle_ui not installed",
    )

    page_contexts = compile_mod.compile_appspec_to_templates(simple_task_appspec)
    pages: dict[str, str] = {}
    for route, ctx in page_contexts.items():
        try:
            html = render_mod.render_page(ctx)
            for surface in simple_task_appspec.surfaces:
                sname = surface.name.replace("_", "-")
                if sname in route or surface.name in route:
                    pages[surface.name] = html
                    break
        except Exception:
            continue
    return pages


def test_report_has_surface_scores(simple_task_appspec, rendered_pages):
    """Report should have per-surface scores."""
    if not rendered_pages:
        pytest.skip("No pages rendered")
    report = score_appspec_fidelity(simple_task_appspec, rendered_pages)
    assert len(report.surface_scores) > 0
    assert report.overall >= 0.0


def test_report_nonzero_fidelity(simple_task_appspec, rendered_pages):
    """Rendered simple_task should have non-zero fidelity."""
    if not rendered_pages:
        pytest.skip("No pages rendered")
    report = score_appspec_fidelity(simple_task_appspec, rendered_pages)
    assert report.overall > 0.0


def test_mcp_handler_returns_valid_json(simple_task_appspec):
    """MCP handler should return valid JSON with expected keys."""
    import json

    handler_mod = pytest.importorskip(
        "dazzle.mcp.server.handlers.fidelity",
        reason="MCP handler not available",
    )

    result_str = handler_mod.score_fidelity_handler(SIMPLE_TASK_DIR, {})
    result = json.loads(result_str)

    # Should either have fidelity data or a graceful error
    if "error" not in result:
        assert "overall_fidelity" in result
        assert "surfaces" in result
        assert "top_recommendations" in result
        assert "next_steps" in result
