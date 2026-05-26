# Agent Code Quality Substrate — Round 4: `dazzle.types` + `PA-LLM-10 magic_string_typing`

**Status:** Draft
**Author:** James Barlow (idea), Claude (design)
**Date:** 2026-05-26
**Related issue:** #1270
**Previous rounds:** v0.75.0 (PA-LLM-07), v0.76.0 (PA-LLM-08), v0.76.1 (comprehension N+1), v0.77.0 (PA-LLM-09 + dazzle.result — first Layer-2 ship)

## 1. Why this design exists

Round 3 (v0.77.0) shipped the first Layer-2 substrate piece: `dazzle.result`. Round 4 ships the second: `dazzle.types`. Together they form the Layer-2 substrate's primary surface — `dazzle.result` for distinguishing failure modes, `dazzle.types` for distinguishing identifier classes.

The `magic-string-typing` pattern is gap #7 in the substrate audit (`dev_docs/2026-05-25-substrate-audit.md`) — partially countered by DSL-level enum support, but uncovered at the user-app Python boundary. Round 4 closes that boundary.

## 2. What already exists

- **Round-3 substrate pipeline** (library + catalogue + detector, bidirectional drift, CI gate) is fully battle-tested. Round 4 reuses the same pattern.
- **`dazzle.result`** (round 3) as the precedent for Layer-2 ergonomics: thin convention library + catalogue convention + detector enforcement.
- **No existing `NewType` usage** in `src/dazzle/` — round 4 introduces the pattern without colliding with framework-internal types.

Genuinely missing:

- **`dazzle.types` module.** No file at `src/dazzle/types.py` (the existing `dazzle.layout.types` is unrelated — UI layout types).
- **`magic-string-typing.md` catalogue entry.** The substrate-audit gap #7 has no formal catalogue documentation yet.
- **`PA-LLM-10` heuristic.** PythonAuditAgent stops at PA-LLM-09.

## 3. Three artefacts

### Artefact A — `dazzle.types` convention library

**File:** `src/dazzle/types.py` (new), ~15 LOC. Pure re-export of `typing.NewType`.

```python
"""Branded types for identifier classes — distinguish UserId from TenantId.

Counter-prior: `magic-string-typing`. The catalogue at
`docs/counter-priors/magic-string-typing.md` explains the antipattern this
shape inoculates against and the convention for declaring branded ID types.

NewType is Python stdlib (typing.NewType) and is runtime-free — the
returned callable is the identity function. The type checker treats
`UserId = NewType("UserId", str)` as distinct from str, catching mix-ups
between identifier classes.

Convention: declare branded types where they belong (typically `app/ids.py`).
This module re-exports NewType for one-stop discovery; you do not need to
import from typing at all.

Example:

    from dazzle.types import NewType

    UserId = NewType("UserId", str)
    TenantId = NewType("TenantId", str)

    def fetch(uid: UserId, tid: TenantId) -> User:
        ...

    # Type checker catches: fetch(tid, uid)  # arguments swapped, would silently break
"""

from __future__ import annotations

from typing import NewType

__all__ = ["NewType"]
```

**Public re-exports** in `src/dazzle/__init__.py`:

```python
from .types import NewType

__all__ = [
    # ... existing entries including round-3's Ok/Err/Result/UnwrapError ...
    "NewType",
]
```

**Tests** at `tests/unit/test_types.py`, ~50 LOC:

- `test_newtype_creates_branded_alias` — `UserId = NewType("UserId", str); assert UserId("x") == "x"` (identity at runtime).
- `test_newtype_type_name` — `UserId.__name__ == "UserId"`.
- `test_newtype_supertype` — `UserId.__supertype__ is str`.
- `test_public_import_from_dazzle_types` — `from dazzle.types import NewType` works.
- `test_public_import_from_dazzle_root` — `from dazzle import NewType` works and is the same object as `typing.NewType`.

### Artefact B — `magic-string-typing.md` counter-prior

**File:** `docs/counter-priors/magic-string-typing.md` (new). Four mandatory sections + frontmatter declaring PA-LLM-10.

**Frontmatter:**

