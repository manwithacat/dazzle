# Message scroller (`message-scroller`)

Chat transcript viewport — scrollable stack of message rows. Document order is chronological (newest last).

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="message-scroller" data-message-scroller role="log" aria-label="Conversation" aria-live="polite" tabindex="0">
  <div class="message" data-message data-from="in">
    <span class="message__media" aria-hidden="true">MR</span>
    <div class="message__body">
      <div class="message__meta"><span class="message__author">Maya Reyes</span><time class="message__time" datetime="2026-07-12T10:02">10:02</time></div>
      <div class="bubble" data-bubble data-from="in">
        <p>Can we reschedule the walkthrough to Thursday?</p>
      </div>
    </div>
  </div>
  <div class="message" data-message data-from="out">
    <span class="message__media" aria-hidden="true">You</span>
    <div class="message__body">
      <div class="message__meta"><span class="message__author">You</span><time class="message__time" datetime="2026-07-12T10:04">10:04</time></div>
      <div class="bubble" data-bubble data-from="out">
        <p>Thursday 14:00 works — I'll send a calendar hold.</p>
      </div>
    </div>
  </div>
  <div class="message" data-message data-from="in">
    <span class="message__media" aria-hidden="true">MR</span>
    <div class="message__body">
      <div class="message__meta"><span class="message__author">Maya Reyes</span><time class="message__time" datetime="2026-07-12T10:05">10:05</time></div>
      <div class="bubble" data-bubble data-from="in">
        <p>Perfect — see you then.</p>
      </div>
    </div>
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

PLACEHOLDER — shadcn parity (HMC-042). role=log + aria-live=polite for assistive updates. Auto-scroll-to-bottom controller deferred; prefer append-at-end + optional host scrollIntoView.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
