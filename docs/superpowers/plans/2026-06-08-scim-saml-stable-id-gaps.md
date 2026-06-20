# SCIM/SAML stable-ID gaps 3 + 2 Implementation Plan

> **For agentic workers:** Execute Hybrid (inline), independent security review at the
> checkpoint. Steps use checkbox (`- [ ]`).

**Goal:** Gap 3 — SAML group-overage fail-safe (loud log). Gap 2 — group→role matches on the
group's `external_id` (GUID) OR `display_name`, with `externalId` captured + echoed via SCIM.

**Spec:** `docs/superpowers/specs/2026-06-08-scim-saml-stable-id-gaps-design.md`

---

## File Structure

- Modify `src/dazzle/http/runtime/auth/saml_provider.py` — `_extract_groups` overage check.
- Modify `src/dazzle/http/runtime/auth/models.py` — `ScimGroupRecord.external_id`.
- Modify `src/dazzle/http/runtime/auth/store.py` — `create_scim_group`/`_row_to_scim_group`
  external_id; new `get_member_group_keys`.
- Modify `src/dazzle/http/runtime/auth/scim_provisioning.py` — `create_group(external_id)`;
  `recompute_membership_roles` uses `get_member_group_keys`.
- Modify `src/dazzle/http/runtime/auth/scim_routes.py` — POST passes `externalId`; `_group_to_scim` echoes it.
- Tests: `test_saml_provider.py`, a provisioning unit test, `test_connections_pg.py`.

---

### Task 1: Gap 3 — SAML overage fail-safe

**Files:** Modify `src/dazzle/http/runtime/auth/saml_provider.py`

- [ ] **Step 1: Failing tests** (append to `tests/unit/test_saml_provider.py`):

```python
def test_extract_groups_warns_on_overage(caplog) -> None:
    p = NativeSAMLProvider()
    conn = _conn()  # default groups_attribute "groups"
    attrs = {"http://schemas.microsoft.com/claims/groups.link": ["https://graph../link"]}
    with caplog.at_level("WARNING"):
        groups = p._extract_groups(conn, attrs)
    assert groups == []  # the real groups were truncated by the IdP
    assert any("overage" in r.getMessage().lower() for r in caplog.records)


def test_extract_groups_no_warning_normal(caplog) -> None:
    p = NativeSAMLProvider()
    with caplog.at_level("WARNING"):
        groups = p._extract_groups(_conn(), {"groups": ["g1", "g2"]})
    assert groups == ["g1", "g2"]
    assert not [r for r in caplog.records if "overage" in r.getMessage().lower()]
```

- [ ] **Step 2: Implement** — in `_extract_groups`, before/after extracting, detect the
overage indicator (any attribute key ending `groups.link`, case-insensitive):

```python
    def _extract_groups(
        self, connection: ConnectionRecord, attributes: dict[str, Any]
    ) -> list[str]:
        if any(str(k).lower().endswith("groups.link") for k in attributes):
            _logger.warning(  # nosemgrep
                "SAML connection %s: group overage — the IdP truncated the groups claim "
                "(>150 groups); this member's group-derived roles may be incomplete. Use "
                "IdP app-role assignment or reduce the group count for this app.",
                connection.id,
            )
        attr = (connection.config or {}).get("groups_attribute") or _DEFAULT_GROUPS_ATTR
        raw = attributes.get(attr) or []
        if isinstance(raw, (list, tuple)):
            return [str(g).strip() for g in raw if g is not None and str(g).strip()]
        return [str(raw).strip()] if str(raw).strip() else []
```

- [ ] **Step 3: Run** `pytest tests/unit/test_saml_provider.py -k extract_groups -q` → PASS.

---

### Task 2: Gap 2 storage — `ScimGroupRecord.external_id` + store

**Files:** Modify `src/dazzle/http/runtime/auth/models.py`, `store.py`

- [ ] **Step 1: Model** — add to `ScimGroupRecord` (after `connection_id`):
```python
    external_id: str | None = None  # the IdP's stable group id (Entra objectId GUID)
```

- [ ] **Step 2: `create_scim_group`** — add `external_id` param + persist:
```python
    def create_scim_group(
        self, connection_id: str, display_name: str, external_id: str | None = None
    ) -> "ScimGroupRecord":  # noqa: F821
        from uuid import uuid4
        from dazzle.http.runtime.auth.models import ScimGroupRecord

        now = datetime.now(UTC).isoformat()
        gid = str(uuid4())
        self._execute(
            "INSERT INTO scim_groups (id, connection_id, display_name, external_id, "
            "created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s)",
            (gid, connection_id, display_name, external_id, now, now),
        )
        return ScimGroupRecord(
            id=gid, connection_id=connection_id, display_name=display_name,
            external_id=external_id, created_at=now, updated_at=now,
        )
```

- [ ] **Step 3: `_row_to_scim_group`** — read it: `external_id=row.get("external_id")`.

- [ ] **Step 4: New `get_member_group_keys`** (next to `get_member_group_names`):
```python
    def get_member_group_keys(self, membership_id: str, connection_id: str) -> list[str]:
        """The role-mapping candidate keys for a member's SCIM groups: each group's
        display_name AND its external_id (GUID) when set. So a group_mapping keyed by EITHER
        (Entra GUID / Google name) matches (#1342 schools gap 2)."""
        rows = self._execute(
            "SELECT g.display_name AS display_name, g.external_id AS external_id "
            "FROM scim_group_members m JOIN scim_groups g ON g.id = m.group_id "
            "WHERE m.membership_id = %s AND g.connection_id = %s",
            (membership_id, connection_id),
        )
        keys: list[str] = []
        for r in rows:
            keys.append(r["display_name"])
            if r.get("external_id"):
                keys.append(r["external_id"])
        return keys
```

