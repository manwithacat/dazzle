# DD-011: Rendering DSL-declared islands (`src:` / `title` / `fallback:`) — parked until a consumer mounts one from the DSL

```yaml
id: DD-011
status: PARKED
issues: []
adrs: [0011, 0053, 0057]
decided: 2026-10-14
decided_at_sha: bcb7323114bfdb13f7a9fe86a44e1a8789d2b05a
parent: flense-programme
```

## One-line intent

The `island` construct parses `title`, `entity:`, `src:` and `fallback:`, but
only `entity:` has a runtime effect (it mounts
`GET /_dazzle/islands/{name}/data`). Nothing renders an island: no DSL
construct references an island from a surface or workspace, so no page emits
its `<div data-island=…>` mount point, and `render.context.IslandContext` /
`PageContext.islands` are never populated. Flense ship N found this; ship R
keeps the construct (cyfuture and `examples/support_tickets` declare it), makes
`dazzle validate` warn when `title`/`src:`/`fallback:` are declared, and parks
rendering here instead of building it speculatively.

## Plan (what we already concluded)

The client half already exists and is not in question:
`page/runtime/static/js/dz-islands.js` mounts any
`<div data-island data-island-src data-island-props data-island-api-base>`,
rescans after htmx swaps and calls the module's cleanup on removal; the
signing flow (`signing/routes.py`) emits such a div by hand and is the working
reference. What is missing is the **reference** from a page to an island and
the server-side emission of the mount point.

When forced:

1. **Reference syntax** — add one way for a page to place an island. Prefer a
   workspace region display (`display: island` + `island: <name>`) over a new
   top-level construct, so the dashboard slot owns the card chrome and the
   card-safety invariants (`docs/reference/card-safety-invariants.md`) apply
   unchanged. The linker resolves `<name>` against `AppSpec.islands`
   (unknown name → validation error).
2. **Emission** — the region renderer emits the mount point with
   `data-island-src` (`src:`, defaulting to `/static/islands/{name}/index.js`),
   `data-island-api-base` (`/_dazzle/islands/{name}` when `entity:` is set,
   else empty) and the `fallback:` text as the escaped server-rendered body.
   `title` becomes the region heading through the slot, not inside the island.
   Populate `IslandContext` here rather than adding a second context type.
3. **Loader** — the page includes `dz-islands.js` when it contains at least
   one island; consumers stop needing `[ui] app_scripts` for it.
4. **Warning** — delete `validate_island_render_fields` (the DD-011 warning)
   in the same change.

Counter-priors: no SPA framework and no client-side routing (ADR-0011); an
island is a capability, never design-system chrome (ADR-0053 — if it grows
chrome, extract a Hyperpart); `fallback:` is rendered as escaped text, never
raw HTML from the DSL.

## Reopen when (consumer force)

1. **Named consumer** — cyfuture or AegisMark needs a DSL-declared island
   rendered on a page. cyfuture is the likely one: it declares
   `liveness_capture` and `video_call` (`entity: AMLVerification`) and ships
   `static/js/islands/liveness-capture.js` / `video-call.js` with the
   `mount({ el, props, apiBase })` contract, but nothing in cyfuture emits
   their mount points today.
2. **Evidence of host workaround** — a consumer hand-writing
   `<div data-island=…>` in a custom route or `render:` surface to mount a
   DSL-declared island.
3. **Acceptance that unblocks** — the consumer's page renders the island's
   mount point from the DSL alone, `dz-islands.js` mounts it, and
   `dazzle validate` no longer warns for that island.

When a force lands:

1. Set `status: FORCED` and date it.
2. Comment on every linked issue with the consumer + this DD path.
3. Implement against the plan above; open child issues if the plan splits.
4. When shipped, set `status: DONE` and close issues.

## Already shipped (do not re-litigate)

- `island` construct, `IslandSpec`, parser (`core/dsl_parser_impl/island.py`).
- `entity:` → `GET /_dazzle/islands/{name}/data` (`http/runtime/island_routes.py`,
  mounted in `app_factory`).
- Client loader `dz-islands.js` and the signing-pad island.
- `dazzle validate` WARNING for declared-but-unrendered `title`/`src:`/`fallback:`
  (`core/validation/ux.validate_island_render_fields`, flense ship R).

## Explicitly out of scope until force

- Island props declared in the DSL (`props:` — the docs never had a parser
  for it); per-island CSS bundling; island-to-island events.
- Removing the construct: consumers declare it, and `entity:` is live.

## Trail

| Date | Event |
|------|--------|
| 2026-10-14 | Parked (this DD), flense ship R |
