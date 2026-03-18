# Dazzle DB: DSL-Driven Database Operations — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `dazzle db status/verify/reset/cleanup` commands that derive all their logic from the DSL's entity graph — zero project-specific config for Layer A operations.

**Architecture:** A new `src/dazzle/db/` package holds pure-logic functions (no CLI/MCP types). CLI commands in the existing `src/dazzle/cli/db.py` call these functions. A new MCP handler exposes `status` and `verify` as read-only operations. The existing `src/dazzle/cli/backup.py` is left untouched — this plan covers only Layer A (DSL-derived operations).

**Tech Stack:** Python 3.12, asyncpg (raw SQL for row counts / FK checks), graphlib (topological sort), Typer (CLI), MCP handler pattern (handlers_consolidated.py).

**Spec:** `docs/superpowers/specs/2026-03-18-dazzle-db-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/dazzle/db/__init__.py` | Package init, re-export public API |
| `src/dazzle/db/graph.py` | Entity dependency graph from AppSpec (topological sort, orphan detection) |
| `src/dazzle/db/sql.py` | SQL helpers: `quote_identifier()` re-export, query builders |
| `src/dazzle/db/status.py` | `db_status_impl()` — row counts per entity, database size |
| `src/dazzle/db/verify.py` | `db_verify_impl()` — FK integrity check, orphan detection |
| `src/dazzle/db/reset.py` | `db_reset_impl()` — truncate entity tables in dependency order |
| `src/dazzle/db/cleanup.py` | `db_cleanup_impl()` — find and remove FK orphans |
| `src/dazzle/db/connection.py` | `resolve_db_url()` / `get_connection()` — resolve DB URL from manifest + env |
| `src/dazzle/cli/db.py` | **Modify** — add status, verify, reset, cleanup commands to existing db_app |
| `src/dazzle/mcp/server/handlers/db.py` | MCP handler for db status/verify |
| `src/dazzle/mcp/server/handlers_consolidated.py` | **Modify** — register `db` tool handler |
| `src/dazzle/mcp/server/tools_consolidated.py` | **Modify** — add `db` tool definition |
| `tests/unit/conftest.py` | **Modify** — add `make_entity` fixture for db tests |
| `tests/unit/test_db_graph.py` | Tests for dependency graph |
| `tests/unit/test_db_status.py` | Tests for status (mocked DB) |
| `tests/unit/test_db_verify.py` | Tests for verify (mocked DB) |
| `tests/unit/test_db_reset.py` | Tests for reset (mocked DB) |
| `tests/unit/test_db_cleanup.py` | Tests for cleanup (mocked DB) |
| `tests/unit/test_cli_db.py` | Tests for CLI commands |
| `tests/unit/mcp/test_db_handlers.py` | Tests for MCP handlers |

---

## Task 1: Entity Dependency Graph

**Files:**
- Create: `src/dazzle/db/__init__.py`
- Create: `src/dazzle/db/graph.py`
- Create: `tests/unit/test_db_graph.py`

This task extracts and extends the topological sort logic from `src/dazzle/demo_data/loader.py` into a reusable module. The new module provides both parent-first order (for schema creation) and leaf-first order (for truncation/deletion).

**Important codebase facts (apply to all tasks):**
- Tables use **quoted PascalCase** names: `"StaffMember"`, not `staff_member`. Use `quote_identifier()` from `dazzle_back.runtime.query_builder`.
- FK columns use the **field name directly** (e.g., `school`), not `school_id`. See `relation_loader.py:130-136`.
- Only `FieldTypeKind.REF` fields create FK columns on the entity. `has_many`, `has_one`, `embeds`, `belongs_to` do NOT — filter them out.
- Auth integrity and baseline validation from the spec are deferred to a follow-up (Layer A-plus). This plan covers FK integrity only.
- Backup inventory in `db status` is deferred (Layer B territory).

- [ ] **Step 1: Create shared test fixtures**

Add the `make_entity` fixture to the existing `tests/unit/conftest.py` (append at the end of the file):

```python
# Append to tests/unit/conftest.py

@pytest.fixture
def make_entity():
    """Factory for mock EntitySpec objects with ref fields (for dazzle.db tests)."""
    from unittest.mock import MagicMock

    def _make(name: str, refs: dict[str, str] | None = None) -> MagicMock:
        entity = MagicMock()
        entity.name = name
        fields = []
        # PK field
        pk = MagicMock()
        pk.name = "id"
        pk.type = MagicMock()
        pk.type.kind = "uuid"
        pk.type.ref_entity = None
        fields.append(pk)
        # Ref fields (FieldTypeKind.REF — the only kind with FK columns on this entity)
        if refs:
            for field_name, ref_entity in refs.items():
                f = MagicMock()
                f.name = field_name
                f.type = MagicMock()
                f.type.kind = "ref"
                f.type.ref_entity = ref_entity
                fields.append(f)
        entity.fields = fields
        return entity

    return _make
```

- [ ] **Step 2: Write failing tests for dependency graph**

