# Agent Code Quality Substrate — Round 3: `dazzle.result` + `PA-LLM-09 optional_instead_of_result`

**Status:** Draft
**Author:** James Barlow (idea), Claude (design)
**Date:** 2026-05-26
**Related issue:** #1257
**Previous rounds:** v0.75.0 (PA-LLM-07), v0.76.0 (PA-LLM-08), v0.76.1 (comprehension N+1)

## 1. Why this design exists

Rounds 1 and 2 of the substrate landed entirely in **Layer 3 (Filter)** — detectors that flag wrong shapes in user code, plus the catalogue that documents them. **Layer 2 (Inference)** — the convention library that makes the right shape ergonomic at agent inference time — has been deliberately untouched until now.

Round 3 ships the first piece of Layer 2: `dazzle.result`. A minimal `Ok[T] / Err[E] / Result[T, E]` tagged-union substrate that gives agents a non-`T | None` answer to "what do I return when this function might fail in multiple ways." The companion counter-prior (`optional-instead-of-result`) documents the antipattern. The companion detector (`PA-LLM-09`) catches user code that emitted the antipattern anyway.

This is the substrate's "do you have the right tool?" round. Rounds 1 and 2 said "don't do the wrong thing"; round 3 finally provides the right thing.

## 2. What already exists

- **Substrate pipeline** end-to-end: counter-prior catalogue with `detectors:` wiring, bidirectional drift test, `PythonAuditAgent` host, CI gate, scaffolding (`dazzle quality bootstrap`).
- **Public import surface** in `src/dazzle/__init__.py` with `__all__` listing — natural home for `Ok`, `Err`, `Result`, `UnwrapError`.
- **Counter-prior frontmatter schema** with optional `detectors:` array (`src/dazzle/mcp/semantics_kb/counter_priors.py`).
- **`@heuristic` decorator** + `_ShapeHit` dataclass + suppression idiom (`# noqa: PA-LLM-XX`) on PA's heuristic methods.

Genuinely missing:

- **`dazzle.result` module.** No file at `src/dazzle/result.py`. No `Ok`/`Err`/`Result` types anywhere in the codebase.
- **`optional-instead-of-result.md` catalogue entry.** Counter-prior dir has 13 entries; this one is not among them.
- **`PA-LLM-09` heuristic.** PythonAuditAgent has PA-LLM-07 and PA-LLM-08 (plus the five ecosystem-hygiene heuristics).

## 3. Three artefacts

### Artefact A — `dazzle.result` convention library

**File:** `src/dazzle/result.py` (new), ~80 LOC.

```python
"""Result type — distinguish multiple failure modes from `None`-as-sentinel.

Counter-prior: `optional-instead-of-result`. The catalogue at
`docs/counter-priors/optional-instead-of-result.md` explains the antipattern
this shape inoculates against and the convention for composing Err types.

Pattern-matching is the canonical consumption idiom:

    match parse_event(text):
        case Ok(event):
            handle(event)
        case Err(EmptyInput()):
            log.warning("empty input — skipping")
        case Err(MalformedJson() as e):
            log.error("parse failed: %s", e.detail)

The four methods (`unwrap`, `unwrap_or`, `is_ok`, `is_err`) cover common
single-branch checks. Match handles composition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, NoReturn, TypeVar

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    """Successful Result carrying a value."""

    value: T

    def unwrap(self) -> T:
        """Return the wrapped value. Always succeeds for Ok."""
        return self.value

    def unwrap_or(self, default: T) -> T:
        """Return the wrapped value. The `default` is unused for Ok."""
        return self.value

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    """Failed Result carrying an error value."""

    error: E

    def unwrap(self) -> NoReturn:
        """Raise `UnwrapError`. Use `match` or `unwrap_or` for safety."""
        raise UnwrapError(self.error)

    def unwrap_or[T2](self, default: T2) -> T2:
        """Return the `default`. The wrapped error is discarded.

        The method-local type variable T2 is independent of E — Err knows
        only the error's type, not the value type of the matching Ok.
        """
        return default

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True


type Result[T, E] = Ok[T] | Err[E]


class UnwrapError(Exception):
    """Raised by `Err.unwrap()`. Carries the wrapped error as `.error`."""

    def __init__(self, error: object) -> None:
        super().__init__(f"called unwrap() on an Err value: {error!r}")
        self.error = error
```

