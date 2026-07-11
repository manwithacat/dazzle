# UX Catalogue

Every component below is rendered from real Dazzle DSL through the real render pipeline — the same code that produces a running app's HTML. Each card shows the live component and the DSL that produced it.

## List

The workhorse table. Here it carries the `outlier_on` decorator — the `latency_ms` cell flags the statistical outlier (⚠ high) vs the displayed rows.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_list" id="region-cat_list"><div class="dz-list-region"><div class="dz-list-actions"><div class="dz-list-action-group"><button type="button" data-dz-csv-endpoint="/api/workspaces/ux_catalogue/regions/cat_list" data-dz-csv-filename="cat_list.csv" onclick="window.dz.downloadCsv(this.dataset.dzCsvEndpoint, this.dataset.dzCsvFilename)" class="dz-list-csv-button" title="Export CSV" aria-label="Export CSV"><svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg></button></div></div><div class="dz-list-scroll"><table class="dz-list-table"><thead><tr><th>Name</th><th>Team</th><th>Status</th><th>Latency Ms</th><th>Error Rate</th><th>Target Ms</th></tr></thead><tbody><tr data-dz-list-kind="region" class="dz-list-row "><td>alpha</td><td>platform</td><td>healthy</td><td>42</td><td>0.1</td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>bravo</td><td>platform</td><td>healthy</td><td>38</td><td>0.2</td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>charlie</td><td>payments</td><td>degraded</td><td>44</td><td>1.4</td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>delta</td><td>payments</td><td>healthy</td><td>40</td><td>0.3</td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>echo</td><td>growth</td><td>healthy</td><td>46</td><td>0.2</td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>foxtrot</td><td>data</td><td>critical</td><td><div class="dz-cluster" data-dz-gap="sm">380<span class="dz-badge dz-badge-sm" data-dz-tone="warning" aria-label="Outlier: high">⚠ high</span></div></td><td>7.2</td><td>50</td></tr></tbody></table></div></div></div>
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
<div data-dz-region data-dz-region-name="cat_pivot" id="region-cat_pivot"><div class="dz-pivot-region"><div class="dz-pivot-scroll"><table class="dz-pivot-grid"><thead><tr><th>Team</th><th>Status</th><th class="is-measure">Team</th><th class="is-measure">Status</th><th class="is-measure">Count</th></tr></thead><tbody><tr><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Platform">Platform</span></td><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Healthy">Healthy</span></td><td class="is-measure">platform</td><td class="is-measure">healthy</td><td class="is-measure">8</td></tr><tr><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Platform">Platform</span></td><td><span class="dz-badge dz-badge-sm " data-dz-tone="destructive" role="status" aria-label="Status: Critical"><span class="dz-badge-icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" /> <path d="m15 9-6 6" /> <path d="m9 9 6 6" /></svg></span>Critical</span></td><td class="is-measure">platform</td><td class="is-measure">critical</td><td class="is-measure">1</td></tr><tr><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Payments">Payments</span></td><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Healthy">Healthy</span></td><td class="is-measure">payments</td><td class="is-measure">healthy</td><td class="is-measure">6</td></tr><tr><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Payments">Payments</span></td><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Degraded">Degraded</span></td><td class="is-measure">payments</td><td class="is-measure">degraded</td><td class="is-measure">2</td></tr></tbody></table></div><p class="dz-pivot-summary">4 rows</p></div></div>
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
<div data-dz-region data-dz-region-name="cat_kanban" id="region-cat_kanban"><div class="dz-kanban-board" role="region" aria-label="Kanban board" tabindex="0"><div class="dz-kanban-column"><div class="dz-kanban-column-head"><span class="dz-badge  " data-dz-tone="neutral" role="status" aria-label="Status: Healthy">Healthy</span><span class="dz-kanban-column-count">4</span></div><div class="dz-kanban-stack"><div class="dz-kanban-card" data-dz-kanban-card><div class="dz-kanban-card-body"><h4 class="dz-kanban-card-title">alpha</h4><p class="dz-kanban-card-field"><span>Team:</span> platform</p><p class="dz-kanban-card-field"><span>Latency Ms:</span> 42</p><p class="dz-kanban-card-field"><span>Error Rate:</span> 0.1</p><p class="dz-kanban-card-field"><span>Target Ms:</span> 50</p></div></div><div class="dz-kanban-card" data-dz-kanban-card><div class="dz-kanban-card-body"><h4 class="dz-kanban-card-title">bravo</h4><p class="dz-kanban-card-field"><span>Team:</span> platform</p><p class="dz-kanban-card-field"><span>Latency Ms:</span> 38</p><p class="dz-kanban-card-field"><span>Error Rate:</span> 0.2</p><p class="dz-kanban-card-field"><span>Target Ms:</span> 50</p></div></div><div class="dz-kanban-card" data-dz-kanban-card><div class="dz-kanban-card-body"><h4 class="dz-kanban-card-title">delta</h4><p class="dz-kanban-card-field"><span>Team:</span> payments</p><p class="dz-kanban-card-field"><span>Latency Ms:</span> 40</p><p class="dz-kanban-card-field"><span>Error Rate:</span> 0.3</p><p class="dz-kanban-card-field"><span>Target Ms:</span> 50</p></div></div><div class="dz-kanban-card" data-dz-kanban-card><div class="dz-kanban-card-body"><h4 class="dz-kanban-card-title">echo</h4><p class="dz-kanban-card-field"><span>Team:</span> growth</p><p class="dz-kanban-card-field"><span>Latency Ms:</span> 46</p><p class="dz-kanban-card-field"><span>Error Rate:</span> 0.2</p><p class="dz-kanban-card-field"><span>Target Ms:</span> 50</p></div></div></div></div><div class="dz-kanban-column"><div class="dz-kanban-column-head"><span class="dz-badge  " data-dz-tone="neutral" role="status" aria-label="Status: Degraded">Degraded</span><span class="dz-kanban-column-count">1</span></div><div class="dz-kanban-stack"><div class="dz-kanban-card" data-dz-kanban-card><div class="dz-kanban-card-body"><h4 class="dz-kanban-card-title">charlie</h4><p class="dz-kanban-card-field"><span>Team:</span> payments</p><p class="dz-kanban-card-field"><span>Latency Ms:</span> 44</p><p class="dz-kanban-card-field"><span>Error Rate:</span> 1.4</p><p class="dz-kanban-card-field"><span>Target Ms:</span> 50</p></div></div></div></div><div class="dz-kanban-column"><div class="dz-kanban-column-head"><span class="dz-badge  " data-dz-tone="destructive" role="status" aria-label="Status: Critical"><span class="dz-badge-icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" /> <path d="m15 9-6 6" /> <path d="m9 9 6 6" /></svg></span>Critical</span><span class="dz-kanban-column-count">1</span></div><div class="dz-kanban-stack"><div class="dz-kanban-card" data-dz-kanban-card><div class="dz-kanban-card-body"><h4 class="dz-kanban-card-title">foxtrot</h4><p class="dz-kanban-card-field"><span>Team:</span> data</p><p class="dz-kanban-card-field"><span>Latency Ms:</span> 380</p><p class="dz-kanban-card-field"><span>Error Rate:</span> 7.2</p><p class="dz-kanban-card-field"><span>Target Ms:</span> 50</p></div></div></div></div></div></div>
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
<div data-dz-region data-dz-region-name="cat_insight" id="region-cat_insight"><div class="dz-stack" data-dz-gap="sm"><span class="dz-text dz-text--tone-default">Alert volume is concentrated in Platform, with ML unusually quiet — worth checking whether ML's pipeline is reporting.</span><span class="dz-text dz-text--tone-muted">Based on: platform 20 · payments 19 · growth 18 · data 17 · infra 16 · ml 1</span><span class="dz-badge dz-badge-sm" data-dz-tone="warning" role="status" aria-label="Confidence: medium">confidence: medium</span><span class="dz-text dz-text--tone-muted">across all team · as of 2026-06-25 14:00 UTC</span></div></div>
</div>

