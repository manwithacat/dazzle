# Chart legend (`chart-legend`)

The shared tail of every multi-series chart: swatch + series-name chips and a sample/series summary line.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="hm-measure-lg">
  <ul class="chart-legend">
    <li class="chart-legend-item"><span class="chart-legend-swatch" style="background:var(--colour-brand)"></span><span class="chart-legend-name">Revenue</span></li>
    <li class="chart-legend-item"><span class="chart-legend-swatch" style="background:var(--colour-success)"></span><span class="chart-legend-name">Costs</span></li>
  </ul>
  <p class="chart-summary">12 buckets · 2 series · peak £48,900</p>
</div>
```

## Guidance (prose; HTML from the registry notes field)

Every SVG chart (line / area / radar / box-plot) ends with this pair instead of restyling it per chart: a <code>&lt;ul&gt;</code> of swatch + mono series-name items, and a mono summary line of bucket/series counts and the peak. The swatch background is the series colour the chart body uses for its strokes — inline, per series, server-assigned.
