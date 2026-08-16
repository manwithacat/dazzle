/* HYPERPART: field */
/*
 * dz-number — native number ↔ editable companion.
 *
 * Contract:
 *   - root: `[data-dz-number-group]` (gallery also accepts `[data-number-group]`)
 *   - native: `input[type=number]` — this is the submitted value
 *             (the companion has no name)
 *   - out: `[data-dz-number-value]` — editable text (no name)
 *
 * Leftover honesty (cycle 2149): leftover junk must not invent a
 * number. parseFloat("12abc") === 12 / "zzz" / "1e2" is invalid — the
 * native stays put and both controls fail custom validity so submit
 * cannot post the previous number as if the leftover were accepted.
 * Empty companion on blur restores from the native (empty is not
 * leftover junk). Valid decimals write the native; out-of-[min,max]
 * is invalid (do not invent by clamping). Blur normalizes the
 * companion to the native value (after native step snap).
 *
 * Same class as slider leftover readout (2134), date leftover ISO
 * (2145), and money leftover junk (2121).
 */
(function () {
  "use strict";

  function rootOf(el) {
    if (!el || !el.closest) return null;
    return (
      el.closest("[data-dz-number-group]") || el.closest("[data-number-group]")
    );
  }

  function parts(el) {
    var group = rootOf(el);
    if (!group) return null;
    return {
      group: group,
      native: group.querySelector('input[type="number"]'),
      out: group.querySelector("[data-dz-number-value]"),
    };
  }

  function leftoverMessage() {
    return "Enter a number";
  }

  // kind: empty | partial | invalid | ok. parseFloat("12abc") === 12, so
  // leftover junk is invalid — not a silent 12. Out-of-[min,max] is
  // invalid (do not invent by clamping). Scientific leftover ("1e2")
  // is invalid — the companion is decimal text, not JS parseFloat.
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

  function mark(el, bad, msg) {
    if (!el) return;
    if (el.setCustomValidity) el.setCustomValidity(bad ? msg : "");
    if (bad) el.setAttribute("aria-invalid", "true");
    else el.removeAttribute("aria-invalid");
  }

  function syncValidity(p, parsed) {
    var msg = parsed.kind === "invalid" ? leftoverMessage() : "";
    mark(p.out, parsed.kind === "invalid", msg);
    mark(p.native, parsed.kind === "invalid", msg);
  }

  function applyFromNative(p) {
    if (!p.native || !p.out) return;
    p.out.value = p.native.value || "";
    syncValidity(p, { kind: "ok" });
  }

  function applyFromOut(p, normalize) {
    if (!p.out) return;
    var min = p.native ? parseFloat(p.native.min) : NaN;
    var max = p.native ? parseFloat(p.native.max) : NaN;
    var parsed = parseNumber(p.out.value, min, max, normalize);
    if (parsed.kind === "ok") {
      if (p.native) p.native.value = String(parsed.value);
      if (normalize && p.native)
        p.out.value = p.native.value || String(parsed.value);
    }
    // leftover junk / empty: do not write the native (never invent)
    syncValidity(p, parsed);
    return parsed;
  }

  document.addEventListener("input", function (evt) {
    var p = parts(evt.target);
    if (!p) return;
    if (evt.target === p.native) {
      applyFromNative(p);
      return;
    }
    if (evt.target === p.out) {
      applyFromOut(p, false);
    }
  });

  document.addEventListener("change", function (evt) {
    var p = parts(evt.target);
    if (!p) return;
    if (evt.target === p.native) applyFromNative(p);
  });

  document.addEventListener(
    "blur",
    function (evt) {
      var p = parts(evt.target);
      if (!p || !p.out || evt.target !== p.out) return;
      var min = p.native ? parseFloat(p.native.min) : NaN;
      var max = p.native ? parseFloat(p.native.max) : NaN;
      var parsed = parseNumber(p.out.value, min, max, true);
      if (parsed.kind === "ok") {
        applyFromOut(p, true);
      } else if (parsed.kind === "empty") {
        applyFromNative(p);
      } else {
        // leftover junk stays visible — must not vanish / revert
        applyFromOut(p, false);
      }
    },
    true,
  );
})();