- [ ] **Step 5:** `update_scim_group_external_id(group_id, connection_id, external_id)` (for
PUT replace) — a one-line UPDATE, mirroring `rename_scim_group`.

---

### Task 3: Gap 2 wiring — provisioning + routes

**Files:** Modify `scim_provisioning.py`, `scim_routes.py`

- [ ] **Step 1: `create_group`** — thread `external_id`:
```python
def create_group(
    store, connection, display_name, member_ids, *, external_id=None
):
    ...
    group = store.create_scim_group(connection.id, display_name, external_id)
    ...
```

- [ ] **Step 2: `recompute_membership_roles`** — switch to the dual-key keys:
```python
    keys = store.get_member_group_keys(membership_id, connection.id)
    roles = map_groups_to_roles(keys, connection.group_mapping or {})
```
(replaces `names = store.get_member_group_names(...)` — `get_member_group_names` stays for
other callers.)

- [ ] **Step 3: POST `/scim/v2/Groups`** — pass the GUID:
```python
        group = sp.create_group(
            store, conn, body.get("displayName", ""), member_ids,
            external_id=body.get("externalId"),
        )
```

- [ ] **Step 4: `_group_to_scim`** — echo it:
```python
        resource = {... existing ...}
        if getattr(group, "external_id", None):
            resource["externalId"] = group.external_id
        return resource
```

- [ ] **Step 5: PUT replace group** — if the body has `externalId`, call
`update_scim_group_external_id` (alongside the existing rename). Skip if the route's PUT
handler doesn't already load the group; keep minimal.

- [ ] **Step 6: Failing tests** — provisioning unit (`map_groups_to_roles` via GUID key and
name key; unmapped GUID → no role) + a PG test (Task 4).

---

### Task 4: PG integration test

**Files:** Modify `tests/integration/test_connections_pg.py` (or a scim PG test)

- [ ] **Step 1:** Append:
```python
def test_scim_group_external_id_drives_roles(store_url: str) -> None:
    store = _store(store_url)
    # connection with a GUID-keyed group_mapping (mimics Entra: SAML sends GUIDs)
    conn = store.create_connection(
        tenant_id="orgG", type="scim",
        config={}, secrets={}, domains=[],
        group_mapping={"99999999-aaaa": "teacher"},  # the Entra group GUID → role
    )
    # a member to put in the group
    user = store.create_user(email="t@school.test", password="x")
    m = store.create_membership(tenant_id="orgG", identity_id=str(user.id), roles=[])
    # group created via SCIM carrying the Entra GUID as externalId, member added
    g = store.create_scim_group(conn.id, "Year 7 Teachers", "99999999-aaaa")
    store.add_group_member(g.id, m.id)

    from dazzle.http.runtime.auth.scim_provisioning import recompute_membership_roles
    recompute_membership_roles(store, conn, m.id)
    assert "teacher" in store.get_membership(m.id).roles  # matched by GUID, not display_name

    # keys include both name + GUID; the SCIM group round-trips external_id
    keys = store.get_member_group_keys(m.id, conn.id)
    assert "99999999-aaaa" in keys and "Year 7 Teachers" in keys
    assert store.get_scim_group(g.id, conn.id).external_id == "99999999-aaaa"
```
(Confirm `create_connection` accepts `group_mapping=` + `create_membership` signature against
the store; adapt to the real signatures if they differ.)

- [ ] **Step 2: Run** `DATABASE_URL=…/dazzle_dev pytest tests/integration/test_connections_pg.py -k "external_id or group_external" -q` → PASS. Run the broader scim/auth PG slice for no regression.

---

### Checkpoint — independent security review

- [ ] Dispatch `feature-dev:code-reviewer` on the diff. Focus: (1) still default-deny — a
captured GUID grants a role ONLY if explicitly in `group_mapping`; (2) the org-containment
chokepoint in `recompute_membership_roles` is untouched (dual-key changes *which keys grant*,
not *which memberships recompute*); (3) the overage log can't be turned into a DoS/log-spam
vector (one WARNING per assertion, fine); (4) no SCIM externalId injection issue (it's an
opaque string used only as a map key + echoed). Fix any CRITICAL.

---

### Task 5: Ship

- [ ] CHANGELOG `### Added`: Gap 3 overage fail-safe + Gap 2 group→role by stable ID
(`externalId` captured/echoed; `group_mapping` matches GUID or name; one mapping now works for
SAML + SCIM). `### Agent Guidance`: group_mapping keys may be IdP group GUIDs (Entra) or names
(Google) — both match.
- [ ] `/bump patch`; gates (`ruff`, `mypy src/dazzle`, drift/policy, `pytest -m "not e2e"`,
postgres slice); commit (verify `COMMIT_EXIT=0`), tag, push, watch CI (incl. PostgreSQL +
integration) + release.
- [ ] Update memory — gaps 3+2 shipped; Gap 1 (user externalId, dedup+loud-log) is the last.

## Self-review

- **Spec coverage:** overage log (T1), external_id storage+model (T2), dual-key match +
  capture/echo (T3), PG proof (T4), review (checkpoint). ✓
- **Type consistency:** `create_scim_group(..., external_id=None)`; `get_member_group_keys ->
  list[str]`; `create_group(..., *, external_id=None)`; `map_groups_to_roles` UNCHANGED. ✓
- **Backward-compat:** name-keyed `group_mapping` still matches (display_name is always a key);
  `map_groups_to_roles` + the SAML caller untouched. ✓
- **No placeholders:** the only "confirm signature" notes (T4 create_connection/membership) are
  test-fixture adaptations, not shipped code.
