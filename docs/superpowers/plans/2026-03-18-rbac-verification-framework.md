# RBAC Verification Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-layer RBAC verification framework (static matrix + dynamic verification + decision audit trail) that proves DSL-declared access rules are enforced at runtime, plus fix the critical #520 enforcement bug.

**Architecture:** Layer 1 generates an access matrix from the AppSpec (pure computation). Layer 2 spins up the app with golden-master data and probes every (role, entity, operation) cell. Layer 3 instruments `evaluate_permission()` to emit structured audit records. The Shapes validation app exercises every RBAC pattern.

**Tech Stack:** Python 3.12+, Pydantic models, typer CLI, httpx for probing, existing Dazzle runtime (FastAPI, SQLite)

**Spec:** `docs/superpowers/specs/2026-03-18-rbac-verification-framework-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/dazzle_back/runtime/route_generator.py` | Modify | Fix #520 — `_is_field_condition()` + gate fix |
| `tests/unit/test_rbac_enforcement.py` | Modify | Fix broken test, add regression tests |
| `src/dazzle/rbac/__init__.py` | Create | Package init |
| `src/dazzle/rbac/matrix.py` | Create | Layer 1 — static access matrix generator |
| `src/dazzle/rbac/audit.py` | Create | Layer 3 — audit types + sink protocol |
| `src/dazzle/rbac/verifier.py` | Create | Layer 2 — dynamic verification |
| `src/dazzle/rbac/report.py` | Create | Compliance report generator |
| `src/dazzle_back/runtime/access_evaluator.py` | Modify | Instrument evaluate_permission with audit sink |
| `src/dazzle/cli/rbac.py` | Create | CLI command group |
| `src/dazzle/cli/__init__.py` | Modify | Register rbac_app |
| `src/dazzle/mcp/server/handlers/policy.py` | Modify | Add `access_matrix` operation |
| `examples/shapes_validation/dazzle.toml` | Create | Shapes app config |
| `examples/shapes_validation/dsl/app.dsl` | Create | Module + personas |
| `examples/shapes_validation/dsl/entities.dsl` | Create | Shape, Realm, Inscription |
| `examples/shapes_validation/dsl/surfaces.dsl` | Create | List/detail surfaces |
| `tests/unit/test_rbac_matrix.py` | Create | Layer 1 unit tests |
| `tests/unit/test_rbac_audit.py` | Create | Layer 3 unit tests |

---

### Task 1: Fix #520 — LIST Gate Bug

**Files:**
- Modify: `src/dazzle_back/runtime/route_generator.py:904-923`
- Modify: `tests/unit/test_rbac_enforcement.py`

- [ ] **Step 1: Write failing test that reproduces #520**

Add to `tests/unit/test_rbac_enforcement.py`. This test uses `condition=role_check` (the real production path) instead of `personas=`:

