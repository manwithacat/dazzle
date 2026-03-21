# DSL Conformance Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a framework that mechanically derives behavioral test cases from the DSL specification and verifies the runtime enforces them — targeting 100% conformance coverage before deployment.

**Architecture:** Pure-function derivation engine extracts `(entity, persona, operation)` triples from the AppSpec and computes expected behaviors. Fixture engine generates deterministic seed data. pytest plugin boots an in-process FastAPI app against PostgreSQL, seeds fixtures, and runs HTTP assertions via httpx ASGI transport.

**Tech Stack:** pytest (plugin + parametrize), httpx (AsyncClient with ASGITransport), Dazzle AppSpec IR, existing `app_factory.create_app()`, existing `/__test__/authenticate` endpoints.

**Spec:** `docs/superpowers/specs/2026-03-21-conformance-testing-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/dazzle/conformance/__init__.py` | Create | Package init, exports |
| `src/dazzle/conformance/models.py` | Create | `ConformanceCase`, `ConformanceFixtures`, `ScopeOutcome` |
| `src/dazzle/conformance/derivation.py` | Create | `derive_conformance_cases()` — AppSpec → case list |
| `src/dazzle/conformance/fixtures.py` | Create | `generate_fixtures()` — AppSpec → seed data |
| `src/dazzle/conformance/plugin.py` | Create | pytest plugin: collection, app boot, test execution |
| `src/dazzle/conformance/generator.py` | Create | Static TOML generator |
| `src/dazzle/cli/conformance.py` | Create | CLI commands: `dazzle conformance generate`, `dazzle conformance run` |
| `src/dazzle/mcp/server/handlers/conformance.py` | Create | MCP tool: summary, cases, gaps |
| `tests/unit/test_conformance_derivation.py` | Create | Derivation engine tests |
| `tests/unit/test_conformance_fixtures.py` | Create | Fixture engine tests |
| `tests/unit/test_conformance_plugin.py` | Create | Plugin integration tests |

---

### Task 1: Data models — ConformanceCase, ConformanceFixtures, ScopeOutcome

**Files:**
- Create: `src/dazzle/conformance/__init__.py`
- Create: `src/dazzle/conformance/models.py`
- Test: `tests/unit/test_conformance_derivation.py` (initial model tests)

- [ ] **Step 1: Create package and models**

Create `src/dazzle/conformance/__init__.py`:
```python
"""DSL conformance testing framework."""
```

Create `src/dazzle/conformance/models.py`:
```python
"""Data models for conformance testing."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID, uuid5

# Fixed namespace for deterministic UUID generation
CONFORMANCE_NS = UUID("d4zzl3c0-0f0r-4a0c-b3e5-000000000000")


class ScopeOutcome(StrEnum):
    ALL = "all"
    FILTERED = "filtered"
    SCOPE_EXCLUDED = "scope_excluded"
    ACCESS_DENIED = "access_denied"
    FORBIDDEN = "forbidden"
    UNAUTHENTICATED = "unauthenticated"
    UNPROTECTED = "unprotected"


@dataclass
class ConformanceCase:
    entity: str
    persona: str
    operation: str  # list, create, read, update, delete
    expected_status: int
    expected_rows: int | None = None
    row_target: str | None = None  # "own" or "other" for read/update/delete
    description: str = ""
    scope_type: ScopeOutcome = ScopeOutcome.UNPROTECTED

    @property
    def test_id(self) -> str:
        parts = [self.persona, self.operation, self.entity, self.scope_type.value]
        if self.row_target:
            parts.append(self.row_target)
        return "-".join(parts)


@dataclass
class ConformanceFixtures:
    users: dict[str, dict] = field(default_factory=dict)
    entity_rows: dict[str, list[dict]] = field(default_factory=dict)
    junction_rows: dict[str, list[dict]] = field(default_factory=dict)
    expected_counts: dict[tuple[str, str], int] = field(default_factory=dict)


def conformance_uuid(entity: str, purpose: str) -> str:
    """Generate a deterministic UUID for conformance fixtures."""
    return str(uuid5(CONFORMANCE_NS, f"{entity}.{purpose}"))
```

