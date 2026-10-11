# Substrate Round 3: `dazzle.result` + `PA-LLM-09` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Layer 2 of the substrate — a `dazzle.result` convention library (Ok/Err/Result) + `optional-instead-of-result` counter-prior catalogue entry + `PA-LLM-09` Sentinel heuristic — so agents have a real "right shape" for multi-failure-mode functions instead of reaching for `T | None`.

**Architecture:** Three sequential commits in one branch. Library first (testable in isolation), catalogue second (drift test goes red because heuristic doesn't exist yet — intended forcing function), heuristic third (drift returns to green). Single squash-merged PR.

**Tech Stack:** Python 3.12+, `@dataclass(frozen=True, slots=True)` for Ok/Err, PEP 695 generics syntax (`Ok[T]`, `type Result[T, E] = ...`), `ast` stdlib for detection, pytest. No new dependencies.

**Source spec:** `docs/superpowers/specs/2026-05-25-substrate-round-3-result-design.md`.

**Hard scope limit:** cumulative diff must stay under 700 LOC. If a task pushes the total over, stop and re-scope.

---

## File structure

### Create

| Path | Responsibility |
|---|---|
| `src/dazzle/result.py` | `Ok[T]`, `Err[E]`, `type Result[T, E] = Ok[T] \| Err[E]`, `UnwrapError`. Frozen dataclasses with slots. 4 methods per type (`unwrap`, `unwrap_or`, `is_ok`, `is_err`). ~80 LOC. |
| `tests/unit/test_result.py` | 13 tests covering construction, methods, match-pattern consumption, equality, frozen-ness, UnwrapError shape. ~120 LOC. |
| `docs/counter-priors/optional-instead-of-result.md` | New counter-prior. Four mandatory sections + frontmatter declaring `PA-LLM-09`. ~95 LOC. |
| `tests/unit/test_python_audit_optional_instead_of_result.py` | 14 tests for `PA-LLM-09`. ~150 LOC. |

### Modify

| Path | Change |
|---|---|
| `src/dazzle/__init__.py` | Add `from .result import Err, Ok, Result, UnwrapError` and four entries to `__all__`. |
| `src/dazzle/mcp/knowledge_graph/seed.py` | Bump `SEED_SCHEMA_VERSION` by 1 (17 → 18). |
| `src/dazzle/sentinel/agents/python_audit.py` | Add module-level helpers `_returns_optional_t`, `_is_none_constant`, `_count_return_none`, `_has_multi_exception_catch_returning_none`, `_detect_optional_instead_of_result`. Add `@heuristic check_optional_instead_of_result` method on `PythonAuditAgent`. ~120 LOC. |
| `CHANGELOG.md` | Add `## [0.77.0]` section with Added + Agent Guidance bullets. |
| Version files (5 lines, via `/bump minor`) | `pyproject.toml`, `core.toml`, `CLAUDE.md`, `ROADMAP.md`, `homebrew/dazzle.rb`. |

**Bidirectional drift test reuses round-1 infrastructure.** No test additions needed beyond the unit tests above.

---

## Task 1: `dazzle.result` library

Frozen-dataclass Ok/Err with PEP 695 generics, four methods each, `UnwrapError` exception. Public re-export. Standalone — no dependency on the catalogue or heuristic.

**Files:**
- Create: `src/dazzle/result.py`
- Create: `tests/unit/test_result.py`
- Modify: `src/dazzle/__init__.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_result.py`:

```python
"""Tests for dazzle.result — Ok / Err / Result / UnwrapError."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from dazzle.result import Err, Ok, Result, UnwrapError


# ---------------------------------------------------------------------------
# Construction + field access
# ---------------------------------------------------------------------------


def test_ok_carries_value() -> None:
    assert Ok(42).value == 42


def test_err_carries_error() -> None:
    assert Err("oops").error == "oops"


# ---------------------------------------------------------------------------
# unwrap / unwrap_or
# ---------------------------------------------------------------------------


def test_ok_unwrap_returns_value() -> None:
    assert Ok(7).unwrap() == 7


def test_err_unwrap_raises_unwrap_error() -> None:
    e = Err("boom")
    with pytest.raises(UnwrapError) as exc_info:
        e.unwrap()
    assert exc_info.value.error == "boom"


def test_ok_unwrap_or_returns_value_default_unused() -> None:
    # Default is unused for Ok — Ok preserves its own value.
    assert Ok(1).unwrap_or(99) == 1


def test_err_unwrap_or_returns_default() -> None:
    assert Err("boom").unwrap_or(99) == 99


# ---------------------------------------------------------------------------
# is_ok / is_err
# ---------------------------------------------------------------------------


def test_ok_is_ok_true_is_err_false() -> None:
    o = Ok(1)
    assert o.is_ok() is True
    assert o.is_err() is False


def test_err_is_ok_false_is_err_true() -> None:
    e = Err("x")
    assert e.is_ok() is False
    assert e.is_err() is True


# ---------------------------------------------------------------------------
# Match-pattern consumption
# ---------------------------------------------------------------------------


def test_match_pattern_ok_branch() -> None:
    match Ok(7):
        case Ok(value):
            assert value == 7
        case Err(_):
            pytest.fail("matched Err for Ok input")


def test_match_pattern_err_branch() -> None:
    match Err("nope"):
        case Ok(_):
            pytest.fail("matched Ok for Err input")
        case Err(error):
            assert error == "nope"


# ---------------------------------------------------------------------------
# Equality + identity
# ---------------------------------------------------------------------------


def test_ok_and_err_not_equal_across_types() -> None:
    # dataclass(eq=True) is default; Ok and Err have different classes
    # so cross-type comparison is always False even if inner values match.
    assert Ok(1) != Err(1)
    assert Err(1) != Ok(1)


def test_ok_value_equality() -> None:
    assert Ok(1) == Ok(1)
    assert Ok(1) != Ok(2)


# ---------------------------------------------------------------------------
# Frozen + slots
# ---------------------------------------------------------------------------


def test_frozen_assignment_raises() -> None:
    o = Ok(1)
    with pytest.raises(FrozenInstanceError):
        o.value = 2  # type: ignore[misc]


def test_slots_no_dict() -> None:
    # slots=True means no __dict__ — accessing it raises AttributeError.
    with pytest.raises(AttributeError):
        Ok(1).__dict__  # noqa: B018 — intentionally accessing for the side effect


# ---------------------------------------------------------------------------
# Public re-export surface
# ---------------------------------------------------------------------------


def test_public_imports_from_dazzle_root() -> None:
    """Ok, Err, Result, UnwrapError are importable from `dazzle` top-level."""
    from dazzle import Err as RootErr
    from dazzle import Ok as RootOk
    from dazzle import Result as RootResult
    from dazzle import UnwrapError as RootUnwrapError

    assert RootOk is Ok
    assert RootErr is Err
    assert RootResult is Result
    assert RootUnwrapError is UnwrapError
```

- [ ] **Step 2: Run the failing tests**

Run: `cd /Volumes/SSD/Dazzle && pytest tests/unit/test_result.py -v`
Expected: FAIL — `dazzle.result` module doesn't exist.

- [ ] **Step 3: Create the library module**

Create `src/dazzle/result.py`:

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

- [ ] **Step 4: Wire up the public re-export**

Modify `src/dazzle/__init__.py`. The current shape (verified) is:

```python
from ._version import get_version as _get_version

from .core import ir
from .core.errors import BackendError, DazzleError, LinkError, ParseError, ValidationError

__version__ = _get_version()

__all__ = [
    "__version__",
    "ir",
    "DazzleError",
    "ParseError",
    "LinkError",
    "ValidationError",
    "BackendError",
]
```

Add the new import line after the `.core.errors` import:

```python
from .result import Err, Ok, Result, UnwrapError
```

And extend `__all__`:

```python
__all__ = [
    "__version__",
    "ir",
    "DazzleError",
    "ParseError",
    "LinkError",
    "ValidationError",
    "BackendError",
    "Ok",
    "Err",
    "Result",
    "UnwrapError",
]
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/unit/test_result.py -v`
Expected: PASS on all 13 tests.

- [ ] **Step 6: Type-check the library**

Run: `mypy src/dazzle/result.py`
Expected: no errors. Specifically verify that:
- `Result[int, str]` type-checks as the union of `Ok[int]` and `Err[str]`.
- PEP 695 method-local generics (`unwrap_or[T2]`) don't trip mypy.

If mypy reports `error: PEP 695 generics not yet supported`, your mypy version is too old — Dazzle targets mypy with PEP 695 support. Check `pyproject.toml` for the mypy version pin; bump if needed.

- [ ] **Step 7: Run the wider sentinel/audit suite to confirm no regressions**

Run: `pytest tests/ -m "not e2e" -k "sentinel or python_audit or result"`
Expected: PASS. Existing sentinel suite (455 from round 2.5) plus the new 13 result tests.

- [ ] **Step 8: Commit**

```bash
git add src/dazzle/result.py src/dazzle/__init__.py tests/unit/test_result.py
git commit -m "Add dazzle.result: Ok/Err/Result tagged-union substrate

First piece of Layer 2 of the agent code quality substrate. Frozen
dataclasses with slots, four methods per type (unwrap, unwrap_or,
is_ok, is_err), Result[T, E] as PEP 695 type alias for Ok[T] | Err[E].
UnwrapError carries the wrapped error for inspection after Err.unwrap().

Public re-export from dazzle top-level. Match is the canonical
consumption idiom; the methods cover common single-branch checks."
```

---

## Task 2: Counter-prior catalogue entry (deliberately fails drift)

Adds the counter-prior at `docs/counter-priors/optional-instead-of-result.md` declaring `PA-LLM-09` in its `detectors:` frontmatter. The round-1 bidirectional drift test (`test_every_declared_detector_resolves`) will FAIL on this commit because `PA-LLM-09` doesn't exist yet on `PythonAuditAgent`. That's intentional — it's the forcing function for completing the slice. Task 3 closes the drift gap.

**Files:**
- Create: `docs/counter-priors/optional-instead-of-result.md`
- Modify: `src/dazzle/mcp/knowledge_graph/seed.py`

- [ ] **Step 1: Verify current drift state is green**

Before adding the new entry, confirm baseline:

```bash
cd /Volumes/SSD/Dazzle
pytest tests/unit/test_counter_priors_drift.py -v
```

Expected: PASS (all 38+ tests, no PA-LLM-09 references yet).

- [ ] **Step 2: Create the catalogue entry**

Create `docs/counter-priors/optional-instead-of-result.md`:

````markdown
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

# Optional[T] where Result[T, E] would distinguish failure modes

## The corpus prior

Tutorials and Stack Overflow code overwhelmingly model failure as `None`. "What if the user doesn't exist?" → return None. "What if the JSON is malformed?" → return None. "What if the schema is wrong?" → return None. The corpus contains thousands of examples of `def f(x) -> Foo | None:` with the body collapsing every distinct failure into a `return None`.

The pattern compounds because once a function returns `T | None`, the next agent extending it adds another failure path the cheapest way available: another `return None`. The caller's downstream type narrowing then has no way to distinguish *why* the value is None.

The shape arrives in agent-generated code because the corpus's bias for `Optional[T]` is overwhelming, and the agent's job is "make this function compile and return something sensible." `None` is the cheapest sensible return — even when the failure carries information the caller would want.

## Wrong shape

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

Three distinct failure modes — empty input, parse failure, schema violation — all collapsed into the same `None`. Caller code:

```python
event = parse_event(text)
if event is None:
    # which failure was it? We can't tell. Log generically and hope.
    log.warning("parse_event failed for input of length %d", len(text))
```

The caller cannot log "parse failed at line X" vs "empty input" vs "schema validation failed because the `created_at` field is missing." All three are erased into indistinguishable `None`.

## Right shape

Use `Result[Event, ParseError]` with a tagged error union:

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
        return Err(SchemaViolation(field=str(first["loc"][0]), detail=first["msg"]))
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
- Don't use plain strings as error tokens — `Err("not found")` defeats the type-distinction purpose. Use a frozen dataclass even if empty (it's the variant *name* that carries semantic content).

