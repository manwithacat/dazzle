/**
 * Dazzle consent banner (v0.61.0 Phase 2).
 *
 * Handles:
 *   - Accept all / Reject non-essential / Customise / Save
 *   - Focus trap while the banner is visible
 *   - Keyboard navigation (Tab, Shift+Tab, Esc)
 *   - Consent Mode v2 update signalling (window.gtag when present)
 *   - Reopen-via-footer ("Manage cookies" link)
 *
 * The banner posts choices to POST /dz/consent. The server sets the cookie
 * and returns 204. On success the banner is dismissed and the page reloads
 * so scripts gated by consent can run.
 */
(function () {
  "use strict";

  const BANNER_ID = "dz-consent-banner";
  const CONSENT_ENDPOINT = "/dz/consent";
  const REOPEN_ENDPOINT = "/dz/consent/banner";

  function $(id) {
    return document.getElementById(id);
  }

  function panel(banner, name) {
    return banner.querySelector(`[data-consent-panel="${name}"]`);
  }

  function signalConsentModeUpdate(categories) {
    // Emit gtag consent update. If gtag isn't loaded (e.g. no GTM), the
    // push on dataLayer still lands for later consumers.
    const signal = {
      analytics_storage: categories.analytics ? "granted" : "denied",
      ad_storage: categories.advertising ? "granted" : "denied",
      ad_user_data: categories.advertising ? "granted" : "denied",
      ad_personalization:
        categories.advertising && categories.personalization
          ? "granted"
          : "denied",
      functionality_storage: "granted",
      personalization_storage: categories.personalization
        ? "granted"
        : "denied",
      security_storage: "granted",
    };
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({ event: "dz_consent_update", ...signal });
    if (typeof window.gtag === "function") {
      window.gtag("consent", "update", signal);
    }
  }

  function postChoice(categories) {
    const body = JSON.stringify(categories);
    return fetch(CONSENT_ENDPOINT, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body,
    });
  }

  function getCustomizeCategories(banner) {
    const inputs = banner.querySelectorAll(
      'input[type="checkbox"][data-dz-consent-category]',
    );
    const out = {
      analytics: false,
      advertising: false,
      personalization: false,
      functional: true, // always on
    };
    inputs.forEach((input) => {
      const key = input.getAttribute("data-dz-consent-category");
      out[key] = input.checked || key === "functional";
    });
    return out;
  }

  function showPanel(banner, which) {
    const summary = panel(banner, "summary");
    const customize = panel(banner, "customize");
    if (!summary || !customize) return;
    if (which === "customize") {
      summary.setAttribute("hidden", "");
      customize.removeAttribute("hidden");
      const first = customize.querySelector(
        'input[type="checkbox"]:not([disabled])',
      );
      if (first) first.focus();
    } else {
      customize.setAttribute("hidden", "");
      summary.removeAttribute("hidden");
      const firstBtn = summary.querySelector("button");
      if (firstBtn) firstBtn.focus();
    }
  }

  function hideBanner(banner) {
    banner.setAttribute("hidden", "");
    banner.setAttribute("aria-hidden", "true");
    banner.style.display = "none";
  }

  function showBanner(banner) {
    banner.removeAttribute("hidden");
    banner.removeAttribute("aria-hidden");
    banner.style.display = "";
    showPanel(banner, "summary");
  }

  function trapFocus(banner) {
    banner.addEventListener("keydown", (evt) => {
      if (evt.key !== "Tab") return;
      const focusables = banner.querySelectorAll(
        "button, [href], input:not([disabled]), select:not([disabled])",
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (evt.shiftKey && document.activeElement === first) {
        last.focus();
        evt.preventDefault();
      } else if (!evt.shiftKey && document.activeElement === last) {
        first.focus();
        evt.preventDefault();
      }
    });
  }

  async function commit(banner, categories) {
    try {
      const response = await postChoice(categories);
      if (!response.ok) {
        console.error("[dz-consent] POST /dz/consent failed:", response.status);
        return;
      }
      signalConsentModeUpdate(categories);
      hideBanner(banner);
      window.location.reload();
    } catch (err) {
      console.error("[dz-consent] network error:", err);
    }
  }

  function attach(banner) {
    trapFocus(banner);

    banner.addEventListener("click", (evt) => {
      const trigger = evt.target.closest("[data-dz-consent-action]");
      if (!trigger) return;
      evt.preventDefault();
      const action = trigger.getAttribute("data-dz-consent-action");
      if (action === "accept-all") {
        commit(banner, {
          analytics: true,
          advertising: true,
          personalization: true,
          functional: true,
        });
      } else if (action === "reject-all") {
        commit(banner, {
          analytics: false,
          advertising: false,
          personalization: false,
          functional: true,
        });
      } else if (action === "customize") {
        showPanel(banner, "customize");
      } else if (action === "back") {
        showPanel(banner, "summary");
      } else if (action === "save") {
        commit(banner, getCustomizeCategories(banner));
      }
    });
  }

  /**
   * Parse server-sent banner HTML into a single detached element.
   * Uses DOMParser so scripts don't execute and inline handlers are ignored.
   */
  function parseBannerFragment(html) {
    const doc = new DOMParser().parseFromString(html, "text/html");
    return doc.getElementById(BANNER_ID);
  }

  function init() {
    const banner = $(BANNER_ID);
    if (banner) attach(banner);

    // Expose reopen hook for footer "Manage cookies" link:
    //   <a href="#" onclick="dzConsent.reopen(); return false;">
    window.dzConsent = {
      reopen: function () {
        const existing = $(BANNER_ID);
        if (existing) {
          showBanner(existing);
          return;
        }
        fetch(REOPEN_ENDPOINT, { credentials: "same-origin" })
          .then((r) => (r.ok ? r.text() : ""))
          .then((html) => {
            if (!html) return;
            const parsed = parseBannerFragment(html);
            if (parsed) {
              document.body.appendChild(parsed);
              attach(parsed);
              showBanner(parsed);
            }
          });
      },
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
