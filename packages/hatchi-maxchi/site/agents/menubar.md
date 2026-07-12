# Menubar (`menubar`)

Horizontal app menus (File / Edit / View) — each item is a native details/summary so open state is DOM-native.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="menubar" data-menubar role="menubar" aria-label="App">
  <details class="menubar__item">
    <summary class="menubar__trigger">File</summary>
    <div class="menubar__panel" role="menu" aria-label="File"><a href="#" role="menuitem">New</a><a href="#" role="menuitem">Open…</a><button type="button" role="menuitem">Export</button></div>
  </details>
  <details class="menubar__item">
    <summary class="menubar__trigger">Edit</summary>
    <div class="menubar__panel" role="menu" aria-label="Edit"><button type="button" role="menuitem">Undo</button><button type="button" role="menuitem">Redo</button></div>
  </details>
  <details class="menubar__item">
    <summary class="menubar__trigger">View</summary>
    <div class="menubar__panel" role="menu" aria-label="View"><button type="button" role="menuitem">Zoom in</button><button type="button" role="menuitem">Zoom out</button></div>
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

PLACEHOLDER — shadcn parity (HMC-038). Native details for open state (no Alpine). Single-open across items may need a tiny controller later; compose with menu Hyperpart for denser item lists.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