```python
class TestListGateRoleCheckCondition:
    """Regression tests for #520: role_check conditions must be evaluated at the gate."""

    @pytest.fixture(autouse=True)
    def _require_fastapi(self):
        pytest.importorskip("fastapi")

    @pytest.mark.asyncio
    async def test_list_returns_403_for_role_check_condition_when_role_not_matched(self):
        """Role-check conditions like `list: role(teacher)` must deny at the gate
        when the user doesn't have the role. This is the actual code path the DSL
        parser produces — condition=role_check, personas=[]."""
        from dazzle_back.runtime.route_generator import _list_handler_body
        from dazzle_back.specs.auth import (
            AccessConditionSpec,
            AccessOperationKind,
            AccessPolicyEffect,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        cedar_spec = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.LIST,
                    effect=AccessPolicyEffect.PERMIT,
                    condition=AccessConditionSpec(kind="role_check", role_name="teacher"),
                    personas=[],  # DSL parser never populates this
                ),
            ],
        )

        auth_ctx = MagicMock()
        auth_ctx.user.roles = ["student"]  # not teacher
        auth_ctx.user.is_superuser = False
        auth_ctx.user.id = "user-1"

        mock_service = MagicMock()
        mock_service.execute = AsyncMock(return_value=[])

        with pytest.raises(HTTPException) as exc_info:
            await _list_handler_body(
                service=mock_service,
                access_spec=None,
                is_authenticated=True,
                user_id="user-1",
                request=MagicMock(),
                page=1,
                page_size=50,
                sort=None,
                dir="asc",
                search=None,
                cedar_access_spec=cedar_spec,
                auth_context=auth_ctx,
                entity_name="TestEntity",
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_list_returns_200_for_role_check_condition_when_role_matches(self):
        """Role-check condition should pass the gate when the user has the role."""
        from dazzle_back.runtime.route_generator import _list_handler_body
        from dazzle_back.specs.auth import (
            AccessConditionSpec,
            AccessOperationKind,
            AccessPolicyEffect,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        cedar_spec = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.LIST,
                    effect=AccessPolicyEffect.PERMIT,
                    condition=AccessConditionSpec(kind="role_check", role_name="teacher"),
                    personas=[],
                ),
            ],
        )

        auth_ctx = MagicMock()
        auth_ctx.user.roles = ["teacher"]  # matches
        auth_ctx.user.is_superuser = False
        auth_ctx.user.id = "user-1"

        mock_service = MagicMock()
        mock_service.execute = AsyncMock(return_value=[{"id": "1", "name": "Test"}])

        result = await _list_handler_body(
            service=mock_service,
            access_spec=None,
            is_authenticated=True,
            user_id="user-1",
            request=MagicMock(),
            page=1,
            page_size=50,
            sort=None,
            dir="asc",
            search=None,
            cedar_access_spec=cedar_spec,
            auth_context=auth_ctx,
            entity_name="TestEntity",
        )
        # Should not raise — teacher has access
        assert isinstance(result, (list, dict))

    @pytest.mark.asyncio
    async def test_list_gate_skips_for_field_condition_with_role_check_in_or(self):
        """Mixed condition: `list: role(teacher) or school = current_user.school`
        has a field condition, so gate should skip (defer to row filter)."""
        from dazzle_back.runtime.route_generator import _list_handler_body
        from dazzle_back.specs.auth import (
            AccessConditionSpec,
            AccessLogicalKind,
            AccessOperationKind,
            AccessPolicyEffect,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        mixed_condition = AccessConditionSpec(
            kind="logical",
            logical_op=AccessLogicalKind.OR,
            logical_left=AccessConditionSpec(kind="role_check", role_name="teacher"),
            logical_right=AccessConditionSpec(
                kind="comparison", field="school", comparison_op="eq", value="current_user.school"
            ),
        )

        cedar_spec = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.LIST,
                    effect=AccessPolicyEffect.PERMIT,
                    condition=mixed_condition,
                    personas=[],
                ),
            ],
        )

        auth_ctx = MagicMock()
        auth_ctx.user.roles = ["student"]  # not teacher, but field condition should pass through
        auth_ctx.user.is_superuser = False
        auth_ctx.user.id = "user-1"

        mock_service = MagicMock()
        mock_service.execute = AsyncMock(return_value=[])

        # Should NOT raise 403 — gate is skipped, row filter handles it
        result = await _list_handler_body(
            service=mock_service,
            access_spec=None,
            is_authenticated=True,
            user_id="user-1",
            request=MagicMock(),
            page=1,
            page_size=50,
            sort=None,
            dir="asc",
            search=None,
            cedar_access_spec=cedar_spec,
            auth_context=auth_ctx,
            entity_name="TestEntity",
        )
        assert isinstance(result, (list, dict))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rbac_enforcement.py::TestListGateRoleCheckCondition -v`
Expected: `test_list_returns_403_for_role_check_condition_when_role_not_matched` FAILS (gate is skipped, no 403 raised)

- [ ] **Step 3: Implement `_is_field_condition` and fix the gate**

In `src/dazzle_back/runtime/route_generator.py`, add before the `_list_handler_body` function:

```python
def _is_field_condition(condition: Any) -> bool:
    """Return True if condition requires record data to evaluate.

    Role checks need only the user's roles — evaluable at the gate without a record.
    Comparisons and grant checks reference entity fields — need record data.
    Logical nodes recurse: if either branch needs record data, the whole
    condition is a field condition.
    """
    if condition is None:
        return False
    kind = getattr(condition, "kind", None)
    if kind == "role_check":
        return False
    if kind in ("comparison", "grant_check"):
        return True
    if kind == "logical":
        return _is_field_condition(
            getattr(condition, "logical_left", None)
        ) or _is_field_condition(getattr(condition, "logical_right", None))
    return False
```

Then change line 916 from:
```python
has_field_conditions = any(r.condition is not None for r in list_rules)
```
to:
```python
has_field_conditions = any(_is_field_condition(r.condition) for r in list_rules)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rbac_enforcement.py -v -k "ListGate or list_returns_403 or list_passes_gate"`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `pytest tests/unit/test_rbac_enforcement.py -v`
Expected: ALL PASS

- [ ] **Step 6: Run lint and type check**

Run: `ruff check src/dazzle_back/runtime/route_generator.py --fix && ruff format src/dazzle_back/runtime/route_generator.py && mypy src/dazzle_back/runtime/route_generator.py`

- [ ] **Step 7: Commit**

```bash
git add src/dazzle_back/runtime/route_generator.py tests/unit/test_rbac_enforcement.py
git commit -m "fix: LIST gate evaluates role-check conditions instead of skipping them (#520)

The gate at route_generator.py:916 treated role_check conditions as field
conditions (condition is not None), skipping enforcement. Replace with
_is_field_condition() that recursively classifies conditions: role_check
and None are gate-evaluable, comparison and grant_check need record data.

Adds 3 regression tests using the real production code path (condition=
role_check, personas=[]) instead of the test-only path (personas=[...]).
"
```

