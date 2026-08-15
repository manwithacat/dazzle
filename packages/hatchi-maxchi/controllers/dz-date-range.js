/* HYPERPART: date-range */
/*
 * dz-date-range — keep From/To honest before the hx-get fires.
 *
 * Contract:
 *   - root: `[data-dz-date-range]` (gallery also accepts `[data-date-range]`)
 *   - from: `input[type=date][name=date_from]`
 *   - to:   `input[type=date][name=date_to]`
 *   - iso:  `[data-dz-date-iso]` companion in the same `.dz-date-range-group`
 *           (no name — the native date is the submitted / hx-include value)
 *
 *   change → if both bounds are set and from > to, setCustomValidity
 *            and stop the event so the bar does not hx-get a silent
 *            empty region. Empty either bound is an open range (valid).
 *            Equal dates are a one-day range (valid).
 *
 * Leftover honesty (cycle 2139): leftover ISO junk ("2026-06-01zzz",
 * "zzz", "June 1") must not invent a bound. parseISO is exact
 * YYYY-MM-DD (real calendar day) — a leftover suffix is invalid.
 * The native date stays put and both the companion and the date
 * fail custom validity so submit / hx-get cannot post the previous
 * date as if the leftover were accepted. Empty ISO on blur restores
 * from the native date (empty is not leftover junk). Valid ISO
 * writes the date. Invalid leftover stops so the gallery mock does
 * not invent /mock/search (Aurora) from leftover text.
 *
 * Garbage inverted ranges used to POST as if they were a real window
 * (cycle 2122 — same honesty class as money invalid text inventing 0
 * and search-select type clearing a stale FK).
 *
 * No init pass: native date values are the source of truth. Re-query
 * the DOM on every change (morph-safe).
 */
(function () {
  "use strict";

  function rootOf(el) {
    if (!el || !el.closest) return null;
    return (
      el.closest("[data-dz-date-range]") || el.closest("[data-date-range]")
    );
  }

  function isoOf(dateEl) {
    if (!dateEl || !dateEl.parentElement) return null;
    return dateEl.parentElement.querySelector("[data-dz-date-iso]");
  }

  function parts(root) {
    var from = root.querySelector('input[type="date"][name="date_from"]');
    var to = root.querySelector('input[type="date"][name="date_to"]');
    return {
      from: from,
      to: to,
      fromIso: isoOf(from),
      toIso: isoOf(to),
    };
  }

  function inverted(fromVal, toVal) {
    return !!(fromVal && toVal && fromVal > toVal);
  }

  function mark(el, bad, msg) {
    if (!el) return;
    if (el.setCustomValidity) el.setCustomValidity(bad ? msg : "");
    if (bad) el.setAttribute("aria-invalid", "true");
    else el.removeAttribute("aria-invalid");
  }

  function syncInverted(p) {
    var fv = p.from && p.from.value;
    var tv = p.to && p.to.value;
    var bad = inverted(fv, tv);
    var msg = "From must be on or before To";
    mark(p.from, bad, msg);
    mark(p.to, bad, msg);
    mark(p.fromIso, bad, msg);
    mark(p.toIso, bad, msg);
    return !bad;
  }

  // kind: empty | invalid | ok. Leftover suffix / named months / slashes
  // are invalid — not a silent YYYY-MM-DD parse. Feb 31 is invalid.
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

  function leftoverMessage() {
    return "Enter a date like 2026-06-01";
  }

  function applyFromNative(dateEl) {
    var iso = isoOf(dateEl);
    if (iso) iso.value = dateEl.value || "";
  }

  function applyFromIso(iso, dateEl, normalize) {
    var parsed = parseISO(iso ? iso.value : "");
    if (parsed.kind === "ok") {
      if (dateEl) dateEl.value = parsed.value;
      if (normalize && iso) iso.value = parsed.value;
    }
    // leftover junk / empty: do not write the date (never invent)
    var msg = parsed.kind === "invalid" ? leftoverMessage() : "";
    mark(iso, parsed.kind === "invalid", msg);
    mark(dateEl, parsed.kind === "invalid", msg);
    return parsed;
  }

  function onBoundChange(evt) {
    var t = evt.target;
    if (!t) return;
    var root = rootOf(t);
    if (!root) return;
    var p = parts(root);

    if (t.getAttribute && t.hasAttribute("data-dz-date-iso")) {
      var dateEl = t === p.fromIso ? p.from : t === p.toIso ? p.to : null;
      if (!dateEl && t.parentElement) {
        dateEl = t.parentElement.querySelector('input[type="date"]');
      }
      var parsed = applyFromIso(t, dateEl, false);
      if (parsed.kind === "invalid") {
        evt.stopImmediatePropagation();
        return;
      }
      if (parsed.kind === "ok") {
        p = parts(root);
        if (!syncInverted(p)) {
          evt.stopImmediatePropagation();
          return;
        }
        if (dateEl && evt.type === "input") {
          dateEl.dispatchEvent(new Event("input", { bubbles: true }));
        }
      }
      return;
    }

    if (t.type !== "date") return;
    if (t !== p.from && t !== p.to) return;
    applyFromNative(t);
    if (syncInverted(p)) return;
    // Capture + stop so htmx (change) and the gallery mock (input)
    // never exchange an inverted window. Do not reportValidity() —
    // that focuses the input and the gallery mock treats focus as GET.
    evt.stopImmediatePropagation();
  }

  document.addEventListener("input", onBoundChange, true);
  document.addEventListener("change", onBoundChange, true);

  document.addEventListener(
    "blur",
    function (evt) {
      var t = evt.target;
      if (!t || !t.hasAttribute || !t.hasAttribute("data-dz-date-iso")) {
        return;
      }
      var root = rootOf(t);
      if (!root) return;
      var dateEl =
        t.parentElement && t.parentElement.querySelector('input[type="date"]');
      var parsed = parseISO(t.value);
      if (parsed.kind === "ok") {
        applyFromIso(t, dateEl, true);
        syncInverted(parts(root));
      } else if (parsed.kind === "empty") {
        applyFromNative(dateEl);
        syncInverted(parts(root));
      } else {
        // leftover junk stays visible — must not vanish / revert
        applyFromIso(t, dateEl, false);
      }
    },
    true,
  );
})();
