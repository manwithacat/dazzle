---
id: silent_control_flow
name: Silent control flow that hides a resource or a stall
layer: filter
status: active
summary: >-
  Code that catches an exception, does nothing recoverable, and lets execution
  continue — retrying on an aborted connection, blocking an event loop inside
  `async def`, or polling for a state that will never arrive because the code
  under test already consumed it. Corpus-defaulted because each site looks
  defensive: the handler exists, the retry exists, the loop exists. What is
  missing is the *question* "what is the state of the thing I am operating on,
  and did my handler change it?" A handler that runs more statements than the
  code it guards is not fail-closed.
triggers_text:
  - "just retry"
  - "try again with"
  - "belt and braces"
  - "catch and continue"
  - "poll until"
  - "wait for it"
  - "if we can't tell, allow"
  - "should not happen"
  - "defensive"
  - "in case"
triggers_code:
  - 'except[^\n]*:\s*\n(?:(?!.*(?i:rollback|commit|transaction|savepoint))[^\n]*\n){0,6}?[^\n]*\.execute\('
  - 'async\s+def[^\n]*\n(?:.*\n){0,20}?[^\n]*(urlopen|requests\.(get|post)|verify_oauth2_token)\('
  - 'while\s+[^\n]*:\s*\n(?:.*\n){0,6}?[^\n]*asyncio\.sleep\('
refs:
  adrs: []
  kb_patterns: []
  tests:
    - tests/unit/test_no_db_retry_without_recovery.py
    - tests/unit/test_async_no_blocking_io.py
---

## The corpus prior

*Defensive-looking control flow that never asks what state it is in.*

Retrying, catching, or polling all have the *shape* of caution. What they lack
is the question underneath: **"what is the state of the thing I am operating
on, and did my handler change it?"**

## Wrong shape

```python
# WRONG — the transaction is already aborted; this retry always raises
try:
    cursor.execute(sql, params)
except Exception:
    sql = rebuild_with_alternate_column()
    cursor.execute(sql, params)          # InFailedSqlTransaction
```

```python
# WRONG — blocking the event loop inside async def
async def _confirm_subscription(message):
    with urllib.request.urlopen(req, timeout=10) as resp:   # stalls the loop
        ...
```

```python
# WRONG — the poll absorbs the very stall the test means to detect
for _ in range(200):
    if parked.is_set():
        break
    await asyncio.sleep(0.01)      # on a blocked loop this just waits out the stall
```

## Right shape

Ask what must be true for a second attempt to differ. If nothing changed, the
retry is theatre.

```python
# RIGHT — recover the resource before reusing it
except Exception as first_exc:
    conn.rollback()                 # transaction is aborted until this
    ...
    try:
        cursor.execute(sql, params)
    except Exception as second_exc:
        conn.rollback()
        raise RuntimeError(...) from second_exc
```

```python
# RIGHT — dispatch the blocking call off the loop
loop = asyncio.get_running_loop()
return await loop.run_in_executor(None, _confirm)
```

For a non-blocking test, make the **deadline** the signal: park the worker for
far longer than the probe's timeout, so a blocked loop surfaces as
`wait_for` raising `TimeoutError` rather than a slow pass.

## Why this matters here

Three real instances:

| Site | Failure |
|---|---|
| `repository.py:171-193` | Retry on an aborted psycopg3 transaction. The `effective_to` fallback was **unreachable dead code**, and a soft column-name mismatch surfaced as a hard 500 on any `as_of` read. |
| `channels/ses_webhooks.py:49` | `urlopen(timeout=10)` inline in `async def`. One slow SNS confirmation stalls every concurrent request in the worker, including health checks. |
| `runtime/social_auth.py:97,127` | A synchronous Google tokeninfo round-trip inside `async def`, on every mobile sign-in. |

The repo already had the right pattern at `channels/providers/email.py:179`;
these two sites were simply never swept.

## Why the gates missed them

Existing exception gates key on the handler **body**: silent, trivial, or
single-statement (`test_swallow_ratchet`, `test_no_bare_except_pass`). A
twenty-statement handler that re-executes is counted by none of them, and none
models resource state across the `except` boundary.

`test_no_db_retry_without_recovery.py` keys on that boundary instead: a retried
`cursor.execute` with no **prior** recovery. Recovery after the retry does not
count, and neither does a rollback in a sibling `except` — the first draft of
that gate made exactly that mistake and passed the un-fixed code.

## Related

- [exceptions-as-control-flow](exceptions-as-control-flow.md) — the same prior
  in user app code rather than the runtime.
