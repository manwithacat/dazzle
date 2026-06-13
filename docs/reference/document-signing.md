# Document Signing (`signable: true`)

Native PAdES B-T document signing as a first-class DSL primitive. Mark
an entity `signable: true` and the framework provides:

- An 11-field schema extension covering status workflow, signing
  metadata, and audit timestamps.
- Two auto-mounted routes (`GET /sign/...`, `POST /api/sign/...`)
  that drive the signing flow end-to-end.
- A browser-side signing pad Island for handwritten signatures.
- A CLI command to mint the project's CA + signing cert chain.
- An optional `signing_validator:` hook for project-specific business
  rules (grant checks, domain invariants).

**Conformance:** PAdES B-T (Basic + RFC 3161 timestamp). Exceeds
DocuSeal OSS (B-B only).

**Legal basis:** UK SES under the Electronic Communications Act 2000
and retained UK eIDAS. Sufficient for B2B contracts, engagement
letters, MSA/DPA, employment offers, NDAs, and similar. Higher tiers
(AES, QES) require HSM-backed certificates and are out of phase-1
scope.

**Status:** introduced in v0.79.7 (#1283). End-to-end usable from
v0.79.10.

## Installation

```bash
pip install "dazzle-dsl[signing]"
```

Brings in `fpdf2`, `pyhanko`, `Pillow`, and `cryptography`. All
pure-Python — no system dependencies.

## Quick start

### 1. Mint the project cert

```bash
dazzle signing init --project-name "Acme Ltd"
```

Outputs three env vars to stdout. Capture them into your runtime:

```sh
SIGNING_CERT_PASSWORD="..."
SIGNING_CERT_PFX_B64="..."
SIGNING_TOKEN_SECRET="..."
```

Pass `--heroku-app NAME` to get `heroku config:set` invocation hints
emitted alongside the values.

!!! warning "Cert rotation"
    Re-running `dazzle signing init --force` mints a **new** CA;
    every previously signed document becomes unverifiable against the
    new chain. Phase 1 ships one CA per project on purpose. Document
    rotation explicitly in any runbook before adopting in production.

### 2. Declare a signable entity

```dsl
entity Contract "Service Contract":
  id: uuid pk
  party: str(200) required
  effective_date: date
  signable: true
```

`dazzle validate` accepts the entity; the linker auto-injects 11
framework-canonical fields and sets the audit default. **Project-
declared fields with the same name always win** — use this to widen
the `status` enum or `signing_url` cap.

### 3. Mint a signing link

```python
from dazzle.signing.tokens import mint_token

token = mint_token(str(contract.id), signatory_email)
url = f"https://app.example.com/sign/Contract/{contract.id}?token={token}"
# Email `url` to the signatory.
```

### 4. The signer flow

When the signatory opens the link:

1. `GET /sign/Contract/{id}` validates the token, transitions the row
   `status: sent → viewed`, stamps `viewed_at` / `signer_ip` /
   `signer_user_agent`, and renders the signing page.
2. The signing-pad Island mounts client-side.
3. The signatory ticks the authority-declaration checkbox, signs on
   the canvas, and clicks **Sign & Submit**.
4. `POST /api/sign/Contract/{id}` runs the optional
   `signing_validator:` hook, generates the PDF, applies the PKCS#7
   + RFC 3161 signature, transitions `status: viewed → signed`, and
   returns the signed PDF inline.
5. The browser downloads the signed PDF automatically. If file
   uploads are enabled, the PDF is also persisted via the project's
   file backend and the row's `signed_document` field is patched
   with the URL.

## Auto-injected fields

When `signable: true` is set, the linker appends every field below
whose name is not already declared:

| Field | Type | Notes |
|---|---|---|
| `status` | `enum[draft, sent, viewed, signed, declined, expired, superseded]` required | Project may widen the enum |
| `signing_service` | `enum[native, manual]` required | `manual` is the paper escape hatch |
| `signing_url` | `str(500)` optional | HMAC-signed URL |
| `signed_document` | `file` optional | Set when file storage is wired |
| `signing_token_hash` | `str(64)` optional | SHA-256 of the issued token |
| `signer_ip` | `str(45)` optional | IPv6-safe |
| `signer_user_agent` | `str(500)` optional | |
| `sent_at` | `datetime` optional | |
| `viewed_at` | `datetime` optional | |
| `signed_at` | `datetime` optional | |
| `expires_at` | `datetime` optional | |

`audit: AuditConfig(enabled=True)` is also defaulted when no `audit:`
block is declared — signing is legally meaningful, so the trail is on
by default.

## Validator hook

Optional dotted-path callable that runs before the PDF is generated:

```dsl
entity Contract "Contract":
  id: uuid pk
  party: str(200) required
  signable: true
  signing_validator: app.signing.validators.verify_party_grant
```

The function is invoked as `fn(entity=..., row=...)`. Raise
`SigningError("...")` to block the signature:

```python
# app/signing/validators.py
from dazzle.signing import SigningError

def verify_party_grant(*, entity, row):
    if not has_grant(row, "approve_contract"):
        raise SigningError("Signatory lacks approve_contract grant")
```

The dotted path is regex-constrained to lowercase identifier segments
(`^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)+$`) before
`importlib.import_module` resolution.

## Routes

### `GET /sign/{entity_name}/{record_id}?token=...`

- **200** — Signing page rendered. Status transitions `sent → viewed`
  on first access; subsequent visits keep `status: viewed`.
- **200** + terminal-status message — Document already `signed`,
  `declined`, `expired`, or `superseded`. No mutation.
- **400** — Missing `token` query parameter.
- **403** — Invalid, expired, or tampered token; or token's
  `record_id` does not match the path. An **expired-but-genuine** link
  (valid HMAC, elapsed expiry) renders the recovery page below instead
  of a bare error; a tampered token gets the plain error.
- **404** — Unknown entity or record.

### `POST /sign/{entity_name}/{record_id}/resend`

Expired-link recovery (TR-53). The body carries the expired token
(`token=...`, form-encoded). The server re-verifies the token's HMAC
(integrity only — expiry is *allowed* to be past), and if a
`resend_hook` is configured, mints a **fresh** link and hands it to that
hook for delivery to the original recipient's email.

- **200** — A new link was delivered; confirmation page shown. The fresh
  token is **never** returned in the response.
- **200** + terminal-status message — Document already `signed` /
  `declined` / `superseded`; nothing to renew.
- **403** — Token tampered or `record_id` mismatch.
- **404** — No `resend_hook` configured (self-serve renewal unavailable).
- **500** — The `resend_hook` raised; a generic "couldn't send" page is
  shown.

The expired link's valid HMAC proves only that the bearer once held a
legitimate link, which authorises **requesting** a fresh one be sent to
the original email — never extending the link in the browser. An
attacker replaying a stale link only triggers a mail to the genuine
signer.

### `POST /api/sign/{entity_name}/{record_id}`

Request body:

```json
{
  "token": "...",
  "signatory_name": "Alice",
  "signature_png_b64": "iVBORw0KGgo...",
  "decline": false,
  "decline_reason": null
}
```

- **200** + `application/pdf` body — Signed PDF (download triggered
  by the Island). Status transitions to `signed`; `signed_at` and
  `signing_token_hash` are stamped.
- **200** + `{"status": "declined"}` — When `decline: true` is set.
  Status transitions to `declined`.
- **400** — `signing_validator` raised `SigningError`, or the
  validator dotted-path is malformed.
- **403** — Invalid token or token/record mismatch.
- **404** — Unknown entity or record.
- **409** — Document is in a terminal status (`signed`, `declined`,
  `expired`, `superseded`).

## Token contract

Tokens are URL-safe base64 of `<record_id>:<email>:<expires>:<hmac>`,
where `<hmac>` is `HMAC-SHA256` of the payload keyed on
`SIGNING_TOKEN_SECRET`.

```python
from dazzle.signing.tokens import mint_token, verify_token, token_hash

token = mint_token("a3f1...", "alice@example.com", expires_hours=72)
record_id, email = verify_token(token)
audit_hash = token_hash(token)  # sha256, 64-char hex
```

Default expiry is 72 hours. The verify routine raises
`InvalidTokenError` on tampering, expiry, or malformed input.

## Environment variables

| Variable | Purpose | Required? |
|---|---|---|
| `SIGNING_TOKEN_SECRET` | HMAC key for signing tokens | Always |
| `SIGNING_CERT_PFX_B64` | Base64-encoded PKCS#12 cert + key chain | When the POST handler runs |
| `SIGNING_CERT_PASSWORD` | PKCS#12 encryption password | When the POST handler runs |

The CLI minted all three on first setup. Capture them into your
production environment (Heroku config vars, AWS Parameter Store, etc.).

## PDF branding

The signed PDF carries an organisation header, optional tagline, and
an optional footer line. Configure them in `dazzle.toml`:

```toml
[signing]
organisation = "Acme Ltd"
tagline = "Chartered Accountants"
footer_text = "Acme Ltd | Registered in England & Wales"
location = "England and Wales"
```

`location` is recorded on every PKCS#7 signature (the
`PdfSignatureMetadata.location` field) — it should reflect the legal
jurisdiction of the signer.

