# AGENTS.md — HaTchi-MaXchi for coding agents

This file is the **always-on** entry for agents (Claude Code, Copilot, Cursor, …).
It is deliberately short. Everything it names is either **normative** (follow it)
or **linked** (open when the situation matches). Prefer machine-checkable
artefacts over gallery chrome.

## How to read this package (curriculum)

Reconstruct understanding **in this order**. Do not skip to inventing markup.

| Step | Open | When |
|:----:|------|------|
| 1 | **This file** | Always |
| 2 | **`stems/INDEX.md`** | Framework + package stems (compressed judgement) |
| 3 | `docs/agent/pick-a-surface.md` | Choosing a control / interaction shape |
| 4 | `site/agents/<id>.md` | Implementing one Hyperpart |
| 5 | `CONSUMER_MAP.md` + `CONTRACT_SURFACE.md` | Changing a shared surface or host |
| 6 | `docs/agent/compose-or-refuse.md` | Building a host that embeds or refuses children |
| 7 | `docs/agent/mutate-a-primitive.md` | Editing CSS/JS/contracts of an existing part |
| 8 | `docs/agent/invent-safely.md` + `contracts/AUTHORING.md` | Tempted to add a Hyperpart |
| 9 | `docs/decisions/*` | Decision history (expressions of stems) |

**Authority hierarchy** (higher wins on conflict; then fix the lower artefact):

1. **Machine truth** — `site/registry.py`, dual-lock contracts, CI gates, committed maps
2. **`stems/`** — package stems (see also monorepo `stems/` for framework)
3. **This file** — what to do now
4. **`docs/decisions/`** — dated decision expressions of stems
5. **`docs/agent/`** — how to act in a class of situations
6. **`site/agents/<id>.md`** — unit card for one part (generated spine)
7. Gallery HTML / `MOCK_HTMX` — demo only, never product API

If the model and the maps disagree, **the maps and tests are the organisation**.

## What this is

An htmx4-native design system. The unit of reuse is a **Hyperpart**: a
server-rendered **partial** + its **exchange contracts** (request/response the
server must satisfy) + optionally a vanilla-JS **controller** and **extensions**.

There is **no client state graph**. State lives on the server and in the DOM.
Hyperparts are **not** React components, Server Components, or a prop/event tree.
Composition is **declared host embedding** (and explicit refusal), not imports.

**htmx4 / morph:** prefer morphing for *stable* surfaces (shells, tables, forms);
replacement for disposable fragments. Stable IDs and DOM-carried state are
load-bearing. **Alpine is not HM core** — delegated vanilla controllers only.
Reconstruct: `stems/morph-safe-hypermedia.md` (decisions 0005–0008).
Lint fixtures: `python packages/hatchi-maxchi/tools/template_lint.py`
(`--compose grid`, `--file partial.html`).

## Two audiences (same Hyperpart, different entry)

| Audience | Who | What the agent should do |
|---|---|---|
| **Dazzle** | Founders / vibe coders building SaaS without deep stack knowledge | Treat Dazzle as the product surface. Emit SSR + wiring from the app model; HM supplies the design system the runtime already knows. Prefer monorepo dual-lock (`dz-` / `data-dz-*`) and Dazzle emitters over hand-rolled FastAPI. |
| **Standalone HM** | HTMX4 developers (often with agent support) who own their server | Read each part as: **this markup** (Copy this) → **this DOM contract** → **this API shape** (Server exchange + optional `server_example`). Wire `hx-*`; return HTML fragments, not JSON. |

Humans on HTML part pages get glossary tooltips; agents prefer this file, playbooks,
tables, and `agents/<id>.md`. Do **not** scrape tooltip attributes as the contract.

## Stems (reconstruct these first)

Full text: **`stems/INDEX.md`**. These few ideas generate most correct local
decisions. Decisions under `docs/decisions/` are **expressions** of the same stems.

