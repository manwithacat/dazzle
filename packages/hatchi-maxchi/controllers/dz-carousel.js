/* HYPERPART: carousel */
/*
 * dz-carousel — prev / next / dot activation for a server-marked strip.
 *
 * Contract:
 *   - root:   [data-dz-carousel] (+ optional data-dz-carousel-index)
 *   - slides: .dz-carousel__slide — visible when [data-dz-active]
 *   - prev:   [data-dz-carousel-prev]
 *   - next:   [data-dz-carousel-next]
 *   - dots:   .dz-carousel__dot with aria-current on the active index
 *
 * State lives in the DOM (active slide attr + index on the root + disabled
 * ends). No client state graph. Delegated from document; each control is
 * scoped to its own root so N carousels stay independent.
 *
 * Ends clamp (not wrap) — matches the gallery demo's disabled Previous on
 * slide 0. Product servers may re-render the strip; this controller is the
 * local affordance when the page stays put.
 */
(function () {
  "use strict";

  function rootOf(el) {
    if (!el || !el.closest) return null;
    return el.closest("[data-dz-carousel]") || el.closest(".dz-carousel");
  }

  function slideList(root) {
    return root.querySelectorAll(".dz-carousel__slide");
  }

  function dotList(root) {
    return root.querySelectorAll(".dz-carousel__dot");
  }

  function isActive(slide) {
    return (
      slide.hasAttribute("data-dz-active") || slide.hasAttribute("data-active")
    );
  }

  function currentIndex(root) {
    var list = slideList(root);
    for (var i = 0; i < list.length; i++) {
      if (isActive(list[i])) return i;
    }
    var raw =
      root.getAttribute("data-dz-carousel-index") ||
      root.getAttribute("data-carousel-index") ||
      "0";
    var n = parseInt(raw, 10);
    return isNaN(n) ? 0 : n;
  }

  function setActiveAttr(el, on) {
    if (on) {
      el.setAttribute("data-dz-active", "");
      el.setAttribute("data-active", "");
    } else {
      el.removeAttribute("data-dz-active");
      el.removeAttribute("data-active");
    }
  }

  function goTo(root, index) {
    var list = slideList(root);
    var n = list.length;
    if (!n) return;
    var i = index;
    if (i < 0) i = 0;
    if (i > n - 1) i = n - 1;

    for (var s = 0; s < n; s++) {
      setActiveAttr(list[s], s === i);
    }

    root.setAttribute("data-dz-carousel-index", String(i));
    root.setAttribute("data-carousel-index", String(i));

    var dlist = dotList(root);
    for (var d = 0; d < dlist.length; d++) {
      if (d === i) dlist[d].setAttribute("aria-current", "true");
      else dlist[d].removeAttribute("aria-current");
    }

    var prev =
      root.querySelector("[data-dz-carousel-prev]") ||
      root.querySelector("[data-carousel-prev]");
    var next =
      root.querySelector("[data-dz-carousel-next]") ||
      root.querySelector("[data-carousel-next]");
    if (prev) {
      if (i <= 0) prev.setAttribute("disabled", "");
      else prev.removeAttribute("disabled");
    }
    if (next) {
      if (i >= n - 1) next.setAttribute("disabled", "");
      else next.removeAttribute("disabled");
    }
  }

  document.addEventListener("click", function (evt) {
    var t = evt.target;
    if (!t || !t.closest) return;

    var prevBtn =
      t.closest("[data-dz-carousel-prev]") || t.closest("[data-carousel-prev]");
    var nextBtn =
      t.closest("[data-dz-carousel-next]") || t.closest("[data-carousel-next]");
    var dot =
      t.closest(".dz-carousel__dot") || t.closest(".carousel__dot");

    if (!prevBtn && !nextBtn && !dot) return;
    if (prevBtn && prevBtn.disabled) return;
    if (nextBtn && nextBtn.disabled) return;

    var root = rootOf(prevBtn || nextBtn || dot);
    if (!root) return;

    evt.preventDefault();
    var i = currentIndex(root);
    if (prevBtn) {
      goTo(root, i - 1);
      return;
    }
    if (nextBtn) {
      goTo(root, i + 1);
      return;
    }
    var dlist = dotList(root);
    for (var d = 0; d < dlist.length; d++) {
      if (dlist[d] === dot) {
        goTo(root, d);
        return;
      }
    }
  });
})();
