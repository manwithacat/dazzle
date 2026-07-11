# Funnel (`funnel`)

Stage-by-stage narrowing — each bar's width is the stage's share, with a total summary line.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="funnel-chart-region hm-measure-lg" data-funnel>
  <div class="funnel-stages">
    <div class="funnel-stage-row">
      <div class="funnel-stage" data-funnel-step="0" style="width: 100%;"><span class="funnel-stage-label">Visited</span><span class="funnel-stage-count"> (1,204)</span></div>
    </div>
    <div class="funnel-stage-row">
      <div class="funnel-stage" data-funnel-step="1" style="width: 62%;"><span class="funnel-stage-label">Signed up</span><span class="funnel-stage-count"> (746)</span></div>
    </div>
    <div class="funnel-stage-row">
      <div class="funnel-stage" data-funnel-step="2" style="width: 28%;"><span class="funnel-stage-label">Subscribed</span><span class="funnel-stage-count"> (338)</span></div>
    </div>
  </div>
  <p class="funnel-summary">1,204 total</p>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- no Server exchange on this part — pure presentation or client chrome
- satisfy the DOM contract tables (CI stop-ship)

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/funnel.py`

- **Required root:** `[data-dz-funnel]` (part `funnel`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-funnel]` | `data-dz-funnel` | present (any value) |

#### Ingestion model `FunnelStage`

| Field | Type | Required |
|---|---|---|
| `label` | `string` | yes |
| `count` | `integer` | no |

#### Exemplar `render()`

```python
def render(f: Funnel) -> str:
    """Model → funnel chart region."""
    if not f.stages:
        return (
            f'<div class="dz-funnel-chart-region" data-dz-funnel>'
            f'<p class="dz-empty-dense" role="status">'
            f"{html.escape(f.empty_message)}</p>"
            f"</div>"
        )

    base = f.stages[0].count if f.stages[0].count > 0 else 1
    items: list[str] = []
    for i, stage in enumerate(f.stages):
        pct = int(stage.count / base * 100)
        width = pct if pct >= 20 else 20
        step = i if i < 8 else 7
        items.append(
            f'<div class="dz-funnel-stage-row">'
            f'<div class="dz-funnel-stage" '
            f'data-dz-funnel-step="{step}" '
            f'style="width: {width}%;">'
            f'<span class="dz-funnel-stage-label">{html.escape(stage.label)}</span> '
            f'<span class="dz-funnel-stage-count">({stage.count})</span>'
            f"</div>"
            f"</div>"
        )

    total = f.total if f.total else f.stages[0].count
    return (
        f'<div class="dz-funnel-chart-region" data-dz-funnel>'
        f'<div class="dz-funnel-stages">{"".join(items)}</div>'
        f'<p class="dz-funnel-summary">{total} total</p>'
        f"</div>"
    )
```

## Notes

Dual-lock root is data-dz-funnel (contracts/funnel.py). Widths are SERVER-computed percentages on inline style — the one place inline style is the contract (a per-row datum, like the progress knob). data-dz-funnel-step tones the stages in sequence.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/funnel.py`
