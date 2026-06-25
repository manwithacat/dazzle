# UX Catalogue

Every component below is rendered from real Dazzle DSL through the real render pipeline — the same code that produces a running app's HTML. Each card shows the live component and the DSL that produced it.

## List

The workhorse table. Here it carries the `outlier_on` decorator — the `latency_ms` cell flags the statistical outlier (⚠ high) vs the displayed rows.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_list" id="region-cat_list"><div class="dz-list-region"><div class="dz-list-actions"><div class="dz-list-action-group"><button type="button" data-dz-csv-endpoint="/api/workspaces/ux_catalogue/regions/cat_list" data-dz-csv-filename="cat_list.csv" onclick="window.dz.downloadCsv(this.dataset.dzCsvEndpoint, this.dataset.dzCsvFilename)" class="dz-list-csv-button" title="Export CSV" aria-label="Export CSV"><svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg></button></div></div><div class="dz-list-scroll"><table class="dz-list-table"><thead><tr><th>Name</th><th>Team</th><th>Status</th><th>Latency Ms</th><th>Error Rate</th><th>Target Ms</th></tr></thead><tbody><tr class="dz-list-row "><td>alpha</td><td>platform</td><td>healthy</td><td>42</td><td>0.1</td><td>50</td></tr><tr class="dz-list-row "><td>bravo</td><td>platform</td><td>healthy</td><td>38</td><td>0.2</td><td>50</td></tr><tr class="dz-list-row "><td>charlie</td><td>payments</td><td>degraded</td><td>44</td><td>1.4</td><td>50</td></tr><tr class="dz-list-row "><td>delta</td><td>payments</td><td>healthy</td><td>40</td><td>0.3</td><td>50</td></tr><tr class="dz-list-row "><td>echo</td><td>growth</td><td>healthy</td><td>46</td><td>0.2</td><td>50</td></tr><tr class="dz-list-row "><td>foxtrot</td><td>data</td><td>critical</td><td><div class="dz-row dz-row--gap-sm dz-row--align-center">380<span class="dz-badge dz-badge-sm" data-dz-tone="warning" role="status" aria-label="Outlier: high">⚠ high</span></div></td><td>7.2</td><td>50</td></tr></tbody></table></div></div></div>
</div>

```dsl
cat_list:
  source: Box
  display: list
  sort: name asc
  outlier_on: latency_ms
  outlier_method: iqr
  empty: "No boxes"
```

## Metrics

KPI tiles — scalar aggregates over the scoped set.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_metrics" id="region-cat_metrics"><div class="dz-metrics-grid" data-dz-tile-count="3"><div class="dz-metric-tile" data-dz-metric-key="total"><div class="dz-metric-label">Total</div><div class="dz-metric-value">42</div></div><div class="dz-metric-tile" data-dz-metric-key="critical"><div class="dz-metric-label">Critical</div><div class="dz-metric-value">7</div></div><div class="dz-metric-tile" data-dz-metric-key="avg_latency"><div class="dz-metric-label">Avg Latency</div><div class="dz-metric-value">41</div></div></div></div>
</div>

```dsl
cat_metrics:
  source: Box
  display: metrics
  aggregate:
    total: count(Box)
    critical: count(Box where status = critical)
    avg_latency: avg(latency_ms)
```

## Bar Chart

Distribution by a category — one bar per group. One scope-aware GROUP BY.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_bar_chart" id="region-cat_bar_chart"><div class="dz-bar-chart-region"><div class="dz-bar-chart-bars"><div class="dz-bar-chart-row"><span class="dz-bar-chart-label"><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Platform">Platform</span></span><div class="dz-bar-chart-track"><div class="dz-bar-chart-fill" style="width: 100%"></div></div><span class="dz-bar-chart-value">8</span></div><div class="dz-bar-chart-row"><span class="dz-bar-chart-label"><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Payments">Payments</span></span><div class="dz-bar-chart-track"><div class="dz-bar-chart-fill" style="width: 100%"></div></div><span class="dz-bar-chart-value">8</span></div><div class="dz-bar-chart-row"><span class="dz-bar-chart-label"><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Growth">Growth</span></span><div class="dz-bar-chart-track"><div class="dz-bar-chart-fill" style="width: 100%"></div></div><span class="dz-bar-chart-value">8</span></div><div class="dz-bar-chart-row"><span class="dz-bar-chart-label"><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Data">Data</span></span><div class="dz-bar-chart-track"><div class="dz-bar-chart-fill" style="width: 100%"></div></div><span class="dz-bar-chart-value">8</span></div></div></div></div>
</div>

