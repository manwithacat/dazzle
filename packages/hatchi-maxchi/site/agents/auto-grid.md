# Auto grid (`auto-grid`)

A responsive card grid with no breakpoints: columns pack to fit, each at least the minimum width, all equal.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="auto-grid" style="--grid-min: 9rem">
  <div class="hm-demo-box">A</div>
  <div class="hm-demo-box">B</div>
  <div class="hm-demo-box">C</div>
  <div class="hm-demo-box">D</div>
  <div class="hm-demo-box">E</div>
</div>
```

## Notes

grid-template-columns: repeat(auto-fit, minmax(min(var(--dz-grid-min, 14rem), 100%), 1fr)) — the inner min() stops overflow when the container is narrower than the minimum (the classic auto-fit footgun). --dz-grid-min is a PUBLIC knob; gap rides data-dz-gap as on stack.
