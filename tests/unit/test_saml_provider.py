"""NativeSAMLProvider unit tests (auth Plan 5.i).

python3-saml's auth object is faked (via `_build_auth`) so these run without
libxmlsec1 and without real signed XML — they pin the provider's settings, the
fail-closed validation gate, and the assertion→AssertedIdentity mapping, NOT the
library's signature crypto (that's delegated).
"""

from datetime import datetime
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.auth.connections import (
    AssertedIdentity,
    ConnectionError,
    ConnectionRecord,
    resolve_provider,
)
from dazzle.http.runtime.auth.saml_provider import (
    NativeSAMLProvider,
    register_native_saml,
)


def _conn(**over) -> ConnectionRecord:
    base = {
        "id": "conn-1",
        "tenant_id": "org-1",
        "type": "saml",
        "provider": "native",
        "domains": [],
        "verified_domains": [],
        "config": {
            "idp_entity_id": "https://idp.example/entity",
            "idp_sso_url": "https://idp.example/sso",
            "idp_x509_cert": "MIIB...fake-cert...",
        },
        "secrets": {},
        "group_mapping": {},
        "status": "active",
        "created_at": datetime(2026, 6, 6),
        "updated_at": datetime(2026, 6, 6),
    }
    base.update(over)
    return ConnectionRecord(**base)


class _FakeUrl:
    scheme = "https"
    hostname = "app.test"
    path = "/auth/saml/acs"


class _FakeForm(dict):
    pass


class _FakeRequest:
    def __init__(self, *, form=None, request_id="req-stashed", store=None):
        self.base_url = "https://app.test/"
        self.url = _FakeUrl()
        self.query_params = {}
        self.session: dict = {}
        # callback requires a stashed AuthnRequest id (SP-initiated). Seed one by default;
        # pass request_id=None to model a missing/lost session.
        if request_id is not None:
            self.session["saml_request_id"] = request_id
        self._form = form or {}
        # the IdP-initiated replay cache reads request.app.state.auth_store
        self.app = SimpleNamespace(state=SimpleNamespace(auth_store=store))

    async def form(self):
        return _FakeForm(self._form)


class _FakeAuth:
    """Stands in for OneLogin_Saml2_Auth."""

    def __init__(
        self,
        *,
        login_url="https://idp.example/sso?SAMLRequest=abc",
        request_id="req-123",
        errors=None,
        authenticated=True,
        nameid="jane@acme.test",
        attributes=None,
        assertion_id="assert-1",
        assertion_not_on_or_after="2099-01-01T00:00:00+00:00",
    ):
        self._login_url = login_url
        self._request_id = request_id
        self._errors = errors or []
        self._authenticated = authenticated
        self._nameid = nameid
        self._attributes = attributes or {}
        self._assertion_id = assertion_id
        self._assertion_noa = assertion_not_on_or_after
        self.process_called_with = None

    def login(self):
        return self._login_url

    def get_last_request_id(self):
        return self._request_id

    def process_response(self, request_id=None):
        self.process_called_with = request_id

    def get_errors(self):
        return self._errors

    def is_authenticated(self):
        return self._authenticated

    def get_nameid(self):
        return self._nameid

    def get_attributes(self):
        return self._attributes

    def get_last_assertion_id(self):
        return self._assertion_id

    def get_last_assertion_not_on_or_after(self):
        return self._assertion_noa


class _FakeReplayStore:
    """Records record_consumed_assertion calls; ``fresh`` controls the return (False = replay)."""

    def __init__(self, *, fresh=True):
        self._fresh = fresh
        self.calls: list = []

    def record_consumed_assertion(self, assertion_id, *, connection_id, tenant_id, expires_at):
        self.calls.append((assertion_id, connection_id, tenant_id, expires_at))
        return self._fresh


def _provider_with(auth: _FakeAuth) -> NativeSAMLProvider:
    p = NativeSAMLProvider()
    p._build_auth = lambda request_data, settings: auth  # type: ignore[method-assign]
    return p


# ---- settings ----


def test_settings_built_from_config() -> None:
    p = NativeSAMLProvider()
    req = _FakeRequest()
    s = p._settings(_conn(), req)
    assert s["strict"] is True
    assert s["security"]["wantAssertionsSigned"] is True
    assert s["idp"]["entityId"] == "https://idp.example/entity"
    assert s["idp"]["x509cert"] == "MIIB...fake-cert..."
    assert s["sp"]["assertionConsumerService"]["url"] == "https://app.test/auth/saml/acs"


