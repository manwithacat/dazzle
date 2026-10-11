# Auth Plan 5.i — NativeSAMLProvider (SP validation kernel)

> **For agentic workers:** hybrid inline execution + adversarial review (SAML = the most
> footgun-laden auth protocol; signature/XXE validation is DELEGATED to python3-saml).

**Goal:** Fill the `(saml, native)` ConnectionProvider seam — SP-initiated SAML 2.0:
`initiate` builds the AuthnRequest redirect; `callback` validates the IdP's SAML Response
(signature, conditions, audience, InResponseTo) and returns an `AssertedIdentity`. All XML
parsing + signature validation is **python3-saml's** job (secure defaults: `strict=True`,
`wantAssertionsSigned=True`) — no hand-rolled XML (XXE/signature-wrapping live in the lib).

**Architecture:** Per-connection settings are built from the connection's `config`
(`idp_entity_id` / `idp_sso_url` / `idp_x509_cert` [public cert string] / optional
`sp_entity_id` / attribute names) — a dict, no files on disk. `callback` reads the POSTed
`SAMLResponse`, hands it to `OneLogin_Saml2_Auth.process_response(request_id=<stashed>)`,
and only on `is_authenticated()` + no errors maps NameID/attributes → `AssertedIdentity`
(`claims_source="saml_assertion"`). The JIT join (5.ii) reuses `provision_enterprise_login`;
its differential-trust is generalized to a **validated-sources set** `{id_token, saml_assertion}`
so a signature-validated SAML assertion is trusted (the unsigned OIDC UserInfo fallback still
requires `email_verified`). python3-saml → a new **`[saml]` extra** (needs native libxmlsec1),
lazy-imported; the construction is behind `_build_auth` so tests mock it (no xmlsec needed).

**Tech Stack:** python3-saml (`onelogin.saml2`), the 4a seam, the 4b.ii join.

---

## Security properties (must hold)

1. **Validation delegated + strict** — `strict=True` + `wantAssertionsSigned=True`; `callback`
   fails closed unless `get_errors()` is empty AND `is_authenticated()`. No assertion is trusted
   without a valid signature against the connection's configured IdP cert.
2. **No hand-rolled XML** — never parse/canonicalize/verify XML ourselves (XXE, signature
   wrapping, comment truncation are the library's concern).
3. **Replay protection** — `initiate` stashes the AuthnRequest id; `callback` passes it to
   `process_response(request_id=…)` so an unsolicited/replayed Response is rejected (InResponseTo).
4. **Email required** — empty NameID/email → refuse (no empty identity asserted).
5. **Trusted source** — `claims_source="saml_assertion"` is in the validated set, so the join
   trusts it like an id_token; the unsigned UserInfo fallback alone still needs `email_verified`.

## Task 1: trust-model generalization

**Files:** Modify `src/dazzle/http/runtime/auth/enterprise_login.py` (+ test).

- `_VALIDATED_CLAIMS_SOURCES = frozenset({"id_token", "saml_assertion"})`; the differential-trust
  check uses `claims_source not in _VALIDATED_CLAIMS_SOURCES`.

## Task 2: the provider

**Files:** Create `src/dazzle/http/runtime/auth/saml_provider.py`, `tests/unit/test_saml_provider.py`.
Add `[saml]` extra (`python3-saml`) to `pyproject.toml`.

- `NativeSAMLProvider` (`_settings`, `_request_data`, `_build_auth`, async `initiate`/`callback`,
  `_extract_email`/`_extract_groups`), `register_native_saml()`.
- Tests (mock `_build_auth` → fake auth): settings built from config; missing config → ConnectionError;
  initiate returns the login URL + stashes request id; callback maps validated auth → AssertedIdentity
  (`claims_source="saml_assertion"`, email from attr or NameID, groups); errors/not-authenticated →
  ConnectionError; empty email → ConnectionError; register→resolve.

## Task 3: verify + review + ship

- ruff + mypy + drift + mkdocs --strict; full unit slice.
- Adversarial review (silent-failure-hunter) on fail-closed validation + replay + email.
- `/bump patch`, CHANGELOG `### Added` + `### Agent Guidance`, ship.
