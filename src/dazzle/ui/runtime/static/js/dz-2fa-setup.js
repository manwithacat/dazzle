/* dz-2fa-setup.js — client behavior for the typed 2FA setup view.
 *
 * Extracted from src/dazzle_ui/templates/site/auth/2fa_setup.html as
 * part of the Jinja2 retirement Phase 1.D.2 (v0.67.37). Same DOM
 * contract as the legacy template: targets the same element IDs and
 * follows the same fetch-driven state machine for TOTP setup, email-
 * OTP enable, and recovery-code display.
 *
 * DOM contract (element IDs the script reads):
 *   #dz-auth-error          — error banner (.hidden by default)
 *   #dz-auth-success        — success banner (.hidden by default)
 *   #dz-setup-totp          — "Generate QR Code" trigger button
 *   #dz-qr-container        — QR image landing zone (and starting button host)
 *   #dz-totp-verify         — wrapper around the TOTP verify form (.hidden by default)
 *   #dz-totp-secret         — code element receiving the manual-entry secret
 *   #dz-totp-form           — form posting the user-typed TOTP code
 *   #totp_code              — numeric input inside dz-totp-form
 *   #dz-enable-email-otp    — "Enable Email OTP" button
 *   #dz-recovery-section    — wrapper around the recovery-codes grid (.hidden)
 *   #dz-recovery-codes      — grid container for the issued recovery codes
 *
 * No build step. Plain ES2015+ wrapped in an IIFE, same as the legacy
 * inline block. Auth/CSRF flows assume `/auth/` is in the CSRF
 * exempt_path_prefixes (verified by test_auth_2fa_endpoints_are_csrf_exempt).
 */
(function () {
  const errorDiv = document.getElementById("dz-auth-error");
  const successDiv = document.getElementById("dz-auth-success");
  const RECOVERY_CODE_CLASSES = "dz-auth-recovery-pill";

  function showError(msg) {
    if (!errorDiv) return;
    errorDiv.textContent = msg;
    errorDiv.classList.remove("hidden");
    if (successDiv) successDiv.classList.add("hidden");
  }

  function showSuccess(msg) {
    if (!successDiv) return;
    successDiv.textContent = msg;
    successDiv.classList.remove("hidden");
    if (errorDiv) errorDiv.classList.add("hidden");
  }

  function showRecoveryCodes(codes) {
    const container = document.getElementById("dz-recovery-codes");
    if (!container) return;
    container.replaceChildren();
    codes.forEach(function (code) {
      const pill = document.createElement("div");
      pill.className = RECOVERY_CODE_CLASSES;
      pill.textContent = code;
      container.appendChild(pill);
    });
    const section = document.getElementById("dz-recovery-section");
    if (section) section.classList.remove("hidden");
  }

  const setupBtn = document.getElementById("dz-setup-totp");
  if (setupBtn) {
    setupBtn.addEventListener("click", async function () {
      try {
        const resp = await fetch("/auth/2fa/setup/totp", { method: "POST" });
        const data = await resp.json();
        if (!resp.ok) {
          showError(data.detail || "Setup failed");
          return;
        }
        const secretEl = document.getElementById("dz-totp-secret");
        if (secretEl) secretEl.textContent = data.secret;
        const qrContainer = document.getElementById("dz-qr-container");
        if (qrContainer) {
          qrContainer.replaceChildren();
          const img = document.createElement("img");
          img.src = data.qr_data_uri;
          img.alt = "QR Code";
          img.width = 200;
          img.height = 200;
          qrContainer.appendChild(img);
        }
        const verifyBlock = document.getElementById("dz-totp-verify");
        if (verifyBlock) verifyBlock.classList.remove("hidden");
      } catch (err) {
        showError("Network error");
      }
    });
  }

  const totpForm = document.getElementById("dz-totp-form");
  if (totpForm) {
    totpForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      const codeEl = document.getElementById("totp_code");
      const code = codeEl ? codeEl.value : "";
      try {
        const resp = await fetch("/auth/2fa/verify/totp", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code: code }),
        });
        const data = await resp.json();
        if (!resp.ok) {
          showError(data.detail || "Invalid code");
          return;
        }
        showSuccess("TOTP enabled successfully!");
        if (data.recovery_codes) {
          showRecoveryCodes(data.recovery_codes);
        }
      } catch (err) {
        showError("Network error");
      }
    });
  }

  const enableEmailBtn = document.getElementById("dz-enable-email-otp");
  if (enableEmailBtn) {
    enableEmailBtn.addEventListener("click", async function () {
      try {
        const resp = await fetch("/auth/2fa/setup/email-otp", {
          method: "POST",
        });
        const data = await resp.json();
        if (!resp.ok) {
          showError(data.detail || "Setup failed");
          return;
        }
        showSuccess("Email OTP enabled!");
        this.textContent = "Enabled";
        this.disabled = true;
      } catch (err) {
        showError("Network error");
      }
    });
  }
})();
