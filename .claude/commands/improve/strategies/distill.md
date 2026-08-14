# Strategy: distill

**Lane:** example-apps
**Force path:** `/improve example-apps distill` · `/improve example-apps distill <app>`
**Doctrine:** Goal C — a lead can work the first screen. Residual: `scripts/goal_b_coat.py`
**Opposite of:** `interesting_product` (add depth). This strategy **subtracts**.

When Goal A is green and a desk is a filter wall (conversation siblings,
enum×ball cartesian slices, document-rail pile, or a 12+ focus list), do **not**
add another Goal B slice. Delete until the flag drops or one honest grain
remains. Lower `FREEZE` in the same ship. Recapture a quieter still.

---

## When to pick

* `goal_b_coat residual_total>0` (probe or `improve_policy.py --status`)
* Operator force: `/improve example-apps distill` / `… distill support_tickets`

Skip when:

* product / demo / journey / presentation residual > 0 (Goal A / chrome first)
* The named app’s `coat_flag=0` — pick the probe `next=` app or stop

---

## Honest grain (done)

| Signal | Cap | Meaning |
|--------|-----|---------|
| `conv_siblings` | 2 | One thread + one pressure trail on the same source |
| `slice_cartesian` | 0 | No enum × `ball_in_court` extra slices |
| `document_rails` | 8 | Not a rail per settlement flavour |
| `max_focus` | 12 | Not a 19-wide focus list |

`metric_keys` is diagnostic. Do not distill a desk only because it has 12 tiles.

---

## Playbook (one app)

### 1. OBSERVE

```bash
uv run python scripts/goal_b_coat.py --status
uv run python scripts/goal_b_coat.py --json
# honor next= unless operator named an app
```

Log `app`, `conv_sib`, `cartesian`, `focus`, `rails`, `sibling_key`.

### 2. SELECT what to delete

On the worst workspace (`sibling_key`):

* Keep **one** live thread (`live_conversation` / hub `display: conversation`).
* Keep **at most one** pressure trail (`needs_reply` / ball-only).
* Delete synonym slices (`thankful_*`, `medium_*`, channel×ball, escalation×ball).
* Drop matching `count()` metric keys and `focus:` entries.
* Document desks: keep one packet/line spine; delete extra `*_rail` / `*_watch`.

Do **not** invent a field or a new region this cycle.

### 3. IMPLEMENT

* Edit DSL only on that app.
* Remove or rewrite Goal B **floor** unit tests that assert a deleted region
  exists. Add nothing that requires the coat to stay.
* **Lower `FREEZE` in `scripts/goal_b_coat.py`** to the new live counts
  (same ship). If you don’t, the ratchet still describes the wall.

### 4. PROVE

```bash
uv run python scripts/goal_b_coat.py --status   # this app flag=0 or over dropped
uv run pytest tests/unit/test_goal_b_coat.py tests/unit/test_<app>_*_goal_b.py -q
.venv/bin/python scripts/recapture_demo_fleet_1626.py --apps <app>
```

Still must look **quieter** above the fold (fewer regions), not new chrome.

### 5. RECORD

```text
depth_id: distill
harness_only: false
app: <showcase>
coat_before: siblings=… cartesian=… focus=…
coat_after: …
freeze_lowered: yes
```

One app per cycle. Stop when that app’s `coat_flag=0` or honest grain is met
on the worst desk. Do not start a second app.

`require_mutation` is **on** — a deletion is a ship.
