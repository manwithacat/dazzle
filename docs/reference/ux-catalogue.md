# UX Catalogue

Every component below is rendered from real Dazzle DSL through the real render pipeline — the same code that produces a running app's HTML. Each card shows the live component and the DSL that produced it.

## List

The workhorse table. Here it carries the `outlier_on` decorator — the `latency_ms` cell flags the statistical outlier (⚠ high) vs the displayed rows.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_list" id="region-cat_list"><div class="dz-list-region" data-dz-list-region><div class="dz-list-actions"><div class="dz-list-action-group"><button type="button" data-dz-csv-endpoint="/api/workspaces/ux_catalogue/regions/cat_list" data-dz-csv-filename="cat_list.csv" onclick="window.dz.downloadCsv(this.dataset.dzCsvEndpoint, this.dataset.dzCsvFilename)" class="dz-list-csv-button" title="Export Box CSV" aria-label="Export Box CSV"><svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg></button></div></div><div class="dz-list-scroll"><table class="dz-list-table"><thead><tr><th>Name</th><th>Team</th><th>Status</th><th>Latency Ms</th><th>Error Rate</th><th>Target Ms</th></tr></thead><tbody><tr data-dz-list-kind="region" class="dz-list-row "><td>alpha</td><td>platform</td><td>healthy</td><td>42</td><td>0.1</td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>bravo</td><td>platform</td><td>healthy</td><td>38</td><td>0.2</td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>charlie</td><td>payments</td><td>degraded</td><td>44</td><td>1.4</td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>delta</td><td>payments</td><td>healthy</td><td>40</td><td>0.3</td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>echo</td><td>growth</td><td>healthy</td><td>46</td><td>0.2</td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>foxtrot</td><td>data</td><td>critical</td><td><div class="dz-cluster" data-dz-gap="sm">380<span class="dz-badge dz-badge-sm" data-dz-tone="warning" aria-label="Outlier: high">⚠ high</span></div></td><td>7.2</td><td>50</td></tr></tbody></table></div></div></div>
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
<div data-dz-region data-dz-region-name="cat_metrics" id="region-cat_metrics"><div class="dz-metrics-grid" data-dz-tile-count="3"><div class="dz-metric-tile" data-dz-metric-key="total"><div class="dz-metric-label" title="Total">Total</div><div class="dz-metric-value">42</div></div><div class="dz-metric-tile" data-dz-metric-key="critical"><div class="dz-metric-label" title="Critical">Critical</div><div class="dz-metric-value">7</div></div><div class="dz-metric-tile" data-dz-metric-key="avg_latency"><div class="dz-metric-label" title="Avg latency">Avg latency</div><div class="dz-metric-value">41</div></div></div></div>
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
<div data-dz-region data-dz-region-name="cat_bar_chart" id="region-cat_bar_chart"><div class="dz-bar-chart-region" data-dz-bar-chart><div class="dz-bar-chart-bars"><div class="dz-bar-chart-row"><span class="dz-bar-chart-label"><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Platform">Platform</span></span><div class="dz-bar-chart-track"><div class="dz-bar-chart-fill" style="width: 100%"></div></div><span class="dz-bar-chart-value">8</span></div><div class="dz-bar-chart-row"><span class="dz-bar-chart-label"><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Payments">Payments</span></span><div class="dz-bar-chart-track"><div class="dz-bar-chart-fill" style="width: 100%"></div></div><span class="dz-bar-chart-value">8</span></div><div class="dz-bar-chart-row"><span class="dz-bar-chart-label"><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Growth">Growth</span></span><div class="dz-bar-chart-track"><div class="dz-bar-chart-fill" style="width: 100%"></div></div><span class="dz-bar-chart-value">8</span></div><div class="dz-bar-chart-row"><span class="dz-bar-chart-label"><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Data">Data</span></span><div class="dz-bar-chart-track"><div class="dz-bar-chart-fill" style="width: 100%"></div></div><span class="dz-bar-chart-value">8</span></div></div></div></div>
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
<div data-dz-region data-dz-region-name="cat_comparison" id="region-cat_comparison"><div class="dz-bar-track-region" data-dz-bar-track><div class="dz-bar-track-rows"><div class="dz-bar-track-row"><span class="dz-bar-track-label" title="1. platform">1. platform</span><div class="dz-bar-track" role="progressbar" aria-valuemin="0" aria-valuemax="12" aria-valuenow="12" aria-label="1. platform: 12"><span class="dz-bar-track-fill" style="width: 100%;" title="1. platform: 12"></span></div><span class="dz-bar-track-value">12</span></div><div class="dz-bar-track-row"><span class="dz-bar-track-label" title="2. payments">2. payments</span><div class="dz-bar-track" role="progressbar" aria-valuemin="0" aria-valuemax="12" aria-valuenow="11" aria-label="2. payments: 11"><span class="dz-bar-track-fill" style="width: 91.67%;" title="2. payments: 11"></span></div><span class="dz-bar-track-value">11</span></div><div class="dz-bar-track-row"><span class="dz-bar-track-label" title="3. growth">3. growth</span><div class="dz-bar-track" role="progressbar" aria-valuemin="0" aria-valuemax="12" aria-valuenow="10" aria-label="3. growth: 10"><span class="dz-bar-track-fill" style="width: 83.33%;" title="3. growth: 10"></span></div><span class="dz-bar-track-value">10</span></div><div class="dz-bar-track-row"><span class="dz-bar-track-label" title="4. data">4. data</span><div class="dz-bar-track" role="progressbar" aria-valuemin="0" aria-valuemax="12" aria-valuenow="9" aria-label="4. data: 9"><span class="dz-bar-track-fill" style="width: 75%;" title="4. data: 9"></span></div><span class="dz-bar-track-value">9</span></div><div class="dz-bar-track-row"><span class="dz-bar-track-label" title="5. infra">5. infra</span><div class="dz-bar-track" role="progressbar" aria-valuemin="0" aria-valuemax="12" aria-valuenow="9" aria-label="5. infra: 9"><span class="dz-bar-track-fill" style="width: 75%;" title="5. infra: 9"></span></div><span class="dz-bar-track-value">9</span></div><div class="dz-bar-track-row"><span class="dz-bar-track-label" title="6. ml">6. ml</span><div class="dz-bar-track" role="progressbar" aria-valuemin="0" aria-valuemax="12" aria-valuenow="1" aria-label="6. ml: 1"><span class="dz-bar-track-fill" style="width: 8.33%;" title="6. ml: 1"></span></div><span class="dz-bar-track-value">1</span></div></div><p class="dz-bar-track-summary"><span class="dz-bar-track-summary-gutter" aria-hidden="true"></span><span class="dz-bar-track-summary-meta">6 rows</span><span class="dz-bar-track-summary-scale">0–12</span></p></div></div>
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

