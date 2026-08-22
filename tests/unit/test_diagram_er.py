"""Diagram must not dump empty ER while entities exist (oral #166)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_region_computes import compute_diagram_data
from dazzle.http.runtime.workspace_region_render import (
    RegionRenderInputs,
    RenderEnv,
    _build_specialty_adapter_ctx,
)
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeDiagram:
    name = "fleet_diagram"
    title = "Fleet diagram"
    display = "diagram"
    empty_message = "No devices to diagram"


def _fieldtest_fleet_diagram():
    spec = load_project(Path("examples/fieldtest_hub"))
    for ws in spec.workspaces:
        for region in ws.regions:
            if region.name == "fleet_diagram":
                return spec, region
    raise AssertionError("fieldtest_hub fleet_diagram missing")


def test_fieldtest_fleet_diagram_is_diagram() -> None:
    _spec, region = _fieldtest_fleet_diagram()
    assert str(getattr(region.display, "value", region.display)) == "diagram"
    assert region.source == "Device"


def test_compute_diagram_data_emits_fieldtest_refs() -> None:
    spec, _region = _fieldtest_fleet_diagram()
    mermaid = compute_diagram_data(spec)
    assert mermaid.startswith("erDiagram")
    assert "Device {" in mermaid
    assert "Tester {" in mermaid
    assert "IssueReport {" in mermaid
    assert "Device }o--|| Tester : assigned_tester_id" in mermaid
    assert "zzz" not in mermaid


def test_empty_spec_does_not_invent_leftover_entities() -> None:
    assert compute_diagram_data(None) == ""
    empty = SimpleNamespace(domain=SimpleNamespace(entities=[]))
    mermaid = compute_diagram_data(empty)
    assert mermaid == "erDiagram"
    assert "zzz" not in mermaid


def test_diagram_html_renders_er_not_empty() -> None:
    spec, _region = _fieldtest_fleet_diagram()
    mermaid = compute_diagram_data(spec)
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakeDiagram(),
            {"diagram_data": mermaid},
        )
    )
    assert "erDiagram" in html
    assert "Device" in html
    assert "Tester" in html
    assert "assigned_tester_id" in html
    assert "No entity relationships to display." not in html
    assert "zzz" not in html


def test_specialty_ctx_forwards_precomputed_mermaid() -> None:
    mermaid = "erDiagram\n    Device {\n        str name\n    }"
    ctx = SimpleNamespace(
        ctx_region=SimpleNamespace(display="DIAGRAM", nodes=[], edges=[]),
        diagram_data=mermaid,
    )
    env = RenderEnv(
        ctx=ctx,  # type: ignore[arg-type]
        ir_region=None,
        inputs=RegionRenderInputs(),
        request=None,
        user_ctx=None,  # type: ignore[arg-type]
        sort=None,
        sort_dir="asc",
    )
    out = _build_specialty_adapter_ctx("DIAGRAM", env, {})
    assert out["diagram_data"] == mermaid
    assert out["nodes"] == []
