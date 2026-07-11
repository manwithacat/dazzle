# Skeleton (`skeleton`)

Loading placeholder with a lifecycle-driven sheen (TASTE-9) — drop it into a swap target while the request is in flight.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="card card-body hm-measure hm-stack" aria-hidden="true">
  <div class="hm-demo-row">
    <div class="skeleton" data-shape="circle"></div>
    <div class="hm-grow hm-stack">
      <div class="skeleton" data-shape="text"></div>
      <div class="skeleton" data-shape="text"></div>
    </div>
  </div>
  <div class="skeleton" data-shape="block"></div>
</div>
```

## Notes

Purely decorative, so the placeholder region is aria-hidden; announce “loading” on the live region that owns the swap. Shapes: data-dz-shape="text|circle|block". The sheen honours prefers-reduced-motion.
