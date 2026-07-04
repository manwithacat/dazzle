/* HYPERPART: slider */
/*
 * dz-slider — live value readout for a native <input type="range">.
 *
 * Delegated from document; on `input` it writes the range's current value into
 * the `[data-dz-range-value]` readout within the SAME group, so N sliders on a
 * page stay independent (every query scoped to the input's own group — never a
 * global document.querySelector).
 *
 * Skips inputs already managed by a widget bridge (`[data-dz-widget]`) so it
 * never double-handles a host that wires its own range controller. It is the
 * canonical HM value controller: a host adopts it simply by dropping that
 * wrapper attribute.
 */
(function () {
  "use strict";

  // The readout for a range input, or null if this input isn't ours to touch
  // (not a dz-slider, or already owned by a widget bridge). One guard, used by
  // both the delegated listener and the one-time mount sync.
  function readoutFor(input) {
    if (!input || !input.matches) return null;
    if (!input.matches('input[type="range"][data-dz-slider]')) return null;
    if (input.closest("[data-dz-widget]")) return null;
    var group = input.closest(".dz-form-slider-group") || input.parentElement;
    return group ? group.querySelector("[data-dz-range-value]") : null;
  }

  document.addEventListener("input", function (evt) {
    var out = readoutFor(evt.target);
    if (out) out.textContent = evt.target.value;
  });

  // One-time sync so a hard-coded `value=` matches its readout before the first
  // input (copy-paste robustness). Respects the same guard, so it never touches
  // a widget-bridge-managed range.
  function sync() {
    var inputs = document.querySelectorAll(
      'input[type="range"][data-dz-slider]',
    );
    for (var i = 0; i < inputs.length; i++) {
      var out = readoutFor(inputs[i]);
      if (out) out.textContent = inputs[i].value;
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", sync);
  } else {
    sync();
  }
})();
