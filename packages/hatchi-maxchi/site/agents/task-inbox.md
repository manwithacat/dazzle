# Task inbox (`task-inbox`)

The personal worklist: filter chips over urgency-flagged items, each a drill link with title and meta.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="hm-measure-lg">
  <div class="task-inbox-chips">
    <div class="task-inbox-chip" data-chip-id="all"><span class="task-inbox-chip-count">6</span><span class="task-inbox-chip-label">All</span></div>
    <div class="task-inbox-chip" data-chip-id="overdue"><span class="task-inbox-chip-count">2</span><span class="task-inbox-chip-label">Overdue</span></div>
  </div>
  <ul class="task-inbox-items">
    <li class="task-inbox-item" data-urgency="overdue" data-item-id="t1">
      <a class="task-inbox-item-link" href="#">
        <span class="task-inbox-item-icon" aria-hidden="true"><svg class="icon" aria-hidden="true"><use href="#i-inbox"/></svg></span>
        <div class="task-inbox-item-body">
          <div class="task-inbox-item-title">Approve refund — Acme</div>
          <div class="task-inbox-item-meta">due in 2h · assigned to you</div>
        </div>
      </a>
    </li>
    <li class="task-inbox-item" data-urgency="due" data-item-id="t2">
      <a class="task-inbox-item-link" href="#">
        <span class="task-inbox-item-icon" aria-hidden="true"><svg class="icon" aria-hidden="true"><use href="#i-inbox"/></svg></span>
        <div class="task-inbox-item-body">
          <div class="task-inbox-item-title">Review KYC — Globex</div>
          <div class="task-inbox-item-meta">due tomorrow</div>
        </div>
      </a>
    </li>
  </ul>
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

Items carry data-dz-urgency="overdue|due|soon|later" (the server clamps anything else to later) + a stable data-dz-item-id; the whole row is one link, leading with its icon. Chips render count THEN label (data-dz-chip-id anchors a filter exchange in Dazzle).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
