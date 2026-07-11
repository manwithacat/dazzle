# Tags (`tags`)

Multi-value chips + free create — a native text input carrying a comma-joined value, progressively enhanced into a chips UI. JS off: a usable comma-separated text field. JS on: type + Enter/comma creates a chip, × removes; the native input stays as the submitted value.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<label class="field hm-measure" for="hm-tags-field"><span class="field__label">Labels</span><input id="hm-tags-field" name="labels" type="text" data-tags class="form-input" value="urgent,backend" placeholder="Add a label…"></label>
```

## How to use it

### Seams

- native input value is a comma-joined tag string — the permanent submit shape
- chips UI rewrites the native input on every add/remove and fires change

### Do / Don't

| Do | Don't |
|---|---|
| keep the native input as the form value under the chips root | post a JSON array the server has never seen from a plain field |

### Pitfalls

- JS off: type a, b, c — server splits on comma; do not require the chips UI
- dedupe/trim/skip-empty on add; paste splits on comma and newline

### Keyboard / AT

- chips are role=list of listitem; each × is labelled Remove {tag}
- Enter or comma creates a chip; Backspace on empty entry removes the last

### Related parts

- `field` — agents/field.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/tags.py`

- **Required root:** `[data-dz-tags]` (part `tags`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-tags]` | `name` | present (any value) |

#### Ingestion model `TagsField`

| Field | Type | Required |
|---|---|---|
| `name` | `string` | yes |
| `field_id` | `string` | yes |
| `label` | `string` | yes |
| `tags` | `array` | no |
| `placeholder` | `string` | no |

#### Exemplar `render()`

```python
def render(field: TagsField) -> str:
    joined = ",".join(field.tags)
    return (
        f'<label class="dz-field" for="{html.escape(field.field_id, quote=True)}">'
        f'<span class="dz-field__label">{html.escape(field.label)}</span>'
        f'<input id="{html.escape(field.field_id, quote=True)}" '
        f'name="{html.escape(field.name, quote=True)}" type="text" data-dz-tags '
        f'class="dz-form-input" value="{html.escape(joined, quote=True)}" '
        f'placeholder="{html.escape(field.placeholder, quote=True)}"></label>'
    )
```

## Notes

Progressive enhancement: the server renders a plain <input type="text" data-dz-tags> whose value is a COMMA-JOINED tag string — usable and submittable with no JS (type a, b, c; the server splits on comma), native required intact. On first interaction dz-tags.js wraps it in a .dz-tags root — a role="list" of removable chips + a borderless entry — and hides the native input (kept in the DOM as the submitted value). Every add/remove rewrites the native input to the comma-joined chip list and fires change, so the submit shape never changes. Type + Enter or comma creates a chip (trim/dedup/skip-empty); paste splits on comma/newline; × or Backspace-on-empty removes a chip; add/remove is announced via a visually-hidden aria-live region.

## Source files

- `controllers/dz-tags.js`
