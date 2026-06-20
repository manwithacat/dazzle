# RLS-Backed Row Tenancy — Phase A (Discriminator Substrate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the tenant discriminator **framework-owned and uniform** for `tenancy: mode: shared_schema` apps, and emit the construction rules that make the boundary enforceable: a uniform injected `tenant_id` column, `UNIQUE(tenant_id, id)`, composite intra-tenant FKs, tenant-scoped uniqueness, and a `tenant_id`-leading index — the substrate Phase B's RLS sits on.

**Architecture:** Two layers. (1) **IR/linker** — move tenant-FK injection out of `expand_archetypes` (which has no tenancy context) into a new post-merge, pre-FK-graph stage that, under `SHARED_SCHEMA`, injects a *uniform* `partition_key` (default `tenant_id`) ref to the declared tenant entity on every tenant-scoped entity, honoring `tenancy.entities_excluded`. (2) **Schema generation** — `sa_schema.build_metadata` learns which entities are tenant-scoped and emits `UNIQUE(tenant_id, id)`, composite FKs `(tenant_id, fk) → parent(tenant_id, id)`, tenant-scoped uniqueness, and a leading index.

**Tech stack:** Python 3.12, Pydantic IR (frozen models, `model_copy`), SQLAlchemy Core metadata, psycopg v3, pytest (`-m "not e2e"` unit, `-m postgres` real-PG).

---

## Context the implementer needs

- **Reuse the existing tenancy layer — do not invent.** `tenancy:` DSL block → `TenancySpec` (`/Volumes/SSD/Dazzle/src/dazzle/core/ir/governance.py:127-160`): `isolation.mode` (`TenancyMode.SHARED_SCHEMA`), `isolation.partition_key` (default `"tenant_id"`), `entities_excluded`, `admin_personas`. Used by `/Volumes/SSD/Dazzle/examples/invoice_ops` and `/Volumes/SSD/Dazzle/examples/support_tickets`. Design + decisions: `/Volumes/SSD/Dazzle/docs/superpowers/specs/2026-06-04-rls-tenancy-design.md` (§3.1 reconciliation) and its companion `/Volumes/SSD/Dazzle/docs/superpowers/specs/2026-06-04-rls-tenancy-generation-rules.md` (authoritative for emitted DDL).
- **Tenant identity (resolved §7 Q3):** the author's declared tenant entity (`archetype: tenant` → `is_tenant_root`) is canonical; `tenant_id` is a `ref <TenantEntity>`. `public.tenants` is its 1:1 registry — **but wiring that linkage is Phase E, not Phase A.** Phase A's FK target is the tenant entity.
- **Greenfield only.** No backfill of existing DBs, no migration of deployed apps. These are *forward construction rules* for newly-generated schemas. Existing examples that hand-declare `tenant_id` keep working via the skip-if-present guard.
- **Sequencing fact (load-bearing):** `tenancy` is only available after `merge_fragments` (`/Volumes/SSD/Dazzle/src/dazzle/core/linker.py:132`). The current `_inject_tenant_fk` runs at Stage 5 (`linker.py:115`, inside `expand_archetypes`) with no tenancy context and injects a *per-app-named* ref (`Company` → `company`) whenever a tenant entity exists. Phase A moves this into a tenancy-aware post-merge stage.
- **Out of scope for Phase A (later phases):** RLS policies / `ENABLE/FORCE RLS` / `set_config` runtime context / the three-role model (Phase B); auth-store tenant-scoping (its own phase); the `public.tenants` 1:1 provisioning linkage + excision (Phase E); the `app`-schema move (tables stay in the default/`public` schema for now). Do **not** build these here.
- **PK invariant:** every entity has a single `id` PK (`sa_schema.py:406-409`). Composite FKs and `UNIQUE(tenant_id, id)` rely on this.

## File structure

