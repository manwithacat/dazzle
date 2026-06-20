# Auth Plan 3c — `archetype: profile`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `archetype: profile` DSL construct so an app author can declare per-member application data (e.g. `display_name`, `avatar`) that the framework links 1:1 to a membership — keyed by `(tenant_id, identity_id)` — without the author hand-wiring the linkage.

**Architecture:** A profile is a normal **tenant-scoped domain entity** (it gets the framework `tenant_id` injected by tenancy Phase A). The archetype expander injects an `identity_id` (uuid) column marked `unique`, which the schema generator rewrites to a tenant-scoped `UNIQUE(tenant_id, identity_id)` — so each member has exactly one profile per org, matching the membership's natural key. No cross-world FK (membership lives in the auth-store raw-SQL world); the link is by shared key. An `is_profile` flag rides the IR → back EntitySpec (mirroring `is_tenant_root`) so a future runtime can resolve "the current member's profile" by `(active_membership.tenant_id, current_user.id)`.

**Tech Stack:** Python 3.12, the IR/parser/linker (`src/dazzle/core/`), the back converter + `sa_schema` (`src/dazzle/http/`), Alembic not involved (profile is a DSL/domain entity, schema via `build_metadata`), pytest. **Staged IR-first** (project pattern): 3c ships the DSL + IR + expander + converter + schema; the runtime profile-resolution route/surface is a follow-on.

**Spec:** `docs/superpowers/specs/2026-06-05-auth-identity-model-design.md` §7 (Tier 1) + §10 (the profile↔membership linkage open question — **resolved here as keyed-by-`(tenant_id, identity_id)`**). Slice **3c** of Plan 3 (3a invitations v0.81.41, 3b member-admin v0.81.42 shipped). The `tenancy: multi_org:` flag is deferred to **3c.ii**.

**Decisions (confirmed):** `archetype: profile` first (defer `multi_org:`); linkage = `(tenant_id, identity_id)`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/dazzle/core/ir/archetype.py` (**modify**) | Add `PROFILE = "profile"` to `ArchetypeKind`. |
| `src/dazzle/core/ir/domain.py` (**modify**) | Add `is_profile: bool = False` to `EntitySpec`. |
| `src/dazzle/core/dsl_parser_impl/entity.py` (**modify**) | Map the `"profile"` archetype keyword → `ArchetypeKind.PROFILE`. |
| `src/dazzle/core/archetype_expander.py` (**modify**) | `_expand_profile_archetype` (inject `identity_id` uuid required unique; set `is_profile=True`) + dispatch. |
| `src/dazzle/core/validator.py` (**modify**) | Validate `archetype: profile` requires `tenancy: mode: shared_schema` (else no `tenant_id` → the `(tenant_id, identity_id)` key is broken). |
| `src/dazzle/http/specs/entity.py` (**modify**) | Add `is_profile: bool` to the back `EntitySpec`. |
| `src/dazzle/http/converters/entity_converter.py` (**modify**) | Pass `is_profile` through `convert_entity`. |
| `fixtures/tenant_rls/dsl/entities.dsl` (**modify**) | Add a `MemberProfile` profile entity to exercise it end-to-end. |
| `docs/reference/grammar.md` (**modify**) | Document the `profile` archetype kind + the `(tenant_id, identity_id)` linkage. |
| `tests/unit/test_archetype_profile.py` (**create**) | Parser (profile→PROFILE+is_profile), expander (identity_id injected, unique), converter passthrough, validation. |
| `tests/integration/test_profile_schema_pg.py` (**create**) | Real-PG: the profile table has `tenant_id` + `identity_id` + `UNIQUE(tenant_id, identity_id)`. |

---

## Task 1: IR — `ArchetypeKind.PROFILE` + `EntitySpec.is_profile`

**Files:**
- Modify: `src/dazzle/core/ir/archetype.py` (`ArchetypeKind` enum ~line 36)
- Modify: `src/dazzle/core/ir/domain.py` (`EntitySpec` ~line 394)
- Test: `tests/unit/test_archetype_profile.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_archetype_profile.py
"""archetype: profile — IR + parser + expander + converter + validation (Plan 3c)."""