def test_settings_missing_config_raises() -> None:
    p = NativeSAMLProvider()
    conn = _conn(config={"idp_entity_id": "x"})  # missing sso_url + cert
    with pytest.raises(ConnectionError, match="missing required config"):
        p._settings(conn, _FakeRequest())


def test_settings_require_signed_assertions() -> None:
    s = NativeSAMLProvider()._settings(_conn(), _FakeRequest())
    sec = s["security"]
    # Assertion signature is the trust anchor. Replay protection is NOT a python3-saml setting
    # (no `rejectUnsolicited*` option exists in the library) — it's enforced SP-side via the
    # one-time session request id (SP-initiated) + the assertion replay cache (IdP-initiated).
    assert sec["wantAssertionsSigned"] is True
    assert "rejectUnsolicitedResponsesWithInResponseTo" not in sec


# ---- initiate ----


async def test_initiate_returns_login_url_and_stashes_request_id() -> None:
    auth = _FakeAuth(login_url="https://idp.example/sso?SAMLRequest=xyz", request_id="req-9")
    p = _provider_with(auth)
    req = _FakeRequest()
    url = await p.initiate(_conn(), req)
    assert url == "https://idp.example/sso?SAMLRequest=xyz"
    assert req.session["saml_request_id"] == "req-9"  # InResponseTo replay protection


# ---- callback ----


async def test_callback_maps_validated_assertion() -> None:
    auth = _FakeAuth(
        nameid="Jane@Acme.test",
        attributes={"groups": ["eng", "admins"]},
    )
    p = _provider_with(auth)
    req = _FakeRequest(form={"SAMLResponse": "base64..."})
    req.session["saml_request_id"] = "req-9"
    asserted = await p.callback(_conn(), req)
    assert isinstance(asserted, AssertedIdentity)
    assert asserted.email == "jane@acme.test"  # normalized
    assert asserted.groups == ["eng", "admins"]
    assert asserted.claims_source == "saml_assertion"  # trusted source
    assert auth.process_called_with == "req-9"  # request_id passed for InResponseTo


async def test_callback_email_from_configured_attribute() -> None:
    auth = _FakeAuth(nameid="ignored@x.test", attributes={"mail": ["real@acme.test"]})
    p = _provider_with(auth)
    conn = _conn(
        config={
            "idp_entity_id": "e",
            "idp_sso_url": "s",
            "idp_x509_cert": "c",
            "email_attribute": "mail",
        }
    )
    asserted = await p.callback(conn, _FakeRequest(form={"SAMLResponse": "x"}))
    assert asserted.email == "real@acme.test"


async def test_callback_errors_refuse() -> None:
    auth = _FakeAuth(errors=["invalid_signature"])
    p = _provider_with(auth)
    with pytest.raises(ConnectionError, match="response validation failed"):
        await p.callback(_conn(), _FakeRequest(form={"SAMLResponse": "x"}))


async def test_callback_not_authenticated_refuses() -> None:
    auth = _FakeAuth(authenticated=False)
    p = _provider_with(auth)
    with pytest.raises(ConnectionError, match="response validation failed"):
        await p.callback(_conn(), _FakeRequest(form={"SAMLResponse": "x"}))


async def test_callback_empty_email_refuses() -> None:
    auth = _FakeAuth(nameid="", attributes={})
    p = _provider_with(auth)
    with pytest.raises(ConnectionError, match="no email"):
        await p.callback(_conn(), _FakeRequest(form={"SAMLResponse": "x"}))


async def test_callback_missing_request_id_refuses() -> None:
    # No stashed AuthnRequest id (lost session / unsolicited response) + connection has NOT opted
    # into IdP-initiated → refuse before validation, since request_id=None would skip InResponseTo.
    auth = _FakeAuth()
    p = _provider_with(auth)
    req = _FakeRequest(form={"SAMLResponse": "x"}, request_id=None)
    with pytest.raises(ConnectionError, match="only SP-initiated flows"):
        await p.callback(_conn(), req)
    assert auth.process_called_with is None  # never even validated


# ---- IdP-initiated opt-in + assertion replay cache (#1342) ----


