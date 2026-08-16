"""List-region pagination leftover include_closed / as_of (cycle 2175).

``_emit_pagination`` hx-get used to be ``?page=&page_size=`` +
``extra_query``. Valid ``include_closed`` / ``as_of`` were dropped,
so a page click invented open-only / current. Leftover junk (zzz /
2abc / maybe / not-a-date) must not invent. Valid true / YYYY-MM-DD
must ride hx-get. Rest-state gallery omits them (oral #33). Not
leftover CSV / sort-header echo, not leftover list include_closed
clone, not related-tab as_of, not DETAIL as_of onto the edit form.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.render.fragment import URL, FragmentRenderer, Pagination
from dazzle.render.fragment.renderer._render_interactive import leftover_honest_temporal_query

_PAGE_ROUTES = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "page_routes.py"
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
_HTMX = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "htmx_render.py"
)
_CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "hatchi-maxchi"
    / "contracts"
    / "pagination.py"
)


def _render(include_closed: str = "", as_of: str = "", extra_query: str = "") -> str:
    p = Pagination(
        region_name="t",
        endpoint=URL("/app/x"),
        total=100,
        page=2,
        page_size=10,
        extra_query=extra_query,
        include_closed=include_closed,
        as_of=as_of,
    )
    return FragmentRenderer().render(p)


def test_pagination_echoes_leftover_honest_include_closed() -> None:
    html = _render(include_closed="true")
    assert "page=" in html
    assert "include_closed=true" in html
    assert _render(include_closed="1").count("include_closed=true") >= 5
    assert _render(include_closed="YES").count("include_closed=true") >= 5


def test_pagination_echoes_leftover_honest_as_of() -> None:
    html = _render(as_of="2026-01-15")
    assert "as_of=2026-01-15" in html
    assert html.count("as_of=2026-01-15") >= 5


def test_pagination_leftover_junk_does_not_invent() -> None:
    junk_ic = _render(include_closed="zzz")
    assert "include_closed" not in junk_ic
    assert "page=1" in junk_ic
    assert "include_closed" not in _render(include_closed="2abc")
    assert "include_closed" not in _render(include_closed="maybe")
    assert "include_closed" not in _render(include_closed="false")
    junk_ao = _render(as_of="not-a-date")
    assert "as_of" not in junk_ao
    assert "as_of" not in _render(as_of="2abc")
    assert "as_of" not in _render(as_of="zzz")
    assert "as_of" not in _render(as_of="2026-13-40")


def test_pagination_empty_temporal_omits() -> None:
    html = _render()
    assert "include_closed" not in html
    assert "as_of" not in html
    assert "page=1" in html and "page_size=10" in html


def test_pagination_extra_query_still_rides_with_temporal() -> None:
    html = _render(
        include_closed="true",
        as_of="2026-01-15",
        extra_query="&sort=name&dir=asc",
    )
    assert "&amp;sort=name&amp;dir=asc" in html
    assert "include_closed=true" in html
    assert "as_of=2026-01-15" in html


def test_leftover_honest_query_helper() -> None:
    assert leftover_honest_temporal_query("true", "2026-01-15") == (
        "include_closed=true&amp;as_of=2026-01-15"
    )
    assert leftover_honest_temporal_query("zzz", "not-a-date") == ""
    assert leftover_honest_temporal_query("", "") == ""


def test_emit_pagination_source_pins_leftover_honest_echo() -> None:
    src = _EMIT.read_text(encoding="utf-8")
    assert "include_closed=true" in src
    assert "as_of=" in src
    assert "cycle 2175" in src
    assert "must not invent" in src or "invented open-only" in src
    assert "_with_leftover_honest_temporal" in src


def test_pagination_contract_pins_temporal_leftover_honesty() -> None:
    src = _CONTRACT.read_text(encoding="utf-8")
    assert "include_closed" in src
    assert "as_of" in src
    assert "2175" in src


def test_edit_form_still_does_not_time_travel_or_include_closed() -> None:
    """Do not clone leftover list include_closed / related-tab as_of onto edit."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    edit = src.split("async def _handle_edit_form")[1].split("async def ")[0]
    assert "_detail_as_of" not in edit
    assert "_related_tab_as_of_raw" not in edit
    assert "as_of=" not in edit
    assert "as_of_raw=" not in edit
    assert "include_closed" not in edit


def test_sentinel_url_params_now_echo_temporal() -> None:
    """Closed 2177: infinite-scroll sentinel leftover-honest echo.
    Sibling invent class moved to test_list_sentinel_temporal_leftover."""
    src = _HTMX.read_text(encoding="utf-8")
    assert "def _build_table_url_params" in src
    builder = src.split("def _build_table_url_params")[1].split("def ")[0]
    assert "include_closed" in builder
    assert "as_of" in builder
    assert "leftover_honest_temporal_query" in builder