from dazzle.core import ir


def test_archetype_kind_has_profile() -> None:
    assert ir.ArchetypeKind.PROFILE == "profile"


def test_entityspec_has_is_profile_default_false() -> None:
    e = ir.EntitySpec(name="X", display_name="X")
    assert e.is_profile is False
```

(If `EntitySpec(name=, display_name=)` isn't the minimal constructor, match the one other tests use — check `tests/unit/test_archetype_expander.py` for the canonical `EntitySpec(...)` call shape.)

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_archetype_profile.py -q`
Expected: FAIL — `AttributeError: PROFILE` / `is_profile`.

- [ ] **Step 3: Add `PROFILE`** to `ArchetypeKind` (`archetype.py`, after `USER_MEMBERSHIP`):

```python
    USER_MEMBERSHIP = "user_membership"
    PROFILE = "profile"  # auth Plan 3c — per-member app data linked to the membership
```

And update the enum's docstring to mention `PROFILE: Per-member profile data (1:1 with a membership, keyed by (tenant_id, identity_id))`.

- [ ] **Step 4: Add `is_profile`** to `EntitySpec` (`domain.py`, after `is_tenant_root`):

```python
    is_tenant_root: bool = False
    is_profile: bool = False  # auth Plan 3c — archetype: profile (per-member data)
```

Add to the class docstring's attribute list: `is_profile: Whether entity is per-member profile data (Plan 3c)`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/unit/test_archetype_profile.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
ruff check src/dazzle/core/ir/archetype.py src/dazzle/core/ir/domain.py tests/unit/test_archetype_profile.py --fix
ruff format src/dazzle/core/ir/archetype.py src/dazzle/core/ir/domain.py tests/unit/test_archetype_profile.py
git add src/dazzle/core/ir/archetype.py src/dazzle/core/ir/domain.py tests/unit/test_archetype_profile.py
git commit -m "feat(ir): ArchetypeKind.PROFILE + EntitySpec.is_profile (Plan 3c)"
```

**Note:** if `tests/unit/test_api_surface_drift.py` (ir-types baseline) or the IR-reader-parity test (`tests/unit/fixtures/ir_reader_baseline.json`) flags the new field, regenerate per its `--write`/baseline mechanism and add a CHANGELOG note (a new EntitySpec field is a benign IR-surface addition).

---

## Task 2: Parser — `"profile"` keyword → `ArchetypeKind.PROFILE`

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/entity.py` (~line 1131 keyword map)
- Test: `tests/unit/test_archetype_profile.py`

- [ ] **Step 1: Write the failing test**

```python
def test_parser_maps_profile_keyword(tmp_path) -> None:
    from dazzle.core.parser import parse_dsl  # match the parser entrypoint other tests use

    src = """
module m
app a "A"

tenancy:
  mode: shared_schema
  partition_key: tenant_id

entity Workspace "Workspace":
  archetype: tenant
  id: uuid pk
  name: str(100) required

entity MemberProfile "Member Profile":
  archetype: profile
  id: uuid pk
  display_name: str(120)
"""
    appspec = parse_dsl(src)  # adapt to the real entrypoint (parse_string / Parser().parse)
    prof = next(e for e in appspec.domain.entities if e.name == "MemberProfile")
    from dazzle.core import ir

    assert prof.archetype_kind == ir.ArchetypeKind.PROFILE
```

**Adapt the parse entrypoint** to whatever `tests/unit/test_parser.py` / `test_archetype_expander.py` actually call (e.g. `Parser().parse(...)`, `parse_string(...)`, or `load_project_appspec`). Read one of those tests first and mirror it.

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_archetype_profile.py::test_parser_maps_profile_keyword -q`
Expected: FAIL — `archetype_kind` is `CUSTOM` (unknown keyword falls through), not `PROFILE`.

- [ ] **Step 3: Add the keyword** to the archetype map (`entity.py` ~line 1131):

```python
            "user_membership": ir.ArchetypeKind.USER_MEMBERSHIP,
            "profile": ir.ArchetypeKind.PROFILE,
