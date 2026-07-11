# Confirm dialog (`confirm`)

Designed replacement for window.confirm — every hx-confirm upgrades automatically.

## Partial (copy-paste; the live demo renders this exact string)

```html
<button class="button" data-variant="destructive" hx-delete="/mock/noop" hx-confirm="Delete this invoice? This cannot be undone.">Delete invoice</button>
```

## Exchanges (the endpoint contract your server must satisfy)

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `DELETE /app/invoices/{id}` | the button, after the user approves the designed confirm dialog | the server deletes the resource and returns the replacement markup for the affected region (e.g. the row's removal, or an empty-state). Not a toast — the gallery's 'Deleted (demo).' toast is MOCK_HTMX only | per the button's `hx-target`/`hx-swap` (row removal by default) | — |

## Contract modules (typed source of truth)

Epistemic lock: do not invent attrs or response shapes that diverge from these modules. CI validates exemplars against `DOM_CONTRACT` (`tests/test_contracts.py`).

### `contracts/confirm.py`

- **DOM root:** `[hx-confirm]` (part `confirm`)

| Node | Attr | Constraint |
|---|---|---|
| `[hx-confirm]` | `hx-confirm` | present (any value) |

**Module source**

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

## Guidance (structured)

### Seams

- any element with hx-confirm gets the designed dialog via htmx:confirm
- dialog message text IS the hx-confirm attribute value
- on approval the controller issues the underlying request — no per-button wiring

### Pitfalls

- hx-confirm is a client affordance — it needs no Exchange of its own
- do not re-implement confirm with window.confirm (loses the designed dialog)
- gallery toast 'Deleted (demo).' is MOCK_HTMX scaffolding in site/build_site.py — not Hyperpart surface; production returns the DELETE fragment from the Exchange

### Keyboard / AT

- dialog traps focus; Esc / cancel dismisses without issuing the request
- confirm control is keyboard-activatable (Enter/Space)

### Do / Don't

| Do | Don't |
|---|---|
| put hx-confirm on the destructive action element | wire a bespoke dialog open/close for every delete button |

### Composes with

- `button` (agents/button.md)
- `dialog` (agents/dialog.md)

## Guidance (prose; HTML from the registry notes field)

dz-confirm.js intercepts <code>htmx:confirm</code> (a client affordance — no server round-trip of its own). The dialog <em>message</em> is the <code>hx-confirm</code> attribute value (here: &quot;Delete this invoice? This cannot be undone.&quot;). On approval the controller issues the underlying request — no per-button wiring; any element with <code>hx-confirm</code> gets the designed dialog. <strong>Gallery-only toast:</strong> after confirm, this static site flashes <code>Deleted (demo).</code> — that string is hard-coded in the site's <code>MOCK_HTMX</code> shim (<code>site/build_site.py</code>), not in the Hyperpart, not in <code>contracts/confirm.py</code>, and not returned by a server. Production: your <code>DELETE</code> endpoint returns the Exchange response fragment (row removal / empty-state); there is no toast API.

## Controller files

- `controllers/dz-confirm.js`
