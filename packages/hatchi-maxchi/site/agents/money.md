# Money field (`money`)

Major-unit decimal input over a hidden minor-unit carrier — the form posts integer minor units, never floats.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="money hm-measure" data-money data-currency="GBP" data-scale="2">
  <div class="form-money-group"><span class="form-money-prefix" aria-hidden="true">£</span><input type="text" inputmode="decimal" id="hm-money-input" value="15.00" class="form-input form-input-trailing" placeholder="0.00" aria-label="Amount (GBP)"></div>
  <input type="hidden" name="amount_minor" value="1500">
  <input type="hidden" name="amount_currency" value="GBP">
</div>
```

## Guidance (prose; HTML from the registry notes field)

State-in-DOM: the root's <code>data-dz-scale</code> is the conversion factor; <code>dz-money.js</code> keeps the hidden <code>*_minor</code> carrier in sync on input, normalizes the display to <code>toFixed(scale)</code> on blur (empty clears the carrier), and — in selector mode — reads a currency <code>&lt;select&gt;</code>'s <code>data-scale</code>/<code>data-symbol</code> options to retune scale and prefix. The edit-mode display value is SERVER-computed from the minor carrier, so there is no client init pass.

## Controller files

- `controllers/dz-money.js`