```

- [ ] **Step 4: Run the test to verify it passes** — PASS.

- [ ] **Step 5: Commit**

```bash
ruff check src/dazzle/core/dsl_parser_impl/entity.py tests/unit/test_archetype_profile.py --fix
ruff format src/dazzle/core/dsl_parser_impl/entity.py tests/unit/test_archetype_profile.py
git add src/dazzle/core/dsl_parser_impl/entity.py tests/unit/test_archetype_profile.py
git commit -m "feat(parser): archetype: profile keyword → ArchetypeKind.PROFILE (Plan 3c)"
```

---

## Task 3: Expander — inject `identity_id` + set `is_profile`

**Files:**
- Modify: `src/dazzle/core/archetype_expander.py` (dispatch ~line 367 + new `_expand_profile_archetype`)
- Test: `tests/unit/test_archetype_profile.py`

- [ ] **Step 1: Write the failing test**

```python
def test_expander_injects_identity_id_and_sets_is_profile() -> None:
    from dazzle.core import ir
    from dazzle.core.archetype_expander import _expand_profile_archetype

    entity = ir.EntitySpec(
        name="MemberProfile",
        display_name="Member Profile",
        archetype_kind=ir.ArchetypeKind.PROFILE,
        fields=[
            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                         modifiers=[ir.FieldModifier.PRIMARY_KEY]),
            ir.FieldSpec(name="display_name", type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=120)),
        ],
    )
    expanded = _expand_profile_archetype(entity)
    assert expanded.is_profile is True
    idf = next(f for f in expanded.fields if f.name == "identity_id")
    assert idf.type.kind == ir.FieldTypeKind.UUID
    assert idf.is_required is True
    assert idf.is_unique is True  # → tenant-scoped UNIQUE(tenant_id, identity_id)
```

(Match `FieldModifier.PRIMARY_KEY` to the real enum member name — check `fields.py`; it may be `PK`/`PRIMARY_KEY`.)

- [ ] **Step 2: Run it to verify it fails** — `ImportError: _expand_profile_archetype`.

- [ ] **Step 3: Add the expander + dispatch.** In `archetype_expander.py`, add to the dispatch in `_apply_semantic_archetype` (the `elif entity.archetype_kind == ir.ArchetypeKind.TENANT:` chain ~line 367):

```python
    elif entity.archetype_kind == ir.ArchetypeKind.PROFILE:
        return _expand_profile_archetype(entity)
```

And the function (near `_expand_tenant_archetype`):

```python
def _expand_profile_archetype(entity: ir.EntitySpec) -> ir.EntitySpec:
    """Expand the profile archetype (auth Plan 3c).

    A profile holds per-member app data linked 1:1 to a membership. It stays a
    normal tenant-scoped entity (tenancy Phase A injects ``tenant_id``); here we
    inject the ``identity_id`` (the auth identity's id — NOT an IR ``ref``, since
    identity lives in the auth-store) marked ``unique`` so the schema generator
    rewrites it to a tenant-scoped ``UNIQUE(tenant_id, identity_id)`` — one
    profile per member per org. The ``is_profile`` flag rides to the back
    EntitySpec so the runtime can resolve the current member's profile.
    """
    existing = {f.name for f in entity.fields}
    new_fields = list(entity.fields)
    if "identity_id" not in existing:
        new_fields.append(
            ir.FieldSpec(
                name="identity_id",
                type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                modifiers=[ir.FieldModifier.REQUIRED, ir.FieldModifier.UNIQUE],
            )
        )
    return entity.model_copy(update={"is_profile": True, "fields": new_fields})
