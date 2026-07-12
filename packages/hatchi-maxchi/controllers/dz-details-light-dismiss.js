/* HYPERPART: menu */
/* HYPERPART: popover */
/*
 * dz-details-light-dismiss — configurable light-dismiss for overlay <details>.
 *
 * Stem: overlay-light-dismiss (spatial vs temporal abandon).
 *
 * Targets (class defaults when data-dz-dismiss is omitted):
 *   details.dz-menu / details.menu
 *   details.dz-popover / details.popover
 *
 * Per-instance configuration (no CPU when closed — one timer max per open root):
 *
 *   data-dz-dismiss="esc outside"     spatial: Escape + pointer outside (default)
 *   data-dz-dismiss="outside"         spatial outside only (touch-first)
 *   data-dz-dismiss="esc"             Escape only (discouraged alone)
 *   data-dz-dismiss="none"            opt out — native toggle only
 *   data-dz-dismiss-ms="4000"         temporal: auto-close after ms (while open)
 *                                     implies timeout; keeps default spatial unless
 *                                     data-dz-dismiss="none"
 *
 *   Tokens may combine: data-dz-dismiss="esc outside" data-dz-dismiss-ms="5000"
 *
 * Interaction inside an open panel resets the timeout (user is engaged).
 * Does NOT own menubar / navigation-menu (exclusive multi-peer controllers)
 * or accordion / tree (in-flow structure — leave dismiss off / none).
 */
(function () {
  "use strict";

  var ROOT =
    "details.dz-menu, details.menu, details.dz-popover, details.popover";

  /** @type {WeakMap<Element, number>} */
  var timers = new WeakMap();

  function openRoots() {
    return document.querySelectorAll(ROOT);
  }

  /** Gallery unprefixes data-dz-* → data-* on site/; apps keep data-dz-*. */
  function attr(el, dzName, bareName) {
    var v = el.getAttribute(dzName);
    if (v != null) return v;
    return el.getAttribute(bareName);
  }

  function parseMs(el) {
    var raw = attr(el, "data-dz-dismiss-ms", "data-dismiss-ms");
    if (raw == null || raw === "") return 0;
    var n = parseInt(raw, 10);
    return n > 0 && n === n ? n : 0; // NaN → 0
  }

  /**
   * @returns {{ esc: boolean, outside: boolean, ms: number }}
   */
  function policy(el) {
    var ms = parseMs(el);
    var raw = attr(el, "data-dz-dismiss", "data-dismiss");
    if (raw != null) {
      raw = String(raw).trim().toLowerCase();
      if (raw === "none" || raw === "off" || raw === "false") {
        return { esc: false, outside: false, ms: 0 };
      }
      var tokens = raw.split(/\s+/).filter(Boolean);
      function has(t) {
        return tokens.indexOf(t) >= 0;
      }
      // If author only set tokens like "timeout", treat as default spatial + ms
      var esc = has("esc") || has("escape");
      var outside = has("outside") || has("pointer");
      var onlyTimeout =
        tokens.length === 0 ||
        (tokens.length === 1 && (has("timeout") || has("timer")));
      if (onlyTimeout || (!esc && !outside && !has("none"))) {
        if (!esc && !outside) {
          esc = true;
          outside = true;
        }
      }
      if (has("timeout") || has("timer")) {
        if (ms <= 0) ms = 5000; // explicit timeout token without ms
      }
      return { esc: esc, outside: outside, ms: ms };
    }
    // Class default for known overlay roots: spatial only
    return { esc: true, outside: true, ms: ms };
  }

  function clearTimer(el) {
    var id = timers.get(el);
    if (id != null) {
      clearTimeout(id);
      timers.delete(el);
    }
  }

  function armTimer(el) {
    clearTimer(el);
    var p = policy(el);
    if (!el.open || p.ms <= 0) return;
    var id = setTimeout(function () {
      timers.delete(el);
      if (el.open) el.open = false;
    }, p.ms);
    timers.set(el, id);
  }

  function closeEl(el) {
    clearTimer(el);
    if (el.open) el.open = false;
  }

  // Spatial: Escape
  document.addEventListener(
    "keydown",
    function (evt) {
      if (evt.key !== "Escape") return;
      var nodes = openRoots();
      for (var i = 0; i < nodes.length; i++) {
        var d = nodes[i];
        if (!d.open) continue;
        if (policy(d).esc) closeEl(d);
      }
    },
    true,
  );

  // Spatial: outside pointer
  document.addEventListener(
    "pointerdown",
    function (evt) {
      var t = evt.target;
      if (!t) return;
      var nodes = openRoots();
      for (var i = 0; i < nodes.length; i++) {
        var d = nodes[i];
        if (!d.open) continue;
        if (!policy(d).outside) continue;
        if (d.contains(t)) {
          // Temporal: activity inside resets auto-close clock
          armTimer(d);
          continue;
        }
        closeEl(d);
      }
    },
    true,
  );

  // Temporal: arm/clear on open/close; no polling
  document.addEventListener(
    "toggle",
    function (evt) {
      var d = evt.target;
      if (!d || !d.matches || !d.matches(ROOT)) return;
      if (d.open) armTimer(d);
      else clearTimer(d);
    },
    true,
  );

  // Keyboard/pointer activity inside panel resets timeout (capture)
  document.addEventListener(
    "keydown",
    function (evt) {
      var t = evt.target;
      if (!t || !t.closest) return;
      var d = t.closest(ROOT);
      if (d && d.open && policy(d).ms > 0) armTimer(d);
    },
    true,
  );
})();
