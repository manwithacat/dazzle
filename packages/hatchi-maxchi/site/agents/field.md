# Field (`field`)

The label + control + help + error triad as one accessible unit. Error state derives from aria-invalid; help/error bind via aria-describedby.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="hm-stack hm-measure">
  <div class="form-field">
    <label class="form-label" for="hm-field-email">Billing email<span class="form-required">*</span></label>
    <input class="form-input" id="hm-field-email" type="email" required placeholder="you@company.com" aria-describedby="hm-field-email-hint">
    <p class="form-hint" id="hm-field-email-hint">Receipts and renewal notices go here.</p>
  </div>
  <div class="form-field">
    <label class="form-label" for="hm-field-slug">Workspace slug</label>
    <input class="form-input" id="hm-field-slug" value="Acme Corp" aria-invalid="true" aria-describedby="hm-field-slug-error">
    <p class="form-error" id="hm-field-slug-error">Use lowercase letters, numbers and hyphens only.</p>
  </div>
  <div class="form-field">
    <label class="form-label" for="hm-field-color">Brand colour</label>
    <div class="form-color-group" data-color-group><input class="form-color-input" id="hm-field-color" type="color" value="#3b82f6"><span class="form-color-hex">#3b82f6</span></div>
  </div>
</div>
```

## Contract modules (typed source of truth)

### `contracts/color.py`

## Guidance (prose; HTML from the registry notes field)

Reuses the <code>dz-form-*</code> family (label / hint / input / error). The invalid field needs no modifier class — the red border keys off <code>aria-invalid=&quot;true&quot;</code>, the same attribute assistive tech reads. The colour group uses <code>data-dz-color-group</code> so <code>dz-color.js</code> can mirror the swatch into the hex readout (contract: contracts/color.py).
