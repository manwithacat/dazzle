# Metric tiles (`metrics`)

The KPI strip: label + value tiles in a packing grid, optionally toned. The server stamps the tile count for e2e anchors.

## Partial (copy-paste; the live demo renders this exact string)

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

## Guidance (prose; HTML from the registry notes field)

Each tile carries <code>data-dz-metric-key</code> (a stable anchor for tests/telemetry) and an optional <code>data-dz-tone</code>. In Dazzle one scope-aware GROUP BY query fills the whole strip — the tiles can never disagree with each other.
