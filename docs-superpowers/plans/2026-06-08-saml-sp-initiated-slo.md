# SAML SP-initiated Single Logout Implementation Plan

> **For agentic workers:** Execute Hybrid (inline), with an independent security review at the
> checkpoint. Steps use checkbox (`- [ ]`).

**Goal:** Logging out of a SAML session also ends the IdP session (SP sends a signed LogoutRequest
to the IdP SLO; returns to `/auth/saml/sls`). Local logout always happens first.

**Spec:** `docs/superpowers/specs/2026-06-08-saml-sp-initiated-slo-design.md`

---

## File Structure

- Modify `src/dazzle/http/runtime/auth/saml_provider.py` — `initiate_logout` + `_post_logout_url`.
- Create `src/dazzle/http/runtime/auth/saml_logout.py` — `saml_slo_redirect_url(...)` helper.
- Modify `src/dazzle/http/runtime/auth/routes.py` — `_logout` integration.
- Modify `src/dazzle/http/runtime/auth/saml_routes.py` — SLS: guard `SAMLResponse`; don't-400 a
  returning user on a *response* error.
- Create `tests/integration/saml_idp_double.py` — the real-crypto IdP test double.
- Modify `tests/unit/test_saml_provider.py`, `tests/integration/test_saml_routes.py`; create
  `tests/unit/test_saml_logout.py`.

---

### Task 1: Provider — `initiate_logout`

**Files:** Modify `src/dazzle/http/runtime/auth/saml_provider.py`

- [ ] **Step 1: Failing tests** (append to `tests/unit/test_saml_provider.py`):

```python
def test_initiate_logout_returns_idp_slo_redirect() -> None:
    p = NativeSAMLProvider()
    p._build_auth = lambda rd, s: SimpleNamespace(  # type: ignore[method-assign]
        logout=lambda name_id=None, return_to=None: f"https://idp.example/slo?SAMLRequest=x&n={name_id}"
    )
    conn = _conn(config={"idp_entity_id": "e", "idp_sso_url": "s", "idp_x509_cert": "c",
                         "idp_slo_url": "https://idp.example/slo"})
    url = p.initiate_logout(conn, _FakeRequest(), name_id="jane@acme.test")
    assert url.startswith("https://idp.example/slo?SAMLRequest=")
    assert "jane@acme.test" in url


def test_initiate_logout_without_idp_slo_url_raises() -> None:
    p = NativeSAMLProvider()
    conn = _conn(config={"idp_entity_id": "e", "idp_sso_url": "s", "idp_x509_cert": "c"})  # no slo
    with pytest.raises(ConnectionError, match="logout"):
        p.initiate_logout(conn, _FakeRequest(), name_id="jane@acme.test")
```

- [ ] **Step 2: Implement** (near `process_logout`):

```python
    def _post_logout_url(self, request: Any) -> str:
        return f"{str(request.base_url).rstrip('/')}/"

    def initiate_logout(self, connection: ConnectionRecord, request: Any, *, name_id: str) -> str:
        """Build the SP-initiated LogoutRequest and return the redirect to the IdP SLO. Signs the
        request when request-signing is on (reuses _slo_settings / C's keypair). Raises
        ConnectionError when the connection has no idp_slo_url (caller falls back to local logout)."""
        if not (connection.config or {}).get("idp_slo_url"):
            raise ConnectionError(
                f"SAML connection {connection.id!r}: no idp_slo_url — cannot SP-initiate logout"
            )
        settings = self._slo_settings(connection, request)
        auth = self._build_auth(self._request_data(request), settings)
        return auth.logout(name_id=name_id, return_to=self._post_logout_url(request))
```

- [ ] **Step 3: Run** `pytest tests/unit/test_saml_provider.py -q` → PASS.

---

### Task 2: SAML logout helper

**Files:** Create `src/dazzle/http/runtime/auth/saml_logout.py`

- [ ] **Step 1: Failing tests** `tests/unit/test_saml_logout.py` (seam — fake store + provider):

