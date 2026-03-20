# Runtime Parameters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add runtime-configurable parameters to the DSL that are resolved per-request with tenant-scoped cascade (user → tenant → system → default), enabling operational values like thresholds and timeouts to vary without rebuilding the app.

**Architecture:** `param` is a new top-level DSL construct declaring typed parameters with defaults and constraints. `param("key")` references in other constructs emit `ParamRef` IR nodes. At request time, `ParamResolver` looks up overrides from a `_dazzle_params` DB table with scope cascade. MCP tools provide read access; CLI commands handle writes.

**Tech Stack:** Python 3.12, Pydantic v2, PostgreSQL (JSONB), FastAPI, Typer, pytest.

**Spec:** `docs/superpowers/specs/2026-03-20-runtime-params.md`

---

### Task 1: IR Types — ParamSpec, ParamRef, ParamConstraints

Define the data model. No parser, no runtime — pure types.

**Files:**
- Create: `src/dazzle/core/ir/params.py`
- Modify: `src/dazzle/core/ir/appspec.py`
- Modify: `src/dazzle/core/ir/module.py`
- Modify: `src/dazzle/core/ir/__init__.py`
- Test: `tests/unit/test_param_models.py`

- [ ] **Step 1: Write tests for model construction and serialization**

```python
# tests/unit/test_param_models.py
from dazzle.core.ir.params import ParamSpec, ParamRef, ParamConstraints

class TestParamSpec:
    def test_construction(self):
        p = ParamSpec(
            key="heatmap.rag.thresholds",
            param_type="list[float]",
            default=[40, 60],
            scope="tenant",
            description="RAG boundaries",
            category="Assessment Display",
        )
        assert p.key == "heatmap.rag.thresholds"
        assert p.scope == "tenant"

    def test_with_constraints(self):
        c = ParamConstraints(min_length=2, max_length=5, ordered="ascending", range=[0, 100])
        p = ParamSpec(key="x.y", param_type="list[float]", default=[40, 60], scope="system", constraints=c)
        assert p.constraints.ordered == "ascending"

    def test_json_round_trip(self):
        p = ParamSpec(key="a.b", param_type="int", default=42, scope="tenant")
        data = p.model_dump()
        restored = ParamSpec.model_validate(data)
        assert restored == p

class TestParamRef:
    def test_construction(self):
        ref = ParamRef(key="heatmap.rag.thresholds", param_type="list[float]", default=[40, 60])
        assert ref.key == "heatmap.rag.thresholds"

    def test_frozen(self):
        ref = ParamRef(key="a.b", param_type="int", default=0)
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ref.key = "c.d"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_param_models.py -v`

- [ ] **Step 3: Implement IR types**

Create `src/dazzle/core/ir/params.py`:

```python
"""Runtime parameter specification types."""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

class ParamConstraints(BaseModel):
    model_config = ConfigDict(frozen=True)
    min_value: float | None = None
    max_value: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    ordered: str | None = None        # "ascending" | "descending"
    range: list[float] | None = None  # [min, max] for list elements
    enum_values: list[str] | None = None
    pattern: str | None = None

class ParamSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    key: str
    param_type: str
    default: Any
    scope: Literal["system", "tenant", "user"]
    constraints: ParamConstraints | None = None
    description: str | None = None
    category: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    sensitive: bool = False

class ParamRef(BaseModel):
    model_config = ConfigDict(frozen=True)
    key: str
    param_type: str
    default: Any
```

- [ ] **Step 4: Add to AppSpec and ModuleFragment**

In `src/dazzle/core/ir/module.py`, add after the last list field (~line 146):
```python
params: list[ParamSpec] = Field(default_factory=list)
```

In `src/dazzle/core/ir/appspec.py`, add after `grant_schemas` (~line 155):
```python
params: list[ParamSpec] = Field(default_factory=list)
```