def _idp_conn(**over):
    cfg = {
        "idp_entity_id": "https://idp.example/entity",
        "idp_sso_url": "https://idp.example/sso",
        "idp_x509_cert": "MIIB...fake-cert...",
        "allow_idp_initiated": "true",
    }
    return _conn(config=cfg, **over)


async def test_callback_idp_initiated_fresh_assertion_accepts() -> None:
    auth = _FakeAuth(
        assertion_id="assert-xyz", assertion_not_on_or_after="2099-01-01T00:00:00+00:00"
    )
    p = _provider_with(auth)
    store = _FakeReplayStore(fresh=True)
    req = _FakeRequest(form={"SAMLResponse": "x"}, request_id=None, store=store)
    asserted = await p.callback(_idp_conn(), req)
    assert isinstance(asserted, AssertedIdentity)
    assert auth.process_called_with is None  # request_id=None on the IdP-initiated path
    # the assertion id + its NotOnOrAfter were recorded for one-time use
    assert store.calls == [("assert-xyz", "conn-1", "org-1", "2099-01-01T00:00:00+00:00")]


async def test_callback_idp_initiated_replay_refused() -> None:
    auth = _FakeAuth(assertion_id="assert-xyz")
    p = _provider_with(auth)
    store = _FakeReplayStore(fresh=False)  # already consumed → replay
    req = _FakeRequest(form={"SAMLResponse": "x"}, request_id=None, store=store)
    with pytest.raises(ConnectionError, match="already consumed"):
        await p.callback(_idp_conn(), req)


async def test_callback_idp_initiated_no_assertion_id_refuses() -> None:
    auth = _FakeAuth(assertion_id="")  # no id → cannot replay-protect
    p = _provider_with(auth)
    store = _FakeReplayStore(fresh=True)
    req = _FakeRequest(form={"SAMLResponse": "x"}, request_id=None, store=store)
    with pytest.raises(ConnectionError, match="no id"):
        await p.callback(_idp_conn(), req)
    assert store.calls == []  # never recorded


async def test_callback_idp_initiated_off_still_refuses_unsolicited() -> None:
    # default connection (no allow_idp_initiated) + no request id → refuse, store untouched
    auth = _FakeAuth()
    p = _provider_with(auth)
    store = _FakeReplayStore(fresh=True)
    req = _FakeRequest(form={"SAMLResponse": "x"}, request_id=None, store=store)
    with pytest.raises(ConnectionError, match="only SP-initiated flows"):
        await p.callback(_conn(), req)
    assert store.calls == []


async def test_callback_sp_initiated_does_not_touch_replay_store() -> None:
    # a normal SP-initiated login (request id present) must NOT consult the replay cache.
    auth = _FakeAuth()
    p = _provider_with(auth)
    store = _FakeReplayStore(fresh=True)
    req = _FakeRequest(form={"SAMLResponse": "x"}, request_id="req-9", store=store)
    await p.callback(_idp_conn(), req)
    assert auth.process_called_with == "req-9"  # InResponseTo enforced
    assert store.calls == []  # SP-initiated is already replay-safe


async def test_callback_no_session_refuses() -> None:
    auth = _FakeAuth()
    p = _provider_with(auth)

    class _NoSessionRequest:
        url = _FakeUrl()
        query_params: dict = {}
        base_url = "https://app.test/"

        async def form(self):
            return {"SAMLResponse": "x"}

    with pytest.raises(ConnectionError, match="only SP-initiated flows"):
        await p.callback(_conn(), _NoSessionRequest())


async def test_callback_library_exception_normalized_to_refusal() -> None:
    class _RaisingAuth(_FakeAuth):
        def process_response(self, request_id=None):
            raise RuntimeError("malformed base64")

    p = _provider_with(_RaisingAuth())
    with pytest.raises(ConnectionError, match="response validation failed"):
        await p.callback(_conn(), _FakeRequest(form={"SAMLResponse": "x"}))


async def test_callback_custom_groups_attribute() -> None:
    auth = _FakeAuth(nameid="x@acme.test", attributes={"memberOf": ["g1"], "groups": ["ignored"]})
    p = _provider_with(auth)
    conn = _conn(
        config={
            "idp_entity_id": "e",
            "idp_sso_url": "s",
            "idp_x509_cert": "c",
            "groups_attribute": "memberOf",
        }
    )
    asserted = await p.callback(conn, _FakeRequest(form={"SAMLResponse": "x"}))
    assert asserted.groups == ["g1"]


# ---- registration ----