**When `T | None` is genuinely fine:**

The catalogue isn't anti-Optional — Optional has a real use. `T | None` is correct when there's exactly **one** failure mode that the caller never needs to distinguish from another. Examples: `dict.get(k)` returning None for "key not found" (the only possible outcome); a cache lookup returning None for "miss" (the only outcome). The wrong shape emerges when two-or-more failure modes get folded into the same None.

## Why this matters here

Dazzle's framework code paths already practise this discipline (the IR's `LinkError` / `ValidationError` / `ParseError` hierarchy is the framework-layer equivalent — distinct error types, not all collapsed into None). User-app code in `app/` doesn't yet have an idiomatic answer, so agents reach for the corpus default: `T | None`.

`PA-LLM-09` flags the wrong shape at scan time. `dazzle.result` makes the right shape one import away. The catalogue bridges the gap at inference time — `bootstrap` and `knowledge counter_prior` surface this entry when an agent is about to write a multi-failure-mode function.

`unwrap()` deliberately re-introduces an exception (`UnwrapError`). That's by design — `unwrap()` belongs at clearly designated boundaries (CLI entry points, top-level request handlers, test code), not at the inflow consumption point. Inside business logic, the `match` form is the idiom. The catalogue's boundary advice complements the library's safety: the library makes the wrong usage *possible*; the catalogue makes the right usage *obvious*.
````

