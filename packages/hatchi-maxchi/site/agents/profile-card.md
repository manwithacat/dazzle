# Profile card (`profile-card`)

The identity panel: avatar or initials beside name and meta, an optional 3-up stats grid, and a bulleted facts list.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="profile-card-region hm-measure">
  <div class="profile-card">
    <div class="profile-identity">
      <span class="profile-initials" aria-hidden="true">MR</span>
      <div class="profile-text">
        <h3 class="profile-primary">Maya Reyes</h3>
        <p class="profile-secondary">Operations lead · North grid</p>
      </div>
    </div>
    <dl class="profile-stats">
      <div class="profile-stat">
        <dt class="profile-stat-label">Open work orders</dt>
        <dd class="profile-stat-value">7</dd>
      </div>
      <div class="profile-stat">
        <dt class="profile-stat-label">Sites</dt>
        <dd class="profile-stat-value">3</dd>
      </div>
      <div class="profile-stat">
        <dt class="profile-stat-label">On call</dt>
        <dd class="profile-stat-value">—</dd>
      </div>
    </dl>
    <ul class="profile-facts">
      <li class="profile-fact"><span class="profile-fact-bullet" aria-hidden="true">·</span><span class="profile-fact-text">Certified for HV switching</span></li>
      <li class="profile-fact"><span class="profile-fact-bullet" aria-hidden="true">·</span><span class="profile-fact-text">Joined March 2024</span></li>
    </ul>
  </div>
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

The avatar slot prefers an <img class="dz-profile-avatar"> and falls back to an initials chip; empty stat values render an em-dash (absence is data). Stats are a real <dl>; the facts bullet is decorative markup, hidden from assistive tech.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
