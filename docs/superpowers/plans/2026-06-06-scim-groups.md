# SCIM /Groups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persisted SCIM 2.0 `/Groups` resource so an IdP (Okta/Entra) drives Dazzle roles by managing group membership, with faithful multi-group de-escalation.

**Architecture:** Two connection-scoped auth-store tables (`scim_groups`, `scim_group_members`) created in `AuthStore._init_db`. A membership's group-derived roles are recomputed as `map_groups_to_roles(union of its groups' display_names, connection.group_mapping)` after every change. `/Groups` becomes authoritative for group→role; the `User.groups` attribute write-path is dropped to informational. Routes parse REST/JSON + RFC-7644 PATCH; the provisioning layer does state changes + recompute (mirrors the Users split).

**Tech Stack:** Python 3.12, psycopg3 (raw SQL, `%s` params, dict rows), FastAPI, pytest. No new deps.

**Spec:** `docs/superpowers/specs/2026-06-06-scim-groups-design.md`. Capability gate: `auth.enterprise.scim` (routes already mount only when active).

---

## File Structure

- **Modify** `src/dazzle/back/runtime/auth/models.py` — add `ScimGroupRecord`.
- **Modify** `src/dazzle/back/runtime/auth/store.py` — `_init_db` tables (after `CONNECTIONS_DDL`, line ~1696) + group/member store methods.
- **Modify** `src/dazzle/back/runtime/auth/scim_provisioning.py` — `recompute_membership_roles`, `SCIMGroupError`, group domain functions; drop role-mapping in `provision_scim_user`.
- **Modify** `src/dazzle/back/runtime/auth/scim_routes.py` — Groups REST endpoints, Group JSON, PATCH parser; `GET /Users/{id}` read-only `groups` echo.
- **Modify** `docs/reference/enterprise-sso.md` + `CHANGELOG.md`.
- **Tests:** `src/dazzle/back/tests/test_auth.py` (real-PG store methods), `tests/integration/test_scim_routes.py` (fake-store route + PATCH).

**FK note (convention + ordering):** the store scopes by `connection_id`/`tenant_id` in code rather than hard-FKing to `connections` (e.g. `memberships` has no connections FK). Follow that: `scim_groups.connection_id` is a plain `TEXT` column (code-scoped); keep FK + `ON DELETE CASCADE` only within the SCIM tables and to `memberships` (created at line 1625, before the SCIM tables).

---

## Task 1: `ScimGroupRecord` model

**Files:**
- Modify: `src/dazzle/back/runtime/auth/models.py`
- Test: `src/dazzle/back/tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# in src/dazzle/back/tests/test_auth.py (top-level, near other model tests)
def test_scim_group_record_fields() -> None:
    from dazzle.back.runtime.auth.models import ScimGroupRecord

    g = ScimGroupRecord(
        id="g1", connection_id="c1", display_name="Engineering",
        created_at="2026-06-06T00:00:00", updated_at="2026-06-06T00:00:00",
    )
    assert g.id == "g1"
    assert g.connection_id == "c1"
    assert g.display_name == "Engineering"
```

- [ ] **Step 2: Run → fail** — `pytest "src/dazzle/back/tests/test_auth.py::test_scim_group_record_fields" -q` → ImportError.

- [ ] **Step 3: Implement** — add to `models.py` (it already hosts `MembershipRecord`; use the same Pydantic `BaseModel` style):

```python
class ScimGroupRecord(BaseModel):
    """A SCIM 2.0 Group, connection-scoped (#1342). Members are tracked
    separately in scim_group_members and fetched on demand."""

    id: str
    connection_id: str
    display_name: str
    created_at: str
    updated_at: str
