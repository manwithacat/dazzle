# Auto grid (`auto-grid`)

A responsive card grid with no breakpoints: columns pack to fit, each at least the minimum width, all equal.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="auto-grid" style="--grid-min: 9rem">
  <div class="hm-demo-box">A</div>
  <div class="hm-demo-box">B</div>
  <div class="hm-demo-box">C</div>
  <div class="hm-demo-box">D</div>
  <div class="hm-demo-box">E</div>
</div>
```

## Guidance (prose; HTML from the registry notes field)

<code>grid-template-columns: repeat(auto-fit, minmax(min(var(--dz-grid-min, 14rem), 100%), 1fr))</code> — the inner <code>min()</code> stops overflow when the container is narrower than the minimum (the classic auto-fit footgun). <code>--dz-grid-min</code> is a PUBLIC knob; gap rides <code>data-dz-gap</code> as on stack.