```

- [ ] **Step 4: Run the test to verify it passes** — PASS.

- [ ] **Step 5: Commit**

```bash
ruff check src/dazzle/core/archetype_expander.py tests/unit/test_archetype_profile.py --fix
ruff format src/dazzle/core/archetype_expander.py tests/unit/test_archetype_profile.py
git add src/dazzle/core/archetype_expander.py tests/unit/test_archetype_profile.py
git commit -m "feat(archetype): _expand_profile_archetype injects identity_id + tenant-scoped unique (Plan 3c)"
```

---

## Task 4: Validation — profile requires `shared_schema`

**Files:**
- Modify: `src/dazzle/core/validator.py`
- Test: `tests/unit/test_archetype_profile.py`

- [ ] **Step 1: Write the failing test** — a `archetype: profile` app WITHOUT `tenancy: mode: shared_schema` must fail validation with a clear message (no `tenant_id` → the `(tenant_id, identity_id)` key can't exist).

```python
def test_profile_without_shared_schema_is_a_validation_error() -> None:
    from dazzle.core.parser import parse_dsl  # adapt entrypoint
    from dazzle.core.validator import validate_appspec  # adapt to real validator entrypoint

    src = """
module m
app a "A"

entity MemberProfile "Member Profile":
  archetype: profile
  id: uuid pk
  display_name: str(120)
"""
    appspec = parse_dsl(src)
    errors = validate_appspec(appspec)  # adapt: returns list[str] / raises / ValidationResult
    assert any("profile" in str(e).lower() and "shared_schema" in str(e).lower() for e in errors)
```

**Adapt** to the real validator entrypoint + result shape — read `validator.py`'s public function (e.g. `validate(appspec) -> list[ValidationError]`) and how `tests/unit/test_validator*.py` assert errors. Mirror exactly.

- [ ] **Step 2: Run it to verify it fails** (no such validation yet).

- [ ] **Step 3: Add the validation** — in `validator.py`, where entity-level checks run, add: if any entity has `archetype_kind == ArchetypeKind.PROFILE` (or `is_profile`) and `tenancy is None or tenancy.isolation.mode != TenancyMode.SHARED_SCHEMA`, emit an error: `"entity '<name>': archetype: profile requires tenancy: mode: shared_schema (the profile is keyed by (tenant_id, identity_id))"`. Use the validator's existing error-append idiom.

- [ ] **Step 4: Run the test to verify it passes** — PASS. Also run the broad validator suite to confirm no false positives on existing apps: `python -m pytest tests/unit/test_validator*.py -q`.

- [ ] **Step 5: Commit**

```bash
ruff check src/dazzle/core/validator.py tests/unit/test_archetype_profile.py --fix
ruff format src/dazzle/core/validator.py tests/unit/test_archetype_profile.py
git add src/dazzle/core/validator.py tests/unit/test_archetype_profile.py
git commit -m "feat(validator): archetype: profile requires shared_schema tenancy (Plan 3c)"
```

---

## Task 5: Converter — carry `is_profile` to the back EntitySpec

**Files:**
- Modify: `src/dazzle/http/specs/entity.py` (~line 648, near `is_tenant_root`)
- Modify: `src/dazzle/http/converters/entity_converter.py` (~line 795)
- Test: `tests/unit/test_archetype_profile.py`

- [ ] **Step 1: Write the failing test**

```python
def test_is_profile_survives_conversion_and_identity_id_is_present() -> None:
    from pathlib import Path

    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.core.appspec_loader import load_project_appspec

    app = load_project_appspec(Path("fixtures/tenant_rls"))  # after Task 6 adds MemberProfile
    prof = next(e for e in convert_entities(app.domain.entities) if e.name == "MemberProfile")
    assert prof.is_profile is True
    field_names = {f.name for f in prof.fields}
    assert "identity_id" in field_names and "tenant_id" in field_names
```

(This test depends on Task 6's fixture; order Task 6 before running it, or use a synthetic appspec.)

- [ ] **Step 2: Add `is_profile` to the back `EntitySpec`** (`back/specs/entity.py`, near `is_tenant_root`):

```python
    is_profile: bool = Field(default=False, description="archetype: profile (per-member data, Plan 3c)")
