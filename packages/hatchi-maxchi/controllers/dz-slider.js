/* HYPERPART: slider */
/*
 * dz-slider — live value readout for a native <input type="range">.
 *
 * Delegated from document; on `input` it writes the range's current value into
 * the `[data-dz-range-value]` readout within the SAME group, so N sliders on a
 * page stay independent (every query scoped to the input's own group — never a
 * global document.querySelector).
 *
 * Leftover honesty (cycle 2134): when the readout is an editable input
 * (no name — the range is the submitted value), leftover junk ("70abc",
 * "zzz") must not invent a range position. parseFloat("70abc") === 70 is
 * invalid — the range stays put and both controls fail custom validity
 * so submit cannot post the previous value as if the leftover were
 * accepted. Empty readout on blur restores from the range (empty is
 * not leftover junk). Valid numbers write the range; out-of-[min,max]
 * is invalid (do not invent by clamping). Blur normalizes the readout
 * to the range's value (after native step snap).
 *
 * Same class as colour leftover hex (2133) and money leftover junk (2121).
 *
 * Skips inputs already managed by a widget bridge (`[data-dz-widget]`) so it
 * never double-handles a host that wires its own range controller. It is the
 * canonical HM value controller: a host adopts it simply by dropping that
 * wrapper attribute.
 */
(function () {
  "use strict";

  function parts(el) {
    if (!el || !el.closest) return null;
    var group =
      el.closest(".dz-form-slider-group") || el.closest(".form-slider-group");
    if (
      !group &&
      el.matches &&
      el.matches('input[type="range"][data-dz-slider]')
    ) {
      group = el.parentElement;
    }
    if (!group) return null;
    if (group.closest && group.closest("[data-dz-widget]")) return null;
    var range = group.querySelector('input[type="range"][data-dz-slider]');
    var out = group.querySelector("[data-dz-range-value]");
    if (!range || !out) return null;
    return { group: group, range: range, out: out };
  }

  // The readout for a range input, or null if this input isn't ours to touch
  // (not a dz-slider, or already owned by a widget bridge). One guard, used by
  // the one-time mount sync.
  function readoutFor(input) {
    var p = parts(input);
    return p ? p.out : null;
  }

  function outGet(el) {
    if (!el) return "";
    return el.tagName === "INPUT" ? el.value : el.textContent || "";
  }

  function outSet(el, val) {
    if (!el) return;
    if (el.tagName === "INPUT") el.value = val;
    else el.textContent = val;
  }

  // kind: empty | partial | invalid | ok. parseFloat("70abc") === 70, so
  // leftover junk is invalid — not a silent 70. Out-of-[min,max] is
  // invalid (do not invent by clamping).
  function parseNumber(val, min, max, strict) {
    var raw = String(val == null ? "" : val).trim();
    if (!raw) return { kind: "empty" };
    if (raw === "-" || raw === "." || raw === "-.") {
      return strict ? { kind: "invalid" } : { kind: "partial" };
    }
    var trailingDot = raw.charAt(raw.length - 1) === ".";
    if (trailingDot && strict) return { kind: "invalid" };
    var body = trailingDot ? raw.slice(0, -1) : raw;
    if (!/^-?(?:\d+|\d*\.\d+)$/.test(body)) return { kind: "invalid" };
    var num = parseFloat(body);
    if (!isFinite(num)) return { kind: "invalid" };
    if (isFinite(min) && num < min) return { kind: "invalid" };
    if (isFinite(max) && num > max) return { kind: "invalid" };
    return { kind: "ok", value: num };
  }

  function syncValidity(p, parsed) {
    var msg =
      parsed.kind === "invalid" ? "Enter a number within the slider range" : "";
    if (p.out && p.out.setCustomValidity) p.out.setCustomValidity(msg);
    if (p.range && p.range.setCustomValidity) p.range.setCustomValidity(msg);
  }

  function applyFromRange(p) {
    if (!p.range || !p.out) return;
    outSet(p.out, p.range.value);
    syncValidity(p, { kind: "ok" });
  }

  function applyFromOut(p, normalize) {
    if (!p.out) return;
    var min = p.range ? parseFloat(p.range.min) : NaN;
    var max = p.range ? parseFloat(p.range.max) : NaN;
    var parsed = parseNumber(outGet(p.out), min, max, normalize);
    if (parsed.kind === "ok") {
      if (p.range) p.range.value = String(parsed.value);
      if (normalize && p.range) outSet(p.out, p.range.value);
    }
    // leftover junk / empty: do not write the range (never invent)
    syncValidity(p, parsed);
  }

  document.addEventListener("input", function (evt) {
    var p = parts(evt.target);
    if (!p) return;
    if (evt.target === p.range) {
      applyFromRange(p);
      return;
    }
    if (p.out && evt.target === p.out && p.out.tagName === "INPUT") {
      applyFromOut(p, false);
    }
  });

  document.addEventListener(
    "blur",
    function (evt) {
      var p = parts(evt.target);
      if (!p || !p.out || evt.target !== p.out || p.out.tagName !== "INPUT") {
        return;
      }
      var min = p.range ? parseFloat(p.range.min) : NaN;
      var max = p.range ? parseFloat(p.range.max) : NaN;
      var parsed = parseNumber(outGet(p.out), min, max, true);
      if (parsed.kind === "ok") {
        applyFromOut(p, true);
      } else if (parsed.kind === "empty") {
        applyFromRange(p);
      } else {
        // leftover junk stays visible — must not vanish / revert
        syncValidity(p, parsed);
      }
    },
    true, // blur doesn't bubble — capture
  );

  // One-time sync so a hard-coded `value=` matches its readout before the first
  // input (copy-paste robustness). Respects the same guard, so it never touches
  // a widget-bridge-managed range.
  function sync() {
    var inputs = document.querySelectorAll(
      'input[type="range"][data-dz-slider]',
    );
    for (var i = 0; i < inputs.length; i++) {
      var out = readoutFor(inputs[i]);
      if (out) outSet(out, inputs[i].value);
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", sync);
  } else {
    sync();
  }
})();
