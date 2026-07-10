# Two-factor panel (`two-factor`)

The 2FA enrolment/settings card: QR + manual secret, the big-digit code input, recovery-code grid, and factor status rows.

## Partial (copy-paste; the live demo renders this exact string)

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

## Guidance (prose; HTML from the registry notes field)

In Dazzle the enrolment flow is driven by ID-anchored vanilla JS (<code>dz-2fa-setup.js</code>/<code>-settings.js</code> against JSON endpoints): the QR image lands CLASSLESS in <code>dz-auth-qr-container</code> (the container styles it), recovery pills and status rows are JS-created (shown here with status badges; the Dazzle settings JS renders dz-button action controls in that slot), and the error/success alerts toggle via the native <code>hidden</code> attribute on stable ids. The code input reserves letter-spacing for six digits. Wrap full pages in <code>dz-auth-page</code> for the centered layout.