In `src/dazzle/core/ir/__init__.py`, add imports:
```python
from .params import ParamConstraints, ParamRef, ParamSpec
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_param_models.py -v`

- [ ] **Step 6: Run full suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=60 -q`

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/core/ir/params.py src/dazzle/core/ir/appspec.py src/dazzle/core/ir/module.py src/dazzle/core/ir/__init__.py tests/unit/test_param_models.py
git commit -m "feat(ir): runtime parameter types — ParamSpec, ParamRef, ParamConstraints (#572)"
```

---

### Task 2: Lexer + Parser — `param` Construct and `param()` References

Parse `param key "description":` declarations and `param("key")` references in constructs.

**Files:**
- Modify: `src/dazzle/core/lexer.py`
- Create: `src/dazzle/core/dsl_parser_impl/params.py`
- Modify: `src/dazzle/core/dsl_parser_impl/__init__.py`
- Modify: `src/dazzle/core/dsl_parser_impl/base.py`
- Modify: `src/dazzle/core/dsl_parser_impl/workspace.py`
- Test: `tests/unit/test_param_parser.py`

- [ ] **Step 1: Write parser tests**

```python
# tests/unit/test_param_parser.py
from pathlib import Path
from dazzle.core.dsl_parser_impl import parse_dsl

class TestParamDeclaration:
    def test_basic_param(self):
        dsl = '''
module test_app
app test "Test"

param heatmap.rag.thresholds "RAG boundary percentages":
  type: list[float]
  default: [40, 60]
  scope: tenant
'''
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        assert len(fragment.params) == 1
        p = fragment.params[0]
        assert p.key == "heatmap.rag.thresholds"
        assert p.param_type == "list[float]"
        assert p.default == [40, 60]
        assert p.scope == "tenant"

    def test_param_with_constraints(self):
        dsl = '''
module test_app
app test "Test"

param sync.timeout "Sync timeout seconds":
  type: int
  default: 30
  scope: system
  constraints:
    min_value: 1
    max_value: 300
'''
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        p = fragment.params[0]
        assert p.constraints is not None
        assert p.constraints.min_value == 1
        assert p.constraints.max_value == 300

class TestParamReference:
    def test_param_ref_in_heatmap_thresholds(self):
        dsl = '''
module test_app
app test "Test"

param heatmap.rag.thresholds "RAG boundaries":
  type: list[float]
  default: [40, 60]
  scope: tenant

entity Task "Task":
  id: uuid pk
  title: str

workspace dashboard "Dashboard":
  region tasks:
    source: Task
    display: heatmap
    rows: title
    columns: title
    value: title
    thresholds: param("heatmap.rag.thresholds")
'''
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        region = fragment.workspaces[0].regions[0]
        from dazzle.core.ir.params import ParamRef
        assert isinstance(region.heatmap_thresholds, ParamRef)
        assert region.heatmap_thresholds.key == "heatmap.rag.thresholds"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_param_parser.py -v`

- [ ] **Step 3: Add PARAM token to lexer**

In `src/dazzle/core/lexer.py`, add to the `TokenType` enum (after the last keyword, before v0.3.1 section):
```python
PARAM = "param"
```

In `src/dazzle/core/dsl_parser_impl/base.py`, add `TokenType.PARAM` to `KEYWORD_AS_IDENTIFIER_TYPES` set.

- [ ] **Step 4: Create parser mixin**

Create `src/dazzle/core/dsl_parser_impl/params.py`:

```python
"""Parser mixin for runtime parameter declarations."""
from __future__ import annotations
from typing import TYPE_CHECKING, Any
from dazzle.core import ir
from dazzle.core.lexer import TokenType

if TYPE_CHECKING:
    from .base import ParserProtocol

class ParamParserMixin:
    """Mixin for parsing param declarations."""

    def parse_param(self: "ParserProtocol") -> ir.ParamSpec:
        """Parse a param declaration block."""
        # Header: param key.name "description":
        name = self.expect(TokenType.IDENTIFIER).value
        # Allow dotted names: heatmap.rag.thresholds
        while self.match(TokenType.DOT):
            self.advance()
            name += "." + self.expect_identifier_or_keyword().value

        description = None
        if self.match(TokenType.STRING):
            description = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        param_type = "str"
        default: Any = None
        scope = "system"
        category = None
        constraints = None
        depends_on: list[str] = []
        sensitive = False

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            key = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)

            if key == "type":
                # Capture type as string until newline (e.g., "list[float]")
                parts = []
                while not self.match(TokenType.NEWLINE, TokenType.DEDENT):
                    parts.append(self.advance().value)
                param_type = "".join(parts)
            elif key == "default":
                default = self._parse_param_value()
            elif key == "scope":
                scope = self.expect_identifier_or_keyword().value
            elif key == "category":
                category = self.expect(TokenType.STRING).value
            elif key == "sensitive":
                sensitive = self.expect_identifier_or_keyword().value == "true"
            elif key == "depends_on":
                depends_on = self._parse_param_string_list()
            elif key == "constraints":
                constraints = self._parse_param_constraints()
            else:
                # Skip unknown keys
                while not self.match(TokenType.NEWLINE, TokenType.DEDENT):
                    self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.ParamSpec(
            key=name,
            param_type=param_type,
            default=default,
            scope=scope,
            constraints=constraints,
            description=description,
            category=category,
            depends_on=depends_on,
            sensitive=sensitive,
        )

    def _parse_param_value(self: "ParserProtocol") -> Any:
        """Parse a literal value: number, string, bool, or list."""
        if self.match(TokenType.LBRACKET):
            return self._parse_param_list()
        if self.match(TokenType.STRING):
            return self.advance().value
        if self.match(TokenType.NUMBER):
            val = self.advance().value
            return float(val) if "." in val else int(val)
        token = self.expect_identifier_or_keyword()
        if token.value == "true":
            return True
        if token.value == "false":
            return False
        return token.value

    def _parse_param_list(self: "ParserProtocol") -> list:
        """Parse a bracket-enclosed list: [1, 2, 3]."""
        self.advance()  # consume [
        items = []
        while not self.match(TokenType.RBRACKET):
            self.skip_newlines()
            if self.match(TokenType.RBRACKET):
                break
            items.append(self._parse_param_value())
            if self.match(TokenType.COMMA):
                self.advance()
            self.skip_newlines()
        self.expect(TokenType.RBRACKET)
        return items

    def _parse_param_string_list(self: "ParserProtocol") -> list[str]:
        """Parse: [key1, key2, key3]."""
        self.expect(TokenType.LBRACKET)
        items = []
        while not self.match(TokenType.RBRACKET):
            self.skip_newlines()
            if self.match(TokenType.RBRACKET):
                break
            items.append(self.expect_identifier_or_keyword().value)
            if self.match(TokenType.COMMA):
                self.advance()
            self.skip_newlines()
        self.expect(TokenType.RBRACKET)
        return items

    def _parse_param_constraints(self: "ParserProtocol") -> ir.ParamConstraints:
        """Parse constraints block."""
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        kwargs: dict[str, Any] = {}
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            ckey = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)

            if ckey in ("min_value", "max_value"):
                kwargs[ckey] = float(self.expect(TokenType.NUMBER).value)
            elif ckey in ("min_length", "max_length"):
                kwargs[ckey] = int(self.expect(TokenType.NUMBER).value)
            elif ckey == "ordered":
                kwargs[ckey] = self.expect_identifier_or_keyword().value
            elif ckey == "range":
                kwargs[ckey] = self._parse_param_list()
            elif ckey == "enum_values":
                kwargs[ckey] = self._parse_param_string_list()
            elif ckey == "pattern":
                kwargs[ckey] = self.expect(TokenType.STRING).value
            self.skip_newlines()

        self.expect(TokenType.DEDENT)
        return ir.ParamConstraints(**kwargs)
```

