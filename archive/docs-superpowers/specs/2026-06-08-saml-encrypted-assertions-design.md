# SAML Encrypted Assertions (feature B) — Design

**Issue:** #1342 (enterprise auth capability). SAML cluster, feature **B**. Order D→C→B→A;
D (IdP-metadata auto-import) and C (SP-signed AuthnRequests) shipped. A (SLO) follows.

## Goal

Let an operator opt a SAML connection into **encrypted assertions**: the IdP encrypts the
whole SAML assertion to the SP's public certificate, and Dazzle decrypts it with the SP
private key on receipt. One CLI switch per connection, mirroring C's request-signing.

## Mechanism

SAML assertion encryption is XML-Encryption applied to the `<saml:Assertion>` inside the
`<samlp:Response>`. python3-saml handles it transparently:

- **Decrypt on receipt:** with `security.wantAssertionsEncrypted = True` in the SP settings,
  python3-saml requires the incoming assertion to be encrypted and decrypts it using
  `sp.privateKey`. A response carrying a *plaintext* assertion is then rejected (so turning
  this on is a strict posture — only enable it once the IdP is configured to encrypt).
- **Advertise in metadata:** `OneLogin_Saml2_Settings.get_sp_metadata()` calls
  `add_x509_key_descriptors(cert, add_encryption=True)` — when `sp.x509cert` is present the
  generated metadata carries **both** a `use="signing"` and a `use="encryption"`
  KeyDescriptor (same cert for both — the library does not support separate keys). So the
  IdP, on re-import, learns the SP public cert to encrypt to. No new metadata code.

**Single keypair (library-forced).** python3-saml uses one `sp.privateKey` / `sp.x509cert`
pair for signing AND decryption; there is no separate-encryption-key slot. So B **reuses
the exact keypair C generates** (`generate_sp_keypair`, RSA-2048, key encrypted at rest in
the connection `secrets` blob, cert in `config`). This is not a shortcut — it is the only
shape the library supports.

## The one structural change: decouple the keypair lifecycle from `sign_requests`

Today the keypair exists iff request-signing is on: `enable_connection_request_signing`
writes `sp_cert`/`sp_private_key`, and `disable_connection_request_signing` deletes them.
With two independent features sharing one keypair, the keypair must persist while **either**
`sign_requests` **or** `encrypt_assertions` is on.

Refactor `AuthStore` to route keypair writes/removals through two helpers:

- `_ensure_sp_keypair(config, secrets, *, sp_cert, sp_private_key)` — write the cert/key
  only if absent (never clobber an existing keypair, so enabling the second feature keeps
  the first feature's key; rotation stays an explicit disable-both-then-re-enable, as C
  already documents).
- `_maybe_remove_sp_keypair(config, secrets)` — delete `sp_cert`/`sp_private_key` **iff
  neither** `sign_requests` **nor** `encrypt_assertions` remains set.

Then:
- `enable_connection_request_signing` → set `sign_requests='true'` + `_ensure_sp_keypair`.
- `disable_connection_request_signing` → pop `sign_requests`; `_maybe_remove_sp_keypair`.
- `enable_connection_assertion_encryption` (new) → set `encrypt_assertions='true'` +
  `_ensure_sp_keypair`.
- `disable_connection_assertion_encryption` (new) → pop `encrypt_assertions`;
  `_maybe_remove_sp_keypair`.

All four stay SAML-only at the store layer (raise `ValueError` on a non-SAML connection —
the existing guard, so a later `rotate-secret` can't silently destroy an SP key) and write
an audit row to `connection_secret_events`.

### New audit events

`secret_rotation.py` gains `SECRET_EVENT_ENCRYPTION_ENABLED = "sp_encryption_enabled"` and
`SECRET_EVENT_ENCRYPTION_DISABLED = "sp_encryption_disabled"`, mirroring the signing pair.

## Provider settings (`saml_provider.py`)

- `_settings` (full, for ACS/login): when `cfg.get("encrypt_assertions")` and the keypair is
  present, ensure `sp.x509cert` + `sp.privateKey` are in settings (they may already be there
  from signing — set idempotently) and add `settings["security"]["wantAssertionsEncrypted"]
  = True`. Additive to the existing `wantAssertionsSigned`/unsolicited-rejection anchors.
- `_sp_only_settings` (metadata): add the cert/key when `sign_requests` **or**
  `encrypt_assertions` is on (today it's signing-only), so an encryption-only connection
  still advertises its cert → the `use="encryption"` KeyDescriptor appears.

## CLI (`auth_connection.py`)

`enable-assertion-encryption <id>` / `disable-assertion-encryption <id>`, mirroring
request-signing:

- enable: SAML-only guard; if `encrypt_assertions` already set → yellow no-op; reuse an
  existing keypair if present, else `generate_sp_keypair(common_name)`; call the store; print
  the metadata re-import URL + a one-line warning that the IdP must now be configured to
  encrypt assertions (else logins will fail the plaintext-rejected check).
- disable: call the store; report.

## Security review lens (model-driven-failure-modes)

- **Secret at rest:** the SP private key stays in the encrypted `secrets` blob (existing
  AES-GCM `connection_crypto`); never written to config or metadata XML (only the public
  cert is serialized — verified by C's metadata test, extended here).
- **Strict posture:** `wantAssertionsEncrypted=True` means a plaintext assertion is rejected.
  The enable command must warn so an operator doesn't lock out logins by enabling before the
  IdP encrypts. Documented, not silent.
- **No new singletons / DB-side logic;** all behaviour traces from the connection's
  `config`/`secrets` to python3-saml settings — auditable.

## Testing

- `tests/unit/test_saml_provider.py`: `wantAssertionsEncrypted` present iff
  `encrypt_assertions` on + keypair present; absent otherwise; both signing+encryption
  compose (keypair shared); metadata advertises the encryption KeyDescriptor and never the
  private key.
- `tests/unit/test_auth_connection_cli.py`: enable/disable encryption commands; SAML-only
  guard; keypair preserved when the *other* feature is still on; keypair removed when both
  off (the lifecycle decoupling — the core regression risk).
- `tests/integration/test_connections_pg.py`: store round-trip of `encrypt_assertions` +
  audit events against real Postgres; the shared-keypair lifecycle (enable both → disable
  one → keypair survives → disable other → keypair gone).

## Out of scope

- **NameID encryption** (`wantNameIdEncrypted`) — a later micro-feature if a real IdP needs
  it (chosen 2026-06-08).
- Key rotation UX — unchanged from C (disable-both-then-re-enable regenerates).
- SLO (feature A) — next.
