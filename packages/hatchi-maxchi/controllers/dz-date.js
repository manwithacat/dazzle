/* HYPERPART: field */
/*
 * dz-date — native date ↔ ISO companion.
 *
 * Contract:
 *   - root: `[data-dz-date-group]` (gallery also accepts `[data-date-group]`)
 *   - native: `input[type=date]` — this is the submitted value
 *             (the companion has no name)
 *   - iso: `[data-dz-date-iso]` — editable text (no name)
 *
 * Leftover honesty (cycle 2145): leftover ISO junk must not invent a
 * date. parseISO("2026-06-01zzz") / "zzz" / "June 1" is invalid — the
 * native stays put and both controls fail custom validity so submit
 * cannot post the previous date as if the leftover were accepted.
 * Empty ISO on blur restores from the native (empty is not leftover
 * junk). Valid YYYY-MM-DD (real calendar day) writes the native;
 * blur normalizes to the native value. Feb 31 / leftover suffix are
 * invalid.
 *
 * Same class as date-range leftover ISO (2139) and time leftover ISO
 * (2144). Server SSRs the initial ISO, so no init pass.
 */
(function () {
  "use strict";

  function rootOf(el) {
    if (!el || !el.closest) return null;
    return (
      el.closest("[data-dz-date-group]") || el.closest("[data-date-group]")
    );
  }

  function parts(el) {
    var group = rootOf(el);
    if (!group) return null;
    return {
      group: group,
      native: group.querySelector('input[type="date"]'),
      iso: group.querySelector("[data-dz-date-iso]"),
    };
  }

  function leftoverMessage() {
    return "Enter a date like 2026-06-01";
  }

  function parseISO(raw) {
    var s = String(raw == null ? "" : raw).trim();
    if (!s) return { kind: "empty" };
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
    if (!m) return { kind: "invalid" };
    var y = +m[1];
    var mo = +m[2];
    var d = +m[3];
    var dt = new Date(Date.UTC(y, mo - 1, d));
    if (
      dt.getUTCFullYear() !== y ||
      dt.getUTCMonth() !== mo - 1 ||
      dt.getUTCDate() !== d
    ) {
      return { kind: "invalid" };
    }
    return { kind: "ok", value: s };
  }

  function mark(el, bad, msg) {
    if (!el) return;
    if (el.setCustomValidity) el.setCustomValidity(bad ? msg : "");
    if (bad) el.setAttribute("aria-invalid", "true");
    else el.removeAttribute("aria-invalid");
  }

  function syncValidity(p, parsed) {
    var msg = parsed.kind === "invalid" ? leftoverMessage() : "";
    mark(p.iso, parsed.kind === "invalid", msg);
    mark(p.native, parsed.kind === "invalid", msg);
  }

  function applyFromNative(p) {
    if (!p.native || !p.iso) return;
    p.iso.value = p.native.value || "";
    syncValidity(p, { kind: "ok" });
  }

  function applyFromIso(p, normalize) {
    if (!p.iso) return;
    var parsed = parseISO(p.iso.value);
    if (parsed.kind === "ok") {
      if (p.native) p.native.value = parsed.value;
      if (normalize && p.iso) p.iso.value = p.native.value || parsed.value;
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
    if (evt.target === p.iso) {
      applyFromIso(p, false);
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
      if (!p || !p.iso || evt.target !== p.iso) return;
      var parsed = parseISO(p.iso.value);
      if (parsed.kind === "ok") {
        applyFromIso(p, true);
      } else if (parsed.kind === "empty") {
        applyFromNative(p);
      } else {
        // leftover junk stays visible — must not vanish / revert
        applyFromIso(p, false);
      }
    },
    true,
  );
})();