- [ ] **Step 2: Write model tests**

Create `tests/unit/test_conformance_derivation.py`:
```python
"""Tests for conformance testing data models and derivation engine."""
from __future__ import annotations

import pytest


class TestConformanceModels:
    def test_scope_outcome_values(self) -> None:
        from dazzle.conformance.models import ScopeOutcome
        assert ScopeOutcome.ALL == "all"
        assert ScopeOutcome.FORBIDDEN == "forbidden"

    def test_conformance_case_test_id(self) -> None:
        from dazzle.conformance.models import ConformanceCase, ScopeOutcome
        case = ConformanceCase(
            entity="Task", persona="viewer", operation="list",
            expected_status=200, expected_rows=1,
            scope_type=ScopeOutcome.FILTERED,
        )
        assert case.test_id == "viewer-list-Task-filtered"

    def test_conformance_case_test_id_with_row_target(self) -> None:
        from dazzle.conformance.models import ConformanceCase, ScopeOutcome
        case = ConformanceCase(
            entity="Task", persona="viewer", operation="read",
            expected_status=200, row_target="own",
            scope_type=ScopeOutcome.FILTERED,
        )
        assert case.test_id == "viewer-read-Task-filtered-own"

    def test_conformance_uuid_deterministic(self) -> None:
        from dazzle.conformance.models import conformance_uuid
        a = conformance_uuid("Task", "user_a")
        b = conformance_uuid("Task", "user_a")
        c = conformance_uuid("Task", "user_b")
        assert a == b  # same input = same output
        assert a != c  # different input = different output
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_conformance_derivation.py -v`
Expected: 4 passed

- [ ] **Step 4: Lint and commit**

```bash
ruff check src/dazzle/conformance/ tests/unit/test_conformance_derivation.py --fix
ruff format src/dazzle/conformance/ tests/unit/test_conformance_derivation.py
git add src/dazzle/conformance/ tests/unit/test_conformance_derivation.py
git commit -m "feat: conformance testing data models — ConformanceCase, ScopeOutcome, fixtures"
```

---

### Task 2: Derivation engine — AppSpec → ConformanceCase list

**Files:**
- Create: `src/dazzle/conformance/derivation.py`
- Modify: `tests/unit/test_conformance_derivation.py`

- [ ] **Step 1: Write failing tests for derivation**

Add to `tests/unit/test_conformance_derivation.py`:

```python
from types import SimpleNamespace


def _make_entity(name, permissions=None, scopes=None):
    """Build a minimal EntitySpec-like object."""
    access = None
    if permissions or scopes:
        access = SimpleNamespace(
            visibility=[],
            permissions=permissions or [],
            scopes=scopes or [],
        )
    return SimpleNamespace(
        name=name,
        fields=[
            SimpleNamespace(name="id", type=SimpleNamespace(kind="uuid")),
            SimpleNamespace(name="title", type=SimpleNamespace(kind="str")),
        ],
        access=access,
        title=name,
    )


def _make_appspec(entities):
    return SimpleNamespace(
        domain=SimpleNamespace(entities=entities),
        surfaces=[],
        workspaces=[],
        fk_graph=None,
    )


def _permit(operation, effect="permit", personas=None, condition=None):
    return SimpleNamespace(
        operation=operation, effect=effect,
        personas=personas or [], condition=condition,
        require_auth=True,
    )


def _scope(operation, personas, condition=None, predicate=None):
    return SimpleNamespace(
        operation=operation, personas=personas,
        condition=condition, predicate=predicate,
    )


class TestDerivationEngine:
    def test_unprotected_entity(self) -> None:
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.models import ScopeOutcome

        appspec = _make_appspec([_make_entity("Task")])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        # Unprotected entity: authenticated gets 200, unauthenticated gets 401
        list_cases = [c for c in cases if c.entity == "Task" and c.operation == "list"]
        unauth = [c for c in list_cases if c.persona == "unauthenticated"]
        assert len(unauth) == 1
        assert unauth[0].expected_status == 401

    def test_permit_deny(self) -> None:
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.models import ScopeOutcome

        entity = _make_entity("Task", permissions=[
            _permit("create", personas=["admin"]),
            _permit("list", personas=["admin", "viewer"]),
        ])
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        # viewer cannot create
        viewer_create = [c for c in cases if c.persona == "viewer" and c.operation == "create"]
        assert len(viewer_create) == 1
        assert viewer_create[0].expected_status == 403
        assert viewer_create[0].scope_type == ScopeOutcome.ACCESS_DENIED

    def test_scope_all(self) -> None:
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.models import ScopeOutcome

        entity = _make_entity("Task",
            permissions=[_permit("list", personas=["admin"])],
            scopes=[_scope("list", ["admin"])],  # condition=None → scope: all
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        admin_list = [c for c in cases if c.persona == "admin" and c.operation == "list"]
        assert len(admin_list) == 1
        assert admin_list[0].scope_type == ScopeOutcome.ALL

    def test_scope_excluded_default_deny(self) -> None:
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.models import ScopeOutcome

        entity = _make_entity("Task",
            permissions=[_permit("list", personas=["admin", "viewer"])],
            scopes=[_scope("list", ["admin"])],  # only admin has scope
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        # viewer has permit but no scope → 0 rows
        viewer_list = [c for c in cases if c.persona == "viewer" and c.operation == "list"]
        assert len(viewer_list) == 1
        assert viewer_list[0].expected_rows == 0
        assert viewer_list[0].scope_type == ScopeOutcome.SCOPE_EXCLUDED

    def test_forbid_overrides_permit(self) -> None:
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.models import ScopeOutcome

        entity = _make_entity("Task",
            permissions=[
                _permit("list", personas=["admin"]),
                _permit("list", effect="forbid", personas=["admin"]),
            ],
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        admin_list = [c for c in cases if c.persona == "admin" and c.operation == "list"]
        assert len(admin_list) == 1
        assert admin_list[0].expected_status == 403
        assert admin_list[0].scope_type == ScopeOutcome.FORBIDDEN

    def test_wildcard_scope(self) -> None:
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.models import ScopeOutcome

        entity = _make_entity("Task",
            permissions=[_permit("list", personas=["admin", "viewer"])],
            scopes=[_scope("list", ["*"])],  # scope: all for: *
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        for persona in ("admin", "viewer"):
            p_list = [c for c in cases if c.persona == persona and c.operation == "list"]
            assert len(p_list) == 1
            assert p_list[0].scope_type == ScopeOutcome.ALL

    def test_unmatched_role_denied(self) -> None:
        from dazzle.conformance.derivation import derive_conformance_cases
        from dazzle.conformance.models import ScopeOutcome

        entity = _make_entity("Task",
            permissions=[_permit("list", personas=["admin"])],
        )
        appspec = _make_appspec([entity])
        cases = derive_conformance_cases(appspec, auth_enabled=True)

        unmatched = [c for c in cases if c.persona == "unmatched_role" and c.operation == "list"]
        assert len(unmatched) == 1
        assert unmatched[0].expected_status == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_conformance_derivation.py::TestDerivationEngine -v`
Expected: FAIL — `derive_conformance_cases` does not exist

- [ ] **Step 3: Implement the derivation engine**

Create `src/dazzle/conformance/derivation.py`. The core logic:

1. Extract all persona names from permit/forbid/scope `personas` lists
2. Add synthetic `unauthenticated` and `unmatched_role` personas
3. For each `(entity, persona, operation)`:
   - Apply Cedar three-rule evaluation: FORBID > PERMIT > default-deny
   - For LIST: check scope rules → determine expected_rows and scope_type
   - For CREATE: permit gate only (no scope)
   - For READ/UPDATE/DELETE: generate two cases (own-row and other-row)

