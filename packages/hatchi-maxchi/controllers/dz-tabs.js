/* HYPERPART: tabs */
/*
 * dz-tabs — activate a tab + reveal its panel.
 *
 * Contract:
 *   - root:   `[data-dz-tabs]` (class `dz-tabs` is presentation)
 *   - tab:    `.dz-tabs__tab` with `data-dz-tab-target` = panel id
 *   - panel:  `.dz-tabs__panel` — revealed when its id matches the target
 *
 * Delegated from document; a click on a tab marks it `aria-current="true"`
 * and hides sibling panels, scoped to the tab's OWN `[data-dz-tabs]` root
 * so N groups stay independent. Revealing a `hidden` panel triggers
 * `hx-trigger="intersect once"` lazy load.
 */
(function () {
  "use strict";

  function tabsRoot(el) {
    return (
      (el.closest && el.closest("[data-dz-tabs]")) ||
      (el.closest && el.closest(".dz-tabs"))
    );
  }

  document.addEventListener("click", function (evt) {
    var tab = evt.target.closest(".dz-tabs__tab");
    if (!tab) return;
    var root = tabsRoot(tab);
    if (!root) return;

    // Ownership filter: only touch elements whose closest tabs root is this one.
    var tabs = root.querySelectorAll(".dz-tabs__tab");
    for (var i = 0; i < tabs.length; i++)
      if (tabsRoot(tabs[i]) === root) tabs[i].removeAttribute("aria-current");
    tab.setAttribute("aria-current", "true");

    var panels = root.querySelectorAll(".dz-tabs__panel");
    for (var j = 0; j < panels.length; j++)
      if (tabsRoot(panels[j]) === root) panels[j].hidden = true;

    var targetId = tab.getAttribute("data-dz-tab-target");
    var panel = targetId
      ? root.querySelector(
          "#" + (window.CSS && CSS.escape ? CSS.escape(targetId) : targetId),
        )
      : null;
    if (panel) panel.hidden = false; // reveal → triggers the panel's intersect-once load
  });
})();
