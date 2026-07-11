# Separator (`separator`)

A hairline divider on the border token — horizontal (`<hr>`) or vertical (`role=separator`).

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="hm-stack hm-measure">
  <p class="hm-demo-muted">Account details</p>
  <hr class="separator">
  <p class="hm-demo-muted">Billing and invoices</p>
  <div class="hm-demo-row">
    <span class="hm-demo-muted">Draft</span>
    <div class="separator--vertical" role="separator" aria-orientation="vertical"></div>
    <span class="hm-demo-muted">Published</span>
    <div class="separator--vertical" role="separator" aria-orientation="vertical"></div>
    <span class="hm-demo-muted">Archived</span>
  </div>
</div>
```

## Notes

The horizontal rule is a native <hr> (implicitly role=separator); the vertical divider is a zero-width element with an explicit role=separator + aria-orientation="vertical".
