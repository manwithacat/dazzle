---
id: exceptions_as_control_flow
name: Exceptions as control flow
layer: inference
status: active
summary: >-
  `try`/`except: pass`, exception-driven fallbacks, and EAFP misused as a
  general control-flow tool. The corpus is full of these because Stack
  Overflow's top-voted Python answers do exactly this; the result is
  silent failures that surface as "the integration just stopped working"
  months later with no log line.
triggers_text:
  - "error handling"
  - "try except"
  - "swallow exception"
  - "catch and ignore"
  - "log and continue"
  - "robust to errors"
  - "make it not crash"
  - "fallback if it fails"
  - "best effort"
triggers_code:
  - 'except\s*:\s*pass'
  - 'except\s+Exception\s*:\s*(pass|\n\s*pass)'
  - 'except\s+Exception\s*:\s*(return\s+None|\n\s*return\s+None)'
  - 'except\s*\([^)]+\)\s*:\s*pass'
  - 'except.*:.*return\s+None'
refs:
  adrs: []
  memories: []
  pr_review_agents:
    - silent-failure-hunter
  tests:
    - tests/unit/test_no_bare_except_pass.py
---

# Exceptions as control flow

## The corpus prior

LLM training corpora are dominated by Python and JavaScript code where `try`/`except` (or `try`/`catch`) is used not to recover from a specific, anticipated failure but as a *general make-the-error-go-away* tool. Stack Overflow's top-voted answers to "how do I make this not crash" are overwhelmingly of the form `try: do_thing() except: pass` or `try: ... except Exception: return None`. Tutorials reinforce this — "wrap it in a try/except for safety" is canonical advice.

The shape compounds in agent-driven code because the agent's job is "make the task succeed." A `try`/`except` that swallows the error makes the immediate task green. The cost is paid later, by someone else, when the integration stops working and the only signal is the absence of an expected outcome.

Four canonical wrong shapes show up:

1. **Silent swallow** — `except: pass`, `except Exception: pass`. No log, no metric, no re-raise. The error is erased.
2. **Fallback control flow** — `try: result = api.get(x); except Exception: result = default_value`. The exception path replaces a proper conditional. Distinguishing "API was down" from "x doesn't exist" is impossible.
3. **Validation via exception** — `try: int(s); valid = True; except ValueError: valid = False`. A regex or `.isdigit()` would model the question directly. Using exceptions blurs whether the failure is expected (bad input) or unexpected (programmer error).
4. **Try-as-conditional** — `try: x = d[k]; except KeyError: x = None`. `d.get(k)` exists. The corpus prior reaches for try/except because dictionary-not-having-key feels like "an error" rather than "a normal outcome of asking."

## Wrong shape

```python
def sync_orders():
    try:
        orders = api.fetch_orders()
        for order in orders:
            try:
                db.upsert(order)
            except Exception:
                pass  # don't let one bad order block the rest
    except Exception:
        logger.warning("sync failed")
        return None
```

What this gives up: every failure mode collapses into one of three indistinguishable shapes (silent skip, log-once-then-shrug, swallow-and-return-None). The next time the API changes its schema, the per-order `upsert` quietly drops every row; the outer `except` notices but the log line "sync failed" carries no actionable information; the function returns `None` and the caller has no way to know if the result is "no orders" or "everything broke."

## Right shape

Three principles:

1. **Catch the exception you actually expected, at the call site where you expected it.** `except ValueError` because `int(s)` can raise `ValueError`. Not `except Exception`.
2. **Make the fallback explicit, not exceptional.** If you can recover, the recovery is a feature of the API contract, not error handling. Return a `Result`-like tuple, a sentinel, or branch on `if x is not None`.
3. **Re-raise everything you didn't model.** The unhandled exception is the loudest signal a system can produce. Silencing it is the costly choice.

```python
def sync_orders() -> SyncResult:
    orders = api.fetch_orders()  # ApiError propagates; caller decides what to do
    failures: list[OrderUpsertFailure] = []
    succeeded = 0
    for order in orders:
        try:
            db.upsert(order)
        except db.UpsertConflict as e:
            # Specific, anticipated, recoverable; captured for visibility.
            failures.append(OrderUpsertFailure(order.id, str(e)))
        else:
            succeeded += 1
    return SyncResult(succeeded=succeeded, failures=failures)
```

Compare:

- The API failure propagates — the caller chooses retry, alert, or abort.
- The per-order failure is *named* (`UpsertConflict`), not `Exception`.
- The shape of "some succeeded, some failed" is in the return type, not in the absence of an exception.
- A previously-unknown failure mode (e.g. the DB connection dies mid-loop) raises an `OperationalError` that propagates and aborts the sync — the right behaviour for an unknown failure.

For dict access: prefer `.get(k, default)` over `try/except KeyError`. For type-coercion validation: prefer `if not s.isdigit()` or a validator over `try: int(s) except`. For "is this URL reachable": prefer `if response.status_code == 200` over wrapping the request in try/except.

## Why this matters here

Dazzle's `app/sync/`, `app/render/`, and `app/db/` directories are the LLM-authored frontier of every project. The framework code is densely typed, scope-validated, and FK-checked — the substrate holds for what the framework emits. User app code is where prior leakage shows up. A silent-swallow in `app/sync/some_integration.py` typically lands in production unobserved.

The current substrate catches one narrow shape (`tests/unit/test_no_bare_except_pass.py`) but the broader behaviour — exception-as-fallback, validation-via-exception, try-as-conditional — slips through. The pr-review-toolkit's `silent-failure-hunter` agent exists to catch this at review time; this entry is the inference-time counter-prior, so the bad shape never gets written in the first place.

## Cross-references

- `tests/unit/test_no_bare_except_pass.py` — the narrow drift gate.
- pr-review-toolkit:silent-failure-hunter — the review-time net.
- `dev_docs/2026-05-25-substrate-audit.md` §4.1 — the gap that motivated this entry.
