# ADR-0040 — Conformant custom routes: the security model travels with the handler

**Status:** Accepted (2026-06-19) — **fully implemented** (#1420). D2/D4 shipped v0.83.12 (boot
conformance check + raw-DB counter-prior); **D3 (the RBAC-matrix completeness hard gate) shipped
v0.83.13** as `dazzle rbac routes --strict` + a per-example completeness test. Decision ratified in
brainstorming + this session. Builds on the Slice-1 fail-closed guard (v0.83.10) and Slice-2
`expose:` allowlist (v0.83.11). Relates to #1126, #1392, ADR-0025 (entity-level authz), the
provable-RBAC framework (`src/dazzle/rbac/`).

## Context

The #1420 invariant: **no route that touches a domain entity exists outside that entity's
permit/scope model, and the route set is a provable artifact (every route is an RBAC-matrix row).**
Slices 1–2 governed the *generated* routes. Slice 3 governs *custom* routes — the part that is
today an ungoverned escape hatch: a project's hand-written handler can read/write a domain entity
and never run permit/scope.

**Most of the binding machinery already exists** (verified, #1126 / v0.71.24):

- `route_overrides.py` discovers project handlers in `routes/*.py` via a **static declaration
  header** `# dazzle:route-override METHOD /path`. FastAPI first-match + `claimed_routes` (#1101)
  make the override win and suppress the generated route at the same path.
- A second header, `# dazzle:implements Entity.op via <param>`, opts the handler **into** the
  framework's permit/scope: `_wrap_with_policy_gate` wraps it so `policy.check_entity_op` runs
  **before** the body, raising `403`/`404` on denial (fail-closed). `check_entity_op` itself is
  fail-closed (no registry → `RuntimeError`; no auth'd user → `401` even for unprotected entities).

The gap is not *capability* — it's that conformance is **opt-in**. A handler that omits
`# dazzle:implements` silently bypasses the security model. The header is **statically scannable**
(read at discovery, not a runtime decorator), so conformance is *checkable without executing code*.

## Decision

### D1 — The custom-route binding is the existing `# dazzle:implements` header, not a new construct.

Reuse the static `# dazzle:implements Entity.op via <param>` declaration on route-override files.
**Rejected** alternatives: a new DSL `route:`/`endpoint:` construct (custom routes inherently need a
Python body — a construct would be a thin binding wrapper, and `interfaces:` is a *spec-generation*
construct (OpenAPI/AsyncAPI, `core/ir/governance.py`), not a route-mounter); a runtime
`@dazzle_route(...)` decorator (less statically analyzable than a header — defeats the "provable
route set" goal). The header is the conformant path **because it is scannable**.

### D2 — Conformance becomes structural: a domain-touching override without a binding is flagged.

Today, omitting `# dazzle:implements` silently bypasses authz. Make the secure path the enforced
path: a discovered route-override whose `(METHOD, /path)` shadows or shares an entity's generated
CRUD surface, but which carries **no** `# dazzle:implements` binding, is a **conformance violation**.
The handler body stays free Python; the *obligation to declare its entity+op binding* is mandatory.
(Pure non-domain routes — health checks, webhooks, a custom report with no entity write — are not
domain-touching and are exempt; the violation targets handlers that shadow/serve a domain entity's
routes.)

### D3 — The route set is matrix-complete: every domain route is an RBAC-matrix row (HARD CI gate).

Extend the provable-RBAC matrix (`src/dazzle/rbac/`) so every mounted domain route — generated *or*
custom — contributes an `(role × entity × op)` row. A custom route's row comes from its
`# dazzle:implements` binding. A domain-touching route with **no** matrix representation fails the
**CI security gate** (hard, per the brainstorm ratification). This is what makes the route set
*provable*: there is no domain route the matrix doesn't account for. (Ratified hard, not advisory.)

### D4 — A counter-prior catches the irreducible residue (raw DB access in a custom handler).

Structure can't constrain a Turing-complete Python body. A handler that declares
`# dazzle:implements Foo.read` but then does **raw SQL / constructs a repository for `Bar`** escapes
its declared binding. Add a counter-prior (`docs/counter-priors/`) + a `tests/unit/test_no_*.py`
policy gate (mirrors `test_no_bare_except_pass.py`) flagging raw-DB access / direct repository
construction in `routes/*.py` handlers. It fires at **authoring/code-gen time** via the
counter-prior catalogue, steering a coding agent toward `check_entity_op` before it ships. Blocking
(ratified), with a documented escape for genuinely-advanced handlers.

### D5 — `create`-mode binding keeps its #1126 limitation; the imperative form remains.

`_wrap_with_policy_gate` permit-gates `create` but can't scope-check the body payload (the row
doesn't exist yet). For full create-time scope, the handler calls the imperative
`check_entity_op(request, Entity, "create", payload=...)`. v1 of the conformance gate accepts a
`create` binding as satisfying D2/D3 (permit-bound); the counter-prior (D4) nudges toward the
imperative call where scope matters. No change to the #1126 wrapper semantics.

## Rejected alternatives

- **A new DSL construct for custom routes** (`route:` / `endpoint:`). Custom routes need a Python
  body; a construct is a binding wrapper that duplicates the existing header mechanism. `interfaces:`
  is spec-generation, not route-mounting. Rejected (D1).
- **A runtime `@dazzle_route(...)` decorator.** Binds at import time, not statically scannable —
  weakens the "provable route set" property the matrix gate depends on. The header is scanned at
  discovery. Rejected (D1).
- **Leave conformance opt-in (status quo).** The escape hatch this slice exists to close. Rejected (D2).
- **Advisory matrix gate / advisory residue lint.** The brainstorm ratified *blocking* — a coding
  agent routes around advisory warnings. Rejected (D3, D4).
- **Forbid raw DB in custom handlers structurally.** Can't, in Turing-complete Python — hence the
  counter-prior + lint residue tier rather than a structural ban. Rejected as infeasible; D4 is the
  achievable form.

## Framing — model-driven failure-modes check (per CLAUDE.md)

1. **Failure mode risked?** *Hidden side-channel semantics* — we **reduce** it: custom routes move
   from an unanalyzed escape hatch into the declared, matrix-verified surface.
2. **Detector if we're wrong?** The matrix-completeness CI gate (D3) + the raw-DB counter-prior/
   `test_no_*` gate (D4) + the existing fail-closed `check_entity_op`.
3. **Live or documented?** Live — CI security gate + authoring-time counter-prior, not just docs.
4. **Traceable to AppSpec?** Yes — every route is a declared `(entity, op)` with its permit/scope;
   the route set is derivable.
5. **Preserves auth/Postgres semantics?** Preserves — `check_entity_op` (the fail-closed primitive)
   applies; the change *removes* the ungoverned-handler side-channel. No session-identity change.

## Consequences

- **Runtime/tooling, not IR.** No new IR or lexer keyword (D1 reuses the header). New: a conformance
  check over discovered route-overrides (D2), an RBAC-matrix contribution from `# dazzle:implements`
  bindings + a completeness gate (D3), a counter-prior + `test_no_*` gate (D4).
- **Closes the #1420 invariant:** generated routes (Slices 1–2) + custom routes (this slice) are all
  permit/scope-bound and matrix-represented. The route set becomes provable end-to-end.
- **Greenfield-friendly / backward-compatible-ish:** existing overrides that already touch entities
  without a binding will newly fail the conformance gate — that is the point (they were the hole),
  but it is a breaking check for such projects; ship with a clear migration message + the escape.

## Implementation phases (under #1420 PLAN.md, phase-contract)
- **S3.1** — surface the `# dazzle:implements` binding in the route-override descriptor + parse it
  into a structured `(entity, op, via)` the matrix/conformance can read (much exists; formalize).
- **S3.2** — the conformance check (D2): a domain-touching override lacking a binding is a violation,
  surfaced at validate/boot. Reuse `_wrap_with_policy_gate` as the structural enforcement.
- **S3.3** — the RBAC-matrix completeness gate (D3) + the raw-DB counter-prior + `test_no_*` gate (D4).

## Out of scope / deferred
- Full create-time scope via the wrapper (D5 — imperative form remains the path).
- Non-CRUD custom op verbs beyond list/read/create/update/delete (guarded transactional actions are
  ADR-0028/0029's `atomic`).
- GraphQL custom resolvers (REST route surface only in v1).
