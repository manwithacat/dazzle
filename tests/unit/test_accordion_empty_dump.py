"""display: accordion must not dump empty FAQ while entries exist (oral #168)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_region_render import (
    _LIST_FAMILY,
    _TYPED_REGION_DISPLAYS,
    RegionRenderInputs,
    RenderEnv,
    _build_list_adapter_ctx,
)
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeAccordion:
    name = "task_faq"
    title = "Task board FAQ"
    display = "accordion"
    empty_message = "No panels."


def _simple_task_faq():
    spec = load_project(Path("examples/simple_task"))
    for ws in spec.workspaces:
        for region in ws.regions:
            if region.name == "task_faq":
                return spec, region
    raise AssertionError("simple_task task_faq missing")


def test_simple_task_faq_is_accordion() -> None:
    _spec, region = _simple_task_faq()
    assert str(getattr(region.display, "value", region.display)) == "accordion"
    entries = list(getattr(region, "status_entries", None) or [])
    assert len(entries) >= 2
    titles = [getattr(e, "title", None) for e in entries]
    assert "How does priority work?" in titles


def test_accordion_carousel_progress_bar_on_typed_http_whitelist() -> None:
    for name in ("ACCORDION", "CAROUSEL", "PROGRESS_BAR"):
        assert name in _LIST_FAMILY
        assert name in _TYPED_REGION_DISPLAYS


def test_accordion_html_renders_panels_not_empty() -> None:
    entries = [
        {
            "title": "How does priority work?",
            "caption": "Priority is a closed enum.",
        },
        {"title": "zzz", "caption": "leftover panel stays put."},
    ]
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakeAccordion(),
            {"status_entries": entries, "empty_message": "No panels."},
        )
    )
    assert 'class="dz-accordion"' in html
    assert "How does priority work?" in html
    assert "Priority is a closed enum." in html
    assert "zzz" in html
    assert "No panels." not in html


def test_empty_entries_do_not_invent_leftover_panels() -> None:
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakeAccordion(),
            {"status_entries": [], "empty_message": "No panels."},
        )
    )
    assert "zzz" not in html
    assert "No panels." in html or "No panels" in html


def test_list_adapter_ctx_forwards_accordion_entries() -> None:
    entries = [{"title": "How does priority work?", "caption": "Priority is a closed enum."}]
    ctx_region = SimpleNamespace(
        name="task_faq",
        empty_message="No panels.",
        status_entries=entries,
        endpoint="/api/workspaces/admin_dashboard/regions/task_faq",
    )
    ctx = SimpleNamespace(
        ctx_region=ctx_region,
        source="",
        surface_empty_message=None,
        ir_region=None,
        detail_url_template="",
        entity_detail_urls={},
    )
    env = RenderEnv(
        ctx=ctx,  # type: ignore[arg-type]
        ir_region=None,
        inputs=RegionRenderInputs(items=[]),
        request=SimpleNamespace(query_params={}),
        user_ctx=SimpleNamespace(auth_ctx_for_filters=None, user_id=None),  # type: ignore[arg-type]
        sort=None,
        sort_dir="asc",
    )
    out = _build_list_adapter_ctx("ACCORDION", env, {})
    assert out["status_entries"] == entries
    assert out["empty_message"] == "No panels."
    assert "zzz" not in str(out["status_entries"])
