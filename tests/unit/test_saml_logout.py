"""SP-initiated SLO resolution helper (#1342) — seam-level, fakes the store + provider."""

from __future__ import annotations

from types import SimpleNamespace

from dazzle.http.runtime.auth.saml_logout import saml_slo_redirect_url


def _session(membership_id="mem-1"):
    return SimpleNamespace(id="sess-1", active_membership_id=membership_id)


def _membership(tenant_id="org-1", identity_id="uid-1"):
    return SimpleNamespace(id="mem-1", tenant_id=tenant_id, identity_id=identity_id)


def _saml_conn(*, slo=True):
    cfg = {"idp_slo_url": "https://idp.example/slo"} if slo else {}
    return SimpleNamespace(id="conn-1", type="saml", status="active", config=cfg)


class _Store:
    def __init__(self, *, session=None, membership=None, conns=None, user=None):
        self._session = session
        self._membership = membership
        self._conns = conns or []
        self._user = user

    def get_session(self, sid):
        return self._session

    def get_membership(self, mid):
        return self._membership

    def get_connections_for_tenant(self, tid):
        return self._conns

    def get_user_by_id(self, uid):
        return self._user


def _install_provider(monkeypatch, *, url="https://idp.example/slo?SAMLRequest=abc"):
    captured = {}

    class _Prov:
        def initiate_logout(self, conn, request, *, name_id):
            captured["name_id"] = name_id
            return url

    monkeypatch.setattr("dazzle.http.runtime.auth.connections.resolve_provider", lambda c: _Prov())
    return captured


def test_none_for_non_saml_org(monkeypatch) -> None:
    # The org has no SAML connection → None (fall back to local logout).
    store = _Store(session=_session(), membership=_membership(), conns=[])
    assert saml_slo_redirect_url(store, SimpleNamespace(), session_id="sess-1") is None


def test_redirect_built_for_saml_session_with_slo(monkeypatch) -> None:
    import uuid

    uid = uuid.uuid4()
    store = _Store(
        session=_session(),
        membership=_membership(identity_id=str(uid)),
        conns=[_saml_conn(slo=True)],
        user=SimpleNamespace(id=uid, email="jane@acme.test"),
    )
    captured = _install_provider(monkeypatch)
    url = saml_slo_redirect_url(store, SimpleNamespace(), session_id="sess-1")
    assert url == "https://idp.example/slo?SAMLRequest=abc"
    assert captured["name_id"] == "jane@acme.test"  # the session user's own email


def test_none_when_saml_conn_has_no_slo_url(monkeypatch) -> None:
    store = _Store(session=_session(), membership=_membership(), conns=[_saml_conn(slo=False)])
    assert saml_slo_redirect_url(store, SimpleNamespace(), session_id="sess-1") is None


def test_none_on_any_error() -> None:
    # A store that raises must yield None, never propagate (logout must not break).
    class _Boom:
        def get_session(self, sid):
            raise RuntimeError("db down")

    assert saml_slo_redirect_url(_Boom(), SimpleNamespace(), session_id="sess-1") is None


def test_none_without_active_membership() -> None:
    store = _Store(session=SimpleNamespace(active_membership_id=None))
    assert saml_slo_redirect_url(store, SimpleNamespace(), session_id="sess-1") is None
