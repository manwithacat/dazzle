# Progress stages (`progress-region`)

A native progress bar with stage chips — where the work is, stage by stage, with completion tones.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="progress-region hm-measure-lg">
  <div class="progress-header">
    <progress data-progress value="33" max="100"></progress>
    <span>33%</span>
  </div>
  <div class="progress-stages"><span class="progress-chip" data-stage-tone="complete">Draft (4)</span><span class="progress-chip" data-stage-tone="active">Review (2)</span><span class="progress-chip" data-stage-tone="empty">Published (0)</span></div>
  <p class="progress-summary">1 of 3 complete</p>
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

The bar is a NATIVE <progress> (styled via data-dz-progress) with its percent readout as a plain <span> beside it in the header; chips are plain text (Name (count)) toned by data-dz-stage-tone="complete|active|empty"; the summary paragraph follows the stages.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
