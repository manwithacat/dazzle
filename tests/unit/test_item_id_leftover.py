"""Leftover ?id= must not invent empty DETAIL (cycle 2189).

``?id=zzz`` used to land in ``filters['id']`` (workspace_region_fetch)
and invent an empty DETAIL pane (live contact_manager ``contacts``
``contact_detail`` dual_pane). Valid UUID still selects. Rest is
unbound (omit). Oral #71 one-ship close — not a new class.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.workspace_region_fetch import _apply_leftover_honest_item_id
from dazzle.render.fragment.renderer._render_interactive import leftover_honest_entity_id

_HELPER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "render"
    / "fragment"
    / "renderer"
    / "_render_interactive.py"
)
_FETCH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "workspace_region_fetch.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "contact_manager" / "dsl" / "app.dsl"

_VALID = "550e8400-e29b-41d4-a716-446655440000"
_VALID_HEX = "550e8400e29b41d4a716446655440000"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("zzz", ""),
        ("ghost", ""),
        ("2abc", ""),
        ("not-a-uuid", ""),
        ("abc-1", ""),
        ("", ""),
        (None, ""),
        ("  ", ""),
        (_VALID, _VALID),
        (f"  {_VALID} ", _VALID),
        (_VALID_HEX, _VALID_HEX),
    ],
    ids=[
        "item-leftover-named",
        "item-leftover-ghost",
        "item-leftover-suffix",
        "item-leftover-words",
        "item-leftover-slug",
        "item-empty",
        "item-none",
        "item-whitespace",
        "item-valid-uuid",
        "item-valid-padded",
        "item-valid-hex",
    ],
)
def test_leftover_honest_entity_id_does_not_invent_item(raw: object, expected: str) -> None:
    assert leftover_honest_entity_id(raw) == expected


def test_fetch_omits_leftover_item_id() -> None:
    req = SimpleNamespace(query_params={"id": "zzz"})
    assert _apply_leftover_honest_item_id(req, None) is None
    assert _apply_leftover_honest_item_id(req, {"status": "open"}) == {"status": "open"}
    req = SimpleNamespace(query_params={"id": "ghost"})
    assert _apply_leftover_honest_item_id(req, None) is None
    req = SimpleNamespace(query_params={"id": "not-a-uuid"})
    assert _apply_leftover_honest_item_id(req, None) is None


def test_fetch_rides_valid_item_id() -> None:
    req = SimpleNamespace(query_params={"id": _VALID})
    assert _apply_leftover_honest_item_id(req, None) == {"id": _VALID}
    assert _apply_leftover_honest_item_id(req, {"status": "open"}) == {
        "status": "open",
        "id": _VALID,
    }


def test_fetch_absent_item_id_stays_unbound() -> None:
    req = SimpleNamespace(query_params={})
    assert _apply_leftover_honest_item_id(req, None) is None
    assert _apply_leftover_honest_item_id(req, {"status": "open"}) == {"status": "open"}
    assert _apply_leftover_honest_item_id(SimpleNamespace(query_params=None), None) is None
    assert _apply_leftover_honest_item_id(SimpleNamespace(), None) is None


def test_helper_source_pins_entity_leftover() -> None:
    src = _HELPER.read_text(encoding="utf-8")
    assert "def leftover_honest_entity_id" in src
    assert "filters['id']" in src
    assert "Cycle 2187" in src


def test_fetch_source_pins_item_id_leftover() -> None:
    src = _FETCH.read_text(encoding="utf-8")
    assert "def _apply_leftover_honest_item_id" in src
    assert "leftover_honest_entity_id" in src
    assert 'qparams.get("id")' in src
    assert 'out["id"] = item_id' in src
    assert "filters = _apply_leftover_honest_item_id(request, filters)" in src


def test_live_contact_manager_dual_pane_detail() -> None:
    src = _LIVE.read_text(encoding="utf-8")
    assert 'stage: "dual_pane_flow"' in src
    assert "contact_detail:" in src
    assert "display: detail" in src
    assert "id: uuid pk" in src
