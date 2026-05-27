"""Tests for AppSpec.has_signable_entity() helper."""

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.domain import DomainSpec, EntitySpec


def _make_appspec(*entities: EntitySpec) -> AppSpec:
    return AppSpec(name="t", domain=DomainSpec(entities=list(entities)))


def test_has_signable_entity_true_when_one_signable():
    """Test that has_signable_entity() returns True when an entity has signable=True."""
    e = EntitySpec(name="Contract", title="Contract", fields=[], signable=True)
    assert _make_appspec(e).has_signable_entity() is True


def test_has_signable_entity_false_when_none_signable():
    """Test that has_signable_entity() returns False when no entity has signable=True."""
    e = EntitySpec(name="Contact", title="Contact", fields=[], signable=False)
    assert _make_appspec(e).has_signable_entity() is False


def test_has_signable_entity_false_when_empty():
    """Test that has_signable_entity() returns False when domain is empty."""
    assert _make_appspec().has_signable_entity() is False
