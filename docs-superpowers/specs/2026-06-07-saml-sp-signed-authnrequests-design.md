# SAML SP-signed AuthnRequests (Feature C) — Design

**Issue:** #1342 (enterprise auth) — SAML cluster, feature 2 of 4.
**Date:** 2026-06-07
**Status:** Approved (design), pending spec review.

## Problem

Dazzle (the SP) sends *unsigned* AuthnRequests. Some IdPs (and stricter deployments)
require the SP to **sign** its AuthnRequest so the IdP can verify the request originated
from the registered SP. This needs a per-connection SP keypair — which **also** unblocks
encrypted assertions (feature B, reuses the keypair) and SP-signed SLO (feature A).

The Response/assertion signature remains the trust anchor; this adds *request* signing, it
does not change how responses are validated.

## Scope

- **In:** per-connection SP RSA keypair (generate, store encrypted, advertise the cert in
  connection-aware SP metadata); enable/disable request-signing CLI; the
  `authnRequestsSigned` wiring in the python3-saml settings.
- **Out:** encrypted assertions (feature B — reuses this keypair), SLO (feature A). SP-key
  rotation is disable→enable for now (no dedicated rotate). No app-level SP keypair (the
  per-connection model was chosen — each org's SAML relationship is bilateral and
  self-contained, reusing the existing per-connection secret storage + rotation infra).

## Architecture

### New module `src/dazzle/http/runtime/auth/saml_sp_keys.py` (onelogin-free)

```python
def generate_sp_keypair(common_name: str) -> tuple[str, str]:
    """Generate an SP RSA-2048 keypair + self-signed X.509 cert. Returns
    (private_key_pem, cert_pem). CN/subject = common_name (the SP entityId). Pure +
    locally testable (uses `cryptography`, already a [sso] dep — no libxmlsec1)."""
    # rsa.generate_private_key(public_exponent=65537, key_size=2048)
    # x509.CertificateBuilder(): subject==issuer (self-signed), CN, 10-year validity,
    #   serial_number(x509.random_serial_number()), sign(key, hashes.SHA256())
    # → PEM-encode both (PKCS8 private key, no passphrase — it's encrypted at rest by us)
```

The cert is self-signed (an IdP imports it as the trusted SP signing cert; SAML SP certs
are conventionally self-signed — no CA chain needed). Validity ~10 years (re-issue via
disable→enable). Private key PEM is PKCS8, unencrypted *in memory* — it is encrypted **at
rest** by the connection-secret layer (AES-256-GCM), never written in the clear.

### Storage (per connection — reuses existing layers)

- `sp_private_key` (PEM) → connection **`secrets`** (AES-GCM-encrypted at rest, exactly like
  every other secret; masked in `ConnectionRecord.__repr__`).
- `sp_cert` (PEM) → connection **`config`** (public; goes in SP metadata).
- `sign_requests` = `"true"` → connection **`config`** (the on switch).

Two new store methods (the store has no config-merge seam yet):

```python
def enable_connection_request_signing(
    self, connection_id: str, *, sp_cert: str, sp_private_key: str,
    tenant_id: str | None = None,
) -> bool:
    """Persist SP signing material in one transaction: merge {sp_cert, sign_requests:'true'}
    into config and {sp_private_key} into the encrypted secrets blob, bump updated_at.
    Returns True if a row changed. Tenant-fenced when tenant_id given."""

def disable_connection_request_signing(
    self, connection_id: str, *, tenant_id: str | None = None,
) -> bool:
    """Remove sp_cert + sign_requests from config and sp_private_key from secrets
    (one transaction). Returns True if signing was on."""
```

Both read the current `config` (plaintext JSON) + `encrypted_secret` (decrypt → dict),
merge, re-encrypt, and `UPDATE connections SET config=%s, encrypted_secret=%s, updated_at=%s`
in a single `_transaction`. `%s`-bound (no interpolation).

### Signing seam — `_settings()` (saml_provider.py)

After the existing `idp`/`sp`/`security` dict is built, when signing is enabled:

```python
if cfg.get("sign_requests") and (connection.secrets or {}).get("sp_private_key") and cfg.get("sp_cert"):
    settings["sp"]["x509cert"] = cfg["sp_cert"]
    settings["sp"]["privateKey"] = connection.secrets["sp_private_key"]
    settings["security"]["authnRequestsSigned"] = True
    settings["security"]["signatureAlgorithm"] = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
    settings["security"]["digestAlgorithm"] = "http://www.w3.org/2001/04/xmlenc#sha256"
```

python3-saml then signs the AuthnRequest inside `auth.login()` (no change to `initiate`).
`wantAssertionsSigned`/`rejectUnsolicitedResponsesWithInResponseTo` are untouched — response
validation is unchanged.

### Connection-aware metadata

Extend `sp_metadata(self, request, connection=None)`. When a `connection` with `sp_cert` +
`sign_requests` is passed, build SP-only settings that include `sp.x509cert` +
`security.authnRequestsSigned=True` so `get_sp_metadata()` emits a signing `KeyDescriptor`.
No-connection call is unchanged (app-level metadata). Route:

```
GET /auth/saml/metadata               → app-level (today)
GET /auth/saml/metadata?connection=<id> → that connection's metadata, incl. signing cert
```

