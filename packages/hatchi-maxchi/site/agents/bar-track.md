# Bar track (`bar-track`)

Value-against-capacity rows with real progressbar semantics — the resource-usage sibling of the bar chart.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="bar-track-region hm-measure-lg">
  <div class="bar-track-rows">
    <div class="bar-track-row">
      <span class="bar-track-label" title="Storage">Storage</span>
      <div class="bar-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="62" aria-label="Storage: 62%"><span class="bar-track-fill" style="width: 62%;" title="Storage: 62%"></span></div>
      <span class="bar-track-value">62%</span>
    </div>
    <div class="bar-track-row">
      <span class="bar-track-label" title="Compute">Compute</span>
      <div class="bar-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="38" aria-label="Compute: 38%"><span class="bar-track-fill" style="width: 38%;" title="Compute: 38%"></span></div>
      <span class="bar-track-value">38%</span>
    </div>
  </div>
</div>
```

## Notes

Each track is a real role="progressbar" with numeric aria values — the fill width is presentation, the aria is the content. Labels and fills both carry title for hover detail.
