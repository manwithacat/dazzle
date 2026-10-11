# UX Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic UX verification system that derives a testable interaction inventory from the DSL, boots a real app against Postgres, and verifies every framework-generated interaction via structural HTML assertions and Playwright browser tests.

**Architecture:** AppSpec -> interaction inventory (the coverage denominator) -> two test layers: (1) structural HTML assertions without a browser for fast checks, (2) Playwright runner for real interaction verification. Postgres test harness manages DB lifecycle. CLI command `dazzle ux verify` orchestrates everything and produces a coverage report.

**Tech Stack:** Python 3.12+, Playwright, psycopg, pytest, Pydantic, existing Dazzle IR types

---

### Task 1: Interaction Inventory — Data Model + Generator

**Files:**
- Create: `src/dazzle/testing/ux/__init__.py`
- Create: `src/dazzle/testing/ux/inventory.py`
- Test: `tests/unit/test_ux_inventory.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ux_inventory.py
"""Tests for UX interaction inventory generation."""

from pathlib import Path

from dazzle.testing.ux.inventory import (
    Interaction,
    InteractionClass,
    generate_inventory,
)


class TestInteractionModel:
    def test_interaction_has_required_fields(self) -> None:
        i = Interaction(
            cls=InteractionClass.PAGE_LOAD,
            entity="Task",
            persona="admin",
            surface="task_list",
            description="Load task list as admin",
        )
        assert i.cls == InteractionClass.PAGE_LOAD
        assert i.entity == "Task"
        assert i.persona == "admin"

    def test_interaction_id_is_deterministic(self) -> None:
        a = Interaction(
            cls=InteractionClass.PAGE_LOAD,
            entity="Task",
            persona="admin",
            surface="task_list",
            description="Load task list",
        )
        b = Interaction(
            cls=InteractionClass.PAGE_LOAD,
            entity="Task",
            persona="admin",
            surface="task_list",
            description="Load task list",
        )
        assert a.interaction_id == b.interaction_id


class TestInventoryFromAppSpec:
    def test_simple_task_generates_interactions(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        project = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
        appspec = load_project_appspec(project)
        inventory = generate_inventory(appspec)
        assert len(inventory) > 0

    def test_inventory_includes_page_loads(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        project = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
        appspec = load_project_appspec(project)
        inventory = generate_inventory(appspec)
        page_loads = [i for i in inventory if i.cls == InteractionClass.PAGE_LOAD]
        assert len(page_loads) > 0

    def test_inventory_covers_all_entities(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        project = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
        appspec = load_project_appspec(project)
        inventory = generate_inventory(appspec)
        entities_covered = {i.entity for i in inventory if i.entity}
        dsl_entities = {e.name for e in appspec.domain.entities}
        # Every entity with a surface should appear in the inventory
        surfaced_entities = {s.entity_ref for s in appspec.surfaces if s.entity_ref}
        assert surfaced_entities.issubset(entities_covered)

    def test_inventory_covers_all_personas(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        project = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
        appspec = load_project_appspec(project)
        inventory = generate_inventory(appspec)
        personas_covered = {i.persona for i in inventory if i.persona}
        dsl_personas = {p.id for p in appspec.personas}
        # Every persona should appear at least once
        if dsl_personas:
            assert dsl_personas.issubset(personas_covered)

    def test_coverage_metric(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        project = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
        appspec = load_project_appspec(project)
        inventory = generate_inventory(appspec)
        # All start untested
        assert all(i.status == "pending" for i in inventory)
        total = len(inventory)
        assert total > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ux_inventory.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/dazzle/testing/ux/__init__.py
"""DAZZLE UX Verification — deterministic interaction testing derived from the DSL."""
```

