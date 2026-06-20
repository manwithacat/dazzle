"""Pure capability-boot-guard logic (#1344) — no DB, no logging."""

from __future__ import annotations

from dazzle.http.runtime.auth.capability_guard import capability_boot_warnings


def _active(*ids):
    s = set(ids)
    return lambda cid: cid in s


def test_no_warning_when_capability_active() -> None:
    assert capability_boot_warnings({"oidc": 3}, _active("auth.enterprise.oidc")) == []


def test_warns_for_inactive_type_with_connections() -> None:
    w = capability_boot_warnings({"saml": 2}, _active())  # nothing active
    assert len(w) == 1
    assert "2 saml connection(s)" in w[0]
    assert "auth.enterprise.saml" in w[0]
    assert "dazzle capability enable auth.enterprise.saml" in w[0]


def test_zero_count_type_does_not_warn() -> None:
    assert capability_boot_warnings({"scim": 0}, _active()) == []


def test_unknown_type_is_ignored() -> None:
    assert capability_boot_warnings({"ldap": 5}, _active()) == []


def test_capabilities_none_path_warns_for_every_present_type() -> None:
    # When no manifest is resolved the hook passes is_active=lambda: False.
    w = capability_boot_warnings({"oidc": 1, "saml": 1, "scim": 1}, lambda _cid: False)
    assert len(w) == 3


def test_mixed_active_and_inactive() -> None:
    w = capability_boot_warnings({"oidc": 1, "saml": 1}, _active("auth.enterprise.oidc"))
    assert len(w) == 1 and "saml" in w[0]


# ---- wiring: the lifespan startup hook (#1344) ----


def test_boot_guard_hook_logs_for_inactive_capability(caplog) -> None:
    from types import SimpleNamespace

    from dazzle.http.runtime.lifespan_hooks import _STARTUP_ATTR
    from dazzle.http.runtime.subsystems.auth import AuthSubsystem

    app = SimpleNamespace(state=SimpleNamespace())
    store = SimpleNamespace(connection_type_counts=lambda: {"saml": 2})
    ctx = SimpleNamespace(app=app, auth_store=store, capabilities=None)  # None → all inactive
    AuthSubsystem()._register_capability_boot_guard(ctx)

    hooks = getattr(app.state, _STARTUP_ATTR)
    assert len(hooks) == 1
    with caplog.at_level("ERROR"):
        hooks[0]()
    msgs = [r.getMessage() for r in caplog.records]
    assert any("Capability boot guard" in m and "auth.enterprise.saml" in m for m in msgs)


def test_boot_guard_hook_silent_when_capability_active(caplog) -> None:
    from types import SimpleNamespace

    from dazzle.http.runtime.lifespan_hooks import _STARTUP_ATTR
    from dazzle.http.runtime.subsystems.auth import AuthSubsystem

    app = SimpleNamespace(state=SimpleNamespace())
    store = SimpleNamespace(connection_type_counts=lambda: {"saml": 1})
    caps = SimpleNamespace(is_active=lambda cid: True)  # everything active
    ctx = SimpleNamespace(app=app, auth_store=store, capabilities=caps)
    AuthSubsystem()._register_capability_boot_guard(ctx)

    with caplog.at_level("ERROR"):
        getattr(app.state, _STARTUP_ATTR)[0]()
    assert not [r for r in caplog.records if "Capability boot guard" in r.getMessage()]


def test_boot_guard_not_registered_without_store() -> None:
    from types import SimpleNamespace

    from dazzle.http.runtime.lifespan_hooks import _STARTUP_ATTR
    from dazzle.http.runtime.subsystems.auth import AuthSubsystem

    app = SimpleNamespace(state=SimpleNamespace())
    ctx = SimpleNamespace(app=app, auth_store=None, capabilities=None)
    AuthSubsystem()._register_capability_boot_guard(ctx)
    assert getattr(app.state, _STARTUP_ATTR, []) == []
