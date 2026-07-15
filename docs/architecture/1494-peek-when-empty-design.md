# Design: `peek:` (2c) + `when_empty:` (3d) — the first declarative-over-htmx-4 primitives

**Issue:** #1494 · **Epic:** #1491 (UX-maturity primitive roadmap) · **Status:** approved design, not yet implemented
**Rubric:** `docs/reference/ux-maturity.md` · **Roadmap:** `docs/architecture/ux-maturity-primitive-roadmap.md`

These are the first two **Class-(H)** primitives — *declarative wrappers over native
htmx-4 triggers + vendored extensions*, no bespoke per-app JS (SSR+htmx doctrine,
Locality of Behaviour). htmx **4.x beta is already the vendored runtime** (pinned `HTMX_PINNED_VERSION`, currently 4.0.0-beta5), so
the native layer is buildable today; this design also vendors two new beta
extensions (`hx-optimistic`, `hx-upsert`) — a deliberate, accepted bet on the
4.x beta extension API ahead of GA (#1409).

## Decisions (locked in brainstorming)

1. **Scope** — full RFC, both primitives, vendoring the beta extensions now (accepting beta-churn risk).
2. **`peek:` form** — unify with the existing `slide_over` flag. `peek:` is the single entry point; `slide_over: true` becomes a deprecated alias for `peek: slide_over`.
3. **`peek:` default** — **right-by-default**: `peek: expand` when the entity has a detail surface; `peek: off` opts out. (Closes 2c to level 4.)
4. **`when_empty:` default** — **right-by-default by region role**: a lazy/secondary region that resolves empty self-suppresses; the **primary** collection keeps its typed empty-state + create-CTA. (Closes 3d to level 4.)

## §1 — DSL surface

```dsl
surface task_list "Tasks":
  uses entity Task
  mode: list
  peek: expand              # expand | slide_over | off
                            # default: expand when the entity has a detail surface, else off
  section main:
    region recent_activity:
      when_empty: suppress   # message | suppress | collapse
                             # default: message for the primary collection,
                             #          suppress for a lazy/secondary region
```

- **`peek:`** — surface/list-level clause.
  - `expand` — inline expand-in-place (accordion row).
  - `slide_over` — the existing side panel.
  - `off` — plain drill to the detail page (pre-#1494 behaviour).
  - **`slide_over: true`** parses to `peek: slide_over` and emits a deprecation
    diagnostic (clean break preferred, but the alias keeps existing example DSL
    valid within the same commit per ADR-0003's "update all callers").
- **`when_empty:`** — per-region clause: `message` (today's typed empty-state),
  `suppress` (region self-removes), `collapse` (keep header, drop body).

## §2 — IR + parser

- `SurfaceSpec.peek: PeekMode | None` and `WorkspaceRegion.when_empty: WhenEmpty | None`
  (`None` = author wrote nothing → the resolver picks). A **true-unset
  discriminator** distinguishes "unset" from an explicit value, mirroring
  `WorkspaceRegion.display_unset` (#1492). Likely shape: a sentinel default plus
  a `peek_unset`/`when_empty_unset` bool, or `Literal[...] | None` where `None`
  is unambiguous because the parser only ever sets a concrete value.
- Parser: one keyword arm in the surface dispatcher (`peek`) and one in the
  region dispatcher (`when_empty`); the existing `slide_over` arm gains the
  alias + deprecation warning. Round-trip + true-unset covered by parser tests.
- Grammar: add both clauses to `docs/reference/grammar.md`; both lists are
  drift-gated (`tests/unit/test_docs_drift.py`).

## §3 — Render: native htmx-4 layer (no extension needed)

- **`peek: expand`** — each list row gains a chevron affordance (`aria-expanded`,
  `<details>`-semantics) that `hx-get`s the entity's **detail partial** into an
  inserted sibling row beneath it; collapsing removes the inserted row. Reuses
  the existing detail renderer's field rendering — *the panel is the same detail
  body the drill page shows*, so there is one detail renderer, not two.
  - **Click-to-edit** — the detail partial's `Edit` toggle `hx-get`s an
    **edit partial** that swaps the view fields to inputs in place; `Save`
    `hx-put`s and swaps back to the view partial.
- **`when_empty: suppress`** — a lazy (`intersect`-triggered) region whose fetch
  resolves to an empty result returns a **self-removing partial**: the region
  placeholder is removed via a native swap (`hx-swap` delete / OOB removal of the
  region wrapper). No new extension required for this primitive.
  - `collapse` — return a header-only fragment (body omitted).
  - The empty/non-empty decision is **server-side** (the region fetch already
    knows its count), so suppression never flashes dead scaffolding.

## §4 — Beta extensions (vendored now)

- Vendor `hx-optimistic` + `hx-upsert` (htmx 4.x beta) into
  `static/vendor/`, wire into `scripts/update_vendors.py` (pinned version,
  provenance-checked + `sourceMappingURL`-stripped per the #1467/#860 lessons),
  and add to the dist bundle (`scripts/build_dist.py` + `css_loader`/JS bundle
  list). Bump the bundle fingerprint (#1468).
- **`hx-optimistic`** — on click-to-edit `Save`: render the edited value
  immediately, roll back to the prior view partial on a non-2xx response. This
  *reverses* the doctrine's old "no optimistic-render" gap, declaratively.
- **`hx-upsert`** — on `Save`: the edited row updates **in place by id** (no
  full-list refetch).
  - **Scope boundary:** local *edit → row-refresh* only. Multi-user live-insert
    of *other* users' new/changed records (needs an SSE/poll trigger feeding the
    upsert) is **out of scope** for #1494 — a later "live collections" RFC.

## §5 — Defaults, probes, self-measuring re-score

- `resolve_peek_mode(surface, entity) -> PeekMode` and
  `resolve_when_empty(region, is_primary) -> WhenEmpty` — the right-by-default
  resolvers (mirror `resolve_region_display_mode`, #1492). An explicit author
  value always wins; `None` → the role-derived default.
- `_probe_2c` (today: `TableContext.slide_over` manual flag) and `_probe_3d`
  strengthened to assert the resolvers + render wiring exist; **`2c` and `3d`
  baselines bump 2 → 4** in `qa/ux_maturity.py` (drift-gated by
  `tests/unit/test_ux_maturity_baseline.py`). Per the roadmap's self-measuring
  contract, a shipped primitive is a *forced* re-score, not a manual edit.

## §6 — Expected churn

- **Fleet list goldens** — every list whose entity has a detail surface grows
  peek wiring (chevron + `hx-get`). Regenerate + inspect per slice.
- **Dashboards** — empty lazy/secondary regions disappear. Inspect for any
  region that should have stayed (override with `when_empty: message`).
- **UX catalogue** — regenerate (`scripts/gen_ux_catalogue.py`); add a
  `peek`/`when_empty` catalogue mode + manifest marker.
- **Card-safety invariants** (`docs/reference/card-safety-invariants.md`) — the
  expanded panel is new DOM in the list region; run the composite gate
  (`tests/unit/test_htmx_workspace_composite.py`) on the post-expand DOM.

## §7 — Slice plan (4 shippable slices)

1. **`peek:` IR + parser + `expand` render** (native) — chevron + detail-partial
   insert; `slide_over` alias + deprecation; default resolver wired but **off**
   (opt-in) so this slice is byte-stable on the fleet.
2. **Click-to-edit + optimistic + upsert** — vendor `hx-optimistic`/`hx-upsert`;
   view⇄edit partial swap; optimistic save + row upsert-by-id.
3. **`when_empty:` IR + parser + suppress/collapse render** (native) — resolver
   wired but default `message` (opt-in) so byte-stable.
4. **Default-flip + probes + baselines + catalogue** — flip `peek:` default to
   `expand` (opt-out) and `when_empty:` to role-derived; bump the `2c`/`3d`
   baselines 2 → 4; regenerate fleet goldens + catalogue; CHANGELOG
   agent-guidance.

Slices 1 & 3 land byte-stable (resolver present, default off); slice 4 carries
the deliberate fleet churn behind the default-flip — mirroring the #1492
`display: auto` and #1493 `semantic:` default-flip pattern (low-risk primitive
first, churn isolated to the flip).

## §8 — Model-driven failure-mode check (per CLAUDE.md)

- **Risk mode:** "magic default behaviour the author can't trace" (MDE
  over-abstraction). **Detector:** the `peek_unset`/`when_empty_unset`
  discriminator keeps the resolved value inspectable; `dazzle inspect`/the
  rendered `data-*` attrs trace the runtime DOM back to the surface clause.
  **Live?** yes — the drift probe + golden goldens make the default observable.
- **Preserves semantics?** yes — peek reuses the one detail renderer + the
  normal `hx-put` mutation path (RBAC/scope/state-machine unchanged); suppression
  is a render-time presentation choice over the existing scope-aware count.
- **Escape hatch is a keyword, not `mode: custom`** — `peek: off` /
  `when_empty: message` are first-class, so reaching for a custom renderer here
  would itself be the maturity signal the rubric promotes.

## Disposition

This is **large** (2 primitives + extension vendoring + fleet regen). Per the
issue-loop Tier-3 path, this spec is saved and #1494 stays **open**; a dedicated
implementation session expands §7 into a task-level plan (writing-plans) and
ships the four slices.
