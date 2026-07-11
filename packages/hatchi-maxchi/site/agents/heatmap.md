# Heatmap (`heatmap`)

A two-dimensional grid of toned cells — rows × buckets, thresholds driving good/warn/bad tones, never colour alone (the value is IN the cell).

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="heatmap-region hm-measure-lg">
  <div class="heatmap-scroll">
    <table class="heatmap-grid">
      <thead>
        <tr>
          <th></th>
          <th>Mon</th>
          <th>Tue</th>
          <th>Wed</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td class="heatmap-row-label">API</td>
          <td class="heatmap-cell" data-heatmap-tone="good"> 99.9 </td>
          <td class="heatmap-cell" data-heatmap-tone="good"> 99.7 </td>
          <td class="heatmap-cell" data-heatmap-tone="warn"> 97.2 </td>
        </tr>
        <tr>
          <td class="heatmap-row-label">Webhooks</td>
          <td class="heatmap-cell" data-heatmap-tone="warn"> 96.1 </td>
          <td class="heatmap-cell" data-heatmap-tone="bad"> 89.4 </td>
          <td class="heatmap-cell" data-heatmap-tone="good"> 99.2 </td>
        </tr>
      </tbody>
    </table>
  </div>
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

Cell tones ride data-dz-heatmap-tone="good|warn|bad", resolved server-side against the declared thresholds — and the numeric value always renders inside the cell, so tone is reinforcement, not the only signal. Overflowing grids append a dz-heatmap-overflow count line; the scroll wrapper keeps wide grids inside their card.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