```python
# tests/unit/test_db_graph.py
"""Tests for dazzle.db.graph — entity dependency graph utilities."""

from __future__ import annotations

import pytest

from dazzle.db.graph import build_dependency_graph, parents_first, leaves_first, get_ref_fields

# Uses make_entity fixture from conftest_db.py


class TestBuildDependencyGraph:
    def test_empty_entities(self) -> None:
        graph = build_dependency_graph([])
        assert graph == {}

    def test_no_refs(self, make_entity) -> None:
        e1 = make_entity("User")
        e2 = make_entity("Config")
        graph = build_dependency_graph([e1, e2])
        assert graph == {"User": set(), "Config": set()}

    def test_simple_ref(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        graph = build_dependency_graph([school, student])
        assert graph["Student"] == {"School"}
        assert graph["School"] == set()

    def test_self_ref_excluded(self, make_entity) -> None:
        employee = make_entity("Employee", {"manager": "Employee"})
        graph = build_dependency_graph([employee])
        assert graph["Employee"] == set()

    def test_ref_to_external_entity_excluded(self, make_entity) -> None:
        """Refs to entities not in the list are excluded."""
        student = make_entity("Student", {"school": "School"})
        graph = build_dependency_graph([student])
        assert graph["Student"] == set()

    def test_has_many_excluded(self, make_entity) -> None:
        """has_many fields should NOT appear in the dependency graph."""
        from unittest.mock import MagicMock

        parent = make_entity("School")
        # Add a has_many field — should be ignored
        hm = MagicMock()
        hm.name = "students"
        hm.type = MagicMock()
        hm.type.kind = "has_many"
        hm.type.ref_entity = "Student"
        parent.fields.append(hm)

        student = make_entity("Student", {"school": "School"})
        graph = build_dependency_graph([parent, student])
        # School should NOT depend on Student (has_many is reverse)
        assert graph["School"] == set()
        assert graph["Student"] == {"School"}


class TestParentsFirst:
    def test_linear_chain(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        exclusion = make_entity("Exclusion", {"student": "Student"})
        result = parents_first([school, student, exclusion])
        assert result.index("School") < result.index("Student")
        assert result.index("Student") < result.index("Exclusion")

    def test_circular_ref_returns_sorted(self, make_entity) -> None:
        a = make_entity("A", {"b": "B"})
        b = make_entity("B", {"a": "A"})
        result = parents_first([a, b])
        assert sorted(result) == ["A", "B"]


class TestLeavesFirst:
    def test_linear_chain(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        exclusion = make_entity("Exclusion", {"student": "Student"})
        result = leaves_first([school, student, exclusion])
        assert result.index("Exclusion") < result.index("Student")
        assert result.index("Student") < result.index("School")


class TestGetRefFields:
    def test_returns_ref_fields_only(self, make_entity) -> None:
        student = make_entity("Student", {"school": "School", "tutor": "StaffMember"})
        refs = get_ref_fields(student)
        assert len(refs) == 2
        ref_names = {r.name for r in refs}
        assert ref_names == {"school", "tutor"}

    def test_excludes_has_many(self, make_entity) -> None:
        """has_many fields should NOT be returned."""
        from unittest.mock import MagicMock

        parent = make_entity("School")
        hm = MagicMock()
        hm.name = "students"
        hm.type = MagicMock()
        hm.type.kind = "has_many"
        hm.type.ref_entity = "Student"
        parent.fields.append(hm)
        assert get_ref_fields(parent) == []

    def test_no_refs(self, make_entity) -> None:
        config = make_entity("Config")
        assert get_ref_fields(config) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_db_graph.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle.db'`

- [ ] **Step 3: Implement the graph module**

```python
# src/dazzle/db/__init__.py
"""DSL-driven database operations."""
```

```python
# src/dazzle/db/graph.py
"""Entity dependency graph utilities.

Computes FK dependency ordering from AppSpec entities.
Used by reset (leaf-first truncation) and cleanup (orphan detection).
"""

from __future__ import annotations

import logging
from graphlib import TopologicalSorter
from typing import Any

logger = logging.getLogger(__name__)

# Only these FieldTypeKind values create FK columns on the entity.
# has_many, has_one, embeds store FKs on the *other* entity.
_FK_KINDS = frozenset({"ref", "belongs_to"})


def build_dependency_graph(entities: list[Any]) -> dict[str, set[str]]:
    """Build {entity_name: set_of_dependency_names} from ref fields.

    Only includes REF/BELONGS_TO fields (which create FK columns).
    Refs to entities not in the list and self-references are excluded.
    """
    entity_names = {e.name for e in entities}
    graph: dict[str, set[str]] = {}

    for entity in entities:
        deps: set[str] = set()
        for f in entity.fields:
            if (
                f.type
                and f.type.kind in _FK_KINDS
                and f.type.ref_entity
                and f.type.ref_entity in entity_names
                and f.type.ref_entity != entity.name
            ):
                deps.add(f.type.ref_entity)
        graph[entity.name] = deps

    return graph


def parents_first(entities: list[Any]) -> list[str]:
    """Return entity names in parent-first order (for schema creation / data loading).

    Falls back to alphabetical on circular references.
    """
    graph = build_dependency_graph(entities)
    sorter = TopologicalSorter(graph)
    try:
        return list(sorter.static_order())
    except Exception:
        logger.warning("Circular FK references detected, falling back to alphabetical order")
        return sorted(graph.keys())


def leaves_first(entities: list[Any]) -> list[str]:
    """Return entity names in leaf-first order (for truncation / deletion).

    This is the reverse of parents_first.
    """
    return list(reversed(parents_first(entities)))


def get_ref_fields(entity: Any) -> list[Any]:
    """Return only fields that create FK columns (ref, belongs_to)."""
    return [f for f in entity.fields if f.type and f.type.kind in _FK_KINDS and f.type.ref_entity]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_db_graph.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/db/__init__.py src/dazzle/db/graph.py tests/unit/conftest.py tests/unit/test_db_graph.py
git commit -m "feat(db): add entity dependency graph utilities"
```

---

## Task 2: Database Connection Helper

**Files:**
- Create: `src/dazzle/db/connection.py`
- Create: `tests/unit/test_db_connection.py`

Thin wrapper around `resolve_database_url` from `dazzle.core.manifest` plus an asyncpg connection factory. All db operations will use this instead of duplicating URL resolution.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_db_connection.py
"""Tests for dazzle.db.connection — database URL resolution and connection factory."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dazzle.db.connection import resolve_db_url


class TestResolveDbUrl:
    def test_explicit_url_wins(self) -> None:
        url = resolve_db_url(explicit_url="postgresql://localhost/mydb")
        assert url == "postgresql://localhost/mydb"

    @patch.dict("os.environ", {"DATABASE_URL": "postgresql://env/db"}, clear=False)
    def test_env_var_fallback(self) -> None:
        url = resolve_db_url()
        assert url == "postgresql://env/db"

    @patch.dict("os.environ", {}, clear=False)
    @patch("dazzle.db.connection.load_manifest")
    @patch("dazzle.db.connection.Path.exists", return_value=True)
    def test_manifest_fallback(self, mock_exists: MagicMock, mock_load: MagicMock) -> None:
        manifest = MagicMock()
        manifest.database.url = "postgresql://manifest/db"
        mock_load.return_value = manifest
        url = resolve_db_url(project_root=Path("/fake/project"))
        assert url == "postgresql://manifest/db"

    @patch.dict("os.environ", {}, clear=False)
    def test_default_when_nothing_set(self) -> None:
        url = resolve_db_url()
        assert "postgresql://" in url
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_db_connection.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement connection module**

```python
# src/dazzle/db/connection.py
"""Database connection utilities.

