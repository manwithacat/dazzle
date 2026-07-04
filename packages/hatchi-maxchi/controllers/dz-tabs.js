/* HYPERPART: tabs */
/*
 * dz-tabs — activate a tab + reveal its panel.
 *
 * Delegated from document; a click on a `.dz-tabs__tab` marks it
 * `aria-current="true"` and hides its siblings' panels, all scoped to the
 * clicked tab's OWN `.dz-tabs` root (every query via `closest`), so N tab
 * groups on one page stay independent. Revealing a `hidden` panel is what
 * triggers its `hx-trigger="intersect once"` lazy load (a display:none panel
 * has no intersection; showing it makes htmx fetch it once).
 *
 * Replaces the per-tab inline `onclick` handler the legacy tabbed list used —
 * one delegated listener, no inline script (CSP-friendlier), instance-safe.
 */
(function () {
  "use strict";

  document.addEventListener("click", function (evt) {
    var tab = evt.target.closest(".dz-tabs__tab");
    if (!tab) return;
    var root = tab.closest(".dz-tabs");
    if (!root) return;

    var tabs = root.querySelectorAll(".dz-tabs__tab");
    for (var i = 0; i < tabs.length; i++)
      tabs[i].removeAttribute("aria-current");
    tab.setAttribute("aria-current", "true");

    var panels = root.querySelectorAll(".dz-tabs__panel");
    for (var j = 0; j < panels.length; j++) panels[j].hidden = true;

    var targetId = tab.getAttribute("data-dz-tab-target");
    var panel = targetId
      ? root.querySelector(
          "#" + (window.CSS && CSS.escape ? CSS.escape(targetId) : targetId),
        )
      : null;
    if (panel) panel.hidden = false; // reveal → triggers the panel's intersect-once load
  });
})();
