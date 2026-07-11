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

## Contract modules (typed source of truth)

Epistemic lock: do not invent attrs or response shapes that diverge from these modules. CI validates exemplars against `DOM_CONTRACT` (`tests/test_contracts.py`).

### `contracts/money.py`

- **DOM root:** `[data-dz-money]` (part `money`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-money]` | `data-dz-scale` | present (any value) |
| `[data-dz-money]` | `data-dz-currency` | present (any value) |

**Ingestion model:** `MoneyField`

| Field | Type | Required |
|---|---|---|
| `name` | `string` | yes |
| `currency` | `string` | no |
| `scale` | `integer` | no |
| `major_display` | `string` | no |
| `minor_value` | `integer` | no |
| `field_id` | `string` | no |

**Exemplar `render()`** (executable — CI)

```python
def render(field: MoneyField) -> str:
    fid = html.escape(field.field_id, quote=True)
    name = html.escape(field.name, quote=True)
    return (
        f'<div class="dz-money" data-dz-money '
        f'data-dz-currency="{html.escape(field.currency, quote=True)}" '
        f'data-dz-scale="{field.scale}">'
        f'<input id="{fid}" name="{name}" inputmode="decimal" '
        f'value="{html.escape(field.major_display, quote=True)}" class="dz-form-input">'
        f'<input type="hidden" name="{name}_minor" value="{field.minor_value}">'
        f"</div>"
    )
```

## Guidance (structured)

### Seams

- root data-dz-scale is the conversion factor; hidden *_minor carrier is the submit value
- selector mode reads currency <select> data-scale / data-symbol options

### Pitfalls

- display value is SERVER-computed from the minor carrier — no client init pass
- empty blur clears the carrier; never invent a client-side float source of truth

### Keyboard / AT

- display input is a normal text field; AT reads the typed amount
- currency select changes retune scale and prefix without remounting

### Do / Don't

| Do | Don't |
|---|---|
| keep the minor integer in a hidden input the form posts | post the formatted display string as the money value |

### Composes with

- `field` (agents/field.md)

## Guidance (prose; HTML from the registry notes field)

State-in-DOM: the root's <code>data-dz-scale</code> is the conversion factor; <code>dz-money.js</code> keeps the hidden <code>*_minor</code> carrier in sync on input, normalizes the display to <code>toFixed(scale)</code> on blur (empty clears the carrier), and — in selector mode — reads a currency <code>&lt;select&gt;</code>'s <code>data-scale</code>/<code>data-symbol</code> options to retune scale and prefix. The edit-mode display value is SERVER-computed from the minor carrier, so there is no client init pass.

## Controller files

- `controllers/dz-money.js`
