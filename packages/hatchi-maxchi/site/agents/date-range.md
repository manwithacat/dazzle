# Date range (`date-range`)

Two native date inputs driving one htmx exchange — the from/to filter bar for time-scoped regions.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="date-range-picker date-range-bar" data-date-range>
  <label class="date-range-label" for="hm-dr-from">From</label>
  <input type="date" id="hm-dr-from" name="date_from" value="2026-06-01" class="date-range-input" hx-get="/mock/search" hx-target="#hm-dr-out" hx-swap="innerHTML" hx-include="closest .date-range-bar">
  <label class="date-range-label" for="hm-dr-to">To</label>
  <input type="date" id="hm-dr-to" name="date_to" value="2026-06-30" class="date-range-input" hx-get="/mock/search" hx-target="#hm-dr-out" hx-swap="innerHTML" hx-include="closest .date-range-bar">
  <div id="hm-dr-out" hidden></div>
</div>
```

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the **response fragment** in the table (usually HTML, not JSON). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

> **Do not reimplement the gallery.** Flash toasts (e.g. confirm’s > “Deleted (demo).”), `/mock/*` paths, and other static-site > scaffolding are **demo-only** (`MOCK_HTMX` in `site/build_site.py`). > They are not Hyperpart surface and not a product API. If you are > stuck making a toast or mock URL work, stop — implement the > exchange row below instead. See AGENTS.md › *Gallery demos are not > the product API*.

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/{region}?date_from=&date_to=` | either date input's change — hx-include sends both bounds | the re-rendered region body for the new range | innerHTML | — |

## Morph / swap

Stem: `stems/morph-safe-hypermedia.md` · decisions 0005–0007. Morph for **stable** surfaces; replacement for **disposable** fragments. Gallery mocks may approximate morph with `innerHTML` — production follows the swap column in **Server exchange**.

### Replace / `innerHTML` (reset OK)

- `GET /app/{region}?date_from=&date_to=` → innerHTML

### Identity rules

- Morph participants need **stable** `id` / domain keys (not loop indexes).
- Carry selection/edit affordances in the **DOM** (checked, `data-*`, ARIA) — not Alpine/`x-data` or a JS array a morph would orphan.
- Mark third-party widgets as explicit islands / morph-skip boundaries.

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- implement Server exchange endpoints; return HTML fragments, not JSON
- satisfy the DOM contract tables (CI stop-ship)

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/date_range.py`

- **Required root:** `[data-dz-date-range]` (part `date-range`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-date-range]` | `data-dz-date-range` | present (any value) |

#### Ingestion model `DateRange`

| Field | Type | Required |
|---|---|---|
| `region_name` | `string` | no |
| `endpoint` | `string` | no |
| `date_from` | `string` | no |
| `date_to` | `string` | no |
| `target` | `string` | no |

#### Exemplar `render()`

```python
def render(d: DateRange) -> str:
    """Model → date-range picker bar."""
    rname = html.escape(d.region_name, quote=True)
    endpoint = html.escape(d.endpoint, quote=True)
    target = html.escape(d.target or f"#region-{d.region_name}", quote=True)
    date_from = html.escape(d.date_from, quote=True)
    date_to = html.escape(d.date_to, quote=True)
    return (
        f'<div class="dz-date-range-picker date-range-bar" data-dz-date-range>'
        f'<label class="dz-date-range-label" for="date-from-{rname}">From</label>'
        f'<input type="date" id="date-from-{rname}" name="date_from" '
        f'value="{date_from}" class="dz-date-range-input" '
        f'hx-get="{endpoint}" hx-target="{target}" hx-swap="innerHTML" '
        f'hx-include="closest .date-range-bar">'
        f'<label class="dz-date-range-label" for="date-to-{rname}">To</label>'
        f'<input type="date" id="date-to-{rname}" name="date_to" '
        f'value="{date_to}" class="dz-date-range-input" '
        f'hx-get="{endpoint}" hx-target="{target}" hx-swap="innerHTML" '
        f'hx-include="closest .date-range-bar">'
        f"</div>"
    )
```

## Notes

Dual-lock root is data-dz-date-range (contracts/date_range.py). Native type="date" inputs — no picker JS. Each input fires the region's hx-get on change and hx-include="closest .date-range-bar" sends BOTH bounds every time, so the server always sees the full range.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/date_range.py`
