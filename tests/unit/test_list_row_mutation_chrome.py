"""List row mutation chrome — hide delete/update when permit denies.

LAYER: L0 (emit) + permission gate

humanqa: public (anonymous) task board still painted trash + SM chips;
confirm dialog opened and the row could vanish from the painted table
even though server DELETE returned 403.
"""

from __future__ import annotations

from dazzle.render.fragment.primitives import RowCapabilities
from dazzle.render.fragment.renderer._data_row import render_data_row


def _row(**caps_kw) -> str:
    caps = RowCapabilities(drill=True, peek="off", **caps_kw)
    return render_data_row(
        ({"key": "title", "type": "str"},),
        {"id": "t1", "title": "Sample", "status": "todo"},
        caps,
        entity_name="Task",
        api_endpoint="/tasks",
        detail_url_template="/app/task/{id}",
        state_transitions=(),
        status_field="status",
        transition_endpoint="/tasks",
    )


def test_default_caps_emit_delete() -> None:
    html = _row()
    assert 'data-dazzle-action="Task.delete"' in html
    assert "hx-confirm=" in html
    assert "is-destructive" in html


def test_can_delete_false_omits_trash() -> None:
    html = _row(delete=False)
    assert "Task.delete" not in html
    assert "is-destructive" not in html
    assert "hx-delete=" not in html


def test_can_update_false_omits_edit() -> None:
    html = _row(update=False)
    assert "Task.edit" not in html
    assert "pencil" not in html or "Task.edit" not in html
    # View (eye) still present — read is allowed
    assert "Task.view" in html


def test_can_update_false_omits_transitions() -> None:
    from dazzle.render.context import TransitionContext

    caps = RowCapabilities(drill=True, update=False, delete=False)
    html = render_data_row(
        ({"key": "title", "type": "str"},),
        {"id": "t1", "title": "Sample", "status": "todo"},
        caps,
        entity_name="Task",
        api_endpoint="/tasks",
        detail_url_template="/app/task/{id}",
        state_transitions=(
            TransitionContext(
                from_state="todo",
                to_state="in_progress",
                label="In Progress",
                api_url="/tasks/{id}",
            ),
        ),
        status_field="status",
        transition_endpoint="/tasks",
    )
    assert "dz-tr-transition" not in html
    assert "In Progress" not in html
    assert "Task.delete" not in html


def test_build_data_table_threads_can_flags() -> None:
    from dazzle.http.runtime.handlers.list_handlers import build_data_table

    dt = build_data_table(
        {
            "columns": [{"key": "title", "type": "str"}],
            "entity_name": "Task",
            "api_endpoint": "/tasks",
            "detail_url_template": "/app/task/{id}",
            "can_delete": False,
            "can_update": False,
        },
        [{"id": "1", "title": "x"}],
    )
    assert dt.capabilities.delete is False
    assert dt.capabilities.update is False
