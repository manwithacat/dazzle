# Heatmap (`heatmap`)

A two-dimensional grid of toned cells — rows × buckets, thresholds driving good/warn/bad tones, never colour alone (the value is IN the cell).

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

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

## Notes

Cell tones ride data-dz-heatmap-tone="good|warn|bad", resolved server-side against the declared thresholds — and the numeric value always renders inside the cell, so tone is reinforcement, not the only signal. Overflowing grids append a dz-heatmap-overflow count line; the scroll wrapper keeps wide grids inside their card.
