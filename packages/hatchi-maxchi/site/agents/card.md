# Card (`card`)

Bordered surface with a resting stacked shadow. Content classes (label / value / delta) build KPI tiles; compose several in auto-grid so each card keeps a natural width instead of stretching full-bleed across the preview.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="auto-grid" style="--grid-min: 11rem">
  <div class="card card-body">
    <div class="card-label">Total Revenue</div>
    <div class="card-value">£1,250.00</div>
    <div class="card-delta"><svg class="icon" aria-hidden="true"><use href="#i-trending-up"/></svg> +12.5% this month</div>
  </div>
  <div class="card card-body">
    <div class="card-label">Open invoices</div>
    <div class="card-value">18</div>
    <div class="card-delta"><svg class="icon" aria-hidden="true"><use href="#i-trending-down"/></svg> −3 vs last week</div>
  </div>
  <div class="card card-body">
    <div class="card-label">Avg. days to pay</div>
    <div class="card-value">24</div>
    <div class="card-delta"><svg class="icon" aria-hidden="true"><use href="#i-trending-up"/></svg> +2 days</div>
  </div>
</div>
```

## Notes

A card is a surface, not a layout. One card in a full-width preview looks clumsy because the box stretches; real use is several cards in auto-grid (or a stack of content cards). Workspace dashboard cards add data-display for CLS height reservation — static KPI tiles omit it and size to content. Classes: dz-card + dz-card-body + dz-card-label / dz-card-value / dz-card-delta.
