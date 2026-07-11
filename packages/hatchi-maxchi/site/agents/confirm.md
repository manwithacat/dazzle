# Confirm dialog (`confirm`)

Designed replacement for window.confirm — every hx-confirm upgrades automatically.

> **Layer:** L1 surface · **Recipe:** `confirm-affordance` — confirm irreversible action
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<button class="button" data-variant="destructive" hx-delete="/mock/noop" hx-confirm="Delete this invoice? This cannot be undone.">Delete invoice</button>
```

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the **response fragment** in the table (usually HTML, not JSON). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

> **Do not reimplement the gallery.** Flash toasts (e.g. confirm’s > “Deleted (demo).”), `/mock/*` paths, and other static-site > scaffolding are **demo-only** (`MOCK_HTMX` in `site/build_site.py`). > They are not Hyperpart surface and not a product API. If you are > stuck making a toast or mock URL work, stop — implement the > exchange row below instead. See AGENTS.md › *Gallery demos are not > the product API*.

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `DELETE /app/invoices/{id}` | the button, after the user approves the designed confirm dialog | the server deletes the resource and returns the replacement markup for the affected region (e.g. the row's removal, or an empty-state). Not a toast — the gallery's 'Deleted (demo).' toast is MOCK_HTMX only | per the button's `hx-target`/`hx-swap` (row removal by default) | — |

### `DELETE /app/invoices/{id}` — example handler

Application code (not the dual-lock module). FastAPI-shaped; do not use `from __future__ import annotations` in route files (ADR-0014).

```python
# This is the DELETE after confirm — not a “confirm API”.
# The dialog is client-only (hx-confirm + dz-confirm.js).
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()


@app.delete("/app/invoices/{invoice_id}", response_class=HTMLResponse)
def delete_invoice(invoice_id: str) -> str:
    # delete_invoice_from_db(invoice_id)
    # Return whatever hx-target/hx-swap expect, e.g.:
    #   - empty string with hx-swap='delete' on the trigger
    #   - an empty-state partial for the list region
    #   - OOB markup to refresh a sibling region
    return ""
```

## How to use it

### Seams

- any element with hx-confirm gets the designed dialog via htmx:confirm
- dialog message text IS the hx-confirm attribute value
- on approval the controller issues the underlying request — no per-button wiring

### Do / Don't

| Do | Don't |
|---|---|
| put hx-confirm on the destructive action element; implement the DELETE (or other) endpoint as the Server exchange | wire a bespoke dialog open/close for every delete button or invent a POST /confirm endpoint for the dialog itself |

### Pitfalls

- hx-confirm is a client affordance — it needs no Exchange of its own (and no FastAPI route for “confirm”)
- do not re-implement confirm with window.confirm (loses the designed dialog)
- gallery toast 'Deleted (demo).' is MOCK_HTMX scaffolding in site/build_site.py — not Hyperpart surface; production returns the DELETE fragment from the Exchange

### Keyboard / AT

- dialog traps focus; Esc / cancel dismisses without issuing the request
- confirm control is keyboard-activatable (Enter/Space)

### Related parts

- `button` — agents/button.md
- `dialog` — agents/dialog.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/confirm.py`

- **Required root:** `[hx-confirm]` (part `confirm`)

| Node | Attr | Constraint |
|---|---|---|
| `[hx-confirm]` | `hx-confirm` | present (any value) |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: confirm — hx-confirm interceptor (client affordance).

Package-internal dual-lock for CI / validate_dom — not application business
code. To use confirm in an HTMX app: put ``hx-confirm="…"`` on the action
element and load the controller (``controllers/dz-confirm.js``). The dialog
itself is not server-rendered; after the user approves, htmx issues the
element's existing ``hx-*`` request (see the part page Server exchange).

In-contract: any element with ``hx-confirm``. Opt-out: ``data-dz-native-confirm``
(source token; gallery demos may strip the ``dz-`` prefix).
"""

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

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/confirm.py`
- `controllers/dz-confirm.js`
