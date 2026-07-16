# Toast (`toast`)

Stack host + auto-dismiss notifications — title, body, optional actions; hover/focus pauses the timer (htmx OOB or client bridge).

> **Layer:** L2 host · **Recipe:** `chrome-presentation` — presentation / chrome
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div id="toast" class="toast-stack" aria-live="polite" data-toast-cap="8">
  <div class="toast toast-enter" data-toast-level="success" data-remove-after="8s" role="status">
    <span class="toast__icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg></span>
    <div class="toast__body">
      <div class="toast__title">Saved</div>
      <div class="toast__message">Your changes are live.</div>
      <div class="toast__actions"><a class="toast__action" href="#toast">View record</a><button type="button" class="toast__action" data-toast-dismiss>Dismiss</button></div>
    </div>
    <button type="button" class="toast__close" data-toast-dismiss aria-label="Dismiss"></button>
  </div>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## Morph / swap

Stem: `stems/morph-safe-hypermedia.md` · decisions 0005–0007. Morph for **stable** surfaces; replacement for **disposable** fragments. Gallery mocks may approximate morph with `innerHTML` — production follows the swap column in **Server exchange**.

This L2 host has no declared hypermedia exchanges in the registry. If you add persistent region updates, prefer `innerMorph` / `outerMorph` with stable row/panel ids; use replacement for flash panes and full resets.

### Identity rules

- Morph participants need **stable** `id` / domain keys (not loop indexes).
- Carry selection/edit affordances in the **DOM** (checked, `data-*`, ARIA) — not Alpine/`x-data` or a JS array a morph would orphan.
- Mark third-party widgets as explicit islands / morph-skip boundaries.

## How to use it

### Seams

- stack host #dz-toast.dz-toast-stack receives OOB afterbegin
- data-dz-remove-after + data-dz-toast-level on each .dz-toast
- optional .dz-toast__title / __message / __actions slots
- data-dz-toast-dismiss removes the nearest .dz-toast
- showToast CustomEvent or window.dz.toast for client path
- host injects .dz-toast__progress TTL bar (pauses with timer)
- level icon .dz-toast__icon (inline SVG; host ensures if missing)

### Do / Don't

| Do | Don't |
|---|---|
| emit structured toasts (title + message + actions) from the exchange response via with_toast | build a client notification SPA store or copy third-party Alpine toast idioms |
| let hover/focus pause auto-dismiss so users can read or activate actions | force-dismiss while the pointer is over the toast |

### Pitfalls

- do not morph the toast stack — replace/afterbegin only
- do not invent Alpine notify stacks — use OOB + this host
- message text must be textContent (never innerHTML from detail)
- gallery fire buttons are demo chrome — production uses with_toast or HX-Trigger showToast

### Keyboard / AT

- role=status (or alert for error); aria-live on the stack
- dismiss control is keyboard-activatable
- focus inside the stack pauses auto-dismiss

### Related parts

- `button` — agents/button.md
- `alert` — agents/alert.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/toast.py`

- **Required root:** `[data-dz-toast-level]` (part `toast`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-toast-level]` | `data-dz-toast-level` | one of ['info', 'success', 'warning', 'error'] |
| `[data-dz-toast-level]` | `data-dz-remove-after` | present (any value) |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: toast — stack host + auto-dismiss notification unit.

Dual-lock unit is the toast root (``[data-dz-toast-level]`` on ``.dz-toast``)
plus the stack host (``#dz-toast.dz-toast-stack``). Level, auto-dismiss delay,
title, message, and optional action row are host-owned.

Page chrome (decision 0011 / stem ``page-chrome-toast``): viewport stack,
default TTL 8s (10s error), pause on hover/focus, leave before remove. TTL
progress bar is host-injected (not a contract-required node).

Server emit: ``dazzle.http.runtime.response_helpers.with_toast``.
Client emit: ``showToast`` / stack ``toast`` events (``controllers/dz-toast.js``).

Contract selectors use ``[data-dz-*]`` only — the kit has no CSS class engine.
"""

from __future__ import annotations

from contracts._kit import DomContract, Node, OneOf, Present

DOM_CONTRACT = DomContract(
    part="toast",
    root="[data-dz-toast-level]",
    nodes=(
        Node(
            "[data-dz-toast-level]",
            attrs={
                "data-dz-toast-level": OneOf("info", "success", "warning", "error"),
                "data-dz-remove-after": Present(),
            },
        ),
    ),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Dual-lock root .dz-toast + stack #dz-toast.dz-toast-stack. Decision 0011-toast-page-chrome: viewport host, 8s/10s TTL, pause, leave motion, TTL progress, level icons. Server: with_toast(..., title=…, actions=…). Not Alpine notify — HTMX OOB + CustomEvent.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/toast.py`
- `controllers/dz-toast.js`
