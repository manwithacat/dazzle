/* HYPERPART: field */
/*
 * dz-color — mirror a colour input's value into its hex readout.
 *
 * Delegated from document: `input` on `.dz-form-color-input` writes the
 * value into the sibling `.dz-form-color-hex` span. The server SSRs the
 * initial readout, so no init pass. Replaces the last Alpine straggler
 * (an inline `x-data { value }` scope on the colour group).
 */
(function () {
  "use strict";

  document.addEventListener("input", function (evt) {
    var input =
      evt.target.closest && evt.target.closest(".dz-form-color-input");
    if (!input) return;
    var group = input.closest(".dz-form-color-group");
    var hex = group && group.querySelector(".dz-form-color-hex");
    if (hex) hex.textContent = input.value;
  });
})();
