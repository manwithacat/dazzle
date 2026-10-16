"""Enterprise auth boot guard (#1344, DD-013): ``[auth.enterprise] protocols`` gating.

Restored from the archived capability guard (``test_capability_guard.py`` at 23cf59372),
re-keyed on the declared protocols instead of the capability registry.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from dazzle.http.runtime.auth import enterprise_guard
from dazzle.http.runtime.auth.connections import _PROVIDERS
from dazzle.http.runtime.auth.enterprise_guard import (
    EnterpriseAuthBootError,
    undeclared_connection_errors,
)
from dazzle.http.runtime.auth.enterprise_login import ENTERPRISE_OIDC_STATE_ATTR
from dazzle.http.runtime.lifespan_hooks import _STARTUP_ATTR
from dazzle.http.runtime.subsystems.auth import AuthSubsystem


@pytest.fixture(autouse=True)
def _unregister_native_oidc() -> Iterator[None]:
    yield
    _PROVIDERS.pop(("oidc", "native"), None)  # an oidc mount registers it; don't leak


def _ctx(store: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(app=FastAPI(), auth_store=store)


@pytest.mark.parametrize(
    ("counts", "protocols", "flagged"),
    [
        pytest.param({"oidc": 3}, ["oidc"], [], id="declared_is_silent"),
        pytest.param({"scim": 2}, ["oidc"], ["scim"], id="undeclared_type_flagged"),
        pytest.param({"scim": 0}, [], [], id="zero_count_silent"),
        pytest.param({"domain": 4}, [], [], id="routing_only_domain_silent"),
        pytest.param({"oidc": 1, "scim": 1}, [], ["oidc", "scim"], id="nothing_declared"),
        pytest.param({"ldap": 5}, ["oidc"], ["ldap"], id="unsupported_type_flagged"),
    ],
)
def test_undeclared_connection_errors(
    counts: dict[str, int], protocols: list[str], flagged: list[str]
) -> None:
    errors = undeclared_connection_errors(counts, protocols)
    assert [e.split(" ")[1] for e in errors] == flagged
    assert all("[auth.enterprise]" in e for e in errors)


@pytest.mark.parametrize(
    ("protocols", "unavailable", "missing"),
    [
        pytest.param(["oidc"], {"authlib"}, "authlib", id="oidc_without_authlib_errors"),
        pytest.param(["scim"], {"authlib"}, None, id="scim_does_not_need_authlib"),
        pytest.param(["scim"], {"cryptography"}, "cryptography", id="scim_needs_cryptography"),
        pytest.param([], {"authlib", "cryptography"}, None, id="nothing_declared_no_probe"),
    ],
)
def test_declared_protocol_without_its_extra_is_a_boot_error(
    monkeypatch: pytest.MonkeyPatch,
    protocols: list[str],
    unavailable: set[str],
    missing: str | None,
) -> None:
    monkeypatch.setattr(enterprise_guard, "_module_available", lambda m: m not in unavailable)
    if missing is None:
        AuthSubsystem()._mount_enterprise(_ctx(), protocols)
        return
    with pytest.raises(EnterpriseAuthBootError, match=missing):
        AuthSubsystem()._mount_enterprise(_ctx(), protocols)


def test_boot_guard_logs_error_for_undeclared_connection_rows(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(enterprise_guard, "_module_available", lambda _m: True)
    ctx = _ctx(SimpleNamespace(connection_type_counts=lambda: {"scim": 2}))
    AuthSubsystem()._mount_enterprise(ctx, ["oidc"])

    hooks = getattr(ctx.app.state, _STARTUP_ATTR)
    with caplog.at_level("ERROR"):
        hooks[0]()
    errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert any("Enterprise auth boot guard" in m and "2 scim connection(s)" in m for m in errors)


@pytest.mark.parametrize("protocols", [["oidc"], []], ids=["oidc_declared", "nothing_declared"])
def test_oidc_routes_mount_only_when_declared(
    monkeypatch: pytest.MonkeyPatch, protocols: list[str]
) -> None:
    monkeypatch.setattr(enterprise_guard, "_module_available", lambda _m: True)
    ctx = _ctx()
    AuthSubsystem()._mount_enterprise(ctx, protocols)
    paths = set(ctx.app.openapi()["paths"])
    declared = protocols == ["oidc"]
    assert ("/auth/enterprise/login" in paths) is declared
    assert ("/auth/enterprise/callback" in paths) is declared
    assert (("oidc", "native") in _PROVIDERS) is declared
    assert getattr(ctx.app.state, ENTERPRISE_OIDC_STATE_ATTR, False) is declared


def test_boot_guard_not_registered_without_store() -> None:
    ctx = _ctx()
    AuthSubsystem()._mount_enterprise(ctx, [])
    assert getattr(ctx.app.state, _STARTUP_ATTR, []) == []