**Public re-exports** in `src/dazzle/__init__.py`:

```python
from .result import Err, Ok, Result, UnwrapError

__all__ = [
    # ... existing entries ...
    "Ok",
    "Err",
    "Result",
    "UnwrapError",
]
```

**Tests** at `tests/unit/test_result.py`, ~120 LOC:

- `test_ok_carries_value` — `Ok(42).value == 42`
- `test_err_carries_error` — `Err("oops").error == "oops"`
- `test_ok_unwrap_returns_value`
- `test_err_unwrap_raises_unwrap_error` — assert `UnwrapError` raised, assert `.error` carries the wrapped value
- `test_ok_unwrap_or_returns_value` (default unused)
- `test_err_unwrap_or_returns_default`
- `test_ok_is_ok_true_is_err_false` + matching test on Err
- `test_match_pattern_ok_branch` — `match Ok(7): case Ok(v): assert v == 7`
- `test_match_pattern_err_branch`
- `test_ok_and_err_not_equal_across_types` — `Ok(1) != Err(1)` (different classes, dataclass eq is False)
- `test_frozen_assignment_raises` — `o = Ok(1); o.value = 2` raises FrozenInstanceError
- `test_slots_no_dict` — `Ok(1).__dict__` raises AttributeError (slots=True)
- `test_generic_parametrisation` — type-only test (mypy/pyright check); a function declared `def f() -> Result[int, str]` returning `Ok(1)` or `Err("x")` type-checks
- `test_unwrap_error_carries_original_error_for_inspection` — try/except on unwrap to assert .error access

### Artefact B — `optional-instead-of-result.md` counter-prior

**File:** `docs/counter-priors/optional-instead-of-result.md` (new). Follows the four-mandatory-section catalogue schema.

**Frontmatter:**
```yaml
---
id: optional_instead_of_result
name: Optional[T] where Result[T, E] would distinguish failure modes
layer: inference
status: active
summary: >-
  Functions returning `T | None` to indicate failure where multiple distinct
  failure modes get collapsed into a single `None` sentinel. The caller can
  no longer distinguish "not found" from "parse error" from "validation
  failure" — all three become indistinguishable `None`. Reach for
  `Result[T, ErrorUnion]` with a tagged-union error type instead.
triggers_text:
  - "returns None on failure"
  - "return None if something goes wrong"
  - "Optional return type"
  - "T or None"
  - "fail with None"
  - "return None if it's not found or invalid"
triggers_code:
  - 'def\s+\w+\([^)]*\)\s*->\s*\w+\s*\|\s*None\s*:'
  - 'def\s+\w+\([^)]*\)\s*->\s*Optional\['
  - 'return\s+None\s*#\s*(parse|validation|not found|fail)'
refs:
  adrs: []
  memories: []
  tests:
    - tests/unit/test_python_audit_optional_instead_of_result.py
detectors:
  - id: PA-LLM-09
    agent: PA
    note: fires on `def f(...) -> T | None` (or Optional[T]) with ≥2 distinct `return None` statements OR a `try/except (X, Y, ...)` block returning None. Does not flag single-failure-mode Optionals (the legitimate find-or-None pattern).
---
```

**Body** (the four mandatory sections):

**`## The corpus prior`** — Tutorials and StackOverflow code overwhelmingly model failure as `None`. "What if the user doesn't exist?" → return None. "What if the JSON is malformed?" → return None. "What if the schema is wrong?" → return None. The corpus contains thousands of examples of `def f(x) -> Foo | None:` with the body collapsing every distinct failure into a `return None`. The pattern compounds because once a function returns `T | None`, the next agent extending it adds another failure path the cheapest way available: another `return None`. The caller's downstream type narrowing then has no way to distinguish *why* the value is None.

**`## Wrong shape`** — Canonical example:

```python
def parse_event(text: str) -> Event | None:
    if not text:
        return None                                    # empty input

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None                                    # parse failure

    try:
        return Event.model_validate(data)
    except ValidationError:
        return None                                    # schema violation
```

Caller code: `event = parse_event(text); if event is None: ???`. The caller cannot log "parse failed at line X" vs "empty input" vs "schema validation failed because the `created_at` field is missing." All three failure modes have been erased.