- [ ] **Step 5: Register mixin and dispatch**

In `src/dazzle/core/dsl_parser_impl/__init__.py`:

Add import at the top with other mixins:
```python
from .params import ParamParserMixin
```

Add `ParamParserMixin` to the `Parser` class bases.

Add dispatch method (follow the `_dispatch_story` pattern at ~line 224):
```python
def _dispatch_param(self, fragment: "ir.ModuleFragment") -> "ir.ModuleFragment":
    self.advance()  # consume 'param' token
    param = self.parse_param()
    return ir.ModuleFragment(
        **{
            **{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields},
            "params": [*fragment.params, param],
        }
    )
```

Add to dispatch table (~line 555+):
```python
TokenType.PARAM: self._dispatch_param,
```

- [ ] **Step 6: Add param() reference parsing in workspace regions**

In `src/dazzle/core/dsl_parser_impl/workspace.py`, modify `parse_workspace_region()`. In the `thresholds:` branch (~where `heatmap_thresholds` is parsed), add a check for `param(` syntax:

```python
# In the thresholds: branch, before parsing the bracket list:
if self.match(TokenType.PARAM):
    self.advance()  # consume 'param'
    self.expect(TokenType.LPAREN)
    key = self.expect(TokenType.STRING).value
    self.expect(TokenType.RPAREN)
    # Look up default from declared params (not available here, use None)
    heatmap_thresholds = ir.ParamRef(key=key, param_type="list[float]", default=[])
else:
    # existing bracket list parsing
```

Also modify `src/dazzle/core/ir/workspaces.py` to accept `ParamRef` in the thresholds field (add `from .params import ParamRef` at the top):
```python
heatmap_thresholds: list[float] | ParamRef = Field(default_factory=list)
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/unit/test_param_parser.py -v`

- [ ] **Step 8: Run full suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=60 -q`

- [ ] **Step 9: Commit**

```bash
git commit -m "feat(parser): param declaration + param() reference syntax (#572)"
```

---

### Task 3: Linker Integration — Merge Params into AppSpec

Wire params through the linker so they appear in the final AppSpec.

**Files:**
- Modify: `src/dazzle/core/linker.py`
- Test: `tests/unit/test_param_linker.py`

- [ ] **Step 1: Write tests**

```python
# tests/unit/test_param_linker.py
from pathlib import Path
from dazzle.core.dsl_parser_impl import parse_dsl

class TestParamLinker:
    def test_params_appear_in_appspec(self):
        dsl = '''
module test_app
app test "Test"

param display.page_size "Default page size":
  type: int
  default: 25
  scope: tenant

entity Task "Task":
  id: uuid pk
  title: str
'''
        # Parse
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        assert len(fragment.params) == 1
        # The linker merges fragments into AppSpec
        # Just verify the fragment has the param for now

    def test_duplicate_param_keys_error(self):
        # Two params with same key should be caught
        pass  # Implement if linker validates uniqueness
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Add params to linker merge**

In `src/dazzle/core/linker.py`, find the `AppSpec()` constructor call (~line 123) and add:
```python
params=merged_fragment.params,  # v0.44.0 Runtime Parameters
```

