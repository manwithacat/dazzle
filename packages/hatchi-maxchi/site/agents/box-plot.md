# Box plot (`box-plot`)

Distribution five-number summaries per bucket — a server-rendered SVG with the counts in the summary line.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="box-plot-region hm-measure-lg">
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 48" role="img" aria-label="Box plot — 3 buckets"><line x1="20" y1="8" x2="20" y2="40" stroke="var(--colour-text-muted)"/><rect x="8" y="16" width="24" height="16" fill="var(--colour-brand)" fill-opacity="0.25" stroke="var(--colour-brand)"/><line x1="8" y1="24" x2="32" y2="24" stroke="var(--colour-brand)" stroke-width="2"/><line x1="90" y1="4" x2="90" y2="44" stroke="var(--colour-text-muted)"/><rect x="78" y="12" width="24" height="22" fill="var(--colour-brand)" fill-opacity="0.25" stroke="var(--colour-brand)"/><line x1="78" y1="20" x2="102" y2="20" stroke="var(--colour-brand)" stroke-width="2"/><line x1="160" y1="10" x2="160" y2="38" stroke="var(--colour-text-muted)"/><rect x="148" y="18" width="24" height="14" fill="var(--colour-brand)" fill-opacity="0.25" stroke="var(--colour-brand)"/><line x1="148" y1="26" x2="172" y2="26" stroke="var(--colour-brand)" stroke-width="2"/></svg>
  <p class="box-plot-summary">3 buckets · whiskers at min/max</p>
</div>
```

## Guidance (prose; HTML from the registry notes field)

Schematic demo — real whisker/quartile geometry is server-computed. The summary line carries the bucket count.