Resolves DATABASE_URL and provides asyncpg connection factories.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def resolve_db_url(
    *,
    explicit_url: str = "",
    project_root: Path | None = None,
) -> str:
    """Resolve the database URL.

    Priority: explicit_url > DATABASE_URL env > dazzle.toml > default.
    Delegates to dazzle.core.manifest.resolve_database_url.
    """
    from dazzle.core.manifest import resolve_database_url

    manifest = None
    if project_root is not None:
        toml_path = project_root / "dazzle.toml"
        if toml_path.exists():
            from dazzle.core.manifest import load_manifest

            manifest = load_manifest(toml_path)

    return resolve_database_url(manifest, explicit_url=explicit_url)


async def get_connection(
    *,
    explicit_url: str = "",
    project_root: Path | None = None,
) -> Any:
    """Create an asyncpg connection.

    Caller is responsible for closing it.
    """
    import asyncpg

    url = resolve_db_url(explicit_url=explicit_url, project_root=project_root)
    return await asyncpg.connect(url)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_db_connection.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/db/connection.py tests/unit/test_db_connection.py
git commit -m "feat(db): add database connection helper"
```

---

## Task 3: `db status` Implementation

**Files:**
- Create: `src/dazzle/db/status.py`
- Create: `tests/unit/test_db_status.py`

Queries row counts per entity table and total database size via raw SQL. First, create the shared SQL helper module.

- [ ] **Step 1: Create sql.py helper module**

```python
# src/dazzle/db/sql.py
"""SQL helpers for db operations.

Re-exports quote_identifier from the runtime and provides query builders.
All SQL in this package goes through these helpers for safety.
"""

from __future__ import annotations


def quote_id(name: str) -> str:
    """Quote a SQL identifier (table or column name).

    Dazzle uses PascalCase entity names as table names, quoted with double-quotes.
    Re-implements the logic from dazzle_back.runtime.query_builder.quote_identifier
    to avoid importing the runtime package (which has heavier dependencies).
    """
    escaped = name.replace('"', '""')
    return f'"{escaped}"'
```

- [ ] **Step 2: Write failing tests for status**

```python
# tests/unit/test_db_status.py
"""Tests for dazzle.db.status — row counts and database size."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.db.status import db_status_impl


class TestDbStatusImpl:
    @pytest.mark.asyncio
    async def test_returns_entity_row_counts(self, make_entity) -> None:
        e1 = make_entity("User")
        e2 = make_entity("Task")
        entities = [e1, e2]

        conn = AsyncMock()
        conn.fetchval = AsyncMock(side_effect=[
            12,    # User count
            150,   # Task count
            "2.1 MB",  # DB size
        ])

        result = await db_status_impl(entities=entities, conn=conn)

        assert result["total_entities"] == 2
        assert result["total_rows"] == 162
        assert len(result["entities"]) == 2
        assert result["entities"][0]["name"] == "User"
        assert result["entities"][0]["rows"] == 12
        assert result["entities"][1]["name"] == "Task"
        assert result["entities"][1]["rows"] == 150
        assert result["database_size"] == "2.1 MB"

    @pytest.mark.asyncio
    async def test_handles_missing_table(self, make_entity) -> None:
        e1 = make_entity("Missing")
        conn = AsyncMock()
        conn.fetchval = AsyncMock(side_effect=[
            Exception("relation does not exist"),
            "1 MB",
        ])

        result = await db_status_impl(entities=[e1], conn=conn)
        assert result["entities"][0]["rows"] == 0
        assert result["entities"][0]["error"] is not None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/test_db_status.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement status module**

```python
# src/dazzle/db/status.py
"""Database status: row counts per entity, database size."""

from __future__ import annotations

from typing import Any

from .sql import quote_id


async def db_status_impl(
    *,
    entities: list[Any],
    conn: Any,
) -> dict[str, Any]:
    """Get row counts per entity and database size.

    Args:
        entities: List of EntitySpec objects.
        conn: asyncpg connection.

    Returns:
        Dict with entity row counts, totals, and database size.
    """
    results: list[dict[str, Any]] = []
    total_rows = 0

    for entity in entities:
        table = quote_id(entity.name)
        try:
            count = await conn.fetchval(f"SELECT count(*) FROM {table}")
            results.append({"name": entity.name, "table": entity.name, "rows": count, "error": None})
            total_rows += count
        except Exception as e:
            results.append({"name": entity.name, "table": entity.name, "rows": 0, "error": str(e)})

    # Database size
    try:
        db_size = await conn.fetchval("SELECT pg_size_pretty(pg_database_size(current_database()))")
    except Exception:
        db_size = "unknown"

    return {
        "entities": results,
        "total_entities": len(entities),
        "total_rows": total_rows,
        "database_size": db_size,
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_db_status.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/db/sql.py src/dazzle/db/status.py tests/unit/test_db_status.py
git commit -m "feat(db): add sql helpers and status implementation"
```

---

## Task 4: `db verify` Implementation

**Files:**
- Create: `src/dazzle/db/verify.py`
- Create: `tests/unit/test_db_verify.py`

Walks every `ref` field in every entity and checks FK integrity via SQL.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_db_verify.py
"""Tests for dazzle.db.verify — FK integrity checking."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from dazzle.db.verify import db_verify_impl, _build_orphan_query


class TestBuildOrphanQuery:
    def test_generates_valid_sql(self) -> None:
        sql = _build_orphan_query(
            child_table='"Exclusion"',
            fk_column='"student"',
            parent_table='"Student"',
            pk_column='"id"',
        )
        assert '"Exclusion"' in sql
        assert '"Student"' in sql
        assert '"student"' in sql
        assert "NOT EXISTS" in sql


class TestDbVerifyImpl:
    @pytest.mark.asyncio
    async def test_no_orphans(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        entities = [school, student]

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=0)

        result = await db_verify_impl(entities=entities, conn=conn)
        assert result["total_issues"] == 0
        assert len(result["checks"]) == 1
        assert result["checks"][0]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_orphans_found(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        entities = [school, student]

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=3)

        result = await db_verify_impl(entities=entities, conn=conn)
        assert result["total_issues"] == 3
        assert result["checks"][0]["status"] == "orphans"
        assert result["checks"][0]["orphan_count"] == 3

    @pytest.mark.asyncio
    async def test_missing_table_handled(self, make_entity) -> None:
        student = make_entity("Student", {"school": "School"})
        school = make_entity("School")

        conn = AsyncMock()
        conn.fetchval = AsyncMock(side_effect=Exception("relation does not exist"))

        result = await db_verify_impl(entities=[school, student], conn=conn)
        assert result["checks"][0]["status"] == "error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_db_verify.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement verify module**

