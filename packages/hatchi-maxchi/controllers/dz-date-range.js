/* HYPERPART: date-range */
/*
 * dz-date-range — keep From/To honest before the hx-get fires.
 *
 * Contract:
 *   - root: `[data-dz-date-range]` (gallery also accepts `[data-date-range]`)
 *   - from: `input[type=date][name=date_from]`
 *   - to:   `input[type=date][name=date_to]`
 *
 *   change → if both bounds are set and from > to, setCustomValidity
 *            and stop the event so the bar does not hx-get a silent
 *            empty region. Empty either bound is an open range (valid).
 *            Equal dates are a one-day range (valid).
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

  function parts(root) {
    return {
      from: root.querySelector('input[type="date"][name="date_from"]'),
      to: root.querySelector('input[type="date"][name="date_to"]'),
    };
  }

  function inverted(fromVal, toVal) {
    return !!(fromVal && toVal && fromVal > toVal);
  }

  function mark(el, bad, msg) {
    if (!el) return;
    el.setCustomValidity(bad ? msg : "");
    if (bad) el.setAttribute("aria-invalid", "true");
    else el.removeAttribute("aria-invalid");
  }

  function syncValidity(p) {
    var fv = p.from && p.from.value;
    var tv = p.to && p.to.value;
    var bad = inverted(fv, tv);
    var msg = "From must be on or before To";
    mark(p.from, bad, msg);
    mark(p.to, bad, msg);
    return !bad;
  }

  function onBoundChange(evt) {
    var t = evt.target;
    if (!t || t.type !== "date") return;
    var root = rootOf(t);
    if (!root) return;
    var p = parts(root);
    if (t !== p.from && t !== p.to) return;
    if (syncValidity(p)) return;
    // Capture + stop so htmx (change) and the gallery mock (input)
    // never exchange an inverted window. Do not reportValidity() —
    // that focuses the input and the gallery mock treats focus as GET.
    evt.stopImmediatePropagation();
  }

  document.addEventListener("input", onBoundChange, true);
  document.addEventListener("change", onBoundChange, true);
})();
