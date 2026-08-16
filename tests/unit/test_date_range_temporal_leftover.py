"""DateRangePicker leftover include_closed / as_of (cycle 2180).

``_emit_date_range_picker`` / ``render_date_range`` hx-get used to
be the bare endpoint + ``hx-include="closest .date-range-bar"``.
Valid ``include_closed`` / ``as_of`` were dropped, so a bound
change invented open-only / current. Leftover junk (zzz / 2abc /
maybe / not-a-date) must not invent. Valid true / YYYY-MM-DD must
ride hx-get. Rest-state gallery unchanged (oral #33). Not leftover
FilterBar / search chrome / sentinel / pagination / CSV /
sort-header echo, not leftover list include_closed clone, not
related-tab as_of, not DETAIL as_of onto the edit form.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.render.fragment import URL, DateRangePicker, FragmentRenderer
from dazzle.render.fragment.renderer._render_interactive import leftover_honest_temporal_query

_PAGE_ROUTES = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "page_routes.py"
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
_CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "hatchi-maxchi"
    / "contracts"
    / "date_range.py"
)
_KANBAN_EMIT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "render"
    / "fragment"
    / "renderer"
    / "_render_charts.py"
)


def _render(include_closed: str = "", as_of: str = "") -> str:
    return FragmentRenderer().render(
        DateRangePicker(
            endpoint=URL("/app/x"),
            region_name="r",
            date_from="2026-06-01",
            date_to="2026-06-30",
            include_closed=include_closed,
            as_of=as_of,
        )
    )


def _bound_hx_gets(html: str) -> list[str]:
    assert 'class="dz-date-range-input"' in html
    hrefs: list[str] = []
    rest = html
    while "hx-get=" in rest:
        rest = rest.split("hx-get=", 1)[1]
        hrefs.append(rest.split(" ", 1)[0].strip("\"'"))
    assert len(hrefs) == 2
    return hrefs


def test_date_range_echoes_leftover_honest_include_closed() -> None:
    for href in _bound_hx_gets(_render(include_closed="true")):
        assert "include_closed=true" in href
    for href in _bound_hx_gets(_render(include_closed="1")):
        assert "include_closed=true" in href
    for href in _bound_hx_gets(_render(include_closed="YES")):
        assert "include_closed=true" in href


def test_date_range_echoes_leftover_honest_as_of() -> None:
    for href in _bound_hx_gets(_render(as_of="2026-01-15")):
        assert "as_of=2026-01-15" in href


def test_date_range_leftover_junk_does_not_invent() -> None:
    for href in _bound_hx_gets(_render(include_closed="zzz")):
        assert "include_closed" not in href
        assert "/app/x" in href
    for junk in ("2abc", "maybe", "false"):
        for href in _bound_hx_gets(_render(include_closed=junk)):
            assert "include_closed" not in href
    for junk in ("not-a-date", "2abc", "zzz", "2026-13-40"):
        for href in _bound_hx_gets(_render(as_of=junk)):
            assert "as_of" not in href


def test_date_range_empty_temporal_omits() -> None:
    for href in _bound_hx_gets(_render()):
        assert "include_closed" not in href
        assert "as_of" not in href
        assert href == "/app/x"


def test_date_range_bounds_still_ride_with_temporal() -> None:
    html = _render(include_closed="true", as_of="2026-01-15")
    hrefs = _bound_hx_gets(html)
    for href in hrefs:
        assert "include_closed=true" in href
        assert "as_of=2026-01-15" in href
    assert 'name="date_from"' in html
    assert 'name="date_to"' in html
    assert 'hx-include="closest .date-range-bar"' in html
    assert 'value="2026-06-01"' in html
    assert 'value="2026-06-30"' in html


def test_leftover_honest_query_helper() -> None:
    assert leftover_honest_temporal_query("true", "2026-01-15") == (
        "include_closed=true&amp;as_of=2026-01-15"
    )
    assert leftover_honest_temporal_query("zzz", "not-a-date") == ""
    assert leftover_honest_temporal_query("", "") == ""


def test_emit_source_pins_leftover_honest_echo() -> None:
    src = _EMIT.read_text(encoding="utf-8")
    emit = src.split("def _emit_date_range_picker")[1].split("def ", 1)[0]
    assert "include_closed" in emit
    assert "as_of" in emit
    assert "cycle 2180" in emit
    assert "must not invent" in emit


def test_ingest_source_pins_leftover_fields() -> None:
    """Ingest DateRange carries leftover fields for HM schema parity;
    leftover-honest query is baked in ``_emit_date_range_picker`` so
    ``render_date_range`` does not deferred-import the renderer."""
    models = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "dazzle"
        / "render"
        / "fragment"
        / "ingest"
        / "models.py"
    ).read_text(encoding="utf-8")
    block = models.split("class DateRange")[1].split("class ListRegion")[0]
    assert "include_closed" in block
    assert "as_of" in block


def test_builder_source_pins_leftover_honest_echo() -> None:
    src = _BUILDERS.read_text(encoding="utf-8")
    block = src.split("# DateRangePicker")[1].split("# CsvExportButton")[0]
    assert "DateRangePicker(" in block
    assert "include_closed=include_closed" in block
    assert "as_of=as_of" in block


def test_date_range_contract_pins_temporal_leftover_honesty() -> None:
    src = _CONTRACT.read_text(encoding="utf-8")
    assert "include_closed" in src
    assert "as_of" in src
    assert "2180" in src
    render = src.split("def render")[1].split("def ", 1)[0] if "def render" in src else src
    assert "_leftover_honest_temporal" in render or "leftover_honest" in src


def test_edit_form_still_does_not_time_travel_or_include_closed() -> None:
    """Do not clone leftover list include_closed / related-tab as_of onto edit."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    edit = src.split("async def _handle_edit_form")[1].split("async def ")[0]
    assert "_detail_as_of" not in edit
    assert "_related_tab_as_of_raw" not in edit
    assert "as_of=" not in edit
    assert "as_of_raw=" not in edit
    assert "include_closed" not in edit


def test_kanban_load_all_now_echoes_temporal() -> None:
    """Cycle 2181 closed the 2180 seed: kanban Load all leftover-honest
    include_closed / as_of now ride expand."""
    src = _KANBAN_EMIT.read_text(encoding="utf-8")
    emit = src.split("def _emit_kanban_region")[1].split("def ", 1)[0]
    assert "_with_leftover_honest_temporal" in emit
    assert "include_closed" in emit
    assert "as_of" in emit
    assert "cycle 2181" in emit
