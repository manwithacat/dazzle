# Authoring a new Hyperpart — the ordered path

## 0. Should this be a new Hyperpart at all?

- **Compose first**: if existing parts + Layout primitives express it, write a
  Blueprint, not a part.
- **Build-to-replace**: an HM part must REPLACE a Dazzle-native equivalent (or fill a
  hole no Dazzle layer covers). A part that ships alongside an unconverted Dazzle
  equivalent is decoration — it will be shadowed by unlayered Dazzle CSS.
- **Controller only where the platform lacks a primitive** (registry.py doctrine).

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

## 3. Registry entry

Add the Hyperpart to `site/registry.py` with `partial`, `exchanges` (every hx-*
affordance needs one — gated), `controller`/`extensions`, `mock`, and
`contracts=("contracts/<part>.py",)`. A controller-bearing entry without contracts
fails `test_hyperpart_cohesion.py` unless it is in `PENDING_CONTRACTS` — and that
list only shrinks; new parts never enter it.

## 4. Dazzle emitter against the typed model

In the Dazzle monorepo: add the runtime model copy (`dazzle/render/fragment/ingest.py`),
emit the part's `data-*` attributes FROM the model, and watch two gates go green:
`test_hm_contract_schema_parity` (your model matches this module's, field for field)
and `test_hm_contract_dom_conformance` (the real pipeline's DOM satisfies
DOM_CONTRACT). Red gates here are the loop working, not noise.
