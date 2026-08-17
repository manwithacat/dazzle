"""Leftover context_id must not invent current_context (cycle 2187).

``?context_id=zzz`` used to land in ``filter_context["current_context"]``
and invent an empty / wrong slice (live support_tickets
``agent_console`` ``assigned_to = current_context``). Valid UUID still
scopes. Rest is unbound (omit). Distinct from leftover catalog id
(oral #69) and leftover date window (oral #70).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.workspace_region_prelude import apply_leftover_honest_context_id
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
_PRELUDE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "workspace_region_prelude.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "support_tickets" / "dsl" / "app.dsl"

_VALID = "550e8400-e29b-41d4-a716-446655440000"
_VALID_HEX = "550e8400e29b41d4a716446655440000"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("zzz", ""),
        ("ghost", ""),
        ("2abc", ""),
        ("not-a-uuid", ""),
        ("sch-42", ""),
        ("school-123", ""),
        ("", ""),
        (None, ""),
        ("  ", ""),
        (_VALID, _VALID),
        (f"  {_VALID} ", _VALID),
        (_VALID_HEX, _VALID_HEX),
    ],
    ids=[
        "entity-leftover-named",
        "entity-leftover-ghost",
        "entity-leftover-suffix",
        "entity-leftover-words",
        "entity-leftover-slug",
        "entity-leftover-school",
        "entity-empty",
        "entity-none",
        "entity-whitespace",
        "entity-valid-uuid",
        "entity-valid-padded",
        "entity-valid-hex",
    ],
)
def test_leftover_honest_entity_id_does_not_invent(raw: object, expected: str) -> None:
    assert leftover_honest_entity_id(raw) == expected


def test_prelude_omits_leftover_context_id() -> None:
    ctx: dict[str, object] = {}
    apply_leftover_honest_context_id({"context_id": "zzz"}, ctx)
    assert ctx == {}
    apply_leftover_honest_context_id({"context_id": "ghost"}, ctx)
    assert ctx == {}
    apply_leftover_honest_context_id(SimpleNamespace(get=lambda *_a, **_k: "not-a-uuid"), ctx)
    assert ctx == {}


def test_prelude_rides_valid_context_id() -> None:
    ctx: dict[str, object] = {}
    apply_leftover_honest_context_id({"context_id": _VALID}, ctx)
    assert ctx == {"current_context": _VALID}


def test_prelude_absent_context_id_stays_unbound() -> None:
    ctx: dict[str, object] = {}
    apply_leftover_honest_context_id({}, ctx)
    assert ctx == {}
    apply_leftover_honest_context_id(None, ctx)
    assert ctx == {}


def test_helper_source_pins_entity_leftover() -> None:
    src = _HELPER.read_text(encoding="utf-8")
    assert "def leftover_honest_entity_id" in src
    assert "context_id" in src
    assert "Cycle 2187" in src


def test_prelude_source_pins_entity_leftover() -> None:
    src = _PRELUDE.read_text(encoding="utf-8")
    assert "def apply_leftover_honest_context_id" in src
    assert "leftover_honest_entity_id" in src
    assert 'query_params.get("context_id")' in src or "apply_leftover_honest_context_id" in src
    assert "current_context" in src


def test_live_support_tickets_agent_console_context_selector() -> None:
    src = _LIVE.read_text(encoding="utf-8")
    assert "workspace agent_console" in src
    assert "context_selector:" in src
    assert "assigned_to = current_context" in src
    assert "id: uuid pk" in src