```python
# src/dazzle/db/verify.py
"""Database verification: FK integrity checks."""

from __future__ import annotations

from typing import Any

from .graph import get_ref_fields
from .sql import quote_id


def _build_orphan_query(
    *,
    child_table: str,
    fk_column: str,
    parent_table: str,
    pk_column: str,
) -> str:
    """Build SQL to count orphan rows where FK references a missing parent.

    All arguments must already be quoted identifiers.
    """
    return (
        f"SELECT count(*) FROM {child_table} c "
        f"WHERE c.{fk_column} IS NOT NULL "
        f"AND NOT EXISTS ("
        f"SELECT 1 FROM {parent_table} p WHERE p.{pk_column} = c.{fk_column}"
        f")"
    )


async def db_verify_impl(
    *,
    entities: list[Any],
    conn: Any,
) -> dict[str, Any]:
    """Check FK integrity for all ref fields.

    Args:
        entities: List of EntitySpec objects.
        conn: asyncpg connection.

    Returns:
        Dict with check results and total issue count.
    """
    entity_map = {e.name: e for e in entities}
    checks: list[dict[str, Any]] = []
    total_issues = 0

    for entity in entities:
        ref_fields = get_ref_fields(entity)
        for field in ref_fields:
            ref_name = field.type.ref_entity
            if ref_name not in entity_map:
                continue  # external ref, skip

            child_table = quote_id(entity.name)
            parent_table = quote_id(ref_name)
            fk_column = quote_id(field.name)

            sql = _build_orphan_query(
                child_table=child_table,
                fk_column=fk_column,
                parent_table=parent_table,
                pk_column=quote_id("id"),
            )

            try:
                orphan_count = await conn.fetchval(sql)
                if orphan_count > 0:
                    checks.append({
                        "entity": entity.name,
                        "field": field.name,
                        "ref": ref_name,
                        "status": "orphans",
                        "orphan_count": orphan_count,
                    })
                    total_issues += orphan_count
                else:
                    checks.append({
                        "entity": entity.name,
                        "field": field.name,
                        "ref": ref_name,
                        "status": "ok",
                        "orphan_count": 0,
                    })
            except Exception as e:
                checks.append({
                    "entity": entity.name,
                    "field": field.name,
                    "ref": ref_name,
                    "status": "error",
                    "error": str(e),
                })

    return {
        "checks": checks,
        "total_issues": total_issues,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_db_verify.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/db/verify.py tests/unit/test_db_verify.py
git commit -m "feat(db): add verify implementation — FK integrity checks"
```

---

## Task 5: `db reset` Implementation

**Files:**
- Create: `src/dazzle/db/reset.py`
- Create: `tests/unit/test_db_reset.py`