---

### Task 2: Layer 3 — Audit Trail Types and Sinks

**Files:**
- Create: `src/dazzle/rbac/__init__.py`
- Create: `src/dazzle/rbac/audit.py`
- Create: `tests/unit/test_rbac_audit.py`

- [ ] **Step 1: Write failing tests for audit types and sinks**

Create `tests/unit/test_rbac_audit.py`:

```python
"""Tests for RBAC audit trail types and sinks."""
from dazzle.rbac.audit import (
    AccessAuditSink,
    AccessDecisionRecord,
    InMemoryAuditSink,
    JsonFileAuditSink,
    NullAuditSink,
    get_audit_sink,
    set_audit_sink,
)


class TestAccessDecisionRecord:
    def test_create_record(self):
        record = AccessDecisionRecord(
            timestamp="2026-03-18T00:00:00Z",
            request_id="req-1",
            user_id="user-1",
            roles=["teacher"],
            entity="Student",
            operation="list",
            allowed=True,
            effect="permit",
            matched_rule="permit list when role(teacher)",
            record_id=None,
            tier="gate",
        )
        assert record.allowed is True
        assert record.entity == "Student"

    def test_record_to_dict(self):
        record = AccessDecisionRecord(
            timestamp="2026-03-18T00:00:00Z",
            request_id="req-1",
            user_id="user-1",
            roles=["admin"],
            entity="Shape",
            operation="read",
            allowed=False,
            effect="default_deny",
            matched_rule="default_deny",
            record_id="shape-1",
            tier="gate",
        )
        d = record.to_dict()
        assert d["entity"] == "Shape"
        assert d["allowed"] is False
        assert isinstance(d, dict)


class TestNullAuditSink:
    def test_emit_does_nothing(self):
        sink = NullAuditSink()
        record = AccessDecisionRecord(
            timestamp="t", request_id="r", user_id="u", roles=[],
            entity="E", operation="list", allowed=True, effect="permit",
            matched_rule="", record_id=None, tier="gate",
        )
        sink.emit(record)  # should not raise


class TestInMemoryAuditSink:
    def test_collects_records(self):
        sink = InMemoryAuditSink()
        for i in range(3):
            sink.emit(AccessDecisionRecord(
                timestamp="t", request_id=f"r-{i}", user_id="u", roles=[],
                entity="E", operation="list", allowed=True, effect="permit",
                matched_rule="", record_id=None, tier="gate",
            ))
        assert len(sink.records) == 3

    def test_clear(self):
        sink = InMemoryAuditSink()
        sink.emit(AccessDecisionRecord(
            timestamp="t", request_id="r", user_id="u", roles=[],
            entity="E", operation="list", allowed=True, effect="permit",
            matched_rule="", record_id=None, tier="gate",
        ))
        sink.clear()
        assert len(sink.records) == 0


class TestJsonFileAuditSink:
    def test_writes_jsonl(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        sink = JsonFileAuditSink(path)
        sink.emit(AccessDecisionRecord(
            timestamp="2026-03-18T00:00:00Z", request_id="r-1",
            user_id="user-1", roles=["admin"], entity="Shape",
            operation="list", allowed=True, effect="permit",
            matched_rule="permit list role(admin)", record_id=None, tier="gate",
        ))
        sink.close()
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        import json
        data = json.loads(lines[0])
        assert data["entity"] == "Shape"
        assert data["allowed"] is True


class TestGlobalSink:
    def setup_method(self):
        """Reset global sink to NullAuditSink before each test."""
        self._original = get_audit_sink()
        set_audit_sink(NullAuditSink())

    def teardown_method(self):
        set_audit_sink(self._original)

    def test_default_is_null(self):
        assert isinstance(get_audit_sink(), NullAuditSink)

    def test_set_and_get(self):
        mem = InMemoryAuditSink()
        set_audit_sink(mem)
        assert get_audit_sink() is mem
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rbac_audit.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Create `src/dazzle/rbac/__init__.py`**

```python
"""RBAC verification framework — static analysis, dynamic verification, audit trail."""
```

- [ ] **Step 4: Implement `src/dazzle/rbac/audit.py`**

```python
"""Access decision audit trail — types, sinks, and global sink management.

Layer 3 of the RBAC verification framework. Instruments evaluate_permission()
to emit structured records of every access decision.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class AccessDecisionRecord:
    """Structured record of a single access decision."""

    timestamp: str
    request_id: str
    user_id: str
    roles: list[str]
    entity: str
    operation: str
    allowed: bool
    effect: str
    matched_rule: str
    record_id: str | None
    tier: str

    def to_dict(self) -> dict:
        return asdict(self)


class AccessAuditSink(Protocol):
    """Protocol for audit sinks that receive access decision records."""

    def emit(self, record: AccessDecisionRecord) -> None: ...


class NullAuditSink:
    """No-op sink — default in production (zero overhead)."""

    def emit(self, record: AccessDecisionRecord) -> None:
        pass


class InMemoryAuditSink:
    """Collects records in memory — used by Layer 2 verifier during test runs."""

    def __init__(self) -> None:
        self.records: list[AccessDecisionRecord] = []

    def emit(self, record: AccessDecisionRecord) -> None:
        self.records.append(record)

    def clear(self) -> None:
        self.records.clear()


class JsonFileAuditSink:
    """Writes records as JSON Lines to a file."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self._path, "a")  # noqa: SIM115
        self._lock = threading.Lock()

    def emit(self, record: AccessDecisionRecord) -> None:
        line = json.dumps(record.to_dict(), default=str)
        with self._lock:
            self._file.write(line + "\n")
            self._file.flush()

    def close(self) -> None:
        self._file.close()


