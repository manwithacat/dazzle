# Identifying Implicitness in Dazzle

**Status:** working doc, updated after the v0.57.69 post-mortem.

## The principle

Dazzle is consumed primarily by agents, not humans. Humans fill in implicit meaning automatically — "admin has universal access", "the first persona in the list is probably the privileged one", "a workspace nobody owns is probably broken". Agents traversing the DSL don't have that reflex. Every implicit convention in the framework is a latent failure mode the moment an agent is the consumer.

The goal of this document: enumerate the implicit-conventions we've already found, describe how we caught each one, and propose cheap-to-run heuristics for finding more.

## Catalogue of conventions we found (and what each cost us)

### `appspec.personas[0]` ≡ "universal-access persona"

**Where it lived:** fallback in `_pick_workspace_check_persona` and several other CLI code paths.

**The assumption:** projects declare admin first. Therefore personas[0] is the persona with the broadest access, which makes it a safe default when no other signal is available.

**Where it broke:** support_tickets declares admin first, but admin's `default_workspace` is `_platform_admin` (the framework-generated admin UI), not any of the app's workspaces. The runtime's access-control layer correctly returned 403 when admin tried to load persona-gated workspaces. The contracts checker reported three false-positive failures.

**Fix shipped in v0.57.69:** reverse-lookup via `default_workspace` before falling back to positional ordering. 5 unit tests pin the decision tree.

**Framework-level lesson:** add a structural concept of a privileged / admin persona. Either:

- `persona admin "Administrator": admin: true` as a boolean flag on the persona IR, or
- `persona` → `admin_persona` as a distinct top-level construct.

Then code that wants "the highest-access persona" asks for `appspec.admin_persona`, not `personas[0]`. If the project has no admin persona, the API returns `None` and callers must handle it explicitly — no more implicit fallback.

### `default_workspace` points workspace → persona, but nobody reverse-walks it

**Where it lived:** the DSL relation `persona.default_workspace: X` was only consumed one-way (workspace→persona redirect at login). Nothing computed the inverse (workspace→its owning persona).

**Where it broke:** the picker didn't know agent owns `ticket_queue` because it never walked the personas looking for `default_workspace == "ticket_queue"`.

**Fix shipped in v0.57.69:** picker now walks the inverse.

**Framework-level lesson:** every IR relation should be queryable in both directions. Surface a named helper — e.g. `AppSpec.persona_owning(workspace_name)` — so code consuming the implicit ownership graph doesn't have to re-derive it each time. The `_lint_workspace_access_declarations` validator at `validator.py:1449` already does this correctly at validate time; the runtime just wasn't using the same function.

### `access:` block absence ≡ "all authenticated users can reach this"

**Where it lived:** workspace runtime access-control.

**Where it's OK:** the linter already flags this (`validator.py:1449`) and the runtime grants access explicitly once a persona claims the workspace via `default_workspace`. This convention is well-formed in that the DSL has an escape hatch (explicit `access:` block) and a validate-time warning when neither signal is present.

**Lesson:** this is a counter-example — an implicit default that's been made explicit by surfacing both the validator warning and the runtime inference. The test is: *a reader (human or agent) can derive the runtime behavior without extra-DSL knowledge*. `access:` block → visible explicit rule. `default_workspace` reverse-lookup → visible implicit rule. Nothing else.

## Heuristics for finding more implicit conventions

Each of these is cheap to run against the framework and cheap to keep running as a regression gate.

### Heuristic 1: grep for positional indexing into IR lists

Positional indexing (`personas[0]`, `entities[0]`, `workspaces[0]`) is almost always a hidden convention. The position has semantic meaning (first persona = admin, first entity = root) that isn't visible from the list type.

```
rg '(?:personas|entities|workspaces|surfaces|scenarios)\[0\]' src/
```

Every hit is a candidate implicit convention. For each, ask: *what property of that element is the caller actually looking for?* Add a named accessor.

Status as of v0.57.69: this grep returns **25 hits across 15 files**. Many are legitimate (e.g. parsing the first scenario line in a file). But each hit is worth the question: *is this position semantic?* A dedicated audit pass would put each remaining hit in one of three buckets: **legitimate** (truly just "the first element, no semantic load"), **convention** (position has meaning, should become a named accessor), or **stale** (the position-based assumption is already broken in some project layout).

### Heuristic 2: agent-readable DSL property test

Given a stripped-down AppSpec and a natural-language question ("who has access to workspace X?", "what entities does persona Y manage?"), can an agent armed *only* with the DSL — no source code, no framework internals — answer correctly?

If not, the DSL is relying on implicit framework knowledge. Either (a) change the DSL so the answer is derivable, (b) add a canonical MCP tool so the agent has a named way to ask, or (c) accept it's not agent-readable and document that exception.

Status: the MCP `graph` and `knowledge` tools cover a lot of these questions already. Gaps worth checking: persona/workspace ownership graph, access inheritance across roles, scope interactions across entities.

### Heuristic 3: "every structural claim needs a generator and a verifier"

Each of the framework's structural invariants should be enforceable at *two* layers:

- A validate-time check that flags violations of the invariant in the DSL (the *generator* cares about input shape).
- A verify-time check that asserts runtime behavior matches the invariant (the *verifier* cares about output shape).

When only one layer exists, the other is implicit. The card-safety invariants (INV-1..INV-9) cover both; the access-control rules only partially do — there's no test that says "if the DSL declares workspace X is gated to persona P, the runtime actually returns 403 to not-P."

Status: the new `contracts-gate` CI job in `.github/workflows/ci.yml` closes some of this for access-control at the workspace level. Entity-level access-control has similar gaps.

### Heuristic 4: reflect on every post-mortem

After closing a bug, ask:

1. What implicit knowledge did the buggy code assume?
2. Who else in the codebase assumes the same thing?
3. Can that assumption be named (type, property, method) so future callers can ask for it explicitly?

The v0.57.69 bug was "personas[0] means admin". The v0.57.67 bug was "data-dz-region-name is in SSR HTML". Both were implicit data flows between layers, caught only after they shipped. Both would have surfaced earlier if the rule had been: *every cross-layer signal must be named, not positional or timing-dependent*.

## When to stop

Making everything explicit isn't free. An over-specified DSL is also hard for agents — more syntax, more rules, more rejected valid-looking inputs. The test is: *does removing this implicitness stop a real class of bugs, or is it defensive padding?*

The v0.57.69 bug cost a cycle of diagnosis and a round-trip to AegisMark. That's well past the threshold for making admin-access explicit. An imagined bug about "someone might not realize entities are declared in file order" is not.

Save the explicitness budget for patterns that have already burned us once. Ship the gate, run the heuristic, and wait for the next incident to tell us where the next one is.