```

- [ ] **Step 3: Pass it through `convert_entity`** (`entity_converter.py:795`, next to `is_tenant_root=...`):

```python
        is_tenant_root=dazzle_entity.is_tenant_root,  # v0.10.3
        is_profile=dazzle_entity.is_profile,  # auth Plan 3c
```

- [ ] **Step 4: Run the test** (after Task 6) — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/specs/entity.py src/dazzle/http/converters/entity_converter.py tests/unit/test_archetype_profile.py
git commit -m "feat(converter): carry is_profile to the back EntitySpec (Plan 3c)"
```

---

## Task 6: Fixture + real-PG schema proof

**Files:**
- Modify: `fixtures/tenant_rls/dsl/entities.dsl`
- Create: `tests/integration/test_profile_schema_pg.py`

- [ ] **Step 1: Add a profile entity** to `fixtures/tenant_rls/dsl/entities.dsl`:

```dsl
entity MemberProfile "Member Profile":
  archetype: profile
  intent: "Per-member profile data (display name), linked 1:1 to a membership"

  id: uuid pk
  display_name: str(120)
```

- [ ] **Step 2: Confirm it validates** — `cd fixtures/tenant_rls && dazzle validate` (exit 0; the fixture is `shared_schema`, so the Task 4 validation passes). Run the broader fixture-consuming tests that load `tenant_rls` (`tests/integration/test_membership_rls_activation_pg.py` etc.) — they should still pass with the extra entity.

- [ ] **Step 3: Write the schema integration test**

```python
# tests/integration/test_profile_schema_pg.py
"""archetype: profile generates a (tenant_id, identity_id)-keyed table (Plan 3c)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]


def test_profile_table_has_tenant_identity_unique() -> None:
    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.sa_schema import build_metadata, scoped_entity_names
    from dazzle.core.appspec_loader import load_project_appspec

    app = load_project_appspec(Path("fixtures/tenant_rls"))
    pk = app.tenancy.isolation.partition_key
    scoped = sorted(scoped_entity_names(app.domain.entities, pk))
    md = build_metadata(convert_entities(app.domain.entities), partition_key=pk, tenant_scoped=scoped)

    t = md.tables["MemberProfile"]
    cols = {c.name for c in t.columns}
    assert {"id", "tenant_id", "identity_id", "display_name"} <= cols
    # MemberProfile is tenant-scoped (carries the injected tenant_id).
    assert "MemberProfile" in scoped
    # The (tenant_id, identity_id) tenant-scoped unique exists.
    uniques = [
        tuple(c.name for c in con.columns)
        for con in t.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    ]
    assert any(set(u) == {"tenant_id", "identity_id"} for u in uniques), uniques
```

(No DB needed for `build_metadata`, but kept under `e2e`/`postgres` markers alongside the other tenant_rls schema tests; if it needs no PG it can be a unit test — your call, match the nearest sibling.)

- [ ] **Step 4: Run + commit**

```bash
TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_profile_schema_pg.py tests/unit/test_archetype_profile.py -q
git add fixtures/tenant_rls/dsl/entities.dsl tests/integration/test_profile_schema_pg.py tests/unit/test_archetype_profile.py
git commit -m "feat(fixture): tenant_rls MemberProfile + profile schema proof (Plan 3c)"
```

---

## Task 7: Docs + full verification

- [ ] **Step 1: Document** the `profile` archetype in `docs/reference/grammar.md` (mirror the existing archetype-kind docs): `archetype: profile` — per-member data, 1:1 with a membership, keyed by the framework-injected `(tenant_id, identity_id)`; requires `shared_schema`. If the archetype kinds are listed in CLAUDE.md or an ADR, add `profile` there too.
- [ ] **Step 2:** `mypy src/dazzle` (clean — the new `is_profile` fields + expander).
- [ ] **Step 3:** `python -m pytest tests/ -m "not e2e" -q` — full unit slice. Watch: `test_archetype_expander.py` (dispatch grew), `test_api_surface_drift.py` (ir-types — regenerate if the new field is pinned), the IR-reader-parity baseline (regenerate via its mechanism if `is_profile` is read), `test_docs_drift.py` (grammar/construct list), `test_examples_*` (the fixture changed).
- [ ] **Step 4:** Regenerate any drift baselines with the documented `--write`, add a CHANGELOG note, and re-run. Commit fixes.

