"""Tabbed list group_by must not dump empty tabs (oral #164)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_region_computes import compute_tabbed_slices
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeTabs:
    name = "issue_tabs"
    title = "Issue categories"
    display = "tabbed_list"
    empty_message = "No issues reported"


def _fieldtest_issue_tabs():
    spec = load_project(Path("examples/fieldtest_hub"))
    for ws in spec.workspaces:
        for region in ws.regions:
            if region.name == "issue_tabs":
                return region
    raise AssertionError("fieldtest_hub issue_tabs missing")


def test_fieldtest_issue_tabs_groups_by_status() -> None:
    region = _fieldtest_issue_tabs()
    assert str(getattr(region.display, "value", region.display)) == "tabbed_list"
    assert region.group_by == "status"


def test_scalar_group_by_slices_status_tabs() -> None:
    items = [
        {
            "id": "i1",
            "description": "Probe overheats",
            "status": "open",
        },
        {
            "id": "i2",
            "description": "Gateway dropouts",
            "status": "in_progress",
        },
        {
            "id": "i3",
            "description": "Second open",
            "status": "open",
        },
        {
            "id": "i99",
            "description": "Leftover issue",
            "status": "zzz",
        },
    ]
    cols = [{"key": "description", "label": "Description"}]
    tabs = compute_tabbed_slices(items, "status", cols)
    assert [t["key"] for t in tabs] == ["open", "in_progress", "zzz"]
    assert [t["label"] for t in tabs] == ["Open", "In Progress", "zzz"]
    assert [row["description"] for row in tabs[0]["items"]] == [
        "Probe overheats",
        "Second open",
    ]
    assert tabs[2]["items"][0]["description"] == "Leftover issue"


def test_empty_items_do_not_invent_tabs() -> None:
    assert compute_tabbed_slices([], "status", [{"key": "description"}]) == []


def test_tabbed_html_renders_status_tabs_not_empty() -> None:
    items = [
        {"id": "i1", "description": "Probe overheats", "status": "open"},
        {"id": "i2", "description": "Gateway dropouts", "status": "in_progress"},
        {"id": "i99", "description": "Leftover issue", "status": "zzz"},
    ]
    cols = [{"key": "description", "label": "Description"}]
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakeTabs(),
            {"tabs": compute_tabbed_slices(items, "status", cols)},
        )
    )
    assert 'class="dz-tabs"' in html
    assert "Open" in html
    assert "In Progress" in html
    assert "zzz" in html
    assert "Probe overheats" in html
    assert "Gateway dropouts" in html
    assert "Leftover issue" in html
    assert "No tabs" not in html
    assert "hx-get" not in html
