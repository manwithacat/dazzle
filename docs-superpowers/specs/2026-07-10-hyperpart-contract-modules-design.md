# Hyperpart Contract Modules — Design

**Date**: 2026-07-10
**Status**: Approved for planning
**Driver**: #1573 (fleet badge-list crash: `filter_options` reached the renderer in three
producer shapes; the fix normalised at one consumer, but the class is open) and older
issues in the same family. The relationship between HM Hyperparts and the data contract
that feeds them is prose-only: each controller documents its DOM contract in a JS header
comment, and `site/registry.py` declares exchange contracts, but nothing types the
*ingestion data shape* and nothing lints either side. Dazzle is not a SPA — no JSON
ingestion step exists; the requirement is that server code produces data in the right
shape to fill the component's server-rendered DOM.

## Decisions (locked with user, 2026-07-10)

1. **Source of truth: a structured contract module per data-bearing Hyperpart** —
   docs, exemplars, and lint all derive from it.
2. **Exemplars live in the HM package and execute in HM CI** (FastAPI as a dev-only
   dependency; the dist stays pure CSS/JS).
3. **Dazzle-side lint = typed boundary + DOM conformance** — both halves, closing the
   #1573 ingestion class and silent DOM drift.
4. **Rollout: the 19 JS controllers first, grid + grid-edit as the pilot**; CSS-only
   components keep contract_checker/card-safety coverage for now.
5. **Approach A: Pydantic contract modules, triple-derived** (over TOML+codegen and
   golden-snapshot alternatives).
6. **Refinement from exploration**: HM's `site/registry.py` is already the per-component
   source of truth (markup partial, exchange contracts, controller pointers). Contract
   modules ATTACH to registry entries — they do not form a second registry.

## The contract module

`packages/hatchi-maxchi/contracts/<part>.py` — one per data-bearing Hyperpart. Anatomy
(pilot, `grid_edit.py`):

```python
class GridEditCell(BaseModel):
    col: str
    kind: Literal["text", "date", "bool", "select"]
    value: str
    label: str                                      # a11y
    options: list[tuple[str, str]] | None = None    # [[value, label], …]
    # model_validator: kind == "select" requires options; other kinds forbid them.
    # field_validator on options: accepts dicts ({value,label}), tuples, and bare
    # strings; normalises all to pairs — the ONE normalisation boundary, by definition.

DOM_CONTRACT = DomContract(
    part="grid-edit",
    root="[data-dz-grid][data-dz-grid-edit-url]",
    nodes=[Node("[data-dz-grid-edit]", attrs={
        "data-dz-edit-kind":    OneOf("text", "date", "bool", "select"),
        "data-dz-edit-value":   Present(),
        "data-dz-edit-label":   Present(),
        "data-dz-edit-options": JsonPairs(required_when={"data-dz-edit-kind": "select"}),
    })],
)

EXEMPLARS: list[GridEditCell] = [...]   # must include the #1573 shape
                                        # (select kind + producer-shaped options)

def render(cell: GridEditCell) -> str: ...   # model → conforming HTML fragment
app = FastAPI(...)                            # minimal endpoint serving the fragment —
                                              # mirrors how the part is fed in Dazzle
```

Shared kit `contracts/_kit.py`: `DomContract` / `Node` / attribute validators
(`OneOf`, `Present`, `JsonPairs`, …) and `validate_dom(html, contract) -> list[Violation]`.
Used by HM tests and (test-time) by Dazzle gates.

**Relationship to existing artifacts:**
- `site/registry.py`: each controller-bearing entry gains a `contract` pointer naming its
  module; the cohesion gate (extended `test_hyperpart_cohesion.py`) asserts every
  controller-bearing entry has one (or a `PENDING_CONTRACTS` allowlist entry — see
  Rollout).
- The JS controller's prose `Contract:` header stays for reader convenience but gains a
  pointer line to the module; a drift check asserts the attribute names in the prose
  match `DOM_CONTRACT` (names only — prose explains, the module specifies).

## HM side — CI + gallery + authoring docs

- **`tests/test_contracts.py`** (new, HM test suite): for every contract module —
  render every `EXEMPLARS` entry through `render()`, run `validate_dom()` against
  `DOM_CONTRACT`, and pass the output through the existing vnu/axe path. A contract
  module whose exemplar violates its own DOM contract cannot ship.
- **Dependencies**: `fastapi` + `pydantic` become HM *dev/test* dependencies only. The
  dist (CSS/JS) is unchanged — the dist-only consumption boundary holds.
- **Gallery** (`site/build_site.py`): each Hyperpart page gains a contract section —
  the ingestion model's schema rendered as a field table, the exemplar source embedded
  via `inspect.getsource` (the page IS the snippet — Blueprint idiom, docs cannot
  drift), and the exemplar's live rendered output. `llms.txt` lists contract modules.
