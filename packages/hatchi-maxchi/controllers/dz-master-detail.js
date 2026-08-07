/* HYPERPART: master-detail */
/*
 * dz-master-detail — selection state for the master-detail composite.
 *
 * Contract:
 *   - root: `[data-dz-master-detail]` (class `dz-master-detail`)
 *   - list body: `[data-dz-master-detail-list-body]` (optional marker; Dazzle dual_pane)
 *   - detail body: `[data-dz-master-detail-detail-body]` (hx-get target pane marker)
 *   - item: `.dz-master-detail__item` — click sets aria-current within root
 *
 * The detail pane is loaded by htmx (item hx-get swaps a card into
 * .dz-master-detail__detail / [data-dz-master-detail-detail-body]); this
 * controller owns only selection state (+ keyboard parity, cycle 1743).
 *
 * Keyboard (when focus is inside a root, not on a form control):
 *   - ArrowDown / ArrowUp — move aria-current to next/prev item, focus it,
 *     and click so hx-get loads the sibling detail pane
 *   - Home / End — jump to first / last item
 *
 * INSTANCE-ISOLATED — delegated on `document`, every query scoped to the
 * clicked item's OWN `[data-dz-master-detail]` root so N instances stay
 * independent.
 */
(function () {
  "use strict";

  var ITEM_SEL = ".dz-master-detail__item";

  function rootOf(el) {
    if (!el || !el.closest) return null;
    return (
      el.closest("[data-dz-master-detail]") ||
      el.closest(".dz-master-detail")
    );
  }

  function itemList(root) {
    return Array.prototype.slice.call(root.querySelectorAll(ITEM_SEL));
  }

  function isFormField(el) {
    if (!el || !el.tagName) return false;
    if (el.isContentEditable) return true;
    var tag = el.tagName.toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || tag === "option";
  }

  function setCurrent(root, item) {
    var current = root.querySelectorAll(ITEM_SEL + "[aria-current]");
    for (var i = 0; i < current.length; i++) {
      current[i].removeAttribute("aria-current");
    }
    item.setAttribute("aria-current", "true");
  }

  function selectAndActivate(root, item) {
    setCurrent(root, item);
    // Keep keyboard focus on the item so further arrows continue from here.
    if (typeof item.focus === "function") {
      try {
        item.focus({ preventScroll: false });
      } catch (_e) {
        item.focus();
      }
    }
    // Synthetic click: htmx loads the pane; our click listener re-affirms
    // aria-current (idempotent). Native click so MOCK_HTMX / htmx hx-get fire.
    if (typeof item.click === "function") {
      item.click();
    }
  }

  document.addEventListener("click", function (evt) {
    var item = evt.target.closest(ITEM_SEL);
    if (!item) return;
    var root = rootOf(item);
    if (!root) return;
    // clear the previous selection WITHIN THIS root only, then mark this one
    setCurrent(root, item);
  });

  document.addEventListener("keydown", function (evt) {
    var key = evt.key;
    if (
      key !== "ArrowDown" &&
      key !== "ArrowUp" &&
      key !== "Home" &&
      key !== "End"
    ) {
      return;
    }
    var ae = document.activeElement;
    if (!ae || isFormField(ae)) return;
    var root = rootOf(ae);
    if (!root || !root.contains(ae)) return;

    var items = itemList(root);
    if (!items.length) return;

    var idx = -1;
    // Prefer the focused item when it is a list row; else aria-current.
    for (var i = 0; i < items.length; i++) {
      if (items[i] === ae || items[i].contains(ae)) {
        idx = i;
        break;
      }
    }
    if (idx < 0) {
      for (var j = 0; j < items.length; j++) {
        if (items[j].getAttribute("aria-current") === "true") {
          idx = j;
          break;
        }
      }
    }
    if (idx < 0) idx = 0;

    var next = idx;
    if (key === "ArrowDown") {
      next = Math.min(items.length - 1, idx + 1);
    } else if (key === "ArrowUp") {
      next = Math.max(0, idx - 1);
    } else if (key === "Home") {
      next = 0;
    } else if (key === "End") {
      next = items.length - 1;
    }

    if (next === idx && items[idx] === ae) {
      // Already at edge with focus — still prevent page scroll.
      evt.preventDefault();
      return;
    }
    evt.preventDefault();
    selectAndActivate(root, items[next]);
  });
})();
