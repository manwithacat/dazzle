# ADR-0035 — QA-Auth Containment Invariant

**Status:** Accepted 2026-06-05 — **implemented** (#1339). RLS Phase E.2. Completes RLS Phase E (excision was E.1, #1338).
**Issue:** #1339 (signed/contained QA auth + ephemeral test-tenant provisioning), from AegisMark's QA harness. Spec: `docs/superpowers/specs/2026-06-04-tenant-lifecycle-design.md` §5; plan: `docs/superpowers/plans/2026-06-05-rls-phase-e2-qa-auth-containment.md`.
**Relates:** ADR-0033 (CSRF-as-auth-class — the HMAC channel is `NA_SIGNATURE`, structurally CSRF-immune), ADR-0008 (PostgreSQL-only), the auth identity model (Plan 1a–1c: global Identity + fenced Membership + Session(active_membership)) and its RLS fence (Phase B, `dazzle.tenant_id`). Builds on the Slice-0 `is_test` column + reserved `qa-`/`qa_` namespace.

## Context

A CI/QA harness must authenticate into ephemeral test tenants without real user credentials — it provisions a throwaway tenant, drives the app through its real HTTP surface, then tears the tenant down. The dev-only `qa_routes.py` magic-link path is gated purely on env flags (`DAZZLE_ENV=development` + `DAZZLE_QA_MODE=1`) and mints a session for *any* email — acceptable for a local dev box, categorically unacceptable anywhere a real tenant's data lives.

The hazard is specific and severe: **a QA-auth channel that can mint a session is one config slip away from minting a session into a *production* tenant.** An attacker who learns the QA secret (or a misconfigured deployment) must not be able to authenticate as a real user in a real tenant, even knowing that user's email.

## Decision

**A QA-auth mint may scope a session ONLY into a tenant the database itself confirms is a test tenant — resolved from the DB record, never from request input.** Concretely (`qa_secure_routes.py` `POST /qa/secure/mint`):

1. **Secret-gated + self-disabling.** The router factory returns `None` when `QA_AUTH_SECRET` is unset, so the route is *not mounted* — prod-off-by-default with no request-time flag to misconfigure. (Defence-in-depth: the handler re-reads the secret at request time.)
2. **Signed channel (`NA_SIGNATURE`).** The request carries an HMAC-SHA256 token over `email:run_id:issued_ts` keyed by `QA_AUTH_SECRET`, verified constant-time (`hmac.compare_digest`) within a ~60s replay window (rejecting both stale and far-future timestamps). The signature *is* the credential; CSRF is categorically N/A (ADR-0033). Stdlib `hmac` — no new dependency.
3. **The containment invariant (the crux).** The target org is resolved from the **signed** `run_id` (`organizations` where `slug = qa-<run_id>`), never a request-supplied tenant id (no confused-deputy). The mint **refuses (403)** unless *all* hold:
   - the org's `slug` is in the reserved `qa-` namespace, **and**
   - the org's `is_test` column is `true` — **a column, not a slug heuristic, hence unforgeable from the request**, **and**
   - the org exists and the (signed) target user has an **active membership** in it.
   Any one failing → an opaque 403 (no client-facing oracle distinguishing which gate failed; the reason is logged server-side). `email` comes from the signed claims, not the body.
4. **Structural fencing.** The minted session binds `active_membership.tenant_id = organizations.id = dazzle.tenant_id`, so even a hypothetically mis-minted session is fenced by Postgres RLS (Phase B) to that one tenant — defence in depth beneath the app-layer invariant.

Teardown reuses the E.1 excision primitive (`excise_tenant`); provisioning (`provision_test_tenant`) creates the `qa-<run_id>`, `is_test=true` org + admin + membership (the framework org IS the QA tenant — no domain tenant-root row).

## Consequences

- **The QA secret can never reach a real tenant.** Even with a known real email, the DB `is_test` lookup of that user's org fails the gate — the cardinal failure mode is structurally prevented, not merely discouraged.
- **Defence in depth:** reserved-namespace ∧ `is_test` ∧ run-match ∧ active-membership — four independent conditions, any one refusing.
- **Auditable + off-by-default:** the route's existence is conditioned on the secret; its refusals are logged; the guarantee is recorded here.
- **Adversarial tests are first-class:** real-PG proofs that a valid token cannot mint into a non-`is_test` org, that replay/tampered/wrong-secret/run-mismatch tokens 403, that a user shared across a test+real org is scoped to the test org only, and that delimiter-injection in claims can't re-parse a forged payload.

## Alternatives rejected

- **Request-supplied tenant id** — a confused-deputy: the caller could name a real tenant. Resolution must be from the signed `run_id` → DB record only.
- **Slug-prefix-only heuristic** (`qa-` without the `is_test` column) — forgeable/ambiguous; a real org could be named `qa-…`. The `is_test` boolean is the unforgeable signal (the test `qa-realish` is_test=false is correctly refused).
- **`itsdangerous` for signing** — dependency hygiene; stdlib `hmac` is sufficient and already imported.
- **Reusing/loosening the dev `qa_routes.py`** — would erode the "dev route stays dev" boundary; the secret-gated tier is a physically separate, auditable module.
- **A runtime `if prod: disable` branch** — a flag to misconfigure; self-disabling-by-non-mount is safer.