def test_register_native_saml_resolves() -> None:
    from dazzle.http.runtime.auth.connections import _PROVIDERS

    register_native_saml()
    try:
        impl = resolve_provider(SimpleNamespace(type="saml", provider="native"))
        assert isinstance(impl, NativeSAMLProvider)
    finally:
        _PROVIDERS.pop(("saml", "native"), None)


class TestSPMetadata:
    """SP-metadata generation (#1342) — library-free via the _build_sp_settings seam."""

    def test_sp_only_settings_shape(self):
        s = NativeSAMLProvider()._sp_only_settings(_FakeRequest())
        acs = "https://app.test/auth/saml/acs"
        assert s["sp"]["entityId"] == acs
        assert s["sp"]["assertionConsumerService"]["url"] == acs
        assert s["sp"]["assertionConsumerService"]["binding"].endswith("HTTP-POST")
        assert s["sp"]["NameIDFormat"].endswith("emailAddress")
        assert "idp" not in s  # SP-only — no IdP config needed for metadata

    def test_sp_metadata_decodes_and_returns(self, monkeypatch):
        provider = NativeSAMLProvider()

        class _FakeSettings:
            def get_sp_metadata(self):
                return b"<md:EntityDescriptor entityID='x'/>"

            def validate_metadata(self, md):
                return []

        monkeypatch.setattr(provider, "_build_sp_settings", lambda settings: _FakeSettings())
        assert provider.sp_metadata(_FakeRequest()) == "<md:EntityDescriptor entityID='x'/>"

    def test_sp_metadata_raises_on_invalid(self, monkeypatch):
        provider = NativeSAMLProvider()

        class _BadSettings:
            def get_sp_metadata(self):
                return b"<bad/>"

            def validate_metadata(self, md):
                return ["error: not a valid EntityDescriptor"]

        monkeypatch.setattr(provider, "_build_sp_settings", lambda settings: _BadSettings())
        with pytest.raises(RuntimeError, match="validation"):
            provider.sp_metadata(_FakeRequest())

    def test_sp_metadata_real_when_saml_installed(self):
        # End-to-end against real python3-saml when the [saml] extra is present;
        # skipped otherwise (matches the rest of the SAML suite's library handling).
        pytest.importorskip("onelogin")
        xml = NativeSAMLProvider().sp_metadata(_FakeRequest())
        assert "EntityDescriptor" in xml
        assert "https://app.test/auth/saml/acs" in xml


# ---- SP-signed AuthnRequests (#1342, feature C) ----


def test_settings_signs_requests_when_enabled() -> None:
    conn = _conn(
        config={
            "idp_entity_id": "https://idp.example/entity",
            "idp_sso_url": "https://idp.example/sso",
            "idp_x509_cert": "MIIB...fake-cert...",
            "sign_requests": "true",
            "sp_cert": "SPCERT",
        },
        secrets={"sp_private_key": "SPKEY"},
    )
    s = NativeSAMLProvider()._settings(conn, _FakeRequest())
    assert s["security"]["authnRequestsSigned"] is True
    assert s["sp"]["x509cert"] == "SPCERT"
    assert s["sp"]["privateKey"] == "SPKEY"
    assert "rsa-sha256" in s["security"]["signatureAlgorithm"]
    # Response-signature trust anchor is unchanged.
    assert s["security"]["wantAssertionsSigned"] is True


def test_settings_no_signing_by_default() -> None:
    s = NativeSAMLProvider()._settings(_conn(), _FakeRequest())
    assert "authnRequestsSigned" not in s["security"]
    assert "privateKey" not in s["sp"]
    assert "x509cert" not in s["sp"]


def test_settings_signing_ignored_without_keypair() -> None:
    # sign_requests set but no stored key/cert → must NOT enable signing.
    conn = _conn(
        config={
            "idp_entity_id": "https://idp.example/entity",
            "idp_sso_url": "https://idp.example/sso",
            "idp_x509_cert": "MIIB...fake-cert...",
            "sign_requests": "true",
        },
        secrets={},
    )
    s = NativeSAMLProvider()._settings(conn, _FakeRequest())
    assert "authnRequestsSigned" not in s["security"]


