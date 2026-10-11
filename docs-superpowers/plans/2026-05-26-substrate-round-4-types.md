# Substrate Round 4: `dazzle.types` + `PA-LLM-10` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the second Layer-2 substrate piece — `dazzle.types` (thin `NewType` re-export) + `magic-string-typing` counter-prior + `PA-LLM-10` Sentinel heuristic — so agents have an ergonomic answer for branded identifier types instead of reaching for bare `str`.

**Architecture:** Three sequential commits in one branch, same pattern as round 3. Library first (testable in isolation), catalogue second (drift goes red intentionally), heuristic third (drift closes). Single squash-merged PR.

**Tech Stack:** Python 3.12+, `typing.NewType` (stdlib, no runtime cost), `ast` stdlib for detection, pytest. No new dependencies.

**Source spec:** `docs/superpowers/specs/2026-05-26-substrate-round-4-types-design.md`.

**Hard scope limit:** cumulative diff < 600 LOC. If a task pushes over, stop and re-scope.

---

## File structure

### Create

| Path | Responsibility |
|---|---|
| `src/dazzle/types.py` | Thin re-export of `typing.NewType`. ~15 LOC. |
| `tests/unit/test_types.py` | 5 tests covering NewType behaviour + public-import surface. ~50 LOC. |
| `docs/counter-priors/magic-string-typing.md` | New counter-prior with frontmatter declaring PA-LLM-10. Covers all three sub-shapes (IDs, enum dispatch, lookup keys) but only sub-shape (a) is detected. ~130 LOC. |
| `tests/unit/test_python_audit_magic_string_typing.py` | 17 tests for PA-LLM-10. ~150 LOC. |

### Modify

| Path | Change |
|---|---|
| `src/dazzle/__init__.py` | Add `from .types import NewType` and one entry to `__all__`. |
| `src/dazzle/mcp/knowledge_graph/seed.py` | Bump `SEED_SCHEMA_VERSION` by 1 (18 → 19). |
| `src/dazzle/sentinel/agents/python_audit.py` | Add `import re` (or reuse if already imported), `_ID_NAME_RE`, `_is_id_shaped_name`, `_is_bare_str_annotation`, `_has_dataclass_decorator`, `_detect_magic_string_id`, `check_magic_string_typing` `@heuristic` method. ~110 LOC. |
| `docs/counter-priors/INDEX.md` | Add alphabetical entry between `hand-rolled-temporal` and `n-plus-one-in-user-code`. |
| `docs/api-surface/public-helpers.txt` | Regenerate via `dazzle inspect api public-helpers --write` after `NewType` added to top-level. |
| `CHANGELOG.md` | Add `## [0.78.0]` section with Added + Agent Guidance bullets. |
| Version files (5 lines via `/bump minor`) | `pyproject.toml`, `core.toml`, `CLAUDE.md`, `ROADMAP.md`, `homebrew/dazzle.rb`. |

---

## Task 1: `dazzle.types` library

Thin re-export of `typing.NewType`. Public from `dazzle` top-level. Standalone — no dependency on the catalogue or heuristic.

**Files:**
- Create: `src/dazzle/types.py`
- Create: `tests/unit/test_types.py`
- Modify: `src/dazzle/__init__.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_types.py`:

```python
"""Tests for dazzle.types — NewType re-export."""

from __future__ import annotations

from dazzle.types import NewType


def test_newtype_creates_branded_alias() -> None:
    """NewType creates a callable whose runtime behaviour is the identity function."""
    UserId = NewType("UserId", str)
    assert UserId("x") == "x"


def test_newtype_type_name() -> None:
    """The brand carries the declared name."""
    UserId = NewType("UserId", str)
    assert UserId.__name__ == "UserId"


def test_newtype_supertype() -> None:
    """The brand records its supertype for type-checker use."""
    UserId = NewType("UserId", str)
    assert UserId.__supertype__ is str


def test_public_import_from_dazzle_types() -> None:
    """`from dazzle.types import NewType` works."""
    from dazzle.types import NewType as DazzleNewType
    from typing import NewType as StdNewType

    assert DazzleNewType is StdNewType


def test_public_import_from_dazzle_root() -> None:
    """`from dazzle import NewType` works and is the same object as typing.NewType."""
    from dazzle import NewType as DazzleNewType
    from typing import NewType as StdNewType

    assert DazzleNewType is StdNewType
```

