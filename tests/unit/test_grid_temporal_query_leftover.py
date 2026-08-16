"""Grid ownedKeys / buildQuery leftover include_closed / as_of (cycle 2170).

The tbody hx-get is rebuilt from DOM-only query keys. include_closed /
as_of used to be foreign URL params (ownedKeys omitted them) so they
survived on the page URL but were dropped from hx-get on refresh —
all-matching then invented open-only / current even after 2169 consumed
the echo. Leftover junk (zzz / 2abc / maybe / not-a-date) must not
invent. Valid true / YYYY-MM-DD must ride hx-get. The gallery mock must
not treat them as field filters (empty catalog theater). Not leftover
list include_closed clone, not related-tab as_of, not DETAIL as_of onto
the edit form.
"""

from __future__ import annotations

from pathlib import Path

_GRID_JS = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "hatchi-maxchi"
    / "controllers"
    / "dz-grid.js"
)
_MOCK = (
    Path(__file__).resolve().parents[2] / "packages" / "hatchi-maxchi" / "site" / "build_site.py"
)
_CONTRACT = (
    Path(__file__).resolve().parents[2] / "packages" / "hatchi-maxchi" / "contracts" / "grid.py"
)


def test_grid_controller_owns_leftover_honest_temporal_keys() -> None:
    src = _GRID_JS.read_text(encoding="utf-8")
    assert "function parseIncludeClosed" in src
    assert "function parseAsOf" in src
    assert "function readIncludeClosed" in src
    assert "function readAsOf" in src
    assert "include_closed: 1" in src
    assert "as_of: 1" in src
    assert "must not invent" in src
    assert "cycle 2170" in src


def test_grid_build_query_echoes_leftover_honest_temporal() -> None:
    src = _GRID_JS.read_text(encoding="utf-8")
    assert 'q.push("include_closed=" + encodeURIComponent(ic.value))' in src
    assert 'q.push("as_of=" + encodeURIComponent(ao.value))' in src
    assert "readIncludeClosed(root)" in src
    assert "readAsOf(root)" in src


def test_gallery_mock_does_not_treat_temporal_as_field_filters() -> None:
    """include_closed / as_of on hx-get must not invent an empty catalog."""
    src = _MOCK.read_text(encoding="utf-8")
    assert "include_closed: 1" in src
    assert "as_of: 1" in src
    assert "GRID_CONTROL" in src


def test_grid_contract_pins_temporal_leftover_honesty() -> None:
    src = _CONTRACT.read_text(encoding="utf-8")
    assert "include_closed" in src
    assert "as_of" in src
    assert "2170" in src
