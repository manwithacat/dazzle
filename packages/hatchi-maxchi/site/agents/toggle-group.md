# Toggle group (`toggle-group`)

Segmented control on native radios.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<fieldset class="toggle-group" role="radiogroup">
  <label><input type="radio" name="hm-view" checked><span><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-list"/></svg> List</span></label>
  <label><input type="radio" name="hm-view"><span><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-kanban"/></svg> Board</span></label>
  <label><input type="radio" name="hm-view"><span><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-calendar"/></svg> Calendar</span></label>
</fieldset>
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

## Source files

- `site/registry.py` (partial + exchanges + guidance)
