/**
 * Dazzle Site Page Script
 *
 * Handles theme toggling, Lucide icon initialization, and hash-based scrolling.
 * Section rendering is handled server-side by Jinja2 templates.
 */
(function () {
  "use strict";

  // ==========================================================================
  // Theme System (v0.16.0 - Issue #26)
  // ==========================================================================

  const STORAGE_KEY = "dz-theme-variant";
  const COOKIE_NAME = "dz_theme";
  // One year in seconds — theme preference is long-lived; we'd
  // rather respect a returning user's explicit choice than re-prompt
  // annually.
  const COOKIE_MAX_AGE = 60 * 60 * 24 * 365;
  const THEME_LIGHT = "light";
  const THEME_DARK = "dark";

  function getSystemPreference() {
    if (typeof window === "undefined") return THEME_LIGHT;
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    return mediaQuery.matches ? THEME_DARK : THEME_LIGHT;
  }

  function getStoredPreference() {
    if (typeof localStorage === "undefined") return null;
    return localStorage.getItem(STORAGE_KEY);
  }

  function storePreference(variant) {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(STORAGE_KEY, variant);
    }
    // Mirror the preference into a cookie so the server can emit the
    // correct `<html data-theme>` on first paint and the in-app
    // Alpine shell reads the same source. SameSite=Lax is the safe
    // default for a UI-preference cookie (sent on top-level
    // navigations, blocked on cross-site POSTs).
    if (typeof document !== "undefined") {
      document.cookie =
        COOKIE_NAME +
        "=" +
        variant +
        "; path=/; max-age=" +
        COOKIE_MAX_AGE +
        "; SameSite=Lax";
    }
  }

  function applyTheme(variant) {
    const root = document.documentElement;
    root.setAttribute("data-theme", variant);
    root.style.colorScheme = variant;
    root.classList.remove("dz-theme-light", "dz-theme-dark");
    root.classList.add("dz-theme-" + variant);
  }

  function initTheme() {
    const stored = getStoredPreference();
    const system = getSystemPreference();
    const variant = stored || system || THEME_LIGHT;
    applyTheme(variant);

    // Listen for system preference changes
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    mediaQuery.addEventListener("change", function (e) {
      if (!getStoredPreference()) {
        applyTheme(e.matches ? THEME_DARK : THEME_LIGHT);
      }
    });

    return variant;
  }

  function toggleTheme() {
    const current =
      document.documentElement.getAttribute("data-theme") || THEME_LIGHT;
    const newVariant = current === THEME_LIGHT ? THEME_DARK : THEME_LIGHT;
    applyTheme(newVariant);
    storePreference(newVariant);
    return newVariant;
  }

  // Initialize theme immediately (before DOMContentLoaded)
  initTheme();

  // ==========================================================================
  // DOM Ready: Toggle Button + Lucide Icons + Hash Scroll
  // ==========================================================================

  document.addEventListener("DOMContentLoaded", function () {
    // Set up theme toggle button
    const toggleBtn = document.getElementById("dz-theme-toggle");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", toggleTheme);
    }

    // Initialize Lucide icons
    if (typeof lucide !== "undefined") {
      lucide.createIcons();
    }

    // Scroll to hash fragment if present
    if (window.location.hash) {
      const target = document.getElementById(window.location.hash.slice(1));
      if (target) {
        target.scrollIntoView({ behavior: "smooth" });
      }
    }

    // ======================================================================
    // User Preferences API (v0.38.0)
    // ======================================================================

    var _prefQueue = {};
    var _prefTimer = null;

    function _flushPrefs() {
      var batch = _prefQueue;
      _prefQueue = {};
      _prefTimer = null;
      if (Object.keys(batch).length === 0) return;
      fetch("/auth/preferences", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferences: batch }),
      }).catch(function () {
        /* silent — prefs are best-effort */
      });
    }

    window.dzPrefs = {
      /** Set a preference (debounced 500ms batch save). */
      set: function (key, value) {
        _prefQueue[key] = String(value);
        if (_prefTimer) clearTimeout(_prefTimer);
        _prefTimer = setTimeout(_flushPrefs, 500);
      },
      /** Get a preference from the server-rendered initial state. */
      get: function (key, fallback) {
        var el = document.getElementById("dz-user-prefs");
        if (!el) return fallback;
        try {
          var prefs = JSON.parse(el.textContent || "{}");
          return prefs.hasOwnProperty(key) ? prefs[key] : fallback;
        } catch (e) {
          return fallback;
        }
      },
      /** Delete a preference. */
      del: function (key) {
        fetch("/auth/preferences/" + encodeURIComponent(key), {
          method: "DELETE",
        }).catch(function () {});
      },
    };
  });
})();