- **`contracts/AUTHORING.md`** (new): the ordered new-Hyperpart checklist, covering the
  two gaps the contract modules alone don't close:
  1. *Decision test*: when a new part is warranted vs composing existing parts — including
     the build-to-replace rule (an HM part must replace a Dazzle-native equivalent or
     it is decoration).
  2. *Controller idiom rules with named canonical examples*: document-level delegation,
     state-in-DOM, Pointer-Events vanilla JS, hover-only forbidden, morph-path survival
     (canonical example: `dz-grid-edit`'s `root._dzEdit` buffer + before/after-swap
     hooks), touch accommodations.
  3. *The ordered path*: contract module first (exemplar green in HM CI) → controller
     against `DOM_CONTRACT` (behaviour tests) → Dazzle emitter against the typed model
     (schema-parity + DOM-conformance gates red until right).
  HM's AGENTS.md links to it from the contributing section.

## Dazzle side — typed boundary

- `dazzle.render` gains a runtime copy of each ingestion model (the wheel cannot ship
  `packages/`, so no runtime import across the boundary; parity is enforced by the
  schema gate below). Pilot: `GridEditCell` in a new `dazzle/render/fragment/ingest.py`
  (grows one model per contract as rollout proceeds).
- `_data_row.py`'s inline-edit emission constructs `GridEditCell(...)` and emits the
  `data-dz-edit-*` attributes FROM the model. The three `filter_options` producer shapes
  hit the model's field validator and normalise in exactly one place; the current
  3-branch comprehension inside the renderer (the #1573 hotfix) is deleted.
- A small gate pins that `data-dz-edit-*` attributes are emitted only by the typed path
  (no raw string-assembly of those attributes elsewhere in `src/dazzle`).

## Cross-boundary locks (Dazzle `pytest.mark.gate`, test-time reads of `packages/`)

1. **Schema parity** (`tests/unit/test_hm_contract_schema_parity.py`): importlib-load
   `packages/hatchi-maxchi/contracts/<part>.py`, compare canonicalised
   `model_json_schema()` of the HM model vs the Dazzle runtime model. Canonicaliser
   strips titles/descriptions and normalises ordering. Unilateral shape change on either
   side → red with a field-level diff.
2. **DOM conformance** (`tests/unit/test_hm_contract_dom_conformance.py`): render a
   hydrated row through the real Dazzle pipeline (the #1574 rows-present approach:
   `build_data_table` → `render_data_table_rows` with producer-shaped data), parse, and
   run the kit's `validate_dom()` against the HM `DOM_CONTRACT`. This is the gate that
   would have caught #1573 at the contract layer, and catches future drift in either
   direction.

Both gates read `packages/hatchi-maxchi/` from the repo tree at test time — the same
pattern as the existing HM delegation-proof test; no runtime coupling.

## Rollout

1. **Pilot**: `contracts/_kit.py` + `contracts/grid_edit.py` (+ a thin `grid.py` for the
   base grid root contract) end-to-end: HM CI test, gallery section, Dazzle typed
   boundary in `_data_row.py`, both cross-boundary locks. The #1573 producer shapes ship
   as permanent exemplars.
2. **Ratchet**: `PENDING_CONTRACTS` allowlist starts with the remaining ~17 controllers;
   the cohesion gate forbids new controllers without contracts and the allowlist only
   shrinks. Burn-down is lane-able work (hm-convergence-style batches).
3. **AUTHORING.md + registry pointers** land with the pilot so the authoring path is
   real from day one.

## Sufficiency for agents authoring new Hyperparts

The contract module answers the interface questions (data shape, DOM attributes,
reference implementation) — historically the biggest noise source. Exchange wiring,
CSS discipline, and behaviour testing were already gated (`registry.py` exchanges,
`test_contract.py`, dual-engine tests). The two residual gaps — controller
implementation idiom and the new-part-vs-compose decision — are closed by
`contracts/AUTHORING.md` (see HM side). With those, every step of the authoring path is
either machine-checked or explicitly documented with a named canonical example.

## Risks & mitigations

- **HM standalone-repo CI** must gain the contract test job — the sync workflow mirrors
  the package tree; verify at implementation that the standalone CI config picks up
  `tests/test_contracts.py` and the new dev-deps (if CI config lives outside the synced
  tree, update it in the standalone repo in the same arc; never subtree-push manually).
- **Pydantic version skew** between HM dev-env and Dazzle env can perturb
  `model_json_schema()` output — the canonicaliser normalises known-variant keys, and
  the parity gate pins the comparison to structural fields (type/required/enum/items).
- **Second-registry risk** — avoided by decision 6: registry entries point at contract
  modules; the cohesion gate enforces the pairing.
- **Exemplar rot** — impossible by construction: exemplars execute in HM CI and their
  source is embedded in the gallery from the same module.

## Out of scope

- CSS-only components (structure contracts stay with contract_checker / card-safety);
  fold in later if the model earns it.
- Retiring `registry.py` `exchanges` or merging them into contract modules — exchanges
  describe HTTP wiring, contract modules describe data/DOM shape; they stay complementary.
- Dazzle-side full column-model typing beyond the pilot's `data-dz-edit-*` path (the
  broader `build_data_table` dict → model conversion is its own future arc).
