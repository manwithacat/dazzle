"""Progress group_by must not dump empty stages (oral #165)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_region_computes import (
    compute_progress,
    infer_progress_stages,
)
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeProgress:
    name = "agent_lifecycle_progress"
    title = "Agent lifecycle"
    display = "progress"
    empty_message = "No tickets for this agent"


def _support_lifecycle_progress():
    spec = load_project(Path("examples/support_tickets"))
    for ws in spec.workspaces:
        for region in ws.regions:
            if region.name == "agent_lifecycle_progress":
                return spec, region
    raise AssertionError("support_tickets agent_lifecycle_progress missing")


def test_support_progress_groups_by_status_without_stages() -> None:
    spec, region = _support_lifecycle_progress()
    assert str(getattr(region.display, "value", region.display)) == "progress"
    assert region.group_by == "status"
    assert list(region.progress_stages or []) == []
    ticket = spec.get_entity("Ticket")
    assert ticket is not None


def test_infer_progress_stages_from_ticket_enum() -> None:
    spec, _region = _support_lifecycle_progress()
    ticket = spec.get_entity("Ticket")
    items = [
        {"id": "t1", "title": "Login loop", "status": "open"},
        {"id": "t2", "title": "Slow search", "status": "in_progress"},
        {"id": "t3", "title": "Second open", "status": "open"},
        {"id": "t99", "title": "Leftover ticket", "status": "zzz"},
    ]
    stages, leftover = infer_progress_stages(items, "status", ticket, authored=[])
    assert stages[:4] == ["open", "in_progress", "resolved", "closed"]
    assert "zzz" in stages
    assert leftover == frozenset({"zzz"})


def test_empty_items_do_not_invent_leftover_stages() -> None:
    spec, _region = _support_lifecycle_progress()
    ticket = spec.get_entity("Ticket")
    stages, leftover = infer_progress_stages([], "status", ticket, authored=[])
    assert leftover == frozenset()
    assert "zzz" not in stages
    assert "open" in stages


def test_compute_progress_counts_inferred_and_leftover() -> None:
    spec, _region = _support_lifecycle_progress()
    ticket = spec.get_entity("Ticket")
    items = [
        {"id": "t1", "title": "Login loop", "status": "open"},
        {"id": "t2", "title": "Slow search", "status": "in_progress"},
        {"id": "t3", "title": "Second open", "status": "open"},
        {"id": "t4", "title": "Done", "status": "closed"},
        {"id": "t99", "title": "Leftover ticket", "status": "zzz"},
    ]
    stages, leftover = infer_progress_stages(items, "status", ticket, authored=[])
    prog = compute_progress(
        items,
        stages,
        "closed",
        "status",
        leftover_stages=leftover,
    )
    by_name = {row["name"]: row for row in prog["stage_counts"]}
    assert by_name["open"]["count"] == 2
    assert by_name["in_progress"]["count"] == 1
    assert by_name["closed"]["count"] == 1
    assert by_name["closed"]["complete"] is True
    assert by_name["zzz"]["count"] == 1
    assert by_name["zzz"]["complete"] is False
    assert "Login loop" not in {row["name"] for row in prog["stage_counts"]}


def test_progress_html_renders_status_chips_not_empty() -> None:
    spec, _region = _support_lifecycle_progress()
    ticket = spec.get_entity("Ticket")
    items = [
        {"id": "t1", "title": "Login loop", "status": "open"},
        {"id": "t2", "title": "Slow search", "status": "in_progress"},
        {"id": "t99", "title": "Leftover ticket", "status": "zzz"},
    ]
    stages, leftover = infer_progress_stages(items, "status", ticket, authored=[])
    prog = compute_progress(
        items,
        stages,
        "closed",
        "status",
        leftover_stages=leftover,
    )
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakeProgress(),
            {
                "stage_counts": prog["stage_counts"],
                "complete_pct": prog["complete_pct"],
                "complete_count": prog["complete_count"],
                "progress_total": prog["total"],
            },
        )
    )
    assert "Open" in html
    assert "In Progress" in html
    assert "zzz" in html
    assert "Login loop" not in html
    assert "No progress" not in html
