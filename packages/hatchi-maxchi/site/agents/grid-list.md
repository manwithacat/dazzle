# Cell grid (`grid-list`)

A responsive grid of plain record cells — title plus label: value lines, 1 → 2 → 3 columns as the container widens.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="grid-region">
  <div class="grid-list">
    <div class="grid-cell ">
      <h4 class="grid-cell-title">Aurora Substation</h4>
      <p class="grid-cell-field"><span class="grid-cell-field-label">Region:</span> North</p>
      <p class="grid-cell-field"><span class="grid-cell-field-label">Load:</span> 82%</p>
    </div>
    <div class="grid-cell ">
      <h4 class="grid-cell-title">Beacon Substation</h4>
      <p class="grid-cell-field"><span class="grid-cell-field-label">Region:</span> East</p>
      <p class="grid-cell-field"><span class="grid-cell-field-label">Load:</span> 47%</p>
    </div>
    <div class="grid-cell ">
      <h4 class="grid-cell-title">Cinder Substation</h4>
      <p class="grid-cell-field"><span class="grid-cell-field-label">Region:</span> West</p>
      <p class="grid-cell-field"><span class="grid-cell-field-label">Load:</span> 91%</p>
    </div>
  </div>
</div>
```

## Guidance (prose; HTML from the registry notes field)

Cells are deliberately chrome-free — the surrounding card owns borders and title. The column count is a viewport response (1 column, then 2 at 40rem, 3 at 64rem). The <code>is-clickable</code> hover/cursor affordance is styled but currently a LEGACY reserve — the substrate grid emitter does not yet wire cell drill URLs (follow-up on the Dazzle side).
