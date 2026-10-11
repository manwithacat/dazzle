"""Queue empty must not dump generic 'Queue is empty.' (oral #225)."""

from __future__ import annotations

from dazzle.render.breadcrumbs import (
    clerk_empty_queue_title,
)
from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.region._builders_tables import _BuildersTablesMixin


class _A(_BuildersTablesMixin):
    pass


def _region(**overrides: object) -> object:
    base: dict[str, object] = {
        "name": "project_overview",
        "title": "Project overview",
        "empty_message": None,
        "source": "Project",
    }
    base.update(overrides)
    return type("R", (), base)()


def _render_queue(region: object, ctx: dict[str, object] | None = None) -> str:
    return FragmentRenderer().render(_A()._build_queue(region, ctx or {}))


def test_clerk_empty_queue_title_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_empty_queue_title(junk) == "Queue is empty."


def test_queue_empty_is_projects_not_queue_is_empty() -> None:
    html = _render_queue(_region())
    assert "dz-queue-empty" in html
    assert "No projects in this queue." in html
    assert "Queue is empty." not in html
    assert "No projectss" not in html


def test_queue_empty_ctx_source_entity_still_splits() -> None:
    html = _render_queue(_region(source=""), {"source_entity": "Project"})
    assert "No projects in this queue." in html
    assert "Queue is empty." not in html


def test_queue_empty_missing_entity_stays_queue_is_empty() -> None:
    html = _render_queue(_region(source=""))
    assert "Queue is empty." in html
    assert "No projects" not in html


def test_queue_empty_leftover_invents_no_collection() -> None:
    html = _render_queue(_region(source="zzz"))
    assert "Queue is empty." in html
    assert "No zzz" not in html


def test_queue_empty_card_title_item_fallback_does_not_invent() -> None:
    html = _render_queue(_region(source="Project"), {"entity_name": "Item"})
    assert "No projects in this queue." in html
    assert "Queue is empty." not in html


def test_queue_authored_empty_still_wins() -> None:
    html = _render_queue(_region(empty_message="No open projects"))
    assert "No open projects" in html
    assert "Queue is empty." not in html
    assert "No projects in this queue." not in html


def test_queue_populated_still_renders_rows() -> None:
    html = _render_queue(
        _region(),
        {
            "items": [{"id": "p1", "name": "Website relaunch"}],
            "display_key": "name",
            "columns": [{"key": "name", "label": "Name"}],
        },
    )
    assert "Website relaunch" in html
    assert "Queue is empty." not in html
    assert "No projects in this queue." not in html