## Pivot Table

Cross-tab — counts across two dimensions (team × status).

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_pivot" id="region-cat_pivot"><div class="dz-pivot-region" data-dz-pivot><div class="dz-pivot-scroll"><table class="dz-pivot-grid"><thead><tr><th>Team</th><th>Status</th><th class="is-measure">Count</th></tr></thead><tbody><tr><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Platform">Platform</span></td><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Healthy">Healthy</span></td><td class="is-measure">8</td></tr><tr><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Platform">Platform</span></td><td><span class="dz-badge dz-badge-sm " data-dz-tone="destructive" role="status" aria-label="Status: Critical"><span class="dz-badge-icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" /> <path d="m15 9-6 6" /> <path d="m9 9 6 6" /></svg></span>Critical</span></td><td class="is-measure">1</td></tr><tr><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Payments">Payments</span></td><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Healthy">Healthy</span></td><td class="is-measure">6</td></tr><tr><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Payments">Payments</span></td><td><span class="dz-badge dz-badge-sm " data-dz-tone="neutral" role="status" aria-label="Status: Degraded">Degraded</span></td><td class="is-measure">2</td></tr></tbody></table></div><p class="dz-pivot-summary">4 rows</p></div></div>
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

## Kanban

Board view — boxes grouped into status columns.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_kanban" id="region-cat_kanban"><div class="dz-kanban-board" role="region" aria-label="Kanban board" tabindex="0" data-dz-kanban-board data-dz-kanban-rearrange="status" data-dz-kanban-status-field="status" data-dz-kanban-api="/boxes" data-dz-kanban-src="/api/workspaces/ux_catalogue/regions/cat_kanban" data-dz-kanban-rank-field="rank"><div class="dz-kanban-announce" data-dz-kanban-announce aria-live="polite" aria-atomic="true"></div><div class="dz-kanban-column"><div class="dz-kanban-column-head"><span class="dz-badge  " data-dz-tone="neutral" role="status" aria-label="Status: Healthy">Healthy</span><span class="dz-kanban-column-count">4</span></div><div class="dz-kanban-stack" data-dz-kanban-stack data-dz-to-state="healthy"><div class="dz-kanban-card" data-dz-kanban-card data-dz-from-state="healthy" data-dz-rank="1000.0"><div class="dz-kanban-card-body"><h4 class="dz-kanban-card-title">alpha</h4><p class="dz-kanban-card-field"><span>Team:</span> platform</p><p class="dz-kanban-card-field"><span>Latency Ms:</span> 42</p><p class="dz-kanban-card-field"><span>Error Rate:</span> 0.1</p><p class="dz-kanban-card-field"><span>Target Ms:</span> 50</p></div></div><div class="dz-kanban-card" data-dz-kanban-card data-dz-from-state="healthy" data-dz-rank="2000.0"><div class="dz-kanban-card-body"><h4 class="dz-kanban-card-title">bravo</h4><p class="dz-kanban-card-field"><span>Team:</span> platform</p><p class="dz-kanban-card-field"><span>Latency Ms:</span> 38</p><p class="dz-kanban-card-field"><span>Error Rate:</span> 0.2</p><p class="dz-kanban-card-field"><span>Target Ms:</span> 50</p></div></div><div class="dz-kanban-card" data-dz-kanban-card data-dz-from-state="healthy" data-dz-rank="3000.0"><div class="dz-kanban-card-body"><h4 class="dz-kanban-card-title">delta</h4><p class="dz-kanban-card-field"><span>Team:</span> payments</p><p class="dz-kanban-card-field"><span>Latency Ms:</span> 40</p><p class="dz-kanban-card-field"><span>Error Rate:</span> 0.3</p><p class="dz-kanban-card-field"><span>Target Ms:</span> 50</p></div></div><div class="dz-kanban-card" data-dz-kanban-card data-dz-from-state="healthy" data-dz-rank="4000.0"><div class="dz-kanban-card-body"><h4 class="dz-kanban-card-title">echo</h4><p class="dz-kanban-card-field"><span>Team:</span> growth</p><p class="dz-kanban-card-field"><span>Latency Ms:</span> 46</p><p class="dz-kanban-card-field"><span>Error Rate:</span> 0.2</p><p class="dz-kanban-card-field"><span>Target Ms:</span> 50</p></div></div></div></div><div class="dz-kanban-column"><div class="dz-kanban-column-head"><span class="dz-badge  " data-dz-tone="neutral" role="status" aria-label="Status: Degraded">Degraded</span><span class="dz-kanban-column-count">1</span></div><div class="dz-kanban-stack" data-dz-kanban-stack data-dz-to-state="degraded"><div class="dz-kanban-card" data-dz-kanban-card data-dz-from-state="degraded" data-dz-rank="1000.0"><div class="dz-kanban-card-body"><h4 class="dz-kanban-card-title">charlie</h4><p class="dz-kanban-card-field"><span>Team:</span> payments</p><p class="dz-kanban-card-field"><span>Latency Ms:</span> 44</p><p class="dz-kanban-card-field"><span>Error Rate:</span> 1.4</p><p class="dz-kanban-card-field"><span>Target Ms:</span> 50</p></div></div></div></div><div class="dz-kanban-column"><div class="dz-kanban-column-head"><span class="dz-badge  " data-dz-tone="destructive" role="status" aria-label="Status: Critical"><span class="dz-badge-icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" /> <path d="m15 9-6 6" /> <path d="m9 9 6 6" /></svg></span>Critical</span><span class="dz-kanban-column-count">1</span></div><div class="dz-kanban-stack" data-dz-kanban-stack data-dz-to-state="critical"><div class="dz-kanban-card" data-dz-kanban-card data-dz-from-state="critical" data-dz-rank="1000.0"><div class="dz-kanban-card-body"><h4 class="dz-kanban-card-title">foxtrot</h4><p class="dz-kanban-card-field"><span>Team:</span> data</p><p class="dz-kanban-card-field"><span>Latency Ms:</span> 380</p><p class="dz-kanban-card-field"><span>Error Rate:</span> 7.2</p><p class="dz-kanban-card-field"><span>Target Ms:</span> 50</p></div></div></div></div></div></div>
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
<div data-dz-region data-dz-region-name="cat_insight" id="region-cat_insight"><div class="dz-stack" data-dz-gap="sm"><span class="dz-text dz-text--tone-default">Alert volume is concentrated in Platform, with ML unusually quiet — worth checking whether ML's pipeline is reporting.</span><span class="dz-text dz-text--tone-muted">Based on: platform 20 · payments 19 · growth 18 · data 17 · infra 16 · ml 1</span><span class="dz-badge dz-badge-sm" data-dz-tone="warning" role="status" aria-label="Confidence: medium">confidence: medium</span><span class="dz-text dz-text--tone-muted">across all teams · as of 2026-06-25 14:00 UTC</span></div></div>
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
<div data-dz-region data-dz-region-name="cat_rag" id="region-cat_rag"><div class="dz-list-region" data-dz-list-region><div class="dz-list-actions"><div class="dz-list-action-group"><button type="button" data-dz-csv-endpoint="/api/workspaces/ux_catalogue/regions/cat_rag" data-dz-csv-filename="cat_rag.csv" onclick="window.dz.downloadCsv(this.dataset.dzCsvEndpoint, this.dataset.dzCsvFilename)" class="dz-list-csv-button" title="Export Box CSV" aria-label="Export Box CSV"><svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg></button></div></div><div class="dz-list-scroll"><table class="dz-list-table"><thead><tr><th>Name</th><th>Team</th><th>Status</th><th>Latency Ms</th><th>Error Rate</th><th>Target Ms</th></tr></thead><tbody><tr data-dz-list-kind="region" class="dz-list-row "><td>alpha</td><td>platform</td><td>healthy</td><td>42</td><td><div class="dz-cluster" data-dz-gap="sm">0.1<span class="dz-badge dz-badge-sm" data-dz-tone="positive" aria-label="Status: good">● good</span></div></td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>bravo</td><td>platform</td><td>healthy</td><td>38</td><td><div class="dz-cluster" data-dz-gap="sm">0.2<span class="dz-badge dz-badge-sm" data-dz-tone="positive" aria-label="Status: good">● good</span></div></td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>charlie</td><td>payments</td><td>degraded</td><td>44</td><td><div class="dz-cluster" data-dz-gap="sm">1.4<span class="dz-badge dz-badge-sm" data-dz-tone="warning" aria-label="Status: watch">● watch</span></div></td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>delta</td><td>payments</td><td>healthy</td><td>40</td><td><div class="dz-cluster" data-dz-gap="sm">0.3<span class="dz-badge dz-badge-sm" data-dz-tone="positive" aria-label="Status: good">● good</span></div></td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>echo</td><td>growth</td><td>healthy</td><td>46</td><td><div class="dz-cluster" data-dz-gap="sm">0.2<span class="dz-badge dz-badge-sm" data-dz-tone="positive" aria-label="Status: good">● good</span></div></td><td>50</td></tr><tr data-dz-list-kind="region" class="dz-list-row "><td>foxtrot</td><td>data</td><td>critical</td><td>380</td><td><div class="dz-cluster" data-dz-gap="sm">7.2<span class="dz-badge dz-badge-sm" data-dz-tone="destructive" aria-label="Status: critical">● critical</span></div></td><td>50</td></tr></tbody></table></div></div></div>
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

