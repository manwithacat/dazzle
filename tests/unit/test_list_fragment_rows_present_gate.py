"""#1574 — rows-present list-fragment gate.

The #1573 crash (badge-column lists broken fleet-wide for 5 days) survived green
CI because the list handler swallows row-render exceptions into an HTTP-200
error row (#496 posture) and the fragment integration tests only exercised the
empty-state path. This gate closes that hole: for every declared list surface
in a representative example matrix, derive the REAL production columns
(`workspace_columns.build_surface_columns`), derive `inline_editable` with the
exact server rule (server.py C2.3), synthesise one plausible row, and render it
through the real pipeline (`build_data_table` -> `render_data_table_rows`).

Below the #496 swallow, a renderer bug raises here directly — no error-row
marker can mask it. Fast, DB-free, gate-marked. The column-producer shapes are
app-specific (the #1573 trigger was `list(enum_values)` bare strings), which is
why synthetic columns are not enough and real surfaces are walked.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.http.runtime.handlers.list_handlers import build_data_table
from dazzle.http.runtime.workspace_columns import build_surface_columns
from dazzle.render.fragment.renderer._data_row import render_data_table_rows

pytestmark = pytest.mark.gate

REPO_ROOT = Path(__file__).resolve().parents[2]

# Representative matrix, not the full fleet: these three cover the column-shape
# space (badge/enum + bool + date + ref + file + money across list surfaces)
# while keeping the gate fast. #1573 was shape-specific, not app-specific.
_APPS = ("support_tickets", "hr_records", "ops_dashboard")


def _plausible_value(col: dict[str, Any]) -> Any:
    ctype = str(col.get("type", "text"))
    opts = col.get("filter_options") or []
    if ctype == "badge":
        first = opts[0] if opts else "pending"
        return first.get("value") if isinstance(first, dict) else str(first)
    if ctype == "bool":
        return True
    if ctype == "date":
        return "2026-01-01"
    if ctype == "datetime":
        return "2026-07-16T01:30:24.001035+00:00"
    if ctype in ("number", "money", "currency"):
        return 1
    if ctype == "file":
        return f"/files/{uuid.uuid4()}/doc.pdf"
    return "x"


def _mode_is_list(surface: Any) -> bool:
    mode = getattr(surface, "mode", None)
    return (getattr(mode, "value", None) or str(mode)) == "list"


def _cases():
    for app in _APPS:
        appspec = load_project_appspec(REPO_ROOT / "examples" / app)
        entities = {e.name: e for e in appspec.domain.entities}
        enums = getattr(appspec, "enums", None)
        for surface in appspec.surfaces:
            if not _mode_is_list(surface):
                continue
            entity = entities.get(str(getattr(surface, "entity_ref", "") or ""))
            if entity is None:
                continue
            yield pytest.param(app, surface, entity, enums, id=f"{app}-{surface.name}")


@pytest.mark.parametrize(("app", "surface", "entity", "enums"), list(_cases()))
def test_list_surface_renders_a_hydrated_row(app, surface, entity, enums) -> None:
    cols = build_surface_columns(entity, surface, enums)
    if not cols:
        pytest.skip("surface projects no columns")
    # The exact C2.3 server rule (server.py) — replicated, not approximated.
    inline_editable = [
        str(c.get("key", ""))
        for c in cols
        if str(c.get("type", "")) in ("text", "bool", "badge", "date", "datetime")
        and str(c.get("key", "")) not in ("id", "created_at", "updated_at")
        and not str(c.get("key", "")).endswith("_id")
        and (str(c.get("type", "")) != "badge" or c.get("filter_options"))
    ]
    row: dict[str, Any] = {"id": str(uuid.uuid4())}
    for c in cols:
        row[str(c.get("key", ""))] = _plausible_value(c)
    table = {
        "columns": cols,
        "entity_name": entity.name,
        "api_endpoint": f"/{entity.name.lower()}s",
        "table_id": f"t-{surface.name}",
        "detail_url_template": f"/app/{entity.name.lower()}/{{id}}",
        "inline_editable": inline_editable,
    }
    html = render_data_table_rows(build_data_table(table, [row]))
    assert "dz-tr-row" in html, f"{app}/{surface.name}: hydrated row did not render"


def test_matrix_exercises_the_1573_shape() -> None:
    """Detector-liveness of the gate itself: the matrix must include at least
    one badge column with producer-shaped filter_options that lands in
    inline_editable — the exact #1573 crash shape. If example evolution ever
    drops all such columns, this fails and the matrix needs re-choosing."""
    hits = 0
    for param in _cases():
        _app, surface, entity, enums = param.values
        for c in build_surface_columns(entity, surface, enums):
            if str(c.get("type", "")) == "badge" and c.get("filter_options"):
                hits += 1
    assert hits >= 1, "no badge-with-options column in the matrix — gate lost its teeth"


def test_datetime_column_humanises_and_is_inline_editable() -> None:
    """#1597: datetime cols must not render raw ISO or stamp edit-kind=text.

    ``build_surface_columns`` keeps type=datetime; C2.3 marks the field
    inline-editable; the cell editor uses kind=date (date-time capable) while
    display is UK date+time via ``_render_cell_display``.
    """
    cols = [
        {"key": "title", "type": "text", "label": "Title"},
        {"key": "assigned_at", "type": "datetime", "label": "Assigned"},
    ]
    inline_editable = [
        str(c.get("key", ""))
        for c in cols
        if str(c.get("type", "")) in ("text", "bool", "badge", "date", "datetime")
        and str(c.get("key", "")) not in ("id", "created_at", "updated_at")
        and not str(c.get("key", "")).endswith("_id")
    ]
    assert "assigned_at" in inline_editable
    row = {
        "id": str(uuid.uuid4()),
        "title": "Task",
        "assigned_at": "2026-07-16T01:30:24.001035+00:00",
    }
    table = {
        "columns": cols,
        "entity_name": "Task",
        "api_endpoint": "/tasks",
        "table_id": "t-task_list",
        "detail_url_template": "/app/task/{id}",
        "inline_editable": inline_editable,
    }
    html = render_data_table_rows(build_data_table(table, [row]))
    # Visible cell text is humanised (raw ISO may still sit in data-dz-edit-value).
    assert ">16 Jul 2026 01:30<" in html
    assert 'data-dz-edit-kind="date"' in html  # datetime → date editor
    assert 'data-dz-grid-edit="assigned_at"' in html
    # title may still be text; assigned_at must not be
    assert 'data-dz-grid-edit="assigned_at" data-dz-edit-kind="text"' not in html