| File | Responsibility | Change |
|------|----------------|--------|
| `/Volumes/SSD/Dazzle/src/dazzle/core/tenancy_inject.py` | Uniform partition-key injection (IR) | **Create** — `inject_partition_key(entities, tenancy, *, legacy_archetype_fallback)` |
| `/Volumes/SSD/Dazzle/src/dazzle/core/archetype_expander.py` | Archetype expansion | **Modify** — remove the Stage-5 `_inject_tenant_fk` call (line 44-47); keep `_inject_tenant_fk`/`_find_tenant_entity` as importable helpers |
| `/Volumes/SSD/Dazzle/src/dazzle/core/linker.py` | Link pipeline | **Modify** — add the post-merge injection stage (~line 212, after signable injection, before FK-graph build at 217) |
| `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/sa_schema.py` | EntitySpec → SA metadata | **Modify** — `build_metadata` gains tenancy awareness; emit `UNIQUE(tenant_id,id)`, composite FKs, tenant-scoped uniqueness, leading index |
| `/Volumes/SSD/Dazzle/src/dazzle/http/alembic/metadata_loader.py` | Alembic target metadata | **Modify** — pass `appspec.tenancy` into `build_metadata` |
| `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/server.py` | Runtime schema create | **Modify** — pass `appspec.tenancy` into the two `build_metadata` calls (`_setup_database`, `_migrate_tenant_schemas`) |
| `/Volumes/SSD/Dazzle/tests/unit/test_tenancy_partition_inject.py` | Injection unit tests | **Create** |
| `/Volumes/SSD/Dazzle/tests/unit/test_sa_schema_tenant_constraints.py` | Construction-rule unit tests | **Create** |
| `/Volumes/SSD/Dazzle/fixtures/tenant_rls/` | Shared-schema fixture (no hand-declared tenant_id) | **Create** |
| `/Volumes/SSD/Dazzle/tests/integration/test_tenant_rls_constraints_pg.py` | Real-PG constraint test | **Create** |
| `/Volumes/SSD/Dazzle/CHANGELOG.md` | Release notes | **Modify** |

---

## Task 1: Uniform partition-key injection (IR/linker)

**Files:**
- Create: `/Volumes/SSD/Dazzle/src/dazzle/core/tenancy_inject.py`
- Modify: `/Volumes/SSD/Dazzle/src/dazzle/core/archetype_expander.py`, `/Volumes/SSD/Dazzle/src/dazzle/core/linker.py`
- Test: `/Volumes/SSD/Dazzle/tests/unit/test_tenancy_partition_inject.py`

- [ ] **Step 1: Write the failing tests**

Create `/Volumes/SSD/Dazzle/tests/unit/test_tenancy_partition_inject.py`:

```python
"""Unit tests for framework-owned partition-key injection (RLS tenancy Phase A)."""

from __future__ import annotations

from dazzle.core import ir
from dazzle.core.tenancy_inject import inject_partition_key


def _entity(name: str, *fields: ir.FieldSpec, is_tenant_root: bool = False,
            archetype: ir.ArchetypeKind | None = None) -> ir.EntitySpec:
    base = [ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                         modifiers=[ir.FieldModifier.PK])]
    return ir.EntitySpec(name=name, title=name, fields=base + list(fields),
                         is_tenant_root=is_tenant_root, archetype_kind=archetype)


def _ref(name: str, target: str) -> ir.FieldSpec:
    return ir.FieldSpec(name=name, type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity=target),
                        modifiers=[ir.FieldModifier.REQUIRED])


def _shared_schema_tenancy(excluded: list[str] | None = None) -> ir.TenancySpec:
    return ir.TenancySpec(
        isolation=ir.TenantIsolationSpec(mode=ir.TenancyMode.SHARED_SCHEMA, partition_key="tenant_id"),
        entities_excluded=excluded or [],
    )


def test_injects_uniform_tenant_id_on_scoped_entities() -> None:
    entities = [_entity("Workspace", is_tenant_root=True), _entity("Project"), _entity("Task")]
    out = inject_partition_key(entities, _shared_schema_tenancy())
    by_name = {e.name: e for e in out}
    # tenant root itself is NOT scoped
    assert all(f.name != "tenant_id" for f in by_name["Workspace"].fields)
    # every other entity gets a uniform tenant_id ref to the tenant entity, first
    for n in ("Project", "Task"):
        tid = by_name[n].fields[0]
        assert tid.name == "tenant_id"
        assert tid.type.kind == ir.FieldTypeKind.REF
        assert tid.type.ref_entity == "Workspace"
        assert ir.FieldModifier.REQUIRED in tid.modifiers


def test_respects_entities_excluded() -> None:
    entities = [_entity("Workspace", is_tenant_root=True), _entity("Currency"), _entity("Task")]
    out = inject_partition_key(entities, _shared_schema_tenancy(excluded=["Currency"]))
    by_name = {e.name: e for e in out}
    assert all(f.name != "tenant_id" for f in by_name["Currency"].fields)
    assert by_name["Task"].fields[0].name == "tenant_id"


def test_skips_if_already_declared() -> None:
    # invoice_ops back-compat: author already hand-declared tenant_id.
    entities = [_entity("Workspace", is_tenant_root=True),
                _entity("Task", _ref("tenant_id", "Workspace"))]
    out = inject_partition_key(entities, _shared_schema_tenancy())
    task = next(e for e in out if e.name == "Task")
    assert sum(1 for f in task.fields if f.name == "tenant_id") == 1


def test_skips_user_and_settings_archetypes() -> None:
    entities = [_entity("Workspace", is_tenant_root=True),
                _entity("Member", archetype=ir.ArchetypeKind.USER),
                _entity("Config", archetype=ir.ArchetypeKind.SETTINGS)]
    out = inject_partition_key(entities, _shared_schema_tenancy())
    by_name = {e.name: e for e in out}
    assert all(f.name != "tenant_id" for f in by_name["Member"].fields)
    assert all(f.name != "tenant_id" for f in by_name["Config"].fields)


def test_noop_when_not_shared_schema() -> None:
    entities = [_entity("Workspace", is_tenant_root=True), _entity("Task")]
    single = ir.TenancySpec(isolation=ir.TenantIsolationSpec(mode=ir.TenancyMode.SINGLE))
    out = inject_partition_key(entities, single)
    assert all(f.name != "tenant_id" for e in out for f in e.fields if e.name == "Task")


def test_noop_when_no_tenant_entity() -> None:
    entities = [_entity("Project"), _entity("Task")]
    out = inject_partition_key(entities, _shared_schema_tenancy())
    assert out == entities  # nothing to anchor to; left untouched
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_tenancy_partition_inject.py -v`
Expected: FAIL — `dazzle.core.tenancy_inject` does not exist. (First confirm the exact IR symbol names by reading `/Volumes/SSD/Dazzle/src/dazzle/core/ir/governance.py` and `/Volumes/SSD/Dazzle/src/dazzle/core/ir/__init__.py`; if `TenancySpec`/`TenantIsolationSpec`/`TenancyMode`/`ArchetypeKind`/`FieldTypeKind` are re-exported from `dazzle.core.ir`, the imports above are correct — adjust if a test helper field name differs.)

