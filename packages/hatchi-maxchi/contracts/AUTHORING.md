# Authoring a new Hyperpart — the ordered path

**Coverage map (dual-locks):** regenerate with
`python packages/hatchi-maxchi/tools/dual_lock_coverage.py --write` →
`packages/hatchi-maxchi/DUAL_LOCK_COVERAGE.md`. **Promotion queue** (what
`/improve hm-convergence dual_lock_expand` picks next):
`python packages/hatchi-maxchi/tools/dual_lock_queue.py --write` →
`packages/hatchi-maxchi/DUAL_LOCK_QUEUE.md`. Cycle recipe:
`.claude/commands/improve/strategies/dual_lock_expand.md`. Sophistication plan:
`docs/superpowers/plans/2026-07-11-hm-sophistication-plan.md` (epic #1580).

**Visual smoke (subscription, never a ship gate):** after dual-locking a part,
`python scripts/hm_visual_smoke.py --dazzle-emit` writes PNGs under
`.dazzle/hm-visual-smoke/` for host-harness **Read** review. Metered
`component-vision` / `taste-panel` are optional when API credits exist — they
must not block CI.

## 0. Should this be a new Hyperpart at all?

**Read first:** `docs/agent/invent-safely.md` (invention ladder) and
`AGENTS.md` (curriculum + stems). This section is the gate at the top of the
ladder—not optional colour.

- **Ladder:** reuse L1 → refuse+local primitive → promote → **only then** new part.
- **Compose first**: if existing parts + Layout primitives express it, write a
  Blueprint, not a part.
- **Build-to-replace**: an HM part must REPLACE a Dazzle-native equivalent (or fill a
  hole no Dazzle layer covers). A part that ships alongside an unconverted Dazzle
  equivalent is decoration — it will be shadowed by unlayered Dazzle CSS.
- **Controller only where the platform lacks a primitive** (registry.py doctrine).
- **Composition is declared, not inferred**: parent `composes=(child, …)` when the
  partial embeds the child; `guidance.composes_with` for soft agent links;
  `extensions` for optional controllers on another part’s seams. Resembling
  another part’s UX (e.g. grid-edit’s bare `<select>` vs combobox) is **not**
  composition — declare `does_not_compose=NonComposition(...)` with CI
  require/forbid locks and an optional spike path. See
  `docs/decisions/0003-composition-declared.md`, `docs/agent/compose-or-refuse.md`,
  `CONSUMER_MAP.md`, and `docs/spikes/`.
- **Layers:** same job (L0) can have multiple surfaces (L1); do not merge by shape
  (`docs/decisions/0002-three-layers.md`, `docs/agent/pick-a-surface.md`).

## 1. Contract module FIRST — `contracts/<part>.py`

Write, in one module: the **ingestion model** (Pydantic — the single canonical data
shape; put producer-shape normalisation in a field_validator so there is exactly one
normalisation boundary), the **DOM_CONTRACT** (root selector + per-node required
`data-*` attributes with validators from `contracts/_kit.py`), **EXEMPLARS** (including
every producer shape you expect — they are permanent, executable regression docs), a
**render()** turning the model into conforming markup, and a minimal **FastAPI app**
showing how a server feeds it. `tests/test_contracts.py` sweeps all of this in CI: an
exemplar that violates its own contract cannot ship. Green here = your interface is real.

## 2. Controller against the DOM contract

Idiom rules (the gates can't fully see these — follow them):

- **Document-level delegation**, Pointer-Events, vanilla JS. One controller file,
  `HYPERPART: <id>` marker (cohesion-gated).
- **State lives in the DOM** (attributes, `.checked`, `aria-*`) — never in JS objects
  that a morph would orphan.
- **Morph-path survival**: transient interaction state that must outlive a tbody swap
  goes on a stable root property with before/after-swap hooks. Canonical example:
  `controllers/dz-grid-edit.js` — the typed edit buffer lives at `root._dzEdit`, the
  before-swap hook captures the live input value, the after-swap hook re-opens the
  editor on the morph-keyed row.
- **No hover-only affordances**; touch accommodations get tested (README › Touch input).
- Keep the prose `Contract:` header in the controller and point it at the contract
  module — the module is the source of truth; the prose explains.
- **Prose ↔ DOM_CONTRACT drift gate** (`tests/test_contract_prose_drift.py`, #1579):
  every `data-dz-*` / `hx-confirm` name in `DOM_CONTRACT` must appear in the paired
  controller source; when a formal `Contract:` block exists it must name those
  attrs, and must not invent structural attrs absent from the contract (runtime
  flags like `data-dz-open` live in `TRANSIENT_STATE_ATTRS`). Pairing is by stem
  (`contracts/grid_edit.py` → `controllers/dz-grid-edit.js`) plus a small special
  table (`confirm_panel` → `dz-confirm-gate.js`).

## 3. Registry entry

Add the Hyperpart to `site/registry.py` with `partial`, `exchanges` (every hx-*
affordance needs one — gated), `controller`/`extensions`, `mock`, and
`contracts=("contracts/<part>.py",)`. A controller-bearing entry without contracts
fails `test_hyperpart_cohesion.py` unless it is in `PENDING_CONTRACTS` — and that
list only shrinks; new parts never enter it.

If the part has **no** `hx-*` of its own but still has server work on the enclosing
form (e.g. combobox `data-dz-allow-create` catalogue upsert), set `exchange_empty=`
to HTML that documents that form-bound contract — do **not** claim “presentation
only,” and do **not** invent an orphan `Exchange` without a matching affordance.

After any contract surface change (DOM attrs, model fields), regenerate:

```bash
python packages/hatchi-maxchi/tools/contract_surface.py --write
python packages/hatchi-maxchi/tools/consumer_map.py --write
python packages/hatchi-maxchi/tools/dual_lock_coverage.py --write
```

Read `CONSUMER_MAP.md` for the part you changed — hard embeds and blueprints are
blast radius; `refused_by` edges mean “do not dogfood me into that parent.”

## 4. Dazzle emitter against the typed model

In the Dazzle monorepo: add the runtime model copy (`dazzle/render/fragment/ingest.py`),
emit the part's `data-*` attributes FROM the model, and watch two gates go green:
`test_hm_contract_schema_parity` (your model matches this module's, field for field)
and `test_hm_contract_dom_conformance` (the real pipeline's DOM satisfies
DOM_CONTRACT). Red gates here are the loop working, not noise.
