# Money field (`money`)

Major-unit decimal input over a hidden minor-unit carrier — the form posts integer minor units, never floats.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="money hm-measure" data-money data-currency="GBP" data-scale="2">
  <div class="form-money-group"><span class="form-money-prefix" aria-hidden="true">£</span><input type="text" inputmode="decimal" id="hm-money-input" value="15.00" class="form-input form-input-trailing" placeholder="0.00" aria-label="Amount (GBP)"></div>
  <input type="hidden" name="amount_minor" value="1500">
  <input type="hidden" name="amount_currency" value="GBP">
</div>
```

## How to use it

### Seams

- root data-dz-scale is the conversion factor; hidden *_minor carrier is the submit value
- selector mode reads currency <select> data-scale / data-symbol options

### Do / Don't

| Do | Don't |
|---|---|
| keep the minor integer in a hidden input the form posts | post the formatted display string as the money value |

### Pitfalls

- display value is SERVER-computed from the minor carrier — no client init pass
- empty blur clears the carrier; never invent a client-side float source of truth

### Keyboard / AT

- display input is a normal text field; AT reads the typed amount
- currency select changes retune scale and prefix without remounting

### Related parts

- `field` — agents/field.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/money.py`

- **Required root:** `[data-dz-money]` (part `money`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-money]` | `data-dz-scale` | present (any value) |
| `[data-dz-money]` | `data-dz-currency` | present (any value) |

#### Ingestion model `MoneyField`

| Field | Type | Required |
|---|---|---|
| `name` | `string` | yes |
| `currency` | `string` | no |
| `scale` | `integer` | no |
| `major_display` | `string` | no |
| `minor_value` | `integer` | no |
| `field_id` | `string` | no |

#### Exemplar `render()`

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

## Notes

State-in-DOM: the root's data-dz-scale is the conversion factor; dz-money.js keeps the hidden *_minor carrier in sync on input, normalizes the display to toFixed(scale) on blur (empty clears the carrier), and — in selector mode — reads a currency <select>'s data-scale/data-symbol options to retune scale and prefix. The edit-mode display value is SERVER-computed from the minor carrier, so there is no client init pass.

## Source files

- `controllers/dz-money.js`