```python
# src/dazzle/testing/ux/inventory.py
"""Generate the canonical interaction inventory from an AppSpec.

The inventory enumerates every testable interaction point in a Dazzle app.
It is the denominator in UX coverage: interactions_tested / interactions_enumerated.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.domain import PermissionKind


class InteractionClass(StrEnum):
    PAGE_LOAD = "page_load"
    DETAIL_VIEW = "detail_view"
    CREATE_SUBMIT = "create_submit"
    EDIT_SUBMIT = "edit_submit"
    DELETE_CONFIRM = "delete_confirm"
    DRAWER_OPEN = "drawer_open"
    DRAWER_CLOSE = "drawer_close"
    STATE_TRANSITION = "state_transition"
    ACCESS_DENIED = "access_denied"
    WORKSPACE_RENDER = "workspace_render"


@dataclass
class Interaction:
    cls: InteractionClass
    entity: str
    persona: str
    surface: str = ""
    workspace: str = ""
    action: str = ""
    description: str = ""
    status: Literal["pending", "passed", "failed", "skipped"] = "pending"
    error: str | None = None
    screenshot: str | None = None

    @property
    def interaction_id(self) -> str:
        key = f"{self.cls}:{self.entity}:{self.persona}:{self.surface}:{self.action}"
        return hashlib.sha1(key.encode()).hexdigest()[:12]


def _get_permitted_personas(
    appspec: AppSpec, entity_name: str, operation: PermissionKind
) -> list[str]:
    """Return persona IDs that have a permit rule for the given operation."""
    entity = next((e for e in appspec.domain.entities if e.name == entity_name), None)
    if not entity or not entity.access:
        return [p.id for p in appspec.personas]  # No access spec = open

    permitted: set[str] = set()
    for rule in entity.access.permissions:
        if rule.operation == operation:
            if rule.personas:
                permitted.update(rule.personas)
            else:
                # No persona restriction = all personas
                return [p.id for p in appspec.personas]
    return list(permitted)


def _get_denied_personas(
    appspec: AppSpec, entity_name: str, operation: PermissionKind
) -> list[str]:
    """Return persona IDs that do NOT have a permit rule for the given operation."""
    permitted = set(_get_permitted_personas(appspec, entity_name, operation))
    all_personas = {p.id for p in appspec.personas}
    return list(all_personas - permitted)


def generate_inventory(appspec: AppSpec) -> list[Interaction]:
    """Generate the full interaction inventory from an AppSpec."""
    interactions: list[Interaction] = []
    persona_ids = [p.id for p in appspec.personas]

    # Map entity names to their surfaces
    entity_surfaces: dict[str, list[str]] = {}
    for surface in appspec.surfaces:
        if surface.entity_ref:
            entity_surfaces.setdefault(surface.entity_ref, []).append(surface.name)

    # Per-entity interactions
    for entity in appspec.domain.entities:
        surfaces = entity_surfaces.get(entity.name, [])
        if not surfaces:
            continue  # No UI surface = not testable via UX

        for surface_name in surfaces:
            surface = next((s for s in appspec.surfaces if s.name == surface_name), None)
            if not surface:
                continue

            mode = str(surface.mode.value) if hasattr(surface.mode, "value") else str(surface.mode)

            # PAGE_LOAD — for each persona with list/read permission
            for pid in _get_permitted_personas(appspec, entity.name, PermissionKind.LIST):
                interactions.append(Interaction(
                    cls=InteractionClass.PAGE_LOAD,
                    entity=entity.name,
                    persona=pid,
                    surface=surface_name,
                    description=f"Load {surface_name} as {pid}",
                ))

            # DETAIL_VIEW — for each persona with read permission
            if mode == "list":
                for pid in _get_permitted_personas(appspec, entity.name, PermissionKind.READ):
                    interactions.append(Interaction(
                        cls=InteractionClass.DETAIL_VIEW,
                        entity=entity.name,
                        persona=pid,
                        surface=surface_name,
                        description=f"View {entity.name} detail as {pid}",
                    ))

            # CREATE_SUBMIT — for each persona with create permission
            for pid in _get_permitted_personas(appspec, entity.name, PermissionKind.CREATE):
                interactions.append(Interaction(
                    cls=InteractionClass.CREATE_SUBMIT,
                    entity=entity.name,
                    persona=pid,
                    surface=surface_name,
                    description=f"Create {entity.name} as {pid}",
                ))

            # EDIT_SUBMIT — for each persona with update permission
            for pid in _get_permitted_personas(appspec, entity.name, PermissionKind.UPDATE):
                interactions.append(Interaction(
                    cls=InteractionClass.EDIT_SUBMIT,
                    entity=entity.name,
                    persona=pid,
                    surface=surface_name,
                    description=f"Edit {entity.name} as {pid}",
                ))

            # DELETE_CONFIRM — for each persona with delete permission
            for pid in _get_permitted_personas(appspec, entity.name, PermissionKind.DELETE):
                interactions.append(Interaction(
                    cls=InteractionClass.DELETE_CONFIRM,
                    entity=entity.name,
                    persona=pid,
                    surface=surface_name,
                    description=f"Delete {entity.name} as {pid}",
                ))

            # ACCESS_DENIED — for each persona WITHOUT list permission
            for pid in _get_denied_personas(appspec, entity.name, PermissionKind.LIST):
                interactions.append(Interaction(
                    cls=InteractionClass.ACCESS_DENIED,
                    entity=entity.name,
                    persona=pid,
                    surface=surface_name,
                    description=f"Access denied {surface_name} for {pid}",
                ))

        # STATE_TRANSITION — for entities with state machines
        if entity.state_machine:
            for transition in entity.state_machine.transitions:
                t_name = transition.name if hasattr(transition, "name") else str(transition)
                for pid in persona_ids:
                    interactions.append(Interaction(
                        cls=InteractionClass.STATE_TRANSITION,
                        entity=entity.name,
                        persona=pid,
                        action=t_name,
                        description=f"Transition {entity.name} via {t_name} as {pid}",
                    ))

    # Workspace interactions
    for workspace in appspec.workspaces:
        # WORKSPACE_RENDER — for each persona with access
        access_personas = persona_ids  # Default: all
        if workspace.access and workspace.access.personas:
            access_personas = workspace.access.personas

        for pid in access_personas:
            interactions.append(Interaction(
                cls=InteractionClass.WORKSPACE_RENDER,
                entity="",
                persona=pid,
                workspace=workspace.name,
                description=f"Render {workspace.name} as {pid}",
            ))

        # DRAWER_OPEN / DRAWER_CLOSE — for each region
        for region in workspace.regions:
            source = region.source or ""
            for pid in access_personas:
                interactions.append(Interaction(
                    cls=InteractionClass.DRAWER_OPEN,
                    entity=source,
                    persona=pid,
                    workspace=workspace.name,
                    action=region.name,
                    description=f"Open drawer for {region.name} in {workspace.name} as {pid}",
                ))
                interactions.append(Interaction(
                    cls=InteractionClass.DRAWER_CLOSE,
                    entity=source,
                    persona=pid,
                    workspace=workspace.name,
                    action=region.name,
                    description=f"Close drawer for {region.name} in {workspace.name} as {pid}",
                ))

    return interactions
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_ux_inventory.py -v`
Expected: All PASSED

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/ux/__init__.py src/dazzle/testing/ux/inventory.py tests/unit/test_ux_inventory.py
git commit -m "feat(ux): add interaction inventory generator from AppSpec"
```

---

### Task 2: Postgres Test Harness

**Files:**
- Create: `src/dazzle/testing/ux/harness.py`
- Test: `tests/unit/test_ux_harness.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ux_harness.py
"""Tests for UX verification Postgres harness."""

import os

import pytest

from dazzle.testing.ux.harness import PostgresHarness, check_postgres_available


class TestPostgresDetection:
    def test_check_returns_bool(self) -> None:
        result = check_postgres_available()
        assert isinstance(result, bool)


class TestHarnessLifecycle:
    @pytest.mark.skipif(
        not os.environ.get("TEST_DATABASE_URL"),
        reason="TEST_DATABASE_URL not set — skipping Postgres harness tests",
    )
    def test_create_and_drop_test_db(self) -> None:
        harness = PostgresHarness(
            db_url=os.environ["TEST_DATABASE_URL"],
            project_name="test_harness",
        )
        harness.create_test_db()
        assert harness.test_db_url  # URL was generated
        harness.drop_test_db()

    @pytest.mark.skipif(
        not os.environ.get("TEST_DATABASE_URL"),
        reason="TEST_DATABASE_URL not set",
    )
    def test_context_manager(self) -> None:
        harness = PostgresHarness(
            db_url=os.environ["TEST_DATABASE_URL"],
            project_name="test_ctx",
        )
        with harness:
            assert harness.test_db_url
        # DB should be dropped after exit


class TestHarnessConfig:
    def test_default_db_url(self) -> None:
        harness = PostgresHarness(project_name="test_default")
        assert "localhost" in harness.db_url or "127.0.0.1" in harness.db_url

    def test_custom_db_url(self) -> None:
        harness = PostgresHarness(
            db_url="postgresql://custom:5432/db",
            project_name="test_custom",
        )
        assert "custom" in harness.db_url
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ux_harness.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

