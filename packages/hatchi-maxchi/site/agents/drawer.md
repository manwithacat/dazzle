# Drawer (`drawer`)

Edge-anchored panel on the native <dialog> — a drawer with a modal's guarantees (focus trap, inert background, Esc, backdrop). Built on the dialog: shares its opener, adds a side + slide. No drawer-specific JS. Body is a composition host — nest field, badge, card, controls, …

> **Layer:** L1 surface · **Recipe:** `overlay-dialog` — modal / drawer overlay
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="hm-demo-row" style="gap:var(--space-sm);flex-wrap:wrap">
  <button type="button" class="button" data-variant="outline" data-dialog-open="hm-drawer-demo">Open filters</button>
  <button type="button" class="button" data-variant="outline" hx-get="/mock/drawer/detail" hx-target="#hm-drawer-lazy-body" hx-swap="innerHTML" data-dialog-open="hm-drawer-lazy">Open record</button>
</div>
<dialog class="drawer" id="hm-drawer-demo" data-side="right" data-width="md" aria-labelledby="hm-drawer-demo-title" closedby="any">
  <form method="dialog">
    <div class="drawer__header">
      <h2 class="drawer__title" id="hm-drawer-demo-title">Filters</h2>
      <button type="submit" class="drawer__close" aria-label="Close drawer"><svg class="icon" aria-hidden="true"><use href="#i-x"/></svg></button>
    </div>
    <div class="drawer__body" tabindex="0" aria-label="Filter controls">
      <div class="stack" data-gap="md">
        <p class="hm-demo-muted" style="margin:0">Compose field, toggle-group, switch, and controls inside the scrollable body — guests keep their own DOM contracts.</p>
        <div class="form-field">
          <label class="form-label" for="hm-drawer-q">Search</label>
          <input class="form-input" id="hm-drawer-q" type="search" name="q" placeholder="Name, id, or region…" aria-describedby="hm-drawer-q-hint">
          <p class="form-hint" id="hm-drawer-q-hint">Matches title and secondary fields on the list exchange.</p>
        </div>
        <div class="stack" data-gap="xs">
          <div class="form-label" id="hm-drawer-density-label">Density</div>
          <fieldset class="toggle-group" role="radiogroup" aria-labelledby="hm-drawer-density-label">
            <label><input type="radio" name="hm-drawer-density" value="comfortable" checked><span>Comfortable</span></label>
            <label><input type="radio" name="hm-drawer-density" value="compact"><span>Compact</span></label>
          </fieldset>
        </div>
        <fieldset class="stack" data-gap="xs" style="border:0;padding:0;margin:0">
          <legend class="form-label">Status</legend>
          <label class="hm-inline"><input type="checkbox" class="checkbox" name="status" value="active" checked> Active</label>
          <label class="hm-inline"><input type="checkbox" class="checkbox" name="status" value="trial"> Trialing</label>
          <label class="hm-inline"><input type="checkbox" class="checkbox" name="status" value="churned"> Churned</label>
        </fieldset>
        <div class="hm-demo-row" style="justify-content:space-between;align-items:center;gap:var(--space-sm)">
          <label class="switch"><input type="checkbox" name="mine" value="1" data-switch><span class="switch__track" aria-hidden="true"></span><span>Only my records</span></label>
          <span class="badge" data-tone="neutral"><span class="badge-icon"><svg class="icon" aria-hidden="true"><use href="#i-filter"/></svg></span>3 filters</span>
        </div>
        <div class="alert" data-tone="info" role="alert">
          <span class="alert__icon"><svg class="icon" aria-hidden="true"><use href="#i-info"/></svg></span>
          <div class="alert__body">
            <div class="alert__title">Server owns the query</div>
            <div class="alert__description">Apply posts filter params on the list exchange — this form is method=dialog only so the gallery can close without a backend.</div>
          </div>
        </div>
      </div>
    </div>
    <div class="drawer__footer"><button type="submit" class="button" data-variant="ghost" value="reset">Reset</button><button type="submit" class="button" data-variant="primary" value="apply">Apply</button></div>
  </form>