```dsl
cat_insight:
  source: Box
  display: insight_summary
  group_by: team
  aggregate:
    count: count(Box)
```

## List

Fixed-band RAG decorator — `error_rate` cells are coloured green/amber/red against author thresholds (WCAG-safe tone + icon + label). The deterministic sibling of the outlier decorator.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_rag" id="region-cat_rag"><div class="dz-list-region"><div class="dz-list-actions"><div class="dz-list-action-group"><button type="button" data-dz-csv-endpoint="/api/workspaces/ux_catalogue/regions/cat_rag" data-dz-csv-filename="cat_rag.csv" onclick="window.dz.downloadCsv(this.dataset.dzCsvEndpoint, this.dataset.dzCsvFilename)" class="dz-list-csv-button" title="Export CSV" aria-label="Export CSV"><svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg></button></div></div><div class="dz-list-scroll"><table class="dz-list-table"><thead><tr><th>Name</th><th>Team</th><th>Status</th><th>Latency Ms</th><th>Error Rate</th><th>Target Ms</th></tr></thead><tbody><tr data-dz-list-kind="region" class="dz-list-row "><td>alpha</td><td>platform</td><td>healthy</td><td>42</td><td><div class="dz-cluster" data-dz-gap="sm">0.1<span class="dz-badge dz-badge-sm" data-dz-tone="positive" aria-label="Status: good">● good</span></div></td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>bravo</td><td>platform</td><td>healthy</td><td>38</td><td><div class="dz-cluster" data-dz-gap="sm">0.2<span class="dz-badge dz-badge-sm" data-dz-tone="positive" aria-label="Status: good">● good</span></div></td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>charlie</td><td>payments</td><td>degraded</td><td>44</td><td><div class="dz-cluster" data-dz-gap="sm">1.4<span class="dz-badge dz-badge-sm" data-dz-tone="warning" aria-label="Status: watch">● watch</span></div></td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>delta</td><td>payments</td><td>healthy</td><td>40</td><td><div class="dz-cluster" data-dz-gap="sm">0.3<span class="dz-badge dz-badge-sm" data-dz-tone="positive" aria-label="Status: good">● good</span></div></td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>echo</td><td>growth</td><td>healthy</td><td>46</td><td><div class="dz-cluster" data-dz-gap="sm">0.2<span class="dz-badge dz-badge-sm" data-dz-tone="positive" aria-label="Status: good">● good</span></div></td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>foxtrot</td><td>data</td><td>critical</td><td>380</td><td><div class="dz-cluster" data-dz-gap="sm">7.2<span class="dz-badge dz-badge-sm" data-dz-tone="destructive" aria-label="Status: critical">● critical</span></div></td><td>50</td></tr></tbody></table></div></div></div>
</div>

