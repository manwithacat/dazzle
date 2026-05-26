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

## Right shape

Three patterns matching the three sub-shapes:

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

The brand catches mix-ups between **different** ID classes (`UserId` vs `TenantId`). Within a single ID class, parameter-ordering bugs are still possible — the type system catches the harder cross-class error.

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

## Why this matters here

Dazzle's framework code paths use typed IR (`EntityRef`, `PersonaSpec`, etc.) and DSL-level enums (`enum` keyword) that prevent magic-string typing at the model layer. User-app Python in `app/` doesn't yet have an idiomatic answer — agents reach for `str` because the corpus does.

`PA-LLM-10` flags ID-shaped parameters at scan time. `dazzle.types` makes the right shape one import away. The catalogue documents all three sub-shapes for inference-time agent guidance even though only (a) is detected today.

`StrEnum` is stdlib and not part of `dazzle.types` for the same reason `dataclasses` isn't — it's already in the standard library and a re-export would add nothing.
