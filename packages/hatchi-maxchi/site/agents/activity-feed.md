# Activity feed (`activity-feed`)

Who-did-what rows on a dotted spine — actor, time, and a message bubble.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-measure-lg">
  <ul class="activity-feed">
    <li class="activity-row">
      <span class="activity-dot"><svg fill="currentColor" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6"/></svg></span>
      <div class="activity-row-inner">
        <div class="activity-time">09:41</div>
        <div class="activity-bubble"><span class="activity-actor">Ada</span> approved the refund.</div>
      </div>
    </li>
    <li class="activity-row">
      <span class="activity-dot"><svg fill="currentColor" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6"/></svg></span>
      <div class="activity-row-inner">
        <div class="activity-time">09:12</div>
        <div class="activity-bubble"><span class="activity-actor">System</span> flagged the account for review.</div>
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

Rows are server-rendered newest-first; an empty feed renders dz-activity-empty. The dot column and bubble keep alignment without a grid — the row is the flex unit.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
