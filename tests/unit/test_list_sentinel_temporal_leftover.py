"""Infinite-scroll sentinel leftover include_closed / as_of (cycle 2177).

``_build_table_url_params`` used to be ``page=&page_size=`` +
sort/filter/search. Valid ``include_closed`` / ``as_of`` were dropped,
so load-more invented open-only / current. Leftover junk (zzz /
2abc / maybe / not-a-date) must not invent. Valid true / YYYY-MM-DD
must ride the sentinel hx-get. Rest-state gallery unchanged (oral #33).
Not leftover pagination / CSV / sort-header echo, not leftover list
include_closed clone, not related-tab as_of, not DETAIL as_of onto
the edit form.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.http.runtime.htmx_render import _build_table_url_params, _render_table_sentinel
from dazzle.render.fragment.renderer._render_interactive import leftover_honest_temporal_query

_PAGE_ROUTES = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "page_routes.py"
)
_HTMX = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "htmx_render.py"
)
_HANDLERS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "handlers"
    / "list_handlers.py"
)
_BUILDERS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "render"
    / "fragment"
    / "region"
    / "_builders_tables.py"
)
_EMIT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "render"
    / "fragment"
    / "renderer"
    / "_render_interactive.py"
)


def _table(
    *,
    include_closed: str = "",
    as_of: str = "",
    sort_field: str = "",
    sort_dir: str = "asc",
    search_query: str = "",
    filter_values: dict[str, str] | None = None,
    page: int = 1,
    page_size: int = 10,
    total: int = 100,
) -> dict[str, object]:
    return {
        "include_closed": include_closed,
        "as_of": as_of,
        "sort_field": sort_field,
        "sort_dir": sort_dir,
        "search_query": search_query,
        "filter_values": filter_values or {},
        "page": page,
        "page_size": page_size,
        "total": total,
        "columns": [{"key": "name"}],
        "table_id": "dt-x",
        "api_endpoint": "/api/x",
    }


def test_sentinel_echoes_leftover_honest_include_closed() -> None:
    qs = _build_table_url_params(_table(include_closed="true"), 2)
    assert "page=2" in qs
    assert "include_closed=true" in qs
    assert "include_closed=true" in _build_table_url_params(_table(include_closed="1"), 2)
    assert "include_closed=true" in _build_table_url_params(_table(include_closed="YES"), 2)


def test_sentinel_echoes_leftover_honest_as_of() -> None:
    qs = _build_table_url_params(_table(as_of="2026-01-15"), 2)
    assert "as_of=2026-01-15" in qs


def test_sentinel_leftover_junk_does_not_invent() -> None:
    junk_ic = _build_table_url_params(_table(include_closed="zzz"), 2)
    assert "include_closed" not in junk_ic
    assert "page=2" in junk_ic
    assert "include_closed" not in _build_table_url_params(_table(include_closed="2abc"), 2)
    assert "include_closed" not in _build_table_url_params(_table(include_closed="maybe"), 2)
    assert "include_closed" not in _build_table_url_params(_table(include_closed="false"), 2)
    junk_ao = _build_table_url_params(_table(as_of="not-a-date"), 2)
    assert "as_of" not in junk_ao
    assert "as_of" not in _build_table_url_params(_table(as_of="2abc"), 2)
    assert "as_of" not in _build_table_url_params(_table(as_of="zzz"), 2)
    assert "as_of" not in _build_table_url_params(_table(as_of="2026-13-40"), 2)


def test_sentinel_empty_temporal_omits() -> None:
    qs = _build_table_url_params(_table(), 2)
    assert "include_closed" not in qs
    assert "as_of" not in qs
    assert "page=2" in qs and "page_size=10" in qs


def test_sentinel_sort_filter_still_ride_with_temporal() -> None:
    qs = _build_table_url_params(
        _table(
            include_closed="true",
            as_of="2026-01-15",
            sort_field="name",
            sort_dir="asc",
            filter_values={"status": "open"},
        ),
        3,
    )
    assert "sort=name" in qs
    assert "dir=asc" in qs
    assert "filter[status]=open" in qs
    assert "include_closed=true" in qs
    assert "as_of=2026-01-15" in qs


def test_sentinel_html_hx_get_rides_temporal() -> None:
    html = _render_table_sentinel(_table(include_closed="true", as_of="2026-01-15"))
    assert "hx-get=" in html
    assert "include_closed=true" in html
    assert "as_of=2026-01-15" in html
    assert "page=2" in html
    junk = _render_table_sentinel(_table(include_closed="zzz", as_of="not-a-date"))
    assert "include_closed" not in junk
    assert "as_of" not in junk
    assert "page=2" in junk


def test_leftover_honest_query_helper() -> None:
    assert leftover_honest_temporal_query("true", "2026-01-15") == (
        "include_closed=true&amp;as_of=2026-01-15"
    )
    assert leftover_honest_temporal_query("zzz", "not-a-date") == ""
    assert leftover_honest_temporal_query("", "") == ""


def test_builder_source_pins_leftover_honest_echo() -> None:
    src = _HTMX.read_text(encoding="utf-8")
    assert "def _build_table_url_params" in src
    builder = src.split("def _build_table_url_params")[1].split("def ")[0]
    assert "include_closed" in builder
    assert "as_of" in builder
    assert "leftover_honest_temporal_query" in builder
    assert "cycle 2177" in src
    assert "must not invent" in src


def test_list_handlers_thread_raw_temporal_onto_table() -> None:
    src = _HANDLERS.read_text(encoding="utf-8")
    table = src.split("table_dict = {")[1].split("}", 1)[0]
    assert '"include_closed"' in table
    assert '"as_of"' in table
    assert "query_params.get" in table
    assert "cycle 2177" in src


def test_emit_helper_doc_pins_sentinel_cycle() -> None:
    src = _EMIT.read_text(encoding="utf-8")
    helper = src.split("def leftover_honest_temporal_query")[1].split("def ")[0]
    assert "cycle 2177" in helper


def test_edit_form_still_does_not_time_travel_or_include_closed() -> None:
    """Do not clone leftover list include_closed / related-tab as_of onto edit."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    edit = src.split("async def _handle_edit_form")[1].split("async def ")[0]
    assert "_detail_as_of" not in edit
    assert "_related_tab_as_of_raw" not in edit
    assert "as_of=" not in edit
    assert "as_of_raw=" not in edit
    assert "include_closed" not in edit


def test_list_search_chrome_still_drops_temporal() -> None:
    """Sibling invent class (seed next): list search chrome
    ``hx-get="{ep}"`` + ``hx-include="closest .filter-bar"`` still
    omits leftover-honest include_closed / as_of."""
    src = _BUILDERS.read_text(encoding="utf-8")
    assert "dz-list-search-chrome" in src
    search = src.split("dz-list-search-chrome")[1].split("# FilterBar")[0]
    assert "hx-get=" in search
    assert 'hx-get="{ep}"' in search
    assert "include_closed" not in search
    assert "as_of" not in search
    assert "leftover_honest" not in search