Resolution order at runtime:

1. **`[signing]`** block with `organisation` set → full quartet wired
   onto the PDF.
2. **`[project] name`** → minimal fallback. Project name appears as
   the organisation; tagline + footer stay empty.
3. **Nothing useful** → framework default `PdfBranding(organisation="Dazzle App")`.

## Expired-link recovery

When a signer opens an expired link, the default page is a dead end —
no way forward without contacting the sender out of band. Two optional
`[signing]` keys turn that into a recovery path:

```toml
[signing]
support_contact = "help@acme.example"
resend_hook = "app.signing.resend.deliver"
```

- **`support_contact`** — an email or URL shown on signing error pages
  as the human fallback. With nothing else configured, the expired page
  says "contact …" instead of just "expired".
- **`resend_hook`** — a dotted path to a project callable
  `fn(*, entity_name, row, email, signing_url)`. When set, the expired
  page offers a one-click **"Request a new signing link"** button; on
  submit the framework mints a fresh link and calls your hook to deliver
  it to `email` through your own channel (transactional email, queue,
  …). The hook may be sync or async and may raise `SigningError` to
  signal a delivery failure.

```python
# app/signing/resend.py
from app.mail import send_email   # your project's mailer

def deliver(*, entity_name, row, email, signing_url):
    send_email(
        to=email,
        subject="Your new signing link",
        body=f"Open your document to sign: {signing_url}",
    )
```

