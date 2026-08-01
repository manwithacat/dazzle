# Strategy: hyperpart_presentation

**Lane:** framework-ux (default) / example-apps when prove needs recapture
**Force path:** `/improve framework-ux hyperpart_presentation`
**Also:** `/improve example-apps hyperpart_presentation` (recapture / seed only)
**Probe:** `dazzle qa hyperpart-opportunities --app <app> --table`
**MCP:** `presentation` (cognition \| opportunities \| residual) · `product_quality` (score folds presentation residual)
**KG:** `knowledge(operation=counter_prior, id=ref_as_repr)` · doctrine page `hyperpart-presentation`
**Doctrine:** `docs/reference/hyperpart-presentation.md`
**Umbrella:** #1626 presentation process (antagonist 2026-08-01)

Closed **role × host → Hyperpart density** with shared `present()`. Replaces
ad-hoc “browse the gallery and maybe use Avatar” polish. **Stills beat claims.**

## When to pick

* `product_quality` / `dazzle demo quality` shows **presentation residual** (`ref_as_repr` / `person_as_text`)
* Hero stills show person as labeled prose on queues (`Assigned To: Name`)
* Hero stills show entity refs as dict/UUID (`Device: {'id': UUID(...)}`)
* Opportunity scan shows list chips but queue still stringifies (host incompleteness)
* Force path above

Skip when:

* Empty-hero / seed residual dominates → `demo_fleet` / `product_maturity` first
* Matrix row already proven on stills for the touched hosts

## Playbook (one matrix row or one host gap per cycle)

### 1. OBSERVE

```bash
dazzle demo quality -p examples/<app>   # residual_total includes presentation
dazzle qa hyperpart-opportunities --app <app> --table
# MCP (preferred for downstream consumers):
#   product_quality(operation=score, project_root=examples/<app>)
#   presentation(operation=cognition)
#   presentation(operation=opportunities, app=<app>)
#   presentation(operation=residual, app=<app>)
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

## Cognition snapshot (always read)

```bash
# JSON includes presentation_cognition — hosts audited vs matrix-only
cd examples/<app> && dazzle qa hyperpart-opportunities --stdout | head -c 4000
python -c "from dazzle.render.presentation import cognition_snapshot; import json; print(json.dumps(cognition_snapshot(), indent=2))"
```

If `person_rows_all_emit_covered` and caveat says un-audited hosts remain → **still open the PNG**.

## Creativity (closed)

Select matrix densities only. To add capability: matrix row → `present()` → test → recapture.
Do not invent assignee formats. Proposal-quality creativity = good role mapping + justified matrix extension with still evidence.

## Hard rules

* No second avatar CSS class outside dual-lock
* No scanner-only PR without still mtime change when emit changed
* Mid-dot separators (R1) stay; they do not replace Avatar
* Catalogue/HM pick-a-surface is authoring — orthogonal to this emit process
* Do not grow the matrix without a still that proves the host gap
