"""Cycle 1676 — related-entity row/card/file open discovery (queue/grid parity)."""

from __future__ import annotations

from dazzle.render.fragment.primitives.data import RelatedGroup, RelatedTab
from dazzle.render.fragment.renderer import FragmentRenderer
from dazzle.render.fragment.renderer._render_tables import _RenderTablesMixin


def _tab(*, drill: str = "/app/taskcomment/c-1") -> RelatedTab:
    return RelatedTab(
        tab_id="comments",
        label="Comments",
        headers=("Body", "Author"),
        rows=(("Ship it", "Ada"),),
        row_drill=(drill,),
    )


def test_related_drill_attrs_stamps_open_discovery() -> None:
    class _Ctx:
        @staticmethod
        def escape_attr(s: str) -> str:
            return s.replace('"', "&quot;")

    attrs = _RenderTablesMixin._related_drill_attrs("/app/task/t-9", _Ctx())
    assert "data-dz-related-drill" in attrs
    assert 'data-dz-open-entity="Task"' in attrs
    assert 'data-dz-open-via="id"' in attrs
    assert 'data-dz-open-chain="/app/task/t-9"' in attrs
    assert 'data-dz-open-hops="1"' in attrs
    assert "Open Task" in attrs
    assert 'hx-get="/app/task/t-9"' in attrs


def test_related_table_row_stamps_open_discovery() -> None:
    html = FragmentRenderer().render(
        RelatedGroup(
            group_id="comments",
            label="Comments",
            display="table",
            tabs=(_tab(drill="/app/taskcomment/c-42"),),
        )
    )
    assert "data-dz-related-drill" in html
    assert (
        'data-dz-open-entity="Taskcomment"' in html or 'data-dz-open-entity="TaskComment"' in html
    )
    assert 'data-dz-open-via="id"' in html
    assert 'data-dz-open-chain="/app/taskcomment/c-42"' in html
    assert 'hx-get="/app/taskcomment/c-42"' in html
    assert "Ship it" in html


def test_related_status_card_stamps_open_discovery() -> None:
    html = FragmentRenderer().render(
        RelatedGroup(
            group_id="notes",
            label="Notes",
            display="status_cards",
            tabs=(_tab(drill="/app/personnote/n-7"),),
        )
    )
    assert "dz-related-status-card" in html
    assert "data-dz-related-drill" in html
    assert 'data-dz-open-entity="Personnote"' in html or 'data-dz-open-entity="PersonNote"' in html
    assert 'data-dz-open-chain="/app/personnote/n-7"' in html


def test_related_file_row_stamps_open_discovery() -> None:
    html = FragmentRenderer().render(
        RelatedGroup(
            group_id="files",
            label="Files",
            display="file_list",
            tabs=(
                RelatedTab(
                    tab_id="files",
                    label="Files",
                    headers=("Name", "Size"),
                    rows=(("brief.pdf", "12kb"),),
                    row_drill=("/app/attachment/a-1",),
                ),
            ),
        )
    )
    assert "dz-related-file-row" in html
    assert "data-dz-related-drill" in html
    assert 'data-dz-open-entity="Attachment"' in html
    assert 'data-dz-open-chain="/app/attachment/a-1"' in html


def test_related_without_drill_has_no_open_attrs() -> None:
    html = FragmentRenderer().render(
        RelatedGroup(
            group_id="comments",
            label="Comments",
            display="table",
            tabs=(
                RelatedTab(
                    tab_id="comments",
                    label="Comments",
                    headers=("Body",),
                    rows=(("static",),),
                ),
            ),
        )
    )
    assert "data-dz-related-drill" not in html
    assert "data-dz-open-entity" not in html
    assert "data-dz-open-chain" not in html
    assert "hx-get=" not in html
