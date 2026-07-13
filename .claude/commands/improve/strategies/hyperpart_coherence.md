# Strategy: hyperpart_coherence (hm-convergence)

**Lane:** hm-convergence
**Force path:** `/improve hm-convergence hyperpart_coherence`
             `/improve hm-convergence hyperpart_coherence investigate`
             `/improve hm-convergence hyperpart_coherence drain`
**Tooling:**
- Capture/judge: `scripts/hm_pages_vision.py`
- Drain queue: `scripts/hm_coherence_queue.py`
- Host subagents **Read** PNGs (subscription)
**Billing:** subscription (Playwright local; vision via host Read)
**Ship gate:** **false** — advisory scores; **fixes still ship** like any HM bug
**Backlog:** `HMC-NNN` with `scope` = `coherence_drain <stem>` under `## Lane: hm-convergence`

This strategy is **two phases** on the same lane — the driver picks which phase
from the queue + backlog, not a separate top-level lane.

| Phase | Question | Machine signal |
|-------|----------|----------------|
| **investigate** | Which Hyperparts look broken? | No/stale `coherence.json`, or force |
| **drain** | Fix the worst open findings | `hm_coherence_queue.py` depth > 0 **or** PENDING `coherence_drain *` rows |

Complements dual-locks (structure), gallery_probes (interaction), dual-lock smoke (few exemplars).

---

## Driver / lane pick rules (authoritative)

When `/improve` hands off to **hm-convergence**, choose sub-strategy in this order
(after floors green; CI/CodeQL already handled by the driver):

1. **`hyperpart_coherence` drain** — if either:
   - `python scripts/hm_coherence_queue.py --status` reports `queue>0`, **or**
   - backlog has `PENDING` / `IN_PROGRESS` rows with scope `coherence_drain *`
2. **`hyperpart_coherence` investigate** — if either:
   - `coherence.json` missing (`--status` exit 2 / "missing"), **or**
   - last investigate ≥ **20** improve cycles ago (log: no `strategy: hyperpart_coherence` investigate since), **or**
   - force `… hyperpart_coherence investigate`
3. Else fall through: gallery_probes → dual_lock_expand → shadcn_parity → …

Driver Step 1 also biases **toward hm-convergence** when queue depth > 0
(actionable_count includes PENDING `coherence_drain` rows). Force always wins.

Capability map: stamp **HM hyperpart coherence** `USED@N` after either phase runs.

---

## Phase A — Investigate (sweep)

Goal: refresh `.dazzle/hm-hyperpart-coherence/coherence.json` + seed/update queue.

### A1. Capture

```bash
python scripts/hm_pages_vision.py --list-hyperparts

python scripts/hm_pages_vision.py --capture --all-hyperparts \
  --base "file://$(pwd)/packages/hatchi-maxchi/site" \
  --out .dazzle/hm-hyperpart-coherence
# budget: --limit N  or  --stems a,b,c
```

### A2. Batch prompts + subagents

```bash
python scripts/hm_pages_vision.py --write-coherence-prompt \
  --out .dazzle/hm-hyperpart-coherence --batch-size 12
```

For each entry in `coherence-batches.json`, dispatch a **general-purpose** subagent
(session model; Read + Write) with the batch prompt. Subagent Writes
`batch-NN-raw.json`. No metered `taste-panel` / `component-vision`.

### A3. Ingest + queue + backlog seed

```bash
python scripts/hm_pages_vision.py --ingest-coherence \
  .dazzle/hm-hyperpart-coherence/batch-*-raw.json \
  --out .dazzle/hm-hyperpart-coherence

python scripts/hm_coherence_queue.py --write --top 15
python scripts/hm_coherence_queue.py --status
# If new stems lack HMC rows:
python scripts/hm_coherence_queue.py --seed-backlog --start-id <next HMC>
# → paste PENDING rows into improve-backlog.md ## Lane: hm-convergence
```

### A4. Investigate-cycle outcome

| Outcome | When |
|---------|------|
| `EXPLORED` | Sweep completed; queue written; 0–N PENDING rows seeded |
| `PASS` | Sweep completed and **queue empty** (all coherent) |
| `BLOCKED` | No Playwright / site missing / subagent dispatch failed |

- `budget_consumed: 1`
- Log: `strategy: hyperpart_coherence` / `phase: investigate`
- **Do not** start large drains in the same cycle unless queue ≤ 2 and fixes are tiny
- Commit only if backlog seed or tooling changed (artifacts stay gitignored)

---

## Phase B — Drain (fix)

Goal: clear **one** (max two sibling) top queue item(s) per cycle.

### B1. Pick

```bash
python scripts/hm_coherence_queue.py --top 5
# or backlog: first PENDING coherence_drain *
```

Mark the chosen row `IN_PROGRESS`. Prefer:

1. score ≤ 4 or severity high
2. `empty_demo` / `layout_broken` / blank-capture
3. shared root cause (e.g. both message + message-scroller meta)

### B2. Reproduce (cheap)

```bash
# open PNG + live page
open .dazzle/hm-hyperpart-coherence/<stem>.png   # or Read tool
# file://…/site/hyperparts/<stem>.html
```

Classify:

| Class | Meaning | Fix surface |
|-------|---------|-------------|
| **harness** | blank/white PNG but page OK in browser | capture timing / wait / full-page; re-capture before product fix |
| **product** | page itself broken | HM partial, CSS, demo data, assets under `packages/hatchi-maxchi/` |
| **by-design** | intentional sparse demo | dismiss: note in backlog DONE with reason; drop from queue via re-score |

### B3. Fix (product only)

- Edit **HM only** (components, registry demos, controllers, site assets)
- Rebuild as needed: `python packages/hatchi-maxchi/build.py` / site build
- Do **not** add Dazzle CSS for gallery polish

### B4. Verify

```bash
python scripts/hm_pages_vision.py --capture --stems <stem> \
  --base "file://$(pwd)/packages/hatchi-maxchi/site" \
  --out .dazzle/hm-hyperpart-coherence
# re-judge that stem (host Read PNG) or full batch if cheap
# re-ingest / update coherence.json for that stem
python scripts/hm_coherence_queue.py --status
```

Mark HMC row `DONE` when re-score is coherent (score ≥ 7, no high issues) **or**
harness-proven false positive.

### B5. Drain-cycle outcome

| Outcome | When |
|---------|------|
| `PASS` | ≥1 stem fixed + re-verified coherent |
| `FINDINGS` | Investigated; blocked on design intent / multi-cycle |
| `FAIL` | Fix attempted; still incoherent |
| `BLOCKED` | Cannot repro / missing site |

- `budget_consumed: 1`
- Log: `strategy: hyperpart_coherence` / `phase: drain` / stems + scores before→after
- Commit product fix: `improve: cycle N hm-convergence — coherence drain <stem>`

---

## Hard rules

- **Investigate produces queue; drain consumes queue.** Do not treat a one-off
  human walk of PNGs as a substitute for the machine queue.
- **One primary stem per drain cycle** (two if same root cause).
- **Advisory scores, real fixes** — CI does not fail on score; broken demos still fix.
- **Subscription only** for judgment — no metered vision APIs in the default loop.
- **Images over HTML dumps** for “does it look right?”
- Prefer **fix** high-severity over filing endless HMC noise; seed backlog when
  drain will span cycles.

## Related

- Queue MD: `packages/hatchi-maxchi/COHERENCE_QUEUE.md` (`--write`)
- Capture: `scripts/hm_pages_vision.py`
- Taste policy: `docs/reference/taste.md`
- Interaction complement: `improve/strategies/gallery_probes.md`
