# UX-maturity primitive roadmap

The companion to the [framework UX-maturity rubric](../reference/ux-maturity.md).
The rubric *scores*; this *sequences the work*. Premise (per the maturity
ladder): **every criterion implies primitive work** — a level-2 criterion needs a
right-by-default primitive; a level-3 criterion needs the *inference* step that
takes it to **4 (adaptive)**. Even the green ones (`3b`, `3e` at 4) define the
bar the others should clear, not a finish line.

`dazzle ux maturity` is the baseline (v0.88.0: overall **2.62**). This doc maps
each of the 13 criteria to its target primitive, and — crucially — to **how it
should be built**, because the criteria split into two implementation classes
with very different cost/risk.

## Two implementation classes

- **(S) Server-render / IR primitives.** Pure Dazzle: DSL grammar → IR → renderer.
  No client involvement. This is *all* of data-drives-UI (1a–1d) plus the
  inference steps for the negative-space criteria. The cost is IR + renderer
  work; the risk is low (typed-Fragment substrate, no escape hatch).
- **(H) Declarative-over-htmx-4 primitives.** The interaction criteria
  (progressive disclosure 2b–2d; interaction-shaped negative space 3a/3d). These
  must NOT be hand-written JS — per the SSR+htmx doctrine, a DSL keyword wraps a
  native htmx-4 trigger / a vendored extension, keeping markup semantic,
  class-light, build-free, and agent-legible (Locality of Behaviour). htmx 4
  moved several of our learned requirements into *direct expression*, which makes
  this class cheaper than it was at htmx 2.

## The htmx-4 examination — does it express our learned requirements?