```dsl
cat_bar_chart:
  source: Box
  display: bar_chart
  group_by: team
  aggregate:
    count: count(Box)
  empty: "No boxes"
```

## Comparison

Ranked league — rows ranked by a metric with inline bars + automatic outlier flag.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_comparison" id="region-cat_comparison"><div class="dz-bar-track-region"><div class="dz-bar-track-rows"><div class="dz-bar-track-row"><span class="dz-bar-track-label" title="1. platform">1. platform</span><div class="dz-bar-track" role="progressbar" aria-valuemin="0" aria-valuemax="12" aria-valuenow="12" aria-label="1. platform: 12.00"><span class="dz-bar-track-fill" style="width: 100%;" title="1. platform: 12.00"></span></div><span class="dz-bar-track-value">12.00</span></div><div class="dz-bar-track-row"><span class="dz-bar-track-label" title="2. payments">2. payments</span><div class="dz-bar-track" role="progressbar" aria-valuemin="0" aria-valuemax="12" aria-valuenow="11" aria-label="2. payments: 11.00"><span class="dz-bar-track-fill" style="width: 91.67%;" title="2. payments: 11.00"></span></div><span class="dz-bar-track-value">11.00</span></div><div class="dz-bar-track-row"><span class="dz-bar-track-label" title="3. growth">3. growth</span><div class="dz-bar-track" role="progressbar" aria-valuemin="0" aria-valuemax="12" aria-valuenow="10" aria-label="3. growth: 10.00"><span class="dz-bar-track-fill" style="width: 83.33%;" title="3. growth: 10.00"></span></div><span class="dz-bar-track-value">10.00</span></div><div class="dz-bar-track-row"><span class="dz-bar-track-label" title="4. data">4. data</span><div class="dz-bar-track" role="progressbar" aria-valuemin="0" aria-valuemax="12" aria-valuenow="9" aria-label="4. data: 9.00"><span class="dz-bar-track-fill" style="width: 75%;" title="4. data: 9.00"></span></div><span class="dz-bar-track-value">9.00</span></div><div class="dz-bar-track-row"><span class="dz-bar-track-label" title="5. infra">5. infra</span><div class="dz-bar-track" role="progressbar" aria-valuemin="0" aria-valuemax="12" aria-valuenow="9" aria-label="5. infra: 9.00"><span class="dz-bar-track-fill" style="width: 75%;" title="5. infra: 9.00"></span></div><span class="dz-bar-track-value">9.00</span></div><div class="dz-bar-track-row"><span class="dz-bar-track-label" title="6. ml">6. ml</span><div class="dz-bar-track" role="progressbar" aria-valuemin="0" aria-valuemax="12" aria-valuenow="1" aria-label="6. ml: 1.00"><span class="dz-bar-track-fill" style="width: 8.33%;" title="6. ml: 1.00"></span></div><span class="dz-bar-track-value">1.00</span></div></div><p class="dz-bar-track-summary">6 rows · scale 0–12</p></div></div>
</div>

```dsl
cat_comparison:
  source: Box
  display: comparison
  group_by: team
  aggregate:
    total: count(Box)
  rank_by: total
  order: desc
  outlier_method: iqr
  empty: "No boxes"
```

## Heatmap

Matrix density — latency shaded across team × status.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_heatmap" id="region-cat_heatmap"><div class="dz-heatmap-region"><div class="dz-heatmap-scroll"><table class="dz-heatmap-grid"><thead><tr><th></th><th>critical</th><th>degraded</th><th>healthy</th></tr></thead><tbody><tr><td class="dz-heatmap-row-label">data</td><td class="dz-heatmap-cell"> 380.0 </td><td class="dz-heatmap-cell"> 0.0 </td><td class="dz-heatmap-cell"> 0.0 </td></tr><tr><td class="dz-heatmap-row-label">growth</td><td class="dz-heatmap-cell"> 0.0 </td><td class="dz-heatmap-cell"> 0.0 </td><td class="dz-heatmap-cell"> 46.0 </td></tr><tr><td class="dz-heatmap-row-label">payments</td><td class="dz-heatmap-cell"> 0.0 </td><td class="dz-heatmap-cell"> 44.0 </td><td class="dz-heatmap-cell"> 40.0 </td></tr><tr><td class="dz-heatmap-row-label">platform</td><td class="dz-heatmap-cell"> 0.0 </td><td class="dz-heatmap-cell"> 0.0 </td><td class="dz-heatmap-cell"> 38.0 </td></tr></tbody></table></div><p class="dz-heatmap-overflow">Showing 4 of 6</p></div></div>
</div>