# Global audit sink — thread-safe access
_sink_lock = threading.Lock()
_current_sink: AccessAuditSink = NullAuditSink()


def get_audit_sink() -> AccessAuditSink:
    with _sink_lock:
        return _current_sink


def set_audit_sink(sink: AccessAuditSink) -> None:
    global _current_sink
    with _sink_lock:
        _current_sink = sink
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_rbac_audit.py -v`
Expected: ALL PASS

- [ ] **Step 6: Lint and commit**

```bash
ruff check src/dazzle/rbac/ tests/unit/test_rbac_audit.py --fix && ruff format src/dazzle/rbac/ tests/unit/test_rbac_audit.py
git add src/dazzle/rbac/__init__.py src/dazzle/rbac/audit.py tests/unit/test_rbac_audit.py
git commit -m "feat: add RBAC audit trail types and sinks (Layer 3)"
```

---

### Task 3: Instrument Access Evaluator with Audit Sink

**Files:**
- Modify: `src/dazzle_back/runtime/access_evaluator.py:395-487`
- Create: `tests/unit/test_rbac_audit_integration.py`

- [ ] **Step 1: Write integration test**

```python
"""Test that evaluate_permission emits audit records."""
from unittest.mock import MagicMock

from dazzle.rbac.audit import InMemoryAuditSink, get_audit_sink, set_audit_sink
from dazzle_back.runtime.access_evaluator import (
    AccessRuntimeContext,
    evaluate_permission,
)
from dazzle_back.specs.auth import (
    AccessConditionSpec,
    AccessOperationKind,
    AccessPolicyEffect,
    EntityAccessSpec,
    PermissionRuleSpec,
)


class TestEvaluatePermissionAudit:
    def setup_method(self):
        self.sink = InMemoryAuditSink()
        self._original = get_audit_sink()
        set_audit_sink(self.sink)

    def teardown_method(self):
        set_audit_sink(self._original)

    def test_emits_permit_record(self):
        spec = EntityAccessSpec(permissions=[
            PermissionRuleSpec(
                operation=AccessOperationKind.LIST,
                effect=AccessPolicyEffect.PERMIT,
                condition=AccessConditionSpec(kind="role_check", role_name="admin"),
            ),
        ])
        ctx = AccessRuntimeContext(user_id="u1", roles=["admin"])
        result = evaluate_permission(spec, AccessOperationKind.LIST, None, ctx)
        assert result.allowed is True
        assert len(self.sink.records) == 1
        assert self.sink.records[0].allowed is True
        assert self.sink.records[0].effect == "permit"

    def test_emits_deny_record(self):
        spec = EntityAccessSpec(permissions=[
            PermissionRuleSpec(
                operation=AccessOperationKind.LIST,
                effect=AccessPolicyEffect.PERMIT,
                condition=AccessConditionSpec(kind="role_check", role_name="admin"),
            ),
        ])
        ctx = AccessRuntimeContext(user_id="u1", roles=["student"])
        result = evaluate_permission(spec, AccessOperationKind.LIST, None, ctx)
        assert result.allowed is False
        assert len(self.sink.records) == 1
        assert self.sink.records[0].allowed is False
        assert self.sink.records[0].effect == "default"  # runtime uses "default", not "default_deny"

    def test_superuser_bypass_emits_record(self):
        spec = EntityAccessSpec(permissions=[])
        ctx = AccessRuntimeContext(user_id="u1", roles=[], is_superuser=True)
        result = evaluate_permission(spec, AccessOperationKind.LIST, None, ctx)
        assert result.allowed is True
        assert len(self.sink.records) == 1
        assert self.sink.records[0].effect == "permit"
        assert "superuser" in self.sink.records[0].matched_rule
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rbac_audit_integration.py -v`
Expected: FAIL (no audit records emitted)

- [ ] **Step 3: Add audit emit to `evaluate_permission`**

At the end of `evaluate_permission()` in `access_evaluator.py`, before each `return` statement, emit an audit record. Add imports at the top:

```python
import uuid as _uuid
from datetime import UTC, datetime
```

Add a helper inside the function or at module level:

```python
def _emit_audit(
    decision: AccessDecision,
    operation: AccessOperationKind,
    record: dict[str, Any] | None,
    context: AccessRuntimeContext,
    entity: str = "",
) -> None:
    """Emit an access decision to the audit sink."""
    from dazzle.rbac.audit import AccessDecisionRecord, get_audit_sink

    audit_record = AccessDecisionRecord(
        timestamp=datetime.now(UTC).isoformat(),
        request_id=str(_uuid.uuid4()),
        user_id=context.user_id or "",
        roles=sorted(context.roles),
        entity=entity,
        operation=operation.value if hasattr(operation, "value") else str(operation),
        allowed=decision.allowed,
        effect=decision.effect,
        matched_rule=decision.matched_policy,
        record_id=record.get("id", "") if record else None,
        tier="gate" if record is None else "row_filter",
    )
    get_audit_sink().emit(audit_record)
