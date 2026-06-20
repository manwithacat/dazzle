"""ConnectionProvider seam + registry + secret-masking repr (auth Plan 4a)."""

from datetime import UTC, datetime

import pytest

from dazzle.http.runtime.auth.connections import (
    AssertedIdentity,
    ConnectionError,
    ConnectionRecord,
    register_provider,
    resolve_provider,
)


def test_asserted_identity_shape() -> None:
    a = AssertedIdentity(email="x@y.test", attributes={"name": "X"}, groups=["admins"])
    assert a.email == "x@y.test" and a.groups == ["admins"] and a.attributes["name"] == "X"


def test_connection_repr_masks_secrets() -> None:
    rec = ConnectionRecord(
        id="c1",
        tenant_id="org-1",
        type="oidc",
        provider="native",
        domains=[],
        verified_domains=[],
        config={"issuer": "https://idp"},
        secrets={"client_secret": "TOP-SECRET"},
        group_mapping={},
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    text = repr(rec)
    assert "TOP-SECRET" not in text  # never leak the secret value
    assert "client_secret" in text and "***" in text  # key shown, value masked


def test_resolve_unregistered_raises() -> None:
    # A pair nothing registers — robust against other tests registering
    # (oidc, native) (the native OIDC provider from Plan 4b).
    class _Conn:
        type = "bogus"
        provider = "nope"

    with pytest.raises(ConnectionError, match="no provider"):
        resolve_provider(_Conn())


def test_register_then_resolve() -> None:
    class _Conn:
        type = "oidc"
        provider = "native"

    class _Impl:
        def initiate(self, connection, request):  # noqa: ANN001
            return "/redirect"

        def callback(self, connection, request):  # noqa: ANN001
            return AssertedIdentity(email="a@b.test")

    register_provider("oidc", "native", _Impl())
    try:
        prov = resolve_provider(_Conn())
        assert prov.initiate(_Conn(), None) == "/redirect"
    finally:
        from dazzle.http.runtime.auth.connections import _PROVIDERS

        _PROVIDERS.pop(("oidc", "native"), None)  # don't leak into other tests