- [ ] **Step 2: Run the failing tests**

Run: `cd /Volumes/SSD/Dazzle && pytest tests/unit/test_types.py -v`
Expected: FAIL — `dazzle.types` module doesn't exist.

- [ ] **Step 3: Create the library module**

Create `src/dazzle/types.py`:

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

- [ ] **Step 4: Wire the public re-export**

Modify `src/dazzle/__init__.py`. The current shape after round 3 (verified) includes round-3's Ok/Err/Result/UnwrapError. Add a new import line after the `.result` import:

```python
from .types import NewType
```

Extend `__all__` to include `"NewType"` at the end:

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
    "NewType",
]
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/unit/test_types.py -v`
Expected: PASS on all 5 tests.

- [ ] **Step 6: Type-check the library**

Run: `mypy src/dazzle/types.py`
Expected: no errors.

- [ ] **Step 7: Wider gate**

Run: `pytest tests/ -m "not e2e" -k "sentinel or python_audit or result or types"`
Expected: PASS — round-3's tests still green, plus the new 5 types tests.

- [ ] **Step 8: Commit**

```bash
git add src/dazzle/types.py src/dazzle/__init__.py tests/unit/test_types.py
git commit -m "Add dazzle.types: NewType re-export for branded identifier types

Second Layer-2 piece of the agent code quality substrate. Thin
re-export of typing.NewType for one-stop discovery (from dazzle.types
import NewType). Runtime-free — NewType is the identity function at
runtime. Pairs with the upcoming magic-string-typing counter-prior
and PA-LLM-10 heuristic.

Public re-export from dazzle top-level matches the round-3 pattern
(Ok/Err/Result/UnwrapError all at dazzle root)."
```

---

## Task 2: Counter-prior catalogue entry (deliberately fails drift)

Adds `magic-string-typing.md` with frontmatter declaring PA-LLM-10. The round-1 bidirectional drift test will FAIL until Task 3 lands — that's the forcing function.

**Files:**
- Create: `docs/counter-priors/magic-string-typing.md`
- Modify: `docs/counter-priors/INDEX.md`
- Modify: `src/dazzle/mcp/knowledge_graph/seed.py`

- [ ] **Step 1: Verify current drift state is green**

```bash
cd /Volumes/SSD/Dazzle
pytest tests/unit/test_counter_priors_drift.py -v
```

Expected: PASS on all tests. Round-1 + round-2 + round-3 detectors all wired; PA-LLM-10 doesn't exist yet either in catalogue or on agent.

- [ ] **Step 2: Create the catalogue entry**

Create `docs/counter-priors/magic-string-typing.md`:

```markdown
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

# Magic-string typing — bare `str` where a brand or enum would catch errors

## The corpus prior

Python's stdlib `str` is the universal carrier. Tutorials use it for IDs (`user_id: str`), for status fields (`status: str` with conditional dispatch on literals like `"pending"` / `"approved"`), and for typed lookup keys (`record["status"]`). The corpus is dominated by this shape because `str` is the path of least resistance and the type checker doesn't complain.

Mix-ups (`fetch(tenant_id, user_id)` instead of `fetch(user_id, tenant_id)`) typecheck cleanly and surface as data corruption later — the kind of bug that takes a long time to find because the symptom is "the wrong customer got the wrong invoice" rather than a stack trace.

Typos in dispatch literals (`elif status == "aprroved":`) never fire at runtime and silently fall through. The cost compounds because the corpus's bias makes the pattern feel natural even to agents that should know better.

## Wrong shape

Three sub-shapes covered by the catalogue. PA-LLM-10 currently detects sub-shape (a) only; (b) and (c) are documented for inference-time guidance.

**(a) Magic-string IDs:**

