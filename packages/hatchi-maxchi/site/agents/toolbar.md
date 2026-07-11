# Toolbar (`toolbar`)

Inline composition — real button, toggle-group and menu markup nested in a role=toolbar bar. No client tree, no props: composition is HTML.

> **Layer:** L2 host · **Recipe:** `chrome-presentation` — presentation / chrome
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="toolbar" role="toolbar" aria-label="Editor actions">
  <button class="button" data-variant="primary"><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-circle-plus"/></svg> New</button>
  <div class="toggle-group" role="radiogroup" aria-label="View">
    <label><input type="radio" name="tb-view" checked><span>List</span></label>
    <label><input type="radio" name="tb-view"><span>Grid</span></label>
  </div>
  <details class="menu">
    <summary class="button" data-variant="outline">More ▾</summary>
    <div class="menu__panel"><button class="menu__item"><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-copy"/></svg> Duplicate</button><button class="menu__item" data-tone="destructive"><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-trash-2"/></svg> Delete</button></div>
  </details>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- no Server exchange on this part — pure presentation or client chrome
- no typed contracts/ module yet — the partial is the surface of record

## DOM contract

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

The dependency chips aggregate what the children need (here: Sprite, from the menu/button icons). Copy the whole thing — it is just nested markup.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
