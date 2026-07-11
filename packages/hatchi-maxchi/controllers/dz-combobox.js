/* HYPERPART: combobox */
/*
 * dz-combobox — HM-native searchable enum single-select (HMC-018 slice 1),
 * the vanilla replacement for TomSelect's `widget=combobox` mount.
 *
 * Progressive enhancement, delegated from the document, state-in-DOM.
 * The server renders a real `<select data-dz-combobox>` with all its
 * <option>s — fully usable with JS OFF (submits, native `required`). On
 * first interaction (pointerdown / focusin / keydown) we build a sibling
 * searchable overlay: a `role="combobox"` text input + a `role="listbox"`
 * <ul> of the options, wrapped in a `.dz-combobox` root. The native
 * <select> stays in the DOM as the submitted value; on selection we write
 * its `.value` and fire a `change` event, so the form + any listeners see
 * the same control they always did.
 *
 * Open/closed is `data-dz-open` on the `.dz-combobox` ROOT (CSS hides the
 * listbox off it); `aria-expanded` on the input is the a11y mirror. Focus
 * leaving the widget closes after a 200ms grace (mirrors dz-search-select
 * — a click on an option blurs the input first). Enhance-once is marked
 * with `data-dz-enhanced` on the root.
 *
 * a11y: input is role=combobox + aria-expanded + aria-controls +
 * aria-autocomplete=list + aria-haspopup=listbox + aria-activedescendant;
 * the <ul> is role=listbox and each row role=option with aria-selected.
 * Keyboard: type filters (substring, case-insensitive); ArrowUp/Down move
 * the active descendant over visible rows; Enter/click selects; Esc closes;
 * focus opens.
 */