```

Add an `entity_name: str = ""` parameter to `evaluate_permission()`:

```python
def evaluate_permission(
    access_spec: EntityAccessSpec,
    operation: AccessOperationKind,
    record: dict[str, Any] | None,
    context: AccessRuntimeContext,
    *,
    entity_name: str = "",
) -> AccessDecision:
```

Then add `_emit_audit(result, operation, record, context, entity=entity_name)` before each `return result`.

Update the two call sites in `route_generator.py` to pass `entity_name=entity_name`:
- Line ~921 (LIST gate): `evaluate_permission(..., entity_name=entity_name)`
- The existing `_build_cedar_handler` calls also pass `entity_name`

The `entity_name` parameter is already available in both call sites (it's a parameter of `_list_handler_body` and `_build_cedar_handler`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rbac_audit_integration.py tests/unit/test_rbac_audit.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run existing evaluator tests for regressions**

Run: `pytest tests/unit/test_cedar_evaluator.py tests/unit/test_rbac_enforcement.py -v`
Expected: ALL PASS

- [ ] **Step 6: Lint and commit**

```bash
ruff check src/dazzle_back/runtime/access_evaluator.py --fix && ruff format src/dazzle_back/runtime/access_evaluator.py
git add src/dazzle_back/runtime/access_evaluator.py tests/unit/test_rbac_audit_integration.py
git commit -m "feat: instrument evaluate_permission with audit trail emission (Layer 3)"
```

---

### Task 4: Layer 1 — Static Access Matrix Generator

**Files:**
- Create: `src/dazzle/rbac/matrix.py`
- Create: `tests/unit/test_rbac_matrix.py`

- [ ] **Step 1: Write failing tests for the matrix generator**

Create `tests/unit/test_rbac_matrix.py` testing:
- `generate_access_matrix(appspec)` returns an `AccessMatrix`
- Pure role gate: `permit: list: role(admin)` → admin=PERMIT, student=DENY
- Field condition: `permit: list: school = current_user.school` → PERMIT_FILTERED
- Forbid override: `permit: list: role(all)` + `forbid: list: role(student)` → student=DENY
- No rules: entity with no permissions → PERMIT_UNPROTECTED
- Mixed OR: `role(admin) or field = value` → admin=PERMIT_FILTERED (has field condition in OR)
- `matrix.get(role, entity, operation)` accessor
- `matrix.to_table()` returns markdown string
- `matrix.to_json()` returns serializable dict
- `matrix.warnings` contains unrestricted entity warnings

Build test AppSpecs using the IR types directly (`EntitySpec`, `PersonaSpec`, `PermissionRule`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rbac_matrix.py -v`

- [ ] **Step 3: Implement `src/dazzle/rbac/matrix.py`**

Key types:
```python
class PolicyDecision(str, Enum):
    PERMIT = "PERMIT"
    DENY = "DENY"
    PERMIT_FILTERED = "PERMIT_FILTERED"
    PERMIT_UNPROTECTED = "PERMIT_UNPROTECTED"

@dataclass
class PolicyWarning:
    kind: str  # "unrestricted_entity", "orphan_role", "redundant_forbid", "conflict_note"
    entity: str
    role: str | None
    operation: str | None
    message: str

class AccessMatrix:
    cells: dict[tuple[str, str, str], PolicyDecision]  # (role, entity, op) -> decision
    warnings: list[PolicyWarning]
    roles: list[str]
    entities: list[str]
    operations: list[str]

    def get(self, role: str, entity: str, operation: str) -> PolicyDecision: ...
    def to_table(self) -> str: ...  # markdown
    def to_json(self) -> dict: ...

def generate_access_matrix(appspec: AppSpec) -> AccessMatrix: ...
```