## Line Chart

Time series — daily box volume. One `date_trunc('day')` GROUP BY.

<div class="dz-catalogue-preview" markdown="0">
<div data-dz-region data-dz-region-name="cat_line" id="region-cat_line"><div class="dz-line-chart-region" data-dz-time-series><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 120" class="dz-line-chart-svg dz-chart-svg" role="img" aria-label="Cat Line time series — 5 buckets, peak 8"><line x1="8" y1="92" x2="392" y2="92" stroke="var(--colour-border)" stroke-width="1"/><polygon points="8,92 8.0,60.5 104.0,39.5 200.0,50.0 296.0,8.0 392.0,29.0 392,92" fill="var(--colour-brand)" fill-opacity="0.12" stroke="none"/><polyline points="8.0,60.5 104.0,39.5 200.0,50.0 296.0,8.0 392.0,29.0" fill="none" stroke="var(--colour-brand)" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/><circle cx="8.0" cy="60.5" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>2026-06-21: 3</title></circle><circle cx="104.0" cy="39.5" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>2026-06-22: 5</title></circle><circle cx="200.0" cy="50.0" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>2026-06-23: 4</title></circle><circle cx="296.0" cy="8.0" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>2026-06-24: 8</title></circle><circle cx="392.0" cy="29.0" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>2026-06-25: 6</title></circle><text x="8.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">2026-06-21</text><text x="104.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">2026-06-22</text><text x="200.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">2026-06-23</text><text x="296.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">2026-06-24</text><text x="392.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, 'SF Mono', Menlo, monospace">2026-06-25</text></svg><p class="dz-chart-summary">5 buckets · peak 8</p></div></div>
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