---

## Task 8: Adversarial review checkpoint

- [ ] **Dispatch an independent reviewer** (correctness-focused — this is IR/schema, lower security surface, but the linkage is the load-bearing invariant):
  - **Linkage correctness:** does `identity_id` actually become a tenant-scoped `UNIQUE(tenant_id, identity_id)` (not a global unique on identity_id alone, which would forbid the same person having a profile in two orgs)? Confirm `_tenant_unique_fields` rewrites it AND drops the column-level unique.
  - **tenancy_inject interaction:** does a PROFILE entity get `tenant_id` injected (it must — confirm it's not in the skip list)? Does the expander-injected `identity_id` (added before `inject_partition_key` runs) survive?
  - **Validation:** is the `shared_schema` requirement enforced (a profile without it would have no `tenant_id` → a broken/global unique on `identity_id`)? Any false positive on non-profile apps?
  - **Converter:** `is_profile` reaches the back EntitySpec; `identity_id` is a plain uuid column (NOT a `ref` — so the FK graph / scope validation doesn't try to resolve a non-existent identity entity)?
  - **No regression:** existing archetypes (tenant/user/settings) unchanged; the `tenant_rls` fixture + its RLS/membership tests still pass with the new entity.

- [ ] **Fix any findings; re-run. Commit.**

---

## Task 9: CHANGELOG + ship

- [ ] CHANGELOG `### Added`: `archetype: profile` — per-member data linked 1:1 to a membership by the framework-injected `(tenant_id, identity_id)` tenant-scoped unique; `is_profile` rides to the back EntitySpec; requires `shared_schema`; runtime resolution (a `/me/profile` route/surface) is a follow-on. `### Agent Guidance`: declare per-member app data with `archetype: profile`; the framework injects `identity_id` + `tenant_id` and the `(tenant_id, identity_id)` unique — don't hand-declare them; resolve the current member's profile by `(active membership tenant, current_user.id)`.
- [ ] `/bump patch`, then `/ship`.

---

## Self-Review

**1. Spec coverage:** `archetype: profile` (§7 Tier 1 + §10) → IR kind + parser + expander ✓. Linkage resolved as `(tenant_id, identity_id)` (the §10 fork) → injected `identity_id` + tenant-scoped unique ✓. Converter wires it (`is_profile`) ✓. Deferred (acknowledged): the runtime profile-resolution route/surface (staged IR-first) and the `tenancy: multi_org:` flag (3c.ii).

**2. Placeholder scan:** code steps are concrete; the explicitly-flagged adapt points (parser/validator entrypoints + `FieldModifier.PRIMARY_KEY` name) are "read the sibling test/enum and mirror," not guesses — resolve them at execution by reading the real symbol.

**3. Type consistency:** `ArchetypeKind.PROFILE` (Task 1) used by parser (Task 2), expander (Task 3), validator (Task 4). `is_profile` added to IR EntitySpec (Task 1) → set by expander (Task 3) → carried by converter (Task 5) → asserted in tests. `identity_id` injected as `FieldType(kind=UUID)` + `[REQUIRED, UNIQUE]` (Task 3) → tenant-scoped unique asserted in the schema test (Task 6).

**Open risks for execution:** (a) drift/IR-reader baselines may need regenerating for the new `is_profile` field (Task 1/7 — documented); (b) the parser/validator entrypoint names must be read from sibling tests, not assumed; (c) confirm `FieldModifier.UNIQUE` on a tenant-scoped entity truly yields `UNIQUE(tenant_id, identity_id)` and not a global unique (Task 6 asserts it — the load-bearing check).
```
