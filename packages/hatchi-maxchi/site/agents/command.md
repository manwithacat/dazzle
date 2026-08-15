# Command palette (`command`)

The hx-get palette — the htmx4 flagship. Press ⌘K.

> **Layer:** L1 surface · **Recipe:** `command-palette` — command palette search
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<button class="button" data-variant="outline" data-hm-open-command>Open palette <kbd class="kbd">⌘K</kbd></button>
<dialog class="command" data-command aria-label="Command palette" closedby="any">
  <div class="command__bar"><input class="command__input" type="search" name="q" placeholder="Search workspaces and records…" autocomplete="off" aria-controls="command-results" aria-autocomplete="list" hx-get="/mock/command" hx-trigger="input changed delay:150ms, focus once" hx-target="next .command__results"><button type="button" class="command__close" data-hm-close-command aria-label="Close command palette"><svg class="icon" aria-hidden="true"><use href="#i-x"/></svg></button></div>
  <div class="command__results" id="command-results" role="listbox" aria-label="Results"></div>
</dialog>
```

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the **response fragment** in the table (usually HTML, not JSON). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

> **Do not reimplement the gallery.** Flash toasts (e.g. confirm’s > “Deleted (demo).”), `/mock/*` paths, and other static-site > scaffolding are **demo-only** (`MOCK_HTMX` in `site/build_site.py`). > They are not Hyperpart surface and not a product API. If you are > stuck making a toast or mock URL work, stop — implement the > exchange row below instead. See AGENTS.md › *Gallery demos are not > the product API*.

| Request | Trigger | Response fragment | Swap | Envelope | States |
|---|---|---|---|---|---|
| `GET /app/command` | the search input, on `input` (debounced 150ms) and first `focus` | zero or more result rows — `<a>`/`<button class="dz-command__item" role="option">` grouped by `<div class="dz-command__group">` headers; empty query returns the full persona catalog; no matches returns `<div class="dz-command__empty">` | innerHTML of the sibling `.dz-command__results` listbox | `body_only` | loading empty populated error |

## Swap contract

Agent-visible HTMX topology (ADR-0054 / decision 0012). **Exchange envelope** = what the response may re-emit relative to the persistent slot (`body_only` | `outer` | `none` | `host_owned` | `document`). Dual-lock validates part markup only — not this envelope. Stem: `stems/morph-safe-hypermedia.md`.

Gallery mocks may approximate morph with `innerHTML` — production follows the swap column in **Server exchange**.

### Exchanges (swap · envelope)

- `GET /app/command` → innerHTML of the sibling `.dz-command__results` listbox · **envelope=`body_only`**

### Replace / other HTML swap

- `GET /app/command` → body_only

### Envelope rules

- **`body_only`** — innerHTML / innerMorph into a slot; response is interior only (no re-wrap of slot id / nested `data-dz-region`).
- **`outer`** — outerHTML / outerMorph; response may carry identity.
- **`none`** — no HTML swap (JSON/204/bytes; client or OOB companion).
- **`host_owned`** — swap target/mode chosen by the host button's `hx-target` / `hx-swap` (part does not fix the envelope).
- **`document`** — full navigation / document load (not a fragment).
- Slot owns stable `id` / domain keys; state in DOM, not Alpine.

### Envelope response examples

What the **server returns** for each exchange. Match the **exchange envelope**; dual-lock still applies to interior markup.

#### `GET /app/command` · envelope=`body_only`

Correct response for body_only into .dz-command__results (innerHTML / innerMorph). Wrong: re-wrapping the slot.

**Do — correct response body**

```html
<!-- envelope=body_only → option rows for the results listbox -->
<div class="dz-command__group" role="group" aria-label="Actions">
  <a class="dz-command__item" role="option" href="/app/invoices">Invoices</a>
  <button type="button" class="dz-command__item" role="option">New contact</button>
</div>
```

**Don’t — violates `body_only`**

```html
<!-- WRONG: whole command palette chrome -->
<div class="dz-command" data-dz-command>
  <input class="dz-command__input" />
  <div class="dz-command__results">…</div>
</div>
```

## How to use it

### Seams

- hx-get on the search input returns persona-scoped result fragments
- open triggers: data-hm-open-command / ⌘K; close: data-hm-close-command + closedby=any
- shortcut-hint-chrome: opener kbd is adjacent (button gap); item kbd is trailing

### Do / Don't

| Do | Don't |
|---|---|
| return result-list fragments from /app/command (or mock) | hydrate a client-side result model the palette must re-render |
| adjacent gap on opener; trailing auto on result-row kbd | flush label+kbd or treat ⌘K as a primary icon |

### Pitfalls

- type=search swallows Esc to clear the value — the controller must close on first Esc
- do not absolute-position the close button against a modal dialog (Safari/iPadOS collapse)
- do not glue ⌘K to the opener label (0 gap) — chip is spatially secondary

### Keyboard / AT

- Esc closes the palette on first press even mid-query
- Arrow keys move aria-activedescendant through results; Enter activates
- close button is the touch dismiss affordance (no Esc key on tablets)

### Related parts

- `button` — agents/button.md
- `kbd` — agents/kbd.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/command.py`

- **Required root:** `[data-dz-command]` (part `command`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-command]` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: command — palette dialog root contract."""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="command",
    root="[data-dz-command]",
    nodes=(Node("[data-dz-command]", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

In Dazzle the input's hx-get hits /app/command, which returns persona-scoped results as real links. The gallery mock returns <button type=button class=dz-command__item> rows so picking an option closes the palette without href=# scrolling the page to the top mid-browse. Shortcut chips (stem shortcut-hint-chrome): opener uses adjacent layout (button gap); result rows use trailing (margin-inline-start: auto on .dz-kbd).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/command.py`
- `controllers/dz-command.js`
