# Histogram (`histogram`)

Value-distribution buckets as a server-rendered SVG plus a mono summary line.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="histogram-region hm-measure-lg">
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 48" role="img" aria-label="Histogram — 6 buckets, 120 samples"><rect x="4" y="30" width="24" height="18" fill="var(--colour-brand)" fill-opacity="0.7"/><rect x="32" y="18" width="24" height="30" fill="var(--colour-brand)" fill-opacity="0.7"/><rect x="60" y="6" width="24" height="42" fill="var(--colour-brand)" fill-opacity="0.7"/><rect x="88" y="14" width="24" height="34" fill="var(--colour-brand)" fill-opacity="0.7"/><rect x="116" y="28" width="24" height="20" fill="var(--colour-brand)" fill-opacity="0.7"/><rect x="144" y="38" width="24" height="10" fill="var(--colour-brand)" fill-opacity="0.7"/></svg>
  <p class="histogram-summary">6 buckets · 120 samples</p>
</div>
```

## Guidance (prose; HTML from the registry notes field)

The SVG body is SERVER-computed (this demo is schematic — the real geometry comes from <code>dazzle.render.svg.histogram_svg</code>) with the numeric story in <code>aria-label</code> and the mono summary line.
