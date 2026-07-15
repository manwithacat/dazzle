# Message (`message`)

Chat message row — media + author/time meta + bubble. Outbound rows reverse with data-dz-from=out.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-stack" style="gap:0.75rem;max-width:28rem">
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
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- no Server exchange on this part — pure presentation or client chrome
- satisfy the DOM contract tables (CI stop-ship)

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/message.py`

- **Required root:** `.dz-message` (part `message`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-message` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: message — chat message row (media + meta + bubble).

Dual-lock unit is the message root. Author/time, bubble body, and
``data-dz-from`` orientation are host-owned. Class ``.dz-message`` is the
stable substrate root (gallery CSS; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="message",
    root=".dz-message",
    nodes=(Node(".dz-message", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

PLACEHOLDER — shadcn parity (HMC-041). Composes bubble. Live chat = server re-render / OOB append into message-scroller, not client message state. Dual-lock root .dz-message (HMC-134).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/message.py`
