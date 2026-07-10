# Bar chart (`bar-chart`)

Label / track / value rows — the workhorse categorical chart, server-computed and scope-safe.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="bar-chart-region hm-measure-lg">
  <div class="bar-chart-bars">
    <div class="bar-chart-row">
      <span class="bar-chart-label">API</span>
      <div class="bar-chart-track">
        <div class="bar-chart-fill" style="width: 84%"></div>
      </div>
      <span class="bar-chart-value">126</span>
    </div>
    <div class="bar-chart-row">
      <span class="bar-chart-label">Dashboard</span>
      <div class="bar-chart-track">
        <div class="bar-chart-fill" style="width: 56%"></div>
      </div>
      <span class="bar-chart-value">84</span>
    </div>
    <div class="bar-chart-row">
      <span class="bar-chart-label">Billing</span>
      <div class="bar-chart-track">
        <div class="bar-chart-fill" style="width: 23%"></div>
      </div>
      <span class="bar-chart-value">35</span>
    </div>
  </div>
</div>
```

## Guidance (prose; HTML from the registry notes field)

In Dazzle every bar chart compiles to ONE scope-aware <code>GROUP BY</code> — the bucket list and the counts come from the same query, so they cannot disagree (the #847-class bug this design retired). Fill widths are server-computed percentages of the max bucket.
