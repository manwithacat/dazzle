# SCIM /Groups — design

**Date:** 2026-06-06
**Issue:** #1342 (Phase 3 — SCIM completeness)
**Status:** Approved design, ready for implementation planning
**Capability gate:** `auth.enterprise.scim` (routes mount only when active)

## Problem

Dazzle's SCIM 2.0 server exposes `/scim/v2/Users` but not `/scim/v2/Groups`. Today
group→role assignment comes from the **best-effort `User.groups` attribute** on a
User POST/PUT (`provision_scim_user(..., groups=…)` → `map_groups_to_roles` →
`update_membership_roles`). The proper SCIM mechanism — an IdP managing **Group
resources** and their **members** via the Groups endpoint — is missing, so
Okta/Entra "push groups" configurations can't drive Dazzle roles.

A SCIM "User" in Dazzle is a **Membership** (the fenced Identity↔Org join); a
membership's `roles` are its per-org personas. `map_groups_to_roles(groups,
connection.group_mapping)` is default-deny (unmapped groups grant nothing).

## Decisions (from brainstorming)

1. **Faithful multi-group correctness.** A user may belong to several IdP groups
   mapping to different roles; removing them from one group must NOT drop a role
   still granted by another. This is a security-relevant invariant (no stale /
   over-broad roles), and it requires **persisting group membership** — role
   recompute can't be done correctly from role-holders alone.
2. **`/Groups` authoritative; `User.groups` informational (RFC-correct).** RFC 7643
   treats `User.groups` as server-managed/read-only; clients manage membership via
   the Groups resource. So persisted group membership is the **sole** source of
   group-derived roles. The `groups` array on a User write is ignored (logged).
   Clean-break (documented): connections relying on the `User.groups` write path
   switch to `/Groups`.

## Data model

Two new auth-store tables, created in `AuthStore._init_db` (the established
raw-SQL pattern used for `connections`/`memberships`), both connection-scoped:

```sql
CREATE TABLE IF NOT EXISTS scim_groups (
    id            TEXT PRIMARY KEY,              -- server-assigned uuid; the IdP stores this
    connection_id TEXT NOT NULL REFERENCES connections(id),
    display_name  TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE (connection_id, display_name)         -- one group per name per connection
);
CREATE TABLE IF NOT EXISTS scim_group_members (
    group_id      TEXT NOT NULL REFERENCES scim_groups(id) ON DELETE CASCADE,
    membership_id TEXT NOT NULL REFERENCES memberships(id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, membership_id)
);
```

A member references a membership by id (SCIM User id = membership id). A member
must be a membership **in the connection's org** (`_membership_in_org`).

### Role recompute primitive

The single source of truth for group-derived roles:

```
recompute_membership_roles(store, connection, membership_id):
    names = [g.display_name for g in groups membership_id belongs to (this connection)]
    roles = map_groups_to_roles(names, connection.group_mapping or {})   # default-deny
    if set(roles) != set(membership.roles or []):
        store.update_membership_roles(membership_id, roles, reason="SCIM group sync")
```

Called after **every** membership-set change: member add/remove/replace
(PATCH/PUT), group DELETE (each former member), and group `displayName` change
(re-maps the role for all its members). A group whose `display_name` isn't in
`group_mapping` still exists and tracks members — it contributes no role
(default-deny).

## REST surface

Split mirrors Users: **routes** (`scim_routes.py`) parse REST/JSON; **provisioning**
(`scim_provisioning.py`) does state changes + recompute. All bearer-authed +
org-scoped via `_require_scim_connection`.

| Method | Path | Behaviour |
|---|---|---|
| `POST` | `/scim/v2/Groups` | create (`displayName`, optional `members`) → 201 + Group JSON |
| `GET` | `/scim/v2/Groups/{id}` | read one (with members) |
| `GET` | `/scim/v2/Groups?filter=displayName eq "X"` | ListResponse (also bare list) |
| `PUT` | `/scim/v2/Groups/{id}` | replace `displayName` + full member set |
| `PATCH` | `/scim/v2/Groups/{id}` | RFC 7644 ops (below) |
| `DELETE` | `/scim/v2/Groups/{id}` | delete + cascade members + recompute |

**Group JSON:**
```json
{"schemas":["urn:ietf:params:scim:schemas:core:2.0:Group"],
 "id":"<uuid>","displayName":"Engineering",
 "members":[{"value":"<membership_id>","$ref":"<base>/scim/v2/Users/<membership_id>"}],
 "meta":{"resourceType":"Group","location":"<base>/scim/v2/Groups/<id>"}}
