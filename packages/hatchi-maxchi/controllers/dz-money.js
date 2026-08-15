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
 *   input  → hidden minor = round(major × 10^scale) when the text is a
 *            real number; empty/invalid clears the carrier (never 0)
 *   blur   → normalize display to toFixed(scale); empty/invalid clears
 *            minor and does not rewrite the display to 0.00
 *   change (currency <select>) → scale = option's data-scale, prefix
 *            symbol = option's data-symbol, re-normalize only if valid
 *
 * Garbage like "abc" / "12abc" must not become a silent £0.00 post
 * (cycle 2121 — same honesty class as search-select type clearing a
 * stale FK). Required fields use setCustomValidity on invalid text;
 * empty + required stays on native `required`.
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

  // kind: empty | partial | invalid | ok. parseFloat("12abc") === 12, so
  // leftover junk is invalid — not a silent 1200.
  function parseMajor(val, strict) {
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
    return { kind: "ok", value: num };
  }

  function toMinor(num, scale) {
    return Math.round(num * Math.pow(10, scale));
  }

  function syncValidity(p, parsed) {
    if (!p.display) return;
    if (parsed.kind === "invalid") {
      p.display.setCustomValidity("Enter a valid amount");
      return;
    }
    // empty + required: native required owns the bubble
    p.display.setCustomValidity("");
  }

  function applyParsed(p, parsed, normalize) {
    if (!p.minor) return;
    if (parsed.kind === "ok") {
      var minor = toMinor(parsed.value, p.scale);
      p.minor.value = String(minor);
      if (normalize && p.display) {
        p.display.value = (minor / Math.pow(10, p.scale)).toFixed(p.scale);
      }
    } else {
      p.minor.value = "";
    }
    syncValidity(p, parsed);
  }

  document.addEventListener("input", function (evt) {
    var p = parts(evt.target);
    if (!p || evt.target !== p.display || !p.minor) return;
    applyParsed(p, parseMajor(p.display.value, false), false);
  });

  document.addEventListener(
    "blur",
    function (evt) {
      var p = parts(evt.target);
      if (!p || evt.target !== p.display || !p.minor) return;
      applyParsed(p, parseMajor(p.display.value, true), true);
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
    if (p.display && p.minor) {
      applyParsed(p, parseMajor(p.display.value, true), true);
    }
  });
})();
