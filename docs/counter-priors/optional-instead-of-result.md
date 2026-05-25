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