**`## Right shape`** — Use `Result[Event, ParseError]` with a tagged error union:

```python
from dataclasses import dataclass

from dazzle.result import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class EmptyInput: ...


@dataclass(frozen=True, slots=True)
class MalformedJson:
    detail: str


@dataclass(frozen=True, slots=True)
class SchemaViolation:
    field: str
    detail: str


type ParseError = EmptyInput | MalformedJson | SchemaViolation


def parse_event(text: str) -> Result[Event, ParseError]:
    if not text:
        return Err(EmptyInput())

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return Err(MalformedJson(detail=str(e)))

    try:
        return Ok(Event.model_validate(data))
    except ValidationError as e:
        first = e.errors()[0]
        return Err(SchemaViolation(field=first["loc"][0], detail=first["msg"]))
```

Caller code:

```python
match parse_event(text):
    case Ok(event):
        process(event)
    case Err(EmptyInput()):
        log.warning("empty input — skipping")
    case Err(MalformedJson(detail=d)):
        log.error("parse failure: %s", d)
    case Err(SchemaViolation(field=f, detail=d)):
        log.error("schema error on %s: %s", f, d)
```

The three failure modes are now distinguishable at the call site, and the type checker enforces exhaustive handling.

**Convention for error types:**
- Use `@dataclass(frozen=True, slots=True)` for error variants — same shape as `Ok`/`Err` themselves.
- Tagged unions via `type ParseError = X | Y | Z` (PEP 695).
- Don't use plain strings as error tokens — `Err("not found")` defeats the type-distinction purpose. Use a frozen dataclass even if empty.

**`## Why this matters here`** — Dazzle's framework code paths already practise this discipline (the IR's `LinkError` / `ValidationError` / `ParseError` hierarchy is the framework-layer equivalent). User-app code in `app/` doesn't yet have an idiomatic answer, so agents reach for the corpus default: `T | None`. PA-LLM-09 flags the wrong shape at scan time; `dazzle.result` makes the right shape one import away; the catalogue (this file) bridges the gap at inference time.

### Artefact C — `PA-LLM-09` heuristic

**Module additions to `src/dazzle/sentinel/agents/python_audit.py`:**

```python
# ---------------------------------------------------------------------------
# PA-LLM-09 helpers — optional-instead-of-result
# ---------------------------------------------------------------------------


def _returns_optional_t(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True if the function's return annotation is `T | None` or `Optional[T]`.

    Recognises both PEP 604 (`X | None`) and `typing.Optional[X]` (legacy).
    """
    rt = fn.returns
    if rt is None:
        return False
    # X | None or None | X (BinOp with BitOr operator)
    if isinstance(rt, ast.BinOp) and isinstance(rt.op, ast.BitOr):
        left, right = rt.left, rt.right
        return _is_none_constant(left) or _is_none_constant(right)
    # Optional[X]
    if isinstance(rt, ast.Subscript) and isinstance(rt.value, ast.Name):
        return rt.value.id == "Optional"
    return False


def _is_none_constant(node: ast.AST) -> bool:
    """True if node is the literal `None`."""
    return isinstance(node, ast.Constant) and node.value is None


def _count_return_none(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count distinct `return None` statements (or bare `return`) in fn body.

    Walks the function body — including nested ifs, try/except, etc. Skips
    nested function definitions (those are their own scope).
    """
    count = 0
    for node in ast.walk(fn):
        # Don't descend into nested function definitions.
        if node is not fn and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(node, ast.Return):
            if node.value is None:                  # bare `return`
                count += 1
            elif _is_none_constant(node.value):     # `return None`
                count += 1
    return count


def _has_multi_exception_catch_returning_none(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """True if fn body contains `try/except (X, Y, ...) ...: return None`.

    The except clause must catch ≥2 exception types AND its body must
    contain a `return None` (or bare return) statement.
    """
    for node in ast.walk(fn):
        if not isinstance(node, ast.ExceptHandler):
            continue
        # The except type must be a Tuple (e.g. `except (X, Y):`).
        if not isinstance(node.type, ast.Tuple):
            continue
        if len(node.type.elts) < 2:
            continue
        # The handler body must contain a return None.
        for inner in ast.walk(node):
            if isinstance(inner, ast.Return) and (
                inner.value is None or _is_none_constant(inner.value)
            ):
                return True
    return False


def _detect_optional_instead_of_result(
    tree: ast.AST, path: Path
) -> list[_ShapeHit]:
    """Return _ShapeHit records for functions that should use Result.

    Fires when both conditions hold:
    1. Function signature returns `T | None` (or `Optional[T]`).
    2. Function body has ≥2 distinct `return None` statements OR a
       `try/except (X, Y, ...)` block that returns None.
    """
    hits: list[_ShapeHit] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _returns_optional_t(node):
            continue

        return_none_count = _count_return_none(node)
        multi_catch = _has_multi_exception_catch_returning_none(node)

        if return_none_count < 2 and not multi_catch:
            continue

        shape = "multi_return_none" if return_none_count >= 2 else "multi_exception_catch"
        snippet = f"def {node.name}(...) -> ... | None"
        hits.append(
            _ShapeHit(
                line=node.lineno,
                snippet=snippet,
                shape=shape,
                try_line=node.lineno,  # outer fn def line, for noqa scope
            )
        )
    return hits
```

