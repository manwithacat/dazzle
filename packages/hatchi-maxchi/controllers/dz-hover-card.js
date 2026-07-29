/* HYPERPART: hover-card */
/*
 * dz-hover-card — open/close for coarse pointers (and explicit click).
 *
 * Progressive enhancement over CSS :hover / :focus-within:
 *   - Fine pointers still open via CSS hover (no JS required).
 *   - Touch / iPadOS Safari does not keep :hover or button :focus reliably;
 *     a click/tap toggles data-dz-open (gallery: data-open after prefix strip).
 *   - Outside pointer + Escape close the explicit open state.
 *
 * Contract:
 *   Root:    [data-dz-hover-card] | [data-hover-card] | .dz-hover-card | .hover-card
 *   Trigger: .dz-hover-card__trigger | .hover-card__trigger
 *   Panel:   .dz-hover-card__content | .hover-card__content
 *            (.dz-hover-card__panel | .hover-card__panel legacy)
 *   Open:    data-dz-open="" on root (unprefixed data-open on gallery)
 *            aria-expanded on the trigger
 *
 * Distinct from popover (details/summary exclusive open): hover-card is still
 * a lightweight preview; click is the accessibility path for touch, not a
 * second product metaphor.
 */
(function () {
  "use strict";

  var ROOT_SEL =
    "[data-dz-hover-card], [data-hover-card], .dz-hover-card, .hover-card";
  var TRIGGER_SEL = ".dz-hover-card__trigger, .hover-card__trigger";

  function rootOf(el) {
    return el && el.closest ? el.closest(ROOT_SEL) : null;
  }

  function isOpen(root) {
    return (
      root.hasAttribute("data-dz-open") ||
      root.hasAttribute("data-open") ||
      root.classList.contains("is-open")
    );
  }

  function setOpen(root, open) {
    if (open) {
      root.setAttribute("data-dz-open", "");
      root.setAttribute("data-open", "");
      root.classList.add("is-open");
    } else {
      root.removeAttribute("data-dz-open");
      root.removeAttribute("data-open");
      root.classList.remove("is-open");
    }
    var triggers = root.querySelectorAll(TRIGGER_SEL);
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute("aria-expanded", open ? "true" : "false");
    }
  }

  function closeAllExcept(keep) {
    var nodes = document.querySelectorAll(ROOT_SEL);
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i] !== keep && isOpen(nodes[i])) setOpen(nodes[i], false);
    }
  }

  // Capture so we win over gallery links; stopPropagation not required for
  // button type=button (no navigation).
  document.addEventListener(
    "click",
    function (e) {
      var t = e.target;
      if (!t || !t.closest) return;

      var trigger = t.closest(TRIGGER_SEL);
      if (trigger) {
        var root = rootOf(trigger);
        if (!root) return;
        e.preventDefault();
        var next = !isOpen(root);
        closeAllExcept(next ? root : null);
        setOpen(root, next);
        return;
      }

      // Outside: close any explicitly opened cards
      if (!t.closest(ROOT_SEL)) {
        closeAllExcept(null);
      }
    },
    false,
  );

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" && e.key !== "Esc") return;
    closeAllExcept(null);
  });

  // Ensure triggers start with aria-expanded=false for AT
  function stampTriggers() {
    var roots = document.querySelectorAll(ROOT_SEL);
    for (var i = 0; i < roots.length; i++) {
      if (!isOpen(roots[i])) {
        var triggers = roots[i].querySelectorAll(TRIGGER_SEL);
        for (var j = 0; j < triggers.length; j++) {
          if (!triggers[j].hasAttribute("aria-expanded")) {
            triggers[j].setAttribute("aria-expanded", "false");
          }
        }
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", stampTriggers);
  } else {
    stampTriggers();
  }
})();
