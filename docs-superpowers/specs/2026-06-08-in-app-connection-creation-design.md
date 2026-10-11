# In-app enterprise connection creation (OIDC + SCIM + SAML) — Design

**Issue:** #1342 (enterprise auth deferred backlog) — Tooling item "In-app connection *creation* surface".

## Goal

Let an org admin **create** an enterprise connection (OIDC / SCIM / SAML) from the existing
`/auth/connections` web surface, not just manage domains. Today creation is CLI-only — a
deliberate gate because creation accepts IdP **secrets** and the read surface is intentionally
secret-free. This adds the secret-input + masked-display story so creation can move in-app while
keeping every existing invariant (RBAC gate, org-fence, CSRF, secret-at-rest, secret-free reads).

## Security invariants (unchanged, all preserved)

- **RBAC gate** — same `_gate(request)`: caller has an ACTIVE membership in their active org whose
  roles intersect `app.state.org_admin_roles` (fail-closed `may_manage_members`). Ungated → 403.
- **Org-fence** — the new connection's `tenant_id` is **always** the caller's active membership's
  `tenant_id`, never request input. No cross-org creation is expressible.
- **CSRF** — `/auth/connections/create` is added to `csrf.protected_paths` (authenticated,
  same-origin mutation — like add-domain/verify-domain).
- **Secret-at-rest** — secrets go straight to `store.create_connection(..., secrets=...)` which
  AES-GCM-encrypts them; the route never persists plaintext.
- **Secret-free reads** — the connection list still never renders stored secret material. The
  only secret ever shown is the SCIM bearer, **once**, at the moment of minting (below).

## Per-type creation

| Type | Form fields | Secret | Post-create |
|------|-------------|--------|-------------|
| **OIDC** | `issuer` (url, required), `client_id` (text, required), `client_secret` (**password**, required), `group_map` (text, optional) | `{client_secret}` (operator-supplied) | redirect to list |
| **SCIM** | `group_map` (text, optional) | `{scim_bearer}` — **server-minted** (`secrets.token_urlsafe(32)`) | render list + **one-time bearer banner** (shown once, never stored plaintext, never in a URL) |
| **SAML** | `idp_metadata_url` (url, optional) **or** explicit `idp_entity_id` + `idp_sso_url` + `idp_x509_cert` (textarea); `email_attribute`/`groups_attribute` (optional); `group_map` | none (the IdP signing cert is **public** → config, not secret) | redirect to list |

SAML metadata import reuses the SSRF-guarded `saml_metadata.fetch_idp_metadata` +
`parse_idp_metadata_xml` (https-only, public-IP-only, no redirects, size-capped, XXE-safe parse) —
identical to the CLI `create-saml`. Explicit fields override metadata; require either a metadata
URL or all three explicit values (mirrors the CLI's `missing` check).

SAML request-signing / assertion-encryption keypairs stay CLI-only (`enable-request-signing`,
`enable-assertion-encryption`) — out of scope for create; a created SAML connection is the basic
signed-Response trust model, hardened later via those existing commands.

## UX (typed-Fragment + HTMX, no SPA)

`connections_page` gains a `?new=<type>` query param:
- An **"Add a connection"** area renders three links — *Add OIDC* / *Add SCIM* / *Add SAML* — each
  a GET to `/auth/connections?new=<type>`.
- When `new ∈ {oidc, scim, saml}`, the page additionally renders that type's create form
  (`FormStack` of typed `Field`s, POST `/auth/connections/create`, hidden `type`). One form at a
  time — no JS conditional show/hide, fits the server-render substrate.
- Reuses the existing page route (no new GET route); the form is just another Fragment in the page.

`POST /auth/connections/create` (gated, org-fenced):
1. Read `type` (form field). Reject unknown types (400).
2. **OIDC/SCIM require `DAZZLE_CONNECTION_SECRET`** (the at-rest key) — if `environment_flags()[0]`
   is False, return a 400 with the same remedy text the doctor uses (can't encrypt the secret).
   SAML has no secret, so it doesn't require the key.
3. Validate per type (below). On invalid input → 400 with a clear message (no stack leak).
4. `store.create_connection(tenant_id=org_id, type=..., config=..., secrets=..., domains=[], group_mapping=...)`.
5. OIDC/SAML → `_back(request)` (303 / HX-Redirect to the list). SCIM → render the list page with a
   one-time banner showing the minted bearer + the SCIM base URL, with copy-now guidance.

### Validation (server-side, reuses CLI shapes)

- OIDC: `issuer` is an `https://` URL; `client_id`, `client_secret` non-empty.
- SCIM: nothing required.
- SAML: a metadata URL **or** all of (entity_id, sso_url, cert); `SamlMetadataError` from a bad
  metadata fetch → 400 with `exc.reason` (never a 500/stack).
- `group_map` text `"idp-group=role, other=role2"` → parsed to `{idp-group: role, ...}`; malformed
  pairs are skipped (lenient), mirroring the CLI's `_parse_group_map`.

## Files

| File | Change |
|------|--------|
| `connection_admin_routes.py` | `connections_page(new="")` renders the create area + form; new `POST /auth/connections/create` handler (gated, org-fenced, per-type dispatch). |
| `connection_admin_views.py` | `build_connections_view(..., new_form=None)` renders the "Add a connection" links + the active type's `FormStack`; a `scim_bearer_once` param renders the one-time banner. |
| `csrf.py` | add `/auth/connections/create` to `protected_paths`. |
| `connection_create_form.py` (new, small) | pure helpers: per-type field specs, `parse_group_map`, SAML config assembly (reused by the route + tested without HTTP). |

Keeping the per-type field specs + parsing/validation in a small pure module (`connection_create_form.py`)
keeps the route thin and lets the logic be unit-tested without a request — the same seam the rest of
the auth code favours.

## Non-goals

- No SAML signing/encryption keypair setup at create (existing `enable-*` CLI commands own that).
- No edit/delete-from-create (delete already exists; edit is a separate concern).
- No file-upload for SAML cert/metadata (textarea + metadata-URL cover it; file upload is CLI-only).
- No change to the secret-free read surface, the gate, or the org-fence.

## Testing

`tests/unit/test_connection_create_form.py` (pure helpers): group-map parse (valid/malformed/empty);
per-type required-field validation; SAML config assembly (explicit, metadata-derived, explicit-overrides);
OIDC issuer https check.

`tests/integration/test_connection_admin_routes.py` (extend; TestClient + fake store):
- `?new=oidc|scim|saml` renders the matching form; no `new` → no form.
- POST create OIDC → store.create_connection called with `{client_secret}` in secrets, redirect; the
  client_secret never appears in any rendered HTML.
- POST create SCIM → a bearer is minted, shown **once** in the response, and passed to create; a
  subsequent list render does NOT contain it.
- POST create SAML with explicit fields → config carries entity_id/sso_url/cert; with a metadata URL
  (injected fetch) → config derived; a `SamlMetadataError` (injected) → 400, no 500.
- **Gate**: ungated caller → 403; **org-fence**: created connection's tenant_id == caller's org.
- **No key**: `secret_key_ok=False` → OIDC/SCIM create 400 with the remedy; SAML still allowed.
- **CSRF**: `/auth/connections/create` is in `protected_paths` (assert via the csrf config).