def test_metadata_advertises_signing_cert() -> None:
    pytest.importorskip("onelogin")
    from dazzle.http.runtime.auth.saml_sp_keys import generate_sp_keypair

    key, cert = generate_sp_keypair("https://app.test/auth/saml/acs")
    conn = _conn(config={"sign_requests": "true", "sp_cert": cert}, secrets={"sp_private_key": key})
    xml = NativeSAMLProvider().sp_metadata(_FakeRequest(), conn)
    assert 'use="signing"' in xml
    # The metadata advertises only the PUBLIC cert — never the private key.
    assert "PRIVATE KEY" not in xml


def test_metadata_no_signing_cert_app_level() -> None:
    pytest.importorskip("onelogin")
    xml = NativeSAMLProvider().sp_metadata(_FakeRequest())
    assert 'use="signing"' not in xml


# ---- encrypted assertions (#1342 feature B) ----


def test_encrypt_assertions_sets_want_encrypted() -> None:
    conn = _conn(
        config={
            "idp_entity_id": "x",
            "idp_sso_url": "y",
            "idp_x509_cert": "z",
            "encrypt_assertions": "true",
            "sp_cert": "CERT",
        },
        secrets={"sp_private_key": "KEY"},
    )
    s = NativeSAMLProvider()._settings(conn, _FakeRequest())
    assert s["security"]["wantAssertionsEncrypted"] is True
    assert s["sp"]["x509cert"] == "CERT"
    assert s["sp"]["privateKey"] == "KEY"


def test_no_encrypt_flag_leaves_want_encrypted_unset() -> None:
    s = NativeSAMLProvider()._settings(_conn(), _FakeRequest())
    assert "wantAssertionsEncrypted" not in s["security"]


def test_encrypt_and_sign_compose_on_shared_keypair() -> None:
    conn = _conn(
        config={
            "idp_entity_id": "x",
            "idp_sso_url": "y",
            "idp_x509_cert": "z",
            "sign_requests": "true",
            "encrypt_assertions": "true",
            "sp_cert": "CERT",
        },
        secrets={"sp_private_key": "KEY"},
    )
    s = NativeSAMLProvider()._settings(conn, _FakeRequest())
    assert s["security"]["authnRequestsSigned"] is True
    assert s["security"]["wantAssertionsEncrypted"] is True


def test_metadata_advertises_encryption_cert_for_encryption_only() -> None:
    # End-to-end: an encryption-only connection (no signing) emits a use="encryption"
    # KeyDescriptor in the real metadata XML, and never the private key.
    pytest.importorskip("onelogin")
    from dazzle.http.runtime.auth.saml_sp_keys import generate_sp_keypair

    key, cert = generate_sp_keypair("https://app.test/auth/saml/acs")
    conn = _conn(
        config={"encrypt_assertions": "true", "sp_cert": cert},
        secrets={"sp_private_key": key},
    )
    xml = NativeSAMLProvider().sp_metadata(_FakeRequest(), conn)
    assert 'use="encryption"' in xml
    assert "PRIVATE KEY" not in xml


def test_sp_only_settings_advertises_cert_for_encryption_only() -> None:
    # Encryption-only (no signing) must still put the cert in settings so the metadata
    # carries the use="encryption" KeyDescriptor; authnRequestsSigned stays unset.
    conn = _conn(
        config={
            "idp_entity_id": "x",
            "idp_sso_url": "y",
            "idp_x509_cert": "z",
            "encrypt_assertions": "true",
            "sp_cert": "CERT",
        },
        secrets={"sp_private_key": "KEY"},
    )
    s = NativeSAMLProvider()._sp_only_settings(_FakeRequest(), conn)
    assert s["sp"]["x509cert"] == "CERT"
    assert s["sp"]["privateKey"] == "KEY"
    assert s["security"]["wantAssertionsEncrypted"] is True
    assert "authnRequestsSigned" not in s["security"]


# ---- Single Logout (#1342 feature A) ----


def test_slo_settings_require_signed_messages_and_urls() -> None:
    conn = _conn(
        config={
            "idp_entity_id": "e",
            "idp_sso_url": "s",
            "idp_x509_cert": "c",
            "idp_slo_url": "https://idp.example/slo",
        }
    )
    s = NativeSAMLProvider()._slo_settings(conn, _FakeRequest())
    assert s["security"]["wantMessagesSigned"] is True  # reject unsigned LogoutRequests
    assert s["sp"]["singleLogoutService"]["url"].endswith("/auth/saml/sls")
    assert s["idp"]["singleLogoutService"]["url"] == "https://idp.example/slo"


