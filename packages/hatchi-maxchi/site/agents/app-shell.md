# App shell (`app-shell`)

The SaaS/admin application frame: persistent left navigation, an optional sticky top bar, a routed main workspace, and a responsive/collapsible sidebar whose state the server renders.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="app-shell" data-sidebar="open">
  <aside class="app-sidebar" id="app-sidebar">
    <div class="sidebar">
      <div class="sidebar-brand"><span class="sidebar-brand-text">Acme Ops</span></div>
      <nav class="sidebar-nav" aria-label="Primary">
        <ul class="sidebar-nav-list">
          <li><a class="sidebar-nav-link" aria-current="page" href="#"><span class="sidebar-nav-icon"><svg class="icon" aria-hidden="true"><use href="#i-layout-dashboard"/></svg></span><span class="sidebar-nav-label">Dashboard</span></a></li>
          <li><a class="sidebar-nav-link" href="#"><span class="sidebar-nav-icon"><svg class="icon" aria-hidden="true"><use href="#i-receipt"/></svg></span><span class="sidebar-nav-label">Invoices</span></a></li>
        </ul>
      </nav>
    </div>
  </aside>
  <div class="app-content">
    <header class="app-header">
      <div class="topbar">
        <div class="topbar-leading"><button type="button" class="sidebar-toggle" data-sidebar-toggle aria-expanded="true" aria-controls="app-sidebar" aria-label="Toggle navigation"><span class="sidebar-toggle__icon" aria-hidden="true"></span></button></div>
        <div class="topbar-title"><span class="topbar-title-text">Dashboard</span></div>
        <div class="topbar-trailing"><button type="button" class="icon-button" aria-label="Notifications"><svg class="icon" aria-hidden="true"><use href="#i-triangle-alert"/></svg></button></div>
      </div>
    </header>
    <div class="app-main">
      <p class="hm-demo-muted">The routed workspace. The hamburger collapses the sidebar; the state persists via a cookie so the server renders it correctly on the next request.</p>
    </div>
  </div>
</div>
```

## How to use it

### Seams

- root data-dz-sidebar=open|closed is SERVER-rendered from the dz_sidebar cookie
- [data-dz-sidebar-toggle] flips state and rewrites the cookie (1y, SameSite=Lax)

### Do / Don't

| Do | Don't |
|---|---|
| SSR data-dz-sidebar from the cookie so first paint has no flash | default open in HTML and fix it client-side after load |

### Pitfalls

- cookie not localStorage — the server must paint the correct first state
- the component owns the ≥64rem media query (viewport policy); layout primitives stay MQ-free

### Keyboard / AT

- toggle mirrors aria-expanded to the open/closed state
- narrow viewports: sidebar overlays; desktop: persistent rail

### Related parts

- `button` — agents/button.md
- `sidebar-layout` — agents/sidebar-layout.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/app_shell.py`

- **Required root:** `[data-dz-sidebar]` (part `app-shell`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-sidebar]` | `data-dz-sidebar` | one of ['open', 'closed'] |
| `[data-dz-sidebar-toggle]` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: app-shell — DOM contract for the sidebar shell controller."""

from contracts._kit import DomContract, Node, OneOf

DOM_CONTRACT = DomContract(
    part="app-shell",
    root="[data-dz-sidebar]",
    nodes=(
        Node("[data-dz-sidebar]", attrs={"data-dz-sidebar": OneOf("open", "closed")}),
        Node("[data-dz-sidebar-toggle]", attrs={}),
    ),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

The shell root carries data-dz-sidebar="open|closed" — SERVER-rendered from the dz_sidebar cookie, so first paint is correct with no flash; dz-app-shell.js flips the attribute and re-writes the cookie when [data-dz-sidebar-toggle] is clicked (and mirrors aria-expanded). Desktop (≥64rem): the sidebar is persistent and the content pane pads around it; narrow: it slides off-canvas and overlays (this component owns that media query deliberately — viewport policy, not intrinsic wrapping — the layout primitives inside stay media-query-free). The demo above is a standalone page embedded via iframe (its own browsing context, so the fixed sidebar behaves exactly as shipped) — the snippet below is the pure, copyable shell markup, with one embedding concession: the workspace slot is a <div> here because this demo lives inside the gallery's own <main>; in your app it is <main id="main-content"> (one visible main per document — the Blueprint shows the true form). The full motif — routed navigation swapping the main slot — is the saas-shell Blueprint.

## Source files

- `controllers/dz-app-shell.js`
