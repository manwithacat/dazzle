# SAML Single Logout (feature A) Implementation Plan

> **For agentic workers:** Execute Hybrid (inline), with an independent security review at
> the checkpoint marked below. Steps use checkbox (`- [ ]`).

**Goal:** A signature-verified `/auth/saml/sls` endpoint that, on an IdP `LogoutRequest`,
kills the named user's app sessions in that org (IdP-initiated SLO).

**Architecture:** `NativeSAMLProvider.process_logout` wraps python3-saml `process_slo`
(validates the IdP signature, `wantMessagesSigned=True`) and extracts the NameID; the route
maps NameID(email) → `get_user_by_email` → `get_memberships_for_identity` → filter to
`connection.tenant_id` → `delete_sessions_for_membership`. Reuses C's keypair to sign the
LogoutResponse; advertises the SLS in SP metadata. No schema change.

**Tech Stack:** python3-saml ([saml] extra), FastAPI router, psycopg3 auth store.

**Spec:** `docs/superpowers/specs/2026-06-08-saml-single-logout-design.md`

---

## File Structure

- Modify `src/dazzle/http/runtime/auth/saml_provider.py` — `SamlLogout` result, `_sls_url`,
  `_slo_settings`, `process_logout`, `_logout_request_nameid` seam, SLS in
  `_sp_only_settings`.
- Modify `src/dazzle/http/runtime/auth/saml_routes.py` — the `/auth/saml/sls` route.
- Modify `tests/unit/test_saml_provider.py`, `tests/integration/test_saml_routes.py`,
  `tests/unit/test_saml_metadata.py` (or provider metadata test).

---

### Task 1: Provider — SLO settings, process_logout, NameID seam

**Files:** Modify `src/dazzle/http/runtime/auth/saml_provider.py`

- [ ] **Step 1: Add the result type + SLS path constant** near the top (after `_ACS_PATH`
/ the other module constants):

```python
_SLS_PATH = "/auth/saml/sls"


@dataclass(frozen=True)
class SamlLogout:
    """Outcome of processing an IdP LogoutRequest at the SLS."""

    name_id: str | None  # the subject NameID (email, lowercased) or None
    redirect_url: str | None  # LogoutResponse redirect back to the IdP, or None
```
(Add `from dataclasses import dataclass` to the imports if not present.)

- [ ] **Step 2: Write failing provider tests** (append to `tests/unit/test_saml_provider.py`):

```python
def test_slo_settings_require_signed_messages_and_urls() -> None:
    conn = _conn(
        config={
            "idp_entity_id": "e", "idp_sso_url": "s", "idp_x509_cert": "c",
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
            "idp_entity_id": "e", "idp_sso_url": "s", "idp_x509_cert": "c",
            "idp_slo_url": "https://idp.example/slo",
            "sign_requests": "true", "sp_cert": "CERT",
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
    conn = _conn(config={"idp_entity_id": "e", "idp_sso_url": "s", "idp_x509_cert": "c",
                         "idp_slo_url": "https://idp.example/slo"})
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
```

- [ ] **Step 3: Run** `pytest tests/unit/test_saml_provider.py -q` → the 4 new tests FAIL.

- [ ] **Step 4: Implement `_sls_url`, `_slo_settings`, `_logout_request_nameid`,
`process_logout`** (methods on `NativeSAMLProvider`, near `callback`):

