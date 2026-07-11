# Status list (`status-list`)

System / check states as an icon + title + caption list — tone rides data-dz-state per row, never colour alone.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="status-list-region hm-measure-lg">
  <ul class="status-list" data-entry-count="3">
    <li class="status-list-entry" data-state="success">
      <span class="status-list-icon" aria-hidden="true"><svg class="icon" aria-hidden="true"><use href="#i-circle-check"/></svg></span>
      <div class="status-list-text">
        <div class="status-list-title">Payments API</div>
        <div class="status-list-caption">Operational · 99.99% this month</div>
      </div>
      <span class="status-list-pill">success</span>
    </li>
    <li class="status-list-entry" data-state="warning">
      <span class="status-list-icon" aria-hidden="true"><svg class="icon" aria-hidden="true"><use href="#i-triangle-alert"/></svg></span>
      <div class="status-list-text">
        <div class="status-list-title">Webhooks</div>
        <div class="status-list-caption">Elevated retries since 09:20</div>
      </div>
      <span class="status-list-pill">warning</span>
    </li>
    <li class="status-list-entry" data-state="neutral">
      <span class="status-list-icon-spacer" aria-hidden="true"></span>
      <div class="status-list-text">
        <div class="status-list-title">Nightly export</div>
        <div class="status-list-caption">Scheduled 02:00</div>
      </div>
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

Per-row state is data-dz-state on the entry (the pill repeats it as text for WCAG 1.4.1); a neutral row has no pill and an icon SPACER keeps the text column aligned. The wrapper's data-dz-entry-count is the server's row count — handy for e2e assertions without counting DOM.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
