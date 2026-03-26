# ADR-0014: No `from __future__ import annotations` in FastAPI Route Files

**Status:** Accepted
**Date:** 2026-03-26

## Context

PEP 563 (`from __future__ import annotations`) defers annotation evaluation, turning all type hints into strings at runtime. This is harmless in most Python code, but FastAPI requires real types at runtime for dependency injection (`Depends()`) and OpenAPI schema generation (`app.openapi()`).

When a route handler file has `from __future__ import annotations`, Pydantic v2's `TypeAdapter` encounters `ForwardRef('Request')` or `ForwardRef('Response')` instead of the actual classes. It cannot resolve these forward references, causing `/openapi.json` and `/docs` to return 500.

This was discovered after 23 files across `dazzle_back` had accumulated the import by copy-paste. The bug was latent until auth was enabled on the `simple_task` example, which added enough route handlers to trigger the schema generation failure.

## Decision

**Do not use `from __future__ import annotations` in any file that defines FastAPI route handlers, dependencies, or middleware.**

On Python 3.12+, the only feature PEP 563 provides is deferred annotation evaluation. The `X | Y` union syntax works natively. Forward references for circular imports should be solved with `TYPE_CHECKING` guards or deferred imports — not by stringifying all annotations.

## Consequences

### Positive

- `/openapi.json` and `/docs` work correctly
- FastAPI dependency injection resolves types at runtime
- Pydantic v2 can build `TypeAdapter` instances for all route parameters

### Negative

- Developers must remember not to add the import in route files
- Some IDE templates auto-insert `from __future__ import annotations` — must be removed manually

### Neutral

- Files that don't define routes (IR modules, CLI, parsers, tests) can still use it safely
- No performance impact — Python 3.12 evaluates annotations lazily in most contexts anyway

## Alternatives Considered

### 1. Patch Individual Annotations

Change `-> Response` to `-> Any` on each affected handler.

**Rejected:** Whack-a-mole. Every new handler with a FastAPI type annotation would break again.

### 2. Call `model_rebuild()` After Route Registration

Force Pydantic to re-resolve forward references after all routes are registered.

**Rejected:** Fragile — must be called at exactly the right time, after all routes but before first `/openapi.json` request. Easy to forget.

### 3. Remove `from __future__ import annotations` From Route Files

Simply don't use the import in files that FastAPI inspects.

**Accepted:** Eliminates the root cause. No ongoing maintenance burden. Python 3.12+ doesn't need it.

## Implementation

Removed `from __future__ import annotations` from 23 files in `src/dazzle_back/` that define route handlers, middleware, or dependencies. CI badge went green after being red for 24 hours.