| Stem | One-line reconstruction | Stem file |
|------|-------------------------|-----------|
| **Hyperpart** | Partial + exchange (+ optional controller)—not a component | `stems/hyperpart-not-component.md` |
| **Three layers** | L0 recipe → L1 surface → L2 host | `stems/three-layers.md` |
| **Declared composition** | `composes` / `does_not_compose` / extensions | `stems/composition-declared.md` |
| **Invention ladder** | Reuse → refuse+spike → promote → new part | `stems/invention-ladder.md` |
| **Morph-safe hypermedia** | htmx4 morph for stable surfaces; DOM identity/state; no Alpine in core | `stems/morph-safe-hypermedia.md` |
| **Details open intent** | Multi-`<details>` peers: exclusive vs multi_open; chrome needs outside dismiss | `stems/details-open-intent.md` |
| **Affordance disclosure chrome** | Expand/submenu signals: CSS/SVG chevron at control scale, not tiny Unicode | `stems/affordance-disclosure-chrome.md` |
| **Selection strip honest** | Tabs/segments: button vs link by intent; square active underline; no half ARIA tablist | `stems/selection-strip-honest.md` |
| **Shortcut hint chrome** | Keyboard chips: visually secondary + spatially secondary (adjacent gap / trailing) | `stems/shortcut-hint-chrome.md` |
| **Overlay light-dismiss** | Transient overlays: spatial (Esc/outside) vs temporal (opt-in ms); not accordion/tree | `stems/overlay-light-dismiss.md` |
| **Chrome vs protocol** | Modal lookalike L1s: job/lifecycle/authoring/htmx attach; addressing vs request gating | `stems/chrome-vs-protocol.md` |
| **Host chrome symmetry** | Overlay shells: form_shell vs exchange_shell; body hosts guests with honest DOM | `stems/host-chrome-symmetry.md` |

Monorepo framework stems (DSL-first, hypermedia SSR, …): `../../stems/` when
working inside the Dazzle tree.

**Interaction contracts (machine expressions of open intent):**
`GALLERY_PROBES.md` · `python tools/gallery_probes.py --run` (or monorepo
`scripts/hm_gallery_probes.py`). Do not invent exclusive-open on `tree` or ship
menubar/nav without the controller.

**Composition matrix (host × guest structural coherence):**
`python tools/composition_matrix.py --validate` · `--incompatible` ·
`--write-catalog` → `COMPOSITION_MATRIX.md`. form_shell vs exchange_shell,
guest DOM contracts, declared refusals (nested-form / nested-dialog / command),
Playwright coherence subset (`tests/test_composition_matrix_playwright.py`).

**Same visual shape ≠ same Hyperpart.** Lifetime and exchange decide the surface.
Example: form searchable select → `combobox`; dense in-cell enum with PUT + morph
→ grid-edit bare select (`grid.does_not_compose → combobox`). See
`docs/spikes/combobox-in-grid-cell.md`.

## Layers (how to pick and compose)

| Layer | Question | Stable unit |
|-------|----------|-------------|
| **L0 Recipe** | What job is the user doing? | Short pick-matrix in `docs/agent/pick-a-surface.md` |
| **L1 Surface** | What markup, exchange, controller, dual-lock? | One Hyperpart (or host-local primitive) |
| **L2 Host** | Who mounts or refuses that surface? | Parent Hyperpart / Blueprint / extension |

**Composite hosts (L2)** declare every L1 they embed (`composes`) or refuse
(`does_not_compose` + CI locks + optional spike). Parent contracts name **host**
seams only; the child’s dual-lock remains the child’s interface.

| Mechanism | Meaning | Enforced by |
|---|---|---|
| `composes` | Hard embed in partial/exchange | `test_composes_references_real_hyperparts` |
| `composes_with` | Soft related-parts links | ids must exist |
| `extensions` | Optional controller on host seams | cohesion + contracts by stem |
| `does_not_compose` | Same-ish job, local primitive, not child Hyperpart | `CONSUMER_MAP.md` + require/forbid locks |
| DOM / dual-lock | Producer markup contract | `tests/test_contracts.py`, Dazzle `test_hm_contract_*` |
| Contract surface | Attr/field breaking-change detector | `CONTRACT_SURFACE.md` drift gate |
| Consumer map | Reverse blast radius | `CONSUMER_MAP.md` drift gate |

## Invention ladder (freedom with a sequence)