- [ ] **Step 3: Implement the injector**

Create `/Volumes/SSD/Dazzle/src/dazzle/core/tenancy_inject.py`:

```python
"""Framework-owned tenant-discriminator injection (RLS tenancy Phase A).

Under `tenancy: mode: shared_schema`, every tenant-scoped entity gets a uniform
`partition_key` (default `tenant_id`) ``ref <TenantEntity> required`` injected as
its first field — making the discriminator framework-owned rather than
author-declared. Honors `tenancy.entities_excluded`; skips the tenant entity,
USER/SETTINGS archetypes, and entities that already declare the column (so apps
that hand-declared `tenant_id` keep working). Pure IR transform — no DB, no SQL.
"""

from __future__ import annotations

from dazzle.core import ir


def _find_tenant_entity(entities: list[ir.EntitySpec]) -> ir.EntitySpec | None:
    for entity in entities:
        if entity.is_tenant_root or entity.archetype_kind == ir.ArchetypeKind.TENANT:
            return entity
    return None


def inject_partition_key(
    entities: list[ir.EntitySpec],
    tenancy: ir.TenancySpec | None,
) -> list[ir.EntitySpec]:
    """Inject the uniform partition-key ref on tenant-scoped entities.

    Returns the entity list unchanged unless ``tenancy.isolation.mode`` is
    SHARED_SCHEMA and a tenant entity exists.
    """
    if tenancy is None or tenancy.isolation.mode != ir.TenancyMode.SHARED_SCHEMA:
        return entities

    tenant_entity = _find_tenant_entity(entities)
    if tenant_entity is None:
        return entities

    partition_key = tenancy.isolation.partition_key
    excluded = set(tenancy.entities_excluded)
    tenant_name = tenant_entity.name

    result: list[ir.EntitySpec] = []
    for entity in entities:
        if (
            entity.name == tenant_name
            or entity.name in excluded
            or entity.archetype_kind in (ir.ArchetypeKind.USER, ir.ArchetypeKind.SETTINGS)
            or any(f.name == partition_key for f in entity.fields)
        ):
            result.append(entity)
            continue

        field = ir.FieldSpec(
            name=partition_key,
            type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity=tenant_name),
            modifiers=[ir.FieldModifier.REQUIRED],
        )
        result.append(entity.model_copy(update={"fields": [field, *entity.fields]}))

    return result
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_tenancy_partition_inject.py -v`
Expected: PASS. If `ir.TenancySpec`/`ir.TenantIsolationSpec`/`ir.TenancyMode` aren't re-exported from `dazzle.core.ir`, import from `dazzle.core.ir.governance` instead (verify the export surface in `/Volumes/SSD/Dazzle/src/dazzle/core/ir/__init__.py`).