**`@heuristic` method on `PythonAuditAgent`:**

Follows the established pattern. ID `PA-LLM-09`, severity MEDIUM, confidence LIKELY, `catalogue_entry="optional-instead-of-result"`. `# noqa: PA-LLM-09` suppression on the `def` line. The `try_line` carries the function's `def` line.

**Tests** at `tests/unit/test_python_audit_optional_instead_of_result.py`, ~150 LOC:

Positives:
- `test_two_return_none_fires` — function with `T | None` and two distinct return None
- `test_three_return_none_fires` — three return None (more is still one finding)
- `test_optional_legacy_syntax` — `def f() -> Optional[int]` with two return None
- `test_pipe_none_left_position` — `def f() -> None | int` (None first in union)
- `test_bare_return_counts_as_none` — `return` (no value) counts
- `test_async_function_fires` — `async def f() -> int | None`
- `test_multi_exception_catch_fires` — single return None but `except (KeyError, ValueError): return None`
- `test_yields_finding_with_catalogue_entry` — end-to-end Finding shape

Negatives:
- `test_negative_single_return_none` — `T | None` with one return None doesn't fire (legitimate find-or-None)
- `test_negative_no_optional_return` — `def f() -> int` with multiple return None doesn't apply (type-checker error anyway)
- `test_negative_nested_function_returns_dont_count` — `return None` inside a nested `def` doesn't contribute to the outer's count
- `test_negative_single_exception_catch` — `except KeyError: return None` (one type only) doesn't fire
- `test_negative_noqa_suppression_on_def` — `def f(...) -> int | None:  # noqa: PA-LLM-09`
- `test_negative_no_app_dir` — agent on a project without `app/` returns []

Integration:
- `test_heuristic_skips_tests_and_scripts`
- `test_heuristic_yields_finding_for_real_app_file`

## 4. Data flow

No changes to substrate plumbing. `PA-LLM-09` plugs into the existing pipeline exactly like PA-LLM-07 and PA-LLM-08:

```
user app/ Python
     ↓
PythonAuditAgent.check_optional_instead_of_result
     ↓
Finding(catalogue_entry="optional-instead-of-result", remediation.references=[catalogue_url])
     ↓
FindingStore → sentinel findings MCP op → agent on next iteration
```

The catalogue's "right shape" section names `dazzle.result.Ok`/`Err`/`Result` explicitly so the agent has a concrete import target. The bidirectional drift test (round 1) catches any mismatch between the catalogue's `detectors:` declaration and the actual `@heuristic` method.

## 5. Suppression + confidence

