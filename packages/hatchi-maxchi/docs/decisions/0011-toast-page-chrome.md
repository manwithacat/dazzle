# 0011 — Toast as page chrome (stack host + emission)

**Status:** Accepted
**Date:** 2026-07-16
**Stems:** `stems/page-chrome-toast.md`, `stems/hyperpart-not-component.md`,
`stems/three-layers.md`, `stems/morph-safe-hypermedia.md`,
`stems/pragmatic-gallery-aesthetics.md`, `stems/chrome-vs-protocol.md`

## Context

Toast is high-traffic product feedback: every create/save/delete and many
validation paths surface it. Early HM work treated toast as fragment chrome
(message-only, 5s hard remove). After promoting a dual-lock Hyperpart, three
classes of bug kept recurring:

1. **Gallery framing** — shell-width iframes hid fixed top-right units.
2. **Channel drift** — OOB `with_toast` vs `HX-Trigger showToast` vs client
   bridge diverged in slots and timing.
3. **Motion/timing** — instant DOM remove and short TTL felt unfinished next to
   mature exemplars (e.g. Penguin’s 8s + pause + leave transition).

Agents also confuse toast with **alert** (inline), **dialog** (blocking), and
**nudge** (onboarding). This decision freezes the job and the host contract.

## Decision

### Job

**Toast** = L2 **page-chrome host** that stacks **transient**, non-blocking
notifications on the **viewport**. Users keep working; the system reports
outcome for a few seconds.

| Is toast | Is not toast |
|----------|--------------|
| “Saved” / “Created” after mutation | Inline `#form-errors` |
| Transient validation toast when no form target | Blocking confirm / dialog |
| Client bridge for export / rollback | Persistent site banner |
| Optional title + action row | Full notification center / SPA store |

Recipe: `chrome-presentation`. Layer: **L2 host**.

### Stack ownership

| Rule | Detail |
|------|--------|
| Single stack | Shell mounts **one** `#dz-toast.dz-toast-stack` (or unprefixed gallery id) |
| Viewport | `position: fixed` to the **viewport** (not a content column) |
| Cap | `data-dz-toast-cap` (default 8); oldest leave when exceeded |
| Pointer | Stack `pointer-events: none`; units re-enable hits |
| Morph | **Forbidden** on the stack — OOB `afterbegin` / replace only |

### Toast unit (dual-lock)

Root: `[data-dz-toast-level]` on `.dz-toast` with `data-dz-remove-after`.

| Slot | Required | Notes |
|------|----------|--------|
| level | yes | `info` \| `success` \| `warning` \| `error` |
| remove-after | yes | htmx-style duration (`8s`, `300ms`, …) |
| title | no | `.dz-toast__title` |
| message | yes in practice | `.dz-toast__message` (text only from client detail) |
| actions | no | `.dz-toast__actions` → link or dismiss button |
| icon | shipped default | `.dz-toast__icon` decorative inline SVG; host ensures |
| close | yes (shipped) | `[data-dz-toast-dismiss]` |
| progress | host-owned | TTL bar; pauses with timer |

Roles: `role="status"` by default; **`role="alert"`** for `error`.

### Emission channels (must stay parity)

| Channel | Owner | Payload shape |
|---------|-------|----------------|
| OOB HTML | `with_toast(response, message, level, …)` | Server-rendered unit |
| HX-Trigger | `htmx_trigger_headers` / mutation wrappers | `showToast: { title, message, type, actions? }` |
| Client event | `showToast` on document, `toast` on stack, `dz.toast` | Same detail object |

**One host** (`controllers/dz-toast.js`) schedules, pauses, animates leave, and
caps. No second Alpine notify graph.

### Timing and motion

| Rule | Value |
|------|--------|
| Default TTL | **8s** (info / success / warning) |
| Error TTL | **10s** when duration not overridden |
| Pause | Hover or focus **inside the stack** pauses **all** active timers + TTL bars |
| Enter | ~300ms ease-out (from stack edge) |
| Leave | ~300ms ease-in, **then** remove (click, timer, or cap eviction) |
| Reduced motion | Collapse enter/leave duration; still dismiss |

### Gallery

| Rule | Detail |
|------|--------|
| Frame | `framed=True`, **`frame_kind="overlay"`** (natural width; no 64rem hide) |
| Copy this | **Product stack + unit only** — no fire-button stage |
| Live demo | Gallery chrome may wrap a stage + triggers; not part of the contract |
| Observable | Cold viewer sees a seed toast and can fire levels in &lt;5s |

### Dazzle product path

Generated CRUD mutations use titled `showToast` via `htmx_trigger_headers`.
Peek save-and-stay may attach a **View** action when not redirecting to the
same URL. Apps should not invent a parallel toast store.

## Consequences

- Controllers stay vanilla (decision 0010); timing/motion live in host + CSS.
- Contract remains DOM-only dual-lock; progress is host-injected (not contract-required).
- SHADCN / Penguin used as **function catalogues** (pause, TTL, leave), not
  Alpine or Tailwind targets.
- Visual baselines and behaviour tests pin dismiss leave delay and overlay frame.

## Phased sophistication (explicit backlog)

| Phase | Status | Scope |
|-------|--------|--------|
| A — Dual-lock unit + title/actions + pause | **Done** | Hyperpart, `with_toast`, showToast slots |
| B — Viewport gallery + 8s + leave motion | **Done** | overlay frame, enter/leave, shell stack |
| C — TTL progress + error 10s + clean Copy this | **Done** | progress bar, demo_shell split |
| D — Level icons (SSR + client parity) | **Done** | inline SVG `__icon`; host ensures if missing |
| E — Person / message toast | Later | **separate** optional composition, not a severity |
| F — Sound / swipe-dismiss | Later | opt-in only; a11y / preference gated |

## Not decided here

- Bottom vs top stack placement tokens (product may add `data-dz-toast-placement` later).
- Cross-tab / service-worker push (out of Hyperpart scope).
- A fleet notification inbox (different job).
