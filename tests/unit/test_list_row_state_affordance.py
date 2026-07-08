"""#1558 (3c): regular list rows offer only the transitions valid from that
row's current state, in the row actions cell."""

from dazzle.render.context import TransitionContext
from dazzle.render.fragment.renderer._data_row import _render_table_row


def _t(frm, to):
    # Label formatting mirrors the compile build: to_state -> "Title Case".
    return TransitionContext(
        from_state=frm,
        to_state=to,
        label=to.replace("_", " ").title(),
        api_url="/api/tickets/{id}",
    )


def _table(**over):
    base = {
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "entity_name": "Ticket",
        "state_transitions": (_t("open", "in_progress"), _t("in_progress", "resolved")),
        "status_field": "status",
        "transition_endpoint": "/api/tickets",
    }
    base.update(over)
    return base


def test_row_shows_only_current_state_transitions():
    html = _render_table_row(_table(), {"id": "1", "title": "T", "status": "open"})
    assert "In Progress" in html  # open -> in_progress valid from open
    assert "Resolved" not in html  # in_progress -> resolved NOT valid from open
    assert 'hx-put="/api/tickets/1"' in html


def test_row_in_later_state_shows_its_transitions():
    html = _render_table_row(_table(), {"id": "9", "title": "T", "status": "in_progress"})
    assert "Resolved" in html
    assert "In Progress" not in html


def test_row_without_state_machine_has_no_transition_buttons():
    html = _render_table_row(
        {"columns": [{"key": "title", "label": "Title", "type": "text"}], "entity_name": "Ticket"},
        {"id": "1", "title": "T", "status": "open"},
    )
    assert "hx-put" not in html  # byte-identical: no state transitions rendered


def test_unknown_state_shows_no_transitions():
    html = _render_table_row(_table(), {"id": "1", "title": "T", "status": ""})
    assert "hx-put" not in html


# ── sourcing + end-to-end (build_data_table -> render) ──────────────────────

from types import SimpleNamespace  # noqa: E402

from dazzle.core.strings import to_api_plural  # noqa: E402
from dazzle.http.runtime.handlers.list_handlers import (  # noqa: E402
    build_data_table,
    list_state_transitions,
)
from dazzle.render.fragment.renderer._data_row import render_data_table_rows  # noqa: E402


def _entity_with_sm():
    sm = SimpleNamespace(
        status_field="status",
        transitions=[
            SimpleNamespace(from_state="open", to_state="in_progress"),
            SimpleNamespace(from_state="in_progress", to_state="resolved"),
        ],
    )
    return SimpleNamespace(state_machine=sm, name="Ticket")


def test_list_state_transitions_sources_with_from_state():
    tx, sf, ep = list_state_transitions(_entity_with_sm(), "Ticket")
    assert sf == "status"
    assert ep == f"/{to_api_plural('Ticket')}"
    assert [(t.from_state, t.to_state) for t in tx] == [
        ("open", "in_progress"),
        ("in_progress", "resolved"),
    ]


def test_list_state_transitions_no_state_machine():
    assert list_state_transitions(SimpleNamespace(state_machine=None), "X") == ((), "", "")


def test_build_data_table_to_rows_end_to_end():
    tx, sf, ep = list_state_transitions(_entity_with_sm(), "Ticket")
    table_dict = {
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "entity_name": "Ticket",
        "state_transitions": tx,
        "status_field": sf,
        "transition_endpoint": ep,
    }
    dt = build_data_table(table_dict, [{"id": "7", "title": "T", "status": "open"}])
    html = render_data_table_rows(dt)
    assert "In Progress" in html and "Resolved" not in html
    assert f'hx-put="{ep}/7"' in html
