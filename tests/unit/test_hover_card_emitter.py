"""hover-card hyperpart emitter — unit pins (cycle 1765).

Compose guest (no region verb): person chip + email/role meta → ``.dz-hover-card``.
Fragment: ``HoverCard`` dual-lock spine.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.qa.hyperpart_dsl_shapes import shapes_snapshot
from dazzle.render.fragment import FragmentRenderer, HoverCard
from dazzle.render.user_chip import (
    render_user_chip_linked_html,
    wrap_hover_card_preview,
)

ROOT = Path(__file__).resolve().parents[2]
SIMPLE = ROOT / "examples" / "simple_task"


def test_hover_card_emit_mounts_dz_spine() -> None:
    html = FragmentRenderer().render(
        HoverCard(
            trigger="@maya",
            title="Maya Reyes",
            description="Operations lead · Online now",
        )
    )
    assert 'class="dz-hover-card"' in html
    assert "data-dz-hover-card" in html
    assert 'class="dz-hover-card__trigger"' in html
    assert 'aria-expanded="false"' in html
    assert 'class="dz-hover-card__content"' in html
    assert 'role="tooltip"' in html
    assert 'class="dz-hover-card__title"' in html
    assert "Maya Reyes" in html
    assert "Operations lead" in html
    assert "@maya" in html


def test_hover_card_open_stamps_data_dz_open() -> None:
    html = FragmentRenderer().render(HoverCard(trigger="x", title="T", description="D", open=True))
    assert "data-dz-open" in html
    assert 'aria-expanded="true"' in html


def test_wrap_hover_card_preview_guest() -> None:
    html = wrap_hover_card_preview(
        '<span class="dz-user-chip">Ada</span>',
        title="Ada Lovelace",
        description="ada@example.com · admin",
    )
    assert 'class="dz-hover-card"' in html
    assert "data-dz-hover-card" in html
    assert "Ada Lovelace" in html
    assert "ada@example.com" in html
    assert "dz-user-chip" in html
    # Host-owned trigger — no steal-click class on guest wrap path
    assert "dz-hover-card__trigger" not in html


def test_person_chip_compose_guest_when_email_present() -> None:
    html = render_user_chip_linked_html(
        {
            "id": "u1",
            "name": "Alice Admin",
            "email": "admin@example.com",
            "role": "admin",
            "department": "Engineering",
        },
        {"key": "assigned_to", "ref_entity": "User", "ref_route": "/users/{id}"},
    )
    assert 'class="dz-hover-card"' in html
    assert "data-dz-hover-card" in html
    assert "Alice Admin" in html
    assert "admin@example.com" in html
    assert "admin" in html
    assert "Engineering" in html
    assert "dz-user-chip" in html
    assert "dz-user-chip-link" in html


def test_person_chip_skips_hover_without_preview_meta() -> None:
    html = render_user_chip_linked_html(
        {"id": "u2", "name": "Name Only"},
        {"key": "assigned_to", "ref_entity": "User"},
    )
    assert "dz-hover-card" not in html
    assert "Name Only" in html


def test_person_chip_hover_opt_out() -> None:
    html = render_user_chip_linked_html(
        {"id": "u3", "name": "Bob", "email": "bob@example.com"},
        {"key": "assigned_to", "ref_entity": "User", "hover_card": False},
    )
    assert "dz-hover-card" not in html
    assert "Bob" in html


def test_person_chip_avatar_only_skips_hover() -> None:
    html = render_user_chip_linked_html(
        {"id": "u4", "name": "Carol", "email": "carol@example.com"},
        {"key": "assignee", "ref_entity": "User"},
        density="avatar_only",
    )
    assert "dz-hover-card" not in html
    assert "dz-user-chip--avatar-only" in html


def test_simple_task_declares_ref_user_for_fleet() -> None:
    text = (SIMPLE / "dsl" / "app.dsl").read_text(encoding="utf-8")
    assert "ref User" in text
    assert "assigned_to: ref User" in text


def test_hover_card_shape_live() -> None:
    snap = shapes_snapshot()
    assert "hover-card" not in snap["planned_ids"]
    assert snap["next_planned"] != "hover-card"
