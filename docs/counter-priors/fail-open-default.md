---
id: fail_open_default
name: Fail-open default beside fail-closed siblings
layer: filter
status: active
summary: >-
  A function that signals three outcomes — a value, an empty value meaning "no
  restriction", and a sentinel meaning "deny" — returns the permissive one from
  a path where its siblings deny. Empty-container and sentinel semantics are
  corpus-defaulted: `{}` and `None` read as "nothing happened", so the error
  path is written last and inherits the neutral-looking return. Two real
  instances shipped behind green gates, both in scope resolution, where the
  permissive value means *every row*. Read the caller's branch, not the
  function's docstring, and check that every exit is on the safe side.
triggers_text:
  - "treat as no filter"
  - "default to allowing"
  - "empty means no restriction"
  - "fall through and return empty"
  - "if we can't tell, allow"
  - "be permissive by default"
  - "just return nothing"
  - "unfamiliar shape"
triggers_code:
  - 'return\s*\{\}\s*#.*no\s+(filter|restriction)'
  - 'return\s*\{\}\s*#.*treat\s+as'
  - 'if\s+not\s+\w+:\s*#\s*.*allow'
refs:
  adrs: []
  kb_patterns: []
  tests:
    - tests/unit/test_scope_default_deny_returns.py
---

## The corpus prior

*Unclear result → return the neutral-looking value.*

When a function distinguishes three outcomes, the error path is written last and
inherits whatever "nothing happened" looks like. In Python that is `{}` or
`None` — so the error path returns the **empty container**, which is rarely
neutral.

The tell is in the **caller**, not the callee:

```python
if scope_result is None:  return None          # deny
if not scope_result:      unscoped_read(...)  # EVERY ROW
```

`{}` is not "no opinion". It is the *most permissive* outcome.

## Wrong shape

```python
# WRONG — `{}` means "no restriction" to every caller
def _resolve_scope_filters(...):
    ...
    for rule in matched_rules:
        ...
    return {}          # fell off the end: "no resolvable condition"
```

```python
# WRONG — reports nothing about whether it UNDERSTOOD the condition
def _extract_condition_filters(condition, user_id, filters, ...):
    ...
    # unrecognised shape -> filters is still {} -> returned as a success
```

## Right shape

Reserve the permissive value for the specific condition that means
"unrestricted". Everything else denies:

```python
# RIGHT
    return None      # unresolvable -> deny, matching every sibling path
```

And when one condition legitimately produces no filter *from inside* a
recognised branch, the function must **report which branch it took**:

```python
# RIGHT — `bool` is "a recognised shape was interpreted"
if not recognised:
    logger.warning("Scope condition for %s has an unrecognised shape", entity)
    return None
return filters        # may legitimately be {}
```

## Why this matters here

Two real instances, both in `http/runtime/scope_filters.py`, both shipped green:

1. **The fall-through.** After trying every path it could, an unresolvable rule
   returned `{}` — the same value `scope: all` returns.
2. **The successful-but-empty return.** An unrecognised condition shape was
   indistinguishable from a recognised one that legitimately emits nothing (the
   documented `current_context` skip), so the empty dict was returned as success.

Fixing one without the other leaves the bug half-open, which is why the second
needed a `bool` return rather than another `return None`.

## The three-way distinction

The hard case is when two situations both yield "no filters":

| Situation | Correct |
|---|---|
| `scope: all`, or no scopes declared | `{}` — permissive, and it means it |
| Recognised shape, nothing to emit (`current_context`, no selection) | `{}` |
| Shape not recognised | deny |
| Resolution raised | deny |

The middle row is why "deny when nothing was extracted" is wrong: it breaks a
documented behaviour. The resolver cannot distinguish the rows from outside —
the extractor can, because the shape knowledge is already there.

## Related

- [duplicated-business-rule](duplicated-business-rule.md) — both instances were
  reachable only because a rule had been duplicated.
