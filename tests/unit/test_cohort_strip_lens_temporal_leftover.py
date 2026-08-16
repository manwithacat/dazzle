"""Cohort-strip lens leftover include_closed / as_of (cycle 2182).

``_emit_cohort_strip_region`` lens hx-get used to be
``{endpoint}?lens={id}``. Valid ``include_closed`` / ``as_of``
were dropped, so a lens change invented open-only / current.
Leftover junk (zzz / 2abc / maybe / not-a-date) must not invent.
Valid true / YYYY-MM-DD must ride hx-get. Rest-state gallery
unchanged (oral #33). Not leftover kanban Load all / DateRangePicker
/ FilterBar / search chrome / sentinel / pagination / CSV /
sort-header echo, not leftover list include_closed clone, not
related-tab as_of, not DETAIL as_of onto the edit form.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.htmx import URL
from dazzle.render.fragment.primitives.data import (
    CohortStripCell,
    CohortStripLensTab,
    CohortStripRegion,
)
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
    / "_render_dashboard.py"
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
    / "cohort_strip.py"
)
_CARD_RENDERER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "page"
    / "runtime"
    / "workspace_renderer.py"
)


def _render(include_closed: str = "", as_of: str = "") -> str:
    return FragmentRenderer().render(
        CohortStripRegion(
            region_name="cohort",
            endpoint=URL("/app/x"),
            lenses=(
                CohortStripLensTab(id="grade", label="Grade", is_active=True),
                CohortStripLensTab(id="attendance", label="Attendance"),
            ),
            cells=(
                CohortStripCell(
                    member_id="m1",
                    member_name="Ada",
                    primary_value="A",
                ),
            ),
            include_closed=include_closed,
            as_of=as_of,
        )
    )


def _lens_hx_get(html: str, lens_id: str = "grade") -> str:
    marker = f'data-lens-id="{lens_id}"'
    assert marker in html
    chunk = html.split(marker, 1)[1]
    assert "hx-get=" in chunk
    return chunk.split("hx-get=", 1)[1].split(" ", 1)[0].strip("\"'")


def test_cohort_lens_echoes_leftover_honest_include_closed() -> None:
    href = _lens_hx_get(_render(include_closed="true"))
    assert "include_closed=true" in href
    assert "include_closed=true" in _lens_hx_get(_render(include_closed="1"))
    assert "include_closed=true" in _lens_hx_get(_render(include_closed="YES"))


def test_cohort_lens_echoes_leftover_honest_as_of() -> None:
    href = _lens_hx_get(_render(as_of="2026-01-15"))
    assert "as_of=2026-01-15" in href


def test_cohort_lens_leftover_junk_does_not_invent() -> None:
    junk_ic = _lens_hx_get(_render(include_closed="zzz"))
    assert "include_closed" not in junk_ic
    assert "/app/x?lens=grade" in junk_ic
    assert "include_closed" not in _lens_hx_get(_render(include_closed="2abc"))
    assert "include_closed" not in _lens_hx_get(_render(include_closed="maybe"))
    assert "include_closed" not in _lens_hx_get(_render(include_closed="false"))
    junk_ao = _lens_hx_get(_render(as_of="not-a-date"))
    assert "as_of" not in junk_ao
    assert "as_of" not in _lens_hx_get(_render(as_of="2abc"))
    assert "as_of" not in _lens_hx_get(_render(as_of="zzz"))
    assert "as_of" not in _lens_hx_get(_render(as_of="2026-13-40"))


def test_cohort_lens_empty_temporal_omits() -> None:
    href = _lens_hx_get(_render())
    assert "include_closed" not in href
    assert "as_of" not in href
    assert href == "/app/x?lens=grade"


def test_cohort_lens_id_still_rides_with_temporal() -> None:
    html = _render(include_closed="true", as_of="2026-01-15")
    href = _lens_hx_get(html)
    assert "lens=grade" in href
    assert "include_closed=true" in href
    assert "as_of=2026-01-15" in href
    other = _lens_hx_get(html, "attendance")
    assert "lens=attendance" in other
    assert "include_closed=true" in other
    assert "as_of=2026-01-15" in other
    assert 'hx-target="#region-cohort-body"' in html


def test_leftover_honest_query_helper() -> None:
    assert leftover_honest_temporal_query("true", "2026-01-15") == (
        "include_closed=true&amp;as_of=2026-01-15"
    )
    assert leftover_honest_temporal_query("zzz", "not-a-date") == ""
    assert leftover_honest_temporal_query("", "") == ""


def test_emit_source_pins_leftover_honest_echo() -> None:
    src = _EMIT.read_text(encoding="utf-8")
    emit = src.split("def _emit_cohort_strip_region")[1].split("def ", 1)[0]
    assert "_with_leftover_honest_temporal" in emit
    assert "include_closed" in emit
    assert "as_of" in emit
    assert "cycle 2182" in emit
    assert "must not invent" in emit


def test_builder_source_pins_leftover_honest_echo() -> None:
    src = _BUILDERS.read_text(encoding="utf-8")
    block = src.split("def _build_cohort_strip")[1].split("def _build_entity_card")[0]
    assert "include_closed=include_closed" in block
    assert "as_of=as_of" in block
    assert "cycle 2182" in block


def test_adapter_source_pins_leftover_honest_echo() -> None:
    src = _ADAPTER.read_text(encoding="utf-8")
    block = src.split('if display_upper == "COHORT_STRIP":')[1].split("elif display_upper ==")[0]
    assert 'adapter_ctx["include_closed"]' in block
    assert 'adapter_ctx["as_of"]' in block
    assert "cycle 2182" in block


def test_cohort_strip_contract_pins_temporal_leftover_honesty() -> None:
    src = _CONTRACT.read_text(encoding="utf-8")
    assert "include_closed" in src
    assert "as_of" in src
    assert "2182" in src


def test_edit_form_still_does_not_time_travel_or_include_closed() -> None:
    """Do not clone leftover list include_closed / related-tab as_of onto edit."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    edit = src.split("async def _handle_edit_form")[1].split("async def ")[0]
    assert "_detail_as_of" not in edit
    assert "_related_tab_as_of_raw" not in edit
    assert "as_of=" not in edit
    assert "as_of_raw=" not in edit
    assert "include_closed" not in edit


def test_dashboard_card_now_echoes_temporal() -> None:
    """Cycle 2183 closed the 2182 seed: dashboard-card leftover-honest
    include_closed / as_of now ride SSE / poll / lazy-load refresh."""
    src = _CARD_RENDERER.read_text(encoding="utf-8")
    assert 'hx_endpoint=f"/api/workspaces/{workspace.name}/regions/{r.name}"' in src
    emit = _EMIT.read_text(encoding="utf-8")
    card = emit.split("def _emit_dashboard_card")[1].split("def _emit_cohort_strip_region")[0]
    assert "_with_leftover_honest_temporal" in card
    assert "include_closed" in card
    assert "as_of" in card
    assert "cycle 2183" in card