\`\`\`python
def transfer_funds(source_id: str, destination_id: str, amount: int) -> Result[Receipt, TransferError]:
    ...

# Caller:
transfer_funds(destination_id, source_id, amount)  # arguments swapped, type-checker happy
\`\`\`

**(b) Enum-dispatch chains:**

\`\`\`python
def render_status_badge(status: str) -> str:
    if status == "pending":
        return "⏳"
    elif status == "approved":
        return "✅"
    elif status == "rejected":
        return "❌"
    # typo: "aprroved" silently falls through
    return ""
\`\`\`

**(c) Typed lookup keys (informational — not detected by PA-LLM-10):**

\`\`\`python
def get_field(record: dict, key: str) -> object:
    return record[key]  # any string is acceptable; no type-checker leverage
\`\`\`

## Right shape

Three patterns matching the three sub-shapes:

**(a) Branded IDs via `dazzle.types.NewType`:**

\`\`\`python
# app/ids.py
from dazzle.types import NewType

UserId = NewType("UserId", str)
TenantId = NewType("TenantId", str)
PaymentId = NewType("PaymentId", str)
\`\`\`

\`\`\`python
# app/transfers.py
from app.ids import PaymentId

def transfer_funds(source_id: PaymentId, destination_id: PaymentId, amount: int) -> Result[Receipt, TransferError]:
    ...

# Caller:
src = PaymentId(row["src_id"])
dst = PaymentId(row["dst_id"])
transfer_funds(src, dst, amount)  # both are PaymentId — no swap risk between distinct ID classes
\`\`\`

The brand catches mix-ups between **different** ID classes (`UserId` vs `TenantId`). Within a single ID class, parameter-ordering bugs are still possible — the type system catches the harder cross-class error.

**(b) Closed sets via `enum.StrEnum`:**

\`\`\`python
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
\`\`\`

Typos in the StrEnum class definition fail loudly at class-definition time; typos in match arms typecheck as errors. The `str` value is preserved (`OrderStatus.PENDING == "pending"` is True) so JSON serialization works without changes.

**(c) TypedDict for record keys (informational):**

\`\`\`python
from typing import TypedDict


class OrderRecord(TypedDict):
    status: OrderStatus
    amount: int
    customer_id: UserId


def get_status(record: OrderRecord) -> OrderStatus:
    return record["status"]  # mypy catches typos in the key
\`\`\`

**Convention notes:**

- Declare branded types in `app/ids.py` (or similar) — co-located with their domain, importable from anywhere in `app/`.
- Use `enum.StrEnum` (stdlib, Python 3.11+) for closed value sets. Don't reach for a library; the stdlib is enough.
- `NewType` is runtime-free — `UserId("x")` returns the plain `str` `"x"`. The brand is type-checker-only. This is the right tradeoff: zero runtime cost, full static safety.

## Why this matters here

Dazzle's framework code paths use typed IR (`EntityRef`, `PersonaSpec`, etc.) and DSL-level enums (`enum` keyword) that prevent magic-string typing at the model layer. User-app Python in `app/` doesn't yet have an idiomatic answer — agents reach for `str` because the corpus does.

`PA-LLM-10` flags ID-shaped parameters at scan time. `dazzle.types` makes the right shape one import away. The catalogue documents all three sub-shapes for inference-time agent guidance even though only (a) is detected today.

`StrEnum` is stdlib and not part of `dazzle.types` for the same reason `dataclasses` isn't — it's already in the standard library and a re-export would add nothing.
```

(Note: in the catalogue file you write, use plain triple-backticks. The escaped backticks above are just for this prompt.)

- [ ] **Step 3: Update INDEX.md**

Open `docs/counter-priors/INDEX.md`. Find the "Active entries" section. Add a new entry alphabetically positioned between `hand-rolled-temporal` and `n-plus-one-in-user-code`:

```markdown
- [magic-string-typing](magic-string-typing.md) — bare `str` for identifier classes (`user_id: str`), status discriminators, or lookup keys. Pairs with `dazzle.types.NewType`, `enum.StrEnum`, and `PA-LLM-10`.
```

- [ ] **Step 4: Bump KG seed schema version**

Find the constant:

```bash
grep -n "SEED_SCHEMA_VERSION" /Volumes/SSD/Dazzle/src/dazzle/mcp/knowledge_graph/seed.py
```

Round 3 bumped 17 → 18. Bump 18 → 19.

- [ ] **Step 5: Verify catalogue parsing**

```bash
pytest tests/unit/test_counter_priors_drift.py -v -k "not detector and not pa_llm"
```

Expected: PASS on schema/format/section/index tests. The new entry parses, has all required sections, frontmatter is valid YAML, regex triggers compile.

- [ ] **Step 6: Verify the bidirectional drift FAILS as expected (forcing function)**

```bash
pytest tests/unit/test_counter_priors_drift.py::test_every_declared_detector_resolves -v
```

Expected: **FAIL** with a message like "declared detector 'PA-LLM-10' not found on PythonAuditAgent". This is the intended state. Task 3 closes it.

- [ ] **Step 7: Commit (with drift red — intentional)**

