"""Kanban overflow Load all leftover include_closed / as_of (cycle 2181).

``_emit_kanban_region`` Load all hx-get used to be
``{endpoint}?page_size={total}``. Valid ``include_closed`` / ``as_of``
were dropped, so expand invented open-only / current. Leftover junk
(zzz / 2abc / maybe / not-a-date) must not invent. Valid true /
YYYY-MM-DD must ride hx-get. Rest-state gallery unchanged (oral #33).
Not leftover DateRangePicker / FilterBar / search chrome / sentinel /
pagination / CSV / sort-header echo, not leftover list include_closed
clone, not related-tab as_of, not DETAIL as_of onto the edit form.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.primitives.data import KanbanCard, KanbanColumn, KanbanRegion
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
    / "_builders_cards.py"
)
_EMIT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "render"
    / "fragment"
    / "renderer"
    / "_render_charts.py"
)
_ADAPTER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "workspace_region_render.py"
)
_CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "hatchi-maxchi"
    / "contracts"
    / "kanban_region.py"
)
_COHORT_EMIT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "render"
    / "fragment"
    / "renderer"
    / "_render_dashboard.py"
)


def _render(include_closed: str = "", as_of: str = "") -> str:
    return FragmentRenderer().render(
        KanbanRegion(
            columns=(
                KanbanColumn(
                    label="open",
                    cards=(KanbanCard(title="One"),),
                ),
            ),
            total=5,
            endpoint="/app/x",
            include_closed=include_closed,
            as_of=as_of,
        )
    )


def _load_all_hx_get(html: str) -> str:
    assert 'class="dz-kanban-load-all"' in html
    chunk = html.split('class="dz-kanban-load-all"', 1)[1]
    assert "hx-get=" in chunk
    return chunk.split("hx-get=", 1)[1].split(" ", 1)[0].strip("\"'")


def test_kanban_load_all_echoes_leftover_honest_include_closed() -> None:
    href = _load_all_hx_get(_render(include_closed="true"))
    assert "include_closed=true" in href
    assert "include_closed=true" in _load_all_hx_get(_render(include_closed="1"))
    assert "include_closed=true" in _load_all_hx_get(_render(include_closed="YES"))


def test_kanban_load_all_echoes_leftover_honest_as_of() -> None:
    href = _load_all_hx_get(_render(as_of="2026-01-15"))
    assert "as_of=2026-01-15" in href


def test_kanban_load_all_leftover_junk_does_not_invent() -> None:
    junk_ic = _load_all_hx_get(_render(include_closed="zzz"))
    assert "include_closed" not in junk_ic
    assert "/app/x?page_size=5" in junk_ic
    assert "include_closed" not in _load_all_hx_get(_render(include_closed="2abc"))
    assert "include_closed" not in _load_all_hx_get(_render(include_closed="maybe"))
    assert "include_closed" not in _load_all_hx_get(_render(include_closed="false"))
    junk_ao = _load_all_hx_get(_render(as_of="not-a-date"))
    assert "as_of" not in junk_ao
    assert "as_of" not in _load_all_hx_get(_render(as_of="2abc"))
    assert "as_of" not in _load_all_hx_get(_render(as_of="zzz"))
    assert "as_of" not in _load_all_hx_get(_render(as_of="2026-13-40"))


def test_kanban_load_all_empty_temporal_omits() -> None:
    href = _load_all_hx_get(_render())
    assert "include_closed" not in href
    assert "as_of" not in href
    assert href == "/app/x?page_size=5"


def test_kanban_load_all_page_size_still_rides_with_temporal() -> None:
    html = _render(include_closed="true", as_of="2026-01-15")
    href = _load_all_hx_get(html)
    assert "page_size=5" in href
    assert "include_closed=true" in href
    assert "as_of=2026-01-15" in href
    assert "Showing 1 of 5" in html
    assert 'hx-target="closest [data-dz-region]"' in html


def test_leftover_honest_query_helper() -> None:
    assert leftover_honest_temporal_query("true", "2026-01-15") == (
        "include_closed=true&amp;as_of=2026-01-15"
    )
    assert leftover_honest_temporal_query("zzz", "not-a-date") == ""
    assert leftover_honest_temporal_query("", "") == ""


def test_emit_source_pins_leftover_honest_echo() -> None:
    src = _EMIT.read_text(encoding="utf-8")
    emit = src.split("def _emit_kanban_region")[1].split("def ", 1)[0]
    assert "_with_leftover_honest_temporal" in emit
    assert "include_closed" in emit
    assert "as_of" in emit
    assert "cycle 2181" in emit
    assert "must not invent" in emit


def test_builder_source_pins_leftover_honest_echo() -> None:
    src = _BUILDERS.read_text(encoding="utf-8")
    block = src.split("def _build_kanban")[1].split("def _build_profile_card")[0]
    assert "include_closed=include_closed" in block
    assert "as_of=as_of" in block
    assert "cycle 2181" in block


def test_adapter_source_pins_leftover_honest_echo() -> None:
    src = _ADAPTER.read_text(encoding="utf-8")
    block = src.split('elif display_upper == "KANBAN":')[1].split("elif display_upper ==")[0]
    assert 'adapter_ctx["include_closed"]' in block
    assert 'adapter_ctx["as_of"]' in block
    assert 'adapter_ctx["total"]' in block
    assert "cycle 2181" in block


def test_kanban_region_contract_pins_temporal_leftover_honesty() -> None:
    src = _CONTRACT.read_text(encoding="utf-8")
    assert "include_closed" in src
    assert "as_of" in src
    assert "2181" in src


def test_edit_form_still_does_not_time_travel_or_include_closed() -> None:
    """Do not clone leftover list include_closed / related-tab as_of onto edit."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    edit = src.split("async def _handle_edit_form")[1].split("async def ")[0]
    assert "_detail_as_of" not in edit
    assert "_related_tab_as_of_raw" not in edit
    assert "as_of=" not in edit
    assert "as_of_raw=" not in edit
    assert "include_closed" not in edit


def test_cohort_strip_lens_now_echoes_temporal() -> None:
    """Cycle 2182 closed the 2181 seed: cohort-strip lens leftover-honest
    include_closed / as_of now ride a lens change."""
    src = _COHORT_EMIT.read_text(encoding="utf-8")
    emit = src.split("def _emit_cohort_strip_region")[1].split("def ", 1)[0]
    assert "_with_leftover_honest_temporal" in emit
    assert "include_closed" in emit
    assert "as_of" in emit
    assert "cycle 2182" in emit
