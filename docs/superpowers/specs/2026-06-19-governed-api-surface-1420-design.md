# Governed API surface — #1420

**Status:** Design approved (brainstorming, 2026-06-19); pending implementation plan(s).
**Issue:** #1420 (FR: per-entity opt-out of generated REST CRUD), reframed. Related: #1392
(let custom renderers / route-overrides opt back into framework guarantees), ADR-0025
(authorization is entity-level), the provable-RBAC framework (`src/dazzle/rbac/`).

## Problem (verified against 0.83.9)

The route surface is the one part of Dazzle that isn't *governed* the way the rest of the
framework is. Two leaks:

1. **Generated REST proliferates and can't be trimmed.** An entity with persistence + a
   `permit:` block + any UI surface gets a full generated CRUD surface. `GET`(read+list) and
   `DELETE /<plural>/{id}` are emitted **regardless** — `permit:` only *gates* them, it doesn't
   control their *existence*; `POST`/`PUT` come from create/edit surfaces; workspaces emit a
   **second** full-CRUD surface for their regions' entities. There is no combination of
   permit/surface trimming that removes an entity's generated REST. `headless`
   (`surfaces.py:346`) is the inverse (API-only). So a project that ships its own hand-written
   API at a *different* path (`/api/encumbrances`) is left with an orphaned, redundant parallel
   write API at `/encumbrances`.