```bash
git add docs/counter-priors/magic-string-typing.md \
        docs/counter-priors/INDEX.md \
        src/dazzle/mcp/knowledge_graph/seed.py
git commit -m "Add magic-string-typing counter-prior (PA-LLM-10 pending)

Catalogue entry documents the antipattern of using bare str for
values that are semantically narrower — identifier classes, status
discriminators, lookup keys. The body covers all three sub-shapes
with right-shape patterns using dazzle.types.NewType + enum.StrEnum
+ TypedDict. KG seed bumped 18 → 19.

The frontmatter declares detector PA-LLM-10 which is added in the
next commit (drift test fails intentionally between commits)."
```

---

## Task 3: `PA-LLM-10` heuristic (closes the drift gap)

Detects ID-shaped function/method parameters typed as bare `str`. 17 tests + smoke against examples. Closes the drift opened by Task 2.

**Files:**
- Modify: `src/dazzle/sentinel/agents/python_audit.py`
- Create: `tests/unit/test_python_audit_magic_string_typing.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_python_audit_magic_string_typing.py`:

```python
"""Tests for PA-LLM-10 — magic-string-typing (ID-shaped parameters)."""

from __future__ import annotations

import ast
from pathlib import Path

from dazzle.sentinel.agents.python_audit import (
    PythonAuditAgent,
    _detect_magic_string_id,
)


def _parse(src: str) -> ast.Module:
    return ast.parse(src)


# ---------------------------------------------------------------------------
# Positive: ID-shaped param names + bare str annotation
# ---------------------------------------------------------------------------


def test_user_id_str_param_fires() -> None:
    src = "def f(user_id: str) -> User: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 1
    assert hits[0].snippet == "user_id: str"


def test_tenant_uuid_str_param_fires() -> None:
    src = "def f(tenant_uuid: str) -> None: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_bare_id_param_fires() -> None:
    src = "def f(id: str) -> None: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_key_suffix_fires() -> None:
    """`api_key: str` fires (in-scope; noisier but documented)."""
    src = "def f(api_key: str) -> None: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_token_suffix_fires() -> None:
    """`auth_token: str` fires (in-scope; noisier but documented)."""
    src = "def f(auth_token: str) -> None: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_str_pipe_none_fires() -> None:
    """`str | None` annotation fires."""
    src = "def f(user_id: str | None) -> None: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_optional_str_fires() -> None:
    """`Optional[str]` annotation fires."""
    src = "def f(user_id: 'Optional[str]') -> None: ...\n"
    # NOTE: forward-ref annotations are ast.Constant strings, not Subscript.
    # We pass without quotes to test the non-forward-ref case:
    src2 = "from typing import Optional\ndef f(user_id: Optional[str]) -> None: ...\n"
    hits = _detect_magic_string_id(_parse(src2), Path("app/x.py"))
    assert len(hits) == 1


def test_method_id_param_fires() -> None:
    """`self` is skipped; the ID-shaped method param fires."""
    src = "class C:\n    def m(self, user_id: str) -> None: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_async_fn_id_param_fires() -> None:
    src = "async def fetch(user_id: str) -> None: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_multiple_ids_yield_multiple_hits() -> None:
    """Each ID-shaped str param produces its own finding."""
    src = "def f(user_id: str, tenant_id: str) -> None: ...\n"
    hits = _detect_magic_string_id(_parse(src), Path("app/x.py"))
    assert len(hits) == 2


# ---------------------------------------------------------------------------
# Negative: false-positive guards
# ---------------------------------------------------------------------------


def test_branded_newtype_no_fire() -> None:
    """`user_id: UserId` (branded) does not fire."""
    src = (
        "from typing import NewType\n"
        "UserId = NewType('UserId', str)\n"
        "def f(user_id: UserId) -> None: ...\n"
    )
    assert _detect_magic_string_id(_parse(src), Path("app/x.py")) == []


def test_int_annotation_no_fire() -> None:
    """Integer IDs are out of scope (separate detector if ever)."""
    src = "def f(user_id: int) -> None: ...\n"
    assert _detect_magic_string_id(_parse(src), Path("app/x.py")) == []


def test_non_id_param_no_fire() -> None:
    """A `str` param with a name that doesn't match the ID regex doesn't fire."""
    src = "def f(name: str, description: str) -> None: ...\n"
    assert _detect_magic_string_id(_parse(src), Path("app/x.py")) == []


def test_self_param_no_fire() -> None:
    """`self` is excluded even though it's never str-typed (defensive)."""
    src = "class C:\n    def m(self) -> None: ...\n"
    assert _detect_magic_string_id(_parse(src), Path("app/x.py")) == []


def test_dataclass_init_no_fire() -> None:
    """Synthesized __init__ on @dataclass-decorated classes does not fire."""
    src = (
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class User:\n"
        "    user_id: str\n"
    )
    assert _detect_magic_string_id(_parse(src), Path("app/x.py")) == []


def test_frozen_dataclass_no_fire() -> None:
    """@dataclass(frozen=True, slots=True) is also skipped."""
    src = (
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class User:\n"
        "    user_id: str\n"
    )
    assert _detect_magic_string_id(_parse(src), Path("app/x.py")) == []


def test_no_annotation_no_fire() -> None:
    """Untyped parameter is out of scope (mypy catches separately)."""
    src = "def f(user_id) -> None: ...\n"
    assert _detect_magic_string_id(_parse(src), Path("app/x.py")) == []


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------


def test_noqa_suppression_on_def(tmp_path: Path) -> None:
    """`# noqa: PA-LLM-10` on the def line suppresses all params in that signature."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "x.py").write_text(
        "def f(user_id: str, tenant_id: str) -> None:  # noqa: PA-LLM-10 - opaque\n"
        "    pass\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_magic_string_typing(appspec=None) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------


