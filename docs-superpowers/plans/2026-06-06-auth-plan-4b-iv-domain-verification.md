# Auth Plan 4b.iv — Connection admin CLI + domain verification

> **For agentic workers:** hybrid inline execution + adversarial review (anti-hijack gate).

**Goal:** Give an operator/agent a CLI to manage per-org enterprise connections and to
**verify domain ownership** via DNS TXT — the step that moves a domain from claimed
(`domains`) to trusted (`verified_domains`), which is what authorizes an IdP to assert
identities (the anti-hijack gate the routing + JIT join depend on).

**Architecture:** Verification token is **HMAC-SHA256(connection-secret-key, "domain-verify:
<conn_id>:<domain>")** — deterministic, no storage/migration, unforgeable without the
deployment's `DAZZLE_CONNECTION_SECRET` (the key connections already require). `verify_domain`
does a DNS-TXT lookup through an injectable resolver seam (dnspython default, fake in tests),
checks the token, enforces **one-owner-per-domain uniqueness** (the promise deferred at
`store.py:1198`), and on success appends to `verified_domains`. The admin surface is the
`dazzle auth connection` CLI (DB access = authz, like the rest of `dazzle auth` — agent/devops
driven, matching the north-star), not an in-app RBAC surface.

**Tech Stack:** stdlib `hmac`/`hashlib`, `dnspython` (`[sso]` extra, lazy import), the 4a
connection store API, Typer.

---

## Security properties (must hold)

1. **Unforgeable token** — HMAC under `DAZZLE_CONNECTION_SECRET`; an attacker can't compute the
   TXT value to publish without the deployment key. Per-(connection, domain) so a token for one
   pair never verifies another.
2. **One owner per domain** — `verify_domain` refuses if the domain is already verified by a
   *different* connection (else two orgs could both route/assert it). Same-connection re-verify
   is idempotent.
3. **Fail-closed** — no `DAZZLE_CONNECTION_SECRET` → cannot compute a token → cannot verify
   (raises). A DNS lookup error / missing TXT → not verified (never a silent pass).
4. **Verified ≠ claimed** — verification only ever *adds* to `verified_domains`; the claimed
   `domains` list is advisory and never routes.

## Task 1: domain-verification kernel

**Files:** Create `src/dazzle/http/runtime/auth/domain_verification.py`,
`tests/unit/test_domain_verification.py`. Add `set_connection_domains` to `store.py`.

- `DomainVerificationError(reason, message)`, `verification_token`, `txt_record`,
  `DnsTxtResolver` Protocol, `DnspythonResolver`, `verify_domain(store, connection, domain, *, resolver)`.
- Tests (fake resolver, monkeypatched key): token determinism + per-pair distinctness; TXT
  present → verified + `set_connection_verified_domains` called with the union; TXT absent →
  False; already-verified-by-another-connection → raises; no key → raises; idempotent re-verify.

## Task 2: `dazzle auth connection` CLI

**Files:** Create `src/dazzle/cli/auth_connection.py`; wire `auth_app.add_typer(...)` in
`src/dazzle/cli/auth.py`.

- `create` / `list` / `add-domain` (prints the TXT record to publish) / `verify-domain`
  (dnspython resolver; prints the TXT to add on miss) / `delete`. Store accessed lazily via
  `_get_auth_store` (avoids an import cycle).

## Task 3: deps + verify + review + ship

- Add `dnspython>=2.0` to the `[sso]` extra.
- ruff + mypy + drift + mkdocs --strict; full unit slice.
- Adversarial review (silent-failure-hunter) on token forgeability + uniqueness + fail-closed.
- `/bump patch`, CHANGELOG `### Added` + `### Agent Guidance`, ship.