**Security:** the expired token's valid HMAC authorises *requesting* a
new link sent to the original recipient — nothing more. The fresh token
never returns to the browser, so a replayed stale link can only trigger
a mail to the genuine signer, never extend access for the bearer.

## Architecture

```
+----------------+      mint_token()      +----------------+
|  Your code     | ---------------------> | dazzle.signing |
|                |                        |    .tokens     |
+----------------+                        +-------+--------+
                                                  |
        Email link with token                     |
                |                                 |
                v                                 v
+----------------+   GET /sign/...   +----------------+
|   Signatory's  | ----------------> | dazzle.signing |
|     browser    | <---------------- |    .routes     |
+--------+-------+   HTML + Island   +-------+--------+
         |                                   |
         | POST /api/sign/...                |
         | { token, signature_png_b64 }      |
         v                                   v
                                    +----------------+
                                    | dazzle.signing |
                                    |    .service    |
                                    |   (fpdf2 +     |
                                    |    pyhanko)    |
                                    +----------------+
```

## Limitations + future work

The phase-4 surface covers the canonical happy path. Known gaps:

- **Project-side document template lookup.** The PDF body is
  currently a placeholder ("entity name + id"). Phase 5 deliberately
  defers the templating-system decision — Jinja2 was retired in
  ADR-0023, so the right shape is likely a typed-Fragment template
  function or a project-supplied HTML callable. See the issue thread
  for the latest direction.
- **Per-tenant CAs.** Phase 1 ships one CA per project. Multi-tenant
  Dazzle apps (e.g. one Dazzle install serving N schools) use the
  project identity on the cert; tenant identity belongs in the
  document body.
- **AES escalation.** No HSM-backed CSP support yet. The env-var
  shape is forward-compatible: a future `SIGNING_CERT_SOURCE`
  selector can swap the PKCS#12 source without breaking the entity
  contract.

## See also

- ADR-0023 — Jinja2 removal (relevant to the template-lookup
  decision).
- Issue #1283 — primary tracking issue for the primitive's design
  + phasing.
- `src/dazzle/signing/` — the runtime package (tokens, cert, service,
  routes).
- `src/dazzle/cli/signing.py` — `dazzle signing init`.
- `src/dazzle/ui/runtime/static/js/islands/signing-pad.js` — the
  browser-side Island.

## QA trial harness

`dazzle qa trial` automatically grades signing flows when the app
contains any `signable: true` entity. Five persona-facing tools are
registered on top of the usual trial tool set:

- `read_inbox` — list documents awaiting signature.
- `open_signing_link` — open a link by entity + id + token.
- `sign_document` — submit the signature (requires
  `authority_confirmed: true`).
- `decline_signing` — decline with a reason.
- `tamper_token` — retry the GET with a mangled token.

After the persona ends, the harness inspects the runtime DB, runs
pyhanko on the signed PDF if one was produced, and merges a
`signing_outcomes` block into the trial report. The block has these
keys: `detected`, `expected_outcome_inferred`, `functional`,
`signature_integrity`, `latency_ms`.

### Provisioning

The harness mints an ephemeral ECDSA cert chain into a per-run tmpdir
and injects `SIGNING_CERT_PFX_B64`, `SIGNING_CERT_PASSWORD`,
`SIGNING_TOKEN_SECRET` into the `dazzle serve` subprocess. Torn down
on exit.

### Validator-rejected scenarios

Set `DAZZLE_QA_SIGNING_REJECT_IDS=<id>` and the project's validator
hook will consult that list. Both `contact_manager` and
`support_tickets` ship validator hooks that follow this convention.

### Reference scenarios

`examples/contact_manager/trial.toml` and
`examples/support_tickets/trial.toml` each declare 5 signing scenarios
(happy path, declined, token expired, validator-rejected,
already-signed).
