# Combobox (`combobox`)

Searchable enum single-select — a native <select> progressively enhanced into a type-to-filter combobox. JS off: a fully usable select. JS on: a searchable role=combobox overlay; the native select stays as the submitted value.

## Partial (copy-paste; the live demo renders this exact string)

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

## Contract modules (typed source of truth)

### `contracts/combobox.py`

| Field | Type | Required |
|---|---|---|
| `value` | `string` | yes |
| `label` | `string` | yes |

## Guidance (structured)

### Seams

- server renders a real <select data-dz-combobox> — progressive enhancement
- native select stays as the submitted value after the overlay mounts

### Pitfalls

- pointerdown on the bare select must enhance first and swallow the native menu
- state is data-dz-open on the root — not a JS open flag a morph would drop

### Keyboard / AT

- input is role=combobox with aria-expanded / aria-activedescendant
- ArrowUp/Down move highlight; Enter selects; Esc closes

### Do / Don't

| Do | Don't |
|---|---|
| filter options client-side from the server-rendered <option> list | replace the select with a div and invent a new submit contract |

### Composes with

- `field` (agents/field.md)

## Guidance (prose; HTML from the registry notes field)

Progressive enhancement: the server renders a real <code>&lt;select data-dz-combobox&gt;</code> with all its options (placeholder first) — usable and submittable with no JS, native <code>required</code> intact. On first interaction <code>dz-combobox.js</code> builds a sibling overlay: a <code>role=&quot;combobox&quot;</code> input + a <code>role=&quot;listbox&quot;</code> of the options, hiding the native select (kept in the DOM as the submitted value). State is in the DOM — <code>data-dz-open</code> on the root (CSS hides the listbox off it), <code>aria-expanded</code> mirrored on the input. Typing filters (substring, case-insensitive); Up/Down move <code>aria-activedescendant</code>; Enter/click selects (writes the native select + fires <code>change</code>); Esc closes; focus leaving the widget closes after a 200ms grace.

## Controller files

- `controllers/dz-combobox.js`