```python
def test_redirect_url_none_for_non_saml_session() -> None:
    # session → membership → tenant has no SAML connection → None (fall back to local logout)
    ...

def test_redirect_url_built_for_saml_session_with_slo() -> None:
    # session → membership → tenant's active SAML conn with idp_slo_url → provider.initiate_logout
    # is called with the identity's email; returns its URL
    ...

def test_redirect_url_none_on_any_error() -> None:
    # a store/provider that raises → None (never propagate; logout must not break)
    ...
```
(Build minimal fakes mirroring `test_saml_routes.py`'s `_Store`/`_User`/`_Membership`; add
`get_session`, `get_membership`, `get_user_by_id`, `get_connections_for_tenant`.)

- [ ] **Step 2: Implement** `saml_logout.py`:

```python
"""SP-initiated SAML SLO resolution for the generic logout (#1342). Kept out of routes.py /
saml_routes.py so generic auth carries no SAML dependency; imported lazily by _logout."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

_logger = logging.getLogger(__name__)


def saml_slo_redirect_url(store: Any, request: Any, *, session_id: str) -> str | None:
    """If ``session_id`` is a SAML SSO session whose org has an SLO-configured SAML connection,
    return the IdP SLO redirect (signed LogoutRequest) to send the browser to; else ``None``.
    Called BEFORE the session is deleted. Never raises — any failure → ``None`` (local logout)."""
    try:
        session = store.get_session(session_id)
        if session is None or not getattr(session, "active_membership_id", None):
            return None
        membership = store.get_membership(session.active_membership_id)
        if membership is None:
            return None
        conn = next(
            (
                c
                for c in store.get_connections_for_tenant(membership.tenant_id)
                if c.type == "saml" and c.status == "active" and (c.config or {}).get("idp_slo_url")
            ),
            None,
        )
        if conn is None:
            return None
        user = store.get_user_by_id(UUID(str(membership.identity_id)))
        if user is None or not getattr(user, "email", ""):
            return None
        from dazzle.http.runtime.auth.connections import resolve_provider

        provider = resolve_provider(conn)
        return provider.initiate_logout(conn, request, name_id=user.email)
    except Exception as exc:  # noqa: BLE001 — logout must never break on SLO resolution
        _logger.warning("SAML SP-SLO resolution failed; falling back to local logout: %s", exc)
        return None
```
(`resolve_provider` returns the SAML provider; `initiate_logout` is SAML-only — cast/ignore the
attr-defined like the SLS route, or call via `getattr`.)

- [ ] **Step 3: Run** `pytest tests/unit/test_saml_logout.py -q` → PASS.

---

### Task 3: Generic logout integration

**Files:** Modify `src/dazzle/http/runtime/auth/routes.py` (`_logout`)

- [ ] **Step 1: Failing test** — extend an existing logout test (or add one) asserting: a SAML
session → `/logout` returns a redirect/HX-Redirect to the IdP SLO url (helper faked to return a url);
a non-SAML session → the existing local redirect. (Patch `saml_slo_redirect_url` via monkeypatch.)

- [ ] **Step 2: Implement** — in `_logout`, resolve the SLO url BEFORE deleting the session, and
prefer it after clearing cookies:

```python
    session_id = read_session_id(request, default=deps.cookie_name)

    slo_url = None
    if session_id:
        from dazzle.http.runtime.auth.saml_logout import saml_slo_redirect_url
        slo_url = saml_slo_redirect_url(deps.auth_store, request, session_id=session_id)
        deps.auth_store.delete_session(session_id)

    # ... existing accept/htmx/browser detection ...
    if is_htmx:
        response = Response(status_code=200, headers={"HX-Redirect": slo_url or "/"})
    elif is_browser:
        response = RedirectResponse(url=slo_url or "/", status_code=303)
    else:
        response = JSONResponse(content={"message": "Logout successful"})  # JSON stays local
    # ... existing cookie clearing unchanged ...
```
Local logout (delete + cookie clear) is unconditional and happens regardless of `slo_url` — a broken
IdP can never keep a session alive. JSON/API callers stay local (SP-SLO is a browser flow).

