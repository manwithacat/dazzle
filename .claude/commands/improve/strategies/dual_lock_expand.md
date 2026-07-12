# Strategy: dual_lock_expand

**Lane:** hm-convergence
**Force path:** `/improve hm-convergence dual_lock_expand`
**Metric / queue:** `python packages/hatchi-maxchi/tools/dual_lock_queue.py`

Continue the schema+DOM (or DOM-only) dual-lock expansion that landed the chart
fleet (bar → funnel → heatmap → bullet → bar-track → histogram → pivot →
box-plot → progress → radar → time-series). One improve cycle = **one promotion
unit** (1 part, or 2 siblings that share the same emit mixin).

## When to pick

Pick when **all** of:

1. HM zero-floors green (`python scripts/hm_tailwind_reservoir.py` exits 0)
2. No red `REGRESSION` HMC row
3. Queue depth > 0:

   ```bash
   python packages/hatchi-maxchi/tools/dual_lock_queue.py --top 5
   ```

Skip / HOUSEKEEPING when the queue is empty **and** floors are green (dual-lock
arc drained for now — switch to `dual_lock_visual_smoke` or another lane).

## Preflight (lane-local)

```bash
python scripts/hm_tailwind_reservoir.py
python packages/hatchi-maxchi/tools/dual_lock_coverage.py --write
python packages/hatchi-maxchi/tools/dual_lock_queue.py --write
```

If reservoir red → stop; fix floor first (not this strategy).

## Playbook

### 1. Select candidate

From `--top 5`, take the **lowest `pri`** row that is not already in-flight in
the backlog.

| Prefer | Avoid this cycle |
|--------|------------------|
| `emitter_uncontracted` with `css=yes` | `gallery_uncontracted` without emitter |
| `contract_none` with non-empty `emitters` | Pure docs-only (`code` without Dazzle emit) unless you can invent a stable emission fixture |
| Batch of **2** sibling charts/regions | More than 2 parts (Tier 0 thrash) |

Log the pick: `dual_lock_expand: promoting {stem} ({kind})`.

Seed/update a backlog row under `## Lane: hm-convergence`:

| id | scope | status | notes |
|----|-------|--------|-------|
| HMC-NNN | dual_lock `{stem}` | IN_PROGRESS | kind=…; emitter=… |

### 2. Implement the dual-lock (schema+DOM pattern)

Canonical recent ships: histogram/pivot (`f40622115`), box-plot/progress
(`4b5d09a39`), radar/time-series (`5251968cc`).

**A. HM contract** — `packages/hatchi-maxchi/contracts/<stem>.py`

- `DOM_CONTRACT` root `[data-dz-<hyphen>]` + `Present()`
- Pydantic model(s) (host-trusted HTML fields for SVG/cells when needed)
- `EXEMPLARS` + `render()` matching the intended DOM
- Or `python packages/hatchi-maxchi/tools/scaffold_contract.py <stem>` then fill

**B. Dazzle ingest seam** — `src/dazzle/render/fragment/ingest/`

- `models.py` copy (schema-parity gated)
- `emit.py` root attrs + `render_*` sole-emitter
- `__init__.py` facade exports

**C. Wire real pipeline**

- `_emit_*` builds the seam model and calls `render_*` only
  (no `data-dz-*` assembly outside `ingest/`)

**D. Gates**

- `tests/unit/hm_contract_registry.py` → `CONTRACT_MODELS` rows
- `test_hm_contract_dom_conformance.py` → real FragmentRenderer test + sole-emitter regex token
- Registry Hyperpart: root attr + `contracts=("contracts/<stem>.py",)` when gallery exists
- Region wrappers without CSS rules → `SEMANTIC_ONLY` in `packages/hatchi-maxchi/tests/test_contract.py`

**E. Regen** (mandatory — CI drift gates; AUD-002)

