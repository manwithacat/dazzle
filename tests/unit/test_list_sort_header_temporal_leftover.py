"""List-region sort-header leftover include_closed / as_of (cycle 2172).

``_emit_sort_header`` hx-get used to be ``?sort=&dir=`` only. Valid
``include_closed`` / ``as_of`` were dropped, so a sort click invented
open-only / current. Leftover junk (zzz / 2abc / maybe / not-a-date)
must not invent. Valid true / YYYY-MM-DD must ride hx-get. Gallery
mock must echo the same and must not treat them as field filters.
Not leftover list include_closed clone, not related-tab as_of, not
DETAIL as_of onto the edit form.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.http.runtime.renderers.fragment_adapter import _build_column_header
from dazzle.render.fragment import URL, FragmentRenderer, SortHeader

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
_MOCK = (
    Path(__file__).resolve().parents[2] / "packages" / "hatchi-maxchi" / "site" / "build_site.py"
)
_CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "hatchi-maxchi"
    / "contracts"
    / "sort_header.py"
)


def _render(include_closed: str = "", as_of: str = "") -> str:
    sh = SortHeader(
        label="Name",
        column_key="name",
        endpoint=URL("/app/x"),
        region_name="r",
        include_closed=include_closed,
        as_of=as_of,
    )
    return FragmentRenderer().render(sh)


def test_sort_header_echoes_leftover_honest_include_closed() -> None:
    html = _render(include_closed="true")
    assert "sort=name" in html
    assert "include_closed=true" in html
    assert _render(include_closed="1").count("include_closed=true") == 1
    assert _render(include_closed="YES").count("include_closed=true") == 1


def test_sort_header_echoes_leftover_honest_as_of() -> None:
    html = _render(as_of="2026-01-15")
    assert "as_of=2026-01-15" in html


def test_sort_header_leftover_junk_does_not_invent() -> None:
    junk_ic = _render(include_closed="zzz")
    assert "include_closed" not in junk_ic
    assert "sort=name" in junk_ic
    assert "include_closed" not in _render(include_closed="2abc")
    assert "include_closed" not in _render(include_closed="maybe")
    assert "include_closed" not in _render(include_closed="false")
    junk_ao = _render(as_of="not-a-date")
    assert "as_of" not in junk_ao
    assert "as_of" not in _render(as_of="2abc")
    assert "as_of" not in _render(as_of="zzz")
    assert "as_of" not in _render(as_of="2026-13-40")


def test_sort_header_empty_temporal_omits() -> None:
    html = _render()
    assert "include_closed" not in html
    assert "as_of" not in html
    assert "sort=name" in html and "dir=asc" in html


def test_build_column_header_threads_leftover_honest_temporal() -> None:
    h = _build_column_header(
        col={"key": "name", "label": "Name", "sortable": True},
        endpoint="/app/x",
        region_name="r",
        current_sort="",
        current_direction="asc",
        include_closed="true",
        as_of="2026-01-15",
    )
    assert isinstance(h, SortHeader)
    assert h.include_closed == "true"
    assert h.as_of == "2026-01-15"


def test_emit_sort_header_source_pins_leftover_honest_echo() -> None:
    src = _EMIT.read_text(encoding="utf-8")
    assert "include_closed=true" in src
    assert "as_of=" in src
    assert "cycle 2172" in src
    assert "must not invent" in src or "invented open-only" in src


def test_gallery_mock_echoes_leftover_honest_temporal() -> None:
    src = _MOCK.read_text(encoding="utf-8")
    assert "LIST_CONTROL" in src
    assert "include_closed: 1" in src
    assert "as_of: 1" in src
    assert "leftoverHonestIncludeClosed" in src
    assert "leftoverHonestAsOf" in src
    assert "cycle 2172" in src


def test_sort_header_contract_pins_temporal_leftover_honesty() -> None:
    src = _CONTRACT.read_text(encoding="utf-8")
    assert "include_closed" in src
    assert "as_of" in src
    assert "2172" in src


def test_edit_form_still_does_not_time_travel_or_include_closed() -> None:
    """Do not clone leftover list include_closed / related-tab as_of onto edit."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    edit = src.split("async def _handle_edit_form")[1].split("async def ")[0]
    assert "_detail_as_of" not in edit
    assert "_related_tab_as_of_raw" not in edit
    assert "as_of=" not in edit
    assert "as_of_raw=" not in edit
    assert "include_closed" not in edit