Truncates entity tables in leaf-first order, preserving auth tables.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_db_reset.py
"""Tests for dazzle.db.reset — truncate entity tables in dependency order."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.db.reset import db_reset_impl, AUTH_TABLES


class TestDbResetImpl:
    @pytest.mark.asyncio
    async def test_truncates_in_leaf_first_order(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        exclusion = make_entity("Exclusion", {"student": "Student"})

        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value=10)

        result = await db_reset_impl(entities=[school, student, exclusion], conn=conn)

        assert result["truncated"] == 3
        # Verify leaf-first ordering in calls
        calls = [c for c in conn.execute.call_args_list if "TRUNCATE" in str(c)]
        assert len(calls) == 3
        # Exclusion (leaf) should be truncated first
        assert "Exclusion" in str(calls[0])
        assert "School" in str(calls[2])

    @pytest.mark.asyncio
    async def test_preserves_auth_tables(self, make_entity) -> None:
        """Entity named 'Task' should still be truncated — only internal auth tables preserved."""
        task = make_entity("Task")
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value=5)

        result = await db_reset_impl(entities=[task], conn=conn)
        assert result["truncated"] == 1

    @pytest.mark.asyncio
    async def test_custom_preserve_list(self, make_entity) -> None:
        e1 = make_entity("Config")
        e2 = make_entity("Task")

        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value=5)

        result = await db_reset_impl(
            entities=[e1, e2], conn=conn, preserve={"Config"}
        )
        assert result["truncated"] == 1
        assert result["preserved"] == ["Config"]

    @pytest.mark.asyncio
    async def test_dry_run(self, make_entity) -> None:
        task = make_entity("Task")
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=42)

        result = await db_reset_impl(entities=[task], conn=conn, dry_run=True)
        assert result["dry_run"] is True
        assert result["would_truncate"] == 1
        conn.execute.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_db_reset.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement reset module**

```python
# src/dazzle/db/reset.py
"""Database reset: truncate entity tables in dependency order."""

from __future__ import annotations

import logging
from typing import Any

from .graph import leaves_first
from .sql import quote_id

logger = logging.getLogger(__name__)

# Internal auth/config tables that should never be truncated.
# These are runtime infrastructure, not DSL entities.
# Stored as PascalCase entity names (matching table names).
AUTH_TABLES = frozenset({
    "dazzle_user",
    "dazzle_session",
    "dazzle_role",
    "alembic_version",
})


async def db_reset_impl(
    *,
    entities: list[Any],
    conn: Any,
    preserve: set[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Truncate entity tables in leaf-first order.

    Args:
        entities: List of EntitySpec objects.
        conn: asyncpg connection.
        preserve: Set of entity names to skip (PascalCase).
        dry_run: If True, report what would be truncated without doing it.

    Returns:
        Dict with truncation results.
    """
    preserve_names: set[str] = set()
    if preserve:
        preserve_names |= preserve

    order = leaves_first(entities)
    truncated: list[dict[str, Any]] = []
    preserved: list[str] = []
    total_rows = 0

    for name in order:
        if name in preserve_names:
            preserved.append(name)
            continue

        table = quote_id(name)
        try:
            row_count = await conn.fetchval(f"SELECT count(*) FROM {table}")
        except Exception:
            row_count = 0

        if dry_run:
            truncated.append({"name": name, "table": name, "rows": row_count})
            total_rows += row_count
            continue

        try:
            await conn.execute(f"TRUNCATE TABLE {table} CASCADE")
            truncated.append({"name": name, "table": name, "rows": row_count})
            total_rows += row_count
        except Exception as e:
            logger.warning("Failed to truncate %s: %s", name, e)
            truncated.append({"name": name, "table": name, "rows": 0, "error": str(e)})

    if dry_run:
        return {
            "dry_run": True,
            "would_truncate": len(truncated),
            "total_rows": total_rows,
            "tables": truncated,
            "preserved": preserved,
        }

    return {
        "truncated": len(truncated),
        "total_rows": total_rows,
        "tables": truncated,
        "preserved": preserved,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_db_reset.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/db/reset.py tests/unit/test_db_reset.py
git commit -m "feat(db): add reset implementation — leaf-first truncation"
```

---

## Task 6: `db cleanup` Implementation

**Files:**
- Create: `src/dazzle/db/cleanup.py`
- Create: `tests/unit/test_db_cleanup.py`

Finds and deletes FK orphans iteratively.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_db_cleanup.py
"""Tests for dazzle.db.cleanup — orphan record removal."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from dazzle.db.cleanup import db_cleanup_impl


class TestDbCleanupImpl:
    @pytest.mark.asyncio
    async def test_no_orphans(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=0)

        result = await db_cleanup_impl(entities=[school, student], conn=conn)
        assert result["total_deleted"] == 0

    @pytest.mark.asyncio
    async def test_deletes_orphans(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        conn = AsyncMock()
        # First iteration: 3 orphans found, then deleted
        # Second iteration: 0 orphans (done)
        conn.fetchval = AsyncMock(side_effect=[3, 0])
        conn.execute = AsyncMock(return_value="DELETE 3")

        result = await db_cleanup_impl(entities=[school, student], conn=conn)
        assert result["total_deleted"] == 3
        assert result["iterations"] >= 1

    @pytest.mark.asyncio
    async def test_dry_run(self, make_entity) -> None:
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=5)

        result = await db_cleanup_impl(entities=[school, student], conn=conn, dry_run=True)
        assert result["dry_run"] is True
        assert result["would_delete"] == 5
        conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_max_iterations_cap(self, make_entity) -> None:
        """Stops after MAX_ITERATIONS even if orphans remain."""
        school = make_entity("School")
        student = make_entity("Student", {"school": "School"})
        conn = AsyncMock()
        # Always returns orphans — should stop at cap
        conn.fetchval = AsyncMock(return_value=1)
        conn.execute = AsyncMock(return_value="DELETE 1")

        result = await db_cleanup_impl(entities=[school, student], conn=conn)
        assert result["iterations"] <= 10

    @pytest.mark.asyncio
    async def test_no_checks_returns_zero(self, make_entity) -> None:
        """Entities with no refs should return 0 deleted, 0 iterations."""
        config = make_entity("Config")
        conn = AsyncMock()

        result = await db_cleanup_impl(entities=[config], conn=conn)
        assert result["total_deleted"] == 0
        assert result["iterations"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_db_cleanup.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement cleanup module**

```python
# src/dazzle/db/cleanup.py
"""Database cleanup: find and remove FK orphans."""

from __future__ import annotations

import logging
from typing import Any

from .graph import get_ref_fields
from .sql import quote_id
from .verify import _build_orphan_query

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10


def _build_delete_orphans_query(
    *,
    child_table: str,
    fk_column: str,
    parent_table: str,
    pk_column: str,
) -> str:
    """Build SQL to delete orphan rows. All args must be quoted identifiers."""
    return (
        f"DELETE FROM {child_table} "
        f"WHERE {fk_column} IS NOT NULL "
        f"AND NOT EXISTS ("
        f"SELECT 1 FROM {parent_table} p WHERE p.{pk_column} = {child_table}.{fk_column}"
        f")"
    )


async def db_cleanup_impl(
    *,
    entities: list[Any],
    conn: Any,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Find and remove FK orphans iteratively.

    Repeats until no orphans remain or MAX_ITERATIONS is reached.

    Args:
        entities: List of EntitySpec objects.
        conn: asyncpg connection.
        dry_run: If True, count orphans without deleting.

    Returns:
        Dict with cleanup results.
    """
    entity_map = {e.name: e for e in entities}

    # Build list of (entity_name, field, ref_name) checks
    checks: list[tuple[str, Any, str]] = []
    for entity in entities:
        for field in get_ref_fields(entity):
            if field.type.ref_entity in entity_map:
                checks.append((entity.name, field, field.type.ref_entity))

    if dry_run:
        total_would_delete = 0
        findings: list[dict[str, Any]] = []
        for entity_name, field, ref_name in checks:
            child_table = quote_id(entity_name)
            parent_table = quote_id(ref_name)
            fk_column = quote_id(field.name)
            pk_column = quote_id("id")
            sql = _build_orphan_query(
                child_table=child_table,
                fk_column=fk_column,
                parent_table=parent_table,
                pk_column=pk_column,
            )
            try:
                count = await conn.fetchval(sql)
                if count > 0:
                    findings.append({
                        "entity": entity_name,
                        "field": field.name,
                        "ref": ref_name,
                        "orphan_count": count,
                    })
                    total_would_delete += count
            except Exception as e:
                logger.warning("Error checking %s.%s: %s", entity_name, field.name, e)

        return {
            "dry_run": True,
            "would_delete": total_would_delete,
            "findings": findings,
        }

    # Iterative cleanup
    total_deleted = 0
    iteration = 0  # Initialize before loop to avoid UnboundLocalError
    all_deletions: list[dict[str, Any]] = []

    for iteration in range(1, MAX_ITERATIONS + 1):
        round_deleted = 0

        for entity_name, field, ref_name in checks:
            child_table = quote_id(entity_name)
            parent_table = quote_id(ref_name)
            fk_column = quote_id(field.name)
            pk_column = quote_id("id")

            count_sql = _build_orphan_query(
                child_table=child_table,
                fk_column=fk_column,
                parent_table=parent_table,
                pk_column=pk_column,
            )
            try:
                count = await conn.fetchval(count_sql)
                if count == 0:
                    continue

                delete_sql = _build_delete_orphans_query(
                    child_table=child_table,
                    fk_column=fk_column,
                    parent_table=parent_table,
                    pk_column=pk_column,
                )
                await conn.execute(delete_sql)
                round_deleted += count
                all_deletions.append({
                    "entity": entity_name,
                    "field": field.name,
                    "ref": ref_name,
                    "deleted": count,
                    "iteration": iteration,
                })
            except Exception as e:
                logger.warning("Error cleaning %s.%s: %s", entity_name, field.name, e)

        total_deleted += round_deleted
        if round_deleted == 0:
            break

    return {
        "total_deleted": total_deleted,
        "iterations": iteration,
        "deletions": all_deletions,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_db_cleanup.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/db/cleanup.py tests/unit/test_db_cleanup.py
git commit -m "feat(db): add cleanup implementation — iterative orphan removal"
```

---

## Task 7: CLI Commands

**Files:**
- Modify: `src/dazzle/cli/db.py`
- Create: `tests/unit/test_cli_db_ops.py`

Add `status`, `verify`, `reset`, `cleanup` commands to the existing `db_app` Typer group.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_cli_db_ops.py
"""Tests for dazzle db status/verify/reset/cleanup CLI commands."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from dazzle.cli.db import db_app

runner = CliRunner()


class TestDbStatusCommand:
    @patch("dazzle.cli.db.asyncio.run")
    @patch("dazzle.cli.db.load_project_appspec")
    def test_status_shows_entities(self, mock_load: MagicMock, mock_run: MagicMock) -> None:
        appspec = MagicMock()
        e1 = MagicMock()
        e1.name = "Task"
        appspec.domain.entities = [e1]
        mock_load.return_value = appspec

        mock_run.return_value = {
            "entities": [{"name": "Task", "table": "task", "rows": 42, "error": None}],
            "total_entities": 1,
            "total_rows": 42,
            "database_size": "1 MB",
        }

        result = runner.invoke(db_app, ["status"])
        assert result.exit_code == 0
        assert "Task" in result.output
        assert "42" in result.output


class TestDbVerifyCommand:
    @patch("dazzle.cli.db.asyncio.run")
    @patch("dazzle.cli.db.load_project_appspec")
    def test_verify_shows_results(self, mock_load: MagicMock, mock_run: MagicMock) -> None:
        appspec = MagicMock()
        appspec.domain.entities = []
        mock_load.return_value = appspec

        mock_run.return_value = {
            "checks": [],
            "total_issues": 0,
        }

        result = runner.invoke(db_app, ["verify"])
        assert result.exit_code == 0
        assert "0" in result.output or "issues" in result.output.lower() or "ok" in result.output.lower()


class TestDbResetCommand:
    @patch("dazzle.cli.db.asyncio.run")
    @patch("dazzle.cli.db.load_project_appspec")
    def test_reset_dry_run(self, mock_load: MagicMock, mock_run: MagicMock) -> None:
        appspec = MagicMock()
        e1 = MagicMock()
        e1.name = "Task"
        appspec.domain.entities = [e1]
        mock_load.return_value = appspec

        mock_run.return_value = {
            "dry_run": True,
            "would_truncate": 1,
            "total_rows": 42,
            "tables": [{"name": "Task", "table": "task", "rows": 42}],
            "preserved": [],
        }

        result = runner.invoke(db_app, ["reset", "--dry-run"])
        assert result.exit_code == 0
        assert "42" in result.output


class TestDbCleanupCommand:
    @patch("dazzle.cli.db.asyncio.run")
    @patch("dazzle.cli.db.load_project_appspec")
    def test_cleanup_dry_run(self, mock_load: MagicMock, mock_run: MagicMock) -> None:
        appspec = MagicMock()
        appspec.domain.entities = []
        mock_load.return_value = appspec

        mock_run.return_value = {
            "dry_run": True,
            "would_delete": 0,
            "findings": [],
        }

        result = runner.invoke(db_app, ["cleanup", "--dry-run"])
        assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_cli_db_ops.py -v`
Expected: FAIL — commands don't exist yet

- [ ] **Step 3: Add CLI commands to db.py**

Add the following commands to the existing `src/dazzle/cli/db.py`, after the existing migration commands:

```python
# --- Below existing code in db.py ---

import asyncio
from dazzle.cli.utils import load_project_appspec


async def _run_with_connection(
    project_root: Path,
    database_url: str,
    coro_factory: Any,
) -> Any:
    """Connect to DB, run async operation, close connection."""
    from dazzle.db.connection import get_connection

    conn = await get_connection(explicit_url=database_url, project_root=project_root)
    try:
        return await coro_factory(conn)
    finally:
        await conn.close()


def _resolve_url(database_url: str) -> str:
    """Resolve database URL from flag, env, or manifest."""
    from dazzle.db.connection import resolve_db_url

    return resolve_db_url(explicit_url=database_url, project_root=Path.cwd().resolve())


@db_app.command(name="status")
def status_command(
    database_url: str = typer.Option("", "--database-url", help="Database URL override"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show row counts per entity and database size."""
    import json as json_mod

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    entities = appspec.domain.entities
    url = _resolve_url(database_url)

    from dazzle.db.status import db_status_impl

    async def _run(conn: Any) -> Any:
        return await db_status_impl(entities=entities, conn=conn)

    result = asyncio.run(_run_with_connection(project_root, url, _run))

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    console.print(f"\n[bold]Entity           Rows[/bold]")
    console.print("─" * 30)
    for entry in result["entities"]:
        status = f"[red]error[/red]" if entry.get("error") else str(entry["rows"])
        console.print(f"  {entry['name']:<18} {status}")
    console.print("─" * 30)
    console.print(
        f"Total: {result['total_entities']} entities, "
        f"{result['total_rows']:,} rows, {result['database_size']}"
    )


@db_app.command(name="verify")
def verify_command(
    database_url: str = typer.Option("", "--database-url", help="Database URL override"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Check FK integrity across all entity relationships."""
    import json as json_mod

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    entities = appspec.domain.entities
    url = _resolve_url(database_url)

    from dazzle.db.verify import db_verify_impl

    async def _run(conn: Any) -> Any:
        return await db_verify_impl(entities=entities, conn=conn)

    result = asyncio.run(_run_with_connection(project_root, url, _run))

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    console.print("\n[bold]FK Integrity:[/bold]")
    for check in result["checks"]:
        if check["status"] == "ok":
            console.print(f"  [green]✓[/green] {check['entity']}.{check['field']} → {check['ref']}")
        elif check["status"] == "orphans":
            console.print(
                f"  [red]✗[/red] {check['entity']}.{check['field']} → {check['ref']}: "
                f"{check['orphan_count']} orphans"
            )
        else:
            console.print(
                f"  [yellow]![/yellow] {check['entity']}.{check['field']} → {check['ref']}: "
                f"{check.get('error', 'unknown error')}"
            )

    if result["total_issues"] == 0:
        console.print(f"\n[green]All FK references valid.[/green]")
    else:
        console.print(f"\n[red]{result['total_issues']} issues found.[/red]")


@db_app.command(name="reset")
def reset_command(
    database_url: str = typer.Option("", "--database-url", help="Database URL override"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be truncated"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Truncate entity tables in dependency order (preserves auth)."""
    import json as json_mod

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    entities = appspec.domain.entities
    url = _resolve_url(database_url)

    from dazzle.db.reset import db_reset_impl

    if dry_run:
        async def _run(conn: Any) -> Any:
            return await db_reset_impl(entities=entities, conn=conn, dry_run=True)

        result = asyncio.run(_run_with_connection(project_root, url, _run))

        if as_json:
            console.print(json_mod.dumps(result, indent=2))
            return

        console.print(f"\n[bold]Would truncate {result['would_truncate']} tables ({result['total_rows']:,} rows):[/bold]")
        for t in result["tables"]:
            console.print(f"  {t['name']} ({t['rows']} rows)")
        if result["preserved"]:
            console.print(f"\nPreserved: {', '.join(result['preserved'])}")
        return

    if not yes:
        console.print(f"\nThis will truncate {len(entities)} entity tables.")
        confirm = typer.prompt("Type 'reset' to confirm", default="")
        if confirm != "reset":
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    async def _run(conn: Any) -> Any:
        return await db_reset_impl(entities=entities, conn=conn)

    result = asyncio.run(_run_with_connection(project_root, url, _run))

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    for t in result["tables"]:
        err = f" [red]error: {t['error']}[/red]" if t.get("error") else " ✓"
        console.print(f"  {t['name']} ({t['rows']} rows){err}")
    console.print(f"\n[green]Reset complete: {result['truncated']} tables, {result['total_rows']:,} rows removed.[/green]")


@db_app.command(name="cleanup")
def cleanup_command(
    database_url: str = typer.Option("", "--database-url", help="Database URL override"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be deleted"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Find and remove FK orphan records."""
    import json as json_mod

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    entities = appspec.domain.entities
    url = _resolve_url(database_url)

    from dazzle.db.cleanup import db_cleanup_impl

    if dry_run:
        async def _run(conn: Any) -> Any:
            return await db_cleanup_impl(entities=entities, conn=conn, dry_run=True)

        result = asyncio.run(_run_with_connection(project_root, url, _run))

        if as_json:
            console.print(json_mod.dumps(result, indent=2))
            return

        if result["would_delete"] == 0:
            console.print("[green]No orphan records found.[/green]")
            return

        console.print(f"\n[bold]Found {result['would_delete']} orphan records:[/bold]")
        for f in result["findings"]:
            console.print(f"  {f['orphan_count']} × {f['entity']} ({f['field']} → {f['ref']}: missing)")
        console.print("\nRun without --dry-run to delete.")
        return

    if not yes:
        confirm = typer.prompt("Type 'cleanup' to confirm", default="")
        if confirm != "cleanup":
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    async def _run(conn: Any) -> Any:
        return await db_cleanup_impl(entities=entities, conn=conn)

    result = asyncio.run(_run_with_connection(project_root, url, _run))

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    if result["total_deleted"] == 0:
        console.print("[green]No orphan records found.[/green]")
        return

    for d in result["deletions"]:
        console.print(f"  {d['deleted']} × {d['entity']} ✓")
    console.print(
        f"\n[green]Cleanup complete: {result['total_deleted']} orphans removed "
        f"in {result['iterations']} iteration(s).[/green]"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_cli_db_ops.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/db.py tests/unit/test_cli_db_ops.py
git commit -m "feat(db): add status/verify/reset/cleanup CLI commands"
```

---

## Task 8: MCP Handler + Tool Registration

**Files:**
- Create: `src/dazzle/mcp/server/handlers/db.py`
- Modify: `src/dazzle/mcp/server/handlers_consolidated.py`
- Modify: `src/dazzle/mcp/server/tools_consolidated.py`
- Create: `tests/unit/mcp/test_db_handlers.py`

Expose `db status` and `db verify` as MCP read-only operations.

- [ ] **Step 1: Write failing tests for MCP handler**

```python
# tests/unit/mcp/test_db_handlers.py
"""Tests for db MCP handlers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Pre-mock MCP modules to prevent import errors
sys.modules.setdefault("mcp", MagicMock(pytest_plugins=[]))
sys.modules.setdefault("mcp.types", MagicMock())
sys.modules.setdefault("mcp.server", MagicMock())
sys.modules.setdefault("mcp.server.fastmcp", MagicMock())


class TestDbStatusHandler:
    @patch("dazzle.mcp.server.handlers.db.get_connection")
    @patch("dazzle.mcp.server.handlers.db.load_project_appspec")
    def test_returns_status_json(
        self, mock_load: MagicMock, mock_conn_factory: MagicMock
    ) -> None:
        from dazzle.mcp.server.handlers.db import db_status_handler

        appspec = MagicMock()
        e1 = MagicMock()
        e1.name = "Task"
        appspec.domain.entities = [e1]
        mock_load.return_value = appspec

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(side_effect=[10, "1 MB"])
        mock_conn.close = AsyncMock()

        import asyncio

        async def fake_connect(**kw: object) -> AsyncMock:
            return mock_conn

        mock_conn_factory.side_effect = fake_connect

        project_path = Path("/fake/project")
        args: dict[str, object] = {"_progress": MagicMock()}
        result_str = db_status_handler(project_path, args)
        result = json.loads(result_str)
        assert "entities" in result or "total_rows" in result


class TestDbVerifyHandler:
    @patch("dazzle.mcp.server.handlers.db.get_connection")
    @patch("dazzle.mcp.server.handlers.db.load_project_appspec")
    def test_returns_verify_json(
        self, mock_load: MagicMock, mock_conn_factory: MagicMock
    ) -> None:
        from dazzle.mcp.server.handlers.db import db_verify_handler

        appspec = MagicMock()
        appspec.domain.entities = []
        mock_load.return_value = appspec

        mock_conn = AsyncMock()
        mock_conn.close = AsyncMock()

        import asyncio

        async def fake_connect(**kw: object) -> AsyncMock:
            return mock_conn

        mock_conn_factory.side_effect = fake_connect

        project_path = Path("/fake/project")
        args: dict[str, object] = {"_progress": MagicMock()}
        result_str = db_verify_handler(project_path, args)
        result = json.loads(result_str)
        assert "checks" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/mcp/test_db_handlers.py -v`
Expected: FAIL — handler module doesn't exist

- [ ] **Step 3: Create MCP handler**

```python
# src/dazzle/mcp/server/handlers/db.py
"""Database operations MCP handlers.

Read-only operations: status, verify.
Write operations (reset, cleanup) are CLI-only per MCP/CLI boundary.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .common import extract_progress, load_project_appspec, wrap_handler_errors


async def get_connection(*, project_root: Path) -> Any:
    """Get asyncpg connection for the project."""
    from dazzle.db.connection import get_connection as _get_conn

    return await _get_conn(project_root=project_root)


@wrap_handler_errors
def db_status_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Row counts per entity, database size."""
    progress = extract_progress(args)
    progress.log_sync("Querying database status...")

    appspec = load_project_appspec(project_path)
    entities = appspec.domain.entities

    from dazzle.db.status import db_status_impl

    async def _run() -> dict[str, Any]:
        conn = await get_connection(project_root=project_path)
        try:
            return await db_status_impl(entities=entities, conn=conn)
        finally:
            await conn.close()

    result = asyncio.run(_run())
    return json.dumps(result, indent=2)


@wrap_handler_errors
def db_verify_handler(project_path: Path, args: dict[str, Any]) -> str:
    """FK integrity check with findings list."""
    progress = extract_progress(args)
    progress.log_sync("Verifying FK integrity...")

    appspec = load_project_appspec(project_path)
    entities = appspec.domain.entities

    from dazzle.db.verify import db_verify_impl

    async def _run() -> dict[str, Any]:
        conn = await get_connection(project_root=project_path)
        try:
            return await db_verify_impl(entities=entities, conn=conn)
        finally:
            await conn.close()

    result = asyncio.run(_run())
    return json.dumps(result, indent=2)
```

- [ ] **Step 4: Register in handlers_consolidated.py**

Add after the existing `handle_mock` block (around line 268):

```python
# =============================================================================
# DB Handler
# =============================================================================

_MOD_DB = "dazzle.mcp.server.handlers.db"

handle_db: Callable[[dict[str, Any]], str] = _make_project_handler(
    "db",
    {
        "status": f"{_MOD_DB}:db_status_handler",
        "verify": f"{_MOD_DB}:db_verify_handler",
    },
)
```

Add `"db": handle_db,` to `CONSOLIDATED_TOOL_HANDLERS` dict (around line 1017).

- [ ] **Step 5: Register tool definition in tools_consolidated.py**

Add to the `get_consolidated_tools()` return list:

```python
# =====================================================================
# DB Operations (read-only — write ops are CLI-only)
# =====================================================================
Tool(
    name="db",
    description="Database operations: status (row counts per entity, database size), verify (FK integrity check, orphan detection).",
    inputSchema={
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["status", "verify"],
                "description": "Operation to perform",
            },
            **PROJECT_PATH_SCHEMA,
        },
        "required": ["operation"],
    },
),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/mcp/test_db_handlers.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/mcp/server/handlers/db.py src/dazzle/mcp/server/handlers_consolidated.py src/dazzle/mcp/server/tools_consolidated.py tests/unit/mcp/test_db_handlers.py
git commit -m "feat(db): add MCP handlers for db status and verify"
```

---

## Task 9: Update Package Exports and Documentation

**Files:**
- Modify: `src/dazzle/db/__init__.py`
- Modify: `docs/superpowers/specs/2026-03-18-dazzle-db-design.md` (update status to "Implemented")

- [ ] **Step 1: Update `__init__.py` with public API**

```python
# src/dazzle/db/__init__.py
"""DSL-driven database operations.

Layer A (zero-config, DSL-derived):
  - status: row counts per entity, database size
  - verify: FK integrity checks, orphan detection
  - reset: truncate entity tables in dependency order
  - cleanup: find and remove FK orphans

Layer B (provider-pluggable backup/restore) lives in dazzle.cli.backup.
"""

from .cleanup import db_cleanup_impl
from .connection import get_connection, resolve_db_url
from .graph import build_dependency_graph, get_ref_fields, leaves_first, parents_first
from .reset import db_reset_impl
from .sql import quote_id
from .status import db_status_impl
from .verify import db_verify_impl

__all__ = [
    "build_dependency_graph",
    "db_cleanup_impl",
    "db_reset_impl",
    "db_status_impl",
    "db_verify_impl",
    "get_connection",
    "get_ref_fields",
    "leaves_first",
    "parents_first",
    "quote_id",
    "resolve_db_url",
]
```

- [ ] **Step 2: Update CLAUDE.md command reference**

In `/Volumes/SSD/Dazzle/.claude/CLAUDE.md`, add `db` to the MCP tools table:

```markdown
| `db` | status, verify |
```

And update the CLI commands section to include the new db operations.

- [ ] **Step 3: Run full test suite to verify nothing is broken**

Run: `pytest tests/unit/test_db_*.py tests/unit/test_cli_db_ops.py tests/unit/mcp/test_db_handlers.py -v`
Expected: All PASS

- [ ] **Step 4: Run lint**

Run: `ruff check src/dazzle/db/ src/dazzle/cli/db.py src/dazzle/mcp/server/handlers/db.py --fix && ruff format src/dazzle/db/ src/dazzle/cli/db.py src/dazzle/mcp/server/handlers/db.py`
Expected: No errors

- [ ] **Step 5: Run mypy**

Run: `mypy src/dazzle/db/`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/db/__init__.py .claude/CLAUDE.md
git commit -m "feat(db): finalize package exports and update docs"
```