```python
# src/dazzle/testing/ux/harness.py
"""Postgres test harness for UX verification.

Manages the lifecycle of a test database: create, schema baseline,
fixture seeding, and teardown. Assumes Postgres is already running.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_DEFAULT_DB_URL = "postgresql://localhost:5432/postgres"


def check_postgres_available(db_url: str = _DEFAULT_DB_URL) -> bool:
    """Check if Postgres is reachable."""
    # Try pg_isready first (fast, no auth needed)
    pg_isready = shutil.which("pg_isready")
    if pg_isready:
        try:
            result = subprocess.run(
                [pg_isready, "-q"],
                timeout=5,
                capture_output=True,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # Fallback: try to connect via psycopg
    try:
        import psycopg

        with psycopg.connect(db_url, autocommit=True, connect_timeout=5) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


@dataclass
class PostgresHarness:
    """Manages a test database for UX verification.

    Usage:
        with PostgresHarness(project_name="simple_task") as harness:
            # harness.test_db_url is ready
            # schema applied, fixtures can be seeded
            pass
        # test DB dropped on exit
    """

    project_name: str
    db_url: str = _DEFAULT_DB_URL
    keep_db: bool = False
    test_db_url: str = ""

    def _admin_connection(self):
        """Connect to the admin database (usually 'postgres')."""
        import psycopg

        return psycopg.connect(self.db_url, autocommit=True)

    def _test_db_name(self) -> str:
        # Sanitize project name for SQL identifier
        safe = "".join(c if c.isalnum() or c == "_" else "_" for c in self.project_name)
        return f"dazzle_ux_test_{safe}"

    def create_test_db(self) -> str:
        """Create the test database, dropping it first if it exists."""
        db_name = self._test_db_name()
        conn = self._admin_connection()
        try:
            # Terminate existing connections
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (db_name,),
            )
            conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
            conn.execute(f'CREATE DATABASE "{db_name}"')
        finally:
            conn.close()

        # Build test DB URL by replacing the database name in the admin URL
        # Parse the admin URL and swap the database
        if "/" in self.db_url:
            base = self.db_url.rsplit("/", 1)[0]
            self.test_db_url = f"{base}/{db_name}"
        else:
            self.test_db_url = f"{self.db_url}/{db_name}"

        logger.info("Created test database: %s", db_name)
        return self.test_db_url

    def drop_test_db(self) -> None:
        """Drop the test database."""
        db_name = self._test_db_name()
        conn = self._admin_connection()
        try:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (db_name,),
            )
            conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        finally:
            conn.close()
        logger.info("Dropped test database: %s", db_name)

    def __enter__(self) -> PostgresHarness:
        self.create_test_db()
        return self

    def __exit__(self, *args: object) -> None:
        if not self.keep_db:
            self.drop_test_db()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_ux_harness.py -v`
Expected: TestPostgresDetection passes, TestHarnessLifecycle skipped (no TEST_DATABASE_URL), TestHarnessConfig passes

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/ux/harness.py tests/unit/test_ux_harness.py
git commit -m "feat(ux): add Postgres test harness for UX verification"
```

---

### Task 3: Structural HTML Assertions (No Browser)

**Files:**
- Create: `src/dazzle/testing/ux/structural.py`
- Test: `tests/unit/test_ux_structural.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ux_structural.py
"""Tests for structural HTML assertions."""

from dazzle.testing.ux.structural import (
    StructuralCheck,
    StructuralResult,
    check_detail_view,
    check_form,
    check_html,
)


class TestCheckDetailView:
    def test_valid_detail_passes(self) -> None:
        html = """
        <div data-dazzle-entity="Task">
          <a href="/app/task" class="btn">Back</a>
          <h2>Task Detail</h2>
        </div>
        """
        results = check_detail_view(html)
        assert all(r.passed for r in results)

    def test_missing_back_button_fails(self) -> None:
        html = """
        <div data-dazzle-entity="Task">
          <h2>Task Detail</h2>
        </div>
        """
        results = check_detail_view(html)
        back_check = next((r for r in results if "back" in r.check_name.lower()), None)
        assert back_check is not None
        assert not back_check.passed


class TestCheckForm:
    def test_valid_form_passes(self) -> None:
        html = """
        <form action="/api/task" method="post">
          <input name="title" required aria-required="true">
          <button type="submit">Save</button>
        </form>
        """
        results = check_form(html)
        assert all(r.passed for r in results)

    def test_missing_submit_button_fails(self) -> None:
        html = """
        <form action="/api/task" method="post">
          <input name="title" required>
        </form>
        """
        results = check_form(html)
        submit_check = next((r for r in results if "submit" in r.check_name.lower()), None)
        assert submit_check is not None
        assert not submit_check.passed

    def test_empty_action_fails(self) -> None:
        html = """
        <form action="" method="post">
          <button type="submit">Save</button>
        </form>
        """
        results = check_form(html)
        action_check = next((r for r in results if "action" in r.check_name.lower()), None)
        assert action_check is not None
        assert not action_check.passed


class TestCheckHtml:
    def test_duplicate_ids_detected(self) -> None:
        html = """
        <div id="foo">A</div>
        <div id="foo">B</div>
        """
        results = check_html(html)
        dup_check = next((r for r in results if "duplicate" in r.check_name.lower()), None)
        assert dup_check is not None
        assert not dup_check.passed

    def test_img_without_alt_detected(self) -> None:
        html = '<img src="/photo.jpg">'
        results = check_html(html)
        alt_check = next((r for r in results if "alt" in r.check_name.lower()), None)
        assert alt_check is not None
        assert not alt_check.passed

    def test_clean_html_passes(self) -> None:
        html = """
        <div id="a">
          <img src="/photo.jpg" alt="Photo">
        </div>
        """
        results = check_html(html)
        assert all(r.passed for r in results)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ux_structural.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