```python
    def _sls_url(self, request: Any) -> str:
        return f"{str(request.base_url).rstrip('/')}{_SLS_PATH}"

    def _slo_settings(self, connection: ConnectionRecord, request: Any) -> dict[str, Any]:
        """Settings for processing an IdP LogoutRequest: the standard SP/IdP blocks plus the
        SLS endpoints and wantMessagesSigned (reject an unsigned/forged LogoutRequest —
        the load-bearing anti-forgery control). Signs the LogoutResponse when this
        connection has request-signing enabled (reuses C's keypair)."""
        settings = self._settings(connection, request)
        cfg = connection.config or {}
        settings["sp"]["singleLogoutService"] = {
            "url": self._sls_url(request),
            "binding": _BINDING_REDIRECT,
        }
        if cfg.get("idp_slo_url"):
            settings["idp"]["singleLogoutService"] = {
                "url": cfg["idp_slo_url"],
                "binding": _BINDING_REDIRECT,
            }
        # Reject unsigned LogoutRequests — only the org IdP (whose cert we hold) may log a
        # user out. python3-saml validates the signature against idp.x509cert.
        settings["security"]["wantMessagesSigned"] = True
        sp_cert = cfg.get("sp_cert")
        sp_key = (connection.secrets or {}).get("sp_private_key")
        if cfg.get("sign_requests") and sp_cert and sp_key:
            settings["sp"]["x509cert"] = sp_cert
            settings["sp"]["privateKey"] = sp_key
            settings["security"]["logoutRequestSigned"] = True
            settings["security"]["logoutResponseSigned"] = True
        return settings

    def _logout_request_nameid(self, saml_request: str) -> str | None:
        """Extract the subject NameID from a Redirect-binding LogoutRequest. Isolated as a
        seam (like _build_auth) so tests can fake it without real signed XML."""
        if not saml_request:
            return None
        from onelogin.saml2.logout_request import OneLogin_Saml2_Logout_Request
        from onelogin.saml2.utils import OneLogin_Saml2_Utils

        xml = OneLogin_Saml2_Utils.decode_base64_and_inflate(saml_request)
        return OneLogin_Saml2_Logout_Request.get_nameid(xml)

    def process_logout(self, connection: ConnectionRecord, request: Any) -> SamlLogout:
        """Validate an IdP LogoutRequest (signature, via process_slo) and return the subject
        NameID + the LogoutResponse redirect. Raises ConnectionError on any validation
        error — fail-closed, no session is touched by the caller in that case."""
        settings = self._slo_settings(connection, request)
        request_data = self._request_data(request)
        auth = self._build_auth(request_data, settings)
        try:
            redirect_url = auth.process_slo(keep_local_session=True)
            errors = auth.get_errors()
        except ConnectionError:
            raise
        except Exception as exc:  # noqa: BLE001 — any library failure ⇒ refuse
            raise ConnectionError(
                f"SAML connection {connection.id!r}: logout validation failed ({exc})"
            ) from exc
        if errors:
            raise ConnectionError(
                f"SAML connection {connection.id!r}: logout validation failed ({errors})"
            )
        saml_request = (request_data.get("get_data") or {}).get("SAMLRequest", "")
        name_id = self._logout_request_nameid(saml_request)
        return SamlLogout(
            name_id=(name_id or "").strip().lower() or None, redirect_url=redirect_url
        )
```

- [ ] **Step 5: Advertise the SLS in metadata** — in `_sp_only_settings`, add the SLS block
unconditionally (app-level, like the ACS) so `get_sp_metadata()` emits `<SingleLogoutService>`:

```python
        settings: dict[str, Any] = {
            "strict": True,
            "sp": {
                "entityId": entity,
                "assertionConsumerService": {"url": acs, "binding": _BINDING_POST},
                "singleLogoutService": {"url": self._sls_url(request), "binding": _BINDING_REDIRECT},
                "NameIDFormat": _NAMEID_EMAIL,
            },
        }
```

- [ ] **Step 6: Run** `pytest tests/unit/test_saml_provider.py -q` → all PASS.

- [ ] **Step 7: Metadata advertises SLS** — add a real-XML test (append):

```python
def test_metadata_advertises_single_logout_service() -> None:
    pytest.importorskip("onelogin")
    xml = NativeSAMLProvider().sp_metadata(_FakeRequest())
    assert "SingleLogoutService" in xml
    assert "/auth/saml/sls" in xml
```
Run it → PASS.

---

### Task 2: Route — `/auth/saml/sls`

**Files:** Modify `src/dazzle/http/runtime/auth/saml_routes.py`

