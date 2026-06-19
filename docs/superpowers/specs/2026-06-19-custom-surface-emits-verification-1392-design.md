# Custom-surface emitted-target verification (#1392 item 3) — Design

**Status:** Approved (2026-06-19). Decomposed slice of #1392 ("let custom renderers /
route-overrides opt back into the framework's structural guarantees"). Items 1 (non-empty
output contract, v0.82.66) and 4 (conformance harness, v0.82.77) shipped. This spec covers
**item 3** (build-time emitted-target crawl). Item 2 (chrome-enforced custom mode) is a
separate later pass, blocked on the `build_app_page_context` extraction decision.

## Problem

The structural protection a *declarative* surface enjoys — dead `primary_action -> surface`
references fail the **build** (`LinkError`) — evaporates the moment a surface goes
`render: <custom>` or a `# dazzle:route-override` takes over. A custom renderer's emitted
`<a href>` / `<form action>` / paired JS `fetch()` targets are never verified against the
route registry, so a dead button or a typo'd / renamed / deleted target ships **green** and
404s only when a user clicks it (the AegisMark "dead buttons all green" report).

## Goal

Let a custom surface **declare** the routes/surfaces it links to, and have the linker fail
the build when a declared target resolves to nothing — the custom-mode analogue of the
existing `primary_action -> surface` resolution check. Opt-in and incremental: a custom
surface with no declaration is unconstrained (today's behavior); declaring `emits:` buys back
the dead-target gate.

## Non-goals (YAGNI)

- **Not** render-and-crawl: v1 does not render custom surfaces to detect *undeclared* emitted
  links. It verifies *declared* targets resolve (catches typos, renames, deletions). The
  conformance harness (item 4) can cross-check declared-vs-actual later.
- **Not** item 2 (chrome enforcement) — separate pass.
- **Not** a fix for #1421. #1421 is a *framework*-emitted `/app/<slug>/{id}` page-route bug,
  not a custom-emit declaration gap. Distinct issue.

## Architecture — two declaration sites, one resolver, one build gate

### 1. `render:` / `mode: custom` surfaces — DSL `emits:` clause

A new optional surface clause naming the **surfaces** the custom renderer links to:

```dsl
surface task_board "Board":
  uses entity Task
  mode: custom
  render: kanban_viewer
  emits: [task_detail, task_create]
```

- New IR field `SurfaceSpec.emits: tuple[str, ...]` (default `()`; `()` = undeclared/unconstrained).
- New lexer keyword `emits` + a surface-block parser arm (mirrors how other surface clauses
  parse a bracketed name list).
- Each name must resolve to a **declared surface** in the AppSpec — the same registry and
  failure mode as `primary_action -> surface`.

### 2. Route-overrides — `# dazzle:emits <path>` header

A scannable header alongside `# dazzle:route-override` (no IR — runtime/tooling, mirrors
`# dazzle:implements`, #1126):

```python
# dazzle:route-override GET /app/board
# dazzle:emits /app/tasks/{id}
def board(request): ...
```

- New `_EMITS_RE` in `route_overrides.py`; the discovered descriptor gains
  `emits_paths: tuple[str, ...]`.
- Each path must match a **mounted route**: a generated CRUD route, another route-override,
  or a page route.

### 3. Resolver + build gate

A linker validation pass `validate_emits_targets(appspec, overrides, route_paths)`:

- For each surface with a non-empty `emits:`, every name must be a known surface
  (`appspec.surfaces`). Unknown → error `E_DEAD_EMIT_TARGET`.
- For each route-override with `emits_paths`, every path must resolve against the route
  registry (generated routes + route-override paths + page routes), with path-template
  matching (`{id}` placeholders normalized). Unresolvable → error `E_DEAD_EMIT_TARGET`.
- A dead target is a **build error** (matches the issue's "fail the build on a dead target"
  and the existing `primary_action -> surface` check). Wired into the `dazzle validate` /
  lint pass (alongside the existing surface validators).

Opt-in: no `emits:` / no `# dazzle:emits` ⇒ no new constraint (incremental safety net).

## Model-driven failure-modes check (per CLAUDE.md)

1. **Failure mode risked?** *Hidden side-channel semantics* — a custom renderer's link graph
   living outside the analyzable AppSpec. We **reduce** it: the targets become a declared,
   linker-verified edge.
2. **Detector if wrong?** The new `E_DEAD_EMIT_TARGET` build gate + the existing route/surface
   registries.
3. **Live or documented?** Live — runs in `dazzle validate` / CI, not just docs.
4. **Traceable to AppSpec?** Yes — each `emits:` target is a declared name/path resolving to a
   known surface/route; the custom surface's outbound edges are now in the graph.
5. **Preserves Postgres/auth/workflow/UI semantics?** Yes — pure build-time link check, no
   runtime/semantic change. It *adds* graph coverage the custom escape hatch had removed.

## Components & boundaries

| Unit | Responsibility | Depends on |
|------|----------------|------------|
| `SurfaceSpec.emits` (IR) | Hold declared surface targets | — |
| lexer `EMITS` + surface parser arm | Parse `emits: [a, b]` | lexer, surface parser |
| `route_overrides._EMITS_RE` + descriptor `emits_paths` | Scan `# dazzle:emits` header | route_overrides discovery |
| `validate_emits_targets` | Resolve declared targets, emit `E_DEAD_EMIT_TARGET` | surface registry + route registry |
| lint/validate wiring | Run the pass in `dazzle validate` | lint.py |

## Testing

- **Parser:** `emits: [task_detail]` round-trips into `SurfaceSpec.emits`; an `emits:` naming
  an unknown surface → build error at validate.
- **Header scan:** `# dazzle:emits /app/tasks/{id}` parsed into `emits_paths`; a dead path → error.
- **Resolver:** valid targets resolve clean; dead surface name and dead path each error with
  `E_DEAD_EMIT_TARGET`; undeclared (no `emits:`) is unconstrained.
- **E2E / dogfood:** an example or fixture custom surface declares `emits:` and passes
  `dazzle validate`; flipping a target to a nonexistent name fails validate.

## Implementation phases (for writing-plans)

- **P1 — IR + parser for `emits:`** (SurfaceSpec.emits, lexer keyword, surface parser arm, tests;
  ir-types baseline regen).
- **P2 — route-override `# dazzle:emits` header** (scan + descriptor field, tests).
- **P3 — resolver + build gate** (`validate_emits_targets`, wire into validate/lint, `E_DEAD_EMIT_TARGET`, tests).
- **P4 — dogfood + docs** (one example/fixture custom surface declares `emits:`; reference docs;
  CHANGELOG; close #1392 item 3, note item 2 remains).
