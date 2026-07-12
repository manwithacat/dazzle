# Box plot (`box-plot`)

Distribution five-number summaries per bucket — a server-rendered SVG with the counts in the summary line.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="box-plot-region hm-measure-lg" data-box-plot>
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 48" role="img" aria-label="Box plot — 3 buckets"><line x1="20" y1="8" x2="20" y2="40" stroke="var(--colour-text-muted)"/><rect x="8" y="16" width="24" height="16" fill="var(--colour-brand)" fill-opacity="0.25" stroke="var(--colour-brand)"/><line x1="8" y1="24" x2="32" y2="24" stroke="var(--colour-brand)" stroke-width="2"/><line x1="90" y1="4" x2="90" y2="44" stroke="var(--colour-text-muted)"/><rect x="78" y="12" width="24" height="22" fill="var(--colour-brand)" fill-opacity="0.25" stroke="var(--colour-brand)"/><line x1="78" y1="20" x2="102" y2="20" stroke="var(--colour-brand)" stroke-width="2"/><line x1="160" y1="10" x2="160" y2="38" stroke="var(--colour-text-muted)"/><rect x="148" y="18" width="24" height="14" fill="var(--colour-brand)" fill-opacity="0.25" stroke="var(--colour-brand)"/><line x1="148" y1="26" x2="172" y2="26" stroke="var(--colour-brand)" stroke-width="2"/></svg>
  <p class="box-plot-summary">3 groups · 0 samples</p>
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

### `contracts/box_plot.py`

- **Required root:** `[data-dz-box-plot]` (part `box-plot`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-box-plot]` | `data-dz-box-plot` | present (any value) |

#### Ingestion model `BoxPlotGroup`

| Field | Type | Required |
|---|---|---|
| `label` | `string` | yes |
| `min` | `number` | no |
| `q1` | `number` | no |
| `median` | `number` | no |
| `q3` | `number` | no |
| `max` | `number` | no |
| `samples` | `integer` | no |

#### Exemplar `render()`

```python
def render(b: BoxPlot) -> str:
    """Model → box-plot region."""
    if not b.groups:
        return (
            f'<div class="dz-box-plot-region" data-dz-box-plot>'
            f'<p class="dz-empty-dense" role="status">'
            f"{html.escape(b.empty_message)}</p>"
            f"</div>"
        )
    n_total = sum(g.samples for g in b.groups)
    summary = f'<p class="dz-box-plot-summary">{len(b.groups)} groups · {n_total} samples</p>'
    return f'<div class="dz-box-plot-region" data-dz-box-plot>{b.svg_html}{summary}</div>'
```

## Notes

Dual-lock root is data-dz-box-plot (contracts/box_plot.py). Schematic demo — real whisker/quartile geometry is server-computed via dazzle.render.svg.box_plot_svg and rides trusted svg_html. The summary line carries group count and sample total.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/box_plot.py`
