/** @ts-check */
/**
 * dz-cue.js — opt-in UI cues (sound) for Hyperparts.
 *
 * Parallel to Dazzle's haptic gate (`meta[name=dz-haptic]` / window.dzHaptic):
 * a **product must opt in** before any sound plays. Controllers call
 * `window.dzCue.play(kind)` and get a silent no-op when disabled.
 *
 * Enable when either is true:
 *   - `<meta name="dz-sound" content="on">` (page-wide; emit from dazzle.toml later)
 *   - any host with `data-dz-cue-sound="on"` present in the document
 *
 * Never default-on. Respects `prefers-reduced-motion: reduce` (no auto cues).
 * Uses Web Audio oscillators — **no CDN ding**, no network. Failures are
 * silent so emit paths never block.
 *
 * Kinds: "tap" | "success" | "warning" | "error" | "info"
 *
 * Reuse: toast enter, confirm open, command palette open, etc.
 */

(function () {
  "use strict";

  function reducedMotion() {
    return (
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }

  function metaEnabled() {
    var meta = document.querySelector('meta[name="dz-sound"]');
    return !!(meta && meta.getAttribute("content") === "on");
  }

  function hostEnabled() {
    return !!document.querySelector('[data-dz-cue-sound="on"]');
  }

  function isEnabled() {
    if (reducedMotion()) return false;
    return metaEnabled() || hostEnabled();
  }

  /** @type {AudioContext | null} */
  var sharedCtx = null;

  function getCtx() {
    if (sharedCtx) return sharedCtx;
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    try {
      sharedCtx = new AC();
    } catch (_e) {
      return null;
    }
    return sharedCtx;
  }

  /**
   * Short oscillator blip — no external asset.
   * @param {number} freqHz
   * @param {number} durationSec
   * @param {number} [gain]
   */
  function blip(freqHz, durationSec, gain) {
    if (!isEnabled()) return false;
    var ctx = getCtx();
    if (!ctx) return false;
    try {
      if (ctx.state === "suspended" && typeof ctx.resume === "function") {
        ctx.resume();
      }
      var o = ctx.createOscillator();
      var g = ctx.createGain();
      o.type = "sine";
      o.frequency.value = freqHz;
      g.gain.value = gain == null ? 0.04 : gain;
      o.connect(g);
      g.connect(ctx.destination);
      var t0 = ctx.currentTime;
      g.gain.setValueAtTime(g.gain.value, t0);
      g.gain.exponentialRampToValueAtTime(0.001, t0 + durationSec);
      o.start(t0);
      o.stop(t0 + durationSec + 0.01);
      return true;
    } catch (_e) {
      return false;
    }
  }

  var KINDS = {
    tap: function () {
      return blip(660, 0.06);
    },
    info: function () {
      return blip(720, 0.07);
    },
    success: function () {
      return blip(880, 0.08);
    },
    warning: function () {
      return blip(520, 0.1);
    },
    error: function () {
      blip(320, 0.05);
      setTimeout(function () {
        blip(280, 0.08);
      }, 70);
      return true;
    },
  };

  /**
   * @param {string} [kind]
   * @returns {boolean}
   */
  function play(kind) {
    var k = kind || "tap";
    var fn = KINDS[k] || KINDS.tap;
    try {
      return !!fn();
    } catch (_e) {
      return false;
    }
  }

  window.dzCue = {
    get enabled() {
      return isEnabled();
    },
    play: play,
    /** @deprecated use play */
    sound: play,
  };
})();