```bash
python packages/hatchi-maxchi/tools/dual_lock_coverage.py --write
python packages/hatchi-maxchi/tools/contract_surface.py --write
python packages/hatchi-maxchi/tools/consumer_map.py --write
python packages/hatchi-maxchi/tools/dual_lock_queue.py --write
python packages/hatchi-maxchi/site/build_site.py
python scripts/gen_ux_catalogue.py   # REQUIRED when emit path appears in catalogue
                                     # (list-region, empty-state, skeleton, …)
```

**F. Import + morph ship gates** (mandatory — cycles 345–346 left main red)

1. **Hoist dual-lock ingest imports to module top** on the renderer mixin
   (and any other host that calls `render_*`). Follow charts/tables pattern —
   **never** add function-level `from dazzle.render.fragment.ingest import …`
   (ratchet `#1438` / `test_deferred_imports_ratchet_1438` forbids growth).
2. **Morph-exchange lint:** if the registry `Exchange.swap` mentions morph /
   `innerMorph` / `outerMorph`, the Hyperpart `notes` **or** `partial` must
   also contain that Morph signal (`test_morph_template_gates`).
3. Pre-push smoke (must pass locally):

```bash
pytest tests/unit/test_deferred_imports_ratchet_1438.py \
  packages/hatchi-maxchi/tests/test_morph_template_gates.py::test_registry_and_controllers_are_clean \
  tests/unit/test_contract_surface_tool.py \
  tests/unit/test_hm_package_suite_gate.py -q --tb=line
```

**G. Complexity**

If `test_complexity_ratchet` red after intentional growth:

```bash
dazzle fitness code --write-baseline
```

### 3. Verify

```bash
# focused
pytest tests/unit/test_hm_contract_schema_parity.py \
  tests/unit/test_hm_contract_dom_conformance.py -q --tb=short

# ship floor (+ section F smokes)
make sync-ci-type   # once per session if mypy extras missing
make ci-fast
```

Optional (never ship-blocking):

```bash
python scripts/hm_visual_smoke.py --dazzle-emit
```

### 4. Ship + backlog

- Commit: `feat(hm): promote <stem> to schema+DOM dual-lock` (or batch message)
- `/ship` Tier 0 (or `make ci-fast` + commit + push)
- Emit `form-deployed` (ship skill does this)
- Mark HMC row **DONE** with SHA + dual-lock counts from coverage summary
- Re-run queue: promoted stem **must not** appear in `--top 5`

### 5. Outcome

Return to the improve driver:

```text
status: PASS | FAIL | BLOCKED | EXPLORED
summary: dual_lock_expand {stem} → schema+DOM (schema+DOM N→M); sha=…
signals_to_emit: [{kind: form-deployed, payload: {sha, parts: [...]}}]  # if ship skill didn't
budget_consumed: 0   # implementation cycle, not explore-budget burn
                     # use 1 only if this was pure survey with no ship
```

`BLOCKED` examples:

- No stable Dazzle emission (`code` gallery-only) → note + pick next queue row
- Tier 0 red after honest fix attempts → leave IN_PROGRESS with failure notes

## Hard rules

- **Sole-emitter:** HM contract attrs assembled **only** under `fragment/ingest/`
- **Trusted HTML:** SVG / badge cells stay host-side; dual-lock the chrome + root
- **Byte-faithful** where catalogue/tests assert exact HTML; otherwise root + summary parity
- **Do not** re-open Tailwind drain when floors are 0
- **Batch ≤ 2** siblings per cycle

## Related

- Coverage map: `packages/hatchi-maxchi/DUAL_LOCK_COVERAGE.md`
- Queue: `packages/hatchi-maxchi/DUAL_LOCK_QUEUE.md` (`--write`)
- Authoring: `packages/hatchi-maxchi/contracts/AUTHORING.md` steps 1 + 4
- Plan: `docs/superpowers/plans/2026-07-11-hm-sophistication-plan.md`
- Lane: `improve/lanes/hm-convergence.md`
