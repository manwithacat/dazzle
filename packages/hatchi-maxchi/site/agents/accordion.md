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

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

Open intent: exclusive via native name= on peer <details> (stem details-open-intent) — zero JS. Gallery probe accordion.exclusive_open. No aria-expanded wiring: details/summary carry it. Drop name= only when multi-open FAQ is intentional.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
