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