- [ ] **Step 5: Remove the Stage-5 injection from `expand_archetypes`**

In `/Volumes/SSD/Dazzle/src/dazzle/core/archetype_expander.py`, delete the third-pass tenant-FK injection (lines 44-47):

```python
    # Third pass: inject tenant FK if there's a tenant entity
    tenant_entity = _find_tenant_entity(expanded)
    if tenant_entity:
        expanded = _inject_tenant_fk(expanded, tenant_entity)
```

Leave `_inject_tenant_fk` and `_find_tenant_entity` defined (they remain importable; `_inject_tenant_fk` is no longer called from here — Phase A's `inject_partition_key` replaces it for `shared_schema`). Add a one-line comment where the call was: `# Tenant discriminator is injected post-merge (tenancy-aware) in linker.py — see tenancy_inject.inject_partition_key.`

- [ ] **Step 6: Wire the new stage into the linker**

In `/Volumes/SSD/Dazzle/src/dazzle/core/linker.py`, immediately after the signable injection (line 211, `entities = _inject_signable_fields(entities)`) and before the FK-graph build (line 213-217), add:

```python
    # 9f. Inject the framework-owned tenant discriminator (RLS tenancy Phase A).
    # Runs here — after merge (tenancy is available) and after all other entity
    # injection, but before the FK graph — so the injected `tenant_id` is seen by
    # the FK graph, scope-predicate compilation, converters, and schema gen.
    from .tenancy_inject import inject_partition_key

    entities = inject_partition_key(list(entities), merged_fragment.tenancy)
```

(`merged_fragment.tenancy` is populated at Stage 8, line 132.)

- [ ] **Step 7: Run the linker/tenancy/archetype unit slices**

Run: `pytest tests/unit/ -k "tenancy or archetype or linker or fk_graph" -v`
Expected: PASS. Pre-existing archetype tests that asserted the old `company`-style injection may need updating — if a test asserts auto-injection of a *named* tenant ref *without* a `shared_schema` tenancy block, that path is intentionally removed; update those tests to use the `shared_schema` + uniform `tenant_id` expectation, or move them to assert the new behavior. **If a pre-existing example/fixture breaks, STOP and report which** (do not silently weaken).

- [ ] **Step 8: Commit**

```bash
git add src/dazzle/core/tenancy_inject.py src/dazzle/core/archetype_expander.py src/dazzle/core/linker.py tests/unit/test_tenancy_partition_inject.py
git commit -m "feat(tenancy): framework-owned uniform tenant_id injection under shared_schema (RLS Phase A)"
```

---

## Task 2: Construction rules in schema generation

**Files:**
- Modify: `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/sa_schema.py`, `/Volumes/SSD/Dazzle/src/dazzle/http/alembic/metadata_loader.py`, `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/server.py`
- Test: `/Volumes/SSD/Dazzle/tests/unit/test_sa_schema_tenant_constraints.py`

**Design:** `build_metadata` gains a keyword `partition_key: str | None = None` and `tenant_scoped: set[str] | None = None` (the set of entity names that carry the discriminator). When an entity is in `tenant_scoped`, the table-assembly loop additionally emits: (a) `UNIQUE(<partition_key>, id)`; (b) for each ref field whose target is also in `tenant_scoped`, a **table-level composite FK** `(<partition_key>, <fk>) → <target>(<partition_key>, id)` and the column's own single-column FK is **suppressed**; (c) author unique keys are rewritten to lead with `<partition_key>`; (d) a `(<partition_key>, id)` index. Refs to non-tenant-scoped (global) targets stay single-column.

- [ ] **Step 1: Write the failing tests**

Create `/Volumes/SSD/Dazzle/tests/unit/test_sa_schema_tenant_constraints.py`:

```python
"""Construction-rule tests for tenant-scoped schema generation (RLS Phase A)."""

from __future__ import annotations

from dazzle.core import ir
from dazzle.http.converters.entity_converter import convert_entities
from dazzle.http.runtime.sa_schema import build_metadata


def _e(name: str, *fields: ir.FieldSpec, **kw) -> ir.EntitySpec:
    base = [ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                         modifiers=[ir.FieldModifier.PK])]
    return ir.EntitySpec(name=name, title=name, fields=base + list(fields), **kw)


def _tid(target: str = "Workspace") -> ir.FieldSpec:
    return ir.FieldSpec(name="tenant_id", type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity=target),
                        modifiers=[ir.FieldModifier.REQUIRED])


def _ref(name: str, target: str) -> ir.FieldSpec:
    return ir.FieldSpec(name=name, type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity=target),
                        modifiers=[ir.FieldModifier.REQUIRED])


def _unique(name: str) -> ir.FieldSpec:
    return ir.FieldSpec(name=name, type=ir.FieldType(kind=ir.FieldTypeKind.STR),
                        modifiers=[ir.FieldModifier.REQUIRED, ir.FieldModifier.UNIQUE])


def _md(entities, tenant_scoped):
    conv = convert_entities(entities)
    return build_metadata(conv, partition_key="tenant_id", tenant_scoped=tenant_scoped)


def test_unique_tenant_id_id_emitted() -> None:
    md = _md([_e("Workspace"), _e("Task", _tid())], {"Task"})
    task = md.tables["Task"]
    ucs = [c for c in task.constraints if c.__class__.__name__ == "UniqueConstraint"]
    assert any({col.name for col in uc.columns} == {"tenant_id", "id"} for uc in ucs)


def test_intra_tenant_ref_is_composite_fk() -> None:
    ents = [_e("Workspace"), _e("Project", _tid()), _e("Task", _tid(), _ref("project", "Project"))]
    md = _md(ents, {"Project", "Task"})
    task = md.tables["Task"]
    composite = [fk for fk in task.foreign_key_constraints if len(fk.elements) == 2]
    cols = {tuple(e.parent.name for e in fk.elements) for fk in composite}
    assert ("tenant_id", "project") in cols
    # the single-column FK on `project` is suppressed (only the composite remains)
    single = [fk for fk in task.foreign_key_constraints
              if len(fk.elements) == 1 and fk.elements[0].parent.name == "project"]
    assert not single


def test_ref_to_global_entity_stays_single_column() -> None:
    ents = [_e("Workspace"), _e("Currency"), _e("Task", _tid(), _ref("currency", "Currency"))]
    md = _md(ents, {"Task"})  # Currency NOT tenant-scoped
    task = md.tables["Task"]
    single = [fk for fk in task.foreign_key_constraints
              if len(fk.elements) == 1 and fk.elements[0].parent.name == "currency"]
    assert single


def test_author_unique_is_tenant_scoped() -> None:
    md = _md([_e("Workspace"), _e("Member", _tid(), _unique("email"))], {"Member"})
    member = md.tables["Member"]
    # the email column is NOT globally unique; a (tenant_id, email) unique exists
    assert not member.c.email.unique
    ucs = [c for c in member.constraints if c.__class__.__name__ == "UniqueConstraint"]
    assert any({col.name for col in uc.columns} == {"tenant_id", "email"} for uc in ucs)


def test_tenant_id_leading_index() -> None:
    md = _md([_e("Workspace"), _e("Task", _tid())], {"Task"})
    task = md.tables["Task"]
    assert any(list(ix.columns)[0].name == "tenant_id" for ix in task.indexes)


def test_non_tenant_app_unchanged() -> None:
    # partition_key/tenant_scoped omitted → identical to today's output.
    md = build_metadata(convert_entities([_e("Thing", _unique("sku"))]))
    thing = md.tables["Thing"]
    assert thing.c.sku.unique  # global uniqueness preserved when not tenant-scoped
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_sa_schema_tenant_constraints.py -v`
Expected: FAIL — `build_metadata` does not accept `partition_key`/`tenant_scoped`. (Before implementing, read `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/sa_schema.py:149-197` (`_field_to_column`) and `:336-432` (`build_metadata`) and `/Volumes/SSD/Dazzle/src/dazzle/http/converters/entity_converter.py` to confirm the converted-entity field/modifier accessors — the converted entities feed `build_metadata`, so the construction logic reads the *converted* field shapes, not raw IR. Adjust attribute access to match `convert_entities` output.)

- [ ] **Step 3: Implement the construction rules**

In `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/sa_schema.py`:

(a) Change `_field_to_column` (line 149) to accept `suppress_fk: bool = False` and skip building `fk_args` when `suppress_fk` is True (the composite FK is added at table level instead). Also stop setting `kwargs["unique"] = True` when the caller will tenant-scope it — add a `suppress_unique: bool = False` param that skips the column-level `unique`.

(b) Change `build_metadata` (line ~336) signature to:

```python
def build_metadata(
    entities,
    surfaces=None,
    *,
    partition_key: str | None = None,
    tenant_scoped: set[str] | None = None,
):
```

(c) In the per-entity loop (line 371), when `partition_key and entity.name in (tenant_scoped or set())`:
   - Compute the set of ref fields on this entity whose target is also in `tenant_scoped` → these become composite FKs; pass `suppress_fk=True` for those columns and `suppress_unique=True` for any author-unique column.
   - After building `columns`, append table args:
     - `sa.UniqueConstraint(partition_key, "id", name=f"uq_{entity.name}_{partition_key}_id")`
     - For each composite ref field `f`: `sa.ForeignKeyConstraint([partition_key, f.name], [f"{target}.{partition_key}", f"{target}.id"], name=f"fk_{entity.name}_{f.name}")`
     - For each author-unique field `u`: `sa.UniqueConstraint(partition_key, u.name, name=f"uq_{entity.name}_{partition_key}_{u.name}")`
     - `sa.Index(f"ix_{entity.name}_{partition_key}", partition_key, "id")`
   - Pass these as extra positional args to `sa.Table(entity.name, metadata, *columns, *index_args, *tenant_args)`.

Keep the non-tenant path (when `partition_key is None` or entity not scoped) **byte-identical** to today (the `test_non_tenant_app_unchanged` guard pins this). Write small private helpers (`_tenant_table_args(entity, partition_key, tenant_scoped)`) to keep the loop readable; do not inflate the loop body.

- [ ] **Step 4: Thread tenancy into the call sites**

`/Volumes/SSD/Dazzle/src/dazzle/http/alembic/metadata_loader.py` — change the final call to:

```python
    tenancy = appspec.tenancy
    if tenancy is not None and tenancy.isolation.mode == ir.TenancyMode.SHARED_SCHEMA:
        pk = tenancy.isolation.partition_key
        scoped = {e.name for e in appspec.domain.entities if any(f.name == pk for f in e.fields)}
        return build_metadata(entities, surfaces=list(appspec.surfaces),
                              partition_key=pk, tenant_scoped=scoped)
    return build_metadata(entities, surfaces=list(appspec.surfaces))
```

`/Volumes/SSD/Dazzle/src/dazzle/http/runtime/server.py` — apply the same branch at both `build_metadata(self._entities, surfaces=...)` call sites (`_setup_database` ~line 720 and `_migrate_tenant_schemas` ~line 628), deriving `partition_key`/`tenant_scoped` from `self._appspec.tenancy`. Factor a small helper `_tenancy_metadata_kwargs(appspec)` to avoid duplicating the branch.

- [ ] **Step 5: Run the tests + the broader schema/runtime unit slice**

Run: `pytest tests/unit/test_sa_schema_tenant_constraints.py tests/unit/ -k "sa_schema or metadata or schema_gen or invoice_ops" -v`
Expected: PASS. The `tenant_scoped` derivation (entity has the partition_key field) covers both framework-injected and hand-declared (invoice_ops) cases.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/http/runtime/sa_schema.py src/dazzle/http/alembic/metadata_loader.py src/dazzle/http/runtime/server.py tests/unit/test_sa_schema_tenant_constraints.py
git commit -m "feat(schema): tenant-scoped constraints (composite FK, UNIQUE(tenant_id,id), scoped uniqueness, index) (RLS Phase A)"
```

---

## Task 3: Real-Postgres constraint verification

**Files:**
- Create: `/Volumes/SSD/Dazzle/fixtures/tenant_rls/` (DSL fixture, no hand-declared `tenant_id`)
- Create: `/Volumes/SSD/Dazzle/tests/integration/test_tenant_rls_constraints_pg.py`

- [ ] **Step 1: Create the fixture**

Model `/Volumes/SSD/Dazzle/fixtures/tenant_rls/` on `/Volumes/SSD/Dazzle/fixtures/scope_runtime/` (a `dazzle.toml` + `dsl/` dir). The DSL declares a `tenancy: mode: shared_schema` block and a tenant entity + descendants **without** hand-declaring `tenant_id` (so the test exercises framework injection):

```dsl
# dsl/app.dsl
module tenant_rls
app tenant_rls "Tenant RLS fixture"

tenancy:
  mode: shared_schema
  partition_key: tenant_id

entity Workspace "Workspace":
  archetype: tenant
  id: uuid pk
  name: str(100) required

entity Project "Project":
  id: uuid pk
  name: str(100) required

entity Member "Member":
  id: uuid pk
  email: str(200) required unique   # becomes UNIQUE(tenant_id, email)
```

(Confirm the exact archetype/tenancy DSL syntax against `/Volumes/SSD/Dazzle/examples/invoice_ops/dsl/` and `/Volumes/SSD/Dazzle/examples/support_tickets/dsl/runtime.dsl`. Add a `ref` from Project→Workspace only if the injector doesn't already supply `tenant_id`; the point is to NOT hand-declare `tenant_id`.) Run `dazzle validate` in the fixture dir to confirm it parses clean before writing the test.

- [ ] **Step 2: Write the integration test**

Create `/Volumes/SSD/Dazzle/tests/integration/test_tenant_rls_constraints_pg.py` (mirror the markers/skip-gating of `/Volumes/SSD/Dazzle/tests/integration/test_tenant_is_test_pg.py`):

```python
"""Real-PG verification of Phase-A tenant construction rules.

Builds the fixture's metadata, create_all()s it on a disposable database, and
asserts the engine-level guarantees the construction rules buy — WITHOUT RLS
(that's Phase B): composite FKs forbid cross-tenant references, and uniqueness
is tenant-scoped.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.fixture
def engine():
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    eng = sa.create_engine(_PG_URL.replace("postgresql://", "postgresql+psycopg://"), future=True)
    yield eng
    eng.dispose()


def _build_fixture_metadata():
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.sa_schema import build_metadata
    from dazzle.core import ir

    appspec = load_project_appspec(Path("fixtures/tenant_rls"))
    pk = appspec.tenancy.isolation.partition_key
    scoped = {e.name for e in appspec.domain.entities if any(f.name == pk for f in e.fields)}
    md = build_metadata(convert_entities(appspec.domain.entities),
                        partition_key=pk, tenant_scoped=scoped)
    return md, pk


def test_composite_fk_rejects_cross_tenant_reference(engine) -> None:
    md, pk = _build_fixture_metadata()
    prefix = f"rls_{uuid.uuid4().hex[:8]}_"
    # Namespace tables to avoid clobbering anything in the scratch DB.
    # (Implementer: create_all into a fresh disposable schema/db; see test_tenant_is_test_pg.py
    # for the disposable-DB pattern. Assert: inserting a Project in tenant A and a Member
    # in tenant B that references that Project fails with a foreign-key violation.)
    ...


def test_uniqueness_is_tenant_scoped(engine) -> None:
    # Two tenants may both have a Member with email alice@example.com;
    # one tenant inserting it twice violates UNIQUE(tenant_id, email).
    ...
```

> **Implementer:** flesh out the two test bodies using the disposable-DB pattern from `/Volumes/SSD/Dazzle/tests/integration/test_tenant_is_test_pg.py` (create a scratch DB, `metadata.create_all(engine)`, raw inserts with explicit `tenant_id` values — no runtime context needed since RLS isn't in this phase, insert the parent rows directly). The two assertions are the Phase-A engine guarantees: (1) cross-tenant composite-FK reference raises `ForeignKeyViolation`; (2) same `(tenant_id, email)` twice raises `UniqueViolation`, but the same email under two different `tenant_id`s succeeds. Always drop the scratch DB in a `finally`.

- [ ] **Step 3: Verify against a local scratch DB**

```bash
createdb dazzle_rls_scratch
TEST_DATABASE_URL="postgresql://localhost/dazzle_rls_scratch" pytest tests/integration/test_tenant_rls_constraints_pg.py -v -m postgres
dropdb dazzle_rls_scratch
```
Expected: tests PASS (both constraint guarantees hold against real PG). If a test fails, investigate the real cause — do not weaken assertions.

- [ ] **Step 4: Commit**

```bash
git add fixtures/tenant_rls/ tests/integration/test_tenant_rls_constraints_pg.py
git commit -m "test(tenancy): real-PG verification of Phase-A construction rules (composite FK + scoped uniqueness)"
```

---

## Task 4: Docs, changelog, ship

**Files:** `/Volumes/SSD/Dazzle/CHANGELOG.md` (+ a short note in `/Volumes/SSD/Dazzle/docs/reference/` tenancy docs if one exists)

- [ ] **Step 1: Docs**

If a tenancy reference doc exists under `/Volumes/SSD/Dazzle/docs/reference/`, add a paragraph: under `tenancy: mode: shared_schema`, the `partition_key` (`tenant_id`) column is now **framework-injected** on every tenant-scoped entity (authors no longer hand-declare it; `entities_excluded` opts out); intra-tenant FKs are composite and uniqueness is tenant-scoped. Note RLS enforcement is Phase B. If no such doc exists, skip (CHANGELOG Agent Guidance covers it).

- [ ] **Step 2: CHANGELOG**

Add a new version section at the top of `/Volumes/SSD/Dazzle/CHANGELOG.md` (above `[Unreleased]`'s content rules — follow the existing pattern). Content:

```markdown
### Added
- **RLS-backed row tenancy — Phase A (discriminator substrate)** (ADR-0034, spec `docs/superpowers/specs/2026-06-04-rls-tenancy-design.md`). Under `tenancy: mode: shared_schema`, the `partition_key` (`tenant_id`) is now **framework-injected** as a uniform `ref <TenantEntity> required` on every tenant-scoped entity (the archetype's per-app-named injection is replaced); `tenancy.entities_excluded` opts an entity out. Generated schemas now emit `UNIQUE(tenant_id, id)`, **composite intra-tenant FKs** `(tenant_id, fk) → parent(tenant_id, id)` (closing the FK-integrity-bypasses-RLS hole ahead of Phase B), tenant-scoped uniqueness (`UNIQUE(tenant_id, <key>)`), and a `tenant_id`-leading index. Greenfield only — existing deployed schemas are not migrated.

### Agent Guidance
- Do **not** hand-declare `tenant_id` on entities in a `shared_schema` app — the framework injects it. Use `tenancy.entities_excluded` to opt out reference/global tables. The tenant identity is the declared `archetype: tenant` entity; `public.tenants` (1:1 registry) and RLS enforcement land in later phases.
- Uniqueness on tenant-scoped entities is **per-tenant** by construction (`UNIQUE(tenant_id, …)`); a bare `unique` field is no longer globally unique in `shared_schema` apps.
```

- [ ] **Step 3: Full pre-ship gate** (per saved memory `feedback_pre_ship_test_scope` + `feedback_pre_ship_mypy_scope`)

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
mypy src/dazzle
pytest tests/ -m "not e2e"
```
Expected: all green. Pay attention to discovery/drift tests (`test_examples_*`, `test_docs_drift`, `test_api_surface_drift`) — the injection changes generated schemas for `invoice_ops`/`support_tickets`; if a golden/snapshot test for those examples changes, that is expected — update the snapshot deliberately and note it. (Known unrelated flake: `test_retention_loop.py::...test_dedupes_within_same_minute`.)

- [ ] **Step 4: Bump + commit**

Run `/bump patch`; update the CHANGELOG header to the bumped version; `git commit -m "docs(changelog): RLS tenancy Phase A -- vX.Y.Z"`.

---

## Final integration & ship

- [ ] **Independent review** — dispatch a fresh `feature-dev:code-reviewer` over the whole Phase-A diff, with **adversarial focus on the construction rules** (does the composite-FK + tenant-scoped-uniqueness generation actually hold for multi-hop FK chains, self-refs, and circular refs? does the non-tenant path stay byte-identical? are there example apps whose generated schema silently changed?). Address high-confidence findings via `superpowers:receiving-code-review` (verify before implementing — a suggestion that breaks the circular-ref/`use_alter` path or the non-tenant path is wrong).
- [ ] **Confirm green + clean** — `pytest tests/ -m "not e2e"` green, mypy + ruff clean, `git status` clean.
- [ ] **FF-merge to main + push** — mirror the Slice-0 sequence; confirm each step's exit status before the next (`feedback_commit_before_tag_push`).
- [ ] **Update memory** `project_tenant_lifecycle.md` (or a new `project_rls_tenancy.md`): Phase A shipped; the discriminator is framework-injected under `shared_schema`; construction rules emitted; Phase B (RLS policies + runtime context + roles) next.

---

## Self-Review notes (planner)

- **Spec coverage:** spec §3.1 (reuse existing layer) → Task 1 reuses `TenancySpec`/`entities_excluded`/`partition_key`. Companion §1.1 `UNIQUE(tenant_id,id)`, §4.1 composite FKs, §4.2 tenant-scoped uniqueness, §5 leading index → Task 2. Greenfield (§10) → no backfill anywhere. RLS/roles/context (companion §1.2-1.4/§3/§6) → explicitly deferred to Phase B.
- **Deliberate deferrals (not gaps):** RLS policies, `set_config` context, three-role model, auth-store tenant-scoping, `public.tenants` 1:1 linkage, `app`-schema move. Each named in Context as out-of-scope.
- **Type consistency:** `inject_partition_key(entities, tenancy)`; `build_metadata(entities, surfaces=None, *, partition_key=None, tenant_scoped=None)`; `_field_to_column(..., suppress_fk=False, suppress_unique=False)`; partition_key string default `"tenant_id"`. Used consistently across Tasks 1-3.
- **Risk flagged for execution:** removing the Stage-5 archetype injection may change generated schemas for existing example apps — Task 1 Step 7 and the final review explicitly watch for this; greenfield policy permits the break but it must be surfaced, not silent.
```
