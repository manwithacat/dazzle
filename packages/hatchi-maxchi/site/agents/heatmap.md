# Heatmap (`heatmap`)

A two-dimensional grid of toned cells — rows × buckets, thresholds driving good/warn/bad tones, never colour alone (the value is IN the cell).

## Partial (copy-paste; the live demo renders this exact string)

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

## Guidance (prose; HTML from the registry notes field)

Cell tones ride <code>data-dz-heatmap-tone=&quot;good|warn|bad&quot;</code>, resolved server-side against the declared thresholds — and the numeric value always renders inside the cell, so tone is reinforcement, not the only signal. Overflowing grids append a <code>dz-heatmap-overflow</code> count line; the scroll wrapper keeps wide grids inside their card.
