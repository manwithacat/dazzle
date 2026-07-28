"""Linear-class kanban rearrange — permit gate, SM edges, dual-lock attrs.

Design: docs/superpowers/specs/2026-07-28-kanban-rearrange-htmx-design.md
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from dazzle.http.runtime.workspace_region_computes import compute_kanban_rearrange
from dazzle.http.runtime.workspace_region_orchestration import (
    gate_kanban_rearrange_for_principal,
)
from dazzle.render.fragment.ingest.emit import kanban_card_root_attrs, render_kanban_card
from dazzle.render.fragment.ingest.models import KanbanCard as KanbanCardSeam
from dazzle.render.fragment.primitives.data import KanbanCard, KanbanColumn, KanbanRegion
from dazzle.render.fragment.region._builders_cards import _BuildersCardsMixin

pytestmark = pytest.mark.gate


class _FakeRegion:
    name = "board"
    title = "Board"
    empty_message = None


def test_gate_clears_rearrange_when_update_denied() -> None:
    with patch(
        "dazzle.http.runtime.workspace_region_orchestration._principal_can_op",
        return_value=False,
    ):
        assert (
            gate_kanban_rearrange_for_principal("status", object(), object(), entity_name="Task")
            == ""
        )


def test_gate_keeps_status_when_update_allowed() -> None:
    with patch(
        "dazzle.http.runtime.workspace_region_orchestration._principal_can_op",
        return_value=True,
    ):
        assert (
            gate_kanban_rearrange_for_principal("status", object(), object(), entity_name="Task")
            == "status"
        )


def test_gate_ignores_unknown_mode() -> None:
    assert gate_kanban_rearrange_for_principal("nope", object(), object()) == ""


def test_compute_rearrange_manual_sm_edges_only() -> None:
    """AUTO edges never appear in allowed_to (R3)."""
    auto = SimpleNamespace(to_state="archived", trigger=SimpleNamespace(value="auto"))
    manual = SimpleNamespace(to_state="in_progress", trigger=SimpleNamespace(value="manual"))
    sm = SimpleNamespace(
        status_field="status",
        get_transitions_from=lambda state: [auto, manual] if state == "todo" else [],
    )
    entity = SimpleNamespace(state_machine=sm)
    items = [{"id": "t1", "status": "todo"}]
    mode, field, api, allowed = compute_kanban_rearrange(entity, "status", "Task", items)
    assert mode == "status"
    assert field == "status"
    assert api == "/tasks"
    assert allowed["t1"] == ("in_progress",)


def test_compute_rearrange_free_enum_empty_map() -> None:
    """No SM → rearrange mode on, empty map (builder fills any-other-column)."""
    entity = SimpleNamespace(state_machine=None, fields=[])
    mode, field, api, allowed = compute_kanban_rearrange(
        entity, "stage", "Deal", [{"id": "1", "stage": "a"}]
    )
    assert mode == "status"
    assert field == "stage"
    assert api == "/deals"
    assert allowed == {}


def test_card_render_read_only_no_rearrange_attrs() -> None:
    html = render_kanban_card(KanbanCardSeam(title="Locked", fields_html="", drill_url=""))
    assert "data-dz-kanban-card" in html
    assert "data-dz-entity-id" not in html
    assert "draggable" not in html
    assert "data-dz-kanban-move" not in html


def test_card_render_stamps_allowed_and_move_select() -> None:
    html = render_kanban_card(
        KanbanCardSeam(
            title="Work",
            fields_html="",
            row_id="abc",
            from_state="todo",
            allowed_to=("in_progress", "done"),
        )
    )
    assert 'data-dz-entity-id="abc"' in html
    assert 'data-dz-from-state="todo"' in html
    assert 'data-dz-allowed-to="in_progress done"' in html
    assert 'draggable="true"' in html
    assert 'id="dz-kanban-card-abc"' in html
    assert "data-dz-kanban-move" in html
    assert 'value="in_progress"' in html


def test_kanban_card_root_attrs_sole_emitter() -> None:
    attrs = kanban_card_root_attrs(
        KanbanCardSeam(title="X", row_id="1", from_state="a", allowed_to=("b",))
    )
    assert attrs.startswith("data-dz-kanban-card")
    assert "data-dz-entity-id" in attrs
    assert "draggable" in attrs


def test_builder_rearrange_stamps_board_and_cards() -> None:
    from dazzle.render.fragment.renderer import FragmentRenderer

    class B(_BuildersCardsMixin):
        pass

    builder = B()
    ctx = {
        "items": [
            {"id": "1", "title": "A", "status": "todo"},
            {"id": "2", "title": "B", "status": "todo"},
        ],
        "kanban_columns": ["todo", "in_progress", "done"],
        "group_by": "status",
        "display_key": "title",
        "entity_name": "Task",
        "endpoint": "/ws/board",
        "kanban_rearrange": "status",
        "kanban_status_field": "status",
        "kanban_api_endpoint": "/tasks",
        "kanban_refresh_src": "/ws/board",
        "kanban_allowed_by_id": {
            "1": ("in_progress",),
            "2": ("in_progress", "done"),
        },
    }
    surface = builder._build_kanban(_FakeRegion(), ctx)
    html = FragmentRenderer().render(surface)
    assert 'data-dz-kanban-rearrange="status"' in html
    assert 'data-dz-kanban-api="/tasks"' in html
    assert 'data-dz-to-state="in_progress"' in html
    assert 'data-dz-entity-id="1"' in html
    assert 'data-dz-allowed-to="in_progress"' in html
    assert 'data-dz-allowed-to="in_progress done"' in html
    assert "data-dz-kanban-announce" in html


def test_builder_read_only_board_has_no_rearrange() -> None:
    from dazzle.render.fragment.renderer import FragmentRenderer

    class B(_BuildersCardsMixin):
        pass

    surface = B()._build_kanban(
        _FakeRegion(),
        {
            "items": [{"id": "1", "title": "A", "status": "todo"}],
            "kanban_columns": ["todo", "done"],
            "group_by": "status",
            "display_key": "title",
            "entity_name": "Task",
            "endpoint": "/ws/board",
            # no kanban_rearrange
        },
    )
    html = FragmentRenderer().render(surface)
    assert "data-dz-kanban-rearrange" not in html
    assert "draggable" not in html
    assert "data-dz-entity-id" not in html


def test_region_primitive_fields_default_off() -> None:
    region = KanbanRegion(columns=(KanbanColumn(label="todo", cards=()),))
    assert region.rearrange == ""
    assert region.api_endpoint == ""
    card = KanbanCard(title="x")
    assert card.allowed_to == ()
    assert card.row_id == ""
