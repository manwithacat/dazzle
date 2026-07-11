# Sparkline (`sparkline`)

A headline number with its recent shape — the smallest chart: a current value, its bucket label, and an area glyph.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="sparkline-region">
  <div class="sparkline-headline"><span class="sparkline-value">184ms</span><span class="sparkline-bucket-label">this hour</span></div>
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 32" class="sparkline-svg" role="img" aria-label="Sparkline — 12 points, latest 184ms, peak 240ms"><polygon points="0,32 0,20 18,18 36,22 54,14 72,16 90,10 108,12 126,8 144,14 162,6 180,9 180,32" fill="var(--colour-brand)" fill-opacity="0.15" stroke="none"/><polyline points="0,20 18,18 36,22 54,14 72,16 90,10 108,12 126,8 144,14 162,6 180,9" fill="none" stroke="var(--colour-brand)" stroke-width="1.25" stroke-linejoin="round" stroke-linecap="round"/></svg>
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

The SVG is server-rendered with a numeric summary in aria-label (points / latest / peak) — the glyph is decoration; the numbers are the content. An empty series renders dz-sparkline-empty; a single point renders the headline alone.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