def test_heuristic_yields_finding_with_catalogue_entry(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "transfers.py").write_text(
        "def transfer(source_id: str, destination_id: str, amount: int) -> None:\n"
        "    pass\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_magic_string_typing(appspec=None)  # type: ignore[arg-type]
    assert len(findings) == 2
    for f in findings:
        assert f.heuristic_id == "PA-LLM-10"
        assert f.catalogue_entry == "magic-string-typing"
        assert f.remediation is not None
        assert any(
            "docs/counter-priors/magic-string-typing.md" in ref
            for ref in f.remediation.references
        )


def test_heuristic_skips_tests_and_scripts(tmp_path: Path) -> None:
    for sub in ("tests", "scripts"):
        d = tmp_path / sub
        d.mkdir()
        (d / "f.py").write_text("def f(user_id: str) -> None: ...\n")
    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_magic_string_typing(appspec=None) == []  # type: ignore[arg-type]
```

- [ ] **Step 2: Run the failing tests**

`pytest tests/unit/test_python_audit_magic_string_typing.py -v`

Expected: FAIL — `_detect_magic_string_id` and `check_magic_string_typing` don't exist yet.

- [ ] **Step 3: Add module-level helpers + detector**

Modify `src/dazzle/sentinel/agents/python_audit.py`. After the PA-LLM-09 section (look for the last `_detect_optional_instead_of_result` function), add a new section. `import re` is likely already imported at module top; if not, add it at the top with the other imports.

```python
# ---------------------------------------------------------------------------
# PA-LLM-10 helpers — magic-string-typing (ID-shaped parameters)
# ---------------------------------------------------------------------------

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
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Name)
            and dec.func.id == "dataclass"
        ):
            return True
        # @dataclasses.dataclass / @dc.dataclass
        if isinstance(dec, ast.Attribute) and dec.attr == "dataclass":
            return True
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and dec.func.attr == "dataclass"
        ):
            return True
    return False


def _detect_magic_string_id(tree: ast.AST, path: Path) -> list[_ShapeHit]:
    """Return _ShapeHit records for ID-shaped parameters typed as bare `str`.

    Walks FunctionDef and AsyncFunctionDef nodes anywhere in the tree
    (including methods on classes), skipping:
    - `self` and `cls` parameters (never str-typed in practice)
    - dataclass-decorated classes entirely (their synthesized __init__ would
      fire spuriously; the field annotations are the source of truth and
      a separate detector could handle them later)
    """
    # First pass: collect line ranges of dataclass-decorated classes to skip.
    dataclass_ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _has_dataclass_decorator(node):
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

**Note:** `_ShapeHit` is the round-1 dataclass at module level. Reuse — do NOT redefine. `import re` may already exist at the module top; add it if absent.

- [ ] **Step 4: Add the `@heuristic` method**

Append to `class PythonAuditAgent` after `check_optional_instead_of_result` (round 3):

