/* HYPERPART: money */
/*
 * dz-money — major-unit money input with a hidden minor-unit carrier.
 *
 * Contract:
 *   - root: `[data-dz-money]` with `data-dz-scale` and `data-dz-currency`
 *           (scale is mutable when a currency selector changes it)
 *   - display: visible `inputmode=decimal` input (user types major units)
 *   - carrier: hidden `*_minor` input (form posts integer minor units)
 *
 *   input  → hidden minor = round(major × 10^scale)
 *   blur   → normalize display to toFixed(scale); empty clears minor
 *   change (currency <select>) → scale = option's data-scale, prefix
 *            symbol = option's data-symbol, re-normalize
 *
 * Server precomputes the edit-mode display, so there is no init pass.
 * Replaces the Alpine `dzMoney` island (x-model/x-init bindings).
 */
(function () {
  "use strict";

  function parts(el) {
    var root = el.closest && el.closest("[data-dz-money]");
    if (!root) return null;
    return {
      root: root,
      scale: parseInt(root.getAttribute("data-dz-scale") || "2", 10),
      display: root.querySelector('input[inputmode="decimal"]'),
      minor: root.querySelector('input[type="hidden"][name$="_minor"]'),
    };
  }

  function toMinor(val, scale) {
    var num = parseFloat(val);
    if (isNaN(num)) return 0;
    return Math.round(num * Math.pow(10, scale));
  }

  document.addEventListener("input", function (evt) {
    var p = parts(evt.target);
    if (!p || evt.target !== p.display || !p.minor) return;
    p.minor.value = String(toMinor(p.display.value, p.scale));
  });

  document.addEventListener(
    "blur",
    function (evt) {
      var p = parts(evt.target);
      if (!p || evt.target !== p.display || !p.minor) return;
      if (!p.display.value.trim()) {
        p.minor.value = "";
        return;
      }
      var minor = toMinor(p.display.value, p.scale);
      p.minor.value = String(minor);
      p.display.value = (minor / Math.pow(10, p.scale)).toFixed(p.scale);
    },
    true, // blur doesn't bubble — capture
  );

  document.addEventListener("change", function (evt) {
    var sel = evt.target;
    if (!sel.matches || !sel.matches("[data-dz-money] select")) return;
    var p = parts(sel);
    if (!p) return;
    var opt = sel.selectedOptions && sel.selectedOptions[0];
    if (opt && opt.dataset.scale !== undefined) {
      p.root.setAttribute("data-dz-scale", opt.dataset.scale);
      p.scale = parseInt(opt.dataset.scale, 10);
    }
    var prefix = p.root.querySelector(".dz-form-money-prefix");
    if (prefix && opt && opt.dataset.symbol)
      prefix.textContent = opt.dataset.symbol;
    if (p.display && p.display.value && p.minor) {
      var minor = toMinor(p.display.value, p.scale);
      p.minor.value = String(minor);
      p.display.value = (minor / Math.pow(10, p.scale)).toFixed(p.scale);
    }
  });
})();
