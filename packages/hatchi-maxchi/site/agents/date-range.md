# Date range (`date-range`)

Two native date inputs driving one htmx exchange — the from/to filter bar for time-scoped regions.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="date-range-picker date-range-bar">
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
- no typed contracts/ module yet — the partial is the surface of record

## DOM contract

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

Native type="date" inputs — no picker JS. Each input fires the region's hx-get on change and hx-include="closest .date-range-bar" sends BOTH bounds every time, so the server always sees the full range.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
