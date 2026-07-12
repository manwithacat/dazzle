# Menubar (`menubar`)

Horizontal app menus (File / Edit / View) — each item is a native details/summary so open state is DOM-native.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="menubar" data-menubar role="menubar" aria-label="App">
  <details class="menubar__item">
    <summary class="menubar__trigger">File</summary>
    <div class="menubar__panel" role="menu" aria-label="File"><a href="#" role="menuitem">New</a><a href="#" role="menuitem">Open…</a><button type="button" role="menuitem">Export</button></div>
  </details>
  <details class="menubar__item">
    <summary class="menubar__trigger">Edit</summary>
    <div class="menubar__panel" role="menu" aria-label="Edit"><button type="button" role="menuitem">Undo</button><button type="button" role="menuitem">Redo</button></div>
  </details>
  <details class="menubar__item">
    <summary class="menubar__trigger">View</summary>
    <div class="menubar__panel" role="menu" aria-label="View"><button type="button" role="menuitem">Zoom in</button><button type="button" role="menuitem">Zoom out</button></div>
  </details>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

### Seams

- `[data-dz-menubar]` / `.dz-menubar` root scopes exclusive open
- `details.dz-menubar__item` + `summary.dz-menubar__trigger` for panels

### Do / Don't

| Do | Don't |
|---|---|
| Let the controller close siblings on toggle | Hand-roll per-item open flags in Alpine/React |

### Pitfalls

- Native details allow multi-open — never ship menubar without dz-menubar.js exclusive-open
- Do not nest menubars; one root per chrome strip

### Keyboard / AT

- role=menubar / menuitem on panel actions
- Keyboard: platform details toggle via Enter/Space on summary

### Related parts

- `menu` — agents/menu.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/menubar.py`

- **Required root:** `[data-dz-menubar]` (part `menubar`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-menubar]` | `data-dz-menubar` | present (any value) |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: menubar — app chrome exclusive-open root contract."""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="menubar",
    root="[data-dz-menubar]",
    nodes=(Node("[data-dz-menubar]", attrs={"data-dz-menubar": Present()}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

shadcn parity (HMC-038). Native details for open state; controllers/dz-menubar.js enforces exclusive open across items (gallery probe menubar.exclusive_open). Compose with menu Hyperpart for denser item lists.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/menubar.py`
- `controllers/dz-menubar.js`
