# Combobox (`combobox`)

Searchable single-select over a list of options — a native <select> progressively enhanced into a type-to-filter combobox. Fixed lists by default; growing catalogues (add a missing value) use the same Hyperpart with data-dz-allow-create — not a separate part.

> **Layer:** L1 surface · **Recipe:** `single-select-form` — single-select (form field)
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-stack hm-measure" data-gap="md">
  <label class="field" for="hm-cb-field">
    <span class="field__label">Priority (fixed list)</span>
    <select id="hm-cb-field" name="priority" data-combobox class="form-input">
      <option value="">Select a priority…</option>
      <option value="low">Low</option>
      <option value="medium" selected>Medium</option>
      <option value="high">High</option>
      <option value="urgent">Urgent</option>
    </select>
  </label>
  <label class="field" for="hm-cb-dept">
    <span class="field__label">Department (growing list — type to add)</span>
    <select id="hm-cb-dept" name="department" data-combobox data-allow-create class="form-input">
      <option value="">Pick or add a department…</option>
      <option value="operations">Operations</option>
      <option value="finance">Finance</option>
      <option value="support">Support</option>
    </select>
  </label>
</div>
```

## Server exchange

No dedicated htmx request of this Hyperpart's own — the controller never issues one. The native <select> value rides the enclosing form (or any hx-* you put on that form). That form handler is the server contract for this part.

Fixed list (default — no data-dz-allow-create): closed set. Accept only values that were in the seed <option> list.

Growing list (data-dz-allow-create): the client may submit a value that was not in the seed options (Add "…" appends a local <option> with value = label string). On form submit the server must accept that unknown string and upsert it into the catalogue, then store the field (FK or label per your model). The new option is page-local until that submit succeeds — do not treat client create as durable storage.

If you put hx-* on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

### Seams

- server renders a real <select data-dz-combobox> — progressive enhancement
- native select stays as the submitted value after the overlay mounts
- FIXED list: omit allow-create — filter + pick only; form POST is closed enum
- GROWING list (mutable catalogue): data-dz-allow-create — type a miss → Add "…" row → appends <option> + commits; form POST must upsert the catalogue
- data-dz-focus-after-select=blur|keep|select (default blur)

### Do / Don't

| Do | Don't |
|---|---|
| use combobox + data-dz-allow-create for single growing-list / add-if-missing | invent a new Hyperpart or bespoke create-dropdown for 'add to catalogue' |
| on growing-list form submit, upsert unknown values into the catalogue | reject every value not in the original seed options (breaks Add "…") |
| filter options client-side from the server-rendered <option> list | replace the select with a div and invent a new submit contract |
| use tags for multi free-form labels; search-select for remote FKs | overload combobox for multi-create or server-search FK flows |

### Pitfalls

- pointerdown on the bare select must enhance first and swallow the native menu
- state is data-dz-open on the root — not a JS open flag a morph would drop
- allow-create is client option-list UX only — the enclosing form handler must accept/upsert unknown values; do not treat the new option as durable alone
- multi free-create chips are tags, not combobox; remote ids are search-select

### Keyboard / AT

- input is role=combobox with aria-expanded / aria-activedescendant
- ArrowUp/Down move highlight; Enter selects or creates; Esc closes
- Add "…" row is role=option (same listbox semantics)

### Related parts

- `field` — agents/field.md
- `tags` — agents/tags.md
- `search-select` — agents/search-select.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

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

Same Hyperpart, two recipes. Progressive enhancement: server renders a real <select data-dz-combobox> (placeholder option first). JS builds a filterable listbox; the native select remains the submit value. Fixed list (priority above): the set is authoritative and closed — filter and pick only (workflow priority, severity tiers, anything you do not let users invent). Growing list / mutable catalogue (department above): set data-dz-allow-create on the <select>. When the typed query has no exact match, an Add "…" row appears; Enter/click appends a new <option> and commits it (value = label string). That is the common "pick from our list, or add one" pattern — departments, cost centres, queues, product lines — not a new Hyperpart. Server still owns persistence: on submit upsert the catalogue row if the value is new; the client only extends the option list for this page. Not this part: multi free-form chips → tags; remote FK typeahead → search-select. Do not invent a fourth picker. After select: data-dz-focus-after-select=blur|keep|select (default blur).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/combobox.py`
- `controllers/dz-combobox.js`
