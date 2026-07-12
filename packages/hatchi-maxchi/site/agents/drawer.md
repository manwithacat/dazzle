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
        <p class="hm-demo-muted" style="margin:0">Compose field, toggle-group, and selection controls inside the scrollable body — the drawer is a host, not a special form type.</p>
        <div class="form-field">
          <label class="form-label" for="hm-drawer-q">Search</label>
          <input class="form-input" id="hm-drawer-q" type="search" name="q" placeholder="Name, id, or region…" aria-describedby="hm-drawer-q-hint">
          <p class="form-hint" id="hm-drawer-q-hint">Matches title and secondary fields on the list exchange.</p>
        </div>
        <fieldset class="toggle-group" role="radiogroup" aria-label="Result density">
          <legend class="form-label" style="margin-bottom:var(--space-xs)">Density</legend>
          <label><input type="radio" name="hm-drawer-density" value="comfortable" checked><span>Comfortable</span></label>
          <label><input type="radio" name="hm-drawer-density" value="compact"><span>Compact</span></label>
        </fieldset>
        <fieldset class="stack" data-gap="xs" style="border:0;padding:0;margin:0">
          <legend class="form-label">Status</legend>
          <label class="hm-inline"><input type="checkbox" class="checkbox" name="status" value="active" checked> Active</label>
          <label class="hm-inline"><input type="checkbox" class="checkbox" name="status" value="trial"> Trialing</label>
          <label class="hm-inline"><input type="checkbox" class="checkbox" name="status" value="churned"> Churned</label>
        </fieldset>
        <div class="hm-demo-row" style="justify-content:space-between;align-items:center;gap:var(--space-sm)">
          <label class="hm-inline"><input type="checkbox" class="switch" name="mine" value="1"> Only my records</label>
          <span class="badge" data-tone="neutral"><span class="badge-icon"><svg class="icon" aria-hidden="true"><use href="#i-filter"/></svg></span>3 filters</span>
        </div>
        <div class="alert" data-tone="info" role="status">
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
  <header class="drawer__header">
    <h2 class="drawer__title" id="hm-drawer-lazy-title">Record detail</h2>
    <form method="dialog"><button type="submit" class="drawer__close" aria-label="Close"><svg class="icon" aria-hidden="true"><use href="#i-x"/></svg></button></form>
  </header>
  <div id="hm-drawer-lazy-body" class="drawer__body" tabindex="0" aria-label="Record detail body" aria-live="polite">
    <p class="hm-demo-muted">Open record to load a composed peek fragment…</p>
  </div>
  <div class="drawer__footer">
    <form method="dialog" style="display:contents"><button type="submit" class="button" data-variant="ghost">Close</button></form>
    <button type="button" class="button" data-variant="primary">Open full page</button>
  </div>
</dialog>
```

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the **response fragment** in the table (usually HTML, not JSON). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

> **Do not reimplement the gallery.** Flash toasts (e.g. confirm’s > “Deleted (demo).”), `/mock/*` paths, and other static-site > scaffolding are **demo-only** (`MOCK_HTMX` in `site/build_site.py`). > They are not Hyperpart surface and not a product API. If you are > stuck making a toast or mock URL work, stop — implement the > exchange row below instead. See AGENTS.md › *Gallery demos are not > the product API*.

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/records/{id}?peek=1` | the opener button's click — the SAME click also fires the dz-dialog.js opener (`data-dz-dialog-open`), so the drawer shows while the body loads | composed detail fragment (card, badge, meta stack, actions) swapped into the drawer's body target | innerHTML | — |

## Morph / swap

Stem: `stems/morph-safe-hypermedia.md` · decisions 0005–0007. Morph for **stable** surfaces; replacement for **disposable** fragments. Gallery mocks may approximate morph with `innerHTML` — production follows the swap column in **Server exchange**.

### Replace / `innerHTML` (reset OK)

- `GET /app/records/{id}?peek=1` → innerHTML

### Identity rules

- Morph participants need **stable** `id` / domain keys (not loop indexes).
- Carry selection/edit affordances in the **DOM** (checked, `data-*`, ARIA) — not Alpine/`x-data` or a JS array a morph would orphan.
- Mark third-party widgets as explicit islands / morph-skip boundaries.

## How to use it

### Seams

- addressing: data-dz-dialog-open + dialog.dz-drawer (shares dz-dialog.js)
- body is a composition host — nest field, toggle-group, controls, badge, card, alert
- hypermedia peek: hx-get + data-dz-dialog-open on the same click
- data-dz-side / data-dz-width for placement presets

### Do / Don't

| Do | Don't |
|---|---|
| compose existing Hyperparts inside drawer__body | rebuild field/badge chrome as one-off drawer-only markup |
| pair hx-get target with the scrollable body id | swap the entire dialog element (loses open state / focus trap) |

### Pitfalls

- do not invent a second open protocol — same addressing as dialog
- footer forms: avoid nested <form> inside method=dialog bodies
- lazy body starts empty/skeleton; exchange fills #…-body, not the whole dialog

### Keyboard / AT

- native dialog focus trap + Esc/backdrop; body may be tabindex=0 for scroll
- label the body (aria-label) when it is the live region for peek loads

### Related parts

- `dialog` — agents/dialog.md
- `field` — agents/field.md
- `toggle-group` — agents/toggle-group.md
- `badge` — agents/badge.md
- `card` — agents/card.md
- `button` — agents/button.md
- `alert` — agents/alert.md

## DOM contract

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

Opened by shared dz-dialog.js ([data-dz-dialog-open]); close is native. Composition host: body nests field, toggle-group, checkbox/switch, badge, alert (filters demo) or server-swapped card + badge + menu actions (record peek). Second trigger is the hypermedia peek contract: one click fires hx-get into the body and showModal. data-dz-side / data-dz-width for placement.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
