# Combobox (`combobox`)

Searchable enum single-select — a native <select> progressively enhanced into a type-to-filter combobox. JS off: a fully usable select. JS on: a searchable role=combobox overlay; the native select stays as the submitted value.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<label class="field hm-measure" for="hm-cb-field">
  <span class="field__label">Priority</span>
  <select id="hm-cb-field" name="priority" data-combobox class="form-input">
    <option value="">Select a priority…</option>
    <option value="low">Low</option>
    <option value="medium" selected>Medium</option>
    <option value="high">High</option>
    <option value="urgent">Urgent</option>
  </select>
</label>
```

## How to use it

### Seams

- server renders a real <select data-dz-combobox> — progressive enhancement
- native select stays as the submitted value after the overlay mounts

### Do / Don't

| Do | Don't |
|---|---|
| filter options client-side from the server-rendered <option> list | replace the select with a div and invent a new submit contract |

### Pitfalls

- pointerdown on the bare select must enhance first and swallow the native menu
- state is data-dz-open on the root — not a JS open flag a morph would drop

### Keyboard / AT

- input is role=combobox with aria-expanded / aria-activedescendant
- ArrowUp/Down move highlight; Enter selects; Esc closes

### Related parts

- `field` — agents/field.md

## DOM contract

CI stop-ship (`tests/test_contracts.py`). Do not invent attrs or response shapes outside these modules.

### `contracts/combobox.py`

- **Required root:** `[data-dz-combobox]` (part `combobox`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-combobox]` | `name` | present (any value) |

#### Ingestion model `ComboboxOption`

| Field | Type | Required |
|---|---|---|
| `value` | `string` | yes |
| `label` | `string` | yes |

#### Exemplar `render()`

```python
def render(field: ComboboxField) -> str:
    opts = []
    for o in field.options:
        sel = " selected" if o.value == field.selected and o.value != "" else ""
        # bare-string producer shape lands as value==label after validator
        opts.append(
            f'<option value="{html.escape(o.value, quote=True)}"{sel}>'
            f"{html.escape(o.label)}</option>"
        )
    return (
        f'<label class="dz-field" for="{html.escape(field.field_id, quote=True)}">'
        f'<span class="dz-field__label">{html.escape(field.label)}</span>'
        f'<select id="{html.escape(field.field_id, quote=True)}" '
        f'name="{html.escape(field.name, quote=True)}" data-dz-combobox '
        f'class="dz-form-input">{"".join(opts)}</select></label>'
    )
```

## Notes

Progressive enhancement: the server renders a real <select data-dz-combobox> with all its options (placeholder first) — usable and submittable with no JS, native required intact. On first interaction dz-combobox.js builds a sibling overlay: a role="combobox" input + a role="listbox" of the options, hiding the native select (kept in the DOM as the submitted value). State is in the DOM — data-dz-open on the root (CSS hides the listbox off it), aria-expanded mirrored on the input. Typing filters (substring, case-insensitive); Up/Down move aria-activedescendant; Enter/click selects (writes the native select + fires change); Esc closes; focus leaving the widget closes after a 200ms grace.

## Source files

- `controllers/dz-combobox.js`