(function () {
  "use strict";

  function setOpen(root, open) {
    if (open) root.setAttribute("data-dz-open", "true");
    else root.removeAttribute("data-dz-open");
    var input = root.querySelector(".dz-combobox-input");
    if (input) input.setAttribute("aria-expanded", open ? "true" : "false");
    if (!open) setActive(root, null);
  }

  function options(root) {
    return Array.prototype.slice.call(
      root.querySelectorAll(".dz-combobox-option"),
    );
  }

  function visibleOptions(root) {
    return options(root).filter(function (li) {
      return !li.hidden;
    });
  }

  // The active (keyboard-highlighted) descendant — distinct from the
  // chosen option (aria-selected). Mirrored onto the input's
  // aria-activedescendant so a screen reader tracks the highlight.
  function setActive(root, li) {
    var input = root.querySelector(".dz-combobox-input");
    options(root).forEach(function (o) {
      if (o === li) o.setAttribute("data-dz-active", "true");
      else o.removeAttribute("data-dz-active");
    });
    if (input) {
      if (li) input.setAttribute("aria-activedescendant", li.id);
      else input.removeAttribute("aria-activedescendant");
    }
    if (li) li.scrollIntoView({ block: "nearest" });
  }

  function activeOption(root) {
    return root.querySelector('.dz-combobox-option[data-dz-active="true"]');
  }

  function selectedLabel(root) {
    var chosen = root.querySelector(
      '.dz-combobox-option[aria-selected="true"]',
    );
    return chosen ? chosen.textContent : "";
  }

  // Commit a choice: write the native <select> value, sync the input
  // display + aria-selected, close, and fire `change` so the form and any
  // listeners react exactly as they did with the bare <select>.
  //
  // Do NOT focus() the input after close: the focusin handler opens the
  // listbox, so a post-choose focus immediately re-opens the picker (user
  // sees the value set but the menu stays up). Pointerdown on an option
  // uses preventDefault so focus never left the input; Enter already has
  // focus on the input.
  function choose(root, li) {
    var select = root.querySelector("select[data-dz-combobox]");
    var input = root.querySelector(".dz-combobox-input");
    if (!select || !input) return;
    select.value = li.getAttribute("data-dz-value") || "";
    options(root).forEach(function (o) {
      o.setAttribute("aria-selected", o === li ? "true" : "false");
    });
    input.value = li.textContent;
    setOpen(root, false);
    // Clear filter so a re-open shows the full list, not a stale query.
    filter(root, "");
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function filter(root, query) {
    var q = query.trim().toLowerCase();
    var empty = root.querySelector(".dz-combobox-empty");
    var anyVisible = false;
    options(root).forEach(function (li) {
      var match = li.textContent.toLowerCase().indexOf(q) !== -1;
      li.hidden = !match;
      if (match) anyVisible = true;
    });
    if (empty) empty.hidden = anyVisible;
    // Keep the active descendant on a still-visible row.
    var active = activeOption(root);
    if (!active || active.hidden)
      setActive(root, visibleOptions(root)[0] || null);
  }

  // Build the searchable overlay once, from the server-rendered <select>.
  function enhance(select) {
    var root = document.createElement("div");
    root.className = "dz-combobox";

    var name = select.id || select.name || "dz-combobox";
    var listId = name + "-listbox";

    // Field label: the substrate wraps the widget in
    // `<label class="dz-field"><span class="dz-field__label">…</span>…</label>`.
    var labelSpan = select.closest(".dz-field")
      ? select.closest(".dz-field").querySelector(".dz-field__label")
      : null;
    var labelText = labelSpan ? labelSpan.textContent.trim() : "";

    // The leading value="" option is the placeholder prompt, not a choice.
    var opts = Array.prototype.slice.call(select.options);
    var placeholderOpt = opts.length && opts[0].value === "" ? opts[0] : null;
    var choices = placeholderOpt ? opts.slice(1) : opts;
    var placeholder = placeholderOpt ? placeholderOpt.textContent : "";

    var input = document.createElement("input");
    input.type = "text";
    input.className = "dz-combobox-input";
    input.setAttribute("role", "combobox");
    input.setAttribute("autocomplete", "off");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", listId);
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-haspopup", "listbox");
    if (labelText) input.setAttribute("aria-label", labelText);
    if (placeholder) input.setAttribute("placeholder", placeholder);
    if (select.hasAttribute("required")) {
      input.setAttribute("aria-required", "true");
    }

    var list = document.createElement("ul");
    list.className = "dz-combobox-listbox";
    list.id = listId;
    list.setAttribute("role", "listbox");
    if (labelText) list.setAttribute("aria-label", labelText);

    var selectedText = "";
    choices.forEach(function (opt, i) {
      var li = document.createElement("li");
      li.className = "dz-combobox-option";
      li.id = name + "-opt-" + i;
      li.setAttribute("role", "option");
      li.setAttribute("data-dz-value", opt.value);
      var chosen = opt.selected && opt.value !== "";
      li.setAttribute("aria-selected", chosen ? "true" : "false");
      li.textContent = opt.textContent;
      if (chosen) selectedText = opt.textContent;
      list.appendChild(li);
    });

    var empty = document.createElement("li");
    empty.className = "dz-combobox-empty";
    empty.setAttribute("role", "presentation");
    empty.textContent = "No matches";
    empty.hidden = true;
    list.appendChild(empty);

    if (selectedText) input.value = selectedText;

    // Move the native <select> under the root (submit value + no-JS
    // fallback), take it out of the tab order, and mount the overlay. Drop
    // `required` off the now-`display:none` select: a hidden required control
    // would make the browser block submit with an unfocusable console error
    // and no visible bubble. The visible input carries `aria-required` for
    // AT (set above); server-side validation is the enforcement backstop, and
    // the no-JS path still uses native `required` on the unhidden select.
    select.removeAttribute("required");
    select.parentNode.insertBefore(root, select);
    select.setAttribute("tabindex", "-1");
    root.appendChild(input);
    root.appendChild(select);
    root.appendChild(list);
    root.setAttribute("data-dz-enhanced", "");
    return root;
  }

  function rootFor(select) {
    var existing = select.closest(".dz-combobox[data-dz-enhanced]");
    return existing || enhance(select);
  }

  // ── Enhance-on-first-interaction ─────────────────────────────────────
  // A pointerdown on the bare select would pop the native menu; enhance
  // first and swallow the event, then focus our input.
  document.addEventListener(
    "pointerdown",
    function (evt) {
      var select =
        evt.target.closest && evt.target.closest("select[data-dz-combobox]");
      if (!select || select.closest(".dz-combobox[data-dz-enhanced]")) return;
      evt.preventDefault();
      var root = rootFor(select);
      var input = root.querySelector(".dz-combobox-input");
      if (input) input.focus();
      setOpen(root, true);
    },
    true,
  );

  // Keyboard tab-in / typing onto the bare select enhances too.
  document.addEventListener("focusin", function (evt) {
    var select =
      evt.target.closest && evt.target.closest("select[data-dz-combobox]");
    if (select && !select.closest(".dz-combobox[data-dz-enhanced]")) {
      var root = rootFor(select);
      var input = root.querySelector(".dz-combobox-input");
      if (input) input.focus();
      setOpen(root, true);
      return;
    }
    // Focus entering the enhanced input opens the listbox.
    var input2 = evt.target.closest && evt.target.closest(".dz-combobox-input");
    if (input2) {
      var r = input2.closest(".dz-combobox");
      if (r) setOpen(r, true);
    }
  });

  document.addEventListener("focusout", function (evt) {
    var input = evt.target.closest && evt.target.closest(".dz-combobox-input");
    if (!input) return;
    var root = input.closest(".dz-combobox");
    if (!root) return;
    setTimeout(function () {
      if (root.contains(document.activeElement)) return; // re-focused
      // Restore the display text to the current selection (a half-typed
      // filter must not stick as a phantom value).
      input.value = selectedLabel(root);
      setOpen(root, false);
    }, 200);
  });

  document.addEventListener("input", function (evt) {
    var input = evt.target.closest && evt.target.closest(".dz-combobox-input");
    if (!input) return;
    var root = input.closest(".dz-combobox");
    if (!root) return;
    setOpen(root, true);
    filter(root, input.value);
  });

  document.addEventListener("keydown", function (evt) {
    var input = evt.target.closest && evt.target.closest(".dz-combobox-input");
    if (!input) return;
    var root = input.closest(".dz-combobox");
    if (!root) return;
    var vis = visibleOptions(root);

    if (evt.key === "ArrowDown" || evt.key === "ArrowUp") {
      evt.preventDefault();
      if (!root.hasAttribute("data-dz-open")) {
        setOpen(root, true);
        filter(root, input.value);
        vis = visibleOptions(root);
      }
      if (!vis.length) return;
      var cur = activeOption(root);
      var idx = cur ? vis.indexOf(cur) : -1;
      var next =
        evt.key === "ArrowDown"
          ? Math.min(idx + 1, vis.length - 1)
          : Math.max(idx - 1, 0);
      if (idx === -1) next = evt.key === "ArrowDown" ? 0 : vis.length - 1;
      setActive(root, vis[next]);
    } else if (evt.key === "Enter") {
      var active = activeOption(root);
      if (active && !active.hidden) {
        evt.preventDefault();
        choose(root, active);
      }
    } else if (evt.key === "Escape") {
      if (root.hasAttribute("data-dz-open")) {
        evt.preventDefault();
        input.value = selectedLabel(root);
        setOpen(root, false);
      }
    }
  });

  // pointerdown (capture) so we can preventDefault and keep focus on the
  // combobox input — otherwise the input blurs, then choose() would have
  // needed a re-focus that re-opens the listbox (see choose() note).
  document.addEventListener(
    "pointerdown",
    function (evt) {
      var li = evt.target.closest && evt.target.closest(".dz-combobox-option");
      if (!li || li.hidden) return;
      var root = li.closest(".dz-combobox");
      if (!root) return;
      evt.preventDefault();
      choose(root, li);
    },
    true,
  );
})();
