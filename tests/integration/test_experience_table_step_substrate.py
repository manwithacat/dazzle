"""ADR-0049 Task 6: the experience table-STEP renders its list through the
substrate (the legacy `render_filterable_table` it used is deleted).

This pins the previously UNTESTED experience table-step path the delete-review
flagged (B2): `examples/ops_dashboard` `incident_response` experience → `triage`
step → `alert_list` (`mode: list render: fragment`). The http route pre-renders
the list via the substrate dispatch seam and passes the HTML to the page
renderer, keeping the `page ↛ http` import contract intact.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.appspec_loader import load_project_appspec

pytest.importorskip("dazzle.http.runtime.experience_routes")

_OPS = Path(__file__).resolve().parent.parent.parent / "examples" / "ops_dashboard"


def _services():
    from dazzle.http.runtime.renderers.init import register_default_renderers
    from dazzle.http.runtime.services import RuntimeServices

    services = RuntimeServices()
    register_default_renderers(services)
    return services


class _Req:
    """Minimal request stub carrying app.state.services for the dispatch seam."""

    def __init__(self, services) -> None:
        self.app = type("_App", (), {"state": type("_State", (), {"services": services})()})()


class _Deps:
    def __init__(self, appspec) -> None:
        self.appspec = appspec
        self.app_prefix = ""


def test_experience_triage_step_renders_list_via_substrate() -> None:
    from dazzle.page.converters.experience_compiler import compile_experience_context
    from dazzle.page.runtime.experience_renderer import render_experience_inner_html
    from dazzle.page.runtime.experience_state import ExperienceState

    appspec = load_project_appspec(_OPS)
    experience = next(e for e in appspec.experiences if e.name == "incident_response")
    state = ExperienceState(step="triage", completed=[], data={})
    exp_ctx = compile_experience_context(experience, state, appspec, "")

    # The triage step targets a LIST surface — the compiler exposes its name.
    assert exp_ctx.surface_name == "alert_list"
    assert exp_ctx.page_context is not None
    assert exp_ctx.page_context.table is not None

    # The http route pre-renders the table-step list via the substrate.
    from dazzle.http.runtime.experience_routes import _render_experience_surface_step

    services = _services()
    table_html = _render_experience_surface_step(exp_ctx, _Deps(appspec), _Req(services))

    # It renders the substrate list (not the deleted legacy table chrome).
    assert "dz-region--kind-list" in table_html
    assert 'class="dz-table-body"' in table_html  # the hydrating skeleton tbody
    assert "data-dz-grid" in table_html  # the HM grid root (C2.4: Alpine mount retired)

    # And it composes into the experience inner HTML.
    inner = render_experience_inner_html(exp_ctx, surface_step_html=table_html)
    assert "dz-experience-step" in inner
    assert "dz-region--kind-list" in inner
    # the loud placeholder must NOT appear when the list rendered
    assert "could not be rendered" not in inner


def test_experience_table_step_loud_placeholder_when_no_services() -> None:
    """No services → the page renderer shows a loud placeholder, never a blank
    step (D4: no silent legacy fallback)."""
    from dazzle.page.converters.experience_compiler import compile_experience_context
    from dazzle.page.runtime.experience_renderer import render_experience_inner_html
    from dazzle.page.runtime.experience_state import ExperienceState

    appspec = load_project_appspec(_OPS)
    experience = next(e for e in appspec.experiences if e.name == "incident_response")
    state = ExperienceState(step="triage", completed=[], data={})
    exp_ctx = compile_experience_context(experience, state, appspec, "")

    from dazzle.http.runtime.experience_routes import _render_experience_surface_step

    table_html = _render_experience_surface_step(exp_ctx, _Deps(appspec), _Req(None))
    assert table_html == ""  # route can't render without services
    inner = render_experience_inner_html(exp_ctx, surface_step_html=table_html)
    assert "could not be rendered" in inner
