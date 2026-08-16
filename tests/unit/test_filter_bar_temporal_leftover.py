"""FilterBar leftover include_closed / as_of (cycle 2179).

``_emit_filter_bar`` hx-get used to be the bare endpoint +
``hx-include="closest .filter-bar"``. Valid ``include_closed`` /
``as_of`` were dropped, so a filter change invented open-only /
current. Leftover junk (zzz / 2abc / maybe / not-a-date) must not
invent. Valid true / YYYY-MM-DD must ride hx-get. Rest-state gallery
unchanged (oral #33). Not leftover search chrome / sentinel /
pagination / CSV / sort-header echo, not leftover list include_closed
clone, not related-tab as_of, not DETAIL as_of onto the edit form.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.render.fragment import URL, FilterBar, FilterColumn, FragmentRenderer
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
    / "queue_filters.py"
)
_DATE_RANGE = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "hatchi-maxchi"
    / "contracts"
    / "date_range.py"
)


def _render(include_closed: str = "", as_of: str = "") -> str:
    return FragmentRenderer().render(
        FilterBar(
            endpoint=URL("/app/x"),
            region_name="r",
            columns=(
                FilterColumn(
                    key="status",
                    label="Status",
                    options=(("open", "Open"), ("closed", "Closed")),
                ),
            ),
            include_closed=include_closed,
            as_of=as_of,
        )
    )


def _select_hx_get(html: str) -> str:
    assert 'class="dz-queue-filter-select"' in html
    chunk = html.split('class="dz-queue-filter-select"', 1)[1]
    assert "hx-get=" in chunk
    return chunk.split("hx-get=", 1)[1].split(" ", 1)[0].strip("\"'")


def test_filter_bar_echoes_leftover_honest_include_closed() -> None:
    href = _select_hx_get(_render(include_closed="true"))
    assert "include_closed=true" in href
    assert "include_closed=true" in _select_hx_get(_render(include_closed="1"))
    assert "include_closed=true" in _select_hx_get(_render(include_closed="YES"))


def test_filter_bar_echoes_leftover_honest_as_of() -> None:
    href = _select_hx_get(_render(as_of="2026-01-15"))
    assert "as_of=2026-01-15" in href


def test_filter_bar_leftover_junk_does_not_invent() -> None:
    junk_ic = _select_hx_get(_render(include_closed="zzz"))
    assert "include_closed" not in junk_ic
    assert "/app/x" in junk_ic
    assert "include_closed" not in _select_hx_get(_render(include_closed="2abc"))
    assert "include_closed" not in _select_hx_get(_render(include_closed="maybe"))
    assert "include_closed" not in _select_hx_get(_render(include_closed="false"))
    junk_ao = _select_hx_get(_render(as_of="not-a-date"))
    assert "as_of" not in junk_ao
    assert "as_of" not in _select_hx_get(_render(as_of="2abc"))
    assert "as_of" not in _select_hx_get(_render(as_of="zzz"))
    assert "as_of" not in _select_hx_get(_render(as_of="2026-13-40"))


def test_filter_bar_empty_temporal_omits() -> None:
    href = _select_hx_get(_render())
    assert "include_closed" not in href
    assert "as_of" not in href
    assert href == "/app/x"


def test_filter_bar_filters_still_ride_with_temporal() -> None:
    html = _render(include_closed="true", as_of="2026-01-15")
    href = _select_hx_get(html)
    assert "include_closed=true" in href
    assert "as_of=2026-01-15" in href
    assert 'name="filter_status"' in html
    assert 'hx-include="closest .filter-bar"' in html


def test_leftover_honest_query_helper() -> None:
    assert leftover_honest_temporal_query("true", "2026-01-15") == (
        "include_closed=true&amp;as_of=2026-01-15"
    )
    assert leftover_honest_temporal_query("zzz", "not-a-date") == ""
    assert leftover_honest_temporal_query("", "") == ""


def test_emit_source_pins_leftover_honest_echo() -> None:
    src = _EMIT.read_text(encoding="utf-8")
    emit = src.split("def _emit_filter_bar")[1].split("def _emit_list_filter_bar")[0]
    assert "hx-get=" in emit
    assert "_with_leftover_honest_temporal" in emit
    assert "include_closed" in emit
    assert "as_of" in emit
    assert "cycle 2179" in emit
    assert "must not invent" in emit


def test_builder_source_pins_leftover_honest_echo() -> None:
    src = _BUILDERS.read_text(encoding="utf-8")
    block = src.split("# FilterBar")[1].split("# DateRangePicker")[0]
    assert "FilterBar(" in block
    assert "include_closed=include_closed" in block
    assert "as_of=as_of" in block


def test_queue_filters_contract_pins_temporal_leftover_honesty() -> None:
    src = _CONTRACT.read_text(encoding="utf-8")
    assert "include_closed" in src
    assert "as_of" in src
    assert "2179" in src


def test_edit_form_still_does_not_time_travel_or_include_closed() -> None:
    """Do not clone leftover list include_closed / related-tab as_of onto edit."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    edit = src.split("async def _handle_edit_form")[1].split("async def ")[0]
    assert "_detail_as_of" not in edit
    assert "_related_tab_as_of_raw" not in edit
    assert "as_of=" not in edit
    assert "as_of_raw=" not in edit
    assert "include_closed" not in edit


def test_date_range_picker_still_drops_temporal() -> None:
    """Sibling invent class (seed next): date-range hx-get is still the
    bare endpoint — leftover-honest include_closed / as_of do not ride
    a bound change."""
    src = _DATE_RANGE.read_text(encoding="utf-8")
    bound = src.split("def _bound")[1].split("def render")[0]
    assert 'hx-get="{endpoint}"' in bound
    assert "hx-include" in bound
    assert "include_closed" not in bound
    assert "as_of" not in bound
    assert "leftover_honest" not in bound
