"""Per-example smoke — every flipped example app's primary list surface

declares render: fragment, and the audit reports zero blockers per app.

Plan 11 flipped 74 surfaces across 5 example apps to render: fragment.
This test asserts the closure state — any future regression that demotes
a surface back to Jinja or introduces an adapter-incomplete IR feature
trips one of these parametrised cases.

Why list-mode only for the per-surface check: list is the entry surface
for every app and exercises the whole stack — adapter dispatch, htmx
dispatch guard, template wrapper, CSS class emission. View/create/edit
modes hit the same code path through different adapter branches; the
unit tests in tests/integration/test_simple_task_render_fragment.py
already pin those branches per mode.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.render.fragment.coverage import audit_appspec

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_EXAMPLES = _REPO_ROOT / "examples"

# Plan 11 flip targets. Each entry: (app_dir, primary_list_surface_name).
# Primary list = the first non-admin LIST surface declared in the app.
_APPS: tuple[tuple[str, str], ...] = (
    ("simple_task", "task_list"),
    ("contact_manager", "contact_list"),
    ("support_tickets", "user_list"),
    ("ops_dashboard", "system_list"),
    ("fieldtest_hub", "device_list"),
)


@pytest.mark.parametrize("app_name,primary_list", _APPS)
def test_example_app_primary_list_is_fragment(app_name: str, primary_list: str) -> None:
    """Plan 11 closure: every example's primary list surface is on the
    Fragment path. The DSL `render: fragment` directive must round-trip
    through the parser into SurfaceSpec.render."""
    app_path = _EXAMPLES / app_name
    appspec = load_project_appspec(app_path)
    matching = [s for s in appspec.surfaces if s.name == primary_list]
    assert matching, (
        f"{app_name}: expected a surface named {primary_list!r}; found "
        f"{[s.name for s in appspec.surfaces if s.mode == SurfaceMode.LIST]!r}"
    )
    surface = matching[0]
    assert surface.mode == SurfaceMode.LIST, (
        f"{app_name}.{primary_list}: expected LIST mode, got {surface.mode}"
    )
    assert getattr(surface, "render", None) == "fragment", (
        f"{app_name}.{primary_list}: render directive is "
        f"{getattr(surface, 'render', None)!r}, expected 'fragment'."
    )


@pytest.mark.parametrize("app_name,_primary", _APPS)
def test_example_app_audit_zero_blockers(app_name: str, _primary: str) -> None:
    """Plan 11 closure: every example reports zero audit blockers.

    Catches regressions where a future IR change introduces a feature the
    adapter doesn't handle yet — this would silently re-introduce blockers
    even though `render: fragment` is still on every surface."""
    appspec = load_project_appspec(_EXAMPLES / app_name)
    report = audit_appspec(appspec)
    assert report.blocked_count == 0, (
        f"{app_name}: {report.blocked_count} blocked surface(s); "
        f"aggregated_blockers={dict(report.aggregated_blockers)}"
    )
    assert report.ready_count == len(report.surfaces)
