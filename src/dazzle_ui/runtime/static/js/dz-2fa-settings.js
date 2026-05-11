/* dz-2fa-settings.js — client behavior for the typed 2FA settings view.
 *
 * Extracted from src/dazzle_ui/templates/site/auth/2fa_settings.html as
 * part of the Jinja2 retirement Phase 1.D.2 (v0.67.37). Same DOM
 * contract as the legacy template: targets the same element IDs and
 * follows the same fetch-driven status-and-controls flow for
 * enable/disable per factor + recovery-code regeneration.
 *
 * DOM contract:
 *   #dz-auth-error    — error banner (.hidden by default)
 *   #dz-auth-success  — success banner (.hidden by default)
 *   #dz-status        — container the script fills with one row per factor
 */
(function () {
  const errorDiv = document.getElementById("dz-auth-error");
  const successDiv = document.getElementById("dz-auth-success");
  const statusDiv = document.getElementById("dz-status");

  const ROW_CLASSES = "dz-auth-status-row";
  const ROW_CLASSES_LAST = "dz-auth-status-row is-last";
  const LABEL_CLASSES = "dz-auth-status-label";
  const BTN_PRIMARY = "dz-button dz-button-primary dz-button-sm";
  const BTN_DESTRUCTIVE = "dz-button dz-button-destructive dz-button-sm";
  const BTN_OUTLINE = "dz-button dz-button-outline dz-button-sm";

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

  function makeRow(rowClasses, labelText, button) {
    const row = document.createElement("div");
    row.className = rowClasses;
    const label = document.createElement("div");
    label.className = LABEL_CLASSES;
    label.textContent = labelText;
    row.appendChild(label);
    row.appendChild(button);
    return row;
  }

  async function loadStatus() {
    try {
      const resp = await fetch("/auth/2fa/status");
      const data = await resp.json();
      if (!resp.ok) {
        showError("Failed to load status");
        return;
      }
      renderStatus(data);
    } catch (err) {
      showError("Network error");
    }
  }

  function renderStatus(data) {
    if (!statusDiv) return;
    statusDiv.replaceChildren();

    // TOTP
    const totpBtn = document.createElement("button");
    if (data.totp_enabled) {
      totpBtn.textContent = "Disable";
      totpBtn.className = BTN_DESTRUCTIVE;
      totpBtn.addEventListener("click", async function () {
        const resp = await fetch("/auth/2fa/totp", { method: "DELETE" });
        if (resp.ok) {
          showSuccess("TOTP disabled");
          loadStatus();
        } else {
          showError("Failed to disable TOTP");
        }
      });
    } else {
      totpBtn.textContent = "Set Up";
      totpBtn.className = BTN_PRIMARY;
      totpBtn.addEventListener("click", function () {
        window.location.href = "/2fa/setup";
      });
    }
    statusDiv.appendChild(
      makeRow(ROW_CLASSES, "Authenticator App (TOTP)", totpBtn),
    );

    // Email OTP
    const emailBtn = document.createElement("button");
    if (data.email_otp_enabled) {
      emailBtn.textContent = "Disable";
      emailBtn.className = BTN_DESTRUCTIVE;
      emailBtn.addEventListener("click", async function () {
        const resp = await fetch("/auth/2fa/email-otp", { method: "DELETE" });
        if (resp.ok) {
          showSuccess("Email OTP disabled");
          loadStatus();
        } else {
          showError("Failed to disable email OTP");
        }
      });
    } else {
      emailBtn.textContent = "Enable";
      emailBtn.className = BTN_PRIMARY;
      emailBtn.addEventListener("click", async function () {
        const resp = await fetch("/auth/2fa/setup/email-otp", {
          method: "POST",
        });
        if (resp.ok) {
          showSuccess("Email OTP enabled");
          loadStatus();
        } else {
          showError("Failed to enable email OTP");
        }
      });
    }
    statusDiv.appendChild(makeRow(ROW_CLASSES, "Email OTP", emailBtn));

    // Recovery codes
    const recoveryBtn = document.createElement("button");
    recoveryBtn.textContent = "Regenerate";
    recoveryBtn.className = BTN_OUTLINE;
    recoveryBtn.addEventListener("click", async function () {
      const resp = await fetch("/auth/2fa/recovery/regenerate", {
        method: "POST",
      });
      const rdata = await resp.json();
      if (resp.ok) {
        showSuccess("New recovery codes generated");
        // eslint-disable-next-line no-alert -- intentional: codes must be visible immediately
        alert("Save these codes:\n\n" + rdata.recovery_codes.join("\n"));
        loadStatus();
      } else {
        showError("Failed to regenerate");
      }
    });
    const remaining = data.recovery_codes_remaining || 0;
    statusDiv.appendChild(
      makeRow(
        ROW_CLASSES_LAST,
        "Recovery Codes (" + remaining + " remaining)",
        recoveryBtn,
      ),
    );
  }

  loadStatus();
})();