- [ ] **Step 1: Write failing route tests** (append to
`tests/integration/test_saml_routes.py`; follow the existing faked-provider pattern in that
file). The two security invariants are the point:

```python
def test_sls_kills_org_sessions_for_nameid(monkeypatch, saml_app_client) -> None:
    # A valid LogoutRequest deletes the user's sessions in the connection's org only.
    client, store, conn = saml_app_client  # fixture: app + store + an active SAML conn
    # seed: a user with a membership in conn.tenant_id and a live session
    user = store.get_user_by_email("jane@acme.test")
    membership_id = ...  # membership in conn.tenant_id (see fixture helpers)
    killed: list = []
    monkeypatch.setattr(store, "delete_sessions_for_membership", lambda mid: killed.append(mid))
    # fake the provider so no real signed XML is needed
    monkeypatch.setattr(
        "dazzle.http.runtime.auth.saml_routes.resolve_provider",
        lambda c: _FakeLogoutProvider(name_id="jane@acme.test", redirect="https://idp/slo?x"),
    )
    r = client.get(f"/auth/saml/sls?connection={conn.id}&SAMLRequest=abc", follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert killed == [membership_id]  # org-scoped kill fired


def test_sls_validation_error_kills_nothing(monkeypatch, saml_app_client) -> None:
    # A forged/unsigned LogoutRequest → provider raises → 400 and NO session deleted.
    client, store, conn = saml_app_client
    killed: list = []
    monkeypatch.setattr(store, "delete_sessions_for_membership", lambda mid: killed.append(mid))
    monkeypatch.setattr(
        "dazzle.http.runtime.auth.saml_routes.resolve_provider",
        lambda c: _FakeLogoutProvider(raises=True),
    )
    r = client.get(f"/auth/saml/sls?connection={conn.id}&SAMLRequest=forged",
                   follow_redirects=False)
    assert r.status_code == 400
    assert killed == []  # fail-closed: nothing touched


def test_sls_unresolvable_connection_is_400(saml_app_client) -> None:
    client, store, conn = saml_app_client
    r = client.get("/auth/saml/sls?connection=nope&SAMLRequest=abc", follow_redirects=False)
    assert r.status_code == 400
```
Add a `_FakeLogoutProvider` helper in the test file:
```python
class _FakeLogoutProvider:
    def __init__(self, *, name_id=None, redirect=None, raises=False):
        self._out = SamlLogout(name_id=name_id, redirect_url=redirect)
        self._raises = raises
    def process_logout(self, connection, request):
        if self._raises:
            raise ConnectionError("bad logout")
        return self._out
```
(Inspect the existing `test_saml_routes.py` fixtures — reuse its app/store/connection setup
and its existing seam for `resolve_provider`; adapt the seed of a user+membership+session to
the helpers already present rather than re-inventing them.)

- [ ] **Step 2: Run** the new route tests → FAIL (no `/auth/saml/sls`).

- [ ] **Step 3: Implement the route** inside `create_saml_routes`, after `saml_metadata`:

