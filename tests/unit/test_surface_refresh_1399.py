"""#1399 slice 3 — surface-level live-refresh (`refresh: every Ns`).

Standalone list surfaces may declare ``refresh: every Ns`` to have their
HTMX-loaded ``<tbody>`` poll the existing list data endpoint every N seconds —
the surface analogue of the region primitive (#1391). Two layers:

  1. Parser — the form resolves to ``SurfaceSpec.refresh_interval`` (seconds);
     sub-5s and non-second units error (shared parser with #1391).
  2. Renderer — a `TableContext.refresh_interval` appends ``, every Ns`` to the
     tbody's ``hx-trigger``.
"""

from __future__ import annotations

import pytest

from dazzle.core.errors import ParseError
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules


def _surface(refresh_line: str, tmp_path):
    src = (
        "module t\n"
        'app t "T"\n'
        'entity Task "Task":\n'
        "  id: uuid pk\n"
        "  title: str(100)\n"
        'surface task_list "Tasks":\n'
        "  uses entity Task\n"
        "  mode: list\n"
        f"{refresh_line}"
        "  section main:\n"
        '    field title "Title"\n'
    )
    p = tmp_path / "a.dsl"
    p.write_text(src)
    appspec = build_appspec(parse_modules([p]), "t")
    return next(s for s in appspec.surfaces if s.name == "task_list")


class TestSurfaceRefreshParse:
    def test_every_seconds_suffix(self, tmp_path) -> None:
        assert _surface("  refresh: every 30s\n", tmp_path).refresh_interval == 30

    def test_every_bare_number_is_seconds(self, tmp_path) -> None:
        assert _surface("  refresh: every 30\n", tmp_path).refresh_interval == 30

    def test_bare_seconds_without_every(self, tmp_path) -> None:
        assert _surface("  refresh: 45s\n", tmp_path).refresh_interval == 45

    def test_absent_refresh_is_none(self, tmp_path) -> None:
        assert _surface("", tmp_path).refresh_interval is None

    def test_below_floor_rejected(self, tmp_path) -> None:
        with pytest.raises(ParseError, match="at least 5s"):
            _surface("  refresh: every 2s\n", tmp_path)

    def test_non_second_unit_rejected(self, tmp_path) -> None:
        with pytest.raises(ParseError, match="seconds"):
            _surface("  refresh: every 5m\n", tmp_path)


class TestSurfaceRefreshRender:
    def _table(self, *, refresh_interval=None):
        from dazzle.render.context import ColumnContext, TableContext

        return TableContext(
            entity_name="Task",
            title="Tasks",
            columns=[ColumnContext(key="title", label="Title")],
            api_endpoint="/app/task/data",
            table_id="dt",
            refresh_interval=refresh_interval,
        )

    def test_tbody_trigger_polls_when_set(self) -> None:
        from dazzle.ui.runtime.table_renderer import render_filterable_table

        html = render_filterable_table(self._table(refresh_interval=30))
        assert 'hx-trigger="load, every 30s"' in html

    def test_tbody_trigger_no_poll_by_default(self) -> None:
        from dazzle.ui.runtime.table_renderer import render_filterable_table

        html = render_filterable_table(self._table())
        assert 'hx-trigger="load"' in html
        assert "every" not in html.split("dz-table-body")[0].rsplit("<tbody", 1)[-1]
