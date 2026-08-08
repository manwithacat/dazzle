"""bubble hyperpart emitter — unit pins (cycle 1762).

``display: conversation`` → stack of ``Bubble`` / ``.dz-bubble``.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.qa.hyperpart_dsl_shapes import shapes_snapshot
from dazzle.render.fragment import Bubble, FragmentRenderer, Stack
from dazzle.render.fragment.region._builders_timeline import _BuildersTimelineMixin
from dazzle.render.fragment.region._context import RegionContext

ROOT = Path(__file__).resolve().parents[2]
SIMPLE = ROOT / "examples" / "simple_task"
SUPPORT = ROOT / "examples" / "support_tickets"


def test_bubble_emit_mounts_dz_spine() -> None:
    html = FragmentRenderer().render(Bubble(text="Can we reschedule?", from_="in"))
    assert 'class="dz-bubble"' in html
    assert 'data-dz-from="in"' in html
    assert "<p>Can we reschedule?</p>" in html


def test_bubble_outbound_and_tone() -> None:
    html = FragmentRenderer().render(Bubble(text="Hold sent.", from_="out", tone="danger"))
    assert 'data-dz-from="out"' in html
    assert 'data-dz-tone="danger"' in html
    assert "Hold sent." in html


def test_conversation_stack_emits_bubbles() -> None:
    html = FragmentRenderer().render(
        Stack(
            children=(
                Bubble(text="Hello", from_="in"),
                Bubble(text="Hi back", from_="out"),
            ),
            gap="sm",
        )
    )
    assert html.count('class="dz-bubble"') == 2
    assert 'data-dz-from="in"' in html
    assert 'data-dz-from="out"' in html


def test_build_conversation_from_static_entries() -> None:
    class _A(_BuildersTimelineMixin):
        pass

    region = type("R", (), {"name": "sample_thread", "title": "Sample", "empty_message": None})()
    ctx: RegionContext = {
        "status_entries": [
            {"title": "in", "body": "Inbound note"},
            {"title": "out", "caption": "Outbound reply"},
        ],
        "items": [],
        "empty_message": "none",
    }
    surface = _A()._build_conversation(region, ctx)
    html = FragmentRenderer().render(surface)
    assert 'class="dz-bubble"' in html
    assert "Inbound note" in html
    assert "Outbound reply" in html
    assert 'data-dz-from="in"' in html
    assert 'data-dz-from="out"' in html


def test_build_conversation_from_comment_items() -> None:
    class _A(_BuildersTimelineMixin):
        pass

    region = type("R", (), {"name": "live", "title": "Live", "empty_message": None})()
    ctx: RegionContext = {
        "items": [
            {"content": "Customer: site down", "is_internal": False},
            {"content": "Agent: investigating", "is_internal": True},
        ],
        "status_entries": [],
    }
    surface = _A()._build_conversation(region, ctx)
    html = FragmentRenderer().render(surface)
    assert "Customer: site down" in html
    assert "Agent: investigating" in html
    assert html.count('class="dz-bubble"') == 2


def test_simple_task_declares_sample_thread_conversation() -> None:
    text = (SIMPLE / "dsl" / "app.dsl").read_text(encoding="utf-8")
    assert "sample_thread:" in text
    assert "display: conversation" in text
    assert "Can we reschedule the walkthrough to Thursday?" in text


def test_simple_task_appspec_sample_thread_region() -> None:
    appspec = load_project_appspec(SIMPLE)
    workspaces = list(getattr(appspec, "workspaces", None) or [])
    admin = next((w for w in workspaces if getattr(w, "name", None) == "admin_dashboard"), None)
    assert admin is not None
    regions = list(getattr(admin, "regions", None) or [])
    by_name = {getattr(r, "name", None): r for r in regions}
    region = by_name.get("sample_thread")
    assert region is not None, f"sample_thread missing; regions={list(by_name)}"
    display = getattr(region, "display", None)
    display_v = getattr(display, "value", display)
    assert display_v == "conversation"
    entries = list(getattr(region, "status_entries", None) or [])
    assert len(entries) >= 2


def test_support_tickets_live_conversation_is_conversation() -> None:
    text = (SUPPORT / "dsl" / "app.dsl").read_text(encoding="utf-8")
    # First ticket_queue live_conversation uses conversation display
    assert "display: conversation" in text
    appspec = load_project_appspec(SUPPORT)
    workspaces = list(getattr(appspec, "workspaces", None) or [])
    tq = next((w for w in workspaces if getattr(w, "name", None) == "ticket_queue"), None)
    assert tq is not None
    regions = {getattr(r, "name", None): r for r in list(getattr(tq, "regions", None) or [])}
    live = regions.get("live_conversation")
    assert live is not None
    display = getattr(live, "display", None)
    assert getattr(display, "value", display) == "conversation"


def test_dsl_shapes_bubble_live() -> None:
    snap = shapes_snapshot()
    planned = set(snap.get("planned_ids") or [])
    assert "bubble" not in planned
    assert snap["next_planned"] != "bubble"
    assert snap["live"] >= 69