```yaml
---
id: magic_string_typing
name: Magic-string typing — bare `str` where a brand or enum would catch errors
layer: inference
status: active
summary: >-
  Using bare `str` for values that are semantically narrower than "any
  string": identifier classes (`user_id: str`), status discriminators
  (`status: str` checked against literal strings), or dictionary keys
  for typed lookups. The type checker can't distinguish a UserId from a
  TenantId when both are `str`; an enum dispatch can't catch typos when
  the cases are literal strings. Use NewType for IDs and StrEnum for
  closed value sets.
triggers_text:
  - "id is a string"
  - "status string"
  - "discriminator string"
  - "magic string"
  - "string-typed identifier"
  - "type the id as str"
triggers_code:
  - 'def\s+\w+\([^)]*\b\w*_id:\s*str\b'
  - 'def\s+\w+\([^)]*\b\w*_uuid:\s*str\b'
  - 'if\s+\w+\s*==\s*"\w+":\s*\n\s*(.*\n\s*)*elif\s+\w+\s*==\s*"\w+":'
refs:
  adrs: []
  memories: []
  tests:
    - tests/unit/test_python_audit_magic_string_typing.py
detectors:
  - id: PA-LLM-10
    agent: PA
    note: fires on function/method parameters whose name matches `id`, `*_id`, `*_uuid`, `*_key`, or `*_token` AND whose annotation is bare `str` (or `str | None` / `Optional[str]`). Covers sub-shape (a) magic-string IDs only; sub-shapes (b) enum-dispatch chains and (c) typed-lookup keys are documented in the body but not detected today.
---
```

**Body** — four mandatory sections covering all three sub-shapes:

**`## The corpus prior`** — Python's stdlib `str` is the universal carrier. Tutorials use it for IDs (`user_id: str`), for status fields (`status: str` with conditional dispatch on literals like `"pending"`, `"approved"`), and for typed lookup keys (`record["status"]`). The corpus is dominated by this shape because `str` is the path of least resistance and the type checker doesn't complain. Mix-ups (`fetch(tenant_id, user_id)` instead of `fetch(user_id, tenant_id)`) typecheck cleanly and surface as data corruption later. Typos in dispatch literals (`elif status == "aprroved":`) never fire and silently fall through.

**`## Wrong shape`** — Three sub-shapes:

**(a) Magic-string IDs:**

```python
def transfer_funds(source_id: str, destination_id: str, amount: int) -> Result[Receipt, TransferError]:
    ...

# Caller:
transfer_funds(destination_id, source_id, amount)  # arguments swapped, type-checker happy
```

**(b) Enum-dispatch chains:**

```python
def render_status_badge(status: str) -> str:
    if status == "pending":
        return "⏳"
    elif status == "approved":
        return "✅"
    elif status == "rejected":
        return "❌"
    # typo: "aprroved" silently falls through
    return ""
```

**(c) Typed lookup keys (informational — not detected by PA-LLM-10):**

```python
def get_field(record: dict, key: str) -> object:
    return record[key]  # any string is acceptable; no type-checker leverage
```

**`## Right shape`** — Three patterns:

**(a) Branded IDs via `dazzle.types.NewType`:**

```python
# app/ids.py
from dazzle.types import NewType

UserId = NewType("UserId", str)
TenantId = NewType("TenantId", str)
PaymentId = NewType("PaymentId", str)
```

```python
# app/transfers.py
from app.ids import PaymentId

def transfer_funds(source_id: PaymentId, destination_id: PaymentId, amount: int) -> Result[Receipt, TransferError]:
    ...

# Caller:
src = PaymentId(row["src_id"])
dst = PaymentId(row["dst_id"])
transfer_funds(src, dst, amount)  # both are PaymentId — no swap risk between distinct ID classes
```