The algorithm walks `appspec.entities`, for each entity walks its `access_spec.permissions`, for each persona evaluates Cedar semantics statically. Use the converter to get backend specs if needed, or evaluate directly on IR types.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rbac_matrix.py -v`

- [ ] **Step 5: Lint and commit**

```bash
ruff check src/dazzle/rbac/matrix.py tests/unit/test_rbac_matrix.py --fix && ruff format src/dazzle/rbac/matrix.py tests/unit/test_rbac_matrix.py
git add src/dazzle/rbac/matrix.py tests/unit/test_rbac_matrix.py
git commit -m "feat: static access matrix generator (Layer 1)"
```

---

### Task 5: Shapes Validation App DSL

**Files:**
- Create: `examples/shapes_validation/dazzle.toml`
- Create: `examples/shapes_validation/dsl/app.dsl`
- Create: `examples/shapes_validation/dsl/entities.dsl`
- Create: `examples/shapes_validation/dsl/surfaces.dsl`

- [ ] **Step 1: Create `dazzle.toml`**

```toml
[project]
name = "shapes_validation"
title = "Shapes RBAC Validation"
description = "Abstract domain for RBAC verification — exercises every access pattern"
```

- [ ] **Step 2: Create `dsl/app.dsl`**

```dsl
module shapes_validation
app shapes "Shapes RBAC Validation"

enum ShapeForm "Shape Form":
  circle
  triangle
  square
  hexagon
  star

enum Colour "Colour":
  red
  blue
  green
  gold
  void

enum Material "Material":
  glass
  stone
  metal
  shadow

persona Oracle "Oracle":
  description: "Platform admin — sees everything across all realms"

persona Sovereign "Sovereign":
  description: "Tenant admin — sees everything in own realm only"

persona Architect "Architect":
  description: "Scoped viewer — sees shapes in own realm"

persona Chromat "Chromat":
  description: "Attribute filter — sees shapes matching assigned colour"

persona Forgemaster "Forgemaster":
  description: "Enum filter with forbid — sees metal/stone, forbidden shadow"

persona Witness "Witness":
  description: "Mixed OR — sees own realm or own creations"

persona Outsider "Outsider":
  description: "Deny-all baseline — proves complete mediation"
```

- [ ] **Step 3: Create `dsl/entities.dsl`**

```dsl
entity Realm "Realm":
  id: uuid pk
  name: str(100) required unique
  sigil: str(50)

  permit:
    list: role(oracle)
    read: role(oracle)
    list: role(sovereign)
    read: role(sovereign)
    list: role(architect)
    read: role(architect)

entity Shape "Shape":
  id: uuid pk
  name: str(200) required
  form: enum ShapeForm required
  colour: enum Colour required
  material: enum Material required
  realm: ref Realm required
  creator: ref User required
  created_at: datetime auto_add

  # Oracle: platform admin, sees everything
  permit:
    list: role(oracle)
    read: role(oracle)
    create: role(oracle)
    update: role(oracle)
    delete: role(oracle)

  # Sovereign: tenant admin, scoped to realm
  permit:
    list: realm = current_user.realm
    read: realm = current_user.realm
    create: role(sovereign)
    update: realm = current_user.realm
    delete: realm = current_user.realm

  # Architect: read-only, scoped to realm
  permit:
    list: realm = current_user.realm
    read: realm = current_user.realm

  # Chromat: read-only, scoped to colour
  permit:
    list: colour = current_user.colour
    read: colour = current_user.colour

  # Forgemaster: metal and stone only
  permit:
    list: material = metal or material = stone
    read: material = metal or material = stone

  # Forgemaster: forbidden from shadow
  forbid:
    list: material = shadow
    read: material = shadow

  # Witness: own realm OR own creations
  permit:
    list: realm = current_user.realm or creator = current_user
    read: realm = current_user.realm or creator = current_user

entity Inscription "Inscription":
  id: uuid pk
  text: str(500) required
  shape: ref Shape required
  author: ref User required
  created_at: datetime auto_add

  # Mirror Shape access via parent ref traversal
  permit:
    list: role(oracle)
    read: role(oracle)

  permit:
    list: shape.realm = current_user.realm
    read: shape.realm = current_user.realm
```

- [ ] **Step 4: Create `dsl/surfaces.dsl`**

```dsl
surface realm_list "Realms":
  uses entity Realm
  mode: list
  access: authenticated
  section main:
    field name "Name"
    field sigil "Sigil"

surface shape_list "Shapes":
  uses entity Shape
  mode: list
  access: authenticated
  section main:
    field name "Name"
    field form "Form"
    field colour "Colour"
    field material "Material"

surface shape_detail "Shape Detail":
  uses entity Shape
  mode: view
  access: authenticated
  section main:
    field name
    field form
    field colour
    field material
    field realm
    field creator

surface inscription_list "Inscriptions":
  uses entity Inscription
  mode: list
  access: authenticated
  section main:
    field text "Text"
    field shape "Shape"
    field author "Author"
