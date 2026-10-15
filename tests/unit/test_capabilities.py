"""Tests for the capability opt-in model (#1342)."""

import dataclasses

import pytest

from dazzle.core.capabilities.models import Capability
from tests.unit._fake_capabilities import fake_capabilities  # noqa: F401  (fixture)


def test_capability_is_frozen_and_self_describing():
    cap = Capability(
        id="demo.beta",
        label="Demo beta",
        probe_module="dazzle_demo_absent",
        required_extras=("beta",),
        remediation="pip install 'dazzle-dsl[beta]'",
    )
    assert cap.id == "demo.beta"
    assert cap.required_extras == ("beta",)
    # frozen — id cannot be reassigned
    with pytest.raises(dataclasses.FrozenInstanceError):
        cap.id = "x"  # type: ignore[misc]


def test_no_framework_capability_is_registered():
    # The enterprise auth capabilities were the only ones; DD-013 parked them.
    from dazzle.core.capabilities import known_capability_ids

    assert known_capability_ids() == set()


@pytest.mark.usefixtures("fake_capabilities")
def test_resolution_active_requires_declared_and_available(monkeypatch):
    import dazzle.core.capabilities.registry as reg
    from dazzle.core.capabilities import resolve_capabilities

    # Force alpha's probe module to look installed, everything else absent.
    monkeypatch.setattr(reg, "find_spec", lambda name: object() if name == "authlib" else None)

    resolved = resolve_capabilities(["demo.alpha"])
    assert resolved.is_active("demo.alpha")
    assert not resolved.is_active("demo.beta")  # not declared


@pytest.mark.usefixtures("fake_capabilities")
def test_declared_but_unavailable_raises_with_remediation(monkeypatch):
    import dazzle.core.capabilities.registry as reg
    from dazzle.core.capabilities import resolve_capabilities
    from dazzle.core.capabilities.models import CapabilityUnavailableError

    monkeypatch.setattr(reg, "find_spec", lambda name: None)  # nothing installed

    with pytest.raises(CapabilityUnavailableError) as exc:
        resolve_capabilities(["demo.beta"])
    assert "dazzle-dsl[beta]" in str(exc.value)  # runbook present


@pytest.mark.usefixtures("fake_capabilities")
def test_unknown_id_is_reported_not_resolved():
    from dazzle.core.capabilities import unknown_capability_ids

    assert unknown_capability_ids(["demo.alpha", "demo.bogus"]) == ["demo.bogus"]


@pytest.mark.usefixtures("fake_capabilities")
def test_every_capability_declares_extras_and_remediation():
    from dazzle.core.capabilities import all_capabilities

    for cap in all_capabilities():
        assert cap.id and cap.label, f"{cap.id} missing id/label"
        # A capability with a probe module can be unavailable, so it MUST carry a
        # remediation runbook + its extras. An always-available one (probe=None)
        # needs neither.
        if cap.probe_module is not None:
            assert cap.required_extras, f"{cap.id} missing required_extras"
            assert cap.remediation.strip(), f"{cap.id} missing remediation"


@pytest.mark.usefixtures("fake_capabilities")
def test_probe_free_capability_is_always_available(monkeypatch):
    """A capability with no import-time dependency (#1342 review): declaring it
    activates it even when no optional package is installed."""
    import dazzle.core.capabilities.registry as reg
    from dazzle.core.capabilities import resolve_capabilities

    monkeypatch.setattr(reg, "find_spec", lambda name: None)  # nothing installed
    resolved = resolve_capabilities(["demo.gamma"])  # must NOT raise
    assert resolved.is_active("demo.gamma")


def test_is_available_guards_missing_parent_package(monkeypatch):
    """is_available returns False (not crash) if find_spec raises ModuleNotFoundError
    for a dotted probe whose parent is absent."""
    import dazzle.core.capabilities.registry as reg
    from dazzle.core.capabilities import is_available
    from dazzle.core.capabilities.models import Capability

    def boom(name):
        raise ModuleNotFoundError("no parent")

    monkeypatch.setattr(reg, "find_spec", boom)
    cap = Capability(
        id="x",
        label="X",
        probe_module="missing.child",
        required_extras=("x",),
        remediation="install x",
    )
    assert is_available(cap) is False
