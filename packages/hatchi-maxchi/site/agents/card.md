# Card (`card`)

Bordered surface with a resting stacked shadow. Content classes (label / value / delta) build KPI tiles; compose several in auto-grid so each card keeps a natural width instead of stretching full-bleed across the preview.

## Partial (copy-paste; the live demo renders this exact string)

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

## Guidance (prose; HTML from the registry notes field)

A card is a <strong>surface</strong>, not a layout. One card in a full-width preview looks clumsy because the box stretches; real use is several cards in <code>auto-grid</code> (or a stack of content cards). Workspace dashboard cards add <code>data-display</code> for CLS height reservation — static KPI tiles omit it and size to content. Classes: <code>dz-card</code> + <code>dz-card-body</code> + <code>dz-card-label</code> / <code>dz-card-value</code> / <code>dz-card-delta</code>.
