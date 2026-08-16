"""List search chrome leftover include_closed / as_of (cycle 2178).

``_builders_tables`` search ``hx-get="{ep}"`` +
``hx-include="closest .filter-bar"`` used to drop leftover-honest
``include_closed`` / ``as_of``, so typeahead invented open-only /
current. Leftover junk (zzz / 2abc / maybe / not-a-date) must not
invent. Valid true / YYYY-MM-DD must ride find. Rest-state gallery
unchanged (oral #33). Not leftover sentinel / pagination / CSV /
sort-header echo, not leftover list include_closed clone, not
related-tab as_of, not DETAIL as_of onto the edit form.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer
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
_WORKSPACE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "workspace_region_render.py"
)


class _FakeRegion:
    def __init__(self, name: str = "tasks") -> None:
        self.name = name
        self.title = None
        self.display = "list"
        self.empty_message = None
        self.row_action = None


def _ctx(
    *,
    include_closed: str = "",
    as_of: str = "",
    search_fields: list[str] | None = None,
    active_search: str = "",
) -> dict[str, object]:
    return {
        "items": [{"id": "1", "name": "Ada"}],
        "columns": [{"key": "name", "label": "Name", "type": "text"}],
        "endpoint": "/app/x",
        "region_name": "tasks",
        "search_fields": search_fields if search_fields is not None else ["name"],
        "active_search": active_search,
        "include_closed": include_closed,
        "as_of": as_of,
    }


def _render(**kwargs: object) -> str:
    return FragmentRenderer().render(
        WorkspaceRegionAdapter().build(_FakeRegion(), _ctx(**kwargs))  # type: ignore[arg-type]
    )


def _search_hx_get(html: str) -> str:
    marker = "data-dz-list-search-input"
    assert marker in html
    chunk = html.split(marker, 1)[1]
    assert "hx-get=" in chunk
    return chunk.split("hx-get=", 1)[1].split(" ", 1)[0].strip("\"'")


def test_search_chrome_echoes_leftover_honest_include_closed() -> None:
    html = _render(include_closed="true")
    href = _search_hx_get(html)
    assert "include_closed=true" in href
    assert "include_closed=true" in _search_hx_get(_render(include_closed="1"))
    assert "include_closed=true" in _search_hx_get(_render(include_closed="YES"))


def test_search_chrome_echoes_leftover_honest_as_of() -> None:
    href = _search_hx_get(_render(as_of="2026-01-15"))
    assert "as_of=2026-01-15" in href


def test_search_chrome_leftover_junk_does_not_invent() -> None:
    junk_ic = _search_hx_get(_render(include_closed="zzz"))
    assert "include_closed" not in junk_ic
    assert "/app/x" in junk_ic
    assert "include_closed" not in _search_hx_get(_render(include_closed="2abc"))
    assert "include_closed" not in _search_hx_get(_render(include_closed="maybe"))
    assert "include_closed" not in _search_hx_get(_render(include_closed="false"))
    junk_ao = _search_hx_get(_render(as_of="not-a-date"))
    assert "as_of" not in junk_ao
    assert "as_of" not in _search_hx_get(_render(as_of="2abc"))
    assert "as_of" not in _search_hx_get(_render(as_of="zzz"))
    assert "as_of" not in _search_hx_get(_render(as_of="2026-13-40"))


def test_search_chrome_empty_temporal_omits() -> None:
    href = _search_hx_get(_render())
    assert "include_closed" not in href
    assert "as_of" not in href
    assert href == "/app/x"


def test_search_chrome_q_still_rides_with_temporal() -> None:
    html = _render(
        include_closed="true",
        as_of="2026-01-15",
        active_search="ada",
    )
    href = _search_hx_get(html)
    assert "include_closed=true" in href
    assert "as_of=2026-01-15" in href
    assert 'name="q"' in html
    assert 'value="ada"' in html
    assert 'hx-include="closest .filter-bar"' in html


def test_leftover_honest_query_helper() -> None:
    assert leftover_honest_temporal_query("true", "2026-01-15") == (
        "include_closed=true&amp;as_of=2026-01-15"
    )
    assert leftover_honest_temporal_query("zzz", "not-a-date") == ""
    assert leftover_honest_temporal_query("", "") == ""


def test_builder_source_pins_leftover_honest_echo() -> None:
    src = _BUILDERS.read_text(encoding="utf-8")
    assert "dz-list-search-chrome" in src
    search = src.split("# Free-text list search")[1].split("# FilterBar")[0]
    assert "hx-get=" in search
    assert "hx_get" in search
    assert "leftover_honest_temporal_query" in search
    assert "include_closed" in search
    assert "as_of" in search
    assert "cycle 2178" in search
    assert "must not invent" in search


def test_workspace_ctx_still_threads_raw_temporal() -> None:
    src = _WORKSPACE.read_text(encoding="utf-8")
    assert 'adapter_ctx["include_closed"]' in src
    assert 'adapter_ctx["as_of"]' in src
    assert "query_params.get" in src


def test_emit_helper_doc_pins_search_cycle() -> None:
    src = _EMIT.read_text(encoding="utf-8")
    helper = src.split("def leftover_honest_temporal_query")[1].split("def ")[0]
    assert "cycle 2178" in helper


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
    """Sibling invent class (seed next): DateRangePicker
    ``_emit_date_range_picker`` still forwards the bare endpoint."""
    src = _EMIT.read_text(encoding="utf-8")
    emit = src.split("def _emit_date_range_picker")[1].split("def ", 1)[0]
    assert "include_closed" not in emit
    assert "as_of" not in emit
    assert "leftover_honest" not in emit
    assert "_with_leftover_honest_temporal" not in emit
