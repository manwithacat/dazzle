# Metric tiles (`metrics`)

The KPI strip: label + value tiles in a packing grid, optionally toned. The server stamps the tile count for e2e anchors.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="metrics-grid" data-tile-count="3">
  <div class="metric-tile" data-metric-key="outstanding">
    <div class="metric-label">Outstanding</div>
    <div class="metric-value">£12,450</div>
  </div>
  <div class="metric-tile" data-metric-key="paid" data-tone="positive">
    <div class="metric-label">Paid this month</div>
    <div class="metric-value">£48,900</div>
  </div>
  <div class="metric-tile" data-metric-key="overdue" data-tone="warning">
    <div class="metric-label">Overdue</div>
    <div class="metric-value">3</div>
  </div>
</div>
```

## Notes

Each tile carries data-dz-metric-key (a stable anchor for tests/telemetry) and an optional data-dz-tone. In Dazzle one scope-aware GROUP BY query fills the whole strip — the tiles can never disagree with each other.
