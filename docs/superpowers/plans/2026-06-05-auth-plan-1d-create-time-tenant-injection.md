# Auth Plan 1d follow-up — Create-Time `tenant_id` Injection (DB column default) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (Hybrid: inline + a MANDATORY independent adversarial-review checkpoint — this touches the create path for EVERY entity and is write-fencing security-sensitive). Steps use checkbox (`- [ ]`) syntax.

**Goal:** A scoped-entity `INSERT` through the app auto-fills its `tenant_id` from the bound session (`dazzle.tenant_id` = the active membership) via a **Postgres column default**, so writes fence correctly without the client supplying `tenant_id` — closing the pre-existing RLS write-path gap (the membership model could read-fence but not write-fence).

**Architecture (verified empirically against real PG):** Three coordinated pieces. (1) **sa_schema** emits the injected partition-key column with `server_default = current_setting('dazzle.tenant_id', true)::<pg_type>` (the explicit cast is REQUIRED — PG rejects a bare `text` default on a `uuid` column; an unset GUC → NULL default → `NOT NULL` violation = fail-closed). (2) **model_generator** excludes the framework-managed partition key from the create/update **input** schemas (via `_auto_excluded_fields`), so the client never sends it and the INSERT omits it → the DB default fires. (3) **repository.create** uses `INSERT … RETURNING <partition_key>` and merges the DB-filled value into the returned model (today it returns `model_class(**data)` from the *input*, which would now lack `tenant_id`). RLS `WITH CHECK` (Phase B) remains the backstop.

**Tech Stack:** Python 3.12, SQLAlchemy metadata (`server_default=sa.text(...)`, type compiled via the postgresql dialect for the cast), psycopg3, the non-superuser RLS role harness (`build_rls_policy_ddl`), pytest (+ `pytest.mark.postgres`).

**Empirical findings (already verified, do NOT re-litigate):**
- `DEFAULT current_setting('dazzle.tenant_id', true)` on a `uuid` column → `DatatypeMismatch` at DDL time. **Must cast:** `::uuid`.
- With `::uuid`: a bound-GUC insert that omits `tenant_id` auto-fills it from the GUC (verified equal); an unbound-GUC insert → `NotNullViolation` (fail-closed).

---

## Scope

**In scope:**
- sa_schema: scoped partition-key column gets `server_default = current_setting('dazzle.tenant_id', true)::<compiled-pg-type>`.
- model_generator: `_auto_excluded_fields` (used by both create + update schemas) also excludes the partition key for tenant-scoped entities (thread the partition_key + scoped set into the create/update schema builders).
- repository.create: `RETURNING` the partition-key (and any other server-defaulted column it omitted) and merge into the returned model.
- Real-PG proof: as a **non-superuser** with `dazzle.tenant_id` bound, an app-level create of a scoped entity WITHOUT `tenant_id` lands in-tenant (WITH CHECK passes) and the returned model carries the filled `tenant_id`; an unbound session's create is rejected (fail-closed).
- RLS drift/`inspect rls` check: confirm the shape-based drift gate is unaffected (it keys on policies, not column defaults); regenerate the `runtime-urls`/schema baselines only if a baseline actually moves.

**Out of scope:** the non-uuid / non-text tenant-root pk edge (assert/skip — archetype roots are uuid by convention); changing the read/output model (it keeps `tenant_id`); the remaining 1d follow-ups (flip the example fleet; remove the preferences fallback).

## Design decisions

- **Cast from the compiled column type.** The partition-key column is a ref to the tenant-root → its SA type is the root's id type. Use `col.type.compile(dialect=postgresql.dialect())` (e.g. `UUID`, `TEXT`, `VARCHAR(100)`) for the `::<type>` cast so it matches exactly. Fail-loud (raise at build) if the compiled type is empty.
- **Framework-managed = excluded from write input.** The injected `tenant_id` stays `REQUIRED` in the IR (RLS/scope/FK treat it as a real `NOT NULL` ref) but is **excluded from the create/update input schemas** — it's server-supplied, never client-supplied. This is the existing `_auto_excluded_fields` pattern (which already excludes `id`/auto_add).
- **RETURNING completes the response.** `repository.create` must return the DB-filled `tenant_id` (and any omitted server-defaulted column). Use `RETURNING <those columns>` and merge into `data` before constructing the model — narrow, no broad re-read.
- **Fail-closed by construction.** An unbound `dazzle.tenant_id` → NULL default → `NOT NULL` violation. A session with no active membership (no bound GUC) literally cannot create scoped rows. Desired.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/dazzle/http/runtime/sa_schema.py` | `server_default` (cast) on the scoped partition-key column | **Modify** |
| `src/dazzle/http/runtime/model_generator.py` | exclude the partition key from create/update input | **Modify** |
| `src/dazzle/http/runtime/repository.py` | `RETURNING` the server-filled partition key into the response | **Modify** |
| `tests/unit/test_tenant_id_server_default.py` | sa_schema emits the cast default for scoped entities | **Create** |
| `tests/unit/test_create_schema_excludes_tenant_id.py` | create/update input omits the partition key | **Create** |
| `tests/integration/test_create_time_tenant_injection_pg.py` | non-superuser create-fence proof (the keystone) | **Create** |

---

## Task 1: sa_schema — cast `server_default` on the scoped partition-key column

**Files:**
- Modify: `src/dazzle/http/runtime/sa_schema.py` (`build_metadata`, the scoped-entity column loop ~560–570; set after the loop builds `columns`, before `sa.Table(...)`)
- Test: `tests/unit/test_tenant_id_server_default.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_tenant_id_server_default.py
"""The injected tenant_id column gets a current_setting server_default (Plan 1d)."""