The brand catches mix-ups between **different** ID classes (`UserId` vs `TenantId`). Within a single ID class, mix-ups are still possible (you can swap `source_id` and `destination_id` if they're both `PaymentId`) but that's a parameter-ordering bug a careful reviewer catches; the type checker catches the *cross-class* error which is the harder one.

**(b) Closed sets via `enum.StrEnum`:**

```python
from enum import StrEnum


class OrderStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


def render_status_badge(status: OrderStatus) -> str:
    match status:
        case OrderStatus.PENDING:
            return "⏳"
        case OrderStatus.APPROVED:
            return "✅"
        case OrderStatus.REJECTED:
            return "❌"
    # type checker (with exhaustive match) catches missing cases
```

Typos in the StrEnum class definition fail loudly at class-definition time; typos in match arms typecheck as errors. The `str` value is preserved (`OrderStatus.PENDING == "pending"` is True) so JSON serialization works without changes.

**(c) TypedDict for record keys (informational):**

```python
from typing import TypedDict


class OrderRecord(TypedDict):
    status: OrderStatus
    amount: int
    customer_id: UserId


def get_status(record: OrderRecord) -> OrderStatus:
    return record["status"]  # mypy catches typos in the key
```

**Convention notes:**

- Declare branded types in `app/ids.py` (or similar) — co-located with their domain, importable from anywhere in `app/`.
- Use `enum.StrEnum` (stdlib, Python 3.11+) for closed value sets. Don't reach for a library; the stdlib is enough.
- `NewType` is runtime-free — `UserId("x")` returns the plain `str` `"x"`. The brand is type-checker-only. This is the right tradeoff: zero runtime cost, full static safety.

**`## Why this matters here`** — Dazzle's framework code paths use typed IR (`EntityRef`, `PersonaSpec`, etc.) and DSL-level enums (`enum` keyword) that prevent magic-string typing at the model layer. User-app Python in `app/` doesn't yet have an idiomatic answer — agents reach for `str` because the corpus does. `PA-LLM-10` flags ID-shaped parameters at scan time; `dazzle.types` makes the right shape one import away; the catalogue documents all three sub-shapes for inference-time agent guidance even though only (a) is detected today.

### Artefact C — `PA-LLM-10` heuristic

**Module additions to `src/dazzle/sentinel/agents/python_audit.py`:**

```python
# ---------------------------------------------------------------------------
# PA-LLM-10 helpers — magic-string-typing (ID-shaped parameters)
# ---------------------------------------------------------------------------

import re

# Matches: bare `id`, or any name ending in `_id`, `_uuid`, `_key`, `_token`.
_ID_NAME_RE = re.compile(r"(^id$)|(_(id|uuid|key|token)$)")


def _is_id_shaped_name(name: str) -> bool:
    """True if the parameter name suggests an identifier class."""
    return bool(_ID_NAME_RE.search(name))


def _is_bare_str_annotation(node: ast.AST | None) -> bool:
    """True if the annotation is bare `str`, `str | None`, `None | str`, or `Optional[str]`.

    Does NOT fire on NewType-branded annotations (those are ast.Name with a
    non-str id) or on str subclasses.
    """
    if node is None:
        return False
    # Bare `str`
    if isinstance(node, ast.Name):
        return node.id == "str"
    # `str | None` / `None | str`
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = node.left
        right = node.right
        # Either side is bare str AND the other is None constant
        left_is_str = isinstance(left, ast.Name) and left.id == "str"
        right_is_str = isinstance(right, ast.Name) and right.id == "str"
        left_is_none = isinstance(left, ast.Constant) and left.value is None
        right_is_none = isinstance(right, ast.Constant) and right.value is None
        if (left_is_str and right_is_none) or (right_is_str and left_is_none):
            return True
        return False
    # `Optional[str]`
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        if node.value.id == "Optional":
            inner = node.slice
            return isinstance(inner, ast.Name) and inner.id == "str"
    return False


def _has_dataclass_decorator(cls: ast.ClassDef) -> bool:
    """True if any decorator references `dataclass` by name or attribute."""
    for dec in cls.decorator_list:
        # @dataclass
        if isinstance(dec, ast.Name) and dec.id == "dataclass":
            return True
        # @dataclass(frozen=True, slots=True)
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == "dataclass":
            return True
        # @dataclasses.dataclass / @dc.dataclass
        if isinstance(dec, ast.Attribute) and dec.attr == "dataclass":
            return True
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "dataclass":
            return True
    return False


def _detect_magic_string_id(tree: ast.AST, path: Path) -> list[_ShapeHit]:
    """Return _ShapeHit records for ID-shaped parameters typed as bare `str`.

    Walks FunctionDef and AsyncFunctionDef nodes anywhere in the tree
    (including methods on classes), skipping:
    - `self` and `cls` parameters (never str-typed in practice)
    - dataclass-decorated classes (their synthesized __init__ would
      fire spuriously; the field annotations are the source of truth and
      a separate detector could handle them later)
    - nested functions inside dataclass-decorated classes (skipped by the
      enclosing class skip)
    """
    # First pass: collect line ranges of dataclass-decorated classes to skip.
    dataclass_ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _has_dataclass_decorator(node):
            # ast.ClassDef has .lineno and .end_lineno (Python 3.8+).
            end = getattr(node, "end_lineno", None) or node.lineno
            dataclass_ranges.append((node.lineno, end))

    def _in_dataclass(fn_lineno: int) -> bool:
        return any(start <= fn_lineno <= end for start, end in dataclass_ranges)

    hits: list[_ShapeHit] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if _in_dataclass(node.lineno):
            continue

        # Walk every argument (posonly, regular, kwonly).
        all_args: list[ast.arg] = []
        all_args.extend(node.args.posonlyargs)
        all_args.extend(node.args.args)
        all_args.extend(node.args.kwonlyargs)

        for arg in all_args:
            if arg.arg in ("self", "cls"):
                continue
            if not _is_id_shaped_name(arg.arg):
                continue
            if not _is_bare_str_annotation(arg.annotation):
                continue
            hits.append(
                _ShapeHit(
                    line=arg.lineno if hasattr(arg, "lineno") else node.lineno,
                    snippet=f"{arg.arg}: str",
                    shape="magic_string_id",
                    try_line=node.lineno,  # def line for noqa scoping
                )
            )
    return hits
```

**`@heuristic` method** following the established pattern: ID `PA-LLM-10`, severity MEDIUM, confidence LIKELY, `catalogue_entry="magic-string-typing"`, suppression via `# noqa: PA-LLM-10` on the `def` line OR the parameter line.

**Tests** at `tests/unit/test_python_audit_magic_string_typing.py`, ~150 LOC:

Positives:
- `test_user_id_str_param_fires` — `def f(user_id: str)`
- `test_tenant_uuid_str_param_fires` — `def f(tenant_uuid: str)`
- `test_bare_id_param_fires` — `def f(id: str)`
- `test_key_suffix_fires` — `def f(api_key: str)` (noisy but in-scope)
- `test_token_suffix_fires` — `def f(auth_token: str)` (noisy but in-scope)
- `test_str_pipe_none_fires` — `def f(user_id: str | None)`
- `test_optional_str_fires` — `def f(user_id: Optional[str])`
- `test_method_id_param_fires` — `class C: def m(self, user_id: str)`
- `test_async_fn_id_param_fires` — `async def f(user_id: str)`
- `test_multiple_ids_yield_multiple_hits` — `def f(user_id: str, tenant_id: str)` → 2 hits

Negatives:
- `test_branded_newtype_no_fire` — `def f(user_id: UserId)` (annotation is Name with id="UserId", not "str")
- `test_int_annotation_no_fire` — `def f(user_id: int)` (integer IDs out of scope)
- `test_non_id_param_no_fire` — `def f(name: str)` (name doesn't match `*_id` suffix)
- `test_self_param_no_fire` — `def m(self)` (self never str-typed but defensive check)
- `test_dataclass_init_no_fire` — `@dataclass class User: user_id: str` (synthesized __init__ skipped)
- `test_frozen_dataclass_no_fire` — `@dataclass(frozen=True, slots=True) class User: user_id: str`
- `test_no_annotation_no_fire` — `def f(user_id)` (untyped — out of scope, mypy would catch this separately)

Suppression:
- `test_noqa_suppression_on_def` — `def f(user_id: str):  # noqa: PA-LLM-10`
- `test_noqa_suppression_on_param_line` — `def f(\n    user_id: str,  # noqa: PA-LLM-10\n):` (multi-line param)

Integration:
- `test_heuristic_yields_finding_with_catalogue_entry` — end-to-end
- `test_heuristic_skips_tests_and_scripts` — only `app/` scanned

## 4. Data flow

No new plumbing. PA-LLM-10 plugs into the existing pipeline exactly like PA-LLM-07/08/09:

```
user app/ Python
     ↓
PythonAuditAgent.check_magic_string_typing
     ↓
Finding(catalogue_entry="magic-string-typing", remediation.references=[catalogue_url])
     ↓
FindingStore → sentinel findings MCP → agent on next iteration
```

The catalogue's "right shape" section names `dazzle.types.NewType` and `enum.StrEnum` explicitly so the agent has concrete import targets.

## 5. Suppression + confidence

**Severity:** MEDIUM. **Confidence:** LIKELY — `_key` and `_token` suffixes are noisier than `_id`/`_uuid`:
- `cache_key: str` for a cache lookup is legitimately `str` (it's not a brand, it's a free-form key).
- `auth_token: str` for an opaque bearer token may or may not warrant branding depending on whether the codebase treats different token classes (session vs CSRF vs API key) as distinct.

The catalogue's detector note documents this; `# noqa: PA-LLM-10 — opaque cache key` is the canonical mitigation.

**`# noqa: PA-LLM-10`** on the `def` line OR the parameter line suppresses. The parameter-line form handles multi-line function signatures.

## 6. Scope discipline

**Hard ceiling: 600 LOC total cumulative diff.** Round 3 was 787 (87 over its 700 ceiling); round 4 is smaller because:
- Library is ~15 LOC (just a re-export, vs round 3's 84-LOC dataclasses).
- Detector is comparable to round 2's PA-LLM-08 (~80 LOC vs 193 for PA-LLM-09).

Estimated breakdown:
- `dazzle.types.py` — 15 LOC
- `__init__.py` re-export — 3 LOC
- `tests/unit/test_types.py` — 50 LOC
- `magic-string-typing.md` — 130 LOC (catalogue is content-heavy with all three sub-shapes)
- `python_audit.py` heuristic + helpers — 110 LOC
- `tests/unit/test_python_audit_magic_string_typing.py` — 150 LOC
- KG seed bump — 1 LOC
- API surface baseline regen — variable (Ok/Err/Result + NewType = +1 line)
- CHANGELOG — 20 LOC
- Version files — 6 LOC

Sum: ~485 LOC. Comfortable margin under 600.

## 7. Implementation order

Three task-sized commits, sequential within one branch (`feature/pa-llm-10-magic-string-typing`):

1. **`dazzle.types` library + tests + public re-export.** Standalone.
2. **`magic-string-typing.md` catalogue entry + KG seed bump + INDEX.md.** Frontmatter declares PA-LLM-10; bidirectional drift goes red intentionally.
3. **`PA-LLM-10` heuristic + tests + smoke against examples + CHANGELOG + bump.** Closes the drift.

Same pattern as round 3.

## 8. Risks + open questions

1. **`_key` and `_token` false positives.** Cache keys, parse tokens, security tokens are sometimes legitimately `str`. The confidence is LIKELY (not CONFIRMED) and noqa is the mitigation. If backfill audit shows ≥30% false-positive rate on these suffixes, narrow to `_id`/`_uuid` only in round 4.1.
2. **Dataclass init synthesis.** The `_has_dataclass_decorator` check skips the entire dataclass-decorated class to avoid firing on the synthesized `__init__`. Cost: if the user writes a non-`__init__` method on the dataclass with an ID-shaped param (`def lookup(self, user_id: str)`), it won't fire either. Acceptable tradeoff; explicit non-method functions remain the primary target.
3. **Pydantic models.** `class User(BaseModel): user_id: str` — should this fire? The synthesized `__init__` is similar to dataclass. Round 4 does NOT cover Pydantic models — only `@dataclass`-decorated classes are skipped. Pydantic users would see PA-LLM-10 fire on the synthesized init. Document this as a known caveat; round 4.1 can add `BaseModel`-subclass detection if desired.
4. **`@overload`** — overloaded function signatures live alongside the implementation. The detector walks ALL `FunctionDef` nodes, so an `@overload`-decorated stub with `user_id: str` will fire alongside the impl. Acceptable in v1; could skip `@overload`-decorated functions in a future tightening pass.
5. **`functools.singledispatch`** — registered dispatch implementations have varying parameter shapes. Same disposition as `@overload`.
6. **The `_ID_NAME_RE` regex doesn't match the `_strkey` substring style** (e.g., `usrid` without underscore). Acceptable — the convention is to use underscores, and matching `*_id` rather than `*id` keeps false positives low.

## 9. Success criteria

- All three artefacts ship in one PR. Diff < 600 LOC.
- `dazzle.types.NewType` importable from `dazzle.types` AND `dazzle` top-level.
- Counter-prior entry valid; frontmatter declares PA-LLM-10.
- `PA-LLM-10` heuristic + ~17 tests pass; bidirectional drift test stays green after all three artefacts land.
- Smoke-test on 14 example apps returns zero PA-LLM-10 findings.
- CHANGELOG entry under `[0.78.0]` documents the library + catalogue + heuristic with Agent Guidance bullets.
- API surface drift gate passes after baseline regen (`NewType` added to `public-helpers.txt`).
- pytest (excluding pre-existing flaky #1265), ruff, mypy, mkdocs --strict all clean.

The slice succeeds when an agent prompted to "write a function that takes a user ID and tenant ID" emits `def f(user_id: UserId, tenant_id: TenantId)` (branded) rather than `def f(user_id: str, tenant_id: str)` — because the bootstrap surfaces magic-string-typing from the catalogue, `dazzle.types.NewType` is one import away, and PA-LLM-10 catches reversions to bare `str` at scan time.
