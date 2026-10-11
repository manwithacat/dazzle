# SCIM User externalId echo + dedup (Gap 1) — Design

**Issue:** #1342 (enterprise auth capability) — final SCIM/SAML streamlining gap.

**Goal:** Persist the IdP's stable user identifier (`externalId`, Entra = user objectId GUID) on the membership, echo it in the SCIM User resource, and dedup provisioning by `(tenant_id, externalId)` so a re-push under a *changed email* updates the existing membership instead of forking a duplicate identity.

## Problem

`provision_scim_user` resolves the user by **email only** (`get_user_by_email`). When an IdP renames a user's primary email (common in schools: surname change, marriage, role move) and re-pushes the SCIM User, the new email finds no existing identity → a **new** `users` row + a **new** membership are created. The org now carries two memberships for one human, with the stale one still active until an explicit DELETE that may never come.

Entra also expects the `externalId` it sent to be **round-tripped** in the User resource (it uses it to correlate its directory object to the SP resource). We currently drop it on the User path (Gap 2 already handles it for Groups).

## Decision (depth: dedup + loud-log, no auto-rename)

1. **Persist** `externalId` on the membership (`memberships.external_id` column already exists from the v0.81.98 foundation).
2. **Echo** `externalId` in the rendered SCIM User resource.
3. **Dedup** on POST/PUT: when an `externalId` is supplied, look up the membership by `(tenant_id, external_id)` **first**. If found, that is the membership — even when the pushed email differs from the identity's current email.
4. **On an externalId match with a different email:** keep the existing membership + identity, and emit a **loud WARNING**. Do **NOT** auto-mutate the global identity's email — a global identity can be shared across orgs, so silently rewriting its email from one org's IdP push is a cross-org data-integrity hazard. The warning tells the operator a reconciliation is needed; the membership stays correctly de-duplicated either way.
5. **Backfill:** when an existing membership (found by email, no stored external_id) is provisioned with an externalId, persist it then (first-sight capture).

### Why not auto-rename the identity

The `users` row is the **global** identity, potentially a member of several orgs (one human, two MATs). Email is the identity's natural key for *human-initiated* login and password reset. An org's SCIM connection is authoritative for *that org's membership*, not for the global mailbox. Auto-rewriting `users.email` from a SCIM push would let one org's IdP silently repoint another org's login. Loud-log surfaces the conflict for a human/operator decision without taking that risk.

## Integrity guarantee

Lookup-first dedup closes the duplicate-on-rename hole for the normal sequential push. To close the **concurrent double-POST** race (two provisions for the same externalId arriving together, both seeing "no membership" → two rows), add a **partial unique index** `(tenant_id, external_id) WHERE external_id IS NOT NULL` on `memberships`, in both `_init_db` and a new Alembic migration (mirrors the foundation's dual-write reality). NULL external_ids (non-SCIM memberships, pre-existing rows) are unconstrained.

The index prevents the duplicate *row*, but the loser's INSERT then raises `psycopg.errors.UniqueViolation`. Left unhandled that surfaces as an HTTP 500 — and IdPs retry-storm on 5xx. So the provisioning kernel **converges** on the collision instead: `_converge_on_external_id` catches the UniqueViolation, re-reads `get_membership_by_external_id`, and returns the winning membership idempotently (SCIM POST is idempotent on externalId). The same recovery covers the backfill-collision case (email resolves to membership B while the externalId already names membership A in-org) — converge on A, loud-log. A non-uniqueness DB error is re-raised, never swallowed. This mirrors the existing Group path's `_raise_if_duplicate` precedent. (Added after adversarial review.)

## Surface

| File | Change |
|------|--------|
| `models.py` | `MembershipRecord.external_id: str \| None = None` |
| `store.py` | `_row_to_membership` reads `external_id`; `create_membership(..., external_id=None)` writes it; new `get_membership_by_external_id(tenant_id, external_id)`; new `update_membership_external_id(membership_id, external_id)`; `_init_db` partial unique index |
| `scim_provisioning.py` | `provision_scim_user(..., external_id=None)` — dedup-by-external_id-first, loud-log on email mismatch, backfill on first sight |
| `scim_routes.py` | `_render_user` echoes `externalId`; `create_user`/`replace_user` pass `external_id=body.get("externalId")` |
| `alembic/versions/0014_*.py` | guarded partial unique index mirror |

`SELECT *` is used at every membership read site, so `_row_to_membership` is the single read chokepoint — no per-query column edits.

## Non-goals

- No auto-rename / merge of global identities (explicitly out, per decision).
- No change to `set_scim_user_active` / `deprovision_scim_user` (they resolve by identity_id from the URL membership, not by externalId).
- No SCIM `/Users?filter=externalId eq` support (Entra filters by `userName`; YAGNI).

## Testing

- Unit (fake store): externalId echoed in render; POST with externalId + new email but matching externalId → same membership, no new identity, WARNING logged; backfill path; externalId absent → unchanged email-keyed behaviour.
- The partial unique index is exercised by the existing PG parity gate (`_init_db` then alembic upgrade head → new head) extended to head 0014.
