# Accordion (`accordion`)

Native <details> group; single-open via the HTML name= attribute — opening one closes its siblings, zero JS.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="accordion">
  <details class="accordion__item" name="hm-acc" open>
    <summary class="accordion__trigger">What is a Hyperpart?</summary>
    <div class="accordion__panel">A server-rendered partial plus its exchange contract — the htmx-native unit of reuse.</div>
  </details>
  <details class="accordion__item" name="hm-acc">
    <summary class="accordion__trigger">Do I need a client framework?</summary>
    <div class="accordion__panel">No — state lives on the server and htmx swaps the markup.</div>
  </details>
  <details class="accordion__item" name="hm-acc">
    <summary class="accordion__trigger">Can two panels be open at once?</summary>
    <div class="accordion__panel">Not while they share a name=. Drop the attribute for an independent, multi-open group.</div>
  </details>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## Swap contract

Agent-visible HTMX topology (ADR-0054 / decision 0012). **Exchange envelope** = what the response may re-emit relative to the persistent slot (`body_only` | `outer` | `none` | `host_owned` | `document`). Dual-lock validates part markup only — not this envelope. Stem: `stems/morph-safe-hypermedia.md`.

**No host HTMX exchange** on this part — presentation or client chrome only. **Exchange envelope:** `n/a`.

If a **host** wraps this markup in `hx-*`, **that host owns the swap contract** (sole identity + envelope). Prefer `innerMorph` / `outerMorph` for stable slots; replacement for flash; body-only responses under inner swaps.

### Envelope response examples

What the **server returns** for each exchange. Match the **exchange envelope**; dual-lock still applies to interior markup.

This part has no owned exchange (envelope `n/a`). If a host adds `hx-*`, that host’s envelope applies — typically `body_only`:

```html
<!-- Prefer hx-swap=innerMorph into a stable body slot -->
<div class="dz-stack">content…</div>
```

Do **not** re-own the slot:

```html
<div id="accordion-root" data-dz-region>…</div>
```

## How to use it

### Seams

- `details.dz-accordion__item` + shared `name=` for exclusive group
- `summary.dz-accordion__trigger` — native toggle, no controller

### Do / Don't

| Do | Don't |
|---|---|
| Share one name= across peer items for single-open FAQ | Copy menubar exclusive controller onto accordion panels |

### Pitfalls

- Missing or mismatched name= → multi-open (not exclusive)
- Do not add exclusive-open JS here — browser name= is the contract
- Do not confuse with tree (multi_open forest) or menubar (controller chrome)

### Keyboard / AT

- details/summary expose expanded state natively
- Keyboard: Enter/Space on summary

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/accordion.py`

- **Required root:** `.dz-accordion` (part `accordion`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-accordion` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: accordion — native details group (single-open via name=).

Dual-lock unit is the accordion root. Item open state, panel body, and
shared ``name=`` exclusive-open policy are host-owned. Class
``.dz-accordion`` is the stable substrate root (gallery CSS; no
FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="accordion",
    root=".dz-accordion",
    nodes=(Node(".dz-accordion", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Open intent: exclusive via native name= on peer <details> (stem details-open-intent) — zero JS. Gallery probe accordion.exclusive_open. No aria-expanded wiring: details/summary carry it. Drop name= only when multi-open FAQ is intentional.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/accordion.py`
