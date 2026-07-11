# Popover (`popover`)

Disclosure popover (`<details>`) — free-content panel; body can lazy-load via htmx. Not a focus-trapped/positioned popover.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<details class="popover">
  <summary class="button" data-variant="outline">Details</summary>
  <div class="popover__panel">
    <div class="hm-demo-title">Dimensions</div>
    <p class="hm-demo-muted">Filters, previews, quick forms.</p>
  </div>
</details>
```
