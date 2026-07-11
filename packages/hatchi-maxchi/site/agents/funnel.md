# Funnel (`funnel`)

Stage-by-stage narrowing — each bar's width is the stage's share, with a total summary line.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="funnel-chart-region hm-measure-lg">
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
- no typed contracts/ module yet — the partial is the surface of record

## DOM contract

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

Widths are SERVER-computed percentages on inline style — the one place inline style is the contract (a per-row datum, like the progress knob). data-dz-funnel-step tones the stages in sequence.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
