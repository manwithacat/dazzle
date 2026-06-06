"""Tests for the capability opt-in model (#1342)."""

import dataclasses

import pytest

from dazzle.core.capabilities.models import Capability


def test_capability_is_frozen_and_self_describing():
    cap = Capability(
        id="auth.enterprise.saml",
        label="Enterprise SAML SSO",
        probe_module="onelogin",
        required_extras=("saml",),
        remediation="pip install 'dazzle-dsl[saml]'  # needs native libxmlsec1",
    )
    assert cap.id == "auth.enterprise.saml"
    assert cap.required_extras == ("saml",)
    # frozen — id cannot be reassigned
    with pytest.raises(dataclasses.FrozenInstanceError):
        cap.id = "x"  # type: ignore[misc]


def test_enterprise_capabilities_are_registered():
    from dazzle.core.capabilities import known_capability_ids

    ids = known_capability_ids()
    assert {
        "auth.enterprise.oidc",
        "auth.enterprise.saml",
        "auth.enterprise.scim",
    } <= ids


def test_resolution_active_requires_declared_and_available(monkeypatch):
    import dazzle.core.capabilities.registry as reg
    from dazzle.core.capabilities import resolve_capabilities

    # Force OIDC's probe module to look installed, everything else absent.
    monkeypatch.setattr(reg, "find_spec", lambda name: object() if name == "authlib" else None)

    resolved = resolve_capabilities(["auth.enterprise.oidc"])
    assert resolved.is_active("auth.enterprise.oidc")
    assert not resolved.is_active("auth.enterprise.saml")  # not declared


def test_declared_but_unavailable_raises_with_remediation(monkeypatch):
    import dazzle.core.capabilities.registry as reg
    from dazzle.core.capabilities import resolve_capabilities
    from dazzle.core.capabilities.models import CapabilityUnavailableError

    monkeypatch.setattr(reg, "find_spec", lambda name: None)  # nothing installed

    with pytest.raises(CapabilityUnavailableError) as exc:
        resolve_capabilities(["auth.enterprise.saml"])
    assert "dazzle-dsl[saml]" in str(exc.value)  # runbook present


def test_unknown_id_is_reported_not_resolved():
    from dazzle.core.capabilities import unknown_capability_ids

    assert unknown_capability_ids(["auth.enterprise.oidc", "auth.bogus"]) == ["auth.bogus"]


def test_every_capability_declares_extras_and_remediation():
    from dazzle.core.capabilities import all_capabilities

    for cap in all_capabilities():
        assert cap.required_extras, f"{cap.id} missing required_extras"
        assert cap.remediation.strip(), f"{cap.id} missing remediation"
        assert cap.probe_module, f"{cap.id} missing probe_module"