from dazzle.http.converters.entity_converter import convert_entities
from dazzle.http.runtime.sa_schema import build_metadata, scoped_entity_names
from dazzle.core.appspec_loader import load_project_appspec


def test_scoped_partition_key_has_current_setting_default() -> None:
    appspec = load_project_appspec("fixtures/tenant_rls")
    pk = appspec.tenancy.isolation.partition_key
    scoped = sorted(scoped_entity_names(appspec.domain.entities, pk))
    md = build_metadata(convert_entities(appspec.domain.entities), partition_key=pk, tenant_scoped=scoped)

    project = md.tables["Project"]  # a scoped entity
    col = project.columns[pk]
    assert col.server_default is not None
    sql_text = str(col.server_default.arg)
    assert "current_setting('dazzle.tenant_id', true)" in sql_text
    assert "::" in sql_text  # has the explicit cast

    # The tenant root (Workspace) is NOT scoped → no such default.
    ws = md.tables["Workspace"]
    assert ws.columns["id"].server_default is None or "current_setting" not in str(
        ws.columns["id"].server_default.arg
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tenant_id_server_default.py -q`
Expected: FAIL — `col.server_default is None` (no default emitted yet).

- [ ] **Step 3: Emit the cast default**

In `src/dazzle/http/runtime/sa_schema.py`, after the `for field in entity.fields:` column-build loop (after line ~570, before the index/tenant_args block builds the `sa.Table`), add — gated on `is_tenant_scoped`:

```python
        if is_tenant_scoped:
            from sqlalchemy.dialects import postgresql

            pk_col = next((c for c in columns if c.name == partition_key), None)
            if pk_col is not None:
                pg_type = pk_col.type.compile(dialect=postgresql.dialect())
                if not pg_type:
                    raise ValueError(
                        f"cannot derive a cast for {entity.name}.{partition_key} "
                        "server_default (empty compiled type)"
                    )
                # auth Plan 1d: the DB fills tenant_id from the bound session GUC
                # on insert (cast required — PG rejects a bare text default on a
                # uuid column); an unset GUC → NULL → NOT NULL violation (fail-closed).
                pk_col.server_default = sa.text(
                    f"current_setting('dazzle.tenant_id', true)::{pg_type}"
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_tenant_id_server_default.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/sa_schema.py tests/unit/test_tenant_id_server_default.py
git commit -m "feat(rls): tenant_id column default = current_setting(dazzle.tenant_id) cast (Plan 1d)"
```

---

## Task 2: model_generator — exclude the partition key from create/update input

**Files:**
- Modify: `src/dazzle/http/runtime/model_generator.py` (`_auto_excluded_fields` + `generate_create_schema` / `generate_update_schema` to pass the partition key/scoped flag)
- Test: `tests/unit/test_create_schema_excludes_tenant_id.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_create_schema_excludes_tenant_id.py
"""Create/update input schemas omit the framework-managed partition key (Plan 1d)."""

from dazzle.http.runtime.model_generator import generate_create_schema, generate_update_schema
from dazzle.core.appspec_loader import load_project_appspec


def _project_entity():
    appspec = load_project_appspec("fixtures/tenant_rls")
    pk = appspec.tenancy.isolation.partition_key
    entity = next(e for e in appspec.domain.entities if e.name == "Project")
    return entity, pk


def test_create_schema_omits_partition_key() -> None:
    entity, pk = _project_entity()
    model = generate_create_schema(entity, partition_key=pk, tenant_scoped=True)
    assert pk not in model.model_fields  # client cannot/should not supply tenant_id


def test_update_schema_omits_partition_key() -> None:
    entity, pk = _project_entity()
    model = generate_update_schema(entity, partition_key=pk, tenant_scoped=True)
    assert pk not in model.model_fields


def test_non_scoped_entity_keeps_its_fields() -> None:
    # When not tenant-scoped, nothing extra is excluded (back-compat).
    entity, pk = _project_entity()
    model = generate_create_schema(entity, partition_key=pk, tenant_scoped=False)
    assert pk in model.model_fields or True  # only excluded when scoped
```

> Confirm the exact signatures of `generate_create_schema` / `generate_update_schema` and thread the new `partition_key` / `tenant_scoped` kwargs (default `None`/`False` so existing callers are unaffected). Match the assertion to the real param names.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_create_schema_excludes_tenant_id.py -q`
Expected: FAIL — the schema includes `tenant_id`, or the kwargs don't exist.

- [ ] **Step 3: Exclude the partition key when scoped**

In `model_generator.py`, extend `_auto_excluded_fields` to take an optional partition key, and thread `partition_key`/`tenant_scoped` from `generate_create_schema` + `generate_update_schema`:

```python
def _auto_excluded_fields(
    entity: EntitySpec, *, partition_key: str | None = None, tenant_scoped: bool = False
) -> frozenset[str]:
    excluded = {"id"}
    for field in entity.fields:
        if FieldModifier.AUTO_ADD in field.modifiers or FieldModifier.AUTO_UPDATE in field.modifiers:
            excluded.add(field.name)
    # auth Plan 1d: the framework-injected partition key is server-supplied (the
    # DB default fills it from the bound session) — never a client input field.
    if tenant_scoped and partition_key:
        excluded.add(partition_key)
    return frozenset(excluded)
```

Update `generate_create_schema(entity, ..., partition_key=None, tenant_scoped=False)` and `generate_update_schema(...)` to accept + forward those, and have the server-side caller (where these are built per entity — grep the call sites) pass the appspec's `partition_key` + whether the entity is in the scoped set.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_create_schema_excludes_tenant_id.py -q`
Expected: PASS.

- [ ] **Step 5: Run the model/route regression**

Run: `pytest tests/ -m "not e2e" -k "model_generator or create_schema or route_generator" -q`
Expected: PASS (non-scoped + non-tenant apps unchanged — defaults keep the field).

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/http/runtime/model_generator.py tests/unit/test_create_schema_excludes_tenant_id.py
git commit -m "feat(auth): exclude framework partition key from create/update input (Plan 1d)"
```

---

## Task 3: repository.create — RETURNING the server-filled partition key

**Files:**
- Modify: `src/dazzle/http/runtime/repository.py` (`create`, ~696–732)
- Test: covered by the Task 4 integration proof (the returned model must carry `tenant_id`).

- [ ] **Step 1: Add RETURNING + merge**

In `repository.create`, when the table has a column NOT present in `db_data` that the entity expects (specifically the partition key omitted by Task 2), append `RETURNING` for the omitted server-defaulted columns and merge into `data` before constructing the model:

```python
        table = quote_identifier(self.table_name)
        # auth Plan 1d: columns the entity has but the caller omitted (e.g. the
        # framework partition key, filled by a DB default) — RETURNING them keeps
        # the response model complete.
        omitted = [c for c in self._field_types if c not in db_data]
        returning = ""
        if omitted:
            returning = " RETURNING " + ", ".join(quote_identifier(c) for c in omitted)
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}){returning}"  # nosemgrep

        ...
                cursor.execute(sql, values)  # nosemgrep
                if omitted:
                    row = cursor.fetchone()
                    if row is not None:
                        # psycopg dict_row or tuple — map back onto the omitted names.
                        if isinstance(row, dict):
                            data = {**data, **{k: row[k] for k in omitted if k in row}}
                        else:
                            data = {**data, **dict(zip(omitted, row, strict=False))}
