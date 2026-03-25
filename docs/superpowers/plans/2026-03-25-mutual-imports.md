# Eliminate dazzle_ui → dazzle_back Imports

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Break the `dazzle_ui → dazzle_back` import cycle by moving pure value types to `dazzle.core.access` and injecting backend callables via `_PageDeps`.

**Architecture:** Extract `AccessOperationKind`, `AccessRuntimeContext`, `AccessDecision` to `dazzle.core.access` (zero backend deps). Add 3 callable fields to `_PageDeps` for `evaluate_permission`, `convert_entity`, `inject_display_names`. Wire concrete implementations from `server.py` where `create_page_routes()` is called.

**Tech Stack:** Python protocols/callables, dataclass fields

**Spec:** Issue #679

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `src/dazzle/core/access.py` | Create | Pure value types: `AccessOperationKind`, `AccessRuntimeContext`, `AccessDecision` |
| `src/dazzle_back/runtime/access_evaluator.py` | Modify | Import types from `dazzle.core.access`, delete local definitions |
| `src/dazzle_back/specs/auth.py` | Modify | Delete `AccessOperationKind`, re-export from `dazzle.core.access` |
| `src/dazzle_ui/runtime/page_routes.py` | Modify | Import from `dazzle.core.access`, use `_PageDeps` callables |
| `src/dazzle_ui/runtime/combined_server.py` | Modify | Wire callables into `create_page_routes()` |
| `src/dazzle_back/runtime/subsystems/system_routes.py` | Modify | Wire callables into `create_page_routes()` |

---

### Task 1: Create `dazzle.core.access` with Pure Value Types

**Files:**
- Create: `src/dazzle/core/access.py`

- [ ] **Step 1: Create the module**

Create `src/dazzle/core/access.py`:

```python
"""Access control value types — shared between dazzle_back and dazzle_ui.

These types have NO backend dependencies. They exist in dazzle.core so both
dazzle_back (which implements access evaluation) and dazzle_ui (which consumes
access decisions for UI filtering) can import them without circular deps.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID


class AccessOperationKind(StrEnum):
    """Access operation types."""

    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"


class AccessDecision:
    """Result of an access permission evaluation."""

    __slots__ = ("allowed", "matched_policy", "effect")

    def __init__(
        self,
        allowed: bool,
        matched_policy: str = "",
        effect: str = "",
    ):
        self.allowed = allowed
        self.matched_policy = matched_policy
        self.effect = effect

    def __bool__(self) -> bool:
        return self.allowed

    def __repr__(self) -> str:
        return f"AccessDecision(allowed={self.allowed}, policy={self.matched_policy!r})"


class AccessRuntimeContext:
    """Runtime context for access rule evaluation.

    Provides user identity, roles, and entity resolution for relationship traversal.
    """

    def __init__(
        self,
        user_id: str | UUID | None = None,
        roles: list[str] | None = None,
        is_superuser: bool = False,
        entity_resolver: Any = None,
    ):
        self.user_id = str(user_id) if user_id else None
        self.roles = set(roles or [])
        self.is_superuser = is_superuser
        self.entity_resolver = entity_resolver

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def get_attribute(self, name: str) -> Any:
        return getattr(self, name, None)
```

- [ ] **Step 2: Verify**

Run: `python -c "from dazzle.core.access import AccessOperationKind, AccessRuntimeContext, AccessDecision; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add src/dazzle/core/access.py
git commit -m "refactor: extract access value types to dazzle.core.access (#679)"
```

---

### Task 2: Migrate `access_evaluator.py` and `specs/auth.py` to Import from Core

**Files:**
- Modify: `src/dazzle_back/runtime/access_evaluator.py`
- Modify: `src/dazzle_back/specs/auth.py`

- [ ] **Step 1: Read both files**

Read `src/dazzle_back/runtime/access_evaluator.py` to find where `AccessDecision` (lines 38-57) and `AccessRuntimeContext` (lines 65-99) are defined.

Read `src/dazzle_back/specs/auth.py` to find `AccessOperationKind` (lines 174-181).

- [ ] **Step 2: Replace definitions with imports in `access_evaluator.py`**

Delete the `AccessDecision` class definition (lines 38-57) and `AccessRuntimeContext` class definition (lines 65-99, including all methods). Replace with imports:

```python
from dazzle.core.access import AccessDecision, AccessRuntimeContext
```

Keep any additional methods on `AccessRuntimeContext` that exist in the backend version but not in the core version (e.g., `get_attribute` with backend-specific logic). If all methods are identical, just import.

- [ ] **Step 3: Replace definition with import in `specs/auth.py`**

Delete the `AccessOperationKind` class (lines 174-181). Replace with:

```python
from dazzle.core.access import AccessOperationKind
```

Keep the re-export so existing `from dazzle_back.specs.auth import AccessOperationKind` callers still work (backward compat here is free — it's just a re-export, not a shim).

- [ ] **Step 4: Update all internal `dazzle_back` importers**

Search for files importing these types from the old locations:

```bash
grep -rn "from dazzle_back.runtime.access_evaluator import.*AccessRuntimeContext\|from dazzle_back.runtime.access_evaluator import.*AccessDecision\|from dazzle_back.specs.auth import.*AccessOperationKind" src/dazzle_back/ --include="*.py"
```

Update each to import from `dazzle.core.access` instead. The re-exports in `access_evaluator.py` and `specs/auth.py` provide backward compat, but it's cleaner to update direct callers.

- [ ] **Step 5: Verify**

Run: `python -c "from dazzle_back.runtime.access_evaluator import evaluate_permission, AccessRuntimeContext; print('OK')"`
Run: `python -c "from dazzle_back.specs.auth import AccessOperationKind; print('OK')"`

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_back/runtime/access_evaluator.py src/dazzle_back/specs/auth.py
git commit -m "refactor: import access types from dazzle.core.access (#679)"
```

---

### Task 3: Add Callable Fields to `_PageDeps` and Eliminate dazzle_back Imports

**Files:**
- Modify: `src/dazzle_ui/runtime/page_routes.py`

- [ ] **Step 1: Read the full file for context**

Read `src/dazzle_ui/runtime/page_routes.py` — particularly `_PageDeps` (line 318), `_user_can_mutate` (line 190), `_filter_nav_by_entity_access` (line 249), the detail page handler (line 492), and `create_page_routes` (line 986).

- [ ] **Step 2: Add callable fields to `_PageDeps`**

In the `_PageDeps` dataclass (line 318), add:

```python
    # Callables injected from dazzle_back — breaks circular import (#679)
    evaluate_permission: Callable[..., Any] | None = None
    convert_entity: Callable[..., Any] | None = None
    inject_display_names: Callable[..., Any] | None = None
```

- [ ] **Step 3: Replace imports in `_user_can_mutate` (line 190)**

Replace the deferred imports at lines 206-210:

```python
        from dazzle_back.runtime.access_evaluator import (
            AccessRuntimeContext,
            evaluate_permission,
        )
        from dazzle_back.specs.auth import AccessOperationKind
```

With:

```python
        from dazzle.core.access import AccessOperationKind, AccessRuntimeContext
```

And change `evaluate_permission(...)` call to `deps.evaluate_permission(...)`. Guard with:

```python
    if deps.evaluate_permission is None:
        return True
```

Remove the `except ImportError: return True` since there's no deferred import to fail.

- [ ] **Step 4: Replace imports in `_filter_nav_by_entity_access` (line 249)**

Same pattern — import types from `dazzle.core.access`, use `deps.evaluate_permission`.

- [ ] **Step 5: Replace import in detail page handler (line 492)**

Change:
```python
            from dazzle_back.runtime.workspace_rendering import _inject_display_names
            req_detail.item = _inject_display_names(req_detail.item)
```
To:
```python
            if deps.inject_display_names is not None:
                req_detail.item = deps.inject_display_names(req_detail.item)
```

- [ ] **Step 6: Replace import in `create_page_routes` factory (line 1032)**

Change:
```python
        from dazzle_back.converters.entity_converter import convert_entity
```
To:
```python
        convert_entity_fn = deps.convert_entity  # injected, may be None
```

Where `deps` isn't available yet (it's being built). Move the entity cedar spec building to use the convert_entity from the function parameter. Add `convert_entity` and `evaluate_permission` and `inject_display_names` as parameters to `create_page_routes()`:

```python
def create_page_routes(
    appspec: ir.AppSpec,
    backend_url: str = "http://127.0.0.1:8000",
    theme_css: str = "",
    get_auth_context: Callable[..., Any] | None = None,
    app_prefix: str = "",
    *,
    evaluate_permission_fn: Callable[..., Any] | None = None,
    convert_entity_fn: Callable[..., Any] | None = None,
    inject_display_names_fn: Callable[..., Any] | None = None,
) -> APIRouter:
```

Pass them through to `_PageDeps`:

```python
    deps = _PageDeps(
        ...,
        evaluate_permission=evaluate_permission_fn,
        convert_entity=convert_entity_fn,
        inject_display_names=inject_display_names_fn,
    )
```

Use `convert_entity_fn` for building `entity_cedar_specs` (replacing the deferred import at line 1032):

```python
    entity_cedar_specs: dict[str, Any] = {}
    if convert_entity_fn is not None:
        for _entity in appspec.domain.entities:
            if _entity.access:
                _converted = convert_entity_fn(_entity)
                if _converted.access is not None:
                    entity_cedar_specs[_entity.name] = _converted.access
```

- [ ] **Step 7: Verify no dazzle_back imports remain**

Run: `grep -rn "from dazzle_back\|import dazzle_back" src/dazzle_ui/runtime/page_routes.py`
Expected: 0 matches

- [ ] **Step 8: Commit**

```bash
git add src/dazzle_ui/runtime/page_routes.py
git commit -m "refactor: eliminate dazzle_back imports from page_routes via DI (#679)"
```

---

### Task 4: Wire Callables from Server-Side Callers

**Files:**
- Modify: `src/dazzle_ui/runtime/combined_server.py` (if it calls `create_page_routes`)
- Modify: `src/dazzle_back/runtime/subsystems/system_routes.py` (if it calls `create_page_routes`)

- [ ] **Step 1: Find all callers of `create_page_routes`**

Run: `grep -rn "create_page_routes" src/ --include="*.py"`

- [ ] **Step 2: Update each caller to pass the backend callables**

At each call site, add:

```python
from dazzle_back.runtime.access_evaluator import evaluate_permission
from dazzle_back.converters.entity_converter import convert_entity
from dazzle_back.runtime.workspace_rendering import _inject_display_names

router = create_page_routes(
    appspec,
    ...,
    evaluate_permission_fn=evaluate_permission,
    convert_entity_fn=convert_entity,
    inject_display_names_fn=_inject_display_names,
)
```

If the caller is in `dazzle_ui` (e.g., `combined_server.py`), wrap in try/except ImportError since `dazzle_back` may not be installed:

```python
try:
    from dazzle_back.runtime.access_evaluator import evaluate_permission
    from dazzle_back.converters.entity_converter import convert_entity
    from dazzle_back.runtime.workspace_rendering import _inject_display_names
except ImportError:
    evaluate_permission = None
    convert_entity = None
    _inject_display_names = None
```

- [ ] **Step 3: Verify**

Run: `python -c "from dazzle_ui.runtime.page_routes import create_page_routes; print('OK')"`
Run: `grep -rn "from dazzle_back\|import dazzle_back" src/dazzle_ui/runtime/page_routes.py | wc -l`
Expected: 0

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_ui/runtime/combined_server.py src/dazzle_back/runtime/subsystems/system_routes.py
git commit -m "refactor: wire access callables into create_page_routes (#679)"
```

---

### Task 5: Run Full Test Suite + Quality Checks

- [ ] **Step 1: Run all unit tests**

Run: `pytest tests/ -m "not e2e" -x -q`
Expected: ALL PASS

- [ ] **Step 2: Verify zero dazzle_back imports in page_routes.py**

Run: `grep -rn "from dazzle_back\|import dazzle_back" src/dazzle_ui/runtime/page_routes.py | wc -l`
Expected: 0

- [ ] **Step 3: Lint**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/`

- [ ] **Step 4: Type check**

Run: `mypy src/dazzle/core src/dazzle/cli src/dazzle/mcp --ignore-missing-imports --exclude 'eject' && mypy src/dazzle_back/ --ignore-missing-imports`

- [ ] **Step 5: Commit if lint/format changes**

```bash
git add -u
git commit -m "chore: lint + format fixes for mutual imports refactor (#679)"
```
