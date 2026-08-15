/* HYPERPART: field */
/*
 * dz-color — swatch ↔ hex companion for a colour group.
 *
 * Contract:
 *   - root: `[data-dz-color-group]` (also class `dz-form-color-group`)
 *   - swatch: `.dz-form-color-input` — native <input type=color>; this
 *             is the submitted value (the hex companion has no name)
 *   - hex: `.dz-form-color-hex` — editable text (legacy: a span readout)
 *
 * Leftover honesty (cycle 2133): leftover hex junk must not invent
 * a colour. parseHex("#3b82f6zzz") / "red" / "rgb(…)" is
 * invalid — the swatch stays put and both controls fail custom
 * validity so submit cannot post the previous swatch as if the leftover
 * were accepted. Empty hex on blur restores from the swatch (empty is
 * not leftover junk). Valid 3/6-digit hex (optional #) writes the
 * swatch; blur normalizes to #rrggbb.
 *
 * Same class as money leftover junk (2121) and tags leftover token
 * (2131). Server SSRs the initial hex, so no init pass.
 */
(function () {
  "use strict";

  function parts(el) {
    if (!el || !el.closest) return null;
    var group =
      el.closest("[data-dz-color-group]") || el.closest(".dz-form-color-group");
    if (!group) return null;
    return {
      group: group,
      color: group.querySelector(".dz-form-color-input"),
      hex: group.querySelector(".dz-form-color-hex"),
    };
  }

  function hexGet(el) {
    if (!el) return "";
    return el.tagName === "INPUT" ? el.value : el.textContent || "";
  }

  function hexSet(el, val) {
    if (!el) return;
    if (el.tagName === "INPUT") el.value = val;
    else el.textContent = val;
  }

  // kind: empty | invalid | ok. Named colours / rgb() / leftover
  // suffix after a hex token are invalid — not a silent parse.
  function parseHex(raw) {
    var s = String(raw == null ? "" : raw).trim();
    if (!s) return { kind: "empty" };
    var m = /^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.exec(s);
    if (!m) return { kind: "invalid" };
    var h = m[1];
    if (h.length === 3) {
      h =
        h.charAt(0) +
        h.charAt(0) +
        h.charAt(1) +
        h.charAt(1) +
        h.charAt(2) +
        h.charAt(2);
    }
    return { kind: "ok", value: "#" + h.toLowerCase() };
  }

  function syncValidity(p, parsed) {
    var msg =
      parsed.kind === "invalid" ? "Enter a hex colour like #3b82f6" : "";
    if (p.hex && p.hex.setCustomValidity) p.hex.setCustomValidity(msg);
    if (p.color && p.color.setCustomValidity) p.color.setCustomValidity(msg);
  }

  function applyFromColor(p) {
    if (!p.color || !p.hex) return;
    hexSet(p.hex, p.color.value);
    syncValidity(p, { kind: "ok" });
  }

  function applyFromHex(p, normalize) {
    if (!p.hex) return;
    var parsed = parseHex(hexGet(p.hex));
    if (parsed.kind === "ok") {
      if (p.color) p.color.value = parsed.value;
      if (normalize) hexSet(p.hex, parsed.value);
    }
    // leftover junk / empty: do not write the swatch (never invent)
    syncValidity(p, parsed);
  }

  document.addEventListener("input", function (evt) {
    var p = parts(evt.target);
    if (!p) return;
    if (evt.target.closest && evt.target.closest(".dz-form-color-input")) {
      applyFromColor(p);
      return;
    }
    if (
      p.hex &&
      (evt.target === p.hex || evt.target.closest(".dz-form-color-hex"))
    ) {
      applyFromHex(p, false);
    }
  });

  document.addEventListener(
    "blur",
    function (evt) {
      var p = parts(evt.target);
      if (!p || !p.hex || evt.target !== p.hex) return;
      var parsed = parseHex(hexGet(p.hex));
      if (parsed.kind === "ok") {
        applyFromHex(p, true);
      } else if (parsed.kind === "empty") {
        applyFromColor(p);
      } else {
        // leftover junk stays visible — must not vanish / revert
        syncValidity(p, parsed);
      }
    },
    true,
  );
})();