```

**PATCH ops** — a small focused parser for the concrete forms Okta/Entra send (NOT
a general SCIM path-filter engine):
- `add` · `path:"members"` · `value:[{value:<id>},…]` → add members
- `remove` · `path:'members[value eq "<id>"]'` → remove one member (Okta's form)
- `remove` · `path:"members"` → remove all members
- `replace` · `path:"members"` · `value:[…]` → replace member set
- `replace` · `path:"displayName"` (or value `{displayName:…}`) → rename
- unknown op/path → return the resource unchanged (SCIM-lenient); never 500

Each member `value` is validated `_membership_in_org`; the op then triggers the
recompute for the affected memberships.

## Role authority change

- `provision_scim_user(...)` no longer maps the `groups` attribute to roles. The
  arg stays in the signature (callers unchanged) but is logged as informational,
  not passed to `map_groups_to_roles`. A User POST creates a membership with
  whatever roles its persisted group memberships already grant (often none until
  `/Groups` adds it).
- `GET /Users/{id}` echoes a **read-only** `groups` array reflecting actual
  persisted group memberships (so an IdP reconciling sees the truth).
- **Clean-break:** documented in CHANGELOG `### Changed` + the `enterprise-sso.md`
  SCIM section. This is the only behavioral break; all else is additive.

## Security & errors

- **Org containment:** every member `value` validated `_membership_in_org(store,
  id, conn.tenant_id)` before linking — a SCIM integration can never pull another
  org's membership into its group. Groups are `connection_id`-scoped; all CRUD
  filters by the bearer's connection.
- **Discovery:** `ServiceProviderConfig` already advertises `patch`+`filter`
  (resource-agnostic) — no change. `/Schemas`+`/ResourceTypes` is a separate
  backlog item, out of scope here.
- **Errors:** invalid member ref → `400` SCIM error; unknown group id → `404`;
  duplicate `displayName` within a connection → `409`; broad-catch → SCIM error
  JSON, never a 500 leak (mirrors the Users handlers).

## Files

- `src/dazzle/back/runtime/auth/store.py` — `_init_db` tables + store methods:
  `create_scim_group`, `get_scim_group`, `list_scim_groups`(+filter),
  `rename_scim_group`, `delete_scim_group`, `add_group_member`,
  `remove_group_member`, `replace_group_members`, `get_member_group_names`.
- `src/dazzle/back/runtime/auth/scim_provisioning.py` — group CRUD domain logic +
  `recompute_membership_roles`; drop the role-mapping in `provision_scim_user`.
- `src/dazzle/back/runtime/auth/scim_routes.py` — the Groups REST endpoints + the
  PATCH parser + Group JSON serialisation.
- `src/dazzle/back/tests/test_auth.py` / `tests/integration/test_scim_routes.py`
  (or a new `test_scim_groups.py`) — tests.

## Testing

- **Headline:** multi-group de-escalation — user in 2 groups → 2 roles; remove
  from one via PATCH; the other's role persists.
- PATCH add / remove-by-`value eq` filter / remove-all / replace; PUT replace.
- Rename re-maps role for all members; DELETE recomputes (members lose the role).
- Cross-org member ref rejected (`_membership_in_org`).
- `User.groups` attribute no longer drives roles (the clean-break, asserted).
- Group whose `displayName` isn't in `group_mapping` → exists, tracks members,
  grants no role.
- Real-PG store-method tests (the tables) + fake-store route tests (the REST/PATCH
  layer), matching the existing SCIM test split. Postgres-marked where they hit PG.

## Non-goals / deferred

- `/Schemas` + `/ResourceTypes` discovery endpoints (separate #1342 item).
- Nested groups (members that are groups) — SCIM allows it; not supported (flat
  membership only). Reject/ignore group-typed members.
- A general SCIM PATCH path-filter engine — only the concrete Okta/Entra forms.
- Honoring `User.groups` writes for roles — deliberately removed (see Decisions).