```python
    @router.api_route("/auth/saml/sls", methods=["GET", "POST"])
    async def saml_sls(request: Request, connection: Annotated[str, Query()] = "") -> Response:
        """SAML Single Logout Service — process an IdP LogoutRequest (signature-verified)
        and kill the named user's sessions in the connection's org (IdP-initiated SLO)."""
        store = request.app.state.auth_store
        conn = _resolve_saml_connection(store, request, connection_id=connection, email="")
        if conn is None or conn.type != "saml" or conn.status != "active":
            return Response(content="invalid SAML logout", status_code=400, media_type="text/plain")
        try:
            provider = resolve_provider(conn)
            result = provider.process_logout(conn, request)
        except ConnectionError as exc:
            _logger.warning("SAML SLS: logout validation failed: %s", exc)  # nosemgrep
            return Response(content="invalid SAML logout", status_code=400, media_type="text/plain")
        except Exception as exc:  # noqa: BLE001 — never 500-leak
            _logger.warning("SAML SLS: logout error: %s", exc)  # nosemgrep
            return Response(content="invalid SAML logout", status_code=400, media_type="text/plain")

        # Org-scoped kill: every session the NameID's user holds in THIS connection's org.
        if result.name_id:
            user = store.get_user_by_email(result.name_id)
            if user is not None:
                for m in store.get_memberships_for_identity(str(user.id)):
                    if m.tenant_id == conn.tenant_id:
                        store.delete_sessions_for_membership(m.id)

        if result.redirect_url:
            response: Response = RedirectResponse(url=result.redirect_url, status_code=303)
        else:
            response = Response(content="logged out", status_code=200, media_type="text/plain")
        # Clear this browser's auth + CSRF cookies (best-effort for the carrier browser).
        for name in names_to_clear(request, default=cookie_name):
            response.delete_cookie(name)
        response.delete_cookie("dazzle_csrf")
        return response
```
Add imports at the top of `saml_routes.py`: `from dazzle.http.runtime.auth.cookie_name import
names_to_clear` (confirm the symbol; it is used by the local logout) and ensure `Response`,
`RedirectResponse`, `Query`, `Annotated` are imported (most already are).

- [ ] **Step 4: Run** the route tests → PASS. Then the full SAML route + provider suites
`DATABASE_URL=…/dazzle_dev pytest tests/integration/test_saml_routes.py tests/unit/test_saml_provider.py -q`.

---

### Checkpoint — independent security review

- [ ] Dispatch a `feature-dev:code-reviewer` subagent on the diff. Focus: (1) **forgery** —
is there ANY path where a LogoutRequest kills a session without the signature being
verified (e.g. NameID read before/independently of `process_slo`'s validation)? The NameID
extraction must only be trusted *after* `process_slo` returns no errors. (2) **cross-org** —
can a LogoutRequest on connection A delete a membership in org B? (the `m.tenant_id ==
conn.tenant_id` filter). (3) **enumeration** — does a bad/unknown email or connection reveal
anything (timing or content)? (4) the route never 500-leaks. Fix any CRITICAL before ship.

---

### Task 3: Docs + ship

- [ ] **Step 1: CHANGELOG** `### Added`: "SAML Single Logout (IdP-initiated) — `/auth/saml/sls`
validates a signed LogoutRequest and kills the user's sessions in that org; SP metadata
advertises the SingleLogoutService." `### Agent Guidance` if worth noting the NameID-only-after-
validation rule.
- [ ] **Step 2:** `/bump patch`.
- [ ] **Step 3: Gates** — `ruff`, `mypy src/dazzle`, drift/policy, `pytest tests/ -m "not
e2e"`, and the postgres slice (`DATABASE_URL=… pytest -m postgres -q` for the auth/connections
+ saml route PG tests). Mutation gate unaffected.
- [ ] **Step 4:** commit (verify `COMMIT_EXIT=0` before tag), tag, push, watch CI (incl. the
`integration` SAML job) + release.
- [ ] **Step 5:** update memory `project_1342_enterprise_auth_capability` — A shipped; the
SAML cluster (D/C/B/A) is complete; remaining #1342 backlog = SP-initiated SLO follow-on +
#1344 boot guard.

## Self-review

- **Spec coverage:** SLS route (Task 2), signature-verified process_logout (Task 1),
  org-scoped kill (Task 2), metadata SLS advertisement (Task 1), fail-closed + cross-org
  tests (Task 2), security review (checkpoint). ✓
- **Type consistency:** `process_logout → SamlLogout(name_id, redirect_url)`; the kill chain
  `get_user_by_email → str(user.id) → get_memberships_for_identity → m.tenant_id /
  m.id → delete_sessions_for_membership` matches `enterprise_login.py:131` exactly. ✓
- **No placeholders:** route + provider code complete; the only "inspect existing fixtures"
  note is in Task 2 Step 1 (seed helpers), not in shipped code. ✓