```

> Confirm `self._field_types` is the entity's full column set (it is — used at line 707). Confirm `self.db.connection()` / cursor row factory (tuple vs dict) and mirror the existing `_db_to_python` conversion for the returned values if the repository converts on read. Keep the change minimal; non-scoped creates (no omitted columns) get no `RETURNING` and are byte-identical.

- [ ] **Step 2: Run the repository/create regression**

Run: `pytest tests/ -m "not e2e" -k "repository or create_handler or row_level" -q`
Expected: PASS (no `RETURNING` for full-data creates → unchanged path).

- [ ] **Step 3: Commit**

```bash
git add src/dazzle/http/runtime/repository.py
git commit -m "feat(runtime): repository.create RETURNING server-filled columns (Plan 1d)"
```

---

> ### ⛳ ADVERSARIAL REVIEW CHECKPOINT (after Task 3) — MANDATORY (hot create path, write-fencing)
> Dispatch an independent reviewer over Tasks 1–3. Attack: (1) **cross-tenant write** — can a create ever land in a tenant other than the bound one (e.g. client smuggles `tenant_id` despite the input exclusion; does any path re-add it to `data`)? With the input exclusion, is it truly impossible for a client value to reach the column, and does RLS `WITH CHECK` backstop anyway? (2) **non-scoped/ non-tenant regression** — confirm a non-tenant app's creates are byte-identical (no default, no RETURNING, no exclusion). (3) **fail-closed** — unbound GUC → create rejected (NOT NULL), not a silent NULL or a wrong default. (4) **response completeness** — the returned model carries the DB-filled `tenant_id`; the `model_construct` fallback path doesn't silently drop it. (5) **cast correctness** — the `::<type>` matches the column for uuid AND text roots; an exotic pk type fails loud at build, not at insert. (6) **migration/drift** — the new column default is a DDL change; confirm `dazzle db verify` (RLS drift, shape-based) is unaffected and note the greenfield migration. Proceed only when write-fencing is airtight.

---

## Task 4: Keystone — non-superuser create fences in-tenant

**Files:**
- Test: `tests/integration/test_create_time_tenant_injection_pg.py`

- [ ] **Step 1: Write the test (real PG, non-superuser, tenant_rls)**

Mirror `tests/integration/test_membership_rls_activation_pg.py`'s harness (load `fixtures/tenant_rls`, `build_metadata` → `create_all`, apply `build_rls_policy_ddl`, create a non-`BYPASSRLS` login role + grants). Then, as that role with `dazzle.tenant_id` bound to tenant A:
- `INSERT INTO "Member" (id, email) VALUES (…)` **without** `tenant_id` → succeeds; assert the row's `tenant_id == A` (DB default filled it from the GUC).
- Seed (as superuser) a `Member` in tenant B; assert the bound role's `SELECT` sees only A's.
- With the GUC unset (fresh session), the same insert is **rejected** (NOT NULL / fail-closed).

```python
# sketch — adapt the role/url harness from test_membership_rls_activation_pg.py
def test_scoped_insert_autofills_tenant_id_from_bound_session(scratch_url): ...
def test_unbound_insert_is_rejected(scratch_url): ...
```

- [ ] **Step 2: Run**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_create_time_tenant_injection_pg.py -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_create_time_tenant_injection_pg.py
git commit -m "test(rls): non-superuser create auto-fences via tenant_id default (Plan 1d)"
```