```dsl
cat_heatmap:
  source: Box
  display: heatmap
  rows: team
  columns: status
  value: latency_ms
  empty: "No boxes"
```

## Pivot Table

Cross-tab — counts across two dimensions (team × status).

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_pivot" id="region-cat_pivot"><div class="dz-pivot-region"><div class="dz-pivot-scroll"><table class="dz-pivot-grid"><thead><tr><th>Team</th><th>Status</th><th class="is-measure">Team</th><th class="is-measure">Status</th><th class="is-measure">Count</th></tr></thead><tbody><tr><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Platform">Platform</span></td><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Healthy">Healthy</span></td><td class="is-measure">platform</td><td class="is-measure">healthy</td><td class="is-measure">8</td></tr><tr><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Platform">Platform</span></td><td><span class="dz-badge dz-badge-sm " data-dz-tone="destructive" role="status" aria-label="Status: Critical">Critical</span></td><td class="is-measure">platform</td><td class="is-measure">critical</td><td class="is-measure">1</td></tr><tr><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Payments">Payments</span></td><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Healthy">Healthy</span></td><td class="is-measure">payments</td><td class="is-measure">healthy</td><td class="is-measure">6</td></tr><tr><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Payments">Payments</span></td><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Degraded">Degraded</span></td><td class="is-measure">payments</td><td class="is-measure">degraded</td><td class="is-measure">2</td></tr></tbody></table></div><p class="dz-pivot-summary">4 rows</p></div></div>
</div>

```dsl
cat_pivot:
  source: Box
  display: pivot_table
  group_by: [team, status]
  aggregate:
    count: count(Box)
  empty: "No boxes"
```

## Bullet

Actual-vs-target rows — each box's latency against its target.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_bullet" id="region-cat_bullet"><div class="dz-bullet-region"><div class="dz-bullet-rows"><div class="dz-bullet-row"><span class="dz-bullet-label">alpha</span><div class="dz-bullet-track"><span class="dz-bullet-actual" style="width: 11.05%;" title="alpha actual: 42"></span><span class="dz-bullet-target" style="left: 13.16%;" title="alpha target: 50"></span></div><span class="dz-bullet-value">42 / 50</span></div><div class="dz-bullet-row"><span class="dz-bullet-label">bravo</span><div class="dz-bullet-track"><span class="dz-bullet-actual" style="width: 10.0%;" title="bravo actual: 38"></span><span class="dz-bullet-target" style="left: 13.16%;" title="bravo target: 50"></span></div><span class="dz-bullet-value">38 / 50</span></div><div class="dz-bullet-row"><span class="dz-bullet-label">charlie</span><div class="dz-bullet-track"><span class="dz-bullet-actual" style="width: 11.58%;" title="charlie actual: 44"></span><span class="dz-bullet-target" style="left: 13.16%;" title="charlie target: 50"></span></div><span class="dz-bullet-value">44 / 50</span></div><div class="dz-bullet-row"><span class="dz-bullet-label">delta</span><div class="dz-bullet-track"><span class="dz-bullet-actual" style="width: 10.53%;" title="delta actual: 40"></span><span class="dz-bullet-target" style="left: 13.16%;" title="delta target: 50"></span></div><span class="dz-bullet-value">40 / 50</span></div><div class="dz-bullet-row"><span class="dz-bullet-label">echo</span><div class="dz-bullet-track"><span class="dz-bullet-actual" style="width: 12.11%;" title="echo actual: 46"></span><span class="dz-bullet-target" style="left: 13.16%;" title="echo target: 50"></span></div><span class="dz-bullet-value">46 / 50</span></div><div class="dz-bullet-row"><span class="dz-bullet-label">foxtrot</span><div class="dz-bullet-track"><span class="dz-bullet-actual" style="width: 100.0%;" title="foxtrot actual: 380"></span><span class="dz-bullet-target" style="left: 13.16%;" title="foxtrot target: 50"></span></div><span class="dz-bullet-value">380 / 50</span></div></div><p class="dz-bullet-summary">6 rows · scale 0–380</p></div></div>
</div>

```dsl
cat_bullet:
  source: Box
  display: bullet
  bullet_label: name
  bullet_actual: latency_ms
  bullet_target: target_ms
  empty: "No boxes"
```

## Kanban