</dialog>
<dialog class="drawer" id="hm-drawer-lazy" data-width="md" data-side="right" closedby="any" aria-labelledby="hm-drawer-lazy-title">
  <div class="drawer__header">
    <h2 class="drawer__title" id="hm-drawer-lazy-title">Record detail</h2>
    <div class="hm-demo-row" style="gap:var(--space-xs);align-items:center">
      <button type="button" class="button" data-variant="ghost" data-drawer-expand aria-pressed="false" aria-label="Expand drawer panel">Expand</button>
      <form method="dialog"><button type="submit" class="drawer__close" aria-label="Close"><svg class="icon" aria-hidden="true"><use href="#i-x"/></svg></button></form>
    </div>
  </div>
  <div id="hm-drawer-lazy-body" class="drawer__body" tabindex="0" aria-label="Record detail body" aria-live="polite">
    <p class="hm-demo-muted">Open record to load a composed peek fragment…</p>
  </div>
  <div class="drawer__footer">
    <form method="dialog"><button type="submit" class="button" data-variant="ghost">Close</button></form>
    <a class="button" data-variant="primary" href="blueprints/record-page.html">Open full page</a>
  </div>
</dialog>
```

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the **response fragment** in the table (usually HTML, not JSON). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

> **Do not reimplement the gallery.** Flash toasts (e.g. confirm’s > “Deleted (demo).”), `/mock/*` paths, and other static-site > scaffolding are **demo-only** (`MOCK_HTMX` in `site/build_site.py`). > They are not Hyperpart surface and not a product API. If you are > stuck making a toast or mock URL work, stop — implement the > exchange row below instead. See AGENTS.md › *Gallery demos are not > the product API*.

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/records/{id}?peek=1` | the opener button's click — the SAME click also fires the dz-dialog.js opener (`data-dz-dialog-open`), so the drawer shows while the body loads | composed detail fragment (card, badge, meta stack, actions) swapped into the drawer's body target | innerHTML | — |
| `GET /app/records/{id}` | Open full page footer link (plain navigation — not hx-*) | full record document (tabs, KPI grid, edit actions) — gallery Blueprint `record-page`; not a fragment swap | document (navigation) | — |

## Morph / swap

Stem: `stems/morph-safe-hypermedia.md` · decisions 0005–0007. Morph for **stable** surfaces; replacement for **disposable** fragments. Gallery mocks may approximate morph with `innerHTML` — production follows the swap column in **Server exchange**.

### Replace / `innerHTML` (reset OK)

- `GET /app/records/{id}?peek=1` → innerHTML
- `GET /app/records/{id}` → document (navigation)

### Identity rules

- Morph participants need **stable** `id` / domain keys (not loop indexes).
- Carry selection/edit affordances in the **DOM** (checked, `data-*`, ARIA) — not Alpine/`x-data` or a JS array a morph would orphan.
- Mark third-party widgets as explicit islands / morph-skip boundaries.

## How to use it

### Seams

- addressing: data-dz-dialog-open + dialog.dz-drawer (shares dz-dialog.js)
- chrome shells: form_shell (method=dialog wrap) vs exchange_shell (scoped close forms) — same header/body/footer BEM
- body is a composition host — nest field, toggle-group, switch, controls, badge, card, alert with honest guest DOM
- hypermedia peek: hx-get + data-dz-dialog-open on the same click (fragment into drawer__body; list stays underneath)
- peek → full page: real href to owned record URL (Blueprint record-page) — not type=button no-op
- expand/restore: data-dz-drawer-expand toggles resting width ↔ xl (aria-pressed + next-action label; not a multi-step cycle)
- data-dz-side / data-dz-width for placement presets
- demo must exercise behaviour: peek body tall enough to scroll independently of the host page
- composition matrix: tools/composition_matrix.py

### Do / Don't

| Do | Don't |
|---|---|
| compose existing Hyperparts inside drawer__body with their standalone DOM contracts | rebuild field/badge/switch chrome as one-off drawer-only markup |
| pick form_shell vs exchange_shell by whether the body may contain nested forms | mix half-patterns (header element + whole-form wrap) without reason |
| pair hx-get target with the scrollable body id | swap the entire dialog element (loses open state / focus trap) |
| use one KPI card per metric (or card-label + card-value meta) | one card wrapping an auto-grid of overridden card-value sizes |
| Open full page = <a href> to the record document (shareable / refreshable URL) | Open full page = expand the dialog or a dead type=button |
| Expand/Restore = 2-state data-dz-width toggle (next-action label + aria-pressed) | cycle md→lg→xl→full under a single “Widen” label |
| peek fragment tall enough that drawer__body scrolls (host page stays put) | short demo content that never exercises body overflow |

### Pitfalls

- do not invent a second open protocol — same addressing as dialog
- do not wrap exchange_shell body in method=dialog if the fragment may contain forms (nested form is invalid HTML)
- do not paint drawer__body muted — guests inherit colour
- do not put legend inside dz-toggle-group (breaks segment flex)
- do not use input.dz-switch when composing the switch Hyperpart (use label.dz-switch + track + data-dz-switch)
- do not use form-field as read-only meta (hint is help, not value)
- lazy body starts empty/skeleton; exchange fills #…-body, not the whole dialog
- do not label Expand/Restore “Open full page” — full page is navigation
- do not use type=button for full-page when the job is a new URL
- do not cycle multi-step widths under a unipolar verb (Widen→reset lies)
- do not leave pointer-open focus on header chrome (close, Expand, …) — settle to [autofocus] or the dialog shell (dz-dialog.js); close-only special-cases miss the next header button
- do not ship a scrollable body claim with content that never overflows

### Keyboard / AT

- native dialog focus trap + Esc/backdrop; body may be tabindex=0 for scroll
- pointer open: settle to [autofocus] else body else shell — never header chrome; re-settle after showModal (rAF) — single settle races
- Expand control: aria-pressed + aria-label for next action (Expand/Restore)
- label the body (aria-label) when it is the live region for peek loads
- toggle-group: external label + aria-labelledby (not legend inside)

### Related parts

- `dialog` — agents/dialog.md
- `field` — agents/field.md
- `toggle-group` — agents/toggle-group.md
- `switch` — agents/switch.md
- `controls` — agents/controls.md
- `badge` — agents/badge.md
- `card` — agents/card.md
- `button` — agents/button.md
- `alert` — agents/alert.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/drawer.py`

- **Required root:** `.dz-drawer` (part `drawer`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-drawer` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: drawer — edge-anchored panel (native dialog or aside).

Dual-lock unit is the drawer surface root. Gallery demos use
``<dialog class="dz-drawer">`` opened via ``data-dz-dialog-open``; the
substrate ``Drawer`` primitive emits ``<aside class="dz-drawer …">``.
Slide-over peek also uses ``dialog.dz-drawer``. Class ``.dz-drawer`` is the
stable cross-path selector.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="drawer",
    root=".dz-drawer",
    nodes=(Node(".dz-drawer", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Opened by shared dz-dialog.js ([data-dz-dialog-open]); close is native. Chrome shells: form_shell (one method=dialog wrap when body has no nested forms) vs exchange_shell (scoped close forms; body is HTMX target). Both keep drawer__header|body|footer as flex children (outer form is display:contents). Composition host: guests mount with their own DOM contracts (field triad, switch track, toggle-group without legend inside the fieldset, honest KPI cards). Peek: one click fires hx-get into the body and showModal. Peek vs full page: footer Open full page is a real link to the record-page Blueprint (owned URL) — not a CSS maximize. Expand / Restore toggles resting data-dz-width ↔ xl (honest next-action labels — not a multi-step cycle). Peek body content must be tall enough to show independent body scroll. See stems/host-chrome-symmetry.md and tools/composition_matrix.py.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/drawer.py`
