# Strategy: gallery_probes (hm-convergence)

**Lane:** hm-convergence
**Force path:** `/improve hm-convergence gallery_probes`
**Tool:** `python scripts/hm_gallery_probes.py`
  (source: `packages/hatchi-maxchi/tools/gallery_probes.py`)

Deterministic **interaction** contracts for the HM gallery. Complements dual-lock
(DOM/schema) and static vision smoke — catches bugs that only appear when the
user *acts* (e.g. menubar File stays open after Edit opens).

## When to pick

- Driver rule 7 OWNED-IDLE: `hm gallery interaction probes` never-exercised or STALE
- A human HMG observation names a stem that has (or needs) a probe
- After shipping a Hyperpart controller, run probes before dual-lock promotion
- Force path above

## Playbook (one cycle)

### 0. Discover (inventory — optional first cycle / after new Hyperparts)

```bash
python scripts/hm_gallery_probes.py --discover
# JSON: --discover --json → .dazzle/hm-gallery-probes/discover.json
```

Uncovered multi-``<details>`` stems without a catalog probe → author a probe that
**declares intent**:

| Intent | When | Fix surface |
|--------|------|-------------|
| `exclusive` | menubar / nav / accordion | controller or native `name=` |
| `multi_open` | tree forests | partial only — do **not** add exclusive controller |

Do **not** ignore `NEED_PROBE` / `author_probe_declare_intent` rows.

### 1. Run

```bash
python scripts/hm_gallery_probes.py --run
# filter:
python scripts/hm_gallery_probes.py --run --stem menubar
# FAIL rows as HMC-style markdown:
python scripts/hm_gallery_probes.py --run --emit-findings
```

Exit **0** = all PASS/SKIP. Exit **1** = FAIL (product UX defect). Exit **2** = harness error.

Report: `.dazzle/hm-gallery-probes/report.json` (+ FAIL PNGs, optional `findings.md`).

### 2. Drain FAILs

For each `verdict: FAIL` in the report:

1. Read `claim`, `detail`, `evidence_png`, `fix_surface`
2. Fix in HM (`controllers/`, `components/`, registry partial) — not Dazzle CSS
3. Rebuild: `python packages/hatchi-maxchi/build.py` (+ site if registry/partial changed)
4. Re-run the failing probe until PASS
5. Optional: seed HMC row under `## Lane: hm-convergence` if multi-cycle
   (`--emit-findings` templates the row)

### 3. Human observation validation

```bash
python scripts/hm_gallery_probes.py --validate-observation \
  '{"stem":"menubar","claim":"opening Edit leaves File open","severity":"high"}'
```

| Result | Meaning |
|--------|---------|
| `CONFIRMED` | Probe FAIL — human was right; fix this cycle if small |
| `NOT_REPRO` | Probe PASS — bug fixed or wrong surface |
| `NO_PROBE` | Author a new `Probe` in `gallery_probes.py` PROBES (+ often `--discover`), re-run |
| `HARNESS_ERROR` | Page/controller missing — repair harness |

### 4. Stamp

Capability map: `hm gallery interaction probes` → `USED@N`.
`budget_consumed: 1`. Commit report only if you add tracked catalog/docs (report itself is gitignored under `.dazzle/`).

## Authoring a new probe

1. Prefer `--discover` to find multi-details stems not in catalog
2. Add a `Probe(...)` to `PROBES` in `tools/gallery_probes.py`
3. Implement `kind` runner or reuse `exclusive_details_open`
4. `--write-catalog` to refresh `GALLERY_PROBES.md`
5. Prefer a matching `tests/test_behaviour.py` scenario (CI) for ship-grade pins

## Hard rules

- **Interaction over aesthetics** — no metered taste-panel
- **Harness first** — if a human observation has `NO_PROBE`, author the probe
  before a one-off visual fix; the goal is autonomous re-detection
- **One FAIL root-cause fix per cycle** when draining (same as dual_lock_expand)
- **Local `site/` by default** — rebuild before trusting PASS after registry edits