Board view — boxes grouped into status columns.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_kanban" id="region-cat_kanban"><div class="dz-kanban-board"><div class="dz-kanban-column"><div class="dz-kanban-column-head"><span class="dz-badge  " data-dz-tone="neutral" role="status" aria-label="Status: Healthy">Healthy</span><span class="dz-kanban-column-count">4</span></div><div class="dz-kanban-stack"><div class="dz-kanban-card"><div class="dz-kanban-card-body"><h4 class="dz-kanban-card-title">alpha</h4><p class="dz-kanban-card-field"><span>Team:</span> platform</p><p class="dz-kanban-card-field"><span>Latency Ms:</span> 42</p><p class="dz-kanban-card-field"><span>Error Rate:</span> 0.1</p><p class="dz-kanban-card-field"><span>Target Ms:</span> 50</p></div></div><div class="dz-kanban-card"><div class="dz-kanban-card-body"><h4 class="dz-kanban-card-title">bravo</h4><p class="dz-kanban-card-field"><span>Team:</span> platform</p><p class="dz-kanban-card-field"><span>Latency Ms:</span> 38</p><p class="dz-kanban-card-field"><span>Error Rate:</span> 0.2</p><p class="dz-kanban-card-field"><span>Target Ms:</span> 50</p></div></div><div class="dz-kanban-card"><div class="dz-kanban-card-body"><h4 class="dz-kanban-card-title">delta</h4><p class="dz-kanban-card-field"><span>Team:</span> payments</p><p class="dz-kanban-card-field"><span>Latency Ms:</span> 40</p><p class="dz-kanban-card-field"><span>Error Rate:</span> 0.3</p><p class="dz-kanban-card-field"><span>Target Ms:</span> 50</p></div></div><div class="dz-kanban-card"><div class="dz-kanban-card-body"><h4 class="dz-kanban-card-title">echo</h4><p class="dz-kanban-card-field"><span>Team:</span> growth</p><p class="dz-kanban-card-field"><span>Latency Ms:</span> 46</p><p class="dz-kanban-card-field"><span>Error Rate:</span> 0.2</p><p class="dz-kanban-card-field"><span>Target Ms:</span> 50</p></div></div></div></div><div class="dz-kanban-column"><div class="dz-kanban-column-head"><span class="dz-badge  " data-dz-tone="neutral" role="status" aria-label="Status: Degraded">Degraded</span><span class="dz-kanban-column-count">1</span></div><div class="dz-kanban-stack"><div class="dz-kanban-card"><div class="dz-kanban-card-body"><h4 class="dz-kanban-card-title">charlie</h4><p class="dz-kanban-card-field"><span>Team:</span> payments</p><p class="dz-kanban-card-field"><span>Latency Ms:</span> 44</p><p class="dz-kanban-card-field"><span>Error Rate:</span> 1.4</p><p class="dz-kanban-card-field"><span>Target Ms:</span> 50</p></div></div></div></div><div class="dz-kanban-column"><div class="dz-kanban-column-head"><span class="dz-badge  " data-dz-tone="destructive" role="status" aria-label="Status: Critical">Critical</span><span class="dz-kanban-column-count">1</span></div><div class="dz-kanban-stack"><div class="dz-kanban-card"><div class="dz-kanban-card-body"><h4 class="dz-kanban-card-title">foxtrot</h4><p class="dz-kanban-card-field"><span>Team:</span> data</p><p class="dz-kanban-card-field"><span>Latency Ms:</span> 380</p><p class="dz-kanban-card-field"><span>Error Rate:</span> 7.2</p><p class="dz-kanban-card-field"><span>Target Ms:</span> 50</p></div></div></div></div></div></div>
</div>

```dsl
cat_kanban:
  source: Box
  display: kanban
  group_by: status
  empty: "No boxes"
```

## Insight Summary

A grounded, deterministic narrative — scale + leader + outlier — over a grouped aggregate, with the underlying values cited so every claim is verifiable. No LLM (that's Slice 2).

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_insight" id="region-cat_insight"><div class="dz-stack dz-stack--gap-sm"><span class="dz-text dz-text--tone-default">91 count across 6 team.</span><span class="dz-text dz-text--tone-default">platform is highest at 20 (22% of the total).</span><span class="dz-text dz-text--tone-default">ml is anomalously low at 1.</span><span class="dz-text dz-text--tone-muted">Based on: platform 20 · payments 19 · growth 18 · data 17 · infra 16 · ml 1</span><span class="dz-text dz-text--tone-muted">across all team · Computed from live data</span></div></div>
</div>

```dsl
cat_insight:
  source: Box
  display: insight_summary
  group_by: team
  aggregate:
    count: count(Box)
```