2. **Custom routes are an ungoverned escape hatch.** Projects define their own API via Python
   `route_overrides` (`route_overrides.py`; same-path overrides already suppress the generated
   route via `claimed_routes`/FastAPI first-match, #1101). The framework offers
   `policy.check_entity_op(request, entity, op, …)` — the *same* permit+scope evaluation the
   generated routes run, fail-closed (no registry → `RuntimeError`; no auth'd user → `401` even
   for unprotected entities; access-spec → `403`/`404`). **But calling it is opt-in.** A custom
   handler can touch a domain entity and never check permit/scope — outside the analyzable
   security surface entirely. *"Define a custom API without conforming to the security model" is
   possible today.* That is the real defect.

3. **Generated routes fail OPEN under `enable_auth=False`.** `server.py:1465`: when auth is
   disabled, `_setup_auth` returns `(None, None)` → no `auth_dep` → the cedar/permit wrapper is
   never applied → generated CRUD is world-writable. `enable_auth` defaults to `False` and is
   driven by `manifest.auth.enabled`. (Notably `check_entity_op` is fail-*closed* even with auth
   off — a hand-written policy-checked handler is *safer* than the generated route here. That
   inversion is the active liability; a downstream hit it in prod.)

## The invariant

**No route that touches a domain entity exists outside that entity's permit/scope model, and
the full route set is a provable artifact — every route is an RBAC-matrix row.** "Unwanted route
proliferation" is the symptom of routes escaping that governance. This extends the provable-RBAC
thesis (ADR-0025, `src/dazzle/rbac/`) from the *matrix* to the *route surface*.

## The principle

**Prefer structure over lint.** A lint is a signal for missing structure (the route-surface
analogue of ADR-0024's "a regex is a signal for missing grammar"). Make the bad thing
*unrepresentable*; lint only the irreducible Python-handler residue.

This keeps the framework's character: a **non-Turing, deterministic DSL** governs *which routes
exist and what authz they carry*; the Python handler body carries *novel logic only*. Custom
APIs become a **declared binding (analyzable, matrix-verified) over a Python body (the freedom)**.

## DSL surface (shape; exact keywords finalized at implementation)

### 1. Generated-REST control — explicit per-op allowlist on the entity

```dsl
entity Encumbrance "Encumbrance":
  api:
    expose: [list, read]    # ONLY these generated routes exist; create/update/delete suppressed
  id: uuid pk
  ...
```

- `expose:` is the **single source of truth** for which generated REST routes exist for the
  entity — decoupled from surface-presence. It also gates the **workspace-emitted CRUD** for that
  entity (no second surface for a suppressed op).
- **No `api:` block ⇒ all ops** (`[list, read, create, update, delete]`) — backward compatible.
- `expose: []` ⇒ no generated public REST (the FR's `internal`); persistence, `permit:`/`scope:`
  model, GraphQL, and admin-workspace surfaces are all retained.
- **Surface ↔ expose reconciliation:** a create/edit surface still renders UI, but no longer
  *independently* creates a route; `create`/`update` must be in `expose` for the POST/PUT to mount.
  A create surface whose op isn't exposed is a `dazzle validate` error (no silent contradiction).

### 2. Custom-API binding — a declared route over a Python handler

A custom route is **declared** (home: the existing `interfaces:` construct or a new sibling —
finalized in plan) naming `(method, path, entity, op, handler-ref)`. The framework mounts it
auto-wrapped with `check_entity_op(request, entity, op, …)` *before* the handler body runs, so
the permit/scope model applies by construction. The handler is Python (the novel logic); the
binding is declared, analyzable, and contributes its `(entity, op)` row to the RBAC matrix.

## The four guardrail tiers

| Tier | What it enforces | Mechanism |
|---|---|---|
| **Structural** | A domain route can't be declared without `(entity, op)`; the policy wrap is automatic. The worst pattern (unchecked handler) is *unrepresentable*. | The declared-binding construct + framework mount wrapper |
| **Conformance (validate + CI, BLOCKING)** | Declared op must have a matching `permit:` rule; **every route is an RBAC-matrix row; an unbound/undeclared domain route fails the CI security gate.** | `core/validation/` rules + `src/dazzle/rbac/` matrix-completeness check (extends the existing CI security gate) |
| **Counter-prior (authoring-time, BLOCKING)** | The Python-handler residue: a custom handler doing **raw SQL / direct repository construction** for an entity (escaping its declared binding). | New `docs/counter-priors/` entry + a `tests/unit/test_no_*.py` policy gate (mirrors `test_no_bare_except_pass.py`); surfaced to a coding agent at code-gen time via the counter-prior catalogue |
| **Runtime fail-closed** | Mutating routes denied when no auth dependency is attached (the `enable_auth=False` hole), outside an explicit dev profile. | A guard in the route-mount / request path |

**Resolved decisions:** the residue lint is **blocking** (policy gate + hard counter-prior) and
matrix-completeness is a **hard CI gate** — per the "enforcing RBAC / deterministic DSL" intent.
Both can be relaxed to advisory later if false-positive rate warrants, but default to enforcing.

## Decomposition into shippable slices

Each slice is independently valuable and testable; ship in order.

### Slice 1 — Fail-closed guard (no DSL change; ships first)
Close the active prod liability: mutating generated/custom routes must not be silently writable
when `enable_auth=False`. Deny mutating routes when no auth dependency is attached, **outside an
explicit dev profile** (the dev/local case where auth-off is intentional stays ergonomic — the
guard fires only in non-dev, or emits a loud boot warning + denies mutations). Protects *every*
app, independent of whether they adopt the new DSL. Highest urgency.

- **Gate:** a test that a mutating route returns 401/403 (not 200) under `enable_auth=False` in a
  non-dev profile, and that an explicit dev profile still allows it; `ruff`/`mypy` clean.

### Slice 2 — `api: expose:` generated-REST control
The per-op allowlist (IR + parser + route-generation gating + workspace-CRUD gating) + the
`declared-op ↔ permit` and `surface-op ↔ expose` validation rules.

- **Gate:** parser/IR tests (`expose:` → IR; default = all ops); a route-inspection test that a
  suppressed op has no generated route (top-level *and* workspace); validate-time errors for the
  reconciliation rules; `ir-types` baseline + golden-master regen; example-app coverage.

### Slice 3 — Declared conformant custom routes
The declared custom-route binding (IR + parser/manifest + the framework mount wrapper around
`check_entity_op`) + RBAC-matrix completeness gate + the raw-DB counter-prior + `test_no_*` gate.
The full realization of the invariant.

- **Gate:** a custom declared route is mounted, auto-enforces permit/scope (403 for a denied
  role, 200 for permitted), and appears as an RBAC-matrix row; an undeclared domain route fails
  the matrix-completeness gate; the counter-prior fires on a raw-SQL custom handler.

## Model-driven failure-modes check (per CLAUDE.md)

1. **Which failure mode does this risk increasing?** *Hidden side-channel semantics* — we
   **reduce** it: custom routes move from an unanalyzed escape hatch into the declared,
   matrix-verified surface.
2. **Which detector catches it if we're wrong?** The RBAC-matrix completeness gate + the
   counter-prior/`test_no_*` policy gate + the validate-time conformance rules.
3. **Live or merely documented?** Live — CI security gate + validate + authoring-time
   counter-prior, not just docs.
4. **Can an engineer trace runtime behaviour to the AppSpec?** Yes — every route (generated or
   custom) is a declared `(entity, op)` with its permit/scope; the route set is derivable.
5. **Preserves auth/Postgres semantics, or pushes them to side code?** Preserves — the security
   model is applied by construction; the change *removes* the ungoverned-handler side-channel.

## Out of scope / deferred

- **Field-level response shaping** (a custom handler returning more than an entity's classified
  fields / PII leak). Connects to `classify`/`pii()` but is a separate concern; not v1.
- **Non-CRUD op vocabulary** for custom routes (ops beyond list/read/create/update/delete, e.g. a
  domain action). v1 binds custom routes to the existing five ops; richer op verbs can extend the
  binding later. Guarded transactional actions already have `atomic` (ADR-0028/0029).
- **GraphQL surface control** — `expose:` governs REST; GraphQL is retained as-is in v1.
- **Auto-migrating existing apps** — greenfield-friendly; no `api:` block = today's behaviour.

## Open items for the plan (not blocking the design)
- Exact home/keyword for the custom-route declaration (`interfaces:` vs a new sibling).
- How "dev profile" is detected for the Slice-1 guard (env / manifest flag / explicit opt-in).
- Whether the residue counter-prior can statically distinguish "raw DB for an undeclared entity"
  from legitimate advanced handlers (false-positive surface) — informs the gate's exact scope.
