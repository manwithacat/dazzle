---
id: raw_db_in_custom_route
name: Raw DB access in a custom route handler
layer: inference
status: active
summary: >-
  A project's custom route handler (a `routes/*.py` override) that touches a
  domain entity must bind to that entity's permit/scope — via the static
  `# dazzle:implements <Entity>.<op> via <param>` header (which auto-runs
  policy.check_entity_op) or by calling check_entity_op in the body — NOT by
  reaching the database directly with raw SQL or a hand-built Repository. Raw DB
  access escapes the declared binding and bypasses RBAC entirely (ADR-0040).
triggers_text:
  - "custom route handler"
  - "route override"
  - "raw SQL in a handler"
  - "execute a DELETE"
  - "query the database directly"
  - "hand-written API endpoint"
  - "bypass the generated route"
triggers_code:
  - '\.execute\s*\(\s*[''"]?\s*(SELECT|INSERT|UPDATE|DELETE)\b'
  - '\bRepository\s*\('
  - '(?m)^\s*(import\s+psycopg|from\s+psycopg)'
---

## The corpus prior

LLM training data is saturated with web handlers that talk to the database
directly: `cur.execute("DELETE FROM ...")`, `db.query(Model).filter(...)`, a
hand-rolled repository constructed inline. In a plain Flask/FastAPI app that is
idiomatic. So when asked to write a *custom* Dazzle route — "implement my own
`POST /encumbrances` with bespoke logic" — a model reaches for the same shape:
open a connection, run SQL, return. It works at request time, which makes the
wrong shape feel correct.

## Wrong shape

```python
# dazzle:route-override DELETE /encumbrances/{id}
async def handler(request, id: str):
    async with get_conn() as c:                 # ← raw DB
        await c.execute("DELETE FROM Encumbrance WHERE id = %s", (id,))
    return {"deleted": True}
```

This handler replaces the generated, permit/scope-bound `DELETE /encumbrances/{id}`
with one that runs **no** permit check and **no** scope predicate. Any role that
can reach the route can delete any row — the entity's `permit:`/`scope:` rules are
silently inert. It is outside the RBAC matrix, so the security model can no longer
be proven.

## Right shape

Bind the handler to the entity + op so the framework runs permit/scope first.
Either declare it statically (preferred — scannable, lands in the RBAC matrix):

```python
# dazzle:route-override DELETE /encumbrances/{id}
# dazzle:implements Encumbrance.delete via id      # ← framework wraps with check_entity_op
async def handler(request, id: str):
    ...                                            # body runs ONLY if permit + scope pass
```

…or call the imperative gate in the body (for body-shaped ops / composite ids):

```python
from dazzle.http.runtime.policy import check_entity_op

async def handler(request, id: str):
    await check_entity_op(request, "Encumbrance", "delete", row_id=id)  # 403/404 on denial
    ...
```

Let the framework's `Repository` + policy do the data access; the handler carries
only the *novel* logic. If you genuinely need a generated route gone, suppress it
with the entity's `expose:` allowlist (#1420 Slice 2) — don't shadow it with an
un-gated override.

## Why this matters here

ADR-0040's invariant is that **no route touching a domain entity exists outside
that entity's permit/scope model, and every domain route is an RBAC-matrix row**.
Raw DB access in a custom handler is *the* way that invariant breaks: it's a write
path the matrix can't see and the permit algebra can't reach. `expose:`/the
conformance check govern the *declared* surface; this counter-prior governs the
*handler body*, the one part structure can't constrain. The
`scan_handler_for_raw_db` filter (`route_overrides.py`) flags the shapes above so
the gap is caught at authoring, not discovered as a prod RBAC bypass.
