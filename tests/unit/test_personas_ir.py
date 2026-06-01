"""Tests for PersonaSpec IR."""

from dazzle.core.ir.personas import PersonaSpec


def test_persona_spec_carries_nav_ref():
    p = PersonaSpec(id="teacher", label="Teacher", nav_ref="teaching")
    assert p.nav_ref == "teaching"


def test_persona_spec_nav_ref_defaults_none():
    assert PersonaSpec(id="teacher", label="Teacher").nav_ref is None
