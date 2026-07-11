# Two-factor panel (`two-factor`)

The 2FA enrolment/settings card: QR + manual secret, the big-digit code input, recovery-code grid, and factor status rows.

> **Layer:** L2 host · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="auth-card hm-measure">
  <h1 class="auth-card-title">Set Up 2FA</h1>
  <p class="auth-card-subtitle">Aurora Ops</p>
  <h2 class="auth-section-title">Authenticator App</h2>
  <p class="auth-section-body">Scan this QR code with your authenticator app.</p>
  <div class="auth-qr-container"><button class="button" data-variant="outline">Generate QR Code</button></div>
  <p class="auth-section-body">Or enter the secret manually: <code class="auth-secret-inline">JBSW Y3DP EHPK 3PXP</code></p>
  <form class="auth-form">
    <div class="auth-field">
      <label for="hm-2fa-code" class="auth-label">Enter code from app</label>
      <input type="text" id="hm-2fa-code" inputmode="numeric" pattern="[0-9]*" maxlength="6" placeholder="000000" class="auth-input-code">
    </div>
    <button type="submit" class="button auth-submit" data-variant="primary">Verify and Enable</button>
  </form>
  <hr class="auth-hr">
  <div class="auth-recovery-alert" role="alert">
    <h3 class="auth-recovery-alert-title">Save Your Recovery Codes</h3>
    <p class="auth-recovery-alert-body">Store these codes in a safe place. Each code can only be used once.</p>
  </div>
  <div class="auth-recovery-grid"><span class="auth-recovery-pill">QK2M-8Y1D</span><span class="auth-recovery-pill">HW7C-04RA</span><span class="auth-recovery-pill">ZX3N-55PT</span><span class="auth-recovery-pill">MB9E-71LQ</span></div>
  <div class="auth-status-row">
    <div class="auth-status-label">Authenticator app</div>
    <span class="badge" data-tone="success">Enabled</span>
  </div>
  <div class="auth-status-row is-last">
    <div class="auth-status-label">Email codes</div>
    <span class="badge">Off</span>
  </div>
  <a href="#" class="auth-back-link">Back to App</a>
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

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- no Server exchange on this part — pure presentation or client chrome
- no typed contracts/ module yet — the partial is the surface of record

## DOM contract

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

In Dazzle the enrolment flow is driven by ID-anchored vanilla JS (dz-2fa-setup.js/-settings.js against JSON endpoints): the QR image lands CLASSLESS in dz-auth-qr-container (the container styles it), recovery pills and status rows are JS-created (shown here with status badges; the Dazzle settings JS renders dz-button action controls in that slot), and the error/success alerts toggle via the native hidden attribute on stable ids. The code input reserves letter-spacing for six digits. Wrap full pages in dz-auth-page for the centered layout.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