```

(If `models.py` uses frozen `model_config`, match it; check an adjacent record.)

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit** — `feat(scim): ScimGroupRecord model (#1342)`

---

## Task 2: Store schema + group/member methods

**Files:**
- Modify: `src/dazzle/back/runtime/auth/store.py`
- Test: `src/dazzle/back/tests/test_auth.py`

- [ ] **Step 1: Write the failing tests** (real-PG; new class, postgres-marked like `TestAuthStore`)

```python
@pytest.mark.postgres
@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
class TestScimGroupStore:
    @pytest.fixture
    def store(self) -> Any:
        return AuthStore(os.environ["DATABASE_URL"])

    @pytest.fixture
    def membership(self, store: Any) -> Any:
        # A real membership to reference as a group member.
        from uuid import uuid4
        user = store.create_user(email=f"m-{uuid4().hex[:8]}@x.test", password="p")
        return store.create_membership(tenant_id="org-1", identity_id=str(user.id), roles=[])

    def test_create_get_list_rename_delete_group(self, store: Any) -> None:
        g = store.create_scim_group("conn-1", "Engineering")
        assert g.id and g.display_name == "Engineering"
        assert store.get_scim_group(g.id, "conn-1").display_name == "Engineering"
        assert store.get_scim_group(g.id, "other-conn") is None  # connection-scoped
        assert [x.display_name for x in store.list_scim_groups("conn-1")] == ["Engineering"]
        assert [x.id for x in store.list_scim_groups("conn-1", display_name="Engineering")] == [g.id]
        store.rename_scim_group(g.id, "conn-1", "Eng")
        assert store.get_scim_group(g.id, "conn-1").display_name == "Eng"
        assert store.delete_scim_group(g.id, "conn-1") is True
        assert store.get_scim_group(g.id, "conn-1") is None

    def test_member_add_remove_replace_and_lookup(self, store: Any, membership: Any) -> None:
        g = store.create_scim_group("conn-1", "Eng")
        store.add_group_member(g.id, membership.id)
        store.add_group_member(g.id, membership.id)  # idempotent
        assert store.get_group_member_ids(g.id) == [membership.id]
        assert g.display_name in store.get_member_group_names(membership.id, "conn-1")
        store.remove_group_member(g.id, membership.id)
        assert store.get_group_member_ids(g.id) == []
        store.replace_group_members(g.id, [membership.id])
        assert store.get_group_member_ids(g.id) == [membership.id]
```

(If `create_membership` has a different signature, adapt the fixture — grep `def create_membership`.)

- [ ] **Step 2: Run → fail** — methods/tables missing.

- [ ] **Step 3a: Add the tables in `_init_db`** — immediately after `cursor.execute(CONNECTIONS_DDL)` (line ~1696):

```python
            # SCIM Groups (#1342). connection_id is code-scoped (no hard FK to
            # connections — matches the memberships convention). Members cascade
            # from the group and from the referenced membership.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scim_groups (
                    id            TEXT PRIMARY KEY,
                    connection_id TEXT NOT NULL,
                    display_name  TEXT NOT NULL,
                    created_at    TEXT NOT NULL,
                    updated_at    TEXT NOT NULL,
                    UNIQUE (connection_id, display_name)
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS ix_scim_groups_conn ON scim_groups(connection_id)"
            )
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scim_group_members (
                    group_id      TEXT NOT NULL REFERENCES scim_groups(id) ON DELETE CASCADE,
                    membership_id TEXT NOT NULL REFERENCES memberships(id) ON DELETE CASCADE,
                    PRIMARY KEY (group_id, membership_id)
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS ix_scim_group_members_member "
                "ON scim_group_members(membership_id)"
            )
```

- [ ] **Step 3b: Add the store methods** (near the connection methods, ~line 1250). Use `_execute`/`_execute_one`/`_execute_modify` (psycopg3, `%s`, dict rows). Timestamps as ISO strings (match the store's `datetime.now(UTC).isoformat()` usage):

```python
    def create_scim_group(self, connection_id: str, display_name: str) -> "ScimGroupRecord":
        from uuid import uuid4

        from dazzle.back.runtime.auth.models import ScimGroupRecord

        now = datetime.now(UTC).isoformat()
        gid = str(uuid4())
        self._execute(
            "INSERT INTO scim_groups (id, connection_id, display_name, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (gid, connection_id, display_name, now, now),
        )
        return ScimGroupRecord(
            id=gid, connection_id=connection_id, display_name=display_name,
            created_at=now, updated_at=now,
        )

    def _row_to_scim_group(self, row: dict[str, Any]) -> "ScimGroupRecord":
        from dazzle.back.runtime.auth.models import ScimGroupRecord

        return ScimGroupRecord(
            id=row["id"], connection_id=row["connection_id"],
            display_name=row["display_name"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def get_scim_group(self, group_id: str, connection_id: str) -> "ScimGroupRecord | None":
        row = self._execute_one(
            "SELECT * FROM scim_groups WHERE id = %s AND connection_id = %s",
            (group_id, connection_id),
        )
        return self._row_to_scim_group(row) if row else None

    def list_scim_groups(
        self, connection_id: str, display_name: str | None = None
    ) -> list["ScimGroupRecord"]:
        if display_name is not None:
            rows = self._execute(
                "SELECT * FROM scim_groups WHERE connection_id = %s AND display_name = %s "
                "ORDER BY created_at",
                (connection_id, display_name),
            )
        else:
            rows = self._execute(
                "SELECT * FROM scim_groups WHERE connection_id = %s ORDER BY created_at",
                (connection_id,),
            )
        return [self._row_to_scim_group(r) for r in rows]

    def rename_scim_group(self, group_id: str, connection_id: str, display_name: str) -> None:
        self._execute_modify(
            "UPDATE scim_groups SET display_name = %s, updated_at = %s "
            "WHERE id = %s AND connection_id = %s",
            (display_name, datetime.now(UTC).isoformat(), group_id, connection_id),
        )

    def delete_scim_group(self, group_id: str, connection_id: str) -> bool:
        n = self._execute_modify(
            "DELETE FROM scim_groups WHERE id = %s AND connection_id = %s",
            (group_id, connection_id),
        )
        return n > 0

    def get_group_member_ids(self, group_id: str) -> list[str]:
        rows = self._execute(
            "SELECT membership_id FROM scim_group_members WHERE group_id = %s "
            "ORDER BY membership_id",
            (group_id,),
        )
        return [r["membership_id"] for r in rows]

    def add_group_member(self, group_id: str, membership_id: str) -> None:
        self._execute_modify(
            "INSERT INTO scim_group_members (group_id, membership_id) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            (group_id, membership_id),
        )

    def remove_group_member(self, group_id: str, membership_id: str) -> None:
        self._execute_modify(
            "DELETE FROM scim_group_members WHERE group_id = %s AND membership_id = %s",
            (group_id, membership_id),
        )

    def replace_group_members(self, group_id: str, membership_ids: list[str]) -> None:
        self._execute_modify("DELETE FROM scim_group_members WHERE group_id = %s", (group_id,))
        for mid in membership_ids:
            self.add_group_member(group_id, mid)

    def get_member_group_names(self, membership_id: str, connection_id: str) -> list[str]:
        rows = self._execute(
            "SELECT g.display_name AS display_name FROM scim_group_members m "
            "JOIN scim_groups g ON g.id = m.group_id "
            "WHERE m.membership_id = %s AND g.connection_id = %s",
            (membership_id, connection_id),
        )
        return [r["display_name"] for r in rows]
```

- [ ] **Step 4: Run → pass** — `DATABASE_URL=… pytest "src/dazzle/back/tests/test_auth.py::TestScimGroupStore" -q`.

- [ ] **Step 5: Commit** — `feat(scim): scim_groups + scim_group_members tables + store methods (#1342)`

---

## Task 3: `recompute_membership_roles`

**Files:**
- Modify: `src/dazzle/back/runtime/auth/scim_provisioning.py`
- Test: `src/dazzle/back/tests/test_auth.py`

- [ ] **Step 1: Write the failing test** (real-PG; uses the Task-2 store)

```python
    def test_recompute_unions_roles_across_groups(self, store: Any, membership: Any) -> None:
        from types import SimpleNamespace

        from dazzle.back.runtime.auth.scim_provisioning import recompute_membership_roles

        conn = SimpleNamespace(
            id="conn-1", tenant_id="org-1",
            group_mapping={"Eng": "engineer", "Ops": "operator"},
        )
        eng = store.create_scim_group("conn-1", "Eng")
        ops = store.create_scim_group("conn-1", "Ops")
        store.add_group_member(eng.id, membership.id)
        store.add_group_member(ops.id, membership.id)
        recompute_membership_roles(store, conn, membership.id)
        assert set(store.get_membership(membership.id).roles) == {"engineer", "operator"}

        # Remove from one group: the other group's role MUST persist (de-escalation).
        store.remove_group_member(eng.id, membership.id)
        recompute_membership_roles(store, conn, membership.id)
        assert set(store.get_membership(membership.id).roles) == {"operator"}
```

(Put this method in `TestScimGroupStore`.)

- [ ] **Step 2: Run → fail** — `recompute_membership_roles` missing.

- [ ] **Step 3: Implement** in `scim_provisioning.py`:

```python
def recompute_membership_roles(store: Any, connection: Any, membership_id: str) -> None:
    """Set a membership's roles to map_groups_to_roles(all its groups) — the single
    source of truth for group-derived roles (#1342). Idempotent."""
    names = store.get_member_group_names(membership_id, connection.id)
    roles = map_groups_to_roles(names, connection.group_mapping or {})
    membership = store.get_membership(membership_id)
    if membership is None:
        return
    if set(roles) != set(membership.roles or []):
        store.update_membership_roles(membership_id, roles, reason="SCIM group sync")
```

(`map_groups_to_roles` is already imported in `scim_provisioning.py`.)

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit** — `feat(scim): recompute_membership_roles (union over a member's groups) (#1342)`

---

## Task 4: Group domain functions (CRUD + member ops, with recompute)

**Files:**
- Modify: `src/dazzle/back/runtime/auth/scim_provisioning.py`
- Test: `src/dazzle/back/tests/test_auth.py`

- [ ] **Step 1: Write the failing tests** (real-PG)

```python
    def test_group_domain_ops_recompute(self, store: Any, membership: Any) -> None:
        from types import SimpleNamespace

        from dazzle.back.runtime.auth import scim_provisioning as sp

        conn = SimpleNamespace(id="conn-1", tenant_id="org-1", group_mapping={"Eng": "engineer"})
        g = sp.create_group(store, conn, "Eng", member_ids=[membership.id])
        assert set(store.get_membership(membership.id).roles) == {"engineer"}

        sp.remove_group_member(store, conn, g.id, membership.id)
        assert store.get_membership(membership.id).roles == []

        sp.add_group_members(store, conn, g.id, [membership.id])
        assert set(store.get_membership(membership.id).roles) == {"engineer"}

        sp.rename_group(store, conn, g.id, "Engineering")  # not in mapping → role drops
        assert store.get_membership(membership.id).roles == []

        sp.delete_group(store, conn, g.id)
        assert store.get_scim_group(g.id, "conn-1") is None

    def test_cross_org_member_rejected(self, store: Any) -> None:
        from types import SimpleNamespace
        from uuid import uuid4

        from dazzle.back.runtime.auth import scim_provisioning as sp

        conn = SimpleNamespace(id="conn-1", tenant_id="org-1", group_mapping={})
        other = store.create_user(email=f"o-{uuid4().hex[:8]}@x.test", password="p")
        other_m = store.create_membership(tenant_id="org-2", identity_id=str(other.id), roles=[])
        with pytest.raises(sp.SCIMGroupError):
            sp.create_group(store, conn, "Eng", member_ids=[other_m.id])
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement** in `scim_provisioning.py`:

```python
class SCIMGroupError(Exception):
    """A SCIM Group operation error → mapped to a SCIM HTTP status by the route."""

    def __init__(self, reason: str, message: str = "", status: int = 400) -> None:
        self.reason = reason
        self.status = status
        super().__init__(message or reason)


def _require_member_in_org(store: Any, connection: Any, membership_id: str) -> Any:
    m = store.get_membership(membership_id)
    if m is None or m.tenant_id != connection.tenant_id:
        raise SCIMGroupError("invalid_member", f"member {membership_id!r} not in this org", 400)
    return m


def create_group(store: Any, connection: Any, display_name: str, member_ids: list[str]) -> Any:
    if not display_name:
        raise SCIMGroupError("invalid_value", "displayName is required", 400)
    for mid in member_ids:
        _require_member_in_org(store, connection, mid)
    # Duplicate displayName within the connection → 409.
    if store.list_scim_groups(connection.id, display_name=display_name):
        raise SCIMGroupError("uniqueness", f"group {display_name!r} already exists", 409)
    group = store.create_scim_group(connection.id, display_name)
    for mid in member_ids:
        store.add_group_member(group.id, mid)
        recompute_membership_roles(store, connection, mid)
    return group


def get_group(store: Any, connection: Any, group_id: str) -> Any:
    group = store.get_scim_group(group_id, connection.id)
    if group is None:
        raise SCIMGroupError("not_found", f"no group {group_id!r}", 404)
    return group


def list_groups(store: Any, connection: Any, display_name: str | None = None) -> list[Any]:
    return store.list_scim_groups(connection.id, display_name=display_name)


def rename_group(store: Any, connection: Any, group_id: str, display_name: str) -> Any:
    group = get_group(store, connection, group_id)
    if display_name and display_name != group.display_name:
        clash = store.list_scim_groups(connection.id, display_name=display_name)
        if clash:
            raise SCIMGroupError("uniqueness", f"group {display_name!r} already exists", 409)
        store.rename_scim_group(group_id, connection.id, display_name)
        for mid in store.get_group_member_ids(group_id):
            recompute_membership_roles(store, connection, mid)
    return store.get_scim_group(group_id, connection.id)


def delete_group(store: Any, connection: Any, group_id: str) -> None:
    get_group(store, connection, group_id)  # 404 if absent / wrong org
    member_ids = store.get_group_member_ids(group_id)
    store.delete_scim_group(group_id, connection.id)  # cascades scim_group_members
    for mid in member_ids:
        recompute_membership_roles(store, connection, mid)


def set_group_members(store: Any, connection: Any, group_id: str, member_ids: list[str]) -> None:
    get_group(store, connection, group_id)
    for mid in member_ids:
        _require_member_in_org(store, connection, mid)
    affected = set(store.get_group_member_ids(group_id)) | set(member_ids)
    store.replace_group_members(group_id, member_ids)
    for mid in affected:
        recompute_membership_roles(store, connection, mid)


def add_group_members(store: Any, connection: Any, group_id: str, member_ids: list[str]) -> None:
    get_group(store, connection, group_id)
    for mid in member_ids:
        _require_member_in_org(store, connection, mid)
        store.add_group_member(group_id, mid)
        recompute_membership_roles(store, connection, mid)


def remove_group_member(store: Any, connection: Any, group_id: str, member_id: str) -> None:
    get_group(store, connection, group_id)
    store.remove_group_member(group_id, member_id)
    recompute_membership_roles(store, connection, member_id)
```

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit** — `feat(scim): group CRUD + member domain ops with role recompute (#1342)`

---

## Task 5: Drop role-mapping from `provision_scim_user` (clean-break)

**Files:**
- Modify: `src/dazzle/back/runtime/auth/scim_provisioning.py` (`provision_scim_user`, ~line 67-113)
- Test: `src/dazzle/back/tests/test_auth.py`

- [ ] **Step 1: Write the failing test** (real-PG)

```python
    def test_user_groups_attribute_no_longer_drives_roles(self, store: Any) -> None:
        from types import SimpleNamespace

        from dazzle.back.runtime.auth.scim_provisioning import provision_scim_user

        conn = SimpleNamespace(id="conn-1", tenant_id="org-1", group_mapping={"Eng": "engineer"})
        result = provision_scim_user(
            store, conn, email="ann@x.test", active=True, groups=["Eng"],
        )
        membership = store.get_membership(result.membership_id)
        assert membership.roles == []  # groups attribute is informational now; /Groups owns roles
```

(Adapt to the actual `provision_scim_user` return shape — grep its return; it returns a result carrying the membership id.)

- [ ] **Step 2: Run → fail** (current code maps groups→roles, so roles == ["engineer"]).

- [ ] **Step 3: Implement** — in `provision_scim_user`, replace the `roles = map_groups_to_roles(groups or [], ...)` line and its uses so the membership is created/synced with roles owned by `/Groups`, not the `groups` arg:

```python
    # #1342: group→role is owned by the /Groups endpoint (RFC: User.groups is
    # server-managed). The `groups` arg is accepted for compatibility but no longer
    # drives roles — log it and leave roles to the persisted group memberships.
    if groups:
        _logger.debug("SCIM User groups attribute ignored for roles (use /Groups): %s", groups)
    roles: list[str] = []
```

Then, for the **existing-membership** branch, do NOT overwrite roles from the (now-empty) `groups`-derived list — leave the membership's current (group-managed) roles intact. Concretely: remove the `update_membership_roles` call that synced from the groups attribute (the block around the old `if set(roles) != set(membership.roles ...)`), so a User re-push no longer clobbers group-managed roles. New memberships are created with `roles=[]`; `/Groups` assigns them.

(Read the current function carefully and ensure the create-path passes `roles=[]` and the update-path leaves roles untouched.)

- [ ] **Step 4: Run → pass**, and update any existing test that asserted `provision_scim_user` roles-from-groups (grep `provision_scim_user` in tests) to the new behaviour.

- [ ] **Step 5: Commit** — `feat(scim)!: User.groups attribute no longer drives roles — /Groups authoritative (#1342)`

---

## Task 6: PATCH op parser

**Files:**
- Modify: `src/dazzle/back/runtime/auth/scim_provisioning.py` (a pure parser) or a small helper module
- Test: `src/dazzle/back/tests/test_auth.py` (pure, no DB)

- [ ] **Step 1: Write the failing tests** (pure function — runs without DATABASE_URL; put in a plain top-level test)

```python
def test_parse_group_patch_ops() -> None:
    from dazzle.back.runtime.auth.scim_provisioning import parse_group_patch

    body = {"Operations": [
        {"op": "add", "path": "members", "value": [{"value": "m1"}, {"value": "m2"}]},
        {"op": "remove", "path": 'members[value eq "m3"]'},
        {"op": "replace", "path": "displayName", "value": "NewName"},
    ]}
    ops = parse_group_patch(body)
    assert ("add_members", ["m1", "m2"]) in ops
    assert ("remove_member", "m3") in ops
    assert ("rename", "NewName") in ops


def test_parse_group_patch_remove_all_and_replace_members() -> None:
    from dazzle.back.runtime.auth.scim_provisioning import parse_group_patch

    ops = parse_group_patch({"Operations": [
        {"op": "remove", "path": "members"},
        {"op": "replace", "path": "members", "value": [{"value": "m9"}]},
        {"op": "replace", "value": {"displayName": "X"}},  # no-path replace form
    ]})
    assert ("replace_members", []) in ops          # remove-all
    assert ("replace_members", ["m9"]) in ops
    assert ("rename", "X") in ops
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement** `parse_group_patch` in `scim_provisioning.py`:

```python
import re as _re

_MEMBER_VALUE_FILTER = _re.compile(r'members\[\s*value\s+eq\s+"([^"]+)"\s*\]', _re.IGNORECASE)


def parse_group_patch(body: dict[str, Any]) -> list[tuple]:
    """Parse a SCIM PATCH body into concrete (op, arg) tuples (#1342).

    Supported (the forms Okta/Entra send): add members, remove one member by
    `members[value eq "id"]`, remove all members (`path:members`), replace members,
    rename displayName (path or no-path value form). Unknown ops are skipped (the
    route returns the resource unchanged).
    """
    ops: list[tuple] = []
    for op in body.get("Operations", []) or []:
        kind = str(op.get("op", "")).lower()
        path = op.get("path")
        value = op.get("value")
        if kind == "add" and path == "members":
            ops.append(("add_members", [m["value"] for m in (value or []) if "value" in m]))
        elif kind == "remove" and isinstance(path, str):
            m = _MEMBER_VALUE_FILTER.fullmatch(path.strip())
            if m:
                ops.append(("remove_member", m.group(1)))
            elif path == "members":
                ops.append(("replace_members", []))  # remove all
        elif kind == "replace" and path == "members":
            ops.append(("replace_members", [m["value"] for m in (value or []) if "value" in m]))
        elif kind in ("add", "replace") and path == "displayName":
            ops.append(("rename", str(value)))
        elif kind in ("add", "replace") and path is None and isinstance(value, dict):
            if "displayName" in value:
                ops.append(("rename", str(value["displayName"])))
            if "members" in value:
                ops.append((
                    "replace_members",
                    [m["value"] for m in (value["members"] or []) if "value" in m],
                ))
        # else: unknown op — skip
    return ops
```

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit** — `feat(scim): RFC-7644 group PATCH parser (Okta/Entra forms) (#1342)`

---

## Task 7: Groups REST routes + JSON

**Files:**
- Modify: `src/dazzle/back/runtime/auth/scim_routes.py` (endpoints + `_group_to_scim` + apply PATCH)
- Test: `tests/integration/test_scim_routes.py`

- [ ] **Step 1: Write the failing tests** — extend the fake `_Store` (in `test_scim_routes.py`) with the group/member methods + `get_membership`/`update_membership_roles`/`get_member_group_names` (an in-memory impl), then:

```python
def test_groups_crud_and_member_patch(scim_client) -> None:
    # POST create, GET, list filter, PATCH add/remove member, rename, DELETE.
    # Assert: 201 + id on create; member PATCH recomputes the membership's roles;
    # remove-by-`value eq` drops it; DELETE → 404 on subsequent GET.
    ...
```

(Model the fake store + client on the existing SCIM Users route tests in the same file. The membership role recompute is observable via the fake store's recorded `update_membership_roles` calls.)

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement** in `scim_routes.py`, inside `create_scim_routes()` (so it's gated with the rest). Add the serializer + endpoints:

```python
    _GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"

    def _group_to_scim(group: Any, member_ids: list[str], base: str) -> dict[str, Any]:
        return {
            "schemas": [_GROUP_SCHEMA],
            "id": group.id,
            "displayName": group.display_name,
            "members": [
                {"value": mid, "$ref": f"{base}/scim/v2/Users/{mid}"} for mid in member_ids
            ],
            "meta": {"resourceType": "Group", "location": f"{base}/scim/v2/Groups/{group.id}"},
        }

    def _scim_error(status: int, detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={"schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
                     "status": str(status), "detail": detail},
        )

    @router.post("/scim/v2/Groups", status_code=201)
    async def scim_create_group(request: Request) -> Any:
        from dazzle.back.runtime.auth import scim_provisioning as sp

        conn = _require_scim_connection(request)
        store = request.app.state.auth_store
        body = await request.json()
        member_ids = [m["value"] for m in (body.get("members") or []) if "value" in m]
        try:
            group = sp.create_group(store, conn, body.get("displayName", ""), member_ids)
        except sp.SCIMGroupError as e:
            return _scim_error(e.status, str(e))
        base = str(request.base_url).rstrip("/")
        return _group_to_scim(group, store.get_group_member_ids(group.id), base)

    @router.get("/scim/v2/Groups/{group_id}")
    async def scim_get_group(group_id: str, request: Request) -> Any:
        from dazzle.back.runtime.auth import scim_provisioning as sp

        conn = _require_scim_connection(request)
        store = request.app.state.auth_store
        try:
            group = sp.get_group(store, conn, group_id)
        except sp.SCIMGroupError as e:
            return _scim_error(e.status, str(e))
        base = str(request.base_url).rstrip("/")
        return _group_to_scim(group, store.get_group_member_ids(group_id), base)

    @router.get("/scim/v2/Groups")
    async def scim_list_groups(request: Request) -> Any:
        from dazzle.back.runtime.auth import scim_provisioning as sp

        conn = _require_scim_connection(request)
        store = request.app.state.auth_store
        flt = request.query_params.get("filter", "")
        name = None
        m = re.search(r'displayName\s+eq\s+"([^"]+)"', flt)
        if m:
            name = m.group(1)
        groups = sp.list_groups(store, conn, display_name=name)
        base = str(request.base_url).rstrip("/")
        resources = [_group_to_scim(g, store.get_group_member_ids(g.id), base) for g in groups]
        return {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
            "totalResults": len(resources),
            "Resources": resources,
            "itemsPerPage": len(resources),
            "startIndex": 1,
        }

    @router.put("/scim/v2/Groups/{group_id}")
    async def scim_put_group(group_id: str, request: Request) -> Any:
        from dazzle.back.runtime.auth import scim_provisioning as sp

        conn = _require_scim_connection(request)
        store = request.app.state.auth_store
        body = await request.json()
        try:
            if body.get("displayName"):
                sp.rename_group(store, conn, group_id, body["displayName"])
            member_ids = [m["value"] for m in (body.get("members") or []) if "value" in m]
            sp.set_group_members(store, conn, group_id, member_ids)
            group = sp.get_group(store, conn, group_id)
        except sp.SCIMGroupError as e:
            return _scim_error(e.status, str(e))
        base = str(request.base_url).rstrip("/")
        return _group_to_scim(group, store.get_group_member_ids(group_id), base)

    @router.patch("/scim/v2/Groups/{group_id}")
    async def scim_patch_group(group_id: str, request: Request) -> Any:
        from dazzle.back.runtime.auth import scim_provisioning as sp

        conn = _require_scim_connection(request)
        store = request.app.state.auth_store
        body = await request.json()
        try:
            sp.get_group(store, conn, group_id)  # 404 if absent/wrong org
            for kind, arg in sp.parse_group_patch(body):
                if kind == "add_members":
                    sp.add_group_members(store, conn, group_id, arg)
                elif kind == "remove_member":
                    sp.remove_group_member(store, conn, group_id, arg)
                elif kind == "replace_members":
                    sp.set_group_members(store, conn, group_id, arg)
                elif kind == "rename":
                    sp.rename_group(store, conn, group_id, arg)
            group = sp.get_group(store, conn, group_id)
        except sp.SCIMGroupError as e:
            return _scim_error(e.status, str(e))
        base = str(request.base_url).rstrip("/")
        return _group_to_scim(group, store.get_group_member_ids(group_id), base)

    @router.delete("/scim/v2/Groups/{group_id}", status_code=204)
    async def scim_delete_group(group_id: str, request: Request) -> Any:
        from dazzle.back.runtime.auth import scim_provisioning as sp

        conn = _require_scim_connection(request)
        store = request.app.state.auth_store
        try:
            sp.delete_group(store, conn, group_id)
        except sp.SCIMGroupError as e:
            return _scim_error(e.status, str(e))
        return Response(status_code=204)
```

Add imports at the top of `scim_routes.py` if missing: `from fastapi import Response` and `from fastapi.responses import JSONResponse` (check current imports; `re` is likely already imported — grep).

- [ ] **Step 4: Run → pass** — `pytest tests/integration/test_scim_routes.py -q`.

- [ ] **Step 5: Commit** — `feat(scim): /scim/v2/Groups REST endpoints + PATCH (#1342)`

---

## Task 8: `GET /Users/{id}` echoes read-only groups

**Files:**
- Modify: `src/dazzle/back/runtime/auth/scim_routes.py` (the User serializer / GET handler)
- Test: `tests/integration/test_scim_routes.py`

- [ ] **Step 1: Write the failing test** — GET a User who is in a group → the response `groups` array contains the group's display name/value (read-only reflection).

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement** — in the SCIM User serialization (grep the function that builds the User JSON, e.g. `_membership_to_scim_user` or inline in the `GET /Users/{id}` handler), add a `groups` field built from `store.get_member_group_names(membership_id, conn.id)` (read-only; display names). Keep it minimal — value can be the display name.

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit** — `feat(scim): User resource echoes read-only group memberships (#1342)`

---

## Task 9: Docs + CHANGELOG

- [ ] Update `docs/reference/enterprise-sso.md` SCIM section: document `/scim/v2/Groups` (CRUD + member PATCH), that group membership drives roles via `group_mapping` (default-deny), and the **clean-break** (the `User.groups` attribute no longer assigns roles — use `/Groups`).
- [ ] CHANGELOG `### Added`: the `/Groups` resource (persisted, multi-group-faithful role recompute). `### Changed` + a migration note: `User.groups` write-path dropped to informational. `#### Agent Guidance`: group→role is owned by `/Groups`; `group_mapping` (default-deny) maps display names to roles.
- [ ] Commit — `docs(scim): /Groups + User.groups clean-break note (#1342)`

---

## Final integration check (before ship)

- [ ] `ruff check src/ tests/ --fix && ruff format src/ tests/`
- [ ] `mypy src/dazzle`
- [ ] `pytest tests/ -m "not e2e"` — full unit suite green
- [ ] `DATABASE_URL=…/dazzle_dev pytest -m postgres -q` — the store + provisioning tests run here (auth-store schema change)
- [ ] Manual: with a SCIM connection, `POST /scim/v2/Groups` (Eng→engineer in group_mapping) + a member → that membership gets `engineer`; add a second group (Ops→operator) + member → both roles; PATCH-remove from Eng → only `operator` remains; DELETE Ops → no roles. `User.groups` on a User PUT does not change roles.
- [ ] `/bump patch`, commit, push, monitor CI (incl. `-m postgres`), comment on #1342.

## Notes for the implementer
- **Real PG required** for Tasks 2-5,8 (the store/provisioning); the PATCH parser (Task 6) is pure. Use `DATABASE_URL=postgresql://localhost/dazzle_dev`.
- **`create_membership` signature**: grep `def create_membership` — adapt the test fixtures if it differs from `(tenant_id, identity_id, roles)`.
- **`provision_scim_user` return shape**: grep it before writing Task 5's assertion.
- **Clean-break blast radius**: Task 5 changes existing SCIM User behaviour — update any test asserting roles-from-`groups`. This is the documented break.
- The routes are inside `create_saml_routes`'s sibling `create_scim_routes()` — already capability-gated via `_mount_scim` (only mounts when `auth.enterprise.scim` is active). No extra gating needed.