The route loads the connection (unauthenticated, like the app-level metadata — it exposes
only the public SP cert + ACS URL; connection ids are high-entropy). A missing/unknown id
falls back to app-level metadata (or 404 — see open question below; default: fall back to
app-level so a bad id can't enumerate). The metadata never contains the private key.

### CLI (auth_connection.py)

```
dazzle auth connection enable-request-signing <id>   # saml-only
dazzle auth connection disable-request-signing <id>
```

`enable`: load connection (404 if absent); refuse if `type != "saml"`; if already signing,
report "already enabled" (idempotent, keep the existing key — rotation is an explicit
disable→enable); else `generate_sp_keypair(sp_entity_id)` →
`store.enable_connection_request_signing(...)`; print the metadata URL to re-import at the
IdP. `disable`: `store.disable_connection_request_signing(...)`; report.

## Files

| File | Change |
|------|--------|
| `src/dazzle/http/runtime/auth/saml_sp_keys.py` | NEW — `generate_sp_keypair` |
| `src/dazzle/http/runtime/auth/store.py` | `enable_/disable_connection_request_signing` |
| `src/dazzle/http/runtime/auth/saml_provider.py` | `_settings` signing branch; `sp_metadata(connection=)` + a connection-aware SP-only settings builder |
| `src/dazzle/http/runtime/auth/saml_routes.py` | `/auth/saml/metadata?connection=<id>` |
| `src/dazzle/cli/auth_connection.py` | `enable-/disable-request-signing` |
| `tests/unit/test_saml_sp_keys.py` | NEW — keypair generation (local) |
| `tests/unit/test_saml_provider.py` | `_settings` signing branch; connection-aware metadata (CI onelogin) |
| `tests/unit/test_auth_connection_cli.py` | enable/disable CLI |
| `tests/integration/test_connections_pg.py` | signing material persists (encrypted) |
| `docs/reference/enterprise-sso.md`, `CHANGELOG.md` | matrix row + changelog; bump → v0.81.83 |

## Testing

- **Local (no onelogin):**
  - `generate_sp_keypair`: the returned private-key PEM parses via
    `serialization.load_pem_private_key` and is RSA-2048; the cert PEM parses via
    `x509.load_pem_x509_certificate`, is self-signed (issuer==subject), CN == the given name,
    not expired.
  - CLI `enable-request-signing` on a non-saml connection → `Exit(1)`; on a missing
    connection → `Exit(1)`; happy path records signing material on the fake store + prints
    the metadata URL; `disable` clears it. (Fake store records the calls; no onelogin.)
- **CI (onelogin — now runs, #1345):**
  - `_settings` with `sign_requests` set includes `authnRequestsSigned=True`,
    `sp.x509cert`, `sp.privateKey`, rsa-sha256; without it, none of those appear and
    `wantAssertionsSigned` is still True.
  - `sp_metadata(request, connection=signing_conn)` output contains a
    `KeyDescriptor use="signing"`; the no-connection metadata does not.
  - An end-to-end `initiate` with a fake auth still works (signing is python3-saml's job).
- **Postgres (`-m postgres`):**
  - `enable_connection_request_signing` then `get_connection`: `secrets["sp_private_key"]`
    round-trips; the raw `encrypted_secret` column does NOT contain the PEM in clear; `config`
    has `sp_cert` + `sign_requests`; `repr(conn)` masks the key. `disable_…` removes all three.
    Tenant-fence: a cross-org `tenant_id` is a no-op.

## Docs

`docs/reference/enterprise-sso.md`: flip **SP-signed AuthnRequests | ❌ → ✅** with a note
(per-connection keypair; `enable-request-signing`; Response signature is still the trust
anchor); document the `?connection=<id>` metadata variant + the enable/disable commands.
CHANGELOG `Added` + Agent Guidance (per-connection SP keypair; private key encrypted at rest
+ never rendered; re-import the connection's metadata at the IdP after enabling).

## Execution

Security-sensitive crypto → independent review focused on: (a) keypair generation correctness
(RSA-2048, self-signed, SHA-256, sane validity, PKCS8); (b) `sp_private_key` is stored ONLY in
the encrypted `secrets` blob — never in `config`, the metadata XML, logs, or CLI output;
(c) the `_settings` change does not weaken response validation (`wantAssertionsSigned` /
`rejectUnsolicitedResponsesWithInResponseTo` unchanged); (d) the public metadata endpoint
can't leak anything but the public cert. Run non-e2e (local keypair + CLI; CI onelogin
settings/metadata) + `-m postgres` (storage).

## Open question (resolve in plan)

`?connection=<unknown>` → fall back to app-level metadata (chosen, prevents id-enumeration
signal) vs 404. Default: **fall back to app-level**.

## Failure-mode notes (per CLAUDE.md review rule)

- **Mode risked:** key mismanagement (private key leak) + a weakened trust path.
- **Detectors:** the postgres test asserts no plaintext key in the row + repr masking; the CI
  `_settings` test asserts response-validation flags are unchanged; review gate (c).
- **Live:** these tests run in CI now (`[saml]` extra wired in #1345) + the `-m postgres` job.
- **Traceable:** signing is a per-connection config flag (`sign_requests`) + the cert in
  metadata; the enable/disable CLI is the only writer.
- **Semantics preserved:** XML signing stays python3-saml's job; the assertion-signature
  trust anchor is unchanged; secrets stay in the encrypted store.
