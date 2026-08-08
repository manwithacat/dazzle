"""display: accordion hyperpart emitter — unit pins (cycle 1750)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.qa.hyperpart_dsl_shapes import shapes_snapshot
from dazzle.render.fragment import Accordion, AccordionItem, FragmentRenderer

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples" / "simple_task"


def test_accordion_emit_mounts_dz_accordion_spine() -> None:
    html = FragmentRenderer().render(
        Accordion(
            items=(
                AccordionItem(title="Q1", body="A1", open=True),
                AccordionItem(title="Q2", body="A2"),
            ),
            name="dz-acc-faq",
        )
    )
    assert 'class="dz-accordion"' in html
    assert 'class="dz-accordion__item"' in html
    assert 'class="dz-accordion__trigger"' in html
    assert 'class="dz-accordion__panel"' in html
    assert 'name="dz-acc-faq"' in html
    assert " open>" in html or ' open"' in html or " open " in html
    assert "Q1" in html and "A1" in html
    assert "Q2" in html and "A2" in html
    assert 'data-dz-entry-count="2"' in html


def test_simple_task_admin_declares_task_faq_accordion() -> None:
    text = (APP / "dsl" / "app.dsl").read_text(encoding="utf-8")
    assert "task_faq:" in text
    assert "display: accordion" in text
    assert "How does priority work?" in text


def test_simple_task_appspec_task_faq_region() -> None:
    appspec = load_project_appspec(APP)
    workspaces = list(getattr(appspec, "workspaces", None) or [])
    admin = next((w for w in workspaces if getattr(w, "name", None) == "admin_dashboard"), None)
    assert admin is not None, (
        f"admin_dashboard missing; names={[getattr(w, 'name', None) for w in workspaces]}"
    )
    regions = list(getattr(admin, "regions", None) or [])
    by_name = {getattr(r, "name", None): r for r in regions}
    region = by_name.get("task_faq")
    assert region is not None, f"task_faq missing; regions={list(by_name)}"
    display = getattr(region, "display", None)
    display_v = getattr(display, "value", display)
    assert display_v == "accordion"
    entries = list(getattr(region, "status_entries", None) or [])
    assert len(entries) >= 2
    assert getattr(entries[0], "title", None)
    assert getattr(entries[0], "caption", None)


def test_dsl_shapes_accordion_live() -> None:
    snap = shapes_snapshot()
    planned = set(snap.get("planned_ids") or [])
    assert "accordion" not in planned
    assert snap["live"] >= 65
