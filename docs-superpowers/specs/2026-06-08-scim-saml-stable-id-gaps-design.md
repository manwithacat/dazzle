# SCIM/SAML stable-ID gaps 3 + 2 — Design

**Context:** Second slice of the schools SCIM/SAML streamlining work (#1342), on the
foundation (`external_id` columns + alembic parity, v0.81.98). Closes Gap 3 (SAML group
overage) and Gap 2 (group→role by stable ID). Source analysis:
`dev_docs/2026-06-08-schools-scim-saml-engagement-analysis.md`. Gap 1 (user `externalId`) is a
separate later slice (dedup + loud-log).

## Gap 3 — SAML group overage fail-safe (no schema)

**Problem:** Entra caps the SAML groups claim at 150 (JWT 200). Over the cap it OMITS the
groups claim and instead emits an overage indicator —
`http://schemas.microsoft.com/claims/groups.link` — pointing at Microsoft Graph. A MAT
teacher in many groups (dynamic groups, School Data Sync) silently arrives with **no groups
→ no roles**, default-denied, with no signal.

**Fix:** `NativeSAMLProvider._extract_groups` detects the overage claim in the assertion
attributes (any attribute key ending in `groups.link`, case-insensitive) and logs a loud
`WARNING` naming the connection — "group overage: the IdP truncated the groups claim; this
member's group-derived roles may be incomplete; use app-role assignment or reduce group
count". It still returns whatever groups ARE present (degraded, never silently under-granting
without a signal). No Graph callback (out of scope — needs Graph creds + a request-time
fetch). Pure-ish + unit-testable on `attributes`.

## Gap 2 — group→role by stable ID (uses `scim_groups.external_id`)

**Problem:** `map_groups_to_roles(groups, group_mapping)` is shared by BOTH paths:
- SAML/OIDC login (`provision_enterprise_login`) passes `asserted.groups` — the raw claim
  values (Entra = group object-ID **GUIDs**, Google = names).
- SCIM `/Groups` (`recompute_membership_roles`) passes group **display_names** only — the
  captured `externalId` (GUID) is dropped.

So an operator must key `group_mapping` by GUID for SAML, but the SAME groups arriving via
SCIM match only by display_name → the two paths disagree, and an Entra rename breaks the SCIM
mapping. The fix makes SCIM *also* offer the group's `external_id` as a match key, so **one
GUID-keyed `group_mapping` works for both SAML and SCIM**, with `display_name` still accepted
(backward-compatible; Google-name configs keep working).

**Changes (capture + match):**
- `ScimGroupRecord` gains `external_id: str | None = None`.
- `AuthStore.create_scim_group(connection_id, display_name, external_id=None)` stores it;
  `_row_to_scim_group` reads it.
- `scim_provisioning.create_group(..., external_id=None)` threads it; the `POST /Groups`
  route passes `external_id=body.get("externalId")` (the Entra group objectId GUID).
- `_group_to_scim` echoes `"externalId"` when present (Entra reconciles on it).
- New `AuthStore.get_member_group_keys(membership_id, connection_id) -> list[str]` — the
  union of each of the member's groups' `display_name` + (non-null) `external_id` (one JOIN,
  selecting both columns). `recompute_membership_roles` uses it instead of
  `get_member_group_names`, so `map_groups_to_roles` grants a role when *either* key is in
  `group_mapping`. `map_groups_to_roles` itself is UNCHANGED (still
  `group_mapping.get(key)`) — it just receives both candidate keys per group; the SAML caller
  is unaffected.
- `get_member_group_names` is kept (other callers / the SCIM User `groups` echo) but
  `recompute_membership_roles` switches to `get_member_group_keys`.

**PUT replace** (`replace_user`/group PUT): if the body carries `externalId`, update it
(cheap; keeps the stored GUID fresh). The org-containment chokepoint in
`recompute_membership_roles` is untouched — the dual-key change doesn't widen what gets
recomputed, only which keys grant roles.

## Security / correctness lens

- **No new authz surface:** still default-deny; a group grants a role only if its name OR its
  GUID is explicitly in `group_mapping`. A captured GUID an operator never mapped grants
  nothing.
- **The org-containment chokepoint** (`recompute_membership_roles` refuses memberships outside
  `connection.tenant_id`) is unchanged — the cross-org-role-zeroing defense holds.
- **Collision:** a `display_name` equal to a *different* group's GUID is astronomically
  unlikely (GUIDs vs human names) and would, at worst, grant a mapped role — acceptable and
  no worse than today's name-only matching.
- **Overage fail-safe** turns a silent under-grant into a loud log — strictly safer.

## Testing

- `tests/unit/test_saml_provider.py`: `_extract_groups` logs a WARNING + returns present
  groups when an overage `*groups.link` attribute is present; no warning on the normal path.
- `tests/unit/test_scim_*` / provisioning unit tests: `map_groups_to_roles` grants via a
  GUID-keyed mapping AND a name-keyed mapping (both keys offered); an unmapped GUID grants
  nothing.
- `tests/integration/test_connections_pg.py` (or a scim PG test): `create_scim_group` round-
  trips `external_id`; `get_member_group_keys` returns name + GUID; `recompute_membership_roles`
  assigns the role from a GUID-keyed `group_mapping`; the SCIM Group resource echoes
  `externalId`.

## Out of scope

- Gap 1 (user `externalId` echo + dedup) — next slice.
- Graph callback for overage resolution.
- Migrating existing display-name-keyed `group_mapping` configs (they keep working).