```

- [ ] **Step 5: Validate the DSL parses**

Run: `cd examples/shapes_validation && dazzle validate`
Expected: Parse succeeds with no errors

- [ ] **Step 6: Commit**

```bash
git add examples/shapes_validation/
git commit -m "feat: add Shapes RBAC validation example app"
```

---

### Task 6: CLI Command Group — `dazzle rbac matrix`

**Files:**
- Create: `src/dazzle/cli/rbac.py`
- Modify: `src/dazzle/cli/__init__.py`

- [ ] **Step 1: Create `src/dazzle/cli/rbac.py`**

```python
"""RBAC verification CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from dazzle.cli.common import resolve_project

rbac_app = typer.Typer(help="RBAC verification and compliance.", no_args_is_help=True)


@rbac_app.command("matrix")
def matrix(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m", help="Path to dazzle.toml"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table, json, csv"),
) -> None:
    """Generate static access matrix from DSL (no server required)."""
    from dazzle.core.parser import parse_project
    from dazzle.rbac.matrix import generate_access_matrix

    root = resolve_project(manifest)
    appspec = parse_project(root)
    matrix = generate_access_matrix(appspec)

    if format == "json":
        typer.echo(json.dumps(matrix.to_json(), indent=2))
    elif format == "csv":
        typer.echo(matrix.to_csv())
    else:
        typer.echo(matrix.to_table())

    # Print warnings
    for w in matrix.warnings:
        typer.echo(f"WARNING: {w.message}", err=True)
```

- [ ] **Step 2: Register in `src/dazzle/cli/__init__.py`**

Add alongside other imports:
```python
from dazzle.cli.rbac import rbac_app  # noqa: E402
app.add_typer(rbac_app, name="rbac")
```

- [ ] **Step 3: Test the CLI**

Run: `cd examples/shapes_validation && dazzle rbac matrix`
Expected: Markdown table output showing the access matrix

- [ ] **Step 4: Lint and commit**

```bash
ruff check src/dazzle/cli/rbac.py --fix && ruff format src/dazzle/cli/rbac.py
git add src/dazzle/cli/rbac.py src/dazzle/cli/__init__.py
git commit -m "feat: add dazzle rbac matrix CLI command (Layer 1)"
```

---

### Task 7: MCP — `policy access_matrix` Operation

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/policy.py`

- [ ] **Step 1: Add `access_matrix` operation**

In `handle_policy()`, add a new `elif operation == "access_matrix"` branch before the final `else`:

```python
elif operation == "access_matrix":
    from dazzle.rbac.matrix import generate_access_matrix
    matrix = generate_access_matrix(appspec)
    result = matrix.to_json()
    result["warnings"] = [{"kind": w.kind, "entity": w.entity, "message": w.message} for w in matrix.warnings]
    return json.dumps(result, indent=2)
```

- [ ] **Step 2: Add `verify_status` operation**

```python
elif operation == "verify_status":
    report_path = project_path / ".dazzle" / "rbac-verify-report.json"
    if not report_path.exists():
        return json.dumps({"status": "no_report", "message": "Run `dazzle rbac verify` first"})
    from dazzle.rbac.verifier import VerificationReport
    report = VerificationReport.load(report_path)
    return json.dumps({
        "status": "ok",
        "timestamp": report.timestamp,
        "total": report.total,
        "passed": report.passed,
        "violated": report.violated,
        "warnings": report.warnings,
    }, indent=2)
```

- [ ] **Step 3: Register in tools_consolidated.py**

Add `"access_matrix"` and `"verify_status"` to the policy tool's operation list.

- [ ] **Step 4: Test via MCP**

Use the `policy` MCP tool with operation `access_matrix` on the shapes_validation project.

- [ ] **Step 4: Lint and commit**

```bash
git add src/dazzle/mcp/server/handlers/policy.py
git commit -m "feat: add policy access_matrix MCP operation"
```

---

### Task 8: Layer 2 — Dynamic Verifier + Report + CLI

**Files:**
- Create: `src/dazzle/rbac/verifier.py`
- Create: `src/dazzle/rbac/report.py`
- Modify: `src/dazzle/cli/rbac.py`

This is the largest task. The verifier:
1. Starts the app in test mode
2. Seeds golden-master data
3. Creates test users
4. Probes every matrix cell
5. Compares observed vs expected
6. Saves `VerificationReport`

- [ ] **Step 0: Write unit tests for comparison logic and report serialization**

Create `tests/unit/test_rbac_verifier.py`:

```python
"""Tests for Layer 2 verifier types and comparison logic."""
import json
from pathlib import Path

from dazzle.rbac.matrix import PolicyDecision
from dazzle.rbac.verifier import CellResult, VerifiedCell, VerificationReport, compare_cell


class TestCompareCell:
    """Test the observed-vs-expected comparison table from the spec."""

    def test_deny_with_403_is_pass(self):
        assert compare_cell(PolicyDecision.DENY, 403, None) == CellResult.PASS

    def test_deny_with_200_is_violation(self):
        assert compare_cell(PolicyDecision.DENY, 200, None) == CellResult.VIOLATION

    def test_permit_with_200_is_pass(self):
        assert compare_cell(PolicyDecision.PERMIT, 200, 10, total=10) == CellResult.PASS

    def test_permit_with_403_is_violation(self):
        assert compare_cell(PolicyDecision.PERMIT, 403, None) == CellResult.VIOLATION

    def test_filtered_with_partial_count_is_pass(self):
        assert compare_cell(PolicyDecision.PERMIT_FILTERED, 200, 5, total=10) == CellResult.PASS

    def test_filtered_with_full_count_is_violation(self):
        assert compare_cell(PolicyDecision.PERMIT_FILTERED, 200, 10, total=10) == CellResult.VIOLATION

    def test_filtered_with_zero_count_is_warning(self):
        assert compare_cell(PolicyDecision.PERMIT_FILTERED, 200, 0, total=10) == CellResult.WARNING

    def test_unprotected_with_200_is_pass(self):
        assert compare_cell(PolicyDecision.PERMIT_UNPROTECTED, 200, 10) == CellResult.PASS

    def test_unprotected_with_403_is_violation(self):
        assert compare_cell(PolicyDecision.PERMIT_UNPROTECTED, 403, None) == CellResult.VIOLATION


class TestVerificationReportRoundTrip:
    """Test save/load serialization."""

    def test_save_and_load(self, tmp_path):
        report = VerificationReport(
            app_name="test",
            timestamp="2026-03-18T00:00:00Z",
            dazzle_version="0.42.0",
            matrix=None,  # simplified for unit test
            cells=[
                VerifiedCell(
                    role="admin", entity="Shape", operation="list",
                    expected=PolicyDecision.PERMIT, observed_status=200,
                    observed_count=10, result=CellResult.PASS,
                    audit_records=[], detail="",
                ),
            ],
            total=1, passed=1, violated=0, warnings=0,
        )
        path = tmp_path / "report.json"
        report.save(path)
        loaded = VerificationReport.load(path)
        assert loaded.app_name == "test"
        assert loaded.total == 1
        assert loaded.passed == 1
        assert loaded.cells[0].role == "admin"
```

- [ ] **Step 1: Define `VerificationReport` and `CellResult` types in `verifier.py`**

```python
class CellResult(str, Enum):
    PASS = "PASS"
    VIOLATION = "VIOLATION"
    WARNING = "WARNING"

@dataclass
class VerifiedCell:
    role: str
    entity: str
    operation: str
    expected: PolicyDecision
    observed_status: int
    observed_count: int | None
    result: CellResult
    audit_records: list[AccessDecisionRecord]
    detail: str

@dataclass
class VerificationReport:
    app_name: str
    timestamp: str
    dazzle_version: str
    matrix: AccessMatrix
    cells: list[VerifiedCell]
    total: int
    passed: int
    violated: int
    warnings: int

    def to_json(self) -> dict: ...
    def save(self, path: Path) -> None: ...

    @classmethod
    def load(cls, path: Path) -> VerificationReport: ...
```

- [ ] **Step 2: Implement probe logic**

The `verify(project_root, *, role_filter, entity_filter)` function orchestrates the pipeline. Use `httpx.AsyncClient` to probe endpoints. Authentication via the existing `/auth/login` endpoint.

- [ ] **Step 3: Implement `report.py`**

```python
def generate_report(report: VerificationReport, format: str = "markdown") -> str:
    """Generate compliance report from verification results."""
```

- [ ] **Step 4: Add `verify` and `report` CLI commands**

```python
@rbac_app.command("verify")
def verify(...): ...

@rbac_app.command("report")
def report(...): ...
```

- [ ] **Step 5: Test against Shapes app**

Run: `cd examples/shapes_validation && dazzle rbac verify`
Expected: All cells PASS (after #520 fix). Verification report saved.

Run: `dazzle rbac report`
Expected: Markdown compliance report printed.

- [ ] **Step 6: Lint and commit**

```bash
git add src/dazzle/rbac/verifier.py src/dazzle/rbac/report.py src/dazzle/cli/rbac.py
git commit -m "feat: dynamic RBAC verifier and compliance report (Layer 2)"
```

---

## Execution Dependencies

```
Task 1 (Fix #520)
    ↓
Task 2 (Audit types) ──→ Task 3 (Instrument evaluator)
    ↓
Task 4 (Matrix generator)
    ↓
Task 5 (Shapes DSL) ──→ Task 6 (CLI matrix)
    ↓                        ↓
Task 7 (MCP)           Task 8 (Verifier + Report + CLI)
```

**Parallelism**: Tasks 1 and 2 can run in parallel (no shared files). Task 3 depends on Task 2 (needs audit types). Task 4 depends on Task 2 (imports audit types). Task 5 is independent but should follow Task 4 so the matrix can be tested against it. Tasks 6 and 7 depend on Task 4. Task 8 depends on all prior tasks.