**Severity:** MEDIUM. **Confidence:** LIKELY — the multi-return-None signal is strong but not infallible (a function with two return None that happen to mean the same thing — e.g., two early guards for the same precondition — is technically the signal we're detecting, even though it's not the antipattern's full crime).

**`# noqa: PA-LLM-09`** on the `def` line suppresses. The signature line is the natural anchor — once you've made the deliberate choice that this function is genuinely Optional-shaped (e.g., it's a legitimate cache lookup with multiple "miss" reasons that the caller doesn't distinguish), document why and move on.

## 6. Scope discipline

**Hard ceiling: 700 LOC total cumulative diff** (library + catalogue + detector + tests + CHANGELOG + bump). Round 1 was ~500, round 2 was ~443, round 3 is materially bigger because of the new library — but if the diff exceeds 700, the design has scope-crept and we stop.

Estimated breakdown:
- `dazzle.result.py` — 80 LOC
- `__init__.py` re-export — 5 LOC
- `tests/unit/test_result.py` — 120 LOC
- `optional-instead-of-result.md` — 80 LOC (catalogue body) + 15 LOC (frontmatter)
- `python_audit.py` heuristic + helpers — 120 LOC
- `tests/unit/test_python_audit_optional_instead_of_result.py` — 150 LOC
- KG seed bump — 1 LOC
- CHANGELOG — 20 LOC
- Version files — 6 LOC

Sum: ~597 LOC. Comfortable margin under 700.

## 7. Implementation order

Three task-sized commits, sequential within one branch (`feature/pa-llm-09-optional-instead-of-result`):

1. **`dazzle.result` library + tests + public re-export.** Standalone — the library is testable in isolation, no dependency on the catalogue or detector. Lands first so the catalogue's right-shape section can reference real importable names.
2. **`optional-instead-of-result.md` catalogue entry + KG seed bump.** Adds the frontmatter declaration; round-1 bidirectional drift test enforces the contract — and will FAIL until step 3 lands (PA-LLM-09 doesn't exist yet). That's the intended pressure: the drift test is the forcing function for completing the slice.
3. **`PA-LLM-09` heuristic + tests + smoke against examples + CHANGELOG + bump.** Closes the drift gap. Smoke-test against all 14 example apps; zero PA-LLM-09 findings expected before promoting CI threshold.

Each commit ends in a `git commit`; whole branch ships as one squash-merged PR.

## 8. Risks + open questions

1. **False positives on legitimate find-or-None.** A function that "finds a thing or returns None" with two early `return None` guards (one for "input is empty", one for "thing not found") will fire. Both `return None` mean the same thing semantically. **Mitigation:** the confidence is LIKELY (not CONFIRMED) and noqa is the documented way to mark this case. If backfill audit shows this is the dominant FP class, the detector can be tightened in round 3.1.
2. **Type-comment-style annotations** (`def f(x): # type: int -> int | None`) won't be caught. PEP 484 type comments are essentially dead in Python 3.12+; not worth supporting.
3. **`functools.singledispatch` and `@overload`** — overloaded functions have separate signatures. The detector inspects only the implementation `def`, not the `@overload` declarations. Acceptable v1 limitation.
4. **`dataclass(eq=True)` default for Ok/Err** — means `Ok(1) == Ok(1)` is True (value-based equality). The user wants this for tests; the catalogue's "tagged union of error variants" pattern depends on it. Confirmed in §3.A test list.
5. **`UnwrapError` is itself an exception** — the substrate is supposed to reduce exception use, but `unwrap()` reintroduces one at the boundary. The catalogue must document that `unwrap()` belongs at boundaries (CLI handlers, top-level request paths, test code) and `match` is the in-flow consumption idiom.

## 9. Success criteria

- All three artefacts ship in one PR. Diff < 700 LOC.
- `dazzle.result` tests pass standalone; `Ok`, `Err`, `Result`, `UnwrapError` importable from `dazzle` top-level.
- Counter-prior entry valid per round-1 drift test schema; frontmatter declares `PA-LLM-09`.
- `PA-LLM-09` heuristic + ~14 tests pass; bidirectional drift test stays green after all three artefacts land.
- Smoke-test on 14 example apps returns zero PA-LLM-09 findings (own dogfood is clean).
- CHANGELOG entry under `[0.77.0]` documents the library + catalogue + heuristic with Agent Guidance bullets.
- pytest (excluding pre-existing flaky #1265), ruff, mypy, mkdocs --strict all clean.

The slice succeeds when an LLM agent prompted to "write a parse function that might fail multiple ways" emits `Result[Event, ParseError]` with a tagged error union instead of `Event | None` — because the bootstrap briefing surfaces `optional-instead-of-result` from the catalogue, the convention library is one import away, and PA-LLM-09 catches it if the agent reverts to the corpus default anyway.
