# Sparkline (`sparkline`)

A headline number with its recent shape — the smallest chart: a current value, its bucket label, and an area glyph.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="sparkline-region">
  <div class="sparkline-headline"><span class="sparkline-value">184ms</span><span class="sparkline-bucket-label">this hour</span></div>
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 32" class="sparkline-svg" role="img" aria-label="Sparkline — 12 points, latest 184ms, peak 240ms"><polygon points="0,32 0,20 18,18 36,22 54,14 72,16 90,10 108,12 126,8 144,14 162,6 180,9 180,32" fill="var(--colour-brand)" fill-opacity="0.15" stroke="none"/><polyline points="0,20 18,18 36,22 54,14 72,16 90,10 108,12 126,8 144,14 162,6 180,9" fill="none" stroke="var(--colour-brand)" stroke-width="1.25" stroke-linejoin="round" stroke-linecap="round"/></svg>
</div>
```

## Guidance (prose; HTML from the registry notes field)

The SVG is server-rendered with a numeric summary in <code>aria-label</code> (points / latest / peak) — the glyph is decoration; the numbers are the content. An empty series renders <code>dz-sparkline-empty</code>; a single point renders the headline alone.