- [ ] **Step 3: Bump KG seed schema version**

Find the constant:

```bash
grep -n "SEED_SCHEMA_VERSION" /Volumes/SSD/Dazzle/src/dazzle/mcp/knowledge_graph/seed.py
```

Round 2 bumped 16 → 17. Bump 17 → 18.

- [ ] **Step 4: Confirm catalogue-only drift tests pass**

```bash
pytest tests/unit/test_counter_priors_drift.py -v -k "not pa_llm_07 and not exceptions_entry"
```

Expected: PASS on the schema-only tests (entry parses, has required sections, INDEX.md membership, regex validity). The bidirectional-resolver tests for the new PA-LLM-09 declaration WILL FAIL — that's expected and intended. The next step verifies the expected red.

- [ ] **Step 5: Verify the bidirectional drift fails as expected**

```bash
pytest tests/unit/test_counter_priors_drift.py::test_every_declared_detector_resolves -v
```

Expected: FAIL with a message like "declared detector 'PA-LLM-09' not found on PythonAuditAgent". This is the forcing function — Task 3 closes it.

- [ ] **Step 6: Update INDEX.md**

Open `docs/counter-priors/INDEX.md`. Find the "Active entries" alphabetical list (it lists existing entries like `domain-coupled-keywords`, `duplicated-parent-fields`, etc.). Add a new entry in alphabetical position:

```markdown
- [optional-instead-of-result](optional-instead-of-result.md) — `def f(...) -> T | None` collapsing multiple distinct failure modes into a single None sentinel. Pairs with `dazzle.result` and `PA-LLM-09`.
```

Slot it alphabetically between `n-plus-one-in-user-code` and `polymorphic-associations`.

- [ ] **Step 7: Re-run the index-membership check**

```bash
pytest tests/unit/test_counter_priors_drift.py::test_index_lists_every_entry -v
```

Expected: PASS — INDEX.md now references `optional-instead-of-result.md`.

- [ ] **Step 8: Commit**

```bash
git add docs/counter-priors/optional-instead-of-result.md \
        docs/counter-priors/INDEX.md \
        src/dazzle/mcp/knowledge_graph/seed.py
git commit -m "Add optional-instead-of-result counter-prior (PA-LLM-09 pending)

Catalogue entry documents the antipattern of collapsing multiple
distinct failure modes into a single None sentinel and the right
shape using dazzle.result + a tagged error union. KG seed bumped
17 → 18. The frontmatter declares detector PA-LLM-09 which is added
in the next commit (drift test fails intentionally between commits)."
```

---

## Task 3: `PA-LLM-09` heuristic (closes the drift gap)

Detects functions returning `T | None` (or `Optional[T]`) with multiple `return None` statements or a multi-exception-catch returning None. Closes the bidirectional drift the previous task deliberately opened.

**Files:**
- Modify: `src/dazzle/sentinel/agents/python_audit.py`
- Create: `tests/unit/test_python_audit_optional_instead_of_result.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_python_audit_optional_instead_of_result.py`:

```python
"""Tests for PA-LLM-09 — optional-instead-of-result."""

from __future__ import annotations

import ast
from pathlib import Path

from dazzle.sentinel.agents.python_audit import (
    PythonAuditAgent,
    _detect_optional_instead_of_result,
)


def _parse(src: str) -> ast.Module:
    return ast.parse(src)


# ---------------------------------------------------------------------------
# Positive: multiple return None
# ---------------------------------------------------------------------------


def test_two_return_none_fires() -> None:
    src = (
        "def parse(text: str) -> int | None:\n"
        "    if not text:\n"
        "        return None\n"
        "    if text.isspace():\n"
        "        return None\n"
        "    return int(text)\n"
    )
    hits = _detect_optional_instead_of_result(_parse(src), Path("app/x.py"))
    assert len(hits) == 1
    assert hits[0].shape == "multi_return_none"


def test_three_return_none_fires_once() -> None:
    """Multiple return None statements yield one finding, not three."""
    src = (
        "def f(x) -> str | None:\n"
        "    if not x: return None\n"
        "    if x < 0: return None\n"
        "    if x > 100: return None\n"
        "    return str(x)\n"
    )
    hits = _detect_optional_instead_of_result(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_optional_legacy_syntax() -> None:
    src = (
        "from typing import Optional\n"
        "def f(x) -> Optional[int]:\n"
        "    if x is None: return None\n"
        "    if x < 0: return None\n"
        "    return x\n"
    )
    hits = _detect_optional_instead_of_result(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_pipe_none_left_position() -> None:
    """`None | int` (None on the left) is the same union as `int | None`."""
    src = (
        "def f(x) -> None | int:\n"
        "    if x == 0: return None\n"
        "    if x < 0: return None\n"
        "    return x\n"
    )
    hits = _detect_optional_instead_of_result(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_bare_return_counts_as_none() -> None:
    """A bare `return` (no value) is equivalent to `return None`."""
    src = (
        "def f(x) -> int | None:\n"
        "    if x == 0: return\n"
        "    if x < 0: return None\n"
        "    return x\n"
    )
    hits = _detect_optional_instead_of_result(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_async_function_fires() -> None:
    src = (
        "async def fetch(uid) -> int | None:\n"
        "    if not uid: return None\n"
        "    if uid < 0: return None\n"
        "    return await load(uid)\n"
    )
    hits = _detect_optional_instead_of_result(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


# ---------------------------------------------------------------------------
# Positive: multi-exception catch
# ---------------------------------------------------------------------------


def test_multi_exception_catch_fires() -> None:
    """Single return None but except (X, Y) catching ≥2 types fires."""
    src = (
        "def parse(text) -> int | None:\n"
        "    try:\n"
        "        return int(text)\n"
        "    except (ValueError, TypeError):\n"
        "        return None\n"
    )
    hits = _detect_optional_instead_of_result(_parse(src), Path("app/x.py"))
    assert len(hits) == 1
    assert hits[0].shape == "multi_exception_catch"


# ---------------------------------------------------------------------------
# Negative: false-positive guards
# ---------------------------------------------------------------------------


def test_negative_single_return_none() -> None:
    """Single failure mode is legitimate Optional usage — no fire."""
    src = (
        "def find_user(uid) -> User | None:\n"
        "    if uid not in users: return None\n"
        "    return users[uid]\n"
    )
    assert _detect_optional_instead_of_result(_parse(src), Path("app/x.py")) == []


def test_negative_no_optional_return() -> None:
    """Function returns int (not int | None) — out of scope even with two return None."""
    src = (
        "def f(x) -> int:\n"
        "    if x == 0: return None\n"
        "    if x < 0: return None\n"
        "    return x\n"
    )
    # The signature isn't `T | None` so PA-LLM-09 doesn't apply.
    # (mypy would catch the actual type bug separately.)
    assert _detect_optional_instead_of_result(_parse(src), Path("app/x.py")) == []


def test_negative_nested_function_returns_dont_count() -> None:
    """`return None` inside a nested def doesn't contribute to the outer count."""
    src = (
        "def outer(x) -> int | None:\n"
        "    def inner():\n"
        "        if x == 0: return None\n"
        "        if x < 0: return None\n"
        "        return x\n"
        "    return inner() if x else None\n"
    )
    # Outer has only one return None (the last line). Inner has two but is a separate scope.
    assert _detect_optional_instead_of_result(_parse(src), Path("app/x.py")) == []


def test_negative_single_exception_catch() -> None:
    """`except KeyError: return None` (one type only) doesn't fire."""
    src = (
        "def get(d, k) -> int | None:\n"
        "    try:\n"
        "        return d[k]\n"
        "    except KeyError:\n"
        "        return None\n"
    )
    assert _detect_optional_instead_of_result(_parse(src), Path("app/x.py")) == []


def test_negative_no_return_annotation() -> None:
    """Function without return annotation doesn't fire (we can't tell intent)."""
    src = (
        "def f(x):\n"
        "    if x: return None\n"
        "    return None\n"
    )
    assert _detect_optional_instead_of_result(_parse(src), Path("app/x.py")) == []


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------


def test_noqa_suppression_on_def(tmp_path: Path) -> None:
    """`# noqa: PA-LLM-09` on the def line suppresses the finding."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "x.py").write_text(
        "def lookup(k) -> int | None:  # noqa: PA-LLM-09 - both Nones mean 'miss'\n"
        "    if not k: return None\n"
        "    if k not in cache: return None\n"
        "    return cache[k]\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_optional_instead_of_result(appspec=None) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------