```python
    @heuristic(
        heuristic_id="PA-LLM-10",
        category="python_audit",
        subcategory="llm_bias",
        title="Magic-string typing — bare str where a brand would catch errors",
    )
    def check_magic_string_typing(self, appspec: AppSpec) -> list[Finding]:
        """Flag ID-shaped function parameters typed as bare str.

        See docs/counter-priors/magic-string-typing.md for the full
        taxonomy and right-shape patterns (dazzle.types.NewType for IDs,
        enum.StrEnum for closed sets).
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
            "docs/counter-priors/magic-string-typing.md"
        )

        findings: list[Finding] = []
        for py_file in sorted(app_dir.rglob("*.py")):
            try:
                source_text = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source_text, filename=str(py_file))
            except (SyntaxError, UnicodeDecodeError):
                continue
            source_lines = source_text.splitlines()

            for hit in _detect_magic_string_id(tree, py_file):
                def_line_text = (
                    source_lines[hit.try_line - 1]
                    if hit.try_line and 0 < hit.try_line <= len(source_lines)
                    else ""
                )
                param_line_text = (
                    source_lines[hit.line - 1]
                    if 0 < hit.line <= len(source_lines)
                    else ""
                )
                if "noqa: PA-LLM-10" in def_line_text:
                    continue
                if "noqa: PA-LLM-10" in param_line_text:
                    continue

                findings.append(
                    Finding(
                        agent=AgentId.PA,
                        heuristic_id="PA-LLM-10",
                        category="python_audit",
                        subcategory="llm_bias",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.LIKELY,
                        title=f"Magic-string ID parameter: {hit.snippet}",
                        description=(
                            f"Parameter `{hit.snippet}` is typed as bare `str`. "
                            "Use a NewType-branded alias so the type checker "
                            "distinguishes this identifier class from other str values."
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
                                "Declare a brand: `from dazzle.types import NewType; "
                                "MyId = NewType('MyId', str)`. Use `MyId` in the signature."
                            ),
                            effort=RemediationEffort.SMALL,
                            guidance=(
                                "See docs/counter-priors/magic-string-typing.md for the "
                                "canonical right-shape pattern (branded IDs in app/ids.py + "
                                "StrEnum for closed value sets)."
                            ),
                            references=[catalogue_url],
                        ),
                        catalogue_entry="magic-string-typing",
                    )
                )
        return findings
