"""Related/workspace conversation must title the clock, not ``Jul 2`` (oral #142)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.page.converters.template_compiler import compile_appspec_to_templates
from dazzle.render.fragment.primitives.data import RelatedGroup, RelatedTab
from dazzle.render.fragment.region._builders_timeline import _conversation_time
from dazzle.render.fragment.renderer import FragmentRenderer
from dazzle.render.fragment.renderer._related_conversation import (
    conversation_time_label,
    related_conversation_messages,
)


def test_conversation_time_label_friendly_en_gb_is_clock_not_month() -> None:
    label, full = conversation_time_label("16 Jul 2026 15:30")
    assert label == "15:30"
    assert full == "16 Jul 2026 15:30"
    assert label != "Jul 2"


def test_conversation_time_label_iso_and_postgres_still_ride() -> None:
    assert conversation_time_label("2026-07-16T15:30:00Z")[0] == "15:30"
    assert conversation_time_label("2026-07-15 10:30:00+01:00")[0] == "10:30"
    assert conversation_time_label("16 July 2026 at 15:30")[0] == "15:30"


def test_conversation_time_label_leftover_stays_put() -> None:
    assert conversation_time_label("zzz") == ("zzz", "zzz")
    assert conversation_time_label("16 Jul 2026 15:30zzz") == (
        "16 Jul 2026 15:30zzz",
        "16 Jul 2026 15:30zzz",
    )
    assert conversation_time_label("2026-07-16T15:30zzz") == (
        "2026-07-16T15:30zzz",
        "2026-07-16T15:30zzz",
    )
    assert conversation_time_label("ghost") == ("ghost", "ghost")


def test_related_conversation_messages_clock_not_month() -> None:
    tab = RelatedTab(
        tab_id="discussion",
        label="Discussion",
        headers=("body", "author", "created_at"),
        rows=(
            (
                "Promo packet ready for compensation review.",
                "Priya Shah",
                "16 Jul 2026 15:30",
            ),
        ),
        row_drill=("/app/person-note/n-1",),
    )
    msgs = related_conversation_messages(tab)
    assert len(msgs) == 1
    assert msgs[0].time_label == "15:30"
    assert msgs[0].time_datetime == "16 Jul 2026 15:30"
    assert msgs[0].time_label != "Jul 2"


def test_related_conversation_leftover_clock_stays_put() -> None:
    tab = RelatedTab(
        tab_id="discussion",
        label="Discussion",
        headers=("body", "author", "created_at"),
        rows=(("Keep leftover visible.", "Priya Shah", "zzz"),),
    )
    msgs = related_conversation_messages(tab)
    assert msgs[0].time_label == "zzz"


def test_related_conversation_html_clock_not_month() -> None:
    html = FragmentRenderer().render(
        RelatedGroup(
            group_id="discussion",
            label="Discussion",
            display="conversation",
            tabs=(
                RelatedTab(
                    tab_id="discussion",
                    label="Discussion",
                    headers=("body", "author", "created_at"),
                    rows=(
                        (
                            "Promo packet ready for compensation review.",
                            "Priya Shah",
                            "16 Jul 2026 15:30",
                        ),
                    ),
                ),
            ),
        )
    )
    assert 'class="dz-message__time"' in html
    assert ">15:30<" in html
    assert ">Jul 2<" not in html
    assert 'datetime="16 Jul 2026 15:30"' in html


def test_workspace_conversation_time_uses_same_clock() -> None:
    label, full = _conversation_time({"created_at": "16 Jul 2026 15:30"})
    assert label == "15:30"
    assert "Jul 2026" in full
    leftover, _ = _conversation_time({"created_at": "zzz"})
    assert leftover == "zzz"


def test_hr_records_discussion_created_at_is_datetime() -> None:
    spec = load_project(Path("examples/hr_records"))
    ctxs = compile_appspec_to_templates(spec)
    detail = ctxs["/person/{id}"].detail
    assert detail is not None
    group = next(g for g in detail.related_groups if g.group_id == "group-discussion")
    assert group.display == "conversation"
    by = {c.key: c for c in group.tabs[0].columns}
    assert by["created_at"].type == "datetime"
    assert by["body"].type in {"text", "str", "string"}
