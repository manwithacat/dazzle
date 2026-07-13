# Strategy: hyperpart_coherence (hm-convergence)

**Lane:** hm-convergence
**Force path:** `/improve hm-convergence hyperpart_coherence`
**Tooling:** `scripts/hm_pages_vision.py` + host-harness subagents that **Read** PNGs
**Billing:** subscription (Playwright capture local; vision judgment via host Read)
**Ship gate:** **false** — advisory only (dual-locks + `pytest -m gate` remain the floor)

Snapshot **every** Hyperpart gallery page and ask a subagent “does this look
coherent?” Faster than a human walking 90 pages; cheaper cognitive target than
full multi-dimension taste scoring; image tokens often beat dumping full HTML
as text for layout judgment.

Complements:

| Path | Question |
|------|----------|
| dual-locks / gate | Structure / DOM / schema correct? |
| `gallery_probes` | Interaction exclusive-open etc.? |
| dual-lock smoke + `hm_subscription_vision` | A few exemplars taste scores |
| **this strategy** | Full catalogue: visual coherence of each live page |

## When to pick

- Operator wants HM **quality** time (not dual-lock expansion alone)
- After a large HM gallery / registry / partial change
- OWNED-IDLE / STALE re-exercise of subscription vision on a wider surface
- Force path above

## Playbook (one cycle — full sweep)

### 1. Capture (local site preferred — offline, deterministic)

```bash
# rebuild site if registry/partials changed
# python packages/hatchi-maxchi/site/build_site.py   # when needed

python scripts/hm_pages_vision.py --list-hyperparts   # inventory (~90)

python scripts/hm_pages_vision.py --capture --all-hyperparts \
  --base "file://$(pwd)/packages/hatchi-maxchi/site" \
  --out .dazzle/hm-hyperpart-coherence
# optional: --clip-demo  (crop to demo region)  --limit N  --stems a,b,c
```

Manifest: `.dazzle/hm-hyperpart-coherence/manifest.json` + one PNG per stem.

### 2. Emit batched mission prompts

```bash
python scripts/hm_pages_vision.py --write-coherence-prompt \
  --out .dazzle/hm-hyperpart-coherence \
  --batch-size 12
```

Writes `coherence-prompt-batch-NN.txt` + `coherence-batches.json`.
Default batch size **12** — parallelize across host subagents without drowning
context.

### 3. Dispatch subagents (subscription Read)

For **each** batch in `coherence-batches.json`:

- `subagent_type`: `general-purpose` (needs Read + Write)
- model: session tier (visual judgment — no Haiku pin)
- `description`: `HM hyperpart coherence batch N`
- `prompt`: contents of `coherence-prompt-batch-NN.txt`

Subagent **Reads** each PNG path, **Writes** `batch-NN-raw.json` (schema in
`dazzle.qa.subscription_vision.build_hyperpart_coherence_prompt`).

Do **not** call metered `dazzle qa taste-panel` / `component-vision`.

### 4. Ingest + rank

```bash
python scripts/hm_pages_vision.py --ingest-coherence \
  .dazzle/hm-hyperpart-coherence/batch-*-raw.json \
  --out .dazzle/hm-hyperpart-coherence
# → coherence.json  (mean_score, worst[], n_incoherent)
```

### 5. Drain (same cycle if small; else backlog)

For each **incoherent** or score ≤ 6 row (worst first):

| Severity / pattern | Action |
|--------------------|--------|
| empty_demo / layout_broken high | Fix HM partial / demo data this cycle if small |
| overflow / contrast medium | Fix or file HMC backlog row |
| copy / low noise | Note only unless trivial |

Fix surface is **HM** (`packages/hatchi-maxchi/`), not Dazzle CSS.

Re-capture only the fixed stems:

```bash
python scripts/hm_pages_vision.py --capture --stems money,wizard \
  --base "file://$(pwd)/packages/hatchi-maxchi/site" \
  --out .dazzle/hm-hyperpart-coherence
```

### 6. Stamp + log

- capability-map: stamp subscription vision / hyperpart_coherence exercise
- improve-log: `lane: hm-convergence` / strategy `hyperpart_coherence`
- `budget_consumed: 1` (explore) — capture+judge is the exercise
- Commit **code fixes** only; `.dazzle/` artifacts stay gitignored

## Partial sweep (budget-friendly)

```bash
# first 15 only
python scripts/hm_pages_vision.py --capture --all-hyperparts --limit 15 \
  --base "file://$(pwd)/packages/hatchi-maxchi/site" \
  --out .dazzle/hm-hyperpart-coherence
```

Or stems from dual-lock queue / recent commits.

## Hard rules

- **Advisory only** — never fail CI solely on coherence scores.
- **Subscription only** — no metered vision APIs in the default loop.
- **Images over HTML dumps** for “does it look right?” — capture PNG, Read PNG.
- **One batch set per cycle** is enough; do not re-score the whole fleet every
  cycle unless the gallery changed materially.
- Prefer **fixing** high-severity incoherent demos over filing noise.

## Outcome shapes

| Outcome | Meaning |
|---------|---------|
| `PASS` | Sweep ran; 0 high-severity incoherent (or fixed this cycle) |
| `FINDINGS` | Incoherent list remains; top N logged / HMC rows |
| `BLOCKED` | No Playwright / site missing / subagent dispatch unavailable |
