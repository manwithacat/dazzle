# `tenant_host:` Keyword Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement issue #1289 — a `tenant_host:` per-entity DSL keyword that auto-mounts Host-header tenant resolution, an LRU cache, history 301/410 redirects, a cross-tenant auth guard, and `__Host-` / `__Secure-` cookie wiring. Replaces five project-side modules in AegisMark phase 1.

**Architecture:** Per-entity `TenantHostSpec` IR; new `dazzle.http.runtime.tenant` package containing pure-logic cache + resolver + cookies + guard + templates plus a `TenantResolutionMiddleware`. App factory auto-mounts middleware when any entity declares `tenant_host:`. Auth dependency injects the cross-tenant guard. Cookie names switch convention only for `tenant_host`-using apps. Slug-history table is project-provided per the spec (the slug field's history sub-field is #1288 Phase 3, deferred).

**Tech Stack:** Python 3.12, FastAPI, Starlette `BaseHTTPMiddleware`, Pydantic v2, the existing Dazzle Repository layer, pytest.

**Spec:** [`docs/superpowers/specs/2026-05-28-tenant-host-keyword-design.md`](../specs/2026-05-28-tenant-host-keyword-design.md)

**Ship discipline:** Each slice ends with `/bump patch` + `/ship`. Seven independent versions in total. Each slice must leave the worktree clean and CI green.

---

## Slice 1 — IR + parser + grammar + validator (stub middleware)

**Purpose:** Land the `tenant_host:` block in the DSL so it parses and validates. Middleware is a stub that raises `NotImplementedError` if mounted, so the validator pass can light up without runtime risk.

**Files in this slice:**
- Create: `src/dazzle/http/runtime/tenant/__init__.py`
- Create: `src/dazzle/http/runtime/tenant/middleware.py` (stub only)
- Modify: `src/dazzle/core/ir/domain.py` (add `TenantHostSpec`, attach to `EntitySpec`)
- Modify: `src/dazzle/core/ir/__init__.py` (export `TenantHostSpec`)
- Modify: `src/dazzle/core/lexer.py` (`TENANT_HOST` token)
- Modify: `src/dazzle/core/dsl_parser_impl/entity.py` (block dispatcher + sub-field parser)
- Modify: `src/dazzle/core/validator.py` (the 6 hard-error rules)
- Modify: `src/dazzle/core/lint.py` (info-level warnings 6 & 7)
- Modify: `docs/reference/grammar.md`
- Regenerate: `docs/api-surface/{ir-types,dsl-constructs}.txt`
- Test: `tests/unit/test_tenant_host_parser.py`
- Test: `tests/unit/test_tenant_host_validator.py`

---

### Task 1.1 — Add `TenantHostSpec` IR type

**Files:**
- Modify: `src/dazzle/core/ir/domain.py` (insert before `class EntitySpec` at line 320)
- Modify: `src/dazzle/core/ir/__init__.py` (add `TenantHostSpec` to the `__all__`-style export block)
- Test: `tests/unit/test_tenant_host_parser.py` (new file)

- [ ] **Step 1: Write the failing IR test**

Create `tests/unit/test_tenant_host_parser.py`:

```python
"""Tests for the `tenant_host:` block parser and IR (#1289)."""
from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl


def test_tenant_host_spec_minimal_fields():
    """TenantHostSpec accepts the minimum required fields."""
    spec = ir.TenantHostSpec(domain="example.com", slug_field="slug")
    assert spec.domain == "example.com"
    assert spec.slug_field == "slug"
    assert spec.canonical_hosts == []
    assert spec.cookie_scope == "host"
    assert spec.super_admin_role == "super_admin"
    assert spec.history_entity is None
    assert spec.order is None


def test_tenant_host_spec_is_frozen():
    """TenantHostSpec instances are immutable."""
    spec = ir.TenantHostSpec(domain="example.com", slug_field="slug")
    with pytest.raises(Exception):
        spec.domain = "other.com"  # type: ignore[misc]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_tenant_host_parser.py::test_tenant_host_spec_minimal_fields -v`
Expected: FAIL with `AttributeError: module 'dazzle.core.ir' has no attribute 'TenantHostSpec'`

- [ ] **Step 3: Add the IR class**

In `src/dazzle/core/ir/domain.py`, immediately before `class EntitySpec`:

```python
class TenantHostSpec(BaseModel):
    """Host-header tenant routing configuration for an entity (#1289).

    Auto-mounts the framework's TenantResolutionMiddleware when any entity
    declares this block. See docs/superpowers/specs/2026-05-28-tenant-host-keyword-design.md
    """

    model_config = ConfigDict(frozen=True)

    domain: str
    slug_field: str
    canonical_hosts: list[str] = Field(default_factory=list)
    cookie_scope: Literal["host", "apex"] = "host"
    super_admin_role: str = "super_admin"
    history_entity: str | None = None
    not_found_template: str | None = None
    expired_template: str | None = None
    order: int | None = None
```

Ensure imports at the top of the file include `Literal` from `typing` and `Field`, `ConfigDict` from `pydantic`.

- [ ] **Step 4: Attach to `EntitySpec`**

In `src/dazzle/core/ir/domain.py`, locate `class EntitySpec(BaseModel):` and add a new optional field. Place it next to other optional spec-level fields (look for `tenancy`, `temporal`, etc. or near the end of the field list before any validators):

```python
    tenant_host: TenantHostSpec | None = None
```

- [ ] **Step 5: Export from the IR package**

In `src/dazzle/core/ir/__init__.py`, locate the existing import / `__all__` block for domain IR types and add `TenantHostSpec`. The existing pattern looks like:

```python
from dazzle.core.ir.domain import (
    EntitySpec,
    FieldSpec,
    ...,
)
```

Add `TenantHostSpec` alphabetically. If there's an `__all__`, add `"TenantHostSpec"` there too.

- [ ] **Step 6: Run the IR tests to verify they pass**

Run: `pytest tests/unit/test_tenant_host_parser.py -v`
Expected: both tests PASS (2 passed)

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/core/ir/domain.py src/dazzle/core/ir/__init__.py tests/unit/test_tenant_host_parser.py
git commit -m "Add TenantHostSpec IR + EntitySpec.tenant_host field (#1289 slice 1)"
```

---

### Task 1.2 — Lexer token for `tenant_host`

**Files:**
- Modify: `src/dazzle/core/lexer.py:185` (insert near `SIGNING_VALIDATOR`)

- [ ] **Step 1: Write the failing lexer test**

Append to `tests/unit/test_tenant_host_parser.py`:

```python
from dazzle.core.lexer import Lexer, TokenType


def test_lexer_emits_tenant_host_token():
    """The lexer recognises `tenant_host` as a keyword."""
    tokens = list(Lexer("tenant_host", Path("<test>")).tokenize())
    assert tokens[0].type == TokenType.TENANT_HOST
    assert tokens[0].value == "tenant_host"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_tenant_host_parser.py::test_lexer_emits_tenant_host_token -v`
Expected: FAIL with `AttributeError: TENANT_HOST` or token type `IDENTIFIER` instead of `TENANT_HOST`.

- [ ] **Step 3: Add the token**

In `src/dazzle/core/lexer.py` after the existing `SIGNING_TEMPLATE` line (around 187), insert:

```python
    # #1289: per-entity Host-header tenant resolution
    TENANT_HOST = "tenant_host"
```

Inspect the lexer to confirm that the keyword set is constructed from the `TokenType` enum values automatically (it usually is — search the file for `value in (token.value for token in TokenType)` or a similar generator). If not, also add `tenant_host` to whatever keyword lookup dict exists.

- [ ] **Step 4: Run the lexer test to verify pass**

Run: `pytest tests/unit/test_tenant_host_parser.py::test_lexer_emits_tenant_host_token -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/lexer.py tests/unit/test_tenant_host_parser.py
git commit -m "Lexer: TENANT_HOST token (#1289 slice 1)"
```

---

### Task 1.3 — Parser for the `tenant_host:` block

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/entity.py` (extend the entity-block dispatcher and add a `_parse_tenant_host_block` method)

- [ ] **Step 1: Write the failing parser test**

Append to `tests/unit/test_tenant_host_parser.py`:

```python
TENANT_HOST_DSL = '''
module test_tenant
app test_tenant "Test"

entity Trust:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
    canonical_hosts: [www.example.com, example.com]
    cookie_scope: host
    super_admin_role: admin
    history_entity: TrustSlugHistory
    not_found_template: pkg.tpl:render_404
    expired_template: pkg.tpl:render_410
    order: 1
'''.lstrip()


def test_parser_extracts_full_tenant_host_block():
    _module, _app, _title, _config, _uses, fragment = parse_dsl(
        TENANT_HOST_DSL, Path("<test>")
    )
    trust = next(e for e in fragment.entities if e.name == "Trust")
    th = trust.tenant_host
    assert th is not None
    assert th.domain == "example.com"
    assert th.slug_field == "slug"
    assert th.canonical_hosts == ["www.example.com", "example.com"]
    assert th.cookie_scope == "host"
    assert th.super_admin_role == "admin"
    assert th.history_entity == "TrustSlugHistory"
    assert th.not_found_template == "pkg.tpl:render_404"
    assert th.expired_template == "pkg.tpl:render_410"
    assert th.order == 1


def test_parser_defaults_when_block_minimal():
    src = '''
module test_tenant
app test_tenant "Test"

entity Trust:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
'''.lstrip()
    _m, _a, _t, _c, _u, fragment = parse_dsl(src, Path("<test>"))
    trust = next(e for e in fragment.entities if e.name == "Trust")
    assert trust.tenant_host is not None
    assert trust.tenant_host.canonical_hosts == []
    assert trust.tenant_host.cookie_scope == "host"
    assert trust.tenant_host.order is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_tenant_host_parser.py::test_parser_extracts_full_tenant_host_block -v`
Expected: FAIL — block currently parsed as an unknown entity-level construct.

- [ ] **Step 3: Wire the block dispatcher**

In `src/dazzle/core/dsl_parser_impl/entity.py`, find the entity-level block dispatcher. Look for an `_ENTITY_BLOCK_KEYWORDS` dict or a chain of `if self.match(TokenType.SIGNABLE): ...` / `if self.match(TokenType.TEMPORAL): ...` near the entity-body parse loop (search for `TokenType.SIGNABLE`). Add a parallel arm:

```python
if self.match(TokenType.TENANT_HOST):
    self._parse_tenant_host_block(ctx)
    continue
```

- [ ] **Step 4: Add the block parser method**

Append to the same file (place near other `_parse_*_block` helpers — search for `def _parse_signable_block` for a good neighbour):

```python
def _parse_tenant_host_block(self, ctx: _EntityParseContext) -> None:
    """Parse the `tenant_host:` indented sub-field block (#1289).

    Expected sub-fields are documented in
    docs/superpowers/specs/2026-05-28-tenant-host-keyword-design.md.
    Unknown sub-fields raise a parse error so typos surface early.
    """
    self.advance()  # consume TENANT_HOST
    self.expect(TokenType.COLON)
    self.skip_newlines()
    self.expect(TokenType.INDENT)

    fields: dict[str, object] = {}
    while not self.match(TokenType.DEDENT) and not self.match(TokenType.EOF):
        key_tok = self.expect_identifier_or_keyword()
        key = key_tok.value
        self.expect(TokenType.COLON)
        if key == "canonical_hosts":
            fields[key] = self._parse_string_list()
        elif key == "order":
            fields[key] = int(self.expect(TokenType.NUMBER).value)
        else:
            fields[key] = self._parse_scalar_block_value()
        self.skip_newlines()

    self.expect(TokenType.DEDENT)

    allowed = {
        "domain", "slug_field", "canonical_hosts", "cookie_scope",
        "super_admin_role", "history_entity", "not_found_template",
        "expired_template", "order",
    }
    extra = set(fields) - allowed
    if extra:
        raise make_parse_error(
            f"Unknown sub-field(s) in tenant_host: block: {sorted(extra)}",
            self.file, key_tok.line, key_tok.column,
        )
    if "domain" not in fields or "slug_field" not in fields:
        raise make_parse_error(
            "tenant_host: requires `domain:` and `slug_field:` sub-fields",
            self.file, key_tok.line, key_tok.column,
        )
    ctx.tenant_host = ir.TenantHostSpec(**fields)  # type: ignore[arg-type]
```

If `_parse_scalar_block_value` and `_parse_string_list` don't already exist with those exact names, locate the equivalent helpers used by other block parsers in this file and call those instead (search for similar block parsers in this module first).

- [ ] **Step 5: Add `tenant_host` to the entity parse context**

In the same file, find `_EntityParseContext` (a `@dataclass` near the top of `entity.py`). Add:

```python
    tenant_host: ir.TenantHostSpec | None = None
```

And in the entity assembly code (search for `EntitySpec(`), pass it through:

```python
EntitySpec(
    ...,
    tenant_host=ctx.tenant_host,
)
```

- [ ] **Step 6: Run the parser tests to verify pass**

Run: `pytest tests/unit/test_tenant_host_parser.py -v`
Expected: 4 of 4 PASS.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/core/dsl_parser_impl/entity.py tests/unit/test_tenant_host_parser.py
git commit -m "Parse tenant_host: block on entities (#1289 slice 1)"
```

---

### Task 1.4 — Validator hard-error rules

**Files:**
- Create: `tests/unit/test_tenant_host_validator.py`
- Modify: `src/dazzle/core/validator.py`

- [ ] **Step 1: Write the failing validator tests**

Create `tests/unit/test_tenant_host_validator.py`:

```python
"""Tests for the tenant_host: validator pass (#1289)."""
from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.validator import validate_appspec


def _parse_and_validate(src: str) -> list[str]:
    _m, _a, _t, _c, _u, fragment = parse_dsl(src, Path("<test>"))
    # Build a minimal AppSpec-shaped object the validator accepts.
    # If validate_appspec needs a full AppSpec, adapt to the project's
    # smallest fixture (search tests for an existing call pattern).
    errors = validate_appspec(fragment)
    return [str(e) for e in errors]


def test_validator_rejects_slug_field_pointing_at_non_slug_field():
    src = '''
module t
app t "T"
entity Trust:
  id: uuid pk
  name: str(40) required
  tenant_host:
    domain: example.com
    slug_field: name
'''.lstrip()
    errors = _parse_and_validate(src)
    assert any("slug_field" in e and "slug" in e.lower() for e in errors)


def test_validator_rejects_unknown_history_entity():
    src = '''
module t
app t "T"
entity Trust:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
    history_entity: NoSuchEntity
'''.lstrip()
    errors = _parse_and_validate(src)
    assert any("history_entity" in e and "NoSuchEntity" in e for e in errors)


def test_validator_requires_order_when_two_entities_share_domain():
    src = '''
module t
app t "T"
entity Trust:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
entity School:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
'''.lstrip()
    errors = _parse_and_validate(src)
    assert any("order" in e and "example.com" in e for e in errors)


def test_validator_accepts_distinct_order_values():
    src = '''
module t
app t "T"
entity Trust:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
    order: 1
entity School:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
    order: 2
'''.lstrip()
    errors = _parse_and_validate(src)
    assert not any("order" in e for e in errors)


def test_validator_rejects_unimportable_template(monkeypatch):
    """Rule 5: dotted-path templates must resolve at validate time."""
    src = '''
module t
app t "T"
entity Trust:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
    not_found_template: no.such.module:render
'''.lstrip()
    errors = _parse_and_validate(src)
    assert any("not_found_template" in e and "no.such.module" in e for e in errors)


def test_validator_rejects_inconsistent_super_admin_role_across_domain():
    """Rule 6: multi-entity-same-domain must agree on cookie_scope, super_admin_role, canonical_hosts."""
    src = '''
module t
app t "T"
entity Trust:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
    order: 1
    super_admin_role: admin
entity School:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
    order: 2
    super_admin_role: owner
'''.lstrip()
    errors = _parse_and_validate(src)
    assert any("super_admin_role" in e and "example.com" in e for e in errors)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_tenant_host_validator.py -v`
Expected: all four tests FAIL — no validator code exists yet.

- [ ] **Step 3: Add the validator function**

In `src/dazzle/core/validator.py`, find the entry point for entity-level validation (search for the top-level `validate_appspec` or whichever function aggregates entity errors). Add a new helper:

```python
def _validate_tenant_host_blocks(
    appspec_or_fragment: object,
) -> list[str]:
    """Hard-error rules for tenant_host: (#1289).

    Rules 1-6 from docs/superpowers/specs/2026-05-28-tenant-host-keyword-design.md.
    """
    errors: list[str] = []
    entities = getattr(appspec_or_fragment, "entities", None) or getattr(
        appspec_or_fragment, "domain"
    ).entities

    by_domain: dict[str, list[tuple[int, EntitySpec]]] = {}
    entity_names: set[str] = {e.name for e in entities}

    for idx, entity in enumerate(entities):
        th = getattr(entity, "tenant_host", None)
        if th is None:
            continue

        # Rule 1: slug_field must name a slug-typed field on the same entity
        match = next((f for f in entity.fields if f.name == th.slug_field), None)
        if match is None:
            errors.append(
                f"Entity {entity.name!r}: tenant_host.slug_field "
                f"{th.slug_field!r} does not match any field on the entity."
            )
        elif getattr(match.type, "kind", None) != FieldTypeKind.SLUG:
            errors.append(
                f"Entity {entity.name!r}: tenant_host.slug_field {th.slug_field!r} "
                f"must point at a `slug:` typed field (got {match.type.kind})."
            )

        # Rule 2: domain must look like a host
        if "." not in th.domain or " " in th.domain:
            errors.append(
                f"Entity {entity.name!r}: tenant_host.domain {th.domain!r} "
                "is not a syntactically valid host."
            )

        # Rule 4: history_entity must exist
        if th.history_entity and th.history_entity not in entity_names:
            errors.append(
                f"Entity {entity.name!r}: tenant_host.history_entity "
                f"{th.history_entity!r} is not declared in this AppSpec."
            )

        by_domain.setdefault(th.domain, []).append((idx, entity))

    # Rule 3: when 2+ entities share a domain, each MUST carry distinct order:
    for domain, items in by_domain.items():
        if len(items) < 2:
            continue
        orders = [e.tenant_host.order for _, e in items]
        if any(o is None for o in orders) or len(set(orders)) != len(orders):
            errors.append(
                f"Domain {domain!r}: 2+ entities declare tenant_host on this "
                "domain; each must carry a distinct `order: N` sub-field. "
                f"Entities involved: {[e.name for _, e in items]}."
            )

    # Rule 5: dotted-path templates must be importable + callable at validate time
    import importlib

    for entity in entities:
        th = getattr(entity, "tenant_host", None)
        if th is None:
            continue
        for attr, label in (
            (th.not_found_template, "not_found_template"),
            (th.expired_template, "expired_template"),
        ):
            if attr is None:
                continue
            try:
                mod_name, _, sym = attr.partition(":")
                mod = importlib.import_module(mod_name)
                target = getattr(mod, sym, None)
                if not callable(target):
                    errors.append(
                        f"Entity {entity.name!r}: tenant_host.{label} "
                        f"{attr!r} resolved but is not callable."
                    )
            except Exception as exc:  # ImportError, ModuleNotFoundError, etc.
                errors.append(
                    f"Entity {entity.name!r}: tenant_host.{label} "
                    f"{attr!r} could not be imported: {exc}"
                )

    # Rule 6: domain-level sub-fields must agree across entities sharing a domain
    for domain, items in by_domain.items():
        if len(items) < 2:
            continue
        for shared in ("cookie_scope", "super_admin_role", "canonical_hosts"):
            values = {tuple(getattr(e.tenant_host, shared)) if shared == "canonical_hosts"
                      else getattr(e.tenant_host, shared) for _, e in items}
            if len(values) > 1:
                errors.append(
                    f"Domain {domain!r}: entities {[e.name for _, e in items]} "
                    f"disagree on tenant_host.{shared} {values!r}; values must be "
                    "identical across all entities sharing the same domain."
                )

    return errors


def _tenant_host_lint_warnings(appspec_or_fragment: object) -> list[str]:
    """Rule 7 + info-level helper output. Returns warning strings (non-blocking)."""
    warnings: list[str] = []
    entities = getattr(appspec_or_fragment, "entities", None) or getattr(
        appspec_or_fragment, "domain"
    ).entities

    by_domain: dict[str, list] = {}
    for e in entities:
        th = getattr(e, "tenant_host", None)
        if th is None:
            continue
        by_domain.setdefault(th.domain, []).append(e)

    # Helper output: print the lookup order when multi-entity-same-domain
    for domain, items in by_domain.items():
        if len(items) >= 2:
            ordered = sorted(items, key=lambda e: (e.tenant_host.order or 0))
            chain = " -> ".join(e.name for e in ordered)
            warnings.append(f"Domain {domain!r} resolution order: {chain}")

    # Rule 7: cross-domain slug collision impossible to detect statically without
    # row data — the warning fires when two domains exist and could theoretically
    # share a slug value at runtime. Emit one info note per multi-domain config.
    if len(by_domain) >= 2:
        warnings.append(
            "Multiple tenant_host domains declared "
            f"({sorted(by_domain.keys())}); slugs are not unique across domains."
        )

    return warnings
```

Wire the warnings function into whichever lint dispatcher `dazzle lint` already uses — search for an existing `lint_appspec` aggregator and append the warnings there.

Call this from the existing `validate_appspec` function. Look for an existing list-of-errors aggregator and add:

```python
errors.extend(_validate_tenant_host_blocks(appspec))
```

Make sure `FieldTypeKind` is imported at the top of `validator.py` if not already.

- [ ] **Step 4: Run the validator tests to verify pass**

Run: `pytest tests/unit/test_tenant_host_validator.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/validator.py tests/unit/test_tenant_host_validator.py
git commit -m "Validate tenant_host: hard-error rules (#1289 slice 1)"
```

---

### Task 1.5 — Stub middleware module

**Files:**
- Create: `src/dazzle/http/runtime/tenant/__init__.py`
- Create: `src/dazzle/http/runtime/tenant/middleware.py`

- [ ] **Step 1: Write the failing import test**

Append to `tests/unit/test_tenant_host_parser.py`:

```python
def test_stub_middleware_raises_not_implemented():
    from dazzle.http.runtime.tenant.middleware import TenantResolutionMiddleware
    with pytest.raises(NotImplementedError, match="slice 3"):
        TenantResolutionMiddleware(app=None)  # type: ignore[arg-type]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_tenant_host_parser.py::test_stub_middleware_raises_not_implemented -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create the package**

Create `src/dazzle/http/runtime/tenant/__init__.py` with a docstring only:

```python
"""Host-header tenant routing (#1289).

See docs/superpowers/specs/2026-05-28-tenant-host-keyword-design.md.
"""
```

Create `src/dazzle/http/runtime/tenant/middleware.py`:

```python
"""TenantResolutionMiddleware stub for #1289 slice 1.

Real implementation lands in slice 3. The stub raises NotImplementedError
at construction so any accidental mount surfaces immediately rather than
silently passing requests through.
"""
from __future__ import annotations

from typing import Any


class TenantResolutionMiddleware:  # pragma: no cover - stub
    def __init__(self, app: Any, **_kwargs: Any) -> None:
        raise NotImplementedError(
            "TenantResolutionMiddleware is not wired yet (lands in #1289 slice 3)."
        )
```

- [ ] **Step 4: Run the stub test**

Run: `pytest tests/unit/test_tenant_host_parser.py::test_stub_middleware_raises_not_implemented -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/tenant/__init__.py src/dazzle/http/runtime/tenant/middleware.py tests/unit/test_tenant_host_parser.py
git commit -m "Stub TenantResolutionMiddleware (#1289 slice 1)"
```

---

### Task 1.6 — Grammar doc + drift baselines

**Files:**
- Modify: `docs/reference/grammar.md`
- Modify: `.claude/CLAUDE.md` (the "Constructs" line near the DSL Quick Reference)
- Regen: `docs/api-surface/ir-types.txt` and `docs/api-surface/dsl-constructs.txt`

- [ ] **Step 1: Add `tenant_host` to the grammar reference**

In `docs/reference/grammar.md`, find the entity-keyword listing (search for `signable` or `temporal`). Add `tenant_host` alongside in the same block, ordered alphabetically.

In the EBNF section (search for `signable:` or `temporal:`), add an `entity_tenant_host_block` production. Use the existing pattern as a template:

```ebnf
entity_tenant_host_block = "tenant_host" ":" NEWLINE INDENT
    tenant_host_field+
    DEDENT ;

tenant_host_field =
    "domain"            ":" string  NEWLINE
  | "slug_field"        ":" IDENT   NEWLINE
  | "canonical_hosts"   ":" string_list NEWLINE
  | "cookie_scope"      ":" ("host" | "apex") NEWLINE
  | "super_admin_role"  ":" IDENT   NEWLINE
  | "history_entity"    ":" IDENT   NEWLINE
  | "not_found_template" ":" string NEWLINE
  | "expired_template"  ":" string  NEWLINE
  | "order"             ":" NUMBER  NEWLINE ;
```

- [ ] **Step 2: Update CLAUDE.md construct line**

In `.claude/CLAUDE.md`, find the line beginning `**Constructs**:` (under "DSL Quick Reference"). Add `tenant_host` alphabetically alongside the others.

- [ ] **Step 3: Regenerate drift baselines**

Run:
```bash
dazzle inspect api ir-types --write
dazzle inspect api dsl-constructs --write
```

- [ ] **Step 4: Confirm drift gates green**

Run: `pytest tests/unit/test_api_surface_drift.py tests/unit/test_docs_drift.py -q`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/reference/grammar.md .claude/CLAUDE.md docs/api-surface/ir-types.txt docs/api-surface/dsl-constructs.txt
git commit -m "Grammar + drift baselines for tenant_host: (#1289 slice 1)"
```

---

### Task 1.7 — Pre-ship gates + bump + ship slice 1

- [ ] **Step 1: Run pre-ship gates**

Run:
```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
mypy src/dazzle
pytest tests/unit/test_tenant_host_parser.py tests/unit/test_tenant_host_validator.py tests/unit/test_*_drift.py tests/unit/test_no_*.py -q
mkdocs build --strict
```

All must pass before proceeding.

- [ ] **Step 2: Bump version and ship**

Run:
```bash
/bump patch
/ship
```

- [ ] **Step 3: Confirm CI green via `/cimonitor`**

If `/cimonitor` reports a red badge, fix and re-ship as a patch bump.

---

## Slice 2 — Cache + Resolver pure-logic modules

**Purpose:** Land `TenantCache` (LRU + ttl + NEGATIVE sentinel + bust API) and `Resolver` (lookup chain across entities + history fallback) as standalone units with full unit coverage. Zero integration with the middleware yet.

**Files in this slice:**
- Create: `src/dazzle/http/runtime/tenant/cache.py`
- Create: `src/dazzle/http/runtime/tenant/resolver.py`
- Test: `tests/unit/test_tenant_cache.py`
- Test: `tests/unit/test_tenant_resolver.py`

---

### Task 2.1 — `TenantCache` LRU with NEGATIVE sentinel

**Files:**
- Create: `src/dazzle/http/runtime/tenant/cache.py`
- Test: `tests/unit/test_tenant_cache.py`

- [ ] **Step 1: Write the failing cache tests**

Create `tests/unit/test_tenant_cache.py`:

```python
"""Unit tests for TenantCache (#1289 slice 2)."""
from __future__ import annotations

import time

from dazzle.http.runtime.tenant.cache import NEGATIVE, TenantCache


def test_set_and_get_round_trip():
    cache = TenantCache(max_entries=4, ttl_seconds=60)
    cache.set("acme", {"id": 1})
    assert cache.get("acme") == {"id": 1}


def test_negative_sentinel_round_trip():
    cache = TenantCache(max_entries=4, ttl_seconds=60)
    cache.set("missing", NEGATIVE)
    assert cache.get("missing") is NEGATIVE


def test_miss_returns_none():
    cache = TenantCache(max_entries=4, ttl_seconds=60)
    assert cache.get("absent") is None


def test_ttl_expiry():
    cache = TenantCache(max_entries=4, ttl_seconds=0.05)
    cache.set("acme", {"id": 1})
    time.sleep(0.1)
    assert cache.get("acme") is None


def test_lru_eviction():
    cache = TenantCache(max_entries=2, ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")           # touch a so b is LRU
    cache.set("c", 3)        # evicts b
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3


def test_bust_removes_entry():
    cache = TenantCache(max_entries=4, ttl_seconds=60)
    cache.set("acme", {"id": 1})
    cache.bust("acme")
    assert cache.get("acme") is None


def test_bust_is_idempotent_on_missing_key():
    cache = TenantCache(max_entries=4, ttl_seconds=60)
    cache.bust("never-existed")  # must not raise
```

- [ ] **Step 2: Run the cache tests to verify they fail**

Run: `pytest tests/unit/test_tenant_cache.py -v`
Expected: import error — `TenantCache` does not exist.

- [ ] **Step 3: Implement `TenantCache`**

Create `src/dazzle/http/runtime/tenant/cache.py`:

```python
"""In-process LRU cache for tenant resolution lookups (#1289).

The cache stores positive hits (typed resolver results) and a `NEGATIVE`
sentinel that memoises cache-misses so a flood of requests for an
unknown slug doesn't trigger a flood of DB lookups.

Configurable via `max_entries` and `ttl_seconds`. Designed as a small
pure-logic unit; the resolver and middleware compose on top of it.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock
from typing import Any, Final


class _Negative:
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return "<NEGATIVE>"


NEGATIVE: Final[_Negative] = _Negative()


class TenantCache:
    """Thread-safe LRU + ttl cache for tenant resolution results."""

    def __init__(self, *, max_entries: int = 1024, ttl_seconds: float = 60.0) -> None:
        self._max = max_entries
        self._ttl = ttl_seconds
        self._lock = Lock()
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()

    def get(self, slug: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(slug)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at <= now:
                del self._store[slug]
                return None
            self._store.move_to_end(slug)  # mark recently used
            return value

    def set(self, slug: str, value: Any) -> None:
        with self._lock:
            self._store[slug] = (value, time.monotonic() + self._ttl)
            self._store.move_to_end(slug)
            while len(self._store) > self._max:
                self._store.popitem(last=False)

    def bust(self, slug: str) -> None:
        with self._lock:
            self._store.pop(slug, None)

    def clear(self) -> None:  # pragma: no cover - convenience for tests
        with self._lock:
            self._store.clear()
```

- [ ] **Step 4: Run the cache tests to verify pass**

Run: `pytest tests/unit/test_tenant_cache.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/tenant/cache.py tests/unit/test_tenant_cache.py
git commit -m "TenantCache LRU + NEGATIVE sentinel + bust API (#1289 slice 2)"
```

---

### Task 2.2 — `Resolver` result types

**Files:**
- Create: `src/dazzle/http/runtime/tenant/resolver.py`
- Test: `tests/unit/test_tenant_resolver.py`

- [ ] **Step 1: Write the failing resolver-type tests**

Create `tests/unit/test_tenant_resolver.py`:

```python
"""Unit tests for tenant Resolver (#1289 slice 2)."""
from __future__ import annotations

from uuid import uuid4

import pytest

from dazzle.http.runtime.tenant.resolver import (
    ExpiredHistoryHit,
    HistoryHit,
    Resolver,
    ResolvedTenant,
)


def test_resolved_tenant_is_frozen():
    rt = ResolvedTenant(kind="Trust", id=uuid4(), slug="acme", name="Acme")
    with pytest.raises(Exception):
        rt.slug = "other"  # type: ignore[misc]


def test_history_hit_carries_old_and_new_slugs():
    h = HistoryHit(old_slug="acme", new_slug="acme-corp")
    assert h.old_slug == "acme"
    assert h.new_slug == "acme-corp"


def test_expired_history_hit_distinct_type():
    e = ExpiredHistoryHit(old_slug="acme", new_slug="acme-corp")
    assert not isinstance(e, HistoryHit)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_tenant_resolver.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement result dataclasses**

Create `src/dazzle/http/runtime/tenant/resolver.py`:

```python
"""Tenant lookup chain (#1289 slice 2).

`Resolver.lookup(slug)` walks the configured tenant_host entities in
lexical (or `order:`) sequence, returning the first match. If no entity
matches and a history_entity is configured, the resolver falls back to
the history table to produce a 301 (active) or 410 (expired) signal.

The actual DB calls are delegated via a `lookup_fn` callable so this
module stays a pure-logic unit testable without database fixtures.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class ResolvedTenant:
    kind: str                # entity name (e.g. "Trust")
    id: UUID
    slug: str
    name: str | None = None


@dataclass(frozen=True)
class HistoryHit:
    old_slug: str
    new_slug: str


@dataclass(frozen=True)
class ExpiredHistoryHit:
    old_slug: str
    new_slug: str


@dataclass(frozen=True)
class EntityProbe:
    """One step of the resolution chain — `(entity_name, slug_field)`."""

    entity_name: str
    slug_field: str


@dataclass(frozen=True)
class HistoryProbe:
    """Optional history-table probe — `(entity_name, old/new/expires fields)`."""

    entity_name: str
    old_slug_field: str = "old_slug"
    new_slug_field: str = "new_slug"
    expires_field: str = "expires_at"


LookupFn = Callable[[str, str], dict | None]
"""Signature: lookup_fn(entity_name, slug) -> row dict or None."""


HistoryLookupFn = Callable[[str, str], dict | None]
"""Signature: history_lookup_fn(entity_name, old_slug) -> row dict or None."""


class Resolver:
    """Stateless lookup chain over configured entity probes."""

    def __init__(
        self,
        probes: list[EntityProbe],
        history_probe: HistoryProbe | None,
        lookup_fn: LookupFn,
        history_lookup_fn: HistoryLookupFn | None = None,
        *,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._probes = probes
        self._history = history_probe
        self._lookup = lookup_fn
        self._history_lookup = history_lookup_fn
        self._now = now_fn

    def lookup(
        self, slug: str
    ) -> ResolvedTenant | HistoryHit | ExpiredHistoryHit | None:
        for probe in self._probes:
            row = self._lookup(probe.entity_name, slug)
            if row is None:
                continue
            return ResolvedTenant(
                kind=probe.entity_name,
                id=row["id"],
                slug=row[probe.slug_field],
                name=row.get("name"),
            )

        if self._history is None or self._history_lookup is None:
            return None

        h = self._history_lookup(self._history.entity_name, slug)
        if h is None:
            return None

        new_slug = h[self._history.new_slug_field]
        expires = h[self._history.expires_field]
        if isinstance(expires, str):
            expires = datetime.fromisoformat(expires)
        if expires > self._now():
            return HistoryHit(old_slug=slug, new_slug=new_slug)
        return ExpiredHistoryHit(old_slug=slug, new_slug=new_slug)
```

- [ ] **Step 4: Run the resolver-type tests**

Run: `pytest tests/unit/test_tenant_resolver.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/tenant/resolver.py tests/unit/test_tenant_resolver.py
git commit -m "Resolver result dataclasses (#1289 slice 2)"
```

---

### Task 2.3 — Resolver lookup chain tests

**Files:**
- Modify: `tests/unit/test_tenant_resolver.py`

- [ ] **Step 1: Add lookup-chain tests**

Append to `tests/unit/test_tenant_resolver.py`:

```python
from datetime import datetime, timedelta, timezone

from dazzle.http.runtime.tenant.resolver import (
    EntityProbe,
    HistoryProbe,
    Resolver,
)


def _id(n: int) -> UUID:
    return UUID(int=n)


def test_lookup_returns_first_matching_entity():
    rows = {("Trust", "acme"): {"id": _id(1), "slug": "acme", "name": "Acme"}}
    r = Resolver(
        probes=[EntityProbe("Trust", "slug"), EntityProbe("School", "slug")],
        history_probe=None,
        lookup_fn=lambda e, s: rows.get((e, s)),
    )
    res = r.lookup("acme")
    assert isinstance(res, ResolvedTenant)
    assert res.kind == "Trust"
    assert res.id == _id(1)


def test_lookup_falls_through_to_second_entity():
    rows = {("School", "westwood"): {"id": _id(2), "slug": "westwood", "name": "Westwood"}}
    r = Resolver(
        probes=[EntityProbe("Trust", "slug"), EntityProbe("School", "slug")],
        history_probe=None,
        lookup_fn=lambda e, s: rows.get((e, s)),
    )
    res = r.lookup("westwood")
    assert isinstance(res, ResolvedTenant)
    assert res.kind == "School"


def test_lookup_returns_none_when_no_match_and_no_history():
    r = Resolver(
        probes=[EntityProbe("Trust", "slug")],
        history_probe=None,
        lookup_fn=lambda e, s: None,
    )
    assert r.lookup("missing") is None


def test_lookup_returns_history_hit_when_unexpired():
    future = datetime.now(timezone.utc) + timedelta(days=30)
    r = Resolver(
        probes=[EntityProbe("Trust", "slug")],
        history_probe=HistoryProbe("TrustHistory"),
        lookup_fn=lambda e, s: None,
        history_lookup_fn=lambda e, s: {
            "old_slug": "acme", "new_slug": "acme-corp", "expires_at": future,
        },
    )
    res = r.lookup("acme")
    assert isinstance(res, HistoryHit)
    assert res.new_slug == "acme-corp"


def test_lookup_returns_expired_history_hit_when_past_ttl():
    past = datetime.now(timezone.utc) - timedelta(days=1)
    r = Resolver(
        probes=[EntityProbe("Trust", "slug")],
        history_probe=HistoryProbe("TrustHistory"),
        lookup_fn=lambda e, s: None,
        history_lookup_fn=lambda e, s: {
            "old_slug": "acme", "new_slug": "acme-corp", "expires_at": past,
        },
    )
    res = r.lookup("acme")
    assert isinstance(res, ExpiredHistoryHit)
```

- [ ] **Step 2: Run the chain tests**

Run: `pytest tests/unit/test_tenant_resolver.py -v`
Expected: all 8 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_tenant_resolver.py
git commit -m "Resolver lookup-chain tests (#1289 slice 2)"
```

---

### Task 2.4 — Pre-ship gates + bump + ship slice 2

- [ ] **Step 1: Run pre-ship gates**

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
mypy src/dazzle
pytest tests/unit/test_tenant_*.py tests/unit/test_*_drift.py tests/unit/test_no_*.py -q
mkdocs build --strict
```

- [ ] **Step 2: Bump + ship**

```bash
/bump patch
/ship
```

- [ ] **Step 3: Confirm CI green via `/cimonitor`**

---

## Slice 3 — Middleware + app_factory auto-mount + framework default templates

**Purpose:** Replace the stub `TenantResolutionMiddleware` with the real impl. Wire app_factory to mount it whenever any entity carries `tenant_host:`. Ship framework default 404 / 410 pages so apps without project overrides still get sensible UX.

**Files:**
- Modify: `src/dazzle/http/runtime/tenant/middleware.py` (replace stub with full impl)
- Create: `src/dazzle/http/runtime/tenant/templates.py` (framework defaults)
- Modify: `src/dazzle/http/runtime/app_factory.py` (conditional auto-mount)
- Test: `tests/unit/test_tenant_middleware.py`

---

### Task 3.1 — Framework default templates

**Files:**
- Create: `src/dazzle/http/runtime/tenant/templates.py`
- Test: `tests/unit/test_tenant_middleware.py` (new file)

- [ ] **Step 1: Write the failing template tests**

Create `tests/unit/test_tenant_middleware.py`:

```python
"""Tests for the tenant middleware + default templates (#1289 slice 3)."""
from __future__ import annotations

from dazzle.http.runtime.tenant.templates import render_default_404, render_default_410


def test_default_404_includes_host():
    body = render_default_404(app_name="acme", host="missing.acme.com")
    assert "missing.acme.com" in body
    assert "404" in body or "not found" in body.lower()


def test_default_410_includes_new_slug():
    body = render_default_410(
        app_name="acme", old_slug="oldco", new_slug="newco", domain="acme.com"
    )
    assert "newco" in body
    assert "oldco" in body
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_tenant_middleware.py -v`
Expected: import error.

- [ ] **Step 3: Implement default templates**

Create `src/dazzle/http/runtime/tenant/templates.py`:

```python
"""Framework default 404 / 410 pages for tenant_host: (#1289 slice 3).

Projects override per-block via the dotted-path `not_found_template:` and
`expired_template:` sub-fields. These defaults exist so the framework
always ships a sensible response without per-project work.
"""
from __future__ import annotations

from html import escape


def render_default_404(*, app_name: str, host: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{escape(app_name)} — Not Found</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:40rem;margin:4rem auto;padding:0 1rem;color:#222}h1{font-size:1.5rem}</style>"
        "</head><body>"
        f"<h1>{escape(app_name)} — Tenant not found</h1>"
        f"<p>No tenant matches <code>{escape(host)}</code>.</p>"
        "<p>Status: 404</p>"
        "</body></html>"
    )


def render_default_410(*, app_name: str, old_slug: str, new_slug: str, domain: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{escape(app_name)} — Moved</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:40rem;margin:4rem auto;padding:0 1rem;color:#222}h1{font-size:1.5rem}</style>"
        "</head><body>"
        f"<h1>{escape(app_name)} — Tenant moved</h1>"
        f"<p><code>{escape(old_slug)}</code> moved to "
        f"<a href='https://{escape(new_slug)}.{escape(domain)}/'>"
        f"<code>{escape(new_slug)}.{escape(domain)}</code></a>.</p>"
        "<p>This redirect link has expired (status: 410).</p>"
        "</body></html>"
    )
```

- [ ] **Step 4: Run the template tests**

Run: `pytest tests/unit/test_tenant_middleware.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/tenant/templates.py tests/unit/test_tenant_middleware.py
git commit -m "Framework default 404/410 templates for tenant_host (#1289 slice 3)"
```

---

### Task 3.2 — Real `TenantResolutionMiddleware`

**Files:**
- Modify: `src/dazzle/http/runtime/tenant/middleware.py` (replace stub)
- Modify: `tests/unit/test_tenant_middleware.py`

- [ ] **Step 1: Write the failing middleware tests**

Append to `tests/unit/test_tenant_middleware.py`:

```python
import importlib
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from dazzle.http.runtime.tenant.cache import TenantCache
from dazzle.http.runtime.tenant.middleware import (
    TenantHostBinding,
    TenantResolutionMiddleware,
)
from dazzle.http.runtime.tenant.resolver import (
    EntityProbe,
    Resolver,
    ResolvedTenant,
)


def _app_with_binding(binding: TenantHostBinding) -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(request: Request) -> dict:
        tenant = getattr(request.state, "tenant", None)
        return {"tenant": None if tenant is None else tenant.slug}

    app.add_middleware(TenantResolutionMiddleware, binding=binding)
    return app


def _binding(
    rows: dict[tuple[str, str], dict],
    *,
    canonical: list[str] | None = None,
    history_rows: dict[tuple[str, str], dict] | None = None,
) -> TenantHostBinding:
    cache = TenantCache(max_entries=64, ttl_seconds=60)
    resolver = Resolver(
        probes=[EntityProbe("Trust", "slug")],
        history_probe=None,
        lookup_fn=lambda e, s: rows.get((e, s)),
    )
    return TenantHostBinding(
        app_name="testapp",
        domain="example.com",
        canonical_hosts=tuple(canonical or []),
        cache=cache,
        resolver=resolver,
        not_found_renderer=lambda host: f"<p>404 {host}</p>",
        expired_renderer=lambda old, new, domain: f"<p>410 {old} -> {new}</p>",
    )


def test_canonical_host_passes_through_with_no_tenant():
    binding = _binding({}, canonical=["www.example.com"])
    client = TestClient(_app_with_binding(binding))
    resp = client.get("/whoami", headers={"host": "www.example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"tenant": None}


def test_tenant_subdomain_resolves():
    rows = {("Trust", "acme"): {"id": uuid4(), "slug": "acme", "name": "Acme"}}
    binding = _binding(rows)
    client = TestClient(_app_with_binding(binding))
    resp = client.get("/whoami", headers={"host": "acme.example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"tenant": "acme"}


def test_unknown_slug_returns_404_with_default_renderer():
    binding = _binding({})
    client = TestClient(_app_with_binding(binding))
    resp = client.get("/whoami", headers={"host": "nope.example.com"})
    assert resp.status_code == 404
    assert "404" in resp.text


def test_host_outside_domain_returns_400():
    binding = _binding({})
    client = TestClient(_app_with_binding(binding))
    resp = client.get("/whoami", headers={"host": "other-site.org"})
    assert resp.status_code == 400


def test_negative_cache_short_circuits_second_request():
    calls: list[str] = []

    def counting_lookup(entity: str, slug: str) -> dict | None:
        calls.append(slug)
        return None

    cache = TenantCache(max_entries=64, ttl_seconds=60)
    resolver = Resolver(
        probes=[EntityProbe("Trust", "slug")],
        history_probe=None,
        lookup_fn=counting_lookup,
    )
    binding = TenantHostBinding(
        app_name="testapp",
        domain="example.com",
        canonical_hosts=(),
        cache=cache,
        resolver=resolver,
        not_found_renderer=lambda host: "<p>404</p>",
        expired_renderer=lambda old, new, domain: "<p>410</p>",
    )
    client = TestClient(_app_with_binding(binding))
    client.get("/whoami", headers={"host": "ghost.example.com"})
    client.get("/whoami", headers={"host": "ghost.example.com"})
    assert calls == ["ghost"]  # second request hit the NEGATIVE cache entry
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_tenant_middleware.py -v`
Expected: import error or NotImplementedError from the stub.

- [ ] **Step 3: Implement the real middleware**

Replace `src/dazzle/http/runtime/tenant/middleware.py` entirely:

```python
"""TenantResolutionMiddleware (#1289 slice 3).

Resolves the Host header to a tenant before any downstream route or
auth dependency runs. See the design spec for the full lifecycle.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.types import ASGIApp

from dazzle.http.runtime.slug_validator import validate_slug
from dazzle.http.runtime.tenant.cache import NEGATIVE, TenantCache
from dazzle.http.runtime.tenant.resolver import (
    ExpiredHistoryHit,
    HistoryHit,
    ResolvedTenant,
    Resolver,
)

logger = logging.getLogger("dazzle.tenant")


NotFoundRenderer = Callable[[str], str]
ExpiredRenderer = Callable[[str, str, str], str]


@dataclass(frozen=True)
class TenantHostBinding:
    """Per-domain configuration for the resolution middleware."""

    app_name: str
    domain: str
    canonical_hosts: tuple[str, ...]
    cache: TenantCache
    resolver: Resolver
    not_found_renderer: NotFoundRenderer
    expired_renderer: ExpiredRenderer


class TenantResolutionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, binding: TenantHostBinding) -> None:
        super().__init__(app)
        self._b = binding

    async def dispatch(self, request: Request, call_next):
        host = (request.headers.get("host") or "").split(":")[0].lower()

        if host in self._b.canonical_hosts:
            request.state.tenant = None
            return await call_next(request)

        suffix = "." + self._b.domain
        if not host.endswith(suffix):
            return Response("Bad Host", status_code=400)

        slug = host[: -len(suffix)]
        try:
            validate_slug(slug)
        except ValueError:
            return HTMLResponse(self._b.not_found_renderer(host), status_code=404)

        cached = self._b.cache.get(slug)
        if cached is NEGATIVE:
            return HTMLResponse(self._b.not_found_renderer(host), status_code=404)

        result = cached
        if result is None:
            try:
                result = self._b.resolver.lookup(slug)
            except Exception:
                logger.exception("tenant resolver lookup failed for %s", slug)
                return Response("Tenant lookup failed", status_code=502)
            self._b.cache.set(slug, result if result is not None else NEGATIVE)

        if result is None:
            return HTMLResponse(self._b.not_found_renderer(host), status_code=404)

        if isinstance(result, HistoryHit):
            target = f"https://{result.new_slug}.{self._b.domain}/"
            return RedirectResponse(target, status_code=301)

        if isinstance(result, ExpiredHistoryHit):
            body = self._b.expired_renderer(result.old_slug, result.new_slug, self._b.domain)
            return HTMLResponse(body, status_code=410)

        assert isinstance(result, ResolvedTenant)
        request.state.tenant = result
        return await call_next(request)
```

- [ ] **Step 4: Run the middleware tests**

Run: `pytest tests/unit/test_tenant_middleware.py -v`
Expected: all 5 PASS (plus the 2 from Task 3.1).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/tenant/middleware.py tests/unit/test_tenant_middleware.py
git commit -m "TenantResolutionMiddleware real implementation (#1289 slice 3)"
```

---

### Task 3.3 — App factory auto-mount

**Files:**
- Modify: `src/dazzle/http/runtime/app_factory.py`

- [ ] **Step 1: Write the failing auto-mount test**

Append to `tests/unit/test_tenant_middleware.py`:

```python
def test_app_factory_auto_mounts_when_tenant_host_present(monkeypatch, tmp_path):
    """When any entity declares tenant_host:, app_factory mounts the middleware.

    Uses a minimal in-memory AppSpec rather than parsing DSL — the parser
    side is covered in slice 1.
    """
    from dazzle.core.ir import AppSpec  # noqa: F401 (imported for fixture pattern docs)

    pytest.skip(
        "Auto-mount integration test requires the app_factory.build_app() "
        "test fixture; pin to follow-up if not already in place. "
        "Slice 3 ships the wiring; full end-to-end mount lives with the"
        " builder fixture next to test_app_factory.py."
    )
```

Note: this skip is intentional — the auto-mount wiring is exercised end-to-end in the integration test we add in Task 3.4 once we know whether `app_factory.build_app()` has a callable test fixture.

- [ ] **Step 2: Wire the auto-mount**

In `src/dazzle/http/runtime/app_factory.py`, after `assemble_post_build_routes(...)` and the `_invoke_project_post_build_hook(app)` line added in #1290 (slice landed in v0.80.10), add:

```python
    _mount_tenant_resolution_middleware(app, appspec)
```

Then append a new helper to the same file (place near `_invoke_project_post_build_hook`):

```python
def _mount_tenant_resolution_middleware(app: "FastAPI", appspec: AppSpec) -> None:
    """#1289 slice 3: mount TenantResolutionMiddleware iff any entity has tenant_host:."""
    tenant_entities = [
        e for e in appspec.domain.entities if getattr(e, "tenant_host", None) is not None
    ]
    if not tenant_entities:
        return

    # Group by domain so one middleware can serve all entities sharing a base host.
    from collections import defaultdict

    by_domain: dict[str, list] = defaultdict(list)
    for e in tenant_entities:
        by_domain[e.tenant_host.domain].append(e)

    from dazzle.http.runtime.tenant.cache import TenantCache
    from dazzle.http.runtime.tenant.middleware import (
        TenantHostBinding,
        TenantResolutionMiddleware,
    )
    from dazzle.http.runtime.tenant.resolver import (
        EntityProbe,
        HistoryProbe,
        Resolver,
    )
    from dazzle.http.runtime.tenant.templates import (
        render_default_404,
        render_default_410,
    )

    for domain, entities in by_domain.items():
        ordered = sorted(entities, key=lambda e: (e.tenant_host.order or 0))
        probes = [EntityProbe(e.name, e.tenant_host.slug_field) for e in ordered]
        history_probe = None
        if ordered[0].tenant_host.history_entity:
            history_probe = HistoryProbe(ordered[0].tenant_host.history_entity)
        canonical = ordered[0].tenant_host.canonical_hosts

        binding = TenantHostBinding(
            app_name=appspec.name,
            domain=domain,
            canonical_hosts=tuple(canonical),
            cache=TenantCache(),
            resolver=Resolver(
                probes=probes,
                history_probe=history_probe,
                lookup_fn=_make_system_lookup_fn(app),
                history_lookup_fn=(
                    _make_system_history_lookup_fn(app) if history_probe else None
                ),
            ),
            not_found_renderer=_resolve_template_or_default(
                ordered[0].tenant_host.not_found_template,
                default=lambda host: render_default_404(app_name=appspec.name, host=host),
            ),
            expired_renderer=_resolve_template_or_default(
                ordered[0].tenant_host.expired_template,
                default=lambda old, new, dom: render_default_410(
                    app_name=appspec.name, old_slug=old, new_slug=new, domain=dom
                ),
            ),
        )
        app.add_middleware(TenantResolutionMiddleware, binding=binding)
```

Add stub helpers in the same file (or pull them into a `_tenant_wiring.py` module if app_factory grows beyond 1500 lines):

```python
def _resolve_template_or_default(dotted: str | None, default):
    if dotted is None:
        return default
    import importlib

    module_name, _, attr = dotted.partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def _make_system_lookup_fn(app: "FastAPI"):
    """Return a callable (entity_name, slug) -> row dict | None using the
    framework's system-context Repository. The exact wiring depends on
    the existing Repository's system-context API; see Task 3.4."""
    async def _lookup(entity_name: str, slug: str):
        raise NotImplementedError("Wired in Task 3.4")
    return _lookup


def _make_system_history_lookup_fn(app: "FastAPI"):
    async def _lookup(entity_name: str, slug: str):
        raise NotImplementedError("Wired in Task 3.4")
    return _lookup
```

- [ ] **Step 3: Run only the previously passing middleware tests to confirm no regression**

Run: `pytest tests/unit/test_tenant_middleware.py -v --deselect tests/unit/test_tenant_middleware.py::test_app_factory_auto_mounts_when_tenant_host_present`
Expected: 6 PASS, 1 SKIPPED.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/http/runtime/app_factory.py tests/unit/test_tenant_middleware.py
git commit -m "app_factory: auto-mount TenantResolutionMiddleware (#1289 slice 3)"
```

---

### Task 3.4 — System-context Repository lookup

**Files:**
- Modify: `src/dazzle/http/runtime/app_factory.py` (replace `_make_system_lookup_fn` stubs with real impl)
- Test: `tests/integration/test_tenant_host_end_to_end.py` (new file)

- [ ] **Step 1: Inspect the existing Repository to find system-context API**

Run: `grep -n "system_context\|admin_context\|unscoped\|class Repository" src/dazzle/http/runtime/repository.py | head -20`

Note the existing pattern — Dazzle's Repository is normally tenant-scoped. The middleware runs before tenancy is known, so we need an unscoped (system) read path. The exact method/flag name varies; the implementer should adopt whatever the codebase already exposes (e.g. `Repository.system_context()` or constructing a fresh `Repository(session, scope=SystemScope())`). If no such API exists, add a `Repository.find_by_slug_system(entity_name, slug)` thin helper that bypasses tenant scoping but otherwise routes through the same query path.

- [ ] **Step 2: Write the failing integration test**

Create `tests/integration/test_tenant_host_end_to_end.py`:

```python
"""End-to-end tenant_host: integration test (#1289 slice 3).

Spins up a minimal AppSpec with one tenant_host entity, builds the app
via the framework's app_factory, seeds a Trust row, and asserts that
Host-header-based requests resolve correctly.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# Match the gate used by other PostgreSQL-touching tests in the suite.
pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping PostgreSQL integration test",
)


def test_tenant_host_resolves_via_postgresql(database_url, seeded_trust_factory):
    """A request to <slug>.<domain> resolves to the seeded Trust row."""
    # The exact builder API depends on the project's existing integration
    # harness — pattern-match on tests/integration/test_*.py for the
    # closest neighbour (e.g. the auth-routes integration tests) and reuse
    # its app-build fixture.
    pytest.fail(
        "Implementer: wire this test to the existing integration harness — "
        "build a minimal AppSpec with one tenant_host entity, seed a Trust "
        "row via seeded_trust_factory, then assert TestClient.get('/some/route', "
        "headers={'host': 'acme.example.com'}) responds 200 and surfaces "
        "request.state.tenant.slug == 'acme'."
    )
```

- [ ] **Step 3: Implement system lookup against Repository**

In `src/dazzle/http/runtime/app_factory.py`, replace the two `NotImplementedError` stubs from Task 3.3 with the actual Repository lookup, using whatever system-context API the codebase exposes after Step 1's inspection. Example shape (adapt to actual API):

```python
def _make_system_lookup_fn(app: "FastAPI"):
    async def _lookup(entity_name: str, slug: str):
        from dazzle.http.runtime.repository import system_repository_for
        repo = system_repository_for(app, entity_name)
        return await repo.find_one_by(slug_field=slug)  # or whichever method exists
    return _lookup
```

If `system_repository_for` doesn't exist, add it as the smallest possible new function in `repository.py` that returns a Repository instance bound to an unscoped session. Keep the surface minimal.

- [ ] **Step 4: Implement the integration test**

Replace the `pytest.fail(...)` body in `tests/integration/test_tenant_host_end_to_end.py` with a concrete test using the integration harness identified in Step 1 of this task. Pattern: seed a row, build app via the factory, hit it via TestClient with a `host:` header, assert 200 + tenant on `request.state`.

- [ ] **Step 5: Run the integration test (locally, with DATABASE_URL set)**

Run: `DATABASE_URL=<dev-pg-url> pytest tests/integration/test_tenant_host_end_to_end.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/http/runtime/app_factory.py src/dazzle/http/runtime/repository.py tests/integration/test_tenant_host_end_to_end.py
git commit -m "System-context Repository lookup + end-to-end integration (#1289 slice 3)"
```

---

### Task 3.5 — Pre-ship gates + bump + ship slice 3

- [ ] **Step 1: Run pre-ship gates**

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
mypy src/dazzle
pytest tests/unit/test_tenant_*.py tests/unit/test_*_drift.py tests/unit/test_no_*.py -q
mkdocs build --strict
```

- [ ] **Step 2: Bump + ship**

```bash
/bump patch
/ship
```

- [ ] **Step 3: Confirm CI green via `/cimonitor`**

---

## Slice 4 — Cookie name switch + login-flow wiring

**Purpose:** Switch the session cookie naming convention from `dazzle_session` to `__Host-<app>_session` (for tenant-bound requests) and `__Secure-<app>_admin` (for canonical-host super-admin sessions) — but only for apps that use `tenant_host:`. Non-tenant_host apps keep `dazzle_session` unchanged.

**Files:**
- Create: `src/dazzle/http/runtime/tenant/cookies.py`
- Modify: `src/dazzle/http/runtime/auth/password_login_routes.py`
- Modify: `src/dazzle/http/runtime/auth/sso_routes.py`
- Modify: `src/dazzle/http/runtime/auth/routes_2fa.py`
- Modify: `src/dazzle/http/runtime/app_factory.py` (pass tenant-cookie naming through to auth wiring)
- Test: `tests/unit/test_tenant_cookies.py`

---

### Task 4.1 — `cookies.py` name helpers

**Files:**
- Create: `src/dazzle/http/runtime/tenant/cookies.py`
- Test: `tests/unit/test_tenant_cookies.py`

- [ ] **Step 1: Write the failing cookie-name tests**

Create `tests/unit/test_tenant_cookies.py`:

```python
"""Tests for tenant cookie helpers (#1289 slice 4)."""
from __future__ import annotations

import pytest

from dazzle.http.runtime.tenant.cookies import (
    apex_cookie_name,
    host_cookie_name,
    normalise_app_name,
)


def test_normalise_app_name_lowercase_and_underscores():
    assert normalise_app_name("AegisMark-Prod") == "aegismark_prod"
    assert normalise_app_name("acme") == "acme"
    assert normalise_app_name("a.b.c") == "a_b_c"


def test_host_cookie_name_uses_prefix_and_normalised_app():
    assert host_cookie_name("Acme-App") == "__Host-acme_app_session"


def test_apex_cookie_name_uses_secure_prefix():
    assert apex_cookie_name("Acme-App") == "__Secure-acme_app_admin"


@pytest.mark.parametrize("name", ["", "   ", "!@#$"])
def test_normalise_rejects_empty_or_non_alnum_only(name):
    with pytest.raises(ValueError):
        normalise_app_name(name)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_tenant_cookies.py -v`
Expected: import error.

- [ ] **Step 3: Implement the helpers**

Create `src/dazzle/http/runtime/tenant/cookies.py`:

```python
"""Cookie name conventions for tenant_host: apps (#1289 slice 4)."""
from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalise_app_name(name: str) -> str:
    """Lowercase, then collapse any non-[a-z0-9] run to a single underscore.

    Trailing/leading underscores are stripped so the resulting token is a
    valid cookie-name-fragment per RFC 6265 token rules.
    """
    lowered = name.lower()
    collapsed = _NON_ALNUM.sub("_", lowered).strip("_")
    if not collapsed:
        raise ValueError(f"app name {name!r} produces an empty normalised token")
    return collapsed


def host_cookie_name(app_name: str) -> str:
    return f"__Host-{normalise_app_name(app_name)}_session"


def apex_cookie_name(app_name: str) -> str:
    return f"__Secure-{normalise_app_name(app_name)}_admin"
```

- [ ] **Step 4: Run the cookie tests**

Run: `pytest tests/unit/test_tenant_cookies.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/tenant/cookies.py tests/unit/test_tenant_cookies.py
git commit -m "Tenant cookie name helpers (#1289 slice 4)"
```

---

### Task 4.2 — Thread cookie-name choice into login flow

**Files:**
- Modify: `src/dazzle/http/runtime/auth/password_login_routes.py`
- Modify: `src/dazzle/http/runtime/auth/sso_routes.py`
- Modify: `src/dazzle/http/runtime/auth/routes_2fa.py`
- Modify: `src/dazzle/http/runtime/app_factory.py`

- [ ] **Step 1: Inspect existing cookie injection points**

Run: `grep -n "set_cookie\|cookie_name" src/dazzle/http/runtime/auth/*.py`

Note every site that sets the session cookie. They share a `cookie_name: str = "dazzle_session"` argument. We need each such site to take a `cookie_name_resolver(request)` callable instead of a hard-coded string when tenant_host is in play.

- [ ] **Step 2: Write the failing cookie-selection test**

Append to `tests/unit/test_tenant_cookies.py`:

```python
from dazzle.http.runtime.tenant.cookies import choose_session_cookie_name


def test_choose_session_cookie_falls_to_host_when_tenant_present():
    """Authenticated user on a tenant subdomain gets the __Host- cookie."""
    name = choose_session_cookie_name(
        app_name="acme",
        is_canonical_host=False,
        user_role="member",
        super_admin_role="super_admin",
    )
    assert name == "__Host-acme_session"


def test_choose_session_cookie_uses_apex_when_canonical_and_super_admin():
    name = choose_session_cookie_name(
        app_name="acme",
        is_canonical_host=True,
        user_role="super_admin",
        super_admin_role="super_admin",
    )
    assert name == "__Secure-acme_admin"


def test_choose_session_cookie_falls_back_to_host_for_non_admin_on_canonical():
    name = choose_session_cookie_name(
        app_name="acme",
        is_canonical_host=True,
        user_role="member",
        super_admin_role="super_admin",
    )
    assert name == "__Host-acme_session"
```

- [ ] **Step 3: Add `choose_session_cookie_name` to `cookies.py`**

Append to `src/dazzle/http/runtime/tenant/cookies.py`:

```python
def choose_session_cookie_name(
    *,
    app_name: str,
    is_canonical_host: bool,
    user_role: str,
    super_admin_role: str,
) -> str:
    """Login-flow decision tree (spec §Cookie wiring)."""
    if is_canonical_host and user_role == super_admin_role:
        return apex_cookie_name(app_name)
    return host_cookie_name(app_name)
```

- [ ] **Step 4: Run the cookie tests**

Run: `pytest tests/unit/test_tenant_cookies.py -v`
Expected: 6 PASS total.

- [ ] **Step 5: Thread the resolver into the auth routes**

In `src/dazzle/http/runtime/auth/password_login_routes.py`, `sso_routes.py`, and `routes_2fa.py`, locate every `set_cookie(...)` and every place a `cookie_name` is read. Add a `cookie_name_for_request(request, user)` argument to each `create_*_routes` factory function and use it instead of the bare `cookie_name`. The resolver is constructed in `app_factory.py` from the AppSpec.

In `app_factory.py`, add a helper that returns the right resolver:

```python
def _build_session_cookie_resolver(appspec: AppSpec):
    tenant_entities = [
        e for e in appspec.domain.entities if getattr(e, "tenant_host", None) is not None
    ]
    if not tenant_entities:
        # Legacy apps keep dazzle_session unchanged.
        return lambda request, user: "dazzle_session"

    from dazzle.http.runtime.tenant.cookies import choose_session_cookie_name

    canonical_hosts: set[str] = set()
    super_admin_role = "super_admin"
    for e in tenant_entities:
        canonical_hosts.update(e.tenant_host.canonical_hosts)
        super_admin_role = e.tenant_host.super_admin_role

    def _resolver(request, user) -> str:
        host = (request.headers.get("host") or "").split(":")[0].lower()
        is_canonical = host in canonical_hosts
        role = getattr(user, "role", "") or ""
        return choose_session_cookie_name(
            app_name=appspec.name,
            is_canonical_host=is_canonical,
            user_role=role,
            super_admin_role=super_admin_role,
        )

    return _resolver
```

Pass `cookie_name_for_request=_build_session_cookie_resolver(appspec)` to each auth route factory at construction time.

- [ ] **Step 6: Run all auth-route tests**

Run: `pytest tests/unit/test_password_login_routes.py tests/unit/test_sso_routes.py tests/unit/test_routes_2fa.py tests/unit/test_tenant_cookies.py -q`
Expected: PASS. If any existing test breaks because of the new resolver signature, update its call site to pass a `lambda request, user: "dazzle_session"` stub.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/http/runtime/tenant/cookies.py src/dazzle/http/runtime/auth/*.py src/dazzle/http/runtime/app_factory.py tests/unit/test_tenant_cookies.py
git commit -m "Login-flow cookie name resolver for tenant_host apps (#1289 slice 4)"
```

---

### Task 4.3 — Pre-ship gates + bump + ship slice 4

- [ ] **Step 1: Pre-ship gates**

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
mypy src/dazzle
pytest tests/unit/test_tenant_*.py tests/unit/test_*auth* tests/unit/test_*_drift.py tests/unit/test_no_*.py -q
mkdocs build --strict
```

- [ ] **Step 2: Bump + ship**

```bash
/bump patch
/ship
```

- [ ] **Step 3: Confirm CI green via `/cimonitor`**

---

## Slice 5 — Cross-tenant guard + auth dependency

**Purpose:** Enforce the truth table from the spec so a tenant-bound cookie can't be reused on a different tenant's host, and an apex super-admin cookie can't be presented on a tenant host without the super-admin role.

**Files:**
- Create: `src/dazzle/http/runtime/tenant/guard.py`
- Modify: `src/dazzle/http/runtime/auth/dependencies.py` (or whichever module holds the existing `current_user` dependency)
- Test: `tests/unit/test_tenant_guard.py`

---

### Task 5.1 — Implement the truth table

**Files:**
- Create: `src/dazzle/http/runtime/tenant/guard.py`
- Test: `tests/unit/test_tenant_guard.py`

- [ ] **Step 1: Write the failing guard tests**

Create `tests/unit/test_tenant_guard.py`:

```python
"""Cross-tenant guard tests (#1289 slice 5)."""
from __future__ import annotations

from uuid import uuid4

import pytest

from dazzle.http.runtime.tenant.guard import (
    ApexCookieNotSuperAdmin,
    CrossTenantForbidden,
    GuardOutcome,
    HostCookieMissingTenant,
    check_cross_tenant,
)
from dazzle.http.runtime.tenant.resolver import ResolvedTenant


def _tenant(slug="acme"):
    return ResolvedTenant(kind="Trust", id=uuid4(), slug=slug, name=slug.title())


def test_host_cookie_matching_tenant_passes():
    out = check_cross_tenant(
        cookie_kind="host", session_tenant_slug="acme", request_tenant=_tenant("acme"),
        user_role="member", super_admin_role="super_admin",
    )
    assert out is GuardOutcome.PASS


def test_host_cookie_mismatched_tenant_raises():
    with pytest.raises(CrossTenantForbidden):
        check_cross_tenant(
            cookie_kind="host", session_tenant_slug="acme", request_tenant=_tenant("other"),
            user_role="member", super_admin_role="super_admin",
        )


def test_host_cookie_on_apex_raises():
    with pytest.raises(HostCookieMissingTenant):
        check_cross_tenant(
            cookie_kind="host", session_tenant_slug="acme", request_tenant=None,
            user_role="member", super_admin_role="super_admin",
        )


def test_apex_cookie_with_super_admin_passes_for_any_tenant():
    out = check_cross_tenant(
        cookie_kind="apex", session_tenant_slug=None, request_tenant=_tenant("acme"),
        user_role="super_admin", super_admin_role="super_admin",
    )
    assert out is GuardOutcome.PASS


def test_apex_cookie_without_super_admin_raises():
    with pytest.raises(ApexCookieNotSuperAdmin):
        check_cross_tenant(
            cookie_kind="apex", session_tenant_slug=None, request_tenant=_tenant("acme"),
            user_role="member", super_admin_role="super_admin",
        )


def test_no_cookie_present_passes_through():
    """Unauthenticated requests don't trip the guard; auth itself decides."""
    out = check_cross_tenant(
        cookie_kind=None, session_tenant_slug=None, request_tenant=_tenant("acme"),
        user_role="", super_admin_role="super_admin",
    )
    assert out is GuardOutcome.PASS
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_tenant_guard.py -v`
Expected: import error.

- [ ] **Step 3: Implement the guard**

Create `src/dazzle/http/runtime/tenant/guard.py`:

```python
"""Cross-tenant session guard (#1289 slice 5).

The truth table is in the design spec. This module exposes a single
`check_cross_tenant()` function plus typed exceptions so the auth
dependency can convert them to HTTP 403 with specific error codes for
logging and observability.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from dazzle.http.runtime.tenant.resolver import ResolvedTenant


class GuardOutcome(Enum):
    PASS = "pass"


class CrossTenantForbidden(Exception):
    pass


class HostCookieMissingTenant(Exception):
    pass


class ApexCookieNotSuperAdmin(Exception):
    pass


def check_cross_tenant(
    *,
    cookie_kind: Literal["host", "apex"] | None,
    session_tenant_slug: str | None,
    request_tenant: ResolvedTenant | None,
    user_role: str,
    super_admin_role: str,
) -> GuardOutcome:
    """Apply the cross-tenant truth table; pass or raise.

    `cookie_kind` is None for unauthenticated requests (no session cookie).
    """
    if cookie_kind is None:
        return GuardOutcome.PASS

    if cookie_kind == "host":
        if request_tenant is None:
            raise HostCookieMissingTenant(
                "host-bound cookie presented on apex (no tenant) request"
            )
        if request_tenant.slug != session_tenant_slug:
            raise CrossTenantForbidden(
                f"host-bound cookie for {session_tenant_slug!r} "
                f"presented on {request_tenant.slug!r}"
            )
        return GuardOutcome.PASS

    # cookie_kind == "apex"
    if user_role != super_admin_role:
        raise ApexCookieNotSuperAdmin(
            f"apex cookie presented by role {user_role!r}, "
            f"requires {super_admin_role!r}"
        )
    return GuardOutcome.PASS
```

- [ ] **Step 4: Run the guard tests**

Run: `pytest tests/unit/test_tenant_guard.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/tenant/guard.py tests/unit/test_tenant_guard.py
git commit -m "Cross-tenant guard truth table (#1289 slice 5)"
```

---

### Task 5.2 — Wire guard into auth dependency

**Files:**
- Modify: `src/dazzle/http/runtime/auth/dependencies.py` (or whichever module owns `get_current_user`)
- Modify: `tests/unit/test_tenant_guard.py`

- [ ] **Step 1: Inspect the existing auth dependency**

Run: `grep -rn "def get_current_user\|def current_user\|Depends.get_current_user" src/dazzle/http/runtime/auth/ | head -10`

Note the function signature and where requests flow through it. Pick the smallest hook point — usually right after the user is loaded from the session.

- [ ] **Step 2: Write the failing wiring test**

Append to `tests/unit/test_tenant_guard.py`:

```python
def test_auth_dependency_returns_403_on_cross_tenant_mismatch(client_with_two_tenants):
    """Pseudo-fixture: an app with Trust acme + Trust other, authed as acme.

    The implementer wires this against the existing auth-dep fixture
    pattern in the integration tests; pin a minimal repro and assert
    HTTPException(403) is raised when an acme-bound cookie hits
    other.example.com.
    """
    import pytest
    pytest.skip(
        "Auth-dep integration scaffolding lands in this task. "
        "Use the existing tests/integration/ fixtures as a template."
    )
```

- [ ] **Step 3: Add the guard call**

In the existing `get_current_user` (or equivalent) dependency, after the user is loaded but before it is returned, insert:

```python
# #1289 slice 5: enforce cross-tenant cookie binding.
from dazzle.http.runtime.tenant.cookies import (
    apex_cookie_name,
    host_cookie_name,
)
from dazzle.http.runtime.tenant.guard import (
    ApexCookieNotSuperAdmin,
    CrossTenantForbidden,
    HostCookieMissingTenant,
    check_cross_tenant,
)
from fastapi import HTTPException

tenant_cfg = getattr(request.app.state, "tenant_host", None)
if tenant_cfg is not None:
    host_name = host_cookie_name(tenant_cfg.app_name)
    apex_name = apex_cookie_name(tenant_cfg.app_name)
    if request.cookies.get(host_name):
        cookie_kind = "host"
    elif request.cookies.get(apex_name):
        cookie_kind = "apex"
    else:
        cookie_kind = None

    try:
        check_cross_tenant(
            cookie_kind=cookie_kind,
            session_tenant_slug=getattr(user, "tenant_slug", None),
            request_tenant=getattr(request.state, "tenant", None),
            user_role=getattr(user, "role", "") or "",
            super_admin_role=tenant_cfg.super_admin_role,
        )
    except (CrossTenantForbidden, HostCookieMissingTenant, ApexCookieNotSuperAdmin) as e:
        raise HTTPException(status_code=403, detail=str(e))
```

`app.state.tenant_host` is set by `_mount_tenant_resolution_middleware` from slice 3 — extend that helper to assign a small `TenantStateMarker(app_name, super_admin_role)` dataclass to `app.state.tenant_host` after constructing the binding(s). The app-level state lets the auth dependency know whether the guard is in scope at all.

- [ ] **Step 4: Update Step 1's skipped test**

Replace the skipped body with a concrete integration test (mirroring an existing auth-dep integration test). Assert HTTPException 403 on a forged cross-tenant cookie.

- [ ] **Step 5: Run the guard wiring test**

Run: `pytest tests/unit/test_tenant_guard.py -v`
Expected: 7 PASS (or 6 PASS + 1 SKIPPED in a unit-only environment).

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/http/runtime/auth/dependencies.py src/dazzle/http/runtime/app_factory.py tests/unit/test_tenant_guard.py
git commit -m "Wire cross-tenant guard into auth dependency (#1289 slice 5)"
```

---

### Task 5.3 — Pre-ship gates + bump + ship slice 5

- [ ] **Step 1: Pre-ship gates**

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
mypy src/dazzle
pytest tests/unit/test_tenant_*.py tests/unit/test_*auth* tests/unit/test_*_drift.py tests/unit/test_no_*.py -q
mkdocs build --strict
```

- [ ] **Step 2: Bump + ship**

```bash
/bump patch
/ship
```

- [ ] **Step 3: Confirm CI green via `/cimonitor`**

---

## Slice 6 — Auto-bust cache hook + manual `dazzle.tenant.bust()` API

**Purpose:** Repository.update() on any entity carrying `tenant_host:` must auto-bust the cache for the row's old and new slug values post-commit. Also expose a public `dazzle.tenant.bust(slug)` helper for raw-SQL renames.

**Files:**
- Modify: `src/dazzle/http/runtime/repository.py` (post-commit hook)
- Modify: `src/dazzle/__init__.py` (re-export `dazzle.tenant.bust`)
- Create: `src/dazzle/tenant.py` (thin public-API module)
- Test: `tests/unit/test_tenant_bust_hook.py`

---

### Task 6.1 — Manual public-API `bust()`

**Files:**
- Create: `src/dazzle/tenant.py`
- Modify: `src/dazzle/__init__.py`
- Test: `tests/unit/test_tenant_bust_hook.py`

- [ ] **Step 1: Write the failing public-API test**

Create `tests/unit/test_tenant_bust_hook.py`:

```python
"""Tests for the auto-bust hook + public dazzle.tenant.bust API (#1289 slice 6)."""
from __future__ import annotations

from dazzle.http.runtime.tenant.cache import TenantCache


def test_public_bust_clears_module_cache(monkeypatch):
    """dazzle.tenant.bust(slug) removes any cached entry for that slug."""
    import dazzle.tenant as t

    cache = TenantCache(max_entries=4, ttl_seconds=60)
    cache.set("acme", {"id": 1})
    monkeypatch.setattr(t, "_active_caches", lambda: [cache])

    t.bust("acme")
    assert cache.get("acme") is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_tenant_bust_hook.py -v`
Expected: import error.

- [ ] **Step 3: Implement the public-API module**

Create `src/dazzle/tenant.py`:

```python
"""Public API for tenant cache management (#1289 slice 6).

Most projects don't need this — the framework auto-busts on
Repository.update of any slug field on a tenant_host: entity. Use this
helper for raw-SQL renames, migration fixups, and admin CLI tools.
"""
from __future__ import annotations

from collections.abc import Iterable

from dazzle.http.runtime.tenant.cache import TenantCache

_REGISTERED_CACHES: list[TenantCache] = []


def _register_cache(cache: TenantCache) -> None:
    """Called from app_factory when a TenantHostBinding is built."""
    _REGISTERED_CACHES.append(cache)


def _active_caches() -> Iterable[TenantCache]:
    return list(_REGISTERED_CACHES)


def bust(slug: str) -> None:
    """Remove `slug` from every registered tenant cache."""
    for cache in _active_caches():
        cache.bust(slug)
```

- [ ] **Step 4: Wire app_factory to register caches**

In `src/dazzle/http/runtime/app_factory.py`, inside `_mount_tenant_resolution_middleware`, after constructing each `TenantHostBinding(...)` (slice 3), call:

```python
from dazzle.tenant import _register_cache
_register_cache(binding.cache)
```

- [ ] **Step 5: Re-export at top level**

In `src/dazzle/__init__.py`, add (or extend an existing `tenant`-related re-export):

```python
from dazzle import tenant  # noqa: F401 — public sub-module
```

If the top-level `__init__.py` already uses `__all__`, append `"tenant"`.

- [ ] **Step 6: Run the public-API test**

Run: `pytest tests/unit/test_tenant_bust_hook.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/tenant.py src/dazzle/__init__.py src/dazzle/http/runtime/app_factory.py tests/unit/test_tenant_bust_hook.py
git commit -m "Public dazzle.tenant.bust API + cache registration (#1289 slice 6)"
```

---

### Task 6.2 — Auto-bust on Repository.update

**Files:**
- Modify: `src/dazzle/http/runtime/repository.py`
- Modify: `tests/unit/test_tenant_bust_hook.py`

- [ ] **Step 1: Write the failing auto-bust test**

Append to `tests/unit/test_tenant_bust_hook.py`:

```python
async def test_repository_update_auto_busts_old_and_new_slug(
    monkeypatch, in_memory_repository_factory
):
    """Updating a row's slug field auto-busts both old and new slug cache entries.

    Pattern: use the existing in-memory repository fixture from the
    project (search tests for `in_memory_repository_factory` or its
    nearest equivalent). If no fixture exists yet, use a thin double of
    Repository.update() that calls the hook.
    """
    import pytest
    pytest.skip(
        "Implementer: wire to the project's in-memory repository fixture. "
        "Pattern: set cache['old'] = {...}, call repo.update(id, "
        "{'slug': 'new'}), assert cache['old'] is None and cache['new'] is None."
    )
```

- [ ] **Step 2: Add the auto-bust hook to Repository.update**

Locate `Repository.update` (around `src/dazzle/http/runtime/repository.py:865`). After the row is committed and just before returning, add:

```python
# #1289 slice 6: auto-bust tenant cache on slug-field updates.
tenant_host = getattr(self._entity_spec, "tenant_host", None)
if tenant_host is not None and tenant_host.slug_field in data:
    from dazzle.tenant import bust

    old_slug = original_row.get(tenant_host.slug_field) if original_row else None
    new_slug = data[tenant_host.slug_field]
    if old_slug:
        bust(old_slug)
    if new_slug and new_slug != old_slug:
        bust(new_slug)
```

`original_row` is the pre-update snapshot. If `Repository.update` doesn't already load the existing row, fetch it via the existing `find_by_id` path so we have the old slug to bust. Keep the additional read scoped — only run it when `tenant_host` is set and `slug_field in data`.

- [ ] **Step 3: Implement the skipped test**

Replace `pytest.skip(...)` with a concrete test using the project's existing repository fixture pattern (search `tests/integration/test_repository*.py` if needed; otherwise build a thin double using SQLAlchemy in-memory).

- [ ] **Step 4: Run the auto-bust test**

Run: `pytest tests/unit/test_tenant_bust_hook.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/repository.py tests/unit/test_tenant_bust_hook.py
git commit -m "Repository.update auto-busts tenant cache on slug change (#1289 slice 6)"
```

---

### Task 6.3 — Pre-ship gates + bump + ship slice 6

- [ ] **Step 1: Pre-ship gates**

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
mypy src/dazzle
pytest tests/unit/test_tenant_*.py tests/unit/test_*_drift.py tests/unit/test_no_*.py -q
mkdocs build --strict
```

- [ ] **Step 2: Bump + ship**

```bash
/bump patch
/ship
```

- [ ] **Step 3: Confirm CI green via `/cimonitor`**

---

## Slice 7 — Docs + AegisMark filing

**Purpose:** Land the public reference page, CHANGELOG Agent Guidance, and post the AegisMark pin-bump filing comment so the second consumer can swap their five project-side modules for the framework primitive.

**Files:**
- Create: `docs/reference/tenant-hosts.md`
- Modify: `mkdocs.yml` (add the new page to nav)
- Modify: `CHANGELOG.md` (Agent Guidance bullet)
- GitHub comment on issue #1289 with the AegisMark pin-bump checklist

---

### Task 7.1 — Reference page

**Files:**
- Create: `docs/reference/tenant-hosts.md`
- Modify: `mkdocs.yml`

- [ ] **Step 1: Write the reference page**

Create `docs/reference/tenant-hosts.md`:

```markdown
# Multi-Tenant Hosts (`tenant_host:`)

The `tenant_host:` entity keyword (#1289) auto-mounts a Host-header
tenant routing stack: subdomain → entity lookup, history-table 301/410
redirects, cross-tenant session guard, and `__Host-` / `__Secure-`
cookie naming. Apps that don't use it are unaffected.

## When to use it

When your app routes by subdomain — `acme.example.com`,
`westwood.example.com` — and you want the framework to handle
resolution, caching, redirect history, and cookie scoping.

## Minimum example

```dsl
entity Trust:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
```

## Full surface

| Sub-field | Default | Meaning |
|---|---|---|
| `domain:` (required) | — | the base host suffix (e.g. `aegismark.ai`) |
| `slug_field:` (required) | — | name of the `slug:` field on this entity |
| `canonical_hosts:` | `[]` | host(s) that pass through with `request.state.tenant = None` |
| `cookie_scope:` | `host` | `host` or `apex`; drives cookie naming |
| `super_admin_role:` | `super_admin` | role allowed to hold the apex cookie |
| `history_entity:` | _none_ | entity tracking renamed slugs (old/new/expires_at) |
| `not_found_template:` | framework default | dotted-path callable returning 404 HTML |
| `expired_template:` | framework default | dotted-path callable returning 410 HTML |
| `order:` | lexical | required iff 2+ entities share a `domain:` |

See the design spec at
`docs/superpowers/specs/2026-05-28-tenant-host-keyword-design.md` for the
truth table, cache contract, and migration notes.

## Cookies

- Non-`tenant_host:` apps: `dazzle_session` cookie unchanged.
- `tenant_host:` apps: session cookie name switches to
  `__Host-<app>_session` for tenant-bound sessions and
  `__Secure-<app>_admin` for canonical-host super-admin sessions.
- `<app>` is the `app <name>` declaration lowercased with non-alphanumeric
  characters collapsed to underscore.

## Cache busting

The framework auto-busts the in-process LRU cache on `Repository.update`
for slug-field changes on `tenant_host:` entities. For raw-SQL renames,
migration fixups, or admin tooling, call:

```python
import dazzle.tenant
dazzle.tenant.bust("renamed-slug")
```

## Validate-time checks

`dazzle validate` rejects:

- `slug_field` pointing at a non-`slug:`-typed field
- A malformed `domain:`
- Multiple entities on one `domain:` without a distinct `order: N`
- `history_entity:` pointing at an entity that doesn't exist
- A dotted-path template that can't be imported

It warns on:

- The full lookup order across multi-entity domains (helper output)
- Cross-domain slug collisions
```

- [ ] **Step 2: Add page to nav**

In `mkdocs.yml`, find the `nav:` section under `reference/` and add:

```yaml
      - Tenant Hosts: reference/tenant-hosts.md
```

Place it alphabetically with the rest of the reference entries.

- [ ] **Step 3: Build docs**

Run: `mkdocs build --strict`
Expected: clean build with the new page included.

- [ ] **Step 4: Commit**

```bash
git add docs/reference/tenant-hosts.md mkdocs.yml
git commit -m "Reference page for tenant_host: (#1289 slice 7)"
```

---

### Task 7.2 — CHANGELOG Agent Guidance + AegisMark filing

**Files:**
- Modify: `CHANGELOG.md`
- GitHub comment on #1289

- [ ] **Step 1: Update CHANGELOG**

In the next version's `Unreleased` block, under `### Agent Guidance`:

```markdown
- When building a multi-tenant Dazzle app, use `tenant_host:` on the
  tenant root entity (per #1289). The framework auto-mounts host
  resolution, the cache, cross-tenant guard, and cookie naming. Project
  code at `pipeline/tenant/*` for these concerns should be deleted
  rather than maintained. See `docs/reference/tenant-hosts.md`.
```

- [ ] **Step 2: Post pin-bump comment on issue #1289**

```bash
gh issue comment 1289 --body "$(cat <<'EOF'
Implemented across v0.80.X through v0.80.X (slices 1-6); docs + CHANGELOG land in slice 7. AegisMark pin-bump checklist:

- [ ] Pin-bump dazzle-dsl to the release containing slice 7
- [ ] Delete `pipeline/tenant/middleware.py`
- [ ] Delete `pipeline/tenant/resolver.py`
- [ ] Delete `pipeline/tenant/cache.py`
- [ ] Delete `pipeline/tenant/guard.py` (framework guard supersedes)
- [ ] Delete `pipeline/tenant/cookies.py` (framework cookies supersede)
- [ ] Keep `pipeline/tenant/reserved_slugs.py` (project policy data)
- [ ] Delete the TenantResolutionMiddleware mount from
  `pipeline/serve/app_init.py:register_middleware` (framework auto-mounts)
- [ ] Add `tenant_host:` block to the Trust + School entity DSL

Closes #1289.
EOF
)"
```

- [ ] **Step 3: Commit + ship**

```bash
git add CHANGELOG.md
/bump patch
/ship
```

- [ ] **Step 4: Close the issue once CI is green**

After `/cimonitor` confirms green:

```bash
gh issue close 1289 --reason completed
gh issue edit 1289 --remove-label needs-triage
```

---

## Final sanity pass

After slice 7 ships:

- [ ] All seven version bumps recorded in CHANGELOG, contiguous patch versions
- [ ] No open `tenant_host:`-tagged TODOs in the codebase (`rg -i 'TODO.*tenant_host' src/`)
- [ ] `docs/api-surface/{ir-types,dsl-constructs}.txt` baselines reflect the new keyword + IR type
- [ ] PyPI publish workflow green for each shipped version (per the [[optional-extras-eager-imports]] memory — `dazzle --help` still works on a base wheel; no new eager imports of optional-extra deps)
- [ ] `gh issue view 1289` shows `state: CLOSED`