- [ ] **Step 3: Run** the logout tests + the full auth-routes suite → PASS.

---

### Task 4: SLS — handle the returning LogoutResponse cleanly

**Files:** Modify `src/dazzle/http/runtime/auth/saml_routes.py`

- [ ] **Step 1: Failing tests** (append to `tests/integration/test_saml_routes.py`, seam-level):
a `SAMLResponse` (LogoutResponse, faked provider → `SamlLogout(name_id=None, redirect_url=None)`) →
**200, nothing killed**; a provider error on a `SAMLResponse` → still **not a 400** (land logged-out,
e.g. 303 to "/"); oversized `SAMLResponse` → 400 (guard).

- [ ] **Step 2: Implement** — in `saml_sls`:
  - Extend the length guard: `max(len(SAMLRequest), len(SAMLResponse)) > _MAX_SAML_REQUEST_B64 → 400`.
  - Determine the inbound kind: `is_response = "SAMLResponse" in request.query_params`.
  - On a provider `ConnectionError`: if `is_response`, log + redirect to "/" (the user is already
    locally logged out — don't 400 them); if a request (IdP-initiated), keep the existing 400.
  - The kill block already no-ops when `result.name_id` is None (LogoutResponse) — unchanged.

- [ ] **Step 3: Run** the SLS tests → PASS (incl. the feature-A IdP-initiated tests, unregressed).

---

### Task 5: The real-crypto IdP double + Tier-2 tests (the centerpiece)

**Files:** Create `tests/integration/saml_idp_double.py`; add Tier-2 tests to
`tests/integration/test_saml_routes.py`.

- [ ] **Step 1: Build the double — test-first against the REAL validator.** The signed Redirect-binding
query byte-format is python3-saml-internal, so do NOT hardcode it from docs — verify it. Write this
test FIRST and iterate `saml_idp_double` until it passes (this pins the encoding):

```python
def test_idp_double_message_validates_against_real_process_slo() -> None:
    pytest.importorskip("onelogin")
    from tests.integration.saml_idp_double import SamlIdpDouble
    from dazzle.http.runtime.auth.saml_provider import NativeSAMLProvider

    sls = "https://app.test/auth/saml/sls"
    idp = SamlIdpDouble(entity_id="https://idp.example/entity", slo_url="https://idp.example/slo")
    conn = _saml_conn(idp_entity_id=idp.entity_id, idp_cert=idp.idp_cert,
                      idp_slo_url=idp.slo_url)  # real cert in the connection
    params = idp.signed_logout_request(name_id="jane@acme.test", sp_sls_url=sls)
    req = _fake_request_with_query(params, base_url="https://app.test/")
    # real process_logout → real signature validation; must NOT raise, must surface the NameID
    out = NativeSAMLProvider().process_logout(conn, req)
    assert out.name_id == "jane@acme.test"
```

`SamlIdpDouble` (`tests/integration/saml_idp_double.py`):
```python
class SamlIdpDouble:
    """In-process IdP with a throwaway RSA-2048 keypair. Mints genuinely-SIGNED Redirect-binding
    LogoutRequest / LogoutResponse so the SP's real process_slo / validate_binary_sign runs. No infra."""
    def __init__(self, *, entity_id: str, slo_url: str):
        # generate RSA-2048 + a self-signed cert (reuse generate_sp_keypair from saml_sp_keys)
        from dazzle.http.runtime.auth.saml_sp_keys import generate_sp_keypair
        self.entity_id, self.slo_url = entity_id, slo_url
        self._key_pem, self._cert_pem = generate_sp_keypair(entity_id)
    @property
    def idp_cert(self) -> str: return self._cert_pem
    def signed_logout_request(self, *, name_id, sp_sls_url) -> dict: ...   # SAMLRequest
    def signed_logout_response(self, *, in_response_to, sp_sls_url) -> dict: ...  # SAMLResponse
    # internals: build minimal LogoutRequest/Response XML (Issuer=entity_id, Destination=sp_sls_url,
    # NameID for the request), deflate_and_base64_encode, build the canonical
    # "SAML(Request|Response)=<quote>&SigAlg=<quote>" string, OneLogin_Saml2_Utils.sign_binary(key),
    # b64encode → {"SAMLRequest"|"SAMLResponse", "SigAlg", "Signature"}.
```
Iterate the query construction (param order, `urllib.parse.quote(safe='')`, SigAlg value) until the
Step-1 test's real `process_slo` returns clean. That agreement IS the proof the encoding is right.

- [ ] **Step 2: Tier-2 behavioural tests** (real crypto, end-to-end through the route):
  - **SP-initiated completion:** a double-signed `LogoutResponse` → GET `/auth/saml/sls` → 303/200
    logged-out, **no kill** (it's a response).
  - **IdP-initiated, real signature (retro-hardens feature A):** a double-signed `LogoutRequest` →
    SLS → **org-scoped kill fires** (seed a user+membership+session); the signature was really validated.
  - **Tamper → rejected:** flip one byte of the `Signature` param → SLS → 400, **nothing killed**.
    (The seam-faked A tests can't catch a signature regression; this does.)

- [ ] **Step 3: Run** `DATABASE_URL=…/dazzle_dev pytest tests/integration/test_saml_routes.py -q`
(Tier-2 needs `[saml]`; gated by importorskip — runs in CI `integration`). All PASS.

---

### Checkpoint — independent security review

- [ ] Dispatch `feature-dev:code-reviewer` on the diff. Focus: (1) local logout is **unconditional
and first** — no SP-SLO path can skip/defer it; (2) `name_id` is only the session user's own email
(SP can't ask the IdP to log out a different user); (3) the SLS still **400s a forged inbound
LogoutRequest with no kill** (feature-A property unregressed) while only being lenient on a
*LogoutResponse*; (4) no open redirect (slo_url from `auth.logout` over operator `idp_slo_url`);
(5) the `SAMLResponse` zip-bomb guard; (6) the IdP double is test-only (under `tests/`, never imported
by `src/`). Fix any CRITICAL before ship.

---

### Task 6: Docs + ship

- [ ] CHANGELOG `### Added`: "SAML SP-initiated Single Logout — logging out of a SAML session now
also ends the IdP session (signed LogoutRequest → IdP SLO → return to /auth/saml/sls). Completes
bidirectional SLO. Local logout always happens first." Note the reusable real-crypto SAML IdP test
double in `### Agent Guidance`.
- [ ] `/bump patch`; gates (`ruff`, `mypy src/dazzle`, drift/policy, `pytest -m "not e2e"`, postgres
slice); commit (verify `COMMIT_EXIT=0`), tag, push, watch CI (incl. `integration`) + release.
- [ ] Update memory `project_1342_enterprise_auth_capability` — SP-initiated SLO shipped; SAML SLO
bidirectional; note the `SamlIdpDouble` real-crypto harness. Remaining #1342 backlog = the schools
SCIM/SAML streamlining gaps (`dev_docs/2026-06-08-schools-scim-saml-engagement-analysis.md`).

## Self-review

- **Spec coverage:** initiate_logout (T1), generic-logout integration via helper (T2/T3), SLS
  response handling + guard (T4), the real-crypto IdP double + tamper test (T5), review (checkpoint). ✓
- **Type consistency:** `initiate_logout(..., *, name_id) -> str`; `saml_slo_redirect_url(..., *,
  session_id) -> str | None`; reuses `_slo_settings`, `process_logout`, `generate_sp_keypair`. ✓
- **De-risking:** the IdP double's signed-query format is verified against the real `process_slo`
  (Task 5 Step 1 is built first and iterated), not assumed from docs. ✓
- **No placeholders in shipped code:** the `...` bodies are in the TEST double's method stubs, to be
  filled while iterating Step 1; all `src/` code is complete.
