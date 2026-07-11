# Confirm dialog (`confirm`)

Designed replacement for window.confirm — every hx-confirm upgrades automatically.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<button class="button" data-variant="destructive" hx-delete="/mock/noop" hx-confirm="Delete this invoice? This cannot be undone.">Delete invoice</button>
```

## Server exchange

After the client affordance runs, htmx issues this request. Return the response fragment (not gallery mock toasts).

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `DELETE /app/invoices/{id}` | the button, after the user approves the designed confirm dialog | the server deletes the resource and returns the replacement markup for the affected region (e.g. the row's removal, or an empty-state). Not a toast — the gallery's 'Deleted (demo).' toast is MOCK_HTMX only | per the button's `hx-target`/`hx-swap` (row removal by default) | — |

## How to use it

### Seams

- any element with hx-confirm gets the designed dialog via htmx:confirm
- dialog message text IS the hx-confirm attribute value
- on approval the controller issues the underlying request — no per-button wiring

### Do / Don't

| Do | Don't |
|---|---|
| put hx-confirm on the destructive action element | wire a bespoke dialog open/close for every delete button |

### Pitfalls

- hx-confirm is a client affordance — it needs no Exchange of its own
- do not re-implement confirm with window.confirm (loses the designed dialog)
- gallery toast 'Deleted (demo).' is MOCK_HTMX scaffolding in site/build_site.py — not Hyperpart surface; production returns the DELETE fragment from the Exchange

### Keyboard / AT

- dialog traps focus; Esc / cancel dismisses without issuing the request
- confirm control is keyboard-activatable (Enter/Space)

### Related parts

- `button` — agents/button.md
- `dialog` — agents/dialog.md

## DOM contract

CI stop-ship (`tests/test_contracts.py`). Do not invent attrs or response shapes outside these modules.

### `contracts/confirm.py`

- **Required root:** `[hx-confirm]` (part `confirm`)

| Node | Attr | Constraint |
|---|---|---|
| `[hx-confirm]` | `hx-confirm` | present (any value) |

#### Module source

```python
"""HYPERPART: confirm — hx-confirm interceptor (no server root; trigger attrs).

Any element with hx-confirm is in-contract; opt-out is data-dz-native-confirm.
"""

from __future__ import annotations

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="confirm",
    root="[hx-confirm]",
    nodes=(Node("[hx-confirm]", attrs={"hx-confirm": Present()}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

dz-confirm.js intercepts htmx:confirm (a client affordance — no server round-trip of its own). The dialog message is the hx-confirm attribute value (here: "Delete this invoice? This cannot be undone."). On approval the controller issues the underlying request — no per-button wiring; any element with hx-confirm gets the designed dialog. Gallery-only toast: after confirm, this static site flashes Deleted (demo). — that string is hard-coded in the site's MOCK_HTMX shim (site/build_site.py), not in the Hyperpart, not in contracts/confirm.py, and not returned by a server. Production: your DELETE endpoint returns the Exchange response fragment (row removal / empty-state); there is no toast API.

## Source files

- `controllers/dz-confirm.js`
