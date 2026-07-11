# Dialog (`dialog`)

Modal on the native <dialog> — one line of JS to open, close for free (Esc / backdrop / method=dialog submit). Focus-trapped by the platform.

> **Layer:** L1 surface · **Recipe:** `overlay-dialog` — modal / drawer overlay
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<button class="button" data-variant="primary" data-dialog-open="hm-dialog-demo">Delete workspace…</button>
<dialog class="dialog" id="hm-dialog-demo" aria-labelledby="hm-dialog-demo-title" closedby="any">
  <form method="dialog">
    <div class="dialog__header">
      <h2 class="dialog__title" id="hm-dialog-demo-title">Delete workspace?</h2>
      <button type="submit" class="dialog__close" aria-label="Close dialog"><svg class="icon" aria-hidden="true"><use href="#i-x"/></svg></button>
    </div>
    <div class="dialog__body">
      <p>This permanently deletes the workspace and every record in it. This action cannot be undone.</p>
    </div>
    <div class="dialog__footer"><button type="submit" class="button" data-variant="outline">Cancel</button><button type="submit" class="button" data-variant="destructive" value="confirm">Delete</button></div>
  </form>
</dialog>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

### Seams

- data-dz-dialog-open triggers showModal() — opening is the only scripted behaviour
- confirm button may carry hx-delete / form submit; closing is native

### Do / Don't

| Do | Don't |
|---|---|
| use native <dialog> with data-dz-dialog-open triggers | build a div[role=dialog] + manual focus trap |

### Pitfalls

- do not re-implement close with custom overlays — use <dialog> + showModal
- returnValue on the confirm button is the hand-off for form-less actions

### Keyboard / AT

- Esc dismisses natively; focus is restored to the open trigger
- confirm / cancel are real buttons inside the dialog

### Related parts

- `button` — agents/button.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/dialog.py`

- **Required root:** `[data-dz-dialog-open]` (part `dialog`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-dialog-open]` | `data-dz-dialog-open` | present (any value) |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: dialog — native <dialog> open trigger contract."""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="dialog",
    root="[data-dz-dialog-open]",
    nodes=(Node("[data-dz-dialog-open]", attrs={"data-dz-dialog-open": Present()}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Opening is the only scripted behaviour (dz-dialog.js calls showModal() for a [data-dz-dialog-open] trigger); closing is native. The confirm button closes the dialog and sets returnValue — in a real app, carry the action on it (hx-delete …) or submit a form to the server.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/dialog.py`
- `controllers/dz-dialog.js`
