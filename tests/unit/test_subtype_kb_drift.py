"""#1217 Phase 3e.vi — KB has the escape-hatch entry; _GUIDANCE updated."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

KB_PATH = Path(__file__).resolve().parents[2] / "src" / "dazzle" / "mcp" / "inference_kb.toml"


def test_subtype_of_only_for_true_isa_entry_present() -> None:
    data = tomllib.loads(KB_PATH.read_text())
    ids = [g["id"] for g in data.get("modeling_guidance", [])]
    assert "subtype_of_only_for_true_isa" in ids


def test_existing_no_polymorphic_keys_unchanged() -> None:
    """Sanity — we ADD a new entry, not replace the existing one."""
    data = tomllib.loads(KB_PATH.read_text())
    ids = [g["id"] for g in data.get("modeling_guidance", [])]
    assert "no_polymorphic_keys" in ids


def test_subtype_of_entry_steers_to_alternatives_first() -> None:
    data = tomllib.loads(KB_PATH.read_text())
    entry = next(g for g in data["modeling_guidance"] if g["id"] == "subtype_of_only_for_true_isa")
    prefer = entry["prefer"].lower()
    # Alternatives must be mentioned BEFORE the "only reach for" gate.
    assert prefer.index("separate entities") < prefer.index("only reach for")
    assert prefer.index("state machine") < prefer.index("only reach for")


def test_guidance_string_mentions_subtype_of() -> None:
    from dazzle.mcp.inference import _GUIDANCE

    assert "subtype_of" in _GUIDANCE