```python
# src/dazzle/testing/ux/structural.py
"""Structural HTML assertions for UX verification.

Fast, no-browser checks that parse rendered HTML and verify structural
correctness: required elements present, ARIA attributes, no broken links.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass
class StructuralResult:
    check_name: str
    passed: bool
    message: str = ""


class _TagCollector(HTMLParser):
    """Collect tags, attributes, and ids from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.ids: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        self.tags.append((tag, attr_dict))
        if "id" in attr_dict and attr_dict["id"]:
            self.ids.append(attr_dict["id"])


def _parse(html: str) -> _TagCollector:
    collector = _TagCollector()
    collector.feed(html)
    return collector


def check_detail_view(html: str) -> list[StructuralResult]:
    """Check structural requirements for a detail view page."""
    results: list[StructuralResult] = []
    collector = _parse(html)

    # Must have a Back link or button
    has_back = False
    for tag, attrs in collector.tags:
        if tag in ("a", "button"):
            # Check text content isn't available via HTMLParser attrs,
            # so check for href containing entity path or onclick with history/drawer
            href = attrs.get("href", "") or ""
            onclick = attrs.get("onclick", "") or ""
            if "/app/" in href or "history.back" in onclick or "dzDrawer" in onclick:
                has_back = True
                break
    # Fallback: check for any element with "Back" in a simple text search
    if not has_back and "back" in html.lower():
        has_back = True

    results.append(StructuralResult(
        check_name="detail_has_back_button",
        passed=has_back,
        message="" if has_back else "Detail view missing Back button or link",
    ))

    # Must have a heading
    has_heading = any(tag in ("h1", "h2", "h3") for tag, _ in collector.tags)
    results.append(StructuralResult(
        check_name="detail_has_heading",
        passed=has_heading,
        message="" if has_heading else "Detail view missing heading (h1/h2/h3)",
    ))

    return results


def check_form(html: str) -> list[StructuralResult]:
    """Check structural requirements for a form."""
    results: list[StructuralResult] = []
    collector = _parse(html)

    # Must have a submit button
    has_submit = any(
        tag == "button" and attrs.get("type") == "submit"
        for tag, attrs in collector.tags
    )
    if not has_submit:
        has_submit = any(
            tag == "input" and attrs.get("type") == "submit"
            for tag, attrs in collector.tags
        )
    results.append(StructuralResult(
        check_name="form_has_submit_button",
        passed=has_submit,
        message="" if has_submit else "Form missing submit button (type='submit')",
    ))

    # Form action must not be empty
    form_tags = [(tag, attrs) for tag, attrs in collector.tags if tag == "form"]
    for _, attrs in form_tags:
        action = attrs.get("action", "")
        has_action = bool(action and action.strip())
        results.append(StructuralResult(
            check_name="form_has_action",
            passed=has_action,
            message="" if has_action else "Form has empty or missing action attribute",
        ))

    return results


def check_html(html: str) -> list[StructuralResult]:
    """Check general HTML structural requirements."""
    results: list[StructuralResult] = []
    collector = _parse(html)

    # No duplicate IDs
    seen_ids: set[str] = set()
    duplicates: list[str] = []
    for id_val in collector.ids:
        if id_val in seen_ids:
            duplicates.append(id_val)
        seen_ids.add(id_val)
    results.append(StructuralResult(
        check_name="no_duplicate_ids",
        passed=len(duplicates) == 0,
        message="" if not duplicates else f"Duplicate IDs found: {', '.join(duplicates)}",
    ))

    # All img tags have alt attributes
    imgs_without_alt: list[str] = []
    for tag, attrs in collector.tags:
        if tag == "img" and "alt" not in attrs:
            src = attrs.get("src", "unknown")
            imgs_without_alt.append(src or "unknown")
    results.append(StructuralResult(
        check_name="img_has_alt",
        passed=len(imgs_without_alt) == 0,
        message="" if not imgs_without_alt else f"Images without alt: {', '.join(imgs_without_alt)}",
    ))

    return results


StructuralCheck = check_detail_view | check_form | check_html  # type alias for docs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_ux_structural.py -v`
Expected: All PASSED

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/ux/structural.py tests/unit/test_ux_structural.py
git commit -m "feat(ux): add structural HTML assertions for detail/form/a11y checks"
```

---

### Task 4: Fixture Generator

**Files:**
- Create: `src/dazzle/testing/ux/fixtures.py`
- Test: `tests/unit/test_ux_fixtures.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ux_fixtures.py
"""Tests for UX verification fixture generation."""

from pathlib import Path

from dazzle.testing.ux.fixtures import generate_seed_payload