The implementation should:
- Use `getattr` for robustness with both real IR objects and SimpleNamespace test objects
- Handle the `for: *` wildcard in scope rules
- Handle `condition=None` in scope rules as `scope: all`
- Produce a filtered ConformanceCase when scope has a condition
- Set `expected_rows` to sentinel values that the fixture engine resolves later

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_conformance_derivation.py -v`
Expected: All passed

- [ ] **Step 5: Lint and commit**

```bash
ruff check src/dazzle/conformance/derivation.py tests/unit/test_conformance_derivation.py --fix
ruff format src/dazzle/conformance/derivation.py tests/unit/test_conformance_derivation.py
git add src/dazzle/conformance/derivation.py tests/unit/test_conformance_derivation.py
git commit -m "feat: conformance derivation engine — AppSpec to ConformanceCase list"
```

---

### Task 3: Fixture engine — AppSpec → ConformanceFixtures

**Files:**
- Create: `src/dazzle/conformance/fixtures.py`
- Create: `tests/unit/test_conformance_fixtures.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_conformance_fixtures.py` with tests for:
- Deterministic UUID generation (same entity+purpose → same UUID)
- User creation per persona (2 users per persona)
- Entity row generation (4 rows per scoped entity)
- FK field resolution (ref fields populated with user UUIDs)
- `expected_counts` computation for `scope: all` (4 rows) and `scope: filtered` (subset)

- [ ] **Step 2: Implement fixture engine**

Create `src/dazzle/conformance/fixtures.py`:
- `generate_fixtures(appspec, cases)` → `ConformanceFixtures`
- For each entity with access rules: create 2 users per persona, 4 entity rows
- Populate ref fields by inspecting `entity.fields` for `kind == "ref"`
- Compute `expected_counts` by evaluating scope predicates against fixture data
- All UUIDs via `conformance_uuid(entity, purpose)`

- [ ] **Step 3: Run tests, lint, commit**

```bash
pytest tests/unit/test_conformance_fixtures.py -v
ruff check src/dazzle/conformance/fixtures.py tests/unit/test_conformance_fixtures.py --fix
ruff format src/dazzle/conformance/fixtures.py tests/unit/test_conformance_fixtures.py
git add src/dazzle/conformance/fixtures.py tests/unit/test_conformance_fixtures.py
git commit -m "feat: conformance fixture engine — deterministic seed data from AppSpec"
```

---

### Task 4: pytest plugin — in-process app boot + HTTP assertions

**Files:**
- Create: `src/dazzle/conformance/plugin.py`
- Create: `tests/unit/test_conformance_plugin.py`

- [ ] **Step 1: Write the pytest plugin**

Create `src/dazzle/conformance/plugin.py`:

```python
"""pytest plugin for DSL conformance testing.

Activated when dazzle.toml is found in project root.
Marker: @pytest.mark.conformance

Usage:
    pytest -m conformance          # run only conformance tests
    pytest -m "not conformance"    # exclude conformance tests
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def pytest_configure(config: Any) -> None:
    config.addinivalue_line("markers", "conformance: DSL conformance tests")


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    """Auto-discover conformance tests when dazzle.toml exists."""
    root = Path(config.rootdir)
    if not (root / "dazzle.toml").exists():
        return
    # Plugin is active — conformance tests will be collected
```

The plugin must:
1. Parse DSL at collection time (from `dazzle.toml` project root)
2. Run derivation engine → cases
3. Run fixture engine → fixtures
4. Generate `test_conformance[{case.test_id}]` parametrized items
5. Session-scoped fixture boots app via `create_app()` with `enable_test_mode=True`
6. Seed fixtures via `/__test__/seed` or direct SQL
7. Authenticate test users via `/__test__/authenticate`
8. Execute HTTP requests via `httpx.AsyncClient(transport=ASGITransport(app))`

- [ ] **Step 2: Write integration test using shapes_validation**

Create `tests/unit/test_conformance_plugin.py` that:
- Loads the `shapes_validation` example AppSpec
- Runs derivation → verifies case count is > 0
- Runs fixture generation → verifies fixtures are populated
- (Full HTTP testing deferred to Task 6 — requires PostgreSQL)

- [ ] **Step 3: Run tests, lint, commit**

```bash
pytest tests/unit/test_conformance_plugin.py -v
git add src/dazzle/conformance/plugin.py tests/unit/test_conformance_plugin.py
git commit -m "feat: conformance pytest plugin — collection, app boot, HTTP assertions"
```

---

### Task 5: Static TOML generator

**Files:**
- Create: `src/dazzle/conformance/generator.py`
- Create: `src/dazzle/cli/conformance.py`

- [ ] **Step 1: Write TOML generator**

Create `src/dazzle/conformance/generator.py`:
- `generate_toml(cases, entity_name)` → TOML string
- Groups cases by entity
- Includes coverage summary (total_cases, scope_types breakdown)
- Adds stage invariant annotations (documented but not asserted)

- [ ] **Step 2: Write CLI command**

Create `src/dazzle/cli/conformance.py`:
- `dazzle conformance generate` — parse DSL, derive cases, write TOML files to `.dazzle/conformance/`
- `dazzle conformance run` — delegate to `pytest -m conformance`
- `dazzle conformance summary` — print coverage metric

- [ ] **Step 3: Register CLI command**

Find the CLI entry point (likely `src/dazzle/cli/__init__.py` or `cli/main.py`) and register the `conformance` subcommand.

- [ ] **Step 4: Test, lint, commit**

```bash
pytest tests/unit/test_conformance_derivation.py tests/unit/test_conformance_fixtures.py -v
ruff check src/dazzle/conformance/ src/dazzle/cli/conformance.py --fix
ruff format src/dazzle/conformance/ src/dazzle/cli/conformance.py
git add src/dazzle/conformance/generator.py src/dazzle/cli/conformance.py
git commit -m "feat: dazzle conformance generate — static TOML test scenario files"
```

---

### Task 6: MCP integration

**Files:**
- Create: `src/dazzle/mcp/server/handlers/conformance.py`
- Modify: MCP tool registration (handlers_consolidated.py or similar)

- [ ] **Step 1: Write MCP handler**

Create `src/dazzle/mcp/server/handlers/conformance.py` with operations:
- `summary` — parse DSL, derive cases, return coverage metric + per-entity counts
- `cases` — derive cases for a specific entity, return as structured data
- `gaps` — find entities with permits but no scope rules (potential conformance gaps)

Follow the existing handler pattern (see other handlers in the same directory).

- [ ] **Step 2: Register the tool**

Add `conformance` to the consolidated tool registration following the existing pattern.

- [ ] **Step 3: Test, lint, commit**

```bash
pytest tests/ -m "not e2e" -x -q
ruff check src/dazzle/mcp/server/handlers/conformance.py --fix
ruff format src/dazzle/mcp/server/handlers/conformance.py
git add src/dazzle/mcp/server/handlers/conformance.py
git commit -m "feat: conformance MCP tool — summary, cases, gaps operations"
```

---

### Task 7: Integration test against shapes_validation

**Files:**
- Modify: `tests/unit/test_conformance_plugin.py`

- [ ] **Step 1: Write full integration test**

Add a test that:
1. Parses the `shapes_validation` example DSL
2. Runs the full derivation → fixture → case generation pipeline
3. Verifies the case list covers all expected `(entity, persona, operation)` triples
4. Verifies the coverage metric calculation
5. Verifies no entity is left uncovered (gaps = empty)

This does NOT require PostgreSQL — it tests the derivation and fixture engines only.

- [ ] **Step 2: Run full test suite for regressions**

```bash
pytest tests/ -m "not e2e" -x -q
```

- [ ] **Step 3: Commit**

```bash
git commit -m "test: conformance integration test against shapes_validation example"
```

---

### Task 8: Quality checks and ship

- [ ] **Step 1: Lint all new files**

```bash
ruff check src/dazzle/conformance/ src/dazzle/cli/conformance.py tests/unit/test_conformance_*.py --fix
ruff format src/dazzle/conformance/ src/dazzle/cli/conformance.py tests/unit/test_conformance_*.py
```

- [ ] **Step 2: Type check**

```bash
mypy src/dazzle/conformance/
```

- [ ] **Step 3: Full test suite**

```bash
pytest tests/ -m "not e2e" -x -q
```

- [ ] **Step 4: Push and monitor CI**

```bash
git push
gh run list --branch $(git branch --show-current) --limit 1
```

- [ ] **Step 5: Update CLAUDE.md**

Add conformance testing to the CLI commands section and MCP tools table in `.claude/CLAUDE.md`.