def test_heuristic_yields_finding_with_catalogue_entry(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "parse.py").write_text(
        "def parse(text: str) -> int | None:\n"
        "    if not text: return None\n"
        "    if text.isspace(): return None\n"
        "    return int(text)\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_optional_instead_of_result(appspec=None)  # type: ignore[arg-type]
    assert len(findings) == 1
    f = findings[0]
    assert f.heuristic_id == "PA-LLM-09"
    assert f.catalogue_entry == "optional-instead-of-result"
    assert f.remediation is not None
    assert any(
        "docs/counter-priors/optional-instead-of-result.md" in ref
        for ref in f.remediation.references
    )


def test_heuristic_skips_tests_and_scripts(tmp_path: Path) -> None:
    for sub in ("tests", "scripts"):
        d = tmp_path / sub
        d.mkdir()
        (d / "f.py").write_text(
            "def f(x) -> int | None:\n"
            "    if not x: return None\n"
            "    if x < 0: return None\n"
            "    return x\n"
        )
    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_optional_instead_of_result(appspec=None) == []  # type: ignore[arg-type]
```

- [ ] **Step 2: Run the failing tests**

Run: `pytest tests/unit/test_python_audit_optional_instead_of_result.py -v`
Expected: FAIL — `_detect_optional_instead_of_result` and `check_optional_instead_of_result` don't exist yet.

- [ ] **Step 3: Add the helpers + detector**

Modify `src/dazzle/sentinel/agents/python_audit.py`. After the PA-LLM-08 helpers section (around line 400 in the post-round-2.5 file — look for the last `_shape_hits_in_body` function), add a new section:

```python
# ---------------------------------------------------------------------------
# PA-LLM-09 helpers — optional-instead-of-result
# ---------------------------------------------------------------------------


def _is_none_constant(node: ast.AST) -> bool:
    """True if node is the literal `None`."""
    return isinstance(node, ast.Constant) and node.value is None


def _returns_optional_t(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True if the function's return annotation is `T | None` or `Optional[T]`.

    Recognises both PEP 604 (`X | None`) and `typing.Optional[X]` (legacy).
    """
    rt = fn.returns
    if rt is None:
        return False
    # X | None or None | X (BinOp with BitOr operator)
    if isinstance(rt, ast.BinOp) and isinstance(rt.op, ast.BitOr):
        return _is_none_constant(rt.left) or _is_none_constant(rt.right)
    # Optional[X]
    if isinstance(rt, ast.Subscript) and isinstance(rt.value, ast.Name):
        return rt.value.id == "Optional"
    return False


def _count_return_none(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count `return None` (or bare `return`) statements in fn body.

    Skips nested function definitions (those have their own scope).
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
       `try/except (X, Y, ...)` block returning None.
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
        hits.append(
            _ShapeHit(
                line=node.lineno,
                snippet=f"def {node.name}(...) -> ... | None",
                shape=shape,
                try_line=node.lineno,  # outer fn def line, for noqa scope
            )
        )
    return hits
```

- [ ] **Step 4: Add the `@heuristic` method**

Append to `class PythonAuditAgent` (after `check_n_plus_one_in_user_code` from round 2):

```python
    @heuristic(
        heuristic_id="PA-LLM-09",
        category="python_audit",
        subcategory="llm_bias",
        title="Optional[T] where Result[T, E] would distinguish failure modes",
    )
    def check_optional_instead_of_result(self, appspec: AppSpec) -> list[Finding]:
        """Flag functions that should use Result instead of T | None.

        See docs/counter-priors/optional-instead-of-result.md for the
        full taxonomy and the right shape (dazzle.result + tagged
        ParseError union).
        """
        from dazzle.sentinel.models import (
            Confidence,
            Evidence,
            Finding,
            Remediation,
            RemediationEffort,
            Severity,
        )

        app_dir = self._project_path / "app"
        if not app_dir.exists():
            return []

        catalogue_url = (
            "https://github.com/cyfutureuk/dazzle/blob/main/"
            "docs/counter-priors/optional-instead-of-result.md"
        )

        findings: list[Finding] = []
        for py_file in sorted(app_dir.rglob("*.py")):
            try:
                source_text = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source_text, filename=str(py_file))
            except (SyntaxError, UnicodeDecodeError):
                continue
            source_lines = source_text.splitlines()

            for hit in _detect_optional_instead_of_result(tree, py_file):
                def_line_text = (
                    source_lines[hit.line - 1]
                    if 0 < hit.line <= len(source_lines)
                    else ""
                )
                if "noqa: PA-LLM-09" in def_line_text:
                    continue

                findings.append(
                    Finding(
                        agent=AgentId.PA,
                        heuristic_id="PA-LLM-09",
                        category="python_audit",
                        subcategory="llm_bias",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.LIKELY,
                        title=f"Optional-instead-of-Result ({hit.shape})",
                        description=(
                            f"Function `{hit.snippet}` collapses multiple distinct failure "
                            "modes into None. Use Result[T, E] with a tagged error union "
                            "so the caller can distinguish failure modes."
                        ),
                        evidence=[
                            Evidence(
                                evidence_type="source_pattern",
                                location=f"{py_file}:{hit.line}",
                                snippet=hit.snippet,
                            )
                        ],
                        remediation=Remediation(
                            summary=(
                                "Return `Result[T, ErrorUnion]` from dazzle.result with "
                                "a tagged union of error variants."
                            ),
                            effort=RemediationEffort.MEDIUM,
                            guidance=(
                                "See docs/counter-priors/optional-instead-of-result.md for "
                                "the canonical right-shape pattern using dazzle.result + "
                                "frozen-dataclass error variants."
                            ),
                            references=[catalogue_url],
                        ),
                        catalogue_entry="optional-instead-of-result",
                    )
                )
        return findings
```

- [ ] **Step 5: Run the new tests**

Run: `pytest tests/unit/test_python_audit_optional_instead_of_result.py -v`
Expected: PASS on all 14 tests.

- [ ] **Step 6: Run the drift test — drift should now be GREEN again**

Run: `pytest tests/unit/test_counter_priors_drift.py -v`
Expected: PASS on all tests including `test_every_declared_detector_resolves`. The forcing-function red opened in Task 2 is now closed.

- [ ] **Step 7: Wider sentinel/audit suite**

Run: `pytest tests/ -m "not e2e" -k "sentinel or python_audit or result"`
Expected: PASS — round 2's 455 + round 3 library (13) + round 3 heuristic (14) ≈ 482 passed.

- [ ] **Step 8: Smoke-test against examples**

```bash
cd /Volumes/SSD/Dazzle
for dir in examples/*/; do
  if [ -f "$dir/dazzle.toml" ]; then
    name=$(basename "$dir")
    cd "$dir" && hits=$(dazzle sentinel scan --agent PA --severity medium 2>&1 | grep -c "PA-LLM-09")
    cd /Volumes/SSD/Dazzle
    echo "$name: $hits"
  fi
done
```

Expected: every example reports `0`. If any fire, classify and either fix the example or tighten the detector (with a regression test for the false positive).

- [ ] **Step 9: Commit**

```bash
git add src/dazzle/sentinel/agents/python_audit.py \
        tests/unit/test_python_audit_optional_instead_of_result.py
git commit -m "Add PA-LLM-09: optional-instead-of-result heuristic

Fires on functions whose signature returns T | None (or Optional[T])
with multiple distinct return None statements OR a try/except
catching ≥2 exception types returning None. Recommends migrating
to dazzle.result with a tagged error union.

Closes the drift opened by the prior commit — PA-LLM-09 declared in
the catalogue frontmatter now resolves to a real heuristic on
PythonAuditAgent."
```

---

## Task 4: CHANGELOG + bump + ship

**Files:**
- Modify: `CHANGELOG.md`
- Modify (via `/bump minor`): `pyproject.toml`, `core.toml`, `CLAUDE.md`, `ROADMAP.md`, `homebrew/dazzle.rb`

- [ ] **Step 1: Update CHANGELOG**

Open `/Volumes/SSD/Dazzle/CHANGELOG.md`. Find the `## [Unreleased]` line. Insert a new dated heading immediately AFTER `## [Unreleased]` and BEFORE the existing `## [0.76.1] - 2026-05-25` heading. Use today's date.

```markdown
## [0.77.0] - 2026-05-26

### Added — agent code quality substrate round 3 (Layer 2: dazzle.result + PA-LLM-09)

- **`dazzle.result`** — new convention library shipping `Ok[T]`, `Err[E]`, `type Result[T, E] = Ok[T] | Err[E]`, and `UnwrapError`. Frozen dataclasses with slots, PEP 695 method-local generics. Four methods per type (`unwrap`, `unwrap_or`, `is_ok`, `is_err`); match is the canonical composition idiom. Importable from `dazzle` top-level.
- **`docs/counter-priors/optional-instead-of-result.md`** — new counter-prior documenting the antipattern of collapsing multiple distinct failure modes into a single `None` sentinel. Frontmatter declares PA-LLM-09. The "right shape" section shows the canonical pattern: `Result[T, ParseError]` with a tagged union of frozen-dataclass error variants.
- **Sentinel heuristic `PA-LLM-09`** (`optional_instead_of_result`) fires on `def f(...) -> T | None` (or `Optional[T]`) with ≥2 distinct `return None` statements OR a `try/except (X, Y, ...)` block returning None. Severity MEDIUM, confidence LIKELY. Suppress via `# noqa: PA-LLM-09 — <reason>` on the `def` line for legitimate single-failure-mode Optionals (find-or-None patterns).

### Agent Guidance

- When a function might fail in **two or more distinguishable ways**, return `Result[T, ErrorUnion]` from `dazzle.result`. Use `@dataclass(frozen=True, slots=True)` for error variants and `type ErrorUnion = X | Y | Z` (PEP 695) for the tagged union. The caller's `match` becomes exhaustive — type checker enforces every variant is handled.
- `T | None` remains correct for **single-failure-mode** Optionals (a cache lookup whose only outcome is "miss"; a `dict.get(k)` clone whose only outcome is "key absent"). The antipattern is collapsing distinct failure modes into the same `None`.
- `.unwrap()` belongs at boundaries (CLI entry points, top-level request handlers, test code). Inside business logic, `match` is the idiom. Calling `.unwrap()` on an `Err` re-raises as `UnwrapError` carrying the wrapped error.
- Layer 2 of the substrate now exists. Future rounds may add `dazzle.types` (branded NewType helpers countering the `magic-string-typing` gap) — `dazzle.result` is the first Layer-2 primitive.
```

- [ ] **Step 2: Run the full pre-ship gate**

Run each in order; stop and report BLOCKED if any fail (except the known pre-existing flaky `test_propose_patterns_1249` — see #1265):

```bash
cd /Volumes/SSD/Dazzle
pytest tests/ -m "not e2e" --deselect tests/unit/test_propose_patterns_1249.py 2>&1 | tail -5
ruff check src/ tests/ --fix 2>&1 | tail -3
ruff format src/ tests/ 2>&1 | tail -3
mypy src/dazzle 2>&1 | tail -3
mkdocs build --strict 2>&1 | tail -5
```

Expected: pytest green (substrate-round-3 brings the suite to ~16215 + the new tests; deselect the known-flaky file), ruff clean, mypy clean, mkdocs strict clean.

- [ ] **Step 3: Commit CHANGELOG**

```bash
git add CHANGELOG.md
git commit -m "Document substrate round 3 in CHANGELOG under [0.77.0]"
```

- [ ] **Step 4: Bump version**

Run `/bump minor` in the Claude session (controller skill invocation; subagent doesn't run this).

Expected: bumps `0.76.1 → 0.77.0` across all 6 lines (pyproject.toml, core.toml, CLAUDE.md, ROADMAP.md, two lines in homebrew/dazzle.rb).

- [ ] **Step 5: Commit version bump**

```bash
git status   # verify only the 5 version files changed
git add pyproject.toml src/dazzle/mcp/semantics_kb/core.toml \
        .claude/CLAUDE.md ROADMAP.md homebrew/dazzle.rb
git commit -m "Release v0.77.0: dazzle.result + PA-LLM-09 (substrate round 3)

Layer 2 of the substrate ships. First non-detector substrate piece —
dazzle.result is the first 'right shape' the substrate provides
rather than the wrong shape it forbids. PA-LLM-09 catches user code
that reached for T | None when Result was the answer."
```

- [ ] **Step 6: Verify diff stays under the scope ceiling**

```bash
git diff main...HEAD --stat
```

Expected: cumulative diff < 700 LOC. The spec estimated ~597. If you've crept past 700, the design is leaking — flag it before pushing.

- [ ] **Step 7: Push branch + open PR**

```bash
git push -u origin feature/pa-llm-09-optional-instead-of-result
gh pr create --title "Substrate round 3: dazzle.result + PA-LLM-09 (optional-instead-of-result) — v0.77.0" --body "$(cat <<'EOF'
## Summary

Round 3 of the agent code quality substrate. **First Layer-2 ship** — Layer 3 (filter) was the entire substrate so far; this round adds the first piece of Layer 2 (convention library / inference-time substrate).

- **`dazzle.result`** convention library: `Ok[T]`, `Err[E]`, `type Result[T, E] = Ok[T] | Err[E]`, `UnwrapError`. Frozen dataclasses with slots. 4 methods per type. Public from `dazzle` top-level.
- **`optional-instead-of-result.md`** counter-prior documenting the antipattern of collapsing multiple failure modes into None, with the canonical right-shape pattern using dazzle.result + tagged error union.
- **`PA-LLM-09`** Sentinel heuristic detecting the wrong shape in user `app/` Python: `T | None` returns with ≥2 distinct `return None` OR multi-exception-catch returning None.

Implements `docs/superpowers/specs/2026-05-25-substrate-round-3-result-design.md`.

## Test plan

- [x] `pytest tests/unit/test_result.py -v` — 13 passed
- [x] `pytest tests/unit/test_python_audit_optional_instead_of_result.py -v` — 14 passed
- [x] `pytest tests/unit/test_counter_priors_drift.py -v` — drift back to green after task 3
- [x] `pytest tests/ -m "not e2e" --deselect tests/unit/test_propose_patterns_1249.py` — clean except known #1265
- [x] `ruff check && ruff format` — clean
- [x] `mypy src/dazzle` — clean
- [x] `mkdocs build --strict` — clean
- [x] Smoke-test: 14 example apps, 0 PA-LLM-09 findings

## Scope discipline

Cumulative diff under 700 LOC (target was ~597 per spec).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes

**Spec coverage:**
- §3.A library (Ok/Err/Result/UnwrapError + 4 methods + public re-export) → Task 1.
- §3.B catalogue entry (4 mandatory sections + frontmatter detectors:) → Task 2.
- §3.C detector (5 module helpers + `@heuristic` method + 14 tests) → Task 3.
- §4 data flow → covered by Task 3's heuristic implementation (catalogue_entry, remediation.references).
- §5 suppression → covered by Task 3 (`# noqa: PA-LLM-09` on def line).
- §6 scope discipline (700 LOC ceiling) → enforced in Task 4 Step 6.
- §7 implementation order (sequential 3 commits with intentional intermediate red drift) → preserved verbatim.
- §8 risks (single-failure-mode FP, type-comments, overloads) → documented in CHANGELOG Agent Guidance section.
- §9 success criteria → checked by Task 4 Step 2 (full pre-ship gate).

**Placeholder scan:** clean. No TBDs. Today's date in CHANGELOG is `2026-05-26` (explicit replacement instruction in Task 4 Step 1).

**Type consistency:**
- `Ok`, `Err`, `Result`, `UnwrapError` declared in Task 1 Step 3, imported in Task 1 Step 1 (tests) and Task 1 Step 4 (public re-export). Catalogue entry (Task 2 Step 2) references them by exact name in the right-shape section.
- `_returns_optional_t`, `_count_return_none`, `_has_multi_exception_catch_returning_none`, `_detect_optional_instead_of_result` declared in Task 3 Step 3, used in Task 3 Step 1 (tests) and Task 3 Step 4 (heuristic method).
- `_ShapeHit` reused from rounds 1 & 2 (same `try_line` carrying the outer-statement line — here, the function `def` line).

**Ambiguity:** PEP 695 generics syntax is mature in Python 3.12+ and ships natively. Spec ambiguity around `Err.unwrap_or[T2]` (method-local generic) is resolved by the docstring in Task 1 Step 3.

**Intentional red drift between tasks 2 and 3:** documented in Task 2's commit message AND in the implementation order — the engineer should not panic when `test_every_declared_detector_resolves` fails after Task 2. Task 3 closes it.
