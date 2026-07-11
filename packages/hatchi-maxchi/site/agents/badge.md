# Badge (`badge`)

Colour + icon + text — status never relies on colour alone (WCAG 1.4.1).

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="hm-demo-row">
  <span class="badge" data-tone="success"><span class="badge-icon"><svg class="icon" aria-hidden="true"><use href="#i-circle-check"/></svg></span>Approved</span>
  <span class="badge" data-tone="warning"><span class="badge-icon"><svg class="icon" aria-hidden="true"><use href="#i-triangle-alert"/></svg></span>Pending</span>
  <span class="badge" data-tone="destructive"><span class="badge-icon"><svg class="icon" aria-hidden="true"><use href="#i-circle-x"/></svg></span>Rejected</span>
  <span class="badge" data-tone="neutral">Draft</span>
</div>
```