When tempted to create something new:

1. **Reuse** an L1 that matches job + lifetime + exchange → `pick-a-surface.md`
2. **Host constraint** blocks that L1 → local primitive + **`does_not_compose`** + optional spike → `compose-or-refuse.md`
3. **Repeated need** → promote (compose for real, or new L1) with dual-lock + tests
4. **Only then** new package Hyperpart → `invent-safely.md` + `contracts/AUTHORING.md`

App-local one-offs need not become package Hyperparts. Blueprints compose existing
parts for page motifs—prefer a Blueprint over a new part when possible.

## Red flags (stop and re-open the curriculum)

- Merging two surfaces because they **look** the same (shape = identity)
- `data-*` flags that switch **commit path** or **lifetime** on one Hyperpart (mode forest)
- Parent rebuilds a child’s root DOM instead of embedding / declaring refuse
- Controller patches display after commit instead of server re-render
- “Composition” with no `composes` and no consumer-map edge
- Gallery `/mock/*` or flash toasts treated as product API
- Same public class name for two jobs (class collision)
- New Hyperpart whose notes say “like X but…” without refuse edge or distinct exchange
- Regenerating maps to green CI **without** reading blast radius

## Consuming Hyperparts (building an app)

- **Source of truth:** `site/registry.py` — partial, exchanges, controller, contracts,
  guidance, `does_not_compose`. Parse it; do not scrape gallery HTML as the contract.
- **Unit card:** `site/agents/<id>.md` — linear spine: Copy this → Server exchange →
  How to use it → DOM contract → Notes → Source files. Prefer `.md` to implement;
  HTML adds live demo. Form-bound parts may use `exchange_empty` (e.g. combobox
  growing-list catalogue upsert on enclosing form POST—still no dedicated hx-* of
  the part).
- **DOM contract** (`contracts/<part>.py`) is package-internal dual-lock—not the
  FastAPI handler you write. **Server exchange** (+ `server_example`) is the
  product API for standalone HTMX4.
- **Dialect:** gallery partials unprefixed; Dazzle dual-lock `dz-` / `data-dz-*`.
  Match the CSS/JS bundle you load.

### Gallery demos are not the product API

| Gallery-only (ignore) | Real contract |
|---|---|
| `/mock/*` | Server exchange table + `server_example` |
| Flash toasts | Exchange response fragment |
| Canned mock HTML | DOM contract / Copy this |
| `hm-toast`, demo chrome | App success/error UX |

**Trap:** inventing toast APIs or `/mock/…` routes. Stop. Return the exchange fragment.

## Changing the system (contributing)

- **Mutate a primitive:** `docs/agent/mutate-a-primitive.md` — then regenerate
  `CONTRACT_SURFACE.md` / `CONSUMER_MAP.md` / `DUAL_LOCK_COVERAGE.md` when surfaces change.
- **New Hyperpart:** `docs/agent/invent-safely.md` then `contracts/AUTHORING.md`
  (contract-first path).
- **This tree** is `packages/hatchi-maxchi/` in the
  [Dazzle monorepo](https://github.com/manwithacat/dazzle) (synced mirror may exist
  standalone). Edit in the monorepo when working there. See CONTRIBUTING.md.
- **Gates** (`python build.py && python -m pytest tests/` from package root as
  appropriate): markup/JS classes ↔ CSS; every request affordance ↔ Exchange;
  controller ownership + `HYPERPART:` markers; consumer/contract map drift;
  Chromium + WebKit behaviour; visual baselines; WCAG.
- **Conventions gates can’t fully see:** state in the DOM; document-delegated
  Pointer-Events vanilla JS; no hover-only affordances; `dz-` is the namespace
  token in source (rewritten at build)—don’t put it in custom-property names
  that must not rename.

## Page wiring (standalone)

Snippets ship unprefixed by default. `build.py --prefix dz-` (or any prefix)
renamespaces classes, data-attributes, and keyframes—pick one and stay with it.
A page needs dist CSS + JS, icon sheet once (`sprite_sheet.svg`), htmx4, and
idiomorph for `hx-swap="innerMorph"`. Gallery Setup: `#setup`.
