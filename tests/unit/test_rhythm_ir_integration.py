"""Tests for rhythm IR integration with ModuleFragment and AppSpec."""

from dazzle.core import ir


def test_rhythm_exported_from_ir():
    assert hasattr(ir, "RhythmSpec")
    assert hasattr(ir, "PhaseSpec")
    assert hasattr(ir, "SceneSpec")


def test_module_fragment_has_rhythms():
    frag = ir.ModuleFragment()
    assert frag.rhythms == []


def test_module_fragment_with_rhythm():
    rhythm = ir.RhythmSpec(name="onboarding", persona="new_user")
    frag = ir.ModuleFragment(rhythms=[rhythm])
    assert len(frag.rhythms) == 1
    assert frag.rhythms[0].name == "onboarding"


def test_appspec_has_rhythms():
    spec = ir.AppSpec(
        name="test",
        title="Test",
        domain=ir.DomainSpec(entities=[]),
    )
    assert spec.rhythms == []
