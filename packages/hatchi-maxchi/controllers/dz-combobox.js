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
 * leaving the widget (input OR listbox) for another control closes it at
 * once; with no focus destination it closes after a 200ms grace.
 * Enhance-once is marked with `data-dz-enhanced` on the root.
 *
 * One Tab stop (#1843): the listbox is tabindex=-1. Input and listbox are
 * named by the field label span (aria-labelledby, so the required marker
 * is not copied into a name), and the label's `for=` moves to the visible
 * input once the native select is hidden.
 *
 * a11y: input is role=combobox + aria-expanded + aria-controls +
 * aria-autocomplete=list + aria-haspopup=listbox + aria-activedescendant;
 * the <ul> is role=listbox and each row role=option with aria-selected.
 * Keyboard: type filters (substring, case-insensitive); ArrowUp/Down move
 * the active descendant over visible rows; Enter/click selects; Esc closes;
 * focus opens.
 *
 * Required honesty (cycle 2120): after enhance, the native <select> is
 * display:none so its `required` would block submit with an unfocusable
 * error. Drop it and setCustomValidity on the visible overlay input until
 * a real option is committed — same class as search-select 2118.
 *
 * Leftover honesty (cycle 2135): leftover typed filter ("zzz", "Hi")
 * must not invent the previous option. Blur used to revert the overlay
 * to the selected label so submit posted Medium as if leftover were
 * abandoned. Leftover junk now stays visible and both the overlay and
 * the native select fail custom validity so submit cannot post the
 * previous value as if the leftover were accepted. Empty leftover on
 * blur restores the selected label (empty is not leftover junk). An
 * exact option label/value on blur commits that option. Growing-list
 * leftover (allow-create) commits as Add "…" — same class as tags
 * leftover token (2131). Escape still cancels to the selected label.
 *
 * Same class as slider leftover readout (2134) and colour leftover
 * hex (2133).
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

  // Permanent options only (not the ephemeral "Add …" create row).
  function options(root) {
    return Array.prototype.slice.call(
      root.querySelectorAll(".dz-combobox-option:not(.dz-combobox-create)"),
    );
  }

  function visibleOptions(root) {
    return Array.prototype.slice
      .call(root.querySelectorAll(".dz-combobox-option"))
      .filter(function (li) {
        return !li.hidden;
      });
  }

  function allowCreate(select) {
    return !!(select && select.hasAttribute("data-dz-allow-create"));
  }

  function ensureCreateRow(root, select) {
    var list = root.querySelector(".dz-combobox-listbox");
    if (!list) return null;
    var create = root.querySelector(".dz-combobox-create");
    if (create) return create;
    var name = select.id || select.name || "dz-combobox";
    create = document.createElement("li");
    create.className = "dz-combobox-option dz-combobox-create";
    create.id = name + "-create";
    create.setAttribute("role", "option");
    create.setAttribute("data-dz-create", "true");
    create.setAttribute("aria-selected", "false");
    create.hidden = true;
    // After permanent options, before the empty-state row.
    var empty = root.querySelector(".dz-combobox-empty");
    if (empty) list.insertBefore(create, empty);
    else list.appendChild(create);
    return create;
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

  // After a commit: default is to *blur* the overlay input so the control
  // feels like a closed select (not a free-text field with an I-beam).
  // Controllable on the native <select> (or enhanced root):
  //   data-dz-focus-after-select="blur"   (default) — leave text-editing mode
  //   data-dz-focus-after-select="keep"   — keep focus for immediate re-filter
  //   data-dz-focus-after-select="select" — keep focus + select-all the label
  //                                        (next keystroke replaces filter)
  function focusAfterSelect(root, select) {
    var raw =
      (select && select.getAttribute("data-dz-focus-after-select")) ||
      root.getAttribute("data-dz-focus-after-select") ||
      "blur";
    return String(raw).toLowerCase();
  }

  function isRequiredCombobox(root) {
    var input = root.querySelector(".dz-combobox-input");
    return !!(input && input.getAttribute("aria-required") === "true");
  }

  function syncRequiredValidity(root) {
    var input = root.querySelector(".dz-combobox-input");
    var select = root.querySelector("select[data-dz-combobox]");
    if (!input || !isRequiredCombobox(root)) return;
    var has = !!(select && String(select.value || "").trim());
    input.setCustomValidity(has ? "" : "Select a value from the list");
  }

  // kind: empty | invalid | ok. Prefix / leftover junk is not a silent
  // commit of the previous option. Exact label or value (case-insensitive)
  // is ok and may carry the matching row for blur-commit.
  function leftoverKind(root, raw) {
    var text = String(raw == null ? "" : raw).trim();
    if (!text) return { kind: "empty" };
    var chosen = selectedLabel(root).trim();
    if (text === chosen) return { kind: "ok" };
    var match = null;
    options(root).forEach(function (o) {
      var label = (o.textContent || "").trim();
      var value = (o.getAttribute("data-dz-value") || "").trim();
      if (
        label.toLowerCase() === text.toLowerCase() ||
        value.toLowerCase() === text.toLowerCase()
      ) {
        match = o;
      }
    });
    if (match) return { kind: "ok", option: match };
    return { kind: "invalid" };
  }

  function leftoverMessage() {
    return "Pick a listed option — leftover text is not a value";
  }

  function syncLeftoverValidity(root, parsed) {
    var input = root.querySelector(".dz-combobox-input");
    var select = root.querySelector("select[data-dz-combobox]");
    if (!input) return;
    if (parsed && parsed.kind === "invalid") {
      var msg = leftoverMessage();
      input.setCustomValidity(msg);
      if (select && select.setCustomValidity) select.setCustomValidity(msg);
      return;
    }
    if (select && select.setCustomValidity) select.setCustomValidity("");
    if (isRequiredCombobox(root)) {
      syncRequiredValidity(root);
    } else {
      input.setCustomValidity("");
    }
  }

  // Commit a choice: write the native <select> value, sync the input
  // display + aria-selected, close, and fire `change` so the form and any
  // listeners react exactly as they did with the bare <select>.
  //
  // Pointerdown on an option uses preventDefault so focus never left the
  // input mid-click (avoids a blur/re-focus reopen race); the commit runs
  // on the following `click` (pointer cancellation). After commit we
  // apply focus-after-select (default blur) so enum picks don't leave the
  // field in free-text edit mode with an I-beam caret.
  // Commit a permanent option (existing or just created).
  function commitValue(root, select, input, value, label) {
    select.value = value;
    options(root).forEach(function (o) {
      var v = o.getAttribute("data-dz-value") || "";
      o.setAttribute("aria-selected", v === value ? "true" : "false");
    });
    input.value = label;
    setOpen(root, false);
    filter(root, "");
    select.dispatchEvent(new Event("change", { bubbles: true }));
    syncLeftoverValidity(root, { kind: "ok" });

    var mode = focusAfterSelect(root, select);
    if (mode === "keep" || mode === "focus") return;
    if (mode === "select" || mode === "select-all") {
      try {
        input.focus();
        input.select();
      } catch (e) {
        /* ignore */
      }
      return;
    }
    try {
      input.blur();
    } catch (e2) {
      /* ignore */
    }
  }

  // Growing-list recipe: append a new <option> to the native select + list
  // row, then commit it. Same Hyperpart as a fixed list — allow-create only.
  function createAndChoose(root, rawLabel) {
    var select = root.querySelector("select[data-dz-combobox]");
    var input = root.querySelector(".dz-combobox-input");
    var list = root.querySelector(".dz-combobox-listbox");
    if (!select || !input || !list) return;
    var label = String(rawLabel || "").trim();
    if (!label) return;

    var value = label;
    var existing = null;
    Array.prototype.forEach.call(select.options, function (opt) {
      if (
        opt.value === value ||
        opt.textContent.trim().toLowerCase() === label.toLowerCase()
      ) {
        existing = opt;
      }
    });
    if (existing) {
      var matchLi = null;
      options(root).forEach(function (o) {
        if (o.getAttribute("data-dz-value") === existing.value) matchLi = o;
      });
      if (matchLi) {
        commitValue(root, select, input, existing.value, existing.textContent);
        return;
      }
      value = existing.value;
      label = existing.textContent;
    } else {
      var opt = document.createElement("option");
      opt.value = value;
      opt.textContent = label;
      select.appendChild(opt);

      var name = select.id || select.name || "dz-combobox";
      var li = document.createElement("li");
      li.className = "dz-combobox-option";
      li.id = name + "-opt-" + options(root).length;
      li.setAttribute("role", "option");
      li.setAttribute("data-dz-value", value);
      li.setAttribute("aria-selected", "false");
      li.textContent = label;
      var create = root.querySelector(".dz-combobox-create");
      if (create) list.insertBefore(li, create);
      else {
        var empty = root.querySelector(".dz-combobox-empty");
        if (empty) list.insertBefore(li, empty);
        else list.appendChild(li);
      }
    }
    commitValue(root, select, input, value, label);
  }

  function choose(root, li) {
    var select = root.querySelector("select[data-dz-combobox]");
    var input = root.querySelector(".dz-combobox-input");
    if (!select || !input || !li) return;
    if (
      li.hasAttribute("data-dz-create") ||
      li.classList.contains("dz-combobox-create")
    ) {
      createAndChoose(root, li.getAttribute("data-dz-value") || input.value);
      return;
    }
    commitValue(
      root,
      select,
      input,
      li.getAttribute("data-dz-value") || "",
      li.textContent,
    );
  }

  function filter(root, query) {
    var select = root.querySelector("select[data-dz-combobox]");
    var qRaw = query.trim();
    var q = qRaw.toLowerCase();
    var empty = root.querySelector(".dz-combobox-empty");
    var anyVisible = false;
    var exact = false;
    options(root).forEach(function (li) {
      var text = li.textContent.toLowerCase();
      var match = !q || text.indexOf(q) !== -1;
      li.hidden = !match;
      if (match) anyVisible = true;
      if (text === q) exact = true;
    });

    // Growing list: offer "Add «query»" when allow-create and no exact match.
    var create = root.querySelector(".dz-combobox-create");
    if (allowCreate(select)) {
      create = ensureCreateRow(root, select);
      if (qRaw && !exact) {
        create.hidden = false;
        create.setAttribute("data-dz-value", qRaw);
        create.textContent = 'Add "' + qRaw + '"';
        anyVisible = true;
      } else {
        create.hidden = true;
        create.removeAttribute("data-dz-value");
      }
    } else if (create) {
      create.hidden = true;
    }

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
    // Name the input + listbox BY the label span (aria-labelledby), never a
    // copy of its text: the span carries the required marker, and a copied
    // aria-label would read "Type*(required)" (#1843, 3.3.2).
    var field = select.closest(".dz-field");
    var labelSpan = field ? field.querySelector(".dz-field__label") : null;
    if (labelSpan && !labelSpan.id) labelSpan.id = name + "-label";
    var labelId = labelSpan ? labelSpan.id : "";

    // The leading value="" option is the placeholder prompt, not a choice.
    var opts = Array.prototype.slice.call(select.options);
    var placeholderOpt = opts.length && opts[0].value === "" ? opts[0] : null;
    var choices = placeholderOpt ? opts.slice(1) : opts;
    var placeholder = placeholderOpt ? placeholderOpt.textContent : "";

    var input = document.createElement("input");
    input.type = "text";
    input.id = name + "-input";
    input.className = "dz-combobox-input";
    input.setAttribute("role", "combobox");
    input.setAttribute("autocomplete", "off");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", listId);
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-haspopup", "listbox");
    if (labelId) input.setAttribute("aria-labelledby", labelId);
    if (placeholder) input.setAttribute("placeholder", placeholder);
    var wasRequired = select.hasAttribute("required");
    if (wasRequired) {
      input.setAttribute("aria-required", "true");
    }

    var list = document.createElement("ul");
    list.className = "dz-combobox-listbox";
    list.id = listId;
    list.setAttribute("role", "listbox");
    // Not a Tab stop (#1843, 2.4.3): a scrollable <ul> is keyboard-focusable
    // in modern engines, which made the listbox a second stop after the
    // input. Arrow keys move the active descendant; -1 keeps it out of the
    // tab order while a click on its scrollbar stays inside the widget.
    list.setAttribute("tabindex", "-1");
    if (labelId) list.setAttribute("aria-labelledby", labelId);

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
    // AT (set above) and setCustomValidity until a real option is committed
    // (cycle 2120). The no-JS path still uses native `required` on the
    // unhidden select.
    select.removeAttribute("required");
    select.parentNode.insertBefore(root, select);
    select.setAttribute("tabindex", "-1");
    root.appendChild(input);
    root.appendChild(select);
    root.appendChild(list);
    root.setAttribute("data-dz-enhanced", "");
    // The label's `for=` pointed at the native select, now display:none —
    // point it at the visible input so the label focuses the real control.
    if (field && field.tagName === "LABEL" && field.htmlFor === select.id) {
      field.htmlFor = input.id;
    }
    if (wasRequired) syncRequiredValidity(root);
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

  // Focus has left the widget: settle the typed text, close the listbox.
  function settle(root) {
    var input = root.querySelector(".dz-combobox-input");
    if (!input) return;
    var parsed = leftoverKind(root, input.value);
    var select = root.querySelector("select[data-dz-combobox]");
    if (parsed.kind === "empty") {
      input.value = selectedLabel(root);
      syncLeftoverValidity(root, { kind: "ok" });
    } else if (parsed.kind === "ok" && parsed.option) {
      choose(root, parsed.option);
      return;
    } else if (parsed.kind === "invalid" && allowCreate(select)) {
      createAndChoose(root, input.value);
      return;
    } else if (parsed.kind === "invalid") {
      // leftover junk stays visible — must not vanish / revert
      // (never invent the previous option as if leftover were accepted)
      syncLeftoverValidity(root, parsed);
    } else {
      input.value = selectedLabel(root);
      syncLeftoverValidity(root, { kind: "ok" });
    }
    setOpen(root, false);
  }

  // Watch focus leaving ANY part of the widget (input or listbox), not only
  // the input (#1843, 2.4.11): focus that left via the listbox used to keep
  // `data-dz-open`, and the z-index:50 listbox covered the fields below.
  document.addEventListener("focusout", function (evt) {
    var root =
      evt.target.closest &&
      evt.target.closest(".dz-combobox[data-dz-enhanced]");
    if (!root) return;
    var next = evt.relatedTarget;
    if (next && root.contains(next)) return; // moving within the widget
    if (next) {
      // Focus went to another control (Tab / Shift+Tab): close now so the
      // listbox never sits over the newly focused field.
      settle(root);
      return;
    }
    // No destination (pointer on a non-focusable spot, window blur): short
    // grace, then settle unless focus came back.
    setTimeout(function () {
      if (root.contains(document.activeElement)) return; // re-focused
      settle(root);
    }, 200);
  });

  document.addEventListener("input", function (evt) {
    var input = evt.target.closest && evt.target.closest(".dz-combobox-input");
    if (!input) return;
    var root = input.closest(".dz-combobox");
    if (!root) return;
    setOpen(root, true);
    filter(root, input.value);
    syncLeftoverValidity(root, leftoverKind(root, input.value));
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
      var selectEl = root.querySelector("select[data-dz-combobox]");
      if (active && !active.hidden) {
        evt.preventDefault();
        choose(root, active);
      } else if (allowCreate(selectEl) && input.value.trim()) {
        // No highlighted row (e.g. empty list + create hidden race) — still create.
        evt.preventDefault();
        createAndChoose(root, input.value);
      }
    } else if (evt.key === "Escape") {
      if (root.hasAttribute("data-dz-open")) {
        evt.preventDefault();
        input.value = selectedLabel(root);
        syncLeftoverValidity(root, { kind: "ok" });
        setOpen(root, false);
      }
    }
  });

  // pointerdown (capture) only keeps focus on the combobox input —
  // preventDefault stops the input blurring mid-press, which would
  // otherwise force a re-focus that re-opens the listbox (see choose()
  // note). The commit itself waits for `click` (WCAG 2.5.2 Pointer
  // Cancellation, #1842): pressing on a row and moving off before
  // release lands the click on a common ancestor, not the row, so
  // nothing is chosen.
  document.addEventListener(
    "pointerdown",
    function (evt) {
      var li = evt.target.closest && evt.target.closest(".dz-combobox-option");
      if (!li || li.hidden || !li.closest(".dz-combobox")) return;
      evt.preventDefault();
    },
    true,
  );

  document.addEventListener(
    "click",
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