Read against the htmx-4 (`four-dev`, 4.0.0-beta4) source + extension set. The
answer is **yes for the interaction layer, no for the data layer** (the data
layer was never htmx's job).

| htmx-4 capability | native / ext | Expresses (criteria) | Verdict for Dazzle |
|---|---|---|---|
| `intersect` / `revealed` triggers | native | lazy region; reveal-rest; row-peek-on-scroll | **adopt** — already used (`fold_count` lazy regions) |
| `every Ns` polling | native | live dashboards | **adopt** — already `refresh: every Ns` |
| **`morph` swaps** (idiomorph in core) | native | every in-place update keeps focus/scroll/input | **adopt** — already default |
| **View Transitions** (`transition:true`) | native | answer-first nav, drill (2a/2b) | **adopt** — already wired |
| **`hx-optimistic`** | ext (NEW in 4) | optimistic inline-edit / action (2c) | **adopt** — *reverses the doctrine's "no optimistic-render" gap*; the row-peek/inline-edit primitive can now be optimistic declaratively |
| **`hx-upsert`** | ext (NEW in 4) | live list/row insert-or-update by id (2c, live `1c`) | **adopt** — declarative live-collection maintenance, no custom JS |
| **`hx-preload`** | ext | drill perceived-perf (2b) | **adopt** — preload detail on hover/intersect |
| **`hx-ptag`** | ext | skip-unchanged polling (efficient live regions) | **adopt** — ETag-style refresh for `every Ns` regions |
| `hx-ws` / `hx-sse` | ext | realtime push | adopt-as-needed (SSE already triggered) |
| **`hx-live`** (reactive `q()` signal graph) | ext | client reactive expressions | **AVOID** — a Datastar-shaped client signal graph; breaks Locality of Behaviour and agent-legibility (the doctrine's explicit rejection). Not a path to any criterion worth the cost. |

**So:** the interaction primitives below are *thin declarative wrappers over
native triggers + the `hx-optimistic` / `hx-upsert` / `hx-preload` / `hx-ptag`
extensions* — no bespoke JS, no build chain. The data primitives are pure
server-side. And one explicit non-goal: do **not** reach for `hx-live` to fake
client reactivity.

## Per-criterion roadmap

| # | Criterion | now→target | Primitive (the work) | Class | htmx-4 leverage |
|---|---|---|---|---|---|
| **1a** | region form inference | 2→4 | **`display: auto`** — infer the region form from the source's data shape (temporal field → timeline/trend; ordered-state enum → board; grouped count → chart; scalar → metrics; else list). **Generalise, don't build:** a *partial* ad-hoc inference already exists (aggregate→SUMMARY EX-047/#1082 in `workspace_renderer`; a kanban auto-promotion) — unify these into one `resolve_auto_display(region, entities)` and extend with the temporal/state rules. | S | — |
| **1b** | semantic-state binding | 2→4 | **`semantic:` on enums** — declare a status field's lifecycle role (`open=warning, done=positive`), validated against the token palette; retire the `_STATUS_TONE_MAP` name guess. Tone+icon then *inferred* from the declared role. | S | — |
| **1c** | comparison context | 2→3→4 | **scalar-with-context default** — a `metrics` tile defaults to delta/trend/rank when a comparison source exists; at 4, infer the comparison from the aggregate's grain. | S | — |
| **1d** | raw-data honesty | 3→4 | **exhaustive format coverage + inference** — close the residual leaks (ISO datetime, JSON, nested ref) and infer format from column type everywhere (not just list cells). | S | — |
| **2a** | answer-first landing | 3→4 | **landing inference** — pick the persona's default workspace/region order from their rhythms/stories, not hand-set `default_workspace`. | S | view-transitions (already) |
| **2b** | depth ≤1 action | 3→4 | **preload-drill** — drill is default; add `hx-preload` so the detail is warm on hover/intersect (perceived 0-cost). | H | `hx-preload`, view-transitions |
| **2c** | action-proximate detail | 2→4 | **`peek:` / inline-edit primitive** — declarative row-peek (expand-in-place) + click-to-edit, **on by default** where the entity has a detail surface; optimistic via `hx-optimistic`. | H | native `intersect`/`<details>`, **`hx-optimistic`**, `hx-upsert` |
| **2d** | field economy | 2→4 | **`priority:` columns** — show top-N by declared/inferred priority, reveal the rest via a `revealed`-triggered lazy expand. At 4, infer priority from field salience. | H | native `revealed` |
| **3a** | frequency-weighted prominence | 2→4 | **action prominence inference** — rare actions auto-demote to overflow / ⌘K; common ones stay primary, derived from usage. The palette is native (`<dialog>`), the *placement* is the primitive. | S (+native) | — |
| **3b** | role-gated affordance | **4** | *bar, not work* — provable RBAC matrix already infers role-gated visibility. Keep as the reference for the others. | S | — |
| **3c** | state-gated affordance | 3→4 | **transition-driven affordances everywhere** — any action (not just buttons) auto-appears only when the state graph allows it; today partial. | S | `hx-put` (action mechanism) |
| **3d** | empty-state suppression | 2→4 | **self-suppressing region** — an empty lazy region removes/collapses itself instead of rendering dead scaffolding; declarative `when_empty: suppress`. | H | native `intersect` + `hx-upsert`/`<partial>` (`hx-ptag`) self-remove-on-empty |
| **3e** | scope concealment | **4** | *bar, not work* — `scope:` → predicate algebra + RLS already conceals by construction. Reference for negative space. | S | — |

## Sequencing (highest leverage first)

1. **1a `display: auto`** *(S)* — the single highest-leverage gap; the vocabulary
   exists, this adds the chooser. Retires "table-by-default" across every app.
2. **1b `semantic:` on enums** *(S)* — cheap, app-wide credibility; turns colour
   from a guess into a declared+validated binding.
3. **2c `peek:` + inline-edit** *(H)* — first declarative-over-htmx-4 primitive;
   proves the `hx-optimistic`/`intersect` wrapper pattern. High user-visible value.
4. **3d self-suppressing region** *(H)* — kills `empty_on_path` dead scaffolding;
   small, native-`intersect`-backed.
5. **2d `priority:` columns** *(H)* — field economy via `revealed` lazy reveal.
6. **1c comparison-default / 1d format closure / 2b preload-drill / 3a placement
   / 2a + 3c inference** — the level-3→4 *inference* steps, after the level-2
   gaps are primitives.

After each lands, re-run `dazzle ux maturity --drift`: the probe should flip
(e.g. a `display: auto` key appears → 1a's probe trips → re-score 1a upward). The
drift gate makes the roadmap self-measuring — a shipped primitive is a forced
re-score, not a manual edit.

## Guardrails (carried from the SSR+htmx doctrine)

- Interaction primitives are **declarative wrappers over native htmx-4 / vendored
  extensions** — never bespoke per-app JS, never a second client app.
- **No `hx-live`** — no client reactive signal graph; everything that matters
  round-trips (server is the source of truth; `morph` preserves focus for free).
- A missing capability is a **framework RFC**, not a `mode: custom` surface
  (custom-renderer reach for one of these is itself the maturity signal the
  rubric's attribution rule promotes).
