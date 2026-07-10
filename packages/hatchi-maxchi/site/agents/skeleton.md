# Skeleton (`skeleton`)

Loading placeholder with a lifecycle-driven sheen (TASTE-9) — drop it into a swap target while the request is in flight.

## Partial (copy-paste; the live demo renders this exact string)

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

## Guidance (prose; HTML from the registry notes field)

Purely decorative, so the placeholder region is <code>aria-hidden</code>; announce &ldquo;loading&rdquo; on the live region that owns the swap. Shapes: <code>data-dz-shape=&quot;text|circle|block&quot;</code>. The sheen honours <code>prefers-reduced-motion</code>.