```dsl
cat_rag:
  source: Box
  display: list
  rag_on: error_rate
  tone_bands:
    - at: 5
      tone: destructive
    - at: 1
      tone: warning
    - at: 0
      tone: positive
```

## Histogram

Continuous-axis distribution — `latency_ms` binned (Sturges' rule).

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_histogram" id="region-cat_histogram"><div class="dz-histogram-region"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 140" class="dz-histogram-svg" role="img" aria-label="Cat Histogram histogram — 4 bins, 6 samples, peak 5"><line x1="8" y1="112" x2="392" y2="112" stroke="var(--colour-border)" stroke-width="1" /><rect x="8.0" y="8.0" width="95.0" height="104.0" fill="var(--colour-brand)" fill-opacity="0.6"><title>38–123.5: 5</title></rect><rect x="104.0" y="112.0" width="95.0" height="0.0" fill="var(--colour-brand)" fill-opacity="0.6"><title>123.5–209: 0</title></rect><rect x="200.0" y="112.0" width="95.0" height="0.0" fill="var(--colour-brand)" fill-opacity="0.6"><title>209–294.5: 0</title></rect><rect x="296.0" y="91.2" width="95.0" height="20.8" fill="var(--colour-brand)" fill-opacity="0.6"><title>294.5–380: 1</title></rect><text x="56.0" y="132" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">38</text><text x="152.0" y="132" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">123.5</text><text x="248.0" y="132" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">209</text><text x="344.0" y="132" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">294.5</text></svg><p class="dz-histogram-summary">4 bins · 6 samples · peak 5</p></div></div>
</div>

```dsl
cat_histogram:
  source: Box
  display: histogram
  value: latency_ms
  bins: auto
  empty: "No boxes"
```

## Box Plot

Quartile spread per team — Q1/median/Q3 + Tukey whiskers over `latency_ms`.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_box_plot" id="region-cat_box_plot"><div class="dz-box-plot-region"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 288 200" class="dz-box-plot-svg" role="img" aria-label="Cat Box Plot box plot — 4 groups, range 38.0–380.0"><line x1="32" y1="168" x2="280" y2="168" stroke="var(--colour-border)" stroke-width="1" /><line x1="32" y1="8" x2="32" y2="168" stroke="var(--colour-border)" stroke-width="1" /><text x="28" y="172" text-anchor="end" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">38.0</text><text x="28" y="12" text-anchor="end" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">380.0</text><line x1="63.0" y1="168.0" x2="63.0" y2="166.13" stroke="var(--colour-text-muted)" stroke-width="1" /><line x1="54.0" y1="168.0" x2="72.0" y2="168.0" stroke="var(--colour-text-muted)" stroke-width="1" /><line x1="54.0" y1="166.13" x2="72.0" y2="166.13" stroke="var(--colour-text-muted)" stroke-width="1" /><rect x="45.0" y="166.6" width="36" height="0.94" fill="var(--colour-brand)" fill-opacity="0.18" stroke="var(--colour-brand)" stroke-width="1"><title>platform: Q1 39.0, median 40.0, Q3 41.0, n=2</title></rect><line x1="45.0" y1="167.06" x2="81.0" y2="167.06" stroke="var(--colour-brand)" stroke-width="1.5" /><text x="63.0" y="192" text-anchor="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">platform</text><line x1="125.0" y1="167.06" x2="125.0" y2="165.19" stroke="var(--colour-text-muted)" stroke-width="1" /><line x1="116.0" y1="167.06" x2="134.0" y2="167.06" stroke="var(--colour-text-muted)" stroke-width="1" /><line x1="116.0" y1="165.19" x2="134.0" y2="165.19" stroke="var(--colour-text-muted)" stroke-width="1" /><rect x="107.0" y="165.66" width="36" height="0.94" fill="var(--colour-brand)" fill-opacity="0.18" stroke="var(--colour-brand)" stroke-width="1"><title>payments: Q1 41.0, median 42.0, Q3 43.0, n=2</title></rect><line x1="107.0" y1="166.13" x2="143.0" y2="166.13" stroke="var(--colour-brand)" stroke-width="1.5" /><text x="125.0" y="192" text-anchor="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">payments</text><line x1="187.0" y1="164.26" x2="187.0" y2="164.26" stroke="var(--colour-text-muted)" stroke-width="1" /><line x1="178.0" y1="164.26" x2="196.0" y2="164.26" stroke="var(--colour-text-muted)" stroke-width="1" /><line x1="178.0" y1="164.26" x2="196.0" y2="164.26" stroke="var(--colour-text-muted)" stroke-width="1" /><rect x="169.0" y="164.26" width="36" height="0.0" fill="var(--colour-brand)" fill-opacity="0.18" stroke="var(--colour-brand)" stroke-width="1"><title>growth: Q1 46.0, median 46.0, Q3 46.0, n=1</title></rect><line x1="169.0" y1="164.26" x2="205.0" y2="164.26" stroke="var(--colour-brand)" stroke-width="1.5" /><text x="187.0" y="192" text-anchor="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">growth</text><line x1="249.0" y1="8.0" x2="249.0" y2="8.0" stroke="var(--colour-text-muted)" stroke-width="1" /><line x1="240.0" y1="8.0" x2="258.0" y2="8.0" stroke="var(--colour-text-muted)" stroke-width="1" /><line x1="240.0" y1="8.0" x2="258.0" y2="8.0" stroke="var(--colour-text-muted)" stroke-width="1" /><rect x="231.0" y="8.0" width="36" height="0.0" fill="var(--colour-brand)" fill-opacity="0.18" stroke="var(--colour-brand)" stroke-width="1"><title>data: Q1 380.0, median 380.0, Q3 380.0, n=1</title></rect><line x1="231.0" y1="8.0" x2="267.0" y2="8.0" stroke="var(--colour-brand)" stroke-width="1.5" /><text x="249.0" y="192" text-anchor="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">data</text></svg><p class="dz-box-plot-summary">4 groups · 6 samples</p></div></div>
</div>

```dsl
cat_box_plot:
  source: Box
  display: box_plot
  group_by: team
  value: latency_ms
  show_outliers: true
  empty: "No boxes"
```

## Funnel Chart

Stage funnel — boxes counted through the status lifecycle.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_funnel" id="region-cat_funnel"><div class="dz-funnel-chart-region"><div class="dz-funnel-stages"><div class="dz-funnel-stage-row"><div class="dz-funnel-stage" data-dz-funnel-step="0" style="width: 100%;"><span class="dz-funnel-stage-label">healthy</span> <span class="dz-funnel-stage-count">(4)</span></div></div><div class="dz-funnel-stage-row"><div class="dz-funnel-stage" data-dz-funnel-step="1" style="width: 25%;"><span class="dz-funnel-stage-label">degraded</span> <span class="dz-funnel-stage-count">(1)</span></div></div><div class="dz-funnel-stage-row"><div class="dz-funnel-stage" data-dz-funnel-step="2" style="width: 25%;"><span class="dz-funnel-stage-label">critical</span> <span class="dz-funnel-stage-count">(1)</span></div></div></div><p class="dz-funnel-summary">6 total</p></div></div>
</div>

```dsl
cat_funnel:
  source: Box
  display: funnel_chart
  group_by: status
  aggregate:
    count: count(Box)
  empty: "No boxes"
```

## Line Chart

Time series — daily box volume. One `date_trunc('day')` GROUP BY.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_line" id="region-cat_line"><div class="dz-line-chart-region"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 120" class="dz-line-chart-svg dz-chart-svg" role="img" aria-label="Cat Line time series — 5 buckets, peak 8"><line x1="8" y1="92" x2="392" y2="92" stroke="var(--colour-border)" stroke-width="1" /><polygon points="8,92 8.0,60.5 104.0,39.5 200.0,50.0 296.0,8.0 392.0,29.0 392,92" fill="var(--colour-brand)" fill-opacity="0.12" stroke="none" /><polyline points="8.0,60.5 104.0,39.5 200.0,50.0 296.0,8.0 392.0,29.0" fill="none" stroke="var(--colour-brand)" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" /><circle cx="8.0" cy="60.5" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>2026-06-21: 3</title></circle><circle cx="104.0" cy="39.5" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>2026-06-22: 5</title></circle><circle cx="200.0" cy="50.0" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>2026-06-23: 4</title></circle><circle cx="296.0" cy="8.0" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>2026-06-24: 8</title></circle><circle cx="392.0" cy="29.0" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>2026-06-25: 6</title></circle><text x="8.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">2026-06-21</text><text x="104.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">2026-06-22</text><text x="200.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">2026-06-23</text><text x="296.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">2026-06-24</text><text x="392.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">2026-06-25</text></svg><p class="dz-chart-summary">5 buckets · peak 8</p></div></div>
</div>

```dsl
cat_line:
  source: Box
  display: line_chart
  group_by: bucket(opened_at, day)
  aggregate:
    count: count(Box)
  empty: "No boxes"
```

## Sparkline

Compact trend tile — the same daily series as a headline + tiny SVG.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_sparkline" id="region-cat_sparkline"><div class="dz-sparkline-region"><div class="dz-sparkline-headline"><span class="dz-sparkline-value">6</span><span class="dz-sparkline-bucket-label">2026-06-25</span></div><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 32" class="dz-sparkline-svg" role="img" aria-label="Sparkline — 5 points, latest 6, peak 8"><polygon points="0,32 0.0,19.5 45.0,12.5 90.0,16.0 135.0,2.0 180.0,9.0 180,32" fill="var(--colour-brand)" fill-opacity="0.15" stroke="none" /><polyline points="0.0,19.5 45.0,12.5 90.0,16.0 135.0,2.0 180.0,9.0" fill="none" stroke="var(--colour-brand)" stroke-width="1.25" stroke-linejoin="round" stroke-linecap="round" /></svg></div></div>
</div>

```dsl
cat_sparkline:
  source: Box
  display: sparkline
  group_by: bucket(opened_at, day)
  aggregate:
    count: count(Box)
  empty: "—"
```

## Radar

Polar profile — one spoke per team, value = box count for that team.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_radar" id="region-cat_radar"><div class="dz-radar-region"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" class="dz-radar-svg dz-chart-svg" role="img" aria-label="Cat Radar radar — 4 spokes, peak 12"><polygon points="160.0,128.0 192.0,160.0 160.0,192.0 128.0,160.0" fill="none" stroke="var(--colour-border)" stroke-width="0.5" stroke-opacity="0.6" /><polygon points="160.0,96.0 224.0,160.0 160.0,224.0 96.0,160.0" fill="none" stroke="var(--colour-border)" stroke-width="0.5" stroke-opacity="0.6" /><polygon points="160.0,64.0 256.0,160.0 160.0,256.0 64.0,160.0" fill="none" stroke="var(--colour-border)" stroke-width="0.5" stroke-opacity="0.6" /><polygon points="160.0,32.0 288.0,160.0 160.0,288.0 32.0,160.00000000000003" fill="none" stroke="var(--colour-border)" stroke-width="0.5" stroke-opacity="0.6" /><line x1="160.0" y1="160.0" x2="160.0" y2="32.0" stroke="var(--colour-border)" stroke-width="0.5" stroke-opacity="0.7" /><line x1="160.0" y1="160.0" x2="288.0" y2="160.0" stroke="var(--colour-border)" stroke-width="0.5" stroke-opacity="0.7" /><line x1="160.0" y1="160.0" x2="160.0" y2="288.0" stroke="var(--colour-border)" stroke-width="0.5" stroke-opacity="0.7" /><line x1="160.0" y1="160.0" x2="32.0" y2="160.00000000000003" stroke="var(--colour-border)" stroke-width="0.5" stroke-opacity="0.7" /><polygon points="160.0,32.0 234.66666666666669,160.0 160.0,202.66666666666666 64.0,160.0" fill="var(--colour-brand)" fill-opacity="0.15" stroke="var(--colour-brand)" stroke-width="1.5" stroke-linejoin="round" /><circle cx="160.0" cy="32.0" r="3" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>platform value: 12</title></circle><circle cx="234.66666666666669" cy="160.0" r="3" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>payments value: 7</title></circle><circle cx="160.0" cy="202.66666666666666" r="3" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>growth value: 4</title></circle><circle cx="64.0" cy="160.0" r="3" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>data value: 9</title></circle><text x="160.0" y="18.0" text-anchor="middle" dominant-baseline="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">platform</text><text x="302.0" y="160.0" text-anchor="middle" dominant-baseline="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">payments</text><text x="160.0" y="302.0" text-anchor="middle" dominant-baseline="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">growth</text><text x="18.0" y="160.00000000000003" text-anchor="middle" dominant-baseline="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">data</text></svg><p class="dz-chart-summary">4 spokes · 1 series · peak 12</p></div></div>
</div>

```dsl
cat_radar:
  source: Box
  display: radar
  group_by: team
  aggregate:
    count: count(Box)
  empty: "No boxes"
```

## Area Chart

Filled area — daily box volume under a single series.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_area" id="region-cat_area"><div class="dz-area-chart-region"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 120" class="dz-line-chart-svg dz-chart-svg" role="img" aria-label="Cat Area time series — 5 buckets, peak 8"><line x1="8" y1="92" x2="392" y2="92" stroke="var(--colour-border)" stroke-width="1" /><polygon points="8,92 8.0,60.5 104.0,39.5 200.0,50.0 296.0,8.0 392.0,29.0 392,92" fill="var(--colour-brand)" fill-opacity="0.12" stroke="none" /><polyline points="8.0,60.5 104.0,39.5 200.0,50.0 296.0,8.0 392.0,29.0" fill="none" stroke="var(--colour-brand)" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" /><circle cx="8.0" cy="60.5" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>2026-06-21: 3</title></circle><circle cx="104.0" cy="39.5" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>2026-06-22: 5</title></circle><circle cx="200.0" cy="50.0" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>2026-06-23: 4</title></circle><circle cx="296.0" cy="8.0" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>2026-06-24: 8</title></circle><circle cx="392.0" cy="29.0" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>2026-06-25: 6</title></circle><text x="8.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">2026-06-21</text><text x="104.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">2026-06-22</text><text x="200.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">2026-06-23</text><text x="296.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">2026-06-24</text><text x="392.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">2026-06-25</text></svg><p class="dz-chart-summary">5 buckets · peak 8</p></div></div>
</div>

```dsl
cat_area:
  source: Box
  display: area_chart
  group_by: bucket(opened_at, day)
  aggregate:
    count: count(Box)
  empty: "No boxes"
```

## Area Chart

Stacked area — weekly box volume split by team. Multi-dim time bucket (#1473): overlaid series, one per team, with a legend.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_area_stacked" id="region-cat_area_stacked"><div class="dz-area-chart-region"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 120" class="dz-line-chart-svg dz-chart-svg" role="img" aria-label="Cat Area Stacked time series — 2 series, 2 buckets, peak 6"><line x1="8" y1="92" x2="392" y2="92" stroke="var(--colour-border)" stroke-width="1" /><polygon points="8,92 8.0,36.0 392.0,8.0 392,92" fill="var(--colour-brand)" fill-opacity="0.12" stroke="none" /><polyline points="8.0,36.0 392.0,8.0" fill="none" stroke="var(--colour-brand)" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" /><circle cx="8.0" cy="36.0" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>platform · 2026-W23: 4</title></circle><circle cx="392.0" cy="8.0" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>platform · 2026-W24: 6</title></circle><polygon points="8,92 8.0,64.0 392.0,50.0 392,92" fill="var(--colour-info)" fill-opacity="0.12" stroke="none" /><polyline points="8.0,64.0 392.0,50.0" fill="none" stroke="var(--colour-info)" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" /><circle cx="8.0" cy="64.0" r="2.5" fill="var(--colour-info)" stroke="var(--colour-surface)" stroke-width="1"><title>payments · 2026-W23: 2</title></circle><circle cx="392.0" cy="50.0" r="2.5" fill="var(--colour-info)" stroke="var(--colour-surface)" stroke-width="1"><title>payments · 2026-W24: 3</title></circle><text x="8.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">2026-W23</text><text x="392.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">2026-W24</text></svg><ul class="dz-chart-legend"><li class="dz-chart-legend-item"><span class="dz-chart-legend-swatch" style="background:var(--colour-brand)"></span><span class="dz-chart-legend-name">platform</span></li><li class="dz-chart-legend-item"><span class="dz-chart-legend-swatch" style="background:var(--colour-info)"></span><span class="dz-chart-legend-name">payments</span></li></ul><p class="dz-chart-summary">2 buckets · 2 series · peak 6</p></div></div>
</div>

```dsl
cat_area_stacked:
  source: Box
  display: area_chart
  group_by: [bucket(opened_at, week), team]
  aggregate:
    count: count(Box)
  empty: "No boxes"
```
