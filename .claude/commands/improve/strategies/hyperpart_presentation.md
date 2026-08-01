# Strategy: hyperpart_presentation

**Lane:** framework-ux (default) / example-apps when prove needs recapture
**Force path:** `/improve framework-ux hyperpart_presentation`
**Probe:** `dazzle qa hyperpart-opportunities --app <app> --table`
**Doctrine:** `docs/reference/hyperpart-presentation.md`
**Umbrella:** #1626 presentation process (antagonist 2026-08-01)

Closed **role × host → Hyperpart density** with shared `present()`. Replaces
ad-hoc “browse the gallery and maybe use Avatar” polish. **Stills beat claims.**

## When to pick

* Hero stills show person as labeled prose on queues (`Assigned To: Name`)
* Opportunity scan shows list chips but queue still stringifies (host incompleteness)
* Force path above

Skip when:

* Empty-hero / seed residual dominates → `demo_fleet` / `product_maturity` first
* Matrix row already proven on stills for the touched hosts

## Playbook (one matrix row or one host gap per cycle)

### 1. OBSERVE

```bash
dazzle demo quality -p examples/<app>   # or product_quality MCP
dazzle qa hyperpart-opportunities --app <app> --table
# open hero still under examples/<app>/.dazzle/qa/screenshots/
```

### 2. MAP

| Field | Role | Hosts | Current emit | Matrix |
|-------|------|-------|--------------|--------|
| assigned_to | person | queue_meta, list_cell | … | … |

Host disagree (list chip, queue plain) → **host incompleteness**, not partial credit.

### 3. SELECT

Lookupup `PRESENTATION_MATRIX` in `src/dazzle/render/presentation.py`.
Legal: matrix density or plain + `matrix_miss`. **No invention.**

### 4. IMPLEMENT

* Framework `present()` / user_chip / queue meta path — not one-app templates
* Person: prefer resolved entity dicts for initials
* Dual-lock `.dz-avatar` only

### 5. PROVE

```bash
# unit: person queue meta has .dz-avatar
pytest tests/unit/test_presentation_matrix_1626.py -q
.venv/bin/python scripts/recapture_demo_fleet_1626.py --apps <app>
# still: avatar present; no sole "Assigned To: Name" identity
```

### 6. RECORD

Matrix rows + still paths. Never claim fleet bake-off pass from residual alone.

## Hard rules

* No second avatar CSS class outside dual-lock
* No scanner-only PR without still mtime change when emit changed
* Mid-dot separators (R1) stay; they do not replace Avatar
* Catalogue/HM pick-a-surface is authoring — orthogonal to this emit process
