# Tags (`tags`)

Multi-value chips + free create — a native text input carrying a comma-joined value, progressively enhanced into a chips UI. JS off: a usable comma-separated text field. JS on: type + Enter/comma creates a chip, × removes; the native input stays as the submitted value.

## Partial (copy-paste; the live demo renders this exact string)

```html
<label class="field hm-measure" for="hm-tags-field"><span class="field__label">Labels</span><input id="hm-tags-field" name="labels" type="text" data-tags class="form-input" value="urgent,backend" placeholder="Add a label…"></label>
```

## Guidance (structured)

### Seams

- native input value is a comma-joined tag string — the permanent submit shape
- chips UI rewrites the native input on every add/remove and fires change

### Pitfalls

- JS off: type a, b, c — server splits on comma; do not require the chips UI
- dedupe/trim/skip-empty on add; paste splits on comma and newline

### Keyboard / AT

- chips are role=list of listitem; each × is labelled Remove {tag}
- Enter or comma creates a chip; Backspace on empty entry removes the last

### Do / Don't

| Do | Don't |
|---|---|
| keep the native input as the form value under the chips root | post a JSON array the server has never seen from a plain field |

### Composes with

- `field` (agents/field.md)

## Guidance (prose; HTML from the registry notes field)

Progressive enhancement: the server renders a plain <code>&lt;input type=&quot;text&quot; data-dz-tags&gt;</code> whose value is a COMMA-JOINED tag string — usable and submittable with no JS (type <code>a, b, c</code>; the server splits on comma), native <code>required</code> intact. On first interaction <code>dz-tags.js</code> wraps it in a <code>.dz-tags</code> root — a <code>role=&quot;list&quot;</code> of removable chips + a borderless entry — and hides the native input (kept in the DOM as the submitted value). Every add/remove rewrites the native input to the comma-joined chip list and fires <code>change</code>, so the submit shape never changes. Type + Enter or comma creates a chip (trim/dedup/skip-empty); paste splits on comma/newline; × or Backspace-on-empty removes a chip; add/remove is announced via a visually-hidden <code>aria-live</code> region.

## Controller files

- `controllers/dz-tags.js`
