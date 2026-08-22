"""Temporal workspaces must show clerk as-of chrome, not a silent snapshot (oral #190)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.page.runtime.workspace_renderer import build_workspace_context
from dazzle.render.fragment import FragmentRenderer, Text, WorkspaceShell
from dazzle.render.fragment.renderer._render_interactive import leftover_honest_iso_date

HR = Path("examples/hr_records/dsl")


def _render(
    *,
    as_of: str = "",
    as_of_enabled: bool = True,
    name: str = "time_machine",
) -> str:
    return FragmentRenderer().render(
        WorkspaceShell(
            workspace_name=name,
            title="Time Machine",
            body=Text(""),
            as_of=as_of,
            as_of_enabled=as_of_enabled,
        )
    )


def test_hr_records_time_machine_is_live() -> None:
    block = (HR / "app.dsl").read_text()
    assert 'workspace time_machine "Time Machine"' in block
    assert "?as_of=" in block
    spec = load_project(Path("examples/hr_records"))
    ws = next(w for w in spec.workspaces if w.name == "time_machine")
    ctx = build_workspace_context(ws, spec)
    assert ctx.as_of_enabled
    ents = {e.name: e for e in spec.domain.entities}
    sources = {r.source for r in ws.regions if r.source}
    assert sources
    assert all(ents[s].temporal is not None for s in sources)


def test_as_of_chrome_omitted_when_disabled() -> None:
    html = _render(as_of="2025-06-01", as_of_enabled=False)
    assert "dz-workspace-as-of" not in html
    assert "dz-workspace-as-of-when" not in html


def test_valid_as_of_shows_clerk_date_not_iso_only() -> None:
    html = _render(as_of="2025-06-01")
    assert 'data-test-id="dz-workspace-as-of"' in html
    assert 'datetime="2025-06-01"' in html
    assert ">1 Jun 2025</time>" in html
    assert 'name="as_of" value="2025-06-01"' in html or 'name="as_of"' in html
    assert 'value="2025-06-01"' in html
    assert ">Now</a>" in html
    assert 'href="/app/workspaces/time_machine"' in html


def test_leftover_as_of_invents_no_chip() -> None:
    html = _render(as_of="zzz")
    assert 'data-test-id="dz-workspace-as-of"' in html
    assert "dz-workspace-as-of-when" not in html
    assert "zzz" not in html
    assert 'value="' not in html or 'value=""' in html
    assert ">Now</a>" not in html


def test_empty_as_of_is_current_no_chip() -> None:
    html = _render(as_of="")
    assert 'data-test-id="dz-workspace-as-of"' in html
    assert "dz-workspace-as-of-when" not in html
    assert ">Now</a>" not in html


def test_leftover_honest_iso_date_stays_put() -> None:
    assert leftover_honest_iso_date("2025-06-01") == "2025-06-01"
    assert leftover_honest_iso_date("zzz") == ""
    assert leftover_honest_iso_date("not-a-date") == ""
    assert leftover_honest_iso_date("") == ""
