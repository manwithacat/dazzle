/* HYPERPART: field */
/*
 * dz-time — native time / datetime-local ↔ ISO companion.
 *
 * Contract:
 *   - root: `[data-dz-time-group]` (gallery also accepts `[data-time-group]`)
 *   - native: `input[type=time]` or `input[type=datetime-local]`
 *             — this is the submitted value (the companion has no name)
 *   - iso: `[data-dz-time-iso]` — editable text (no name)
 *
 * Leftover honesty (cycle 2144): leftover ISO junk must not invent a
 * time. parseClock("14:30zzz") / "2pm" / "14.30" is invalid — the
 * native stays put and both controls fail custom validity so submit
 * cannot post the previous time as if the leftover were accepted.
 * Empty ISO on blur restores from the native (empty is not leftover
 * junk). Valid HH:MM / HH:MM:SS (or YYYY-MM-DDTHH:MM for
 * datetime-local) writes the native; blur normalizes to the native
 * value. Feb 31 / 24:00 / leftover suffix are invalid.
 *
 * Same class as date-range leftover ISO (2139) and colour leftover
 * hex (2133). Server SSRs the initial ISO, so no init pass.
 */
(function () {
  "use strict";

  function rootOf(el) {
    if (!el || !el.closest) return null;
    return (
      el.closest("[data-dz-time-group]") || el.closest("[data-time-group]")
    );
  }

  function parts(el) {
    var group = rootOf(el);
    if (!group) return null;
    return {
      group: group,
      native:
        group.querySelector('input[type="time"]') ||
        group.querySelector('input[type="datetime-local"]'),
      iso: group.querySelector("[data-dz-time-iso]"),
    };
  }

  function isDatetime(native) {
    return !!(native && native.type === "datetime-local");
  }

  function pad2(n) {
    return n < 10 ? "0" + n : String(n);
  }

  // kind: empty | invalid | ok. Leftover suffix / named clocks / dots
  // are invalid — not a silent parse. 24:00 and Feb 31 are invalid.
  function parseClock(raw) {
    var s = String(raw == null ? "" : raw).trim();
    if (!s) return { kind: "empty" };
    var m = /^(\d{2}):(\d{2})(?::(\d{2}))$/.exec(s);
    var hm = /^(\d{2}):(\d{2})$/.exec(s);
    var g = m || hm;
    if (!g) return { kind: "invalid" };
    var hh = +g[1];
    var mm = +g[2];
    var ss = m ? +m[3] : 0;
    if (hh > 23 || mm > 59 || ss > 59) return { kind: "invalid" };
    return { kind: "ok", value: m ? s : s };
  }

  function parseISODate(raw) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
    if (!m) return null;
    var y = +m[1];
    var mo = +m[2];
    var d = +m[3];
    var dt = new Date(Date.UTC(y, mo - 1, d));
    if (
      dt.getUTCFullYear() !== y ||
      dt.getUTCMonth() !== mo - 1 ||
      dt.getUTCDate() !== d
    ) {
      return null;
    }
    return raw;
  }

  function parseISO(raw, datetime) {
    var s = String(raw == null ? "" : raw).trim();
    if (!s) return { kind: "empty" };
    if (!datetime) return parseClock(s);
    var t = s.indexOf("T");
    if (t < 0) return { kind: "invalid" };
    var day = parseISODate(s.slice(0, t));
    if (!day) return { kind: "invalid" };
    var clock = parseClock(s.slice(t + 1));
    if (clock.kind !== "ok") return { kind: "invalid" };
    return { kind: "ok", value: day + "T" + clock.value };
  }

  function leftoverMessage(datetime) {
    return datetime
      ? "Enter a datetime like 2026-06-01T14:30"
      : "Enter a time like 14:30";
  }

  function mark(el, bad, msg) {
    if (!el) return;
    if (el.setCustomValidity) el.setCustomValidity(bad ? msg : "");
    if (bad) el.setAttribute("aria-invalid", "true");
    else el.removeAttribute("aria-invalid");
  }

  function syncValidity(p, parsed) {
    var msg =
      parsed.kind === "invalid" ? leftoverMessage(isDatetime(p.native)) : "";
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
    var parsed = parseISO(p.iso.value, isDatetime(p.native));
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
      var parsed = parseISO(p.iso.value, isDatetime(p.native));
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
