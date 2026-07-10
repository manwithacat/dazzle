# Center (`center`)

A measure-capped, centred column — reading width for prose and forms.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="center" data-measure="prose">
  <p class="hm-demo-muted">A comfortable reading measure tops out around 65 characters; this block centres itself and caps its width so lines stay scannable on any screen.</p>
</div>
```

## Guidance (prose; HTML from the registry notes field)

<code>margin-inline: auto</code> + <code>max-inline-size</code>. <code>data-dz-measure</code>: <code>prose</code> (65ch), <code>wide</code> (90ch), <code>full</code> (no cap, still a centring context). This is the published form of the measure the gallery's own chrome uses.
