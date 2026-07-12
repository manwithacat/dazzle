# Navigation menu (`navigation-menu`)

Top product/site nav with optional mega-menu panels — horizontal, not the app-shell sidebar. Triggers use native details.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<nav class="navigation-menu" data-navigation-menu aria-label="Product">
  <ul class="navigation-menu__list">
    <li class="navigation-menu__item"><a class="navigation-menu__link" href="#" aria-current="page">Home</a></li>
    <li class="navigation-menu__item">
      <details>
        <summary class="navigation-menu__trigger">Product <span class="navigation-menu__caret" aria-hidden="true">▾</span></summary>
        <div class="navigation-menu__panel" data-layout="mega">
          <div class="navigation-menu__group">
            <p class="navigation-menu__group-title">Build</p>
            <a href="#">DSL apps<small>Ship CRUD + workflows</small></a>
            <a href="#">Hyperparts<small>Gallery + contracts</small></a>
          </div>
          <div class="navigation-menu__group">
            <p class="navigation-menu__group-title">Operate</p>
            <a href="#">Deploy<small>Plan + target</small></a>
            <a href="#">Observability<small>Pulse + fitness</small></a>
          </div>
        </div>
      </details>
    </li>
    <li class="navigation-menu__item">
      <details>
        <summary class="navigation-menu__trigger">Resources <span class="navigation-menu__caret" aria-hidden="true">▾</span></summary>
        <div class="navigation-menu__panel">
          <div class="navigation-menu__group"><a href="#">Docs</a><a href="#">Changelog</a><a href="#">Community</a></div>
        </div>
      </details>
    </li>
    <li class="navigation-menu__item"><a class="navigation-menu__link" href="#">Pricing</a></li>
  </ul>
</nav>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

### Seams

- `[data-dz-navigation-menu]` / `.dz-navigation-menu` scopes exclusive open
- `details` + `summary.dz-navigation-menu__trigger` for panels

### Do / Don't

| Do | Don't |
|---|---|
| Let the controller close sibling details on toggle | Leave multi-open mega panels as native multi-details |

### Pitfalls

- Native details allow multi-open — ship dz-navigation-menu.js
- Do not confuse with menubar (app File/Edit) or app-shell sidebar

### Keyboard / AT

- aria-label on root nav
- Keyboard: platform details toggle via Enter/Space on summary

### Related parts

- `menubar` — agents/menubar.md
- `app-shell` — agents/app-shell.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/navigation_menu.py`

- **Required root:** `[data-dz-navigation-menu]` (part `navigation-menu`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-navigation-menu]` | `data-dz-navigation-menu` | present (any value) |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: navigation-menu — product nav exclusive-open root contract."""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="navigation-menu",
    root="[data-dz-navigation-menu]",
    nodes=(
        Node(
            "[data-dz-navigation-menu]",
            attrs={"data-dz-navigation-menu": Present()},
        ),
    ),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

shadcn parity (HMC-039). Distinct from menubar (app chrome) and app-shell (sidebar). Mega layout via data-dz-layout=mega. Exclusive open across panels: controllers/dz-navigation-menu.js (gallery probe navigation_menu.exclusive_open).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/navigation_menu.py`
- `controllers/dz-navigation-menu.js`
