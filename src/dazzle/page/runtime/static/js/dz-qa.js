/**
 * dz-qa.js — QA persona magic-link login (#1553, dev-only).
 *
 * Delegated document-level controller (the HM idiom): one click
 * listener keys off `[data-qa-login-persona]`, POSTs the persona id
 * to /qa/magic-link, and follows the returned URL. Replaces the
 * deprecated inline <script> the landing-page panel used to carry
 * (CSP-friendly; markup stays server-owned).
 *
 * Contract with `_render_qa_personas_html` (site_routes.py):
 *   - buttons carry data-qa-login-persona="<persona id>"
 *   - POST /qa/magic-link {persona_id} → {url}
 *   - button disables while in flight; error re-enables with a
 *     transient message, then restores the label.
 */
(function () {
  "use strict";

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-qa-login-persona]");
    if (!btn || btn.disabled) return;
    var personaId = btn.getAttribute("data-qa-login-persona");
    var originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Logging in...";
    fetch("/qa/magic-link", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ persona_id: personaId }),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        if (data.url) {
          window.location.href = data.url;
        } else {
          throw new Error("No URL in response");
        }
      })
      .catch(function (err) {
        btn.disabled = false;
        btn.textContent = "Error — try again";
        setTimeout(function () {
          btn.textContent = originalText;
        }, 2000);
        console.error("QA magic link failed:", err);
      });
  });
})();
