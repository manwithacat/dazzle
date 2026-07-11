# Chart legend (`chart-legend`)

The shared tail of every multi-series chart: swatch + series-name chips and a sample/series summary line.

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
- no typed contracts/ module yet — the partial is the surface of record

## DOM contract

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

Every SVG chart (line / area / radar / box-plot) ends with this pair instead of restyling it per chart: a <ul> of swatch + mono series-name items, and a mono summary line of bucket/series counts and the peak. The swatch background is the series colour the chart body uses for its strokes — inline, per series, server-assigned.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
