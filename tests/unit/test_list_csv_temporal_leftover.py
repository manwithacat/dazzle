"""List-region CSV leftover include_closed / as_of (cycle 2174).

``_emit_csv_export_button`` / ListRegion ``data-dz-csv-endpoint`` used
to be the bare path. Valid ``include_closed`` / ``as_of`` were dropped,
so a download invented open-only / current. Leftover junk (zzz / 2abc
/ maybe / not-a-date) must not invent. Valid true / YYYY-MM-DD must
ride the endpoint. Gallery mock must echo the same and must not treat
them as field filters. Not leftover sort-header echo, not leftover
list include_closed clone, not related-tab as_of, not DETAIL as_of
onto the edit form.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.http.runtime.workspace_region_fetch import _apply_leftover_honest_temporal
from dazzle.render.fragment import URL, CsvExportButton, FragmentRenderer, ListColumn, ListRegion
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
_TABLES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "render"
    / "fragment"
    / "renderer"
    / "_render_tables.py"
)
_FETCH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "workspace_region_fetch.py"
)
_MOCK = (
    Path(__file__).resolve().parents[2] / "packages" / "hatchi-maxchi" / "site" / "build_site.py"
)
_CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "hatchi-maxchi"
    / "contracts"
    / "csv_export_button.py"
)


def _render_button(include_closed: str = "", as_of: str = "") -> str:
    btn = CsvExportButton(
        endpoint=URL("/app/x"),
        filename="x.csv",
        include_closed=include_closed,
        as_of=as_of,
    )
    return FragmentRenderer().render(btn)


def _render_list(include_closed: str = "", as_of: str = "") -> str:
    lst = ListRegion(
        columns=(ListColumn(key="name", label="Name"),),
        rows=(("Ada",),),
        csv_endpoint="/app/x",
        csv_filename="x.csv",
        include_closed=include_closed,
        as_of=as_of,
    )
    return FragmentRenderer().render(lst)


def test_csv_button_echoes_leftover_honest_include_closed() -> None:
    html = _render_button(include_closed="true")
    assert "include_closed=true" in html
    assert _render_button(include_closed="1").count("include_closed=true") == 1
    assert _render_button(include_closed="YES").count("include_closed=true") == 1


def test_csv_button_echoes_leftover_honest_as_of() -> None:
    html = _render_button(as_of="2026-01-15")
    assert "as_of=2026-01-15" in html


def test_csv_button_leftover_junk_does_not_invent() -> None:
    junk_ic = _render_button(include_closed="zzz")
    assert "include_closed" not in junk_ic
    assert 'data-dz-csv-endpoint="/app/x"' in junk_ic
    assert "include_closed" not in _render_button(include_closed="2abc")
    assert "include_closed" not in _render_button(include_closed="maybe")
    assert "include_closed" not in _render_button(include_closed="false")
    junk_ao = _render_button(as_of="not-a-date")
    assert "as_of" not in junk_ao
    assert "as_of" not in _render_button(as_of="2abc")
    assert "as_of" not in _render_button(as_of="zzz")
    assert "as_of" not in _render_button(as_of="2026-13-40")


def test_csv_button_empty_temporal_omits() -> None:
    html = _render_button()
    assert "include_closed" not in html
    assert "as_of" not in html
    assert 'data-dz-csv-endpoint="/app/x"' in html


def test_list_region_csv_echoes_leftover_honest_temporal() -> None:
    html = _render_list(include_closed="true", as_of="2026-01-15")
    assert "include_closed=true" in html
    assert "as_of=2026-01-15" in html


def test_list_region_csv_leftover_junk_does_not_invent() -> None:
    html = _render_list(include_closed="zzz", as_of="not-a-date")
    assert "include_closed" not in html
    assert "as_of" not in html


def test_leftover_honest_query_helper() -> None:
    assert leftover_honest_temporal_query("true", "2026-01-15") == (
        "include_closed=true&amp;as_of=2026-01-15"
    )
    assert leftover_honest_temporal_query("zzz", "not-a-date") == ""
    assert leftover_honest_temporal_query("", "") == ""


class _FakeParams(dict[str, str]):
    def get(self, key: str, default: str | None = None) -> str | None:  # type: ignore[override]
        return super().get(key, default)


class _FakeRequest:
    def __init__(self, **params: str) -> None:
        self.query_params = _FakeParams(params)


class _FakeTemporal:
    end_field = "valid_to"
    as_of_param = "as_of"


class _FakeRepo:
    def __init__(self, temporal: object | None) -> None:
        self.entity_spec = type("S", (), {"temporal": temporal})()


def test_fetch_applies_leftover_honest_temporal() -> None:
    repo = _FakeRepo(_FakeTemporal())
    out = _apply_leftover_honest_temporal(
        _FakeRequest(include_closed="true", as_of="2026-01-15"),
        repo,
        None,
    )
    assert out is not None
    assert out["valid_to__isnull"] is False
    assert out["__as_of"].isoformat() == "2026-01-15"


def test_fetch_leftover_junk_does_not_invent_temporal() -> None:
    repo = _FakeRepo(_FakeTemporal())
    out = _apply_leftover_honest_temporal(
        _FakeRequest(include_closed="zzz", as_of="not-a-date"),
        repo,
        {"status": "open"},
    )
    assert out == {"status": "open"}


def test_fetch_non_temporal_ignores_raw() -> None:
    repo = _FakeRepo(None)
    out = _apply_leftover_honest_temporal(
        _FakeRequest(include_closed="true", as_of="2026-01-15"),
        repo,
        None,
    )
    assert out is None


def test_emit_csv_source_pins_leftover_honest_echo() -> None:
    src = _EMIT.read_text(encoding="utf-8")
    assert "include_closed=true" in src
    assert "as_of=" in src
    assert "cycle 2174" in src
    assert "must not invent" in src or "invented open-only" in src
    tables = _TABLES.read_text(encoding="utf-8")
    assert "_with_leftover_honest_temporal" in tables
    fetch = _FETCH.read_text(encoding="utf-8")
    assert "_apply_leftover_honest_temporal" in fetch
    assert "cycle 2174" in fetch


def test_gallery_mock_echoes_leftover_honest_csv() -> None:
    src = _MOCK.read_text(encoding="utf-8")
    assert "csvEndpoint" in src
    assert "include_closed" in src
    assert "leftoverHonestIncludeClosed" in src
    assert "cycle 2174" in src


def test_csv_contract_pins_temporal_leftover_honesty() -> None:
    src = _CONTRACT.read_text(encoding="utf-8")
    assert "include_closed" in src
    assert "as_of" in src
    assert "2174" in src


def test_edit_form_still_does_not_time_travel_or_include_closed() -> None:
    """Do not clone leftover list include_closed / related-tab as_of onto edit."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    edit = src.split("async def _handle_edit_form")[1].split("async def ")[0]
    assert "_detail_as_of" not in edit
    assert "_related_tab_as_of_raw" not in edit
    assert "as_of=" not in edit
    assert "as_of_raw=" not in edit
    assert "include_closed" not in edit
