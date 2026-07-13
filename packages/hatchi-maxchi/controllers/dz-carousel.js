/* HYPERPART: carousel */
/*
 * dz-carousel — stage navigation for a server-marked strip.
 *
 * Contract: contracts/carousel.py · Decision 0009 (stage, wrap, autoplay).
 *
 *   root:     [data-dz-carousel]
 *             data-dz-carousel-index
 *             data-dz-carousel-wrap = none|loop  (default none = clamp)
 *             data-dz-carousel-interval = ms     (absent = no autoplay)
 *   slides:   .dz-carousel__slide  — visible when [data-dz-active]
 *   prev:     [data-dz-carousel-prev]
 *   next:     [data-dz-carousel-next]
 *   dots:     .dz-carousel__dot + aria-current
 *   status:   [data-dz-carousel-status]  — "Slide N of M" (optional)
 *
 * State lives in the DOM. Autoplay only mutates the same attrs as prev/next.
 * Timer id on root._dzCarouselTimer (survives as a host property; cleared on
 * pause). Loop is opt-in; clamp disables ends. prefers-reduced-motion kills
 * autoplay. Hover / focus-within / document.hidden pause the timer.
 *
 * Delegated from document; N carousels stay independent.
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

  function wrapMode(root) {
    return (
      root.getAttribute("data-dz-carousel-wrap") ||
      root.getAttribute("data-carousel-wrap") ||
      "none"
    );
  }

  function wraps(root) {
    return wrapMode(root) === "loop";
  }

  function intervalMs(root) {
    var raw =
      root.getAttribute("data-dz-carousel-interval") ||
      root.getAttribute("data-carousel-interval");
    if (raw == null || raw === "") return 0;
    var n = parseInt(raw, 10);
    if (isNaN(n) || n < 500) return 0;
    return n;
  }

  function prefersReducedMotion() {
    try {
      return (
        window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches
      );
    } catch (e) {
      return false;
    }
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

  function updateStatus(root, i, n) {
    var status =
      root.querySelector("[data-dz-carousel-status]") ||
      root.querySelector("[data-carousel-status]");
    if (!status) return;
    status.textContent = "Slide " + (i + 1) + " of " + n;
  }

  function clearTimer(root) {
    if (root._dzCarouselTimer) {
      clearInterval(root._dzCarouselTimer);
      root._dzCarouselTimer = null;
    }
  }

  function shouldPause(root) {
    if (prefersReducedMotion()) return true;
    if (document.hidden) return true;
    try {
      if (root.matches(":hover") || root.matches(":focus-within")) return true;
    } catch (e) {
      /* :focus-within missing in ancient engines */
    }
    return false;
  }

  function armTimer(root) {
    clearTimer(root);
    var ms = intervalMs(root);
    if (!ms || shouldPause(root)) return;
    root._dzCarouselTimer = setInterval(function () {
      if (shouldPause(root)) return;
      var list = slideList(root);
      var n = list.length;
      if (!n) return;
      var i = currentIndex(root);
      if (wraps(root)) {
        goTo(root, i + 1, { fromTimer: true });
      } else if (i < n - 1) {
        goTo(root, i + 1, { fromTimer: true });
      } else {
        clearTimer(root);
      }
    }, ms);
  }

  function goTo(root, index, opts) {
    opts = opts || {};
    var list = slideList(root);
    var n = list.length;
    if (!n) return;
    var i = index;
    if (wraps(root)) {
      i = ((i % n) + n) % n;
    } else {
      if (i < 0) i = 0;
      if (i > n - 1) i = n - 1;
    }

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
    var loop = wraps(root);
    if (prev) {
      if (!loop && i <= 0) prev.setAttribute("disabled", "");
      else prev.removeAttribute("disabled");
    }
    if (next) {
      if (!loop && i >= n - 1) next.setAttribute("disabled", "");
      else next.removeAttribute("disabled");
    }

    updateStatus(root, i, n);

    // User chrome restarts autoplay eligibility; timer tick keeps it armed.
    if (!opts.fromTimer) {
      armTimer(root);
    } else if (!wraps(root) && i >= n - 1) {
      clearTimer(root);
    }
  }

  document.addEventListener("click", function (evt) {
    var t = evt.target;
    if (!t || !t.closest) return;

    var prevBtn =
      t.closest("[data-dz-carousel-prev]") || t.closest("[data-carousel-prev]");
    var nextBtn =
      t.closest("[data-dz-carousel-next]") || t.closest("[data-carousel-next]");
    var dot = t.closest(".dz-carousel__dot") || t.closest(".carousel__dot");

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

  document.addEventListener("keydown", function (evt) {
    var key = evt.key;
    if (
      key !== "ArrowLeft" &&
      key !== "ArrowRight" &&
      key !== "Home" &&
      key !== "End"
    ) {
      return;
    }
    var root = rootOf(document.activeElement);
    if (!root) return;
    // Only when focus is inside this carousel (not bubbling from page chrome).
    if (!root.contains(document.activeElement)) return;

    var i = currentIndex(root);
    var n = slideList(root).length;
    if (!n) return;

    if (key === "ArrowLeft") {
      evt.preventDefault();
      goTo(root, i - 1);
    } else if (key === "ArrowRight") {
      evt.preventDefault();
      goTo(root, i + 1);
    } else if (key === "Home") {
      evt.preventDefault();
      goTo(root, 0);
    } else if (key === "End") {
      evt.preventDefault();
      goTo(root, n - 1);
    }
  });

  function rearmAll() {
    var roots = document.querySelectorAll("[data-dz-carousel], [data-carousel]");
    for (var i = 0; i < roots.length; i++) {
      var root = roots[i];
      var n = slideList(root).length;
      if (!n) continue;
      updateStatus(root, currentIndex(root), n);
      armTimer(root);
    }
  }

  document.addEventListener(
    "mouseenter",
    function (evt) {
      var root = rootOf(evt.target);
      if (root) clearTimer(root);
    },
    true
  );
  document.addEventListener(
    "mouseleave",
    function (evt) {
      var root = rootOf(evt.target);
      if (root && !root.contains(evt.relatedTarget)) armTimer(root);
    },
    true
  );
  document.addEventListener(
    "focusin",
    function (evt) {
      var root = rootOf(evt.target);
      if (root) clearTimer(root);
    },
    true
  );
  document.addEventListener(
    "focusout",
    function (evt) {
      var root = rootOf(evt.target);
      if (!root) return;
      // relatedTarget may be null; re-arm after focus leaves the root
      setTimeout(function () {
        if (!root.contains(document.activeElement)) armTimer(root);
      }, 0);
    },
    true
  );
  document.addEventListener("visibilitychange", function () {
    rearmAll();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", rearmAll);
  } else {
    rearmAll();
  }
})();