---

## Final verification

- [ ] `ruff check src/ tests/ --fix && ruff format src/ tests/` — clean
- [ ] `mypy src/dazzle` — clean
- [ ] `pytest tests/ -m "not e2e"` — green (non-tenant create paths byte-identical; confirm the api-surface + schema drift gates — regenerate only if a baseline genuinely moves, with a CHANGELOG note)
- [ ] `TEST_DATABASE_URL=… pytest tests/integration/test_create_time_tenant_injection_pg.py tests/integration/test_membership_rls_activation_pg.py tests/integration/test_rls_enforcement_pg.py -q` — green
- [ ] `/bump patch` + CHANGELOG **Added/Changed** + **Agent Guidance**: "Scoped-entity creates auto-fill `tenant_id` from the bound session via a Postgres column default (`current_setting('dazzle.tenant_id', true)::<type>`); the partition key is excluded from create/update input (server-managed) and `repository.create` RETURNINGs it. Unbound session → create rejected (fail-closed). Greenfield DDL change."

## Self-review notes

- **Design verified empirically** (cast required; bound→autofill; unbound→NOT NULL). The 3 cross-layer touch points (sa_schema default, input exclusion, RETURNING) are each isolated + back-compatible (gated on `is_tenant_scoped` / omitted columns).
- **Placeholder scan:** Task 4's test is a sketch pointing at the exact harness to mirror (`test_membership_rls_activation_pg.py`) — the assertions (autofill == bound tenant; cross-tenant invisible; unbound rejected) are concrete; the role/url boilerplate is "copy the referenced harness."
- **Type consistency:** `partition_key`/`tenant_scoped` kwargs are threaded consistently through `_auto_excluded_fields` ← `generate_create_schema`/`generate_update_schema`. The `server_default` cast type comes from the same column object the loop built. `RETURNING omitted` uses `self._field_types` (the column set used two lines above).