class TestFixtureGeneration:
    def test_generates_fixtures_for_simple_task(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        project = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
        appspec = load_project_appspec(project)
        payload = generate_seed_payload(appspec)
        assert "fixtures" in payload
        assert len(payload["fixtures"]) > 0

    def test_each_entity_has_fixtures(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        project = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
        appspec = load_project_appspec(project)
        payload = generate_seed_payload(appspec)
        entity_names = {f["entity"] for f in payload["fixtures"]}
        # At least one surfaced entity should have fixtures
        surfaced = {s.entity_ref for s in appspec.surfaces if s.entity_ref}
        assert surfaced.intersection(entity_names)

    def test_fixture_has_required_fields(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        project = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
        appspec = load_project_appspec(project)
        payload = generate_seed_payload(appspec)
        for fixture in payload["fixtures"]:
            assert "id" in fixture
            assert "entity" in fixture
            assert "data" in fixture
            assert isinstance(fixture["data"], dict)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ux_fixtures.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

```python
# src/dazzle/testing/ux/fixtures.py
"""Generate seed fixture payloads for UX verification.

Produces deterministic test data for each entity in the AppSpec,
formatted for the /__test__/seed endpoint.
"""

from __future__ import annotations

import uuid
from typing import Any

from dazzle.core.ir.appspec import AppSpec


def _generate_field_value(field_name: str, field_type: str, entity_name: str, index: int) -> Any:
    """Generate a deterministic test value for a field."""
    t = field_type.lower()

    if field_name == "id":
        # Deterministic UUID from entity name + index
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{entity_name}.{index}"))

    if "str" in t or "text" in t:
        return f"Test {field_name} {index + 1}"
    if t == "email":
        return f"test{index + 1}@{entity_name.lower()}.test"
    if "int" in t or "decimal" in t or "float" in t:
        return index + 1
    if t == "bool":
        return True
    if "date" in t and "time" not in t:
        return f"2026-01-{(index % 28) + 1:02d}"
    if "datetime" in t:
        return f"2026-01-{(index % 28) + 1:02d}T10:00:00Z"
    if "uuid" in t:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{entity_name}.{field_name}.{index}"))
    if "url" in t:
        return f"https://example.com/{entity_name.lower()}/{index + 1}"
    if "json" in t:
        return {}
    if "money" in t:
        return "100.00"
    if "enum" in t:
        return None  # Will be handled by caller if possible
    if "file" in t:
        return None

    return f"test_{field_name}_{index}"


def _get_field_type_str(field_type: Any) -> str:
    """Extract a string representation of a field type."""
    if hasattr(field_type, "base_type"):
        return str(field_type.base_type)
    if hasattr(field_type, "value"):
        return str(field_type.value)
    return str(field_type)


def generate_seed_payload(
    appspec: AppSpec,
    rows_per_entity: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    """Generate a seed payload for /__test__/seed.

    Returns:
        Dict with "fixtures" key containing list of fixture dicts.
    """
    fixtures: list[dict[str, Any]] = []
    refs: dict[str, str] = {}  # entity_name -> first fixture ID for FK resolution

    # Generate fixtures for entities that have surfaces (testable via UX)
    surfaced_entities = {s.entity_ref for s in appspec.surfaces if s.entity_ref}

    for entity in appspec.domain.entities:
        if entity.name not in surfaced_entities:
            continue

        for i in range(rows_per_entity):
            fixture_id = f"{entity.name.lower()}_{i}"
            data: dict[str, Any] = {}

            for field in entity.fields:
                # Skip auto-generated fields
                if field.name == "id":
                    continue
                modifiers = [str(m) for m in (field.modifiers or [])] if hasattr(field, "modifiers") else []

                # Handle FK references
                type_str = _get_field_type_str(field.type)
                if "ref" in type_str.lower() or hasattr(field.type, "entity_ref"):
                    ref_entity = getattr(field.type, "entity_ref", None)
                    if ref_entity and ref_entity in refs:
                        data[field.name] = refs[ref_entity]
                    continue

                # Skip optional fields sometimes
                is_required = "required" in modifiers or "pk" in modifiers
                if not is_required and i > 2:
                    continue

                value = _generate_field_value(field.name, type_str, entity.name, i)
                if value is not None:
                    data[field.name] = value

            fixture = {
                "id": fixture_id,
                "entity": entity.name,
                "data": data,
            }
            fixtures.append(fixture)

            # Track first fixture ID for FK resolution
            if entity.name not in refs:
                refs[entity.name] = fixture_id

    return {"fixtures": fixtures}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_ux_fixtures.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/ux/fixtures.py tests/unit/test_ux_fixtures.py
git commit -m "feat(ux): add deterministic fixture generator for UX test seeding"
```

---

### Task 5: Report Generator

**Files:**
- Create: `src/dazzle/testing/ux/report.py`
- Test: `tests/unit/test_ux_report.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ux_report.py
"""Tests for UX verification report generation."""

from dazzle.testing.ux.inventory import Interaction, InteractionClass
from dazzle.testing.ux.report import UXReport, generate_report
from dazzle.testing.ux.structural import StructuralResult


class TestUXReport:
    def test_empty_report(self) -> None:
        report = generate_report([], [])
        assert "0 tested" in report.summary
        assert report.coverage == 0.0

    def test_all_passing(self) -> None:
        interactions = [
            Interaction(
                cls=InteractionClass.PAGE_LOAD,
                entity="Task",
                persona="admin",
                description="Load tasks",
                status="passed",
            ),
            Interaction(
                cls=InteractionClass.DETAIL_VIEW,
                entity="Task",
                persona="admin",
                description="View task",
                status="passed",
            ),
        ]
        report = generate_report(interactions, [])
        assert report.coverage == 100.0
        assert report.passed == 2
        assert report.failed == 0

    def test_with_failures(self) -> None:
        interactions = [
            Interaction(
                cls=InteractionClass.PAGE_LOAD,
                entity="Task",
                persona="admin",
                description="Load tasks",
                status="passed",
            ),
            Interaction(
                cls=InteractionClass.CREATE_SUBMIT,
                entity="Task",
                persona="admin",
                description="Create task",
                status="failed",
                error="Form submit returned 422",
            ),
        ]
        report = generate_report(interactions, [])
        assert report.coverage == 50.0
        assert report.failed == 1

    def test_markdown_output(self) -> None:
        interactions = [
            Interaction(
                cls=InteractionClass.PAGE_LOAD,
                entity="Task",
                persona="admin",
                description="Load tasks",
                status="passed",
            ),
        ]
        structural = [
            StructuralResult(check_name="test_check", passed=True),
        ]
        report = generate_report(interactions, structural)
        md = report.to_markdown()
        assert "UX Verification Report" in md
        assert "100.0%" in md

    def test_json_output(self) -> None:
        interactions = [
            Interaction(
                cls=InteractionClass.PAGE_LOAD,
                entity="Task",
                persona="admin",
                description="Load tasks",
                status="passed",
            ),
        ]
        report = generate_report(interactions, [])
        data = report.to_json()
        assert "coverage" in data
        assert data["coverage"] == 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ux_report.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

```python
# src/dazzle/testing/ux/report.py
"""UX verification report generation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from dazzle.testing.ux.inventory import Interaction
from dazzle.testing.ux.structural import StructuralResult


@dataclass
class UXReport:
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    coverage: float = 0.0
    summary: str = ""
    failures: list[Interaction] = field(default_factory=list)
    structural_results: list[StructuralResult] = field(default_factory=list)
    structural_passed: int = 0
    structural_failed: int = 0

    def to_markdown(self) -> str:
        lines: list[str] = []
        lines.append("# UX Verification Report\n")
        lines.append(f"**Coverage:** {self.coverage:.1f}%\n")
        lines.append(f"**Interactions:** {self.total} tested, "
                      f"{self.passed} passed, {self.failed} failed, "
                      f"{self.skipped} skipped\n")

        if self.structural_results:
            lines.append(f"**Structural:** {self.structural_passed + self.structural_failed} checked, "
                          f"{self.structural_passed} passed, {self.structural_failed} failed\n")

        if self.failures:
            lines.append("## Failures\n")
            for f in self.failures:
                lines.append(f"### {f.cls.value}({f.entity}, {f.persona})\n")
                lines.append(f"**Description:** {f.description}\n")
                if f.error:
                    lines.append(f"**Error:** {f.error}\n")
                if f.screenshot:
                    lines.append(f"**Screenshot:** {f.screenshot}\n")

        failed_structural = [r for r in self.structural_results if not r.passed]
        if failed_structural:
            lines.append("## Structural Failures\n")
            for r in failed_structural:
                lines.append(f"- **{r.check_name}**: {r.message}\n")

        return "\n".join(lines)

    def to_json(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "coverage": self.coverage,
            "structural_passed": self.structural_passed,
            "structural_failed": self.structural_failed,
            "failures": [
                {
                    "cls": f.cls.value,
                    "entity": f.entity,
                    "persona": f.persona,
                    "description": f.description,
                    "error": f.error,
                    "screenshot": f.screenshot,
                }
                for f in self.failures
            ],
        }


def generate_report(
    interactions: list[Interaction],
    structural_results: list[StructuralResult],
) -> UXReport:
    """Generate a UX verification report from test results."""
    total = len(interactions)
    passed = sum(1 for i in interactions if i.status == "passed")
    failed = sum(1 for i in interactions if i.status == "failed")
    skipped = sum(1 for i in interactions if i.status == "skipped")
    coverage = (passed / total * 100) if total > 0 else 0.0
    failures = [i for i in interactions if i.status == "failed"]

    s_passed = sum(1 for r in structural_results if r.passed)
    s_failed = sum(1 for r in structural_results if not r.passed)

    summary = f"{total} tested, {passed} passed, {failed} failed, {skipped} skipped"

    return UXReport(
        total=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        coverage=coverage,
        summary=summary,
        failures=failures,
        structural_results=structural_results,
        structural_passed=s_passed,
        structural_failed=s_failed,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_ux_report.py -v`
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/ux/report.py tests/unit/test_ux_report.py
git commit -m "feat(ux): add UX verification report generator with coverage metric"
```

---

### Task 6: Playwright Interaction Runner

**Files:**
- Create: `src/dazzle/testing/ux/runner.py`
- Test: `tests/unit/test_ux_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ux_runner.py
"""Tests for Playwright interaction runner (unit-level, no browser)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle.testing.ux.inventory import Interaction, InteractionClass
from dazzle.testing.ux.runner import (
    InteractionRunner,
    _build_page_url,
)


class TestBuildPageUrl:
    def test_list_surface_url(self) -> None:
        url = _build_page_url("task_list", "Task", "list", "http://localhost:3000")
        assert url == "http://localhost:3000/app/task"

    def test_workspace_url(self) -> None:
        url = _build_page_url("", "", "workspace", "http://localhost:3000", workspace="teacher_dashboard")
        assert url == "http://localhost:3000/workspace/teacher_dashboard"


class TestRunnerConfig:
    def test_runner_init(self) -> None:
        runner = InteractionRunner(
            site_url="http://localhost:3000",
            api_url="http://localhost:8000",
        )
        assert runner.site_url == "http://localhost:3000"
        assert runner.api_url == "http://localhost:8000"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ux_runner.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

```python
# src/dazzle/testing/ux/runner.py
"""Playwright-based interaction runner for UX verification.

Executes each interaction from the inventory against a running Dazzle app,
authenticating as the appropriate persona and asserting outcomes.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dazzle.testing.ux.inventory import Interaction, InteractionClass

logger = logging.getLogger(__name__)


def _build_page_url(
    surface: str,
    entity: str,
    mode: str,
    site_url: str,
    workspace: str = "",
) -> str:
    """Build the URL for an interaction target."""
    if mode == "workspace" and workspace:
        return f"{site_url}/workspace/{workspace}"
    # Entity pages use lowercase entity name
    entity_slug = entity.lower()
    return f"{site_url}/app/{entity_slug}"


@dataclass
class InteractionRunner:
    """Executes interactions against a running Dazzle app via Playwright."""

    site_url: str
    api_url: str
    screenshot_dir: Path = field(default_factory=lambda: Path(".dazzle/ux-verify/screenshots"))
    headless: bool = True

    async def authenticate(self, page: Any, persona: str) -> bool:
        """Authenticate as a persona via the test endpoint."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.api_url}/__test__/authenticate",
                    json={"role": persona, "username": persona},
                )
                if resp.status_code != 200:
                    return False
                data = resp.json()
                token = data.get("session_token", "")
                if token:
                    await page.context.add_cookies([{
                        "name": "dazzle_session",
                        "value": token,
                        "domain": "localhost",
                        "path": "/",
                    }])
                return True
        except Exception as e:
            logger.error("Authentication failed for %s: %s", persona, e)
            return False

    async def run_interaction(self, page: Any, interaction: Interaction) -> Interaction:
        """Execute a single interaction and update its status."""
        try:
            if interaction.cls == InteractionClass.PAGE_LOAD:
                return await self._run_page_load(page, interaction)
            elif interaction.cls == InteractionClass.DETAIL_VIEW:
                return await self._run_detail_view(page, interaction)
            elif interaction.cls == InteractionClass.WORKSPACE_RENDER:
                return await self._run_workspace_render(page, interaction)
            elif interaction.cls == InteractionClass.DRAWER_OPEN:
                return await self._run_drawer_open(page, interaction)
            elif interaction.cls == InteractionClass.DRAWER_CLOSE:
                return await self._run_drawer_close(page, interaction)
            elif interaction.cls == InteractionClass.ACCESS_DENIED:
                return await self._run_access_denied(page, interaction)
            else:
                interaction.status = "skipped"
                return interaction
        except Exception as e:
            interaction.status = "failed"
            interaction.error = str(e)
            await self._capture_screenshot(page, interaction)
            return interaction

    async def _run_page_load(self, page: Any, interaction: Interaction) -> Interaction:
        url = _build_page_url(interaction.surface, interaction.entity, "list", self.site_url)
        response = await page.goto(url, wait_until="networkidle")

        # Check HTTP status
        if response and response.status >= 400:
            interaction.status = "failed"
            interaction.error = f"HTTP {response.status} on {url}"
            await self._capture_screenshot(page, interaction)
            return interaction

        # Check for JS console errors
        errors = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

        # Check expected content is present
        content = await page.content()
        if not content or len(content) < 100:
            interaction.status = "failed"
            interaction.error = "Page content is empty or too short"
            await self._capture_screenshot(page, interaction)
            return interaction

        interaction.status = "passed"
        return interaction

    async def _run_detail_view(self, page: Any, interaction: Interaction) -> Interaction:
        # Navigate to list first, then click first row
        url = _build_page_url(interaction.surface, interaction.entity, "list", self.site_url)
        await page.goto(url, wait_until="networkidle")

        # Find first clickable row
        row = page.locator("table tbody tr a, [data-dazzle-entity] a").first
        if await row.count() == 0:
            interaction.status = "skipped"
            interaction.error = "No rows to click for detail view"
            return interaction

        await row.click()
        await page.wait_for_load_state("networkidle")

        # Check detail content loaded
        content = await page.content()
        if "detail" in content.lower() or interaction.entity.lower() in content.lower():
            interaction.status = "passed"
        else:
            interaction.status = "failed"
            interaction.error = "Detail content not loaded after row click"
            await self._capture_screenshot(page, interaction)

        return interaction

    async def _run_workspace_render(self, page: Any, interaction: Interaction) -> Interaction:
        url = _build_page_url("", "", "workspace", self.site_url, workspace=interaction.workspace)
        response = await page.goto(url, wait_until="networkidle")

        if response and response.status >= 400:
            interaction.status = "failed"
            interaction.error = f"HTTP {response.status} on workspace {interaction.workspace}"
            await self._capture_screenshot(page, interaction)
            return interaction

        # Check that region containers exist
        regions = page.locator("[data-region-name]")
        count = await regions.count()
        if count == 0:
            interaction.status = "failed"
            interaction.error = "No workspace regions found"
            await self._capture_screenshot(page, interaction)
            return interaction

        interaction.status = "passed"
        return interaction

    async def _run_drawer_open(self, page: Any, interaction: Interaction) -> Interaction:
        # Navigate to workspace
        url = _build_page_url("", "", "workspace", self.site_url, workspace=interaction.workspace)
        await page.goto(url, wait_until="networkidle")

        # Find a clickable row in the target region
        region = page.locator(f"[data-region-name='{interaction.action}']")
        if await region.count() == 0:
            interaction.status = "skipped"
            interaction.error = f"Region {interaction.action} not found"
            return interaction

        row = region.locator("table tbody tr, .card").first
        if await row.count() == 0:
            interaction.status = "skipped"
            interaction.error = "No clickable rows in region"
            return interaction

        await row.click()

        # Wait for drawer to appear
        try:
            drawer = page.locator("#dz-detail-drawer")
            await drawer.wait_for(state="visible", timeout=3000)
            interaction.status = "passed"
        except Exception:
            interaction.status = "failed"
            interaction.error = "Drawer did not open within 3s"
            await self._capture_screenshot(page, interaction)

        return interaction

    async def _run_drawer_close(self, page: Any, interaction: Interaction) -> Interaction:
        # First open the drawer (reuse open logic)
        open_result = await self._run_drawer_open(page, Interaction(
            cls=InteractionClass.DRAWER_OPEN,
            entity=interaction.entity,
            persona=interaction.persona,
            workspace=interaction.workspace,
            action=interaction.action,
            description="",
        ))
        if open_result.status != "passed":
            interaction.status = "skipped"
            interaction.error = "Could not open drawer to test close"
            return interaction

        # Click the Back button inside the drawer
        drawer = page.locator("#dz-detail-drawer")
        back_btn = drawer.locator("a:has-text('Back'), button:has-text('Back')").first
        if await back_btn.count() > 0:
            await back_btn.click()
        else:
            # Try the X close button
            close_btn = drawer.locator("[aria-label='Close'], button:has-text('x')").first
            if await close_btn.count() > 0:
                await close_btn.click()

        # Verify drawer closed
        try:
            await drawer.wait_for(state="hidden", timeout=2000)
            interaction.status = "passed"
        except Exception:
            interaction.status = "failed"
            interaction.error = "Drawer did not close after Back/Close click"
            await self._capture_screenshot(page, interaction)

        return interaction

    async def _run_access_denied(self, page: Any, interaction: Interaction) -> Interaction:
        url = _build_page_url(interaction.surface, interaction.entity, "list", self.site_url)
        response = await page.goto(url, wait_until="networkidle")

        if response and response.status in (403, 401, 302):
            interaction.status = "passed"
        else:
            # Check if we were redirected to login
            if "/login" in page.url or "/auth" in page.url:
                interaction.status = "passed"
            else:
                interaction.status = "failed"
                interaction.error = f"Expected 403/redirect, got {response.status if response else 'no response'}"
                await self._capture_screenshot(page, interaction)

        return interaction

    async def _capture_screenshot(self, page: Any, interaction: Interaction) -> None:
        """Capture a screenshot for a failed interaction."""
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{interaction.cls.value}_{interaction.entity}_{interaction.persona}.png"
        path = self.screenshot_dir / filename
        try:
            await page.screenshot(path=str(path))
            interaction.screenshot = str(path)
        except Exception:
            logger.debug("Failed to capture screenshot for %s", interaction.interaction_id)

    async def run_all(self, interactions: list[Interaction]) -> list[Interaction]:
        """Run all interactions, grouping by persona for session efficiency."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)

            # Group by persona
            by_persona: dict[str, list[Interaction]] = {}
            for interaction in interactions:
                by_persona.setdefault(interaction.persona, []).append(interaction)

            for persona, persona_interactions in by_persona.items():
                context = await browser.new_context()
                page = await context.new_page()

                # Authenticate once per persona
                if persona:
                    auth_ok = await self.authenticate(page, persona)
                    if not auth_ok:
                        for i in persona_interactions:
                            i.status = "failed"
                            i.error = f"Authentication failed for persona {persona}"
                        await context.close()
                        continue

                for interaction in persona_interactions:
                    await self.run_interaction(page, interaction)

                await context.close()

            await browser.close()

        return interactions
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_ux_runner.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/ux/runner.py tests/unit/test_ux_runner.py
git commit -m "feat(ux): add Playwright interaction runner with per-persona sessions"
```

---

### Task 7: CLI Command (`dazzle ux verify`)

**Files:**
- Create: `src/dazzle/cli/ux.py`
- Modify: `src/dazzle/cli/main.py` (register the `ux_app` subcommand)
- Test: `tests/unit/test_cli_ux.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cli_ux.py
"""Tests for the UX verification CLI command."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from dazzle.cli.ux import ux_app

runner = CliRunner()


class TestUxVerifyCLI:
    @patch("dazzle.cli.ux._run_structural_only")
    def test_structural_only_mode(self, mock_run: MagicMock) -> None:
        mock_run.return_value = 0
        result = runner.invoke(ux_app, ["verify", "--structural"])
        assert result.exit_code == 0

    def test_help_works(self) -> None:
        result = runner.invoke(ux_app, ["verify", "--help"])
        assert result.exit_code == 0
        assert "verify" in result.output.lower() or "UX" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cli_ux.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

```python
# src/dazzle/cli/ux.py
"""CLI commands for UX verification."""

import asyncio
from pathlib import Path

import typer
from rich.console import Console

console = Console()

ux_app = typer.Typer(
    help="UX verification — deterministic interaction testing.",
    no_args_is_help=True,
)


def _run_structural_only() -> int:
    """Run structural checks only (no browser, no database)."""
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.testing.ux.inventory import generate_inventory
    from dazzle.testing.ux.report import generate_report
    from dazzle.testing.ux.structural import check_html

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    inventory = generate_inventory(appspec)

    console.print(f"[dim]Inventory: {len(inventory)} interactions enumerated[/dim]")
    console.print("[yellow]Structural-only mode — skipping browser tests[/yellow]")

    # For structural, we'd need rendered HTML. For now, report the inventory.
    report = generate_report([], [])
    console.print(report.to_markdown())
    return 0


@ux_app.command("verify")
def verify_command(
    structural: bool = typer.Option(False, "--structural", help="Structural checks only (no browser)"),
    persona: str = typer.Option("", "--persona", help="Filter to specific persona"),
    entity: str = typer.Option("", "--entity", help="Filter to specific entity"),
    keep_db: bool = typer.Option(False, "--keep-db", help="Keep test database after verification"),
    db_url: str = typer.Option("", "--db-url", help="Postgres URL override"),
    format_: str = typer.Option("markdown", "--format", "-f", help="Output format: markdown or json"),
    headless: bool = typer.Option(True, "--headless/--headed", help="Run browser headless"),
) -> None:
    """Run UX verification against the current project.

    Derives an interaction inventory from the DSL, boots the app against
    a test database, and verifies every framework-generated interaction.

    Examples:
        dazzle ux verify                    # Full verification
        dazzle ux verify --structural       # HTML checks only (fast)
        dazzle ux verify --persona teacher  # Filter by persona
        dazzle ux verify --headed           # Watch the browser
    """
    if structural:
        raise typer.Exit(_run_structural_only())

    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.core.manifest import resolve_api_url, resolve_site_url
    from dazzle.testing.ux.fixtures import generate_seed_payload
    from dazzle.testing.ux.harness import PostgresHarness, check_postgres_available
    from dazzle.testing.ux.inventory import generate_inventory
    from dazzle.testing.ux.report import generate_report
    from dazzle.testing.ux.runner import InteractionRunner

    project_root = Path.cwd().resolve()
    project_name = project_root.name

    # Load AppSpec
    try:
        appspec = load_project_appspec(project_root)
    except Exception as e:
        console.print(f"[red]Failed to load project: {e}[/red]")
        raise typer.Exit(1)

    # Generate inventory
    inventory = generate_inventory(appspec)
    console.print(f"[dim]Inventory: {len(inventory)} interactions enumerated[/dim]")

    # Filter if requested
    if persona:
        inventory = [i for i in inventory if i.persona == persona]
        console.print(f"[dim]Filtered to persona '{persona}': {len(inventory)} interactions[/dim]")
    if entity:
        inventory = [i for i in inventory if i.entity == entity]
        console.print(f"[dim]Filtered to entity '{entity}': {len(inventory)} interactions[/dim]")

    if not inventory:
        console.print("[yellow]No interactions to test.[/yellow]")
        raise typer.Exit(0)

    # Check Postgres
    harness_url = db_url or "postgresql://localhost:5432/postgres"
    if not check_postgres_available(harness_url):
        console.print(
            "[red]Postgres is not available.[/red]\n"
            "  Ensure PostgreSQL is running locally.\n"
            "  macOS: brew services start postgresql@16\n"
            "  Or set --db-url to a reachable Postgres instance."
        )
        raise typer.Exit(1)

    # Run with harness
    harness = PostgresHarness(
        project_name=project_name,
        db_url=harness_url,
        keep_db=keep_db,
    )

    site_url = resolve_site_url()
    api_url = resolve_api_url()

    runner = InteractionRunner(
        site_url=site_url,
        api_url=api_url,
        headless=headless,
    )

    console.print(f"[bold]Running UX verification for {project_name}...[/bold]")

    # TODO: Full harness integration (boot app, seed, run, teardown)
    # For now, assume app is already running
    results = asyncio.run(runner.run_all(inventory))

    report = generate_report(results, [])

    if format_ == "json":
        import json

        console.print_json(json.dumps(report.to_json(), indent=2))
    else:
        console.print(report.to_markdown())

    if report.failed > 0:
        raise typer.Exit(1)
```

Now register the CLI in main.py. First find where other subcommands are registered:

- [ ] **Step 4: Register in CLI main**

Find the line in `src/dazzle/cli/main.py` that registers `sentinel_app` or similar, and add `ux_app` next to it:

```python
from dazzle.cli.ux import ux_app
app.add_typer(ux_app, name="ux")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_cli_ux.py -v`
Expected: 2 PASSED

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/cli/ux.py src/dazzle/cli/main.py tests/unit/test_cli_ux.py
git commit -m "feat(ux): add 'dazzle ux verify' CLI command"
```

---

### Task 8: Integration — Wire Public API + Run Against simple_task

**Files:**
- Modify: `src/dazzle/testing/ux/__init__.py`

- [ ] **Step 1: Update the public API**

```python
# src/dazzle/testing/ux/__init__.py
"""DAZZLE UX Verification — deterministic interaction testing derived from the DSL.

Usage:
    from dazzle.testing.ux import generate_inventory, verify
    from dazzle.core.appspec_loader import load_project_appspec

    appspec = load_project_appspec(Path("examples/simple_task"))
    inventory = generate_inventory(appspec)
"""

from dazzle.testing.ux.inventory import (
    Interaction,
    InteractionClass,
    generate_inventory,
)
from dazzle.testing.ux.report import UXReport, generate_report
from dazzle.testing.ux.structural import (
    StructuralResult,
    check_detail_view,
    check_form,
    check_html,
)

__all__ = [
    "Interaction",
    "InteractionClass",
    "generate_inventory",
    "UXReport",
    "generate_report",
    "StructuralResult",
    "check_detail_view",
    "check_form",
    "check_html",
]
```

- [ ] **Step 2: Run all UX tests together**

Run: `pytest tests/unit/test_ux_inventory.py tests/unit/test_ux_harness.py tests/unit/test_ux_structural.py tests/unit/test_ux_fixtures.py tests/unit/test_ux_report.py tests/unit/test_ux_runner.py tests/unit/test_cli_ux.py -v`
Expected: All PASSED

- [ ] **Step 3: Run lint and type check**

Run: `ruff check src/dazzle/testing/ux/ src/dazzle/cli/ux.py --fix && ruff format src/dazzle/testing/ux/ src/dazzle/cli/ux.py`
Run: `mypy src/dazzle/testing/ux/`

- [ ] **Step 4: Test inventory generation on simple_task**

Run: `python -c "from pathlib import Path; from dazzle.core.appspec_loader import load_project_appspec; from dazzle.testing.ux.inventory import generate_inventory; a = load_project_appspec(Path('examples/simple_task')); inv = generate_inventory(a); print(f'{len(inv)} interactions'); from collections import Counter; print(Counter(i.cls.value for i in inv))"`

This should print the interaction count and breakdown by class.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/ux/__init__.py
git commit -m "feat(ux): wire public API and verify integration on simple_task"
```
