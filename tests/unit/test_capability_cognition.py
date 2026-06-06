"""Capability cognition gating (#1342 Phase 2)."""

import dazzle.core.capabilities.registry as reg
from dazzle.core.capabilities import active_capability_ids


def test_active_capability_ids_is_non_raising(monkeypatch):
    # OIDC available, SAML not. Unlike resolve_capabilities, this must NOT raise
    # when a declared capability's extra is missing — it just omits it.
    monkeypatch.setattr(reg, "find_spec", lambda name: object() if name == "authlib" else None)
    active = active_capability_ids(["auth.enterprise.oidc", "auth.enterprise.saml", "auth.bogus"])
    assert active == {"auth.enterprise.oidc"}  # available+declared only
    assert "auth.enterprise.saml" not in active  # declared but unavailable → omitted
    assert "auth.bogus" not in active  # unknown → omitted
