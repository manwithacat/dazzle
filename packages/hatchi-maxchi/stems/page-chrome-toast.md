# Stem: Page-chrome toast

## Claim

**Toast** is **page chrome**, not a content Hyperpart and not a modal. It
answers: *“Did that action work, and do I need to notice for a few seconds?”*
The stack is **viewport-owned** (fixed overlay on the whole rendered page).
The **host** owns timing, pause, motion, and cap; the **server or bridge** only
*emits* units into the stack.

## Reconstruct

| Axis | Rule |
|------|------|
| **Job** | Transient feedback after a mutation, validation snag, or system note |
| **Layer** | L2 host (`chrome-presentation`) — shell mounts `#dz-toast` once |
| **Placement** | `position: fixed` against the **viewport** (or framed live viewport), never a content column |
| **Emit** | HTMX OOB into the stack, or `HX-Trigger` / `showToast` / `window.dz.toast` with the **same** slots |
| **State** | Each toast’s life is in the DOM (`data-dz-remove-after`, enter/leave classes); no notification SPA store |
| **Morph** | **Never** morph the stack — afterbegin / replace only (flash surface) |
| **Not toast** | Persistent banners, form error regions, dialogs, drawers, onboarding nudges |

### Emission channels (one host)

| Channel | When |
|---------|------|
| `with_toast(...)` OOB | HTML response should also paint a toast |
| `HX-Trigger: showToast` | JSON / empty body mutations (CRUD headers) |
| Client `showToast` / `dz.toast` | Client-only paths (export fail, optimistic rollback) |

All three must render **indistinguishable** markup under the dual-lock contract.

### Timing (normative defaults)

| Case | Default |
|------|---------|
| info / success / warning | **8s** |
| error | **10s** (longer read; still dismissible) |
| Hover / focus in stack | **Pause** remaining timer (and any TTL progress) |
| Leave / resume | Continue with **remaining** time |
| Dismiss | Leave motion (~300ms), then remove |

Authors may override per toast via `data-dz-remove-after` / `duration`.

### Gallery

- Live demo uses an **overlay** frame (natural width), not the 64rem shell
  iframe — fixed corners must stay on-screen (stem: pragmatic-gallery-aesthetics).
- **Copy this** is product stack markup only; stage/fire buttons are gallery
  chrome, not the Hyperpart contract.

## Not this

- Alpine `x-for` notification arrays as source of truth.
- Embedding the stack inside a card, form, or wide scroll column “for demo.”
- Morphing `#dz-toast` on every swap.
- Cookie banners, consent, or marketing overlays dressed as toasts.
- Treating Penguin/shadcn toast as a style or Alpine target — **functions only**.

## Expressions

- Decision [0011](../docs/decisions/0011-toast-page-chrome.md)
- `site/agents/toast.md`, `contracts/toast.py`, `controllers/dz-toast.js`
- Dazzle: `with_toast`, `htmx_trigger_headers`, shell `#dz-toast`
