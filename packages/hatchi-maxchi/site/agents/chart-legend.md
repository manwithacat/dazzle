# Chart legend (`chart-legend`)

The shared tail of every multi-series chart: swatch + series-name chips and a sample/series summary line.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-measure-lg">
  <ul class="chart-legend">
    <li class="chart-legend-item"><span class="chart-legend-swatch" style="background:var(--colour-brand)"></span><span class="chart-legend-name">Revenue</span></li>
    <li class="chart-legend-item"><span class="chart-legend-swatch" style="background:var(--colour-success)"></span><span class="chart-legend-name">Costs</span></li>
  </ul>
  <p class="chart-summary">12 buckets · 2 series · peak £48,900</p>
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

### `contracts/chart_legend.py`

- **Required root:** `.dz-chart-legend` (part `chart_legend`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-chart-legend` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: chart_legend — shared multi-series chart legend (swatch + name).

Dual-lock unit is the legend list root. Items, swatch colours, series names,
and the optional summary line are host-owned. Class ``.dz-chart-legend`` is
the stable substrate root (gallery CSS; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="chart_legend",
    root=".dz-chart-legend",
    nodes=(Node(".dz-chart-legend", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Every SVG chart (line / area / radar / box-plot) ends with this pair instead of restyling it per chart: a <ul> of swatch + mono series-name items, and a mono summary line of bucket/series counts and the peak. The swatch background is the series colour the chart body uses for its strokes — inline, per series, server-assigned. Dual-lock root .dz-chart-legend (HMC-142).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/chart_legend.py`