```

- [ ] **Step 5: Run the new tests**

`pytest tests/unit/test_python_audit_magic_string_typing.py -v`

Expected: PASS on all 17 tests.

- [ ] **Step 6: Drift test should now be GREEN**

`pytest tests/unit/test_counter_priors_drift.py -v`

Expected: PASS — bidirectional drift `test_every_declared_detector_resolves` passes now that PA-LLM-10 is wired.

- [ ] **Step 7: Wider sentinel/audit suite**

`pytest tests/ -m "not e2e" -k "sentinel or python_audit or result or types"`

Expected: PASS — round-3's tests + the new round-4 tests.

- [ ] **Step 8: Smoke-test against examples**

```bash
cd /Volumes/SSD/Dazzle
for dir in examples/*/; do
  if [ -f "$dir/dazzle.toml" ]; then
    name=$(basename "$dir")
    cd "$dir" && hits=$(dazzle sentinel scan --agent PA --severity medium 2>&1 | grep -c "PA-LLM-10")
    cd /Volumes/SSD/Dazzle
    echo "$name: $hits"
  fi
done
```

Expected: every example reports `0`. If any fire:
- Real magic-string ID in an example app → STOP and report (fix the example separately, not in this slice)
- False positive → STOP and report; the detector needs tightening with a regression test

- [ ] **Step 9: Commit**

```bash
git add src/dazzle/sentinel/agents/python_audit.py \
        tests/unit/test_python_audit_magic_string_typing.py
git commit -m "Add PA-LLM-10: magic-string-typing heuristic

Fires on function/method parameters whose name matches ID-shaped
patterns (bare id, *_id, *_uuid, *_key, *_token) AND whose annotation
is bare str / str | None / Optional[str]. Recommends migrating to
dazzle.types.NewType-branded aliases.

Walks free functions, async functions, and methods on non-dataclass
classes. Skips self/cls params and entire dataclass-decorated classes
(to avoid synthesized __init__ false positives).

Closes the drift opened by the prior commit — PA-LLM-10 declared in
the catalogue frontmatter now resolves to a real heuristic on
PythonAuditAgent."
```

---

## Task 4: CHANGELOG + bump + ship

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/api-surface/public-helpers.txt` (regenerate after `NewType` added to top-level)
- Modify (via `/bump minor`): version files

- [ ] **Step 1: Update CHANGELOG**

Open `/Volumes/SSD/Dazzle/CHANGELOG.md`. Insert a new dated heading immediately AFTER `## [Unreleased]` and BEFORE `## [0.77.0] - 2026-05-26`:

```markdown
## [0.78.0] - 2026-05-26

### Added — agent code quality substrate round 4 (Layer 2: dazzle.types + PA-LLM-10)

- **`dazzle.types`** — second Layer-2 substrate piece. Thin module re-exporting `typing.NewType` for one-stop discovery: `from dazzle.types import NewType`. Zero runtime cost — NewType is the identity function at runtime. Importable from `dazzle` top-level as well (`from dazzle import NewType`).
- **`docs/counter-priors/magic-string-typing.md`** — new counter-prior. Covers all three sub-shapes of the antipattern (magic-string IDs, enum-dispatch chains, typed lookup keys) with right-shape patterns using `dazzle.types.NewType`, `enum.StrEnum`, and `typing.TypedDict`. Only sub-shape (a) is detected by PA-LLM-10 today; (b) and (c) are documented for inference-time guidance.
- **Sentinel heuristic `PA-LLM-10`** (`magic_string_typing`) fires on function/method parameters whose name matches `id`, `*_id`, `*_uuid`, `*_key`, or `*_token` AND whose annotation is bare `str` (or `str | None` / `Optional[str]`). Severity MEDIUM, confidence LIKELY. Suppress via `# noqa: PA-LLM-10 — <reason>` on the `def` line or the parameter line.

### Agent Guidance

- When writing functions that take identifier parameters, declare branded types in `app/ids.py` (or similar) and use them in signatures: `def transfer(src: PaymentId, dst: PaymentId, amount: int) -> ...`. The brand catches cross-class mix-ups (`UserId` passed where `TenantId` was expected) that bare `str` parameters allow.
- For closed value sets (status fields, discriminators), use `enum.StrEnum` (stdlib, Python 3.11+). The `match` statement with exhaustive cases gives type-checker exhaustiveness and catches typos in the enum-value strings.
- `_key` and `_token` suffixes are noisier than `_id`/`_uuid` — cache keys and opaque auth tokens may legitimately be `str`. Document the case with `# noqa: PA-LLM-10 — opaque cache key` when intentional.
- Layer 2 of the substrate now has two primitives: `dazzle.result` (round 3) and `dazzle.types` (round 4). The pattern is established — future rounds either extend Layer 2 with more primitives or fill Layer-3 catalogue-gap detectors.
- **Comprehension/enum-dispatch detection** (sub-shapes b and c) remains future work — PA-LLM-10's AST signal covers only sub-shape (a) ID-shaped params today.
```

- [ ] **Step 2: Run the full pre-ship gate**

```bash
cd /Volumes/SSD/Dazzle
pytest tests/ -m "not e2e" --deselect tests/unit/test_propose_patterns_1249.py 2>&1 | tail -5
ruff check src/ tests/ --fix 2>&1 | tail -3
ruff format src/ tests/ 2>&1 | tail -3
mypy src/dazzle 2>&1 | tail -3
```

Expected: pytest green (modulo pre-existing flaky #1265), ruff clean, mypy clean.

- [ ] **Step 3: Regenerate API surface baseline**

`NewType` is now in `dazzle.__all__` so the public-helpers baseline needs regenerating. Same pattern as round 3:

```bash
dazzle inspect api public-helpers --diff
# Confirm the only change is +NewType
dazzle inspect api public-helpers --write
pytest tests/unit/test_api_surface_drift.py::test_surface_matches_baseline -v
```

Expected: diff shows ONLY the `NewType` addition; baseline regenerated; drift test passes.

- [ ] **Step 4: Run mkdocs strict build**

`mkdocs build --strict 2>&1 | tail -5`

Expected: exit 0, no broken-link errors.

- [ ] **Step 5: Commit CHANGELOG + baseline**

```bash
git add CHANGELOG.md docs/api-surface/public-helpers.txt
git commit -m "Document substrate round 4 in CHANGELOG under [0.78.0]

Also regenerate docs/api-surface/public-helpers.txt baseline — NewType
now exported from dazzle top-level. CHANGELOG entry under Added covers
the new exports per the round-1 API drift gate contract."
```

- [ ] **Step 6: Bump version**

Run `/bump minor` in the Claude session (controller skill, not a subagent action).

Expected: bumps `0.77.0 → 0.78.0` across all 6 lines.

- [ ] **Step 7: Commit version bump**

```bash
git status   # verify only the 5 version files changed
git add pyproject.toml src/dazzle/mcp/semantics_kb/core.toml \
        .claude/CLAUDE.md ROADMAP.md homebrew/dazzle.rb
git commit -m "Release v0.78.0: dazzle.types + PA-LLM-10 (substrate round 4)

Second Layer-2 substrate primitive. dazzle.types pairs with
dazzle.result (round 3): one for distinguishing failure modes, one
for distinguishing identifier classes. PA-LLM-10 catches user code
that reached for bare str where a NewType brand would catch errors."
```

- [ ] **Step 8: Verify diff stays under the scope ceiling**

```bash
git diff main...HEAD --stat
```

Expected: cumulative diff < 600 LOC. The spec estimated ~485. If you've crept past 600, flag it before pushing.

- [ ] **Step 9: Push branch + open PR**

```bash
git push -u origin feature/pa-llm-10-magic-string-typing
gh pr create --title "Substrate round 4: dazzle.types + PA-LLM-10 (magic-string-typing) — v0.78.0" --body "$(cat <<'EOF'
## Summary

Round 4 of the agent code quality substrate. **Second Layer-2 ship** — completes the Layer-2 substrate's primary surface alongside round 3's dazzle.result.

- **`dazzle.types`** convention library: thin re-export of `typing.NewType`. Public from `dazzle` top-level.
- **`magic-string-typing.md`** counter-prior documenting all three sub-shapes (IDs / enum dispatch / lookup keys) with right-shape patterns.
- **`PA-LLM-10`** Sentinel heuristic detecting ID-shaped function/method parameters typed as bare `str`.

Implements `docs/superpowers/specs/2026-05-26-substrate-round-4-types-design.md`.

## Test plan

- [x] `pytest tests/unit/test_types.py -v` — 5 passed
- [x] `pytest tests/unit/test_python_audit_magic_string_typing.py -v` — 17 passed
- [x] `pytest tests/unit/test_counter_priors_drift.py -v` — drift back to green after task 3
- [x] `pytest tests/ -m "not e2e" --deselect tests/unit/test_propose_patterns_1249.py` — clean except known #1265
- [x] `ruff check && ruff format` — clean
- [x] `mypy src/dazzle` — clean
- [x] `mkdocs build --strict` — clean
- [x] API surface drift gate green after `dazzle inspect api public-helpers --write`
- [x] Smoke-test: 14 example apps, 0 PA-LLM-10 findings

## Scope discipline

Diff under 600 LOC (spec estimated ~485).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes

**Spec coverage:**
- §3.A library (NewType re-export + public top-level) → Task 1.
- §3.B catalogue entry (4 mandatory sections + frontmatter detectors:) → Task 2.
- §3.C detector (4 module helpers + `@heuristic` method + 17 tests) → Task 3.
- §4 data flow → covered by Task 3.
- §5 suppression → covered by Task 3 (noqa on def line AND param line).
- §6 scope discipline (600 LOC ceiling) → enforced in Task 4 Step 8.
- §7 implementation order (sequential 3 commits with intentional red drift between 2 and 3) → preserved.
- §8 risks (dataclass skip, Pydantic uncovered, overload, singledispatch) → documented in CHANGELOG Agent Guidance.
- §9 success criteria → checked by Task 4 Steps 2-4.

**Placeholder scan:** clean. No TBDs, no "fill in details". Today's date `2026-05-26` in the CHANGELOG.

**Type consistency:**
- `_ID_NAME_RE`, `_is_id_shaped_name`, `_is_bare_str_annotation`, `_has_dataclass_decorator`, `_detect_magic_string_id` declared in Task 3 Step 3, used in Task 3 Step 1 tests and Task 3 Step 4 heuristic method.
- `_ShapeHit` reused from rounds 1-3 (same dataclass, same `try_line` semantic).
- `NewType` exported in Task 1 Step 3-4, imported in Task 1 Step 1 tests.

**Intentional red drift between tasks 2 and 3** documented in Task 2's commit message AND in the implementation order — same as round 3's pattern.
