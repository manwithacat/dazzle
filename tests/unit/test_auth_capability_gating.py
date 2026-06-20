"""Enterprise auth routes gate on declared capabilities (#1342)."""

from types import SimpleNamespace
from unittest.mock import patch

from dazzle.core.capabilities import resolve_capabilities

_ENTERPRISE = (
    "auth.enterprise.oidc",
    "auth.enterprise.saml",
    "auth.enterprise.scim",
)


def _ctx(caps):
    return SimpleNamespace(capabilities=caps)


def test_no_capabilities_mounts_no_enterprise_routes(monkeypatch):
    import dazzle.core.capabilities.registry as reg

    monkeypatch.setattr(reg, "find_spec", lambda name: object())  # available...
    caps = resolve_capabilities([])  # ...but nothing declared
    from dazzle.http.runtime.subsystems.auth import AuthSubsystem

    sub = AuthSubsystem()
    with (
        patch.object(sub, "_mount_enterprise_sso") as oidc,
        patch.object(sub, "_mount_saml") as saml,
        patch.object(sub, "_mount_scim") as scim,
    ):
        sub._mount_enterprise_capabilities(_ctx(caps))
    oidc.assert_not_called()
    saml.assert_not_called()
    scim.assert_not_called()


def test_declared_oidc_mounts_only_oidc(monkeypatch):
    import dazzle.core.capabilities.registry as reg

    monkeypatch.setattr(reg, "find_spec", lambda name: object())
    caps = resolve_capabilities(["auth.enterprise.oidc"])
    from dazzle.http.runtime.subsystems.auth import AuthSubsystem

    sub = AuthSubsystem()
    with (
        patch.object(sub, "_mount_enterprise_sso") as oidc,
        patch.object(sub, "_mount_saml") as saml,
        patch.object(sub, "_mount_scim") as scim,
    ):
        sub._mount_enterprise_capabilities(_ctx(caps))
    oidc.assert_called_once()
    saml.assert_not_called()
    scim.assert_not_called()  # SCIM no longer mounts unconditionally


def test_any_enterprise_active_gates_admin_surface(monkeypatch):
    import dazzle.core.capabilities.registry as reg

    monkeypatch.setattr(reg, "find_spec", lambda name: object())
    from dazzle.http.runtime.subsystems.auth import AuthSubsystem

    sub = AuthSubsystem()
    assert sub._any_enterprise_active(_ctx(resolve_capabilities([]))) is False
    assert sub._any_enterprise_active(_ctx(resolve_capabilities(["auth.enterprise.oidc"]))) is True
    # None (no manifest resolved) is safe → False
    assert sub._any_enterprise_active(_ctx(None)) is False
