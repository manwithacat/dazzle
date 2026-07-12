# Menu (`menu`)

Disclosure menu (`<details>`) — no JS for open state. A disclosure, not a full ARIA menu: no roving tabindex or typeahead.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<details class="menu">
  <summary class="button" data-variant="outline">Actions</summary>
  <div class="menu__panel">
    <button type="button" class="menu__item"><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-pencil"/></svg> Edit</button>
    <button type="button" class="menu__item"><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-copy"/></svg> Duplicate</button>
    <hr class="menu__separator">
    <button type="button" class="menu__item" data-tone="destructive"><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-trash-2"/></svg> Delete</button>
  </div>
</details>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

### Seams

- `details.dz-menu` + `summary` (usually `.dz-button`) + `.dz-menu__panel`
- disclosure chevron is presentation on summary::after — not label text

### Do / Don't

| Do | Don't |
|---|---|
| label text only + CSS chevron that rotates when [open] | Actions ▾ as a single text string for the expand signal |

### Pitfalls

- do not bake ▾/▼ into the summary text — house disclosure chrome is CSS/SVG
- not a full ARIA menu (no roving tabindex/typeahead) — do not invent role=menu half-contracts
- distinct from menubar (app chrome strip) and navigation-menu (site nav)

### Keyboard / AT

- details/summary carry expand; chevron is decorative
- Keyboard: Enter/Space on summary toggles the panel

### Related parts

- `button` — agents/button.md

## DOM contract

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

Trigger label is plain text; the open-panel signal is CSS ::after chevron on the summary (same family as accordion / navigation-menu — not Unicode ▾ in the label). Open intent is native details (single trigger). Honest disclosure, not ARIA menu with roving tabindex.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
