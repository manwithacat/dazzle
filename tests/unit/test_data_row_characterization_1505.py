"""Characterization fixtures for the rich data-table row (#1505 Phase 1).

The list-render convergence (#1505) moves the rich `dz-tr-row` rendering out of
`http/runtime/htmx_render.py::_render_table_row` into a single `render/`
substrate row-core (`render_data_row`). Phase 1 must reproduce today's output
**byte-for-byte**.

The committed `.html` fixtures froze the original `_render_table_row` output
across a capability matrix (Phase 1). Since Phase 2 deleted that legacy renderer,
`render_data_row` (the render/ substrate row-core) is now both the renderer under
test AND the fixture generator — the fixtures remain the durable byte anchor for
the rich `dz-tr-row` output (`TestRenderDataRowParity`).

Regenerate fixtures intentionally with `UPDATE_CHAR_1505=1 uv run pytest
tests/unit/test_data_row_characterization_1505.py` and inspect the diff before
committing — these bytes ARE the spec of the rich row.
"""

import os
import pathlib

import pytest

_FIXTURE_DIR = pathlib.Path(__file__).parent / "__snapshots__" / "data_row_char_1505"
_UPDATE = os.environ.get("UPDATE_CHAR_1505") == "1"

# Columns exercising every `_render_cell_display` type branch.
_COLS_ALLTYPES = [
    {"key": "name", "type": "str"},
    {"key": "owner", "type": "ref"},
    {"key": "status", "type": "badge"},
    {"key": "active", "type": "bool"},
    {"key": "amount", "type": "currency", "currency_code": "GBP"},
    {"key": "due", "type": "date"},
    {"key": "pct", "type": "percentage"},
    {"key": "ssn", "type": "sensitive"},
]
_ITEM_ALLTYPES = {
    "id": "abc-123",
    "name": "Ada",
    "owner": {"id": "o1", "name": "Grace"},
    "status": "in_progress",
    "active": True,
    "amount": 1234.5,
    "due": "2026-06-28",
    "pct": 42,
    "ssn": "123456789",
}

_BADGE_OPTS = [
    {"value": "open", "label": "Open"},
    {"value": "done", "label": "Done"},
]


def _t(**over: object) -> dict:
    base: dict = {"entity_name": "Task", "api_endpoint": "/api/tasks"}
    base.update(over)
    return base


# (label, table_dict, item) — the capability matrix.
CAP_MATRIX: list[tuple[str, dict, dict]] = [
    ("plain", _t(columns=[{"key": "name", "type": "str"}]), {"id": "abc-123", "name": "Ada"}),
    (
        "bulk",
        _t(columns=[{"key": "name", "type": "str"}], bulk_actions=True),
        {"id": "abc-123", "name": "Ada"},
    ),
    (
        "drill",
        _t(columns=[{"key": "name", "type": "str"}], detail_url_template="/tasks/{id}"),
        {"id": "abc-123", "name": "Ada"},
    ),
    (
        "inline_text",
        _t(columns=[{"key": "name", "type": "str"}], inline_editable=["name"]),
        {"id": "abc-123", "name": "Ada"},
    ),
    (
        "inline_badge",
        _t(
            columns=[{"key": "status", "type": "badge", "filter_options": _BADGE_OPTS}],
            inline_editable=["status"],
        ),
        {"id": "abc-123", "status": "open"},
    ),
    (
        "inline_bool",
        _t(columns=[{"key": "active", "type": "bool"}], inline_editable=["active"]),
        {"id": "abc-123", "active": True},
    ),
    (
        "inline_date",
        _t(columns=[{"key": "due", "type": "date"}], inline_editable=["due"]),
        {"id": "abc-123", "due": "2026-06-28"},
    ),
    ("alltypes", _t(columns=_COLS_ALLTYPES), dict(_ITEM_ALLTYPES)),
    (
        "hidden_col",
        _t(
            columns=[
                {"key": "name", "type": "str"},
                {"key": "secret", "type": "str", "hidden": True},
            ]
        ),
        {"id": "abc-123", "name": "Ada", "secret": "x"},
    ),
    (
        "combined",
        _t(
            columns=_COLS_ALLTYPES,
            bulk_actions=True,
            detail_url_template="/tasks/{id}",
            inline_editable=["name", "status"],
        ),
        dict(_ITEM_ALLTYPES),
    ),
    (
        "id_apostrophe",  # #1327 escaping case
        _t(columns=[{"key": "name", "type": "str"}]),
        {"id": "o'brien", "name": "x"},
    ),
]

_IDS = [c[0] for c in CAP_MATRIX]


def _fixture_path(label: str) -> pathlib.Path:
    return _FIXTURE_DIR / f"{label}.html"


def _caps_call(table: dict, item: dict) -> str:
    """Translate a characterization `table_dict` into the typed
    `render_data_row(columns, item, caps, ...)` call (the substrate-native
    entry) and render it."""
    from dazzle.render.fragment.primitives import RowCapabilities
    from dazzle.render.fragment.renderer._data_row import render_data_row

    caps = RowCapabilities(
        bulk_select=bool(table.get("bulk_actions")),
        inline_editable=tuple(table.get("inline_editable") or ()),
        drill=bool(table.get("detail_url_template")),
    )
    return render_data_row(
        tuple(table["columns"]),
        item,
        caps,
        entity_name=table.get("entity_name", "Item"),
        api_endpoint=table.get("api_endpoint", ""),
        detail_url_template=table.get("detail_url_template", ""),
    )


class TestRenderDataRowParity:
    """The render/ substrate row-core is the rich `dz-tr-row` source of truth;
    the committed fixtures are its durable byte anchor (#1505). `render_data_row`
    is also the fixture generator under `UPDATE_CHAR_1505=1`."""

    @pytest.mark.parametrize(("label", "table", "item"), CAP_MATRIX, ids=_IDS)
    def test_render_data_row_matches_fixture(self, label: str, table: dict, item: dict) -> None:
        rendered = _caps_call(table, item)
        path = _fixture_path(label)
        if _UPDATE:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
        assert path.exists(), f"missing fixture {path} — regenerate with UPDATE_CHAR_1505=1"
        assert rendered == path.read_text(encoding="utf-8")
