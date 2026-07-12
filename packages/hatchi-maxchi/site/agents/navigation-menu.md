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
      <details class="navigation-menu__branch">
        <summary class="navigation-menu__trigger">Product</summary>
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
      <details class="navigation-menu__branch">
        <summary class="navigation-menu__trigger">Resources</summary>
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
- `details.dz-navigation-menu__branch` + `summary.dz-navigation-menu__trigger`
- Submenu affordance: CSS `::after` chevron on trigger (1rem, rotates open)
- pick-a-surface: top product/site go-to → navigation-menu (not menubar / menu / sidebar)

### Do / Don't

| Do | Don't |
|---|---|
| Let the controller close siblings on toggle and outside click | Leave multi-open mega panels as bare multi-details |
| CSS/SVG disclosure chevron at ~1rem control scale | Tiny Unicode caret as the only submenu signal |
| top nav with links + optional mega panels (go somewhere) | File/Edit command strip (menubar) or one Actions dropdown (menu) |

### Pitfalls

- Native details allow multi-open and ignore outside click — ship dz-navigation-menu.js
- Do not confuse with menubar (app File/Edit) or app-shell sidebar
- Gallery: href=# is product-shaped stand-in; MOCK_HTMX inert-hash handler stops host scroll — do not 'fix' Copy this to void(0)
- Do not reintroduce Unicode ▾ spans or 0.65em carets — match accordion disclosure chrome (stem affordance-disclosure-chrome)
- do not use navigation-menu for local action lists — that is menu

### Keyboard / AT

- aria-label on root nav
- Keyboard: Enter/Space toggles summary; Escape dismisses open panels
- Chevron is decorative (CSS); details/summary carry expand semantics

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

**Pick:** product/site **go-to** top nav — not File/Edit app chrome (menubar), not a single Actions dropdown (menu), not left-rail shell (app-shell). See docs/agent/pick-a-surface.md › Menus / panels / chrome strips. Open intent: exclusive + outside/Escape dismiss. Disclosure chevron is CSS on the trigger (not Unicode). Mega layout via data-dz-layout=mega. dz-navigation-menu.js; probes exclusive_open + dismiss_outside. shadcn parity (HMC-039).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/navigation_menu.py`
- `controllers/dz-navigation-menu.js`