- [ ] **Step 4: Run tests + full suite**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(linker): merge runtime params into AppSpec (#572)"
```

---

### Task 4: Param Store — DB Table + Resolver

Storage layer for runtime parameter overrides with scope cascade.

**Files:**
- Create: `src/dazzle_back/runtime/param_store.py`
- Test: `tests/unit/test_param_store.py`

- [ ] **Step 1: Write tests**

Tests should cover:
- `validate_param_value(spec, value)` — type checking, constraint enforcement
- `ParamResolver.resolve(key, tenant_id)` — returns default when no override
- `ParamResolver.resolve(key, tenant_id)` — returns tenant override when set
- `ParamResolver.resolve(key, tenant_id)` — cascade order: user > tenant > system > default
- `resolve_value(raw, resolver, tenant_id)` — passes through literals, resolves ParamRef
- Invalid value rejected by validate

Use in-memory dicts for store in tests (no DB needed).

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement ParamStore and ParamResolver**

Create `src/dazzle_back/runtime/param_store.py`:

```python
"""Runtime parameter storage and resolution."""
from __future__ import annotations
import json
import logging
import time
from typing import Any
from dazzle.core.ir.params import ParamConstraints, ParamRef, ParamSpec

logger = logging.getLogger(__name__)

def validate_param_value(spec: ParamSpec, value: Any) -> list[str]:
    """Validate a value against param type and constraints."""
    errors: list[str] = []
    # Type validation
    expected = spec.param_type
    if expected == "int" and not isinstance(value, int):
        errors.append(f"Expected int, got {type(value).__name__}")
    elif expected == "float" and not isinstance(value, (int, float)):
        errors.append(f"Expected float, got {type(value).__name__}")
    elif expected == "bool" and not isinstance(value, bool):
        errors.append(f"Expected bool, got {type(value).__name__}")
    elif expected == "str" and not isinstance(value, str):
        errors.append(f"Expected str, got {type(value).__name__}")
    elif expected.startswith("list[") and not isinstance(value, list):
        errors.append(f"Expected list, got {type(value).__name__}")

    # Constraint validation
    if spec.constraints and not errors:
        c = spec.constraints
        if isinstance(value, list):
            if c.min_length is not None and len(value) < c.min_length:
                errors.append(f"Minimum length {c.min_length}, got {len(value)}")
            if c.max_length is not None and len(value) > c.max_length:
                errors.append(f"Maximum length {c.max_length}, got {len(value)}")
            if c.ordered == "ascending" and value != sorted(value):
                errors.append("Values must be in ascending order")
            if c.ordered == "descending" and value != sorted(value, reverse=True):
                errors.append("Values must be in descending order")
            if c.range is not None and len(c.range) == 2:
                lo, hi = c.range
                for v in value:
                    if not (lo <= v <= hi):
                        errors.append(f"Value {v} outside range [{lo}, {hi}]")
        if isinstance(value, (int, float)):
            if c.min_value is not None and value < c.min_value:
                errors.append(f"Value {value} below minimum {c.min_value}")
            if c.max_value is not None and value > c.max_value:
                errors.append(f"Value {value} above maximum {c.max_value}")
    return errors


class ParamResolver:
    """Resolves param references at request time with scope cascade."""

    def __init__(self, specs: dict[str, ParamSpec], overrides: dict[tuple[str, str, str], Any] | None = None):
        self._specs = specs
        self._overrides = overrides or {}
        self._cache: dict[str, tuple[Any, str, float]] = {}

    def resolve(self, key: str, tenant_id: str | None = None, user_id: str | None = None) -> tuple[Any, str]:
        """Resolve param value. Returns (value, source)."""
        spec = self._specs.get(key)
        if spec is None:
            raise KeyError(f"Unknown param: {key}")

        cache_key = f"{key}:{tenant_id or ''}:{user_id or ''}"
        cached = self._cache.get(cache_key)
        if cached and cached[2] > time.time():
            return cached[0], cached[1]

        # Cascade: user → tenant → system → default
        for scope, scope_id in [
            ("user", user_id or ""),
            ("tenant", tenant_id or ""),
            ("system", ""),
        ]:
            if not scope_id and scope != "system":
                continue
            override = self._overrides.get((key, scope, scope_id))
            if override is not None:
                source = f"{scope}/{scope_id}" if scope_id else scope
                self._cache[cache_key] = (override, source, time.time() + 60)
                return override, source

        return spec.default, "default"

    def set_override(self, key: str, scope: str, scope_id: str, value: Any) -> list[str]:
        """Set a param override. Returns validation errors (empty = success)."""
        spec = self._specs.get(key)
        if spec is None:
            return [f"Unknown param: {key}"]
        errors = validate_param_value(spec, value)
        if not errors:
            self._overrides[(key, scope, scope_id)] = value
            # Invalidate cache entries for this key
            self._cache = {k: v for k, v in self._cache.items() if not k.startswith(f"{key}:")}
        return errors


def resolve_value(raw: Any, resolver: ParamResolver | None, tenant_id: str | None = None) -> Any:
    """Resolve a value that might be a ParamRef or a literal."""
    if isinstance(raw, ParamRef):
        if resolver is None:
            return raw.default
        value, _ = resolver.resolve(raw.key, tenant_id=tenant_id)
        return value
    return raw
```

- [ ] **Step 4: Run tests + full suite**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(runtime): param store + resolver with scope cascade (#572)"
```

---

### Task 5: Runtime Integration — Wire ParamResolver into Workspace Rendering

Connect the resolver to the workspace region handler so `ParamRef` values in heatmap thresholds are resolved at request time.

**Files:**
- Modify: `src/dazzle_back/runtime/server.py`
- Modify: `src/dazzle_back/runtime/workspace_rendering.py`
- Modify: `src/dazzle_back/runtime/migrations.py`
- Test: `tests/unit/test_param_integration.py`

- [ ] **Step 0: Add `_dazzle_params` table migration**

In `src/dazzle_back/runtime/migrations.py`, add a function alongside the existing `MigrationHistory._ensure_table()` pattern:

```python
def ensure_dazzle_params_table(db_manager: DatabaseBackend) -> None:
    """Create the _dazzle_params framework table if it doesn't exist."""
    with db_manager.connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _dazzle_params (
                key TEXT NOT NULL,
                scope TEXT NOT NULL,
                scope_id TEXT NOT NULL DEFAULT '',
                value_json JSONB NOT NULL,
                updated_by TEXT,
                updated_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (key, scope, scope_id)
            )
        """)
```

Call it in `server.py` `_setup_database()` after `auto_migrate()`, alongside the param resolver creation.

Note: `WorkspaceRegionContext` is a `@dataclass` (not Pydantic), so new fields use plain type annotations:
```python
param_resolver: Any = None  # ParamResolver | None
tenant_id: str | None = None
```

- [ ] **Step 1: Write integration tests**

Tests:
- Heatmap with static thresholds still works (no regression)
- Heatmap with `ParamRef` thresholds resolves to default when no override
- `resolve_value` with literal passes through
- `resolve_value` with `ParamRef` resolves via resolver

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Create ParamResolver at server startup**

In `src/dazzle_back/runtime/server.py`, in `_setup_database()` after migrations, create the resolver:

```python
# Build param resolver from AppSpec (#572)
from dazzle_back.runtime.param_store import ParamResolver
param_specs = {p.key: p for p in self._appspec.params} if hasattr(self._appspec, 'params') else {}
self._param_resolver = ParamResolver(specs=param_specs)
```

Pass it to the workspace rendering context.

- [ ] **Step 4: Resolve ParamRef in heatmap thresholds**

In `src/dazzle_back/runtime/workspace_rendering.py`, in the heatmap section (~line 633):

```python
from dazzle_back.runtime.param_store import resolve_value

# Replace:
heatmap_thresholds = list(getattr(ctx.ctx_region, "heatmap_thresholds", None) or [])
# With:
raw_thresholds = getattr(ctx.ctx_region, "heatmap_thresholds", None)
heatmap_thresholds = list(resolve_value(raw_thresholds, ctx.param_resolver, tenant_id=ctx.tenant_id) or [])
```

Add `param_resolver` and `tenant_id` fields to `WorkspaceRegionContext`.

- [ ] **Step 5: Run tests + full suite**

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(runtime): wire ParamResolver into workspace rendering (#572)"
```

---

### Task 6: MCP Tool + CLI Commands

Read-only MCP access and CLI write commands for param management.

**Files:**
- Create: `src/dazzle/mcp/server/handlers/param.py`
- Modify: `src/dazzle/mcp/server/handlers_consolidated.py`
- Modify: `src/dazzle/mcp/server/tools_consolidated.py`
- Create: `src/dazzle/cli/param.py`
- Modify: `src/dazzle/cli/__init__.py`
- Test: `tests/unit/test_param_cli.py`

- [ ] **Step 1: Write tests for MCP handler**

Test `param_list_handler` returns all declared params with defaults.
Test `param_get_handler` returns value + provenance for a specific key.

- [ ] **Step 2: Implement MCP handler**

Create `src/dazzle/mcp/server/handlers/param.py`:
```python
from .common import error_response, load_project_appspec, wrap_handler_errors

@wrap_handler_errors
def param_list_handler(project_root: Path, args: dict[str, Any]) -> str:
    """List all declared runtime parameters."""
    appspec = load_project_appspec(project_root)
    params = [p.model_dump(mode="json") for p in appspec.params]
    return json.dumps({"params": params, "total": len(params)}, indent=2)

@wrap_handler_errors
def param_get_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Get a specific parameter's DSL declaration + default value.

    Note: MCP tools are stateless reads without tenant context, so this
    returns the declared spec and default — not the runtime-resolved value.
    Use CLI `dazzle param get --tenant X` for tenant-specific resolution.
    """
    key = args.get("key", "")
    appspec = load_project_appspec(project_root)
    spec = next((p for p in appspec.params if p.key == key), None)
    if spec is None:
        return error_response(f"Unknown param: {key}")
    return json.dumps(spec.model_dump(mode="json"), indent=2)
```

- [ ] **Step 3: Register in consolidated handlers + tools**

- [ ] **Step 4: Implement CLI commands**

Create `src/dazzle/cli/param.py` with `list`, `get`, `set`, `validate` commands.

- [ ] **Step 5: Register CLI in `__init__.py`**

- [ ] **Step 6: Run tests + full suite**

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(mcp+cli): param list/get/set commands (#572)"
```

---

### Task 7: Startup Validation + CHANGELOG

Validate stored overrides at startup and update documentation.

**Files:**
- Modify: `src/dazzle_back/runtime/server.py`
- Modify: `CHANGELOG.md`
- Test: extend `tests/unit/test_param_store.py`

- [ ] **Step 1: Add startup validation**

After creating `ParamResolver`, validate any stored overrides against current DSL declarations. Log warnings for type mismatches or removed params.

- [ ] **Step 2: Update CHANGELOG**

Add under `[Unreleased]`:
```markdown
### Added
- `param` DSL construct for runtime-configurable parameters with tenant-scoped cascade
- `param("key")` reference syntax in workspace region constructs
- `_dazzle_params` table for storing per-scope overrides
- `param list/get/set/validate` MCP operations and CLI commands
- Startup validation of stored param overrides against DSL declarations
```

- [ ] **Step 3: Run full suite + lint**

- [ ] **Step 4: Final commit + push**

```bash
git commit -m "feat: startup param validation + changelog (#572)"
git push
```

---

### Task Dependency Order

```
Task 1 (IR types)
  ↓
Task 2 (lexer + parser) ← needs Task 1
  ↓
Task 3 (linker) ← needs Task 2
  ↓
Task 4 (store + resolver) ← needs Task 1 (only IR types)
  ↓
Task 5 (runtime integration) ← needs Tasks 3 + 4
  ↓
Task 6 (MCP + CLI) ← needs Tasks 3 + 4
  ↓
Task 7 (validation + docs) ← needs Task 5
```

Tasks 1-3 are sequential (IR → parser → linker). Task 4 can start after Task 1. Tasks 5 and 6 can proceed in parallel after Tasks 3+4. Task 7 is the final cleanup.
