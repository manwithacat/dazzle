# Keyboard key (`kbd`)

Shortcut chip for docs and command chrome — <kbd class=dz-kbd>.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-demo-row">
  <kbd class="kbd">⌘K</kbd>
  <kbd class="kbd">Esc</kbd>
  <kbd class="kbd">↵</kbd>
  <kbd class="kbd">⇧</kbd>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

### Seams

- `<kbd class="dz-kbd">` — always the house chip, never bare Unicode
- layout roles: adjacent (button:has kbd gap) vs trailing (list/menu auto)

### Do / Don't

| Do | Don't |
|---|---|
| visually secondary chip + adjacent gap or trailing auto | glue ⌘K to the action label or invent a Lucide keyboard as the only hint |

### Pitfalls

- 0px gap between primary label and kbd under-signals secondary metadata
- do not apply affordance-disclosure-chrome (chevrons) rules to shortcuts
- do not put a kbd on every dense toolbar control (clutter)

### Keyboard / AT

- kbd is presentational hint; the control still needs its own accessible name

### Related parts

- `command` — agents/command.md
- `button` — agents/button.md

## DOM contract

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

Stem shortcut-hint-chrome: keyboard chips are visually secondary (mono, small, muted keycap) and spatially secondary — layout roles adjacent (flex gap next to a label) vs trailing (row end via margin-inline-start: auto). Not disclosure iconography. Styles in hm-core.css; pure presentation.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