def test_slo_settings_sign_logout_response_when_signing_on() -> None:
    conn = _conn(
        config={
            "idp_entity_id": "e",
            "idp_sso_url": "s",
            "idp_x509_cert": "c",
            "idp_slo_url": "https://idp.example/slo",
            "sign_requests": "true",
            "sp_cert": "CERT",
        },
        secrets={"sp_private_key": "KEY"},
    )
    s = NativeSAMLProvider()._slo_settings(conn, _FakeRequest())
    assert s["security"]["logoutResponseSigned"] is True
    assert s["sp"]["x509cert"] == "CERT" and s["sp"]["privateKey"] == "KEY"


def test_process_logout_returns_nameid_and_redirect() -> None:
    p = NativeSAMLProvider()
    p._build_auth = lambda rd, s: SimpleNamespace(  # type: ignore[method-assign]
        process_slo=lambda keep_local_session=False: "https://idp.example/slo?SAMLResponse=x",
        get_errors=lambda: [],
    )
    p._logout_request_nameid = lambda saml_request: "Jane@Acme.test"  # type: ignore[method-assign]
    conn = _conn(
        config={
            "idp_entity_id": "e",
            "idp_sso_url": "s",
            "idp_x509_cert": "c",
            "idp_slo_url": "https://idp.example/slo",
        }
    )
    out = p.process_logout(conn, _FakeRequest())
    assert out.name_id == "jane@acme.test"  # normalized
    assert out.redirect_url == "https://idp.example/slo?SAMLResponse=x"


def test_process_logout_raises_on_validation_error() -> None:
    p = NativeSAMLProvider()
    p._build_auth = lambda rd, s: SimpleNamespace(  # type: ignore[method-assign]
        process_slo=lambda keep_local_session=False: None,
        get_errors=lambda: ["invalid_logout_request_signature"],
    )
    conn = _conn(config={"idp_entity_id": "e", "idp_sso_url": "s", "idp_x509_cert": "c"})
    with pytest.raises(ConnectionError, match="logout"):
        p.process_logout(conn, _FakeRequest())


def test_metadata_advertises_single_logout_service() -> None:
    pytest.importorskip("onelogin")
    xml = NativeSAMLProvider().sp_metadata(_FakeRequest())
    assert "SingleLogoutService" in xml
    assert "/auth/saml/sls" in xml


# ---- SP-initiated SLO (#1342) ----


def test_initiate_logout_returns_idp_slo_redirect() -> None:
    p = NativeSAMLProvider()
    p._build_auth = lambda rd, s: SimpleNamespace(  # type: ignore[method-assign]
        logout=lambda name_id=None, return_to=None: (
            f"https://idp.example/slo?SAMLRequest=x&n={name_id}"
        )
    )
    conn = _conn(
        config={
            "idp_entity_id": "e",
            "idp_sso_url": "s",
            "idp_x509_cert": "c",
            "idp_slo_url": "https://idp.example/slo",
        }
    )
    url = p.initiate_logout(conn, _FakeRequest(), name_id="jane@acme.test")
    assert url.startswith("https://idp.example/slo?SAMLRequest=")
    assert "jane@acme.test" in url


def test_initiate_logout_without_idp_slo_url_raises() -> None:
    p = NativeSAMLProvider()
    conn = _conn(config={"idp_entity_id": "e", "idp_sso_url": "s", "idp_x509_cert": "c"})
    with pytest.raises(ConnectionError, match="logout"):
        p.initiate_logout(conn, _FakeRequest(), name_id="jane@acme.test")


# ---- Gap 3: SAML group overage fail-safe (#1342) ----


def test_extract_groups_warns_on_overage(caplog) -> None:
    p = NativeSAMLProvider()
    attrs = {"http://schemas.microsoft.com/claims/groups.link": ["https://graph/link"]}
    with caplog.at_level("WARNING"):
        groups = p._extract_groups(_conn(), attrs)
    assert groups == []  # real groups truncated by the IdP
    assert any("overage" in r.getMessage().lower() for r in caplog.records)


def test_extract_groups_no_warning_on_normal_claim(caplog) -> None:
    p = NativeSAMLProvider()
    with caplog.at_level("WARNING"):
        groups = p._extract_groups(_conn(), {"groups": ["g1", "g2"]})
    assert groups == ["g1", "g2"]
    assert not [r for r in caplog.records if "overage" in r.getMessage().lower()]
