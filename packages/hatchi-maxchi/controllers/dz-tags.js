/* HYPERPART: tags */
/*
 * dz-tags — HM-native multi-value chips input (HMC-018 slice 2), the
 * vanilla replacement for TomSelect's `widget=tags` mount.
 *
 * Progressive enhancement, delegated from the document, state-in-DOM.
 * The server renders a plain `<input type="text" data-dz-tags>` whose value
 * is a COMMA-JOINED tag string (e.g. "alpha,beta") — fully usable with JS
 * OFF (the user types "a, b, c"; the server splits on comma), and it is the
 * submitted value + native `required`. Seeded values (SSR / gallery demos)
 * enhance on DOM ready so chips paint without a click; empty fields still
 * enhance on first interaction (pointerdown / focusin). The chips UI is a
 * `role="list"` of removable chips + a borderless text entry, wrapped in a
 * `.dz-tags` root. The native input STAYS in the DOM (still submits) but
 * leaves the visual layer; on every add/remove we rewrite its `.value` to
 * the comma-joined chip list and fire `change`, so the form + any listeners
 * see the exact same control they always did — the submit contract never
 * changes.
 *
 * Enhance-once is marked with `data-dz-enhanced` on the root. a11y: the
 * chips are a `role="list"` of `role="listitem"` chips, each with a
 * focusable × button labelled "Remove {tag}"; the entry gets an aria-label
 * from the field label; add/remove is announced through a visually-hidden
 * `aria-live="polite"` region.
 *
 * Keyboard: type + Enter or comma creates a chip (trim / dedup / skip
 * empty); paste splits on comma / newline; Backspace on an empty entry
 * removes the last chip; the × button removes its chip (Enter/Space fire
 * it). Tab reaches the entry and each × like any control.
 */
(function () {
  "use strict";

  // Parse a comma-joined value string into an ordered, de-duplicated,
  // empty-stripped list — the shape the server splits back apart.
  function parseTags(raw) {
    var out = [];
    var seen = Object.create(null);
    (raw || "").split(",").forEach(function (part) {
      var tag = part.trim();
      if (!tag || seen[tag]) return;
      seen[tag] = true;
      out.push(tag);
    });
    return out;
  }

  function chips(root) {
    return Array.prototype.slice.call(root.querySelectorAll(".dz-tags-chip"));
  }

  function chipValues(root) {
    return chips(root).map(function (c) {
      return c.getAttribute("data-dz-value") || "";
    });
  }

  // Rewrite the native input (the submitted value) to the comma-joined chip
  // list and fire `change`, so the form + any listeners react exactly as
  // they did with the bare input.
  function sync(root) {
    var native = root.querySelector("input[data-dz-tags]");
    if (!native) return;
    native.value = chipValues(root).join(",");
    native.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function announce(root, msg) {
    var live = root.querySelector("[data-dz-tags-live]");
    if (live) live.textContent = msg;
  }

  function makeChip(value) {
    var chip = document.createElement("span");
    chip.className = "dz-tags-chip";
    chip.setAttribute("role", "listitem");
    chip.setAttribute("data-dz-value", value);

    var label = document.createElement("span");
    label.className = "dz-tags-chip-label";
    label.textContent = value;

    var remove = document.createElement("button");
    remove.type = "button";
    remove.className = "dz-tags-remove";
    remove.setAttribute("aria-label", "Remove " + value);
    remove.textContent = "×"; // ×

    chip.appendChild(label);
    chip.appendChild(remove);
    return chip;
  }

  // Add one tag: trim, skip empty, skip duplicate; returns whether it landed.
  function addTag(root, raw) {
    var value = (raw || "").trim();
    if (!value) return false;
    if (chipValues(root).indexOf(value) !== -1) return false;
    root.querySelector(".dz-tags-list").appendChild(makeChip(value));
    sync(root);
    announce(root, "Added " + value);
    return true;
  }

  // Split a pasted / typed blob on commas + newlines and add each token.
  function addMany(root, text) {
    (text || "").split(/[,\n\r]+/).forEach(function (part) {
      addTag(root, part);
    });
  }

  function removeChip(root, chip) {
    var value = chip.getAttribute("data-dz-value") || "";
    chip.remove();
    sync(root);
    announce(root, "Removed " + value);
    focusEntry(root);
  }

  function focusEntry(root) {
    var entry = root.querySelector(".dz-tags-entry");
    if (entry) entry.focus();
  }

  // Build the chips overlay once, from the server-rendered native input.
  function enhance(native) {
    var root = document.createElement("div");
    root.className = "dz-tags";

    // Field label: the substrate wraps the widget in
    // `<label class="dz-field"><span class="dz-field__label">…</span>…</label>`.
    var labelSpan = native.closest(".dz-field")
      ? native.closest(".dz-field").querySelector(".dz-field__label")
      : null;
    var labelText = labelSpan ? labelSpan.textContent.trim() : "";

    var list = document.createElement("span");
    list.className = "dz-tags-list";
    list.setAttribute("role", "list");
    if (labelText) list.setAttribute("aria-label", labelText);

    var entry = document.createElement("input");
    entry.type = "text";
    entry.className = "dz-tags-entry";
    entry.setAttribute("autocomplete", "off");
    if (labelText) entry.setAttribute("aria-label", labelText);
    var placeholder = native.getAttribute("placeholder");
    if (placeholder) entry.setAttribute("placeholder", placeholder);

    var live = document.createElement("span");
    live.className = "visually-hidden";
    live.setAttribute("data-dz-tags-live", "");
    live.setAttribute("aria-live", "polite");
    live.setAttribute("role", "status");

    // Mount: the native input stays in the DOM as the submit value (+ no-JS
    // fallback) but the CSS hides it off `data-dz-enhanced`. Drop `required`
    // off the now-hidden control (a hidden required field blocks submit with
    // an unfocusable browser error and no visible bubble); the visible entry
    // carries `aria-required` for AT, server-side validation is the backstop,
    // and the no-JS path keeps native `required` on the unhidden input.
    if (native.hasAttribute("required")) {
      native.removeAttribute("required");
      entry.setAttribute("aria-required", "true");
    }
    if (native.getAttribute("aria-invalid") === "true") {
      root.setAttribute("aria-invalid", "true");
    }

    native.parentNode.insertBefore(root, native);
    native.setAttribute("tabindex", "-1");
    root.appendChild(native);
    root.appendChild(list);
    root.appendChild(entry);
    root.appendChild(live);

    // Seed chips from the native input's current comma value, then normalise
    // the native value to the parsed (trimmed / deduped) form. No `change`
    // fires here — only user mutations sync.
    parseTags(native.value).forEach(function (value) {
      list.appendChild(makeChip(value));
    });
    native.value = chipValues(root).join(",");

    root.setAttribute("data-dz-enhanced", "");
    return root;
  }

  function rootFor(native) {
    return native.closest(".dz-tags[data-dz-enhanced]") || enhance(native);
  }

  // ── Seeded values → chips without interaction ───────────────────────
  // Gallery demos and SSR fields with a non-empty comma value should show
  // chips on first paint. Empty fields stay progressive (enhance on first
  // pointer/focus). Also re-run after htmx swaps bring in new markup.
  function enhanceSeeded() {
    document.querySelectorAll("input[data-dz-tags]").forEach(function (native) {
      if (native.closest(".dz-tags[data-dz-enhanced]")) return;
      if (parseTags(native.value).length) enhance(native);
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enhanceSeeded);
  } else {
    enhanceSeeded();
  }
  document.addEventListener("htmx:afterSettle", enhanceSeeded);

  // ── Enhance-on-first-interaction (empty / not-yet-enhanced) ──────────
  // A pointerdown on the bare input would focus it; enhance first and swallow
  // the event, then focus our entry.
  document.addEventListener(
    "pointerdown",
    function (evt) {
      var native =
        evt.target.closest && evt.target.closest("input[data-dz-tags]");
      if (!native || native.closest(".dz-tags[data-dz-enhanced]")) return;
      evt.preventDefault();
      focusEntry(rootFor(native));
    },
    true,
  );

  // Keyboard tab-in onto the bare input enhances too.
  document.addEventListener("focusin", function (evt) {
    var native =
      evt.target.closest && evt.target.closest("input[data-dz-tags]");
    if (native && !native.closest(".dz-tags[data-dz-enhanced]")) {
      focusEntry(rootFor(native));
    }
  });

  // Clicking the box background (not a chip, its × button, or the entry)
  // focuses the entry — the whole box behaves like one input.
  document.addEventListener("pointerdown", function (evt) {
    var root =
      evt.target.closest && evt.target.closest(".dz-tags[data-dz-enhanced]");
    if (!root) return;
    if (
      evt.target.closest(".dz-tags-chip") ||
      evt.target.closest(".dz-tags-entry")
    ) {
      return;
    }
    evt.preventDefault();
    focusEntry(root);
  });

  document.addEventListener("keydown", function (evt) {
    var entry = evt.target.closest && evt.target.closest(".dz-tags-entry");
    if (!entry) return;
    var root = entry.closest(".dz-tags");
    if (!root) return;

    if (evt.key === "Enter" || evt.key === ",") {
      // Enter / comma commit the current token (never let the comma type into
      // the entry, and never let Enter submit the form from here).
      if (entry.value.trim()) {
        evt.preventDefault();
        addTag(root, entry.value);
        entry.value = "";
      } else if (evt.key === ",") {
        evt.preventDefault();
      }
    } else if (evt.key === "Backspace" && entry.value === "") {
      var cs = chips(root);
      if (cs.length) {
        evt.preventDefault();
        removeChip(root, cs[cs.length - 1]);
      }
    }
  });

  document.addEventListener("paste", function (evt) {
    var entry = evt.target.closest && evt.target.closest(".dz-tags-entry");
    if (!entry) return;
    var root = entry.closest(".dz-tags");
    if (!root) return;
    var data = evt.clipboardData || window.clipboardData;
    var text = data ? data.getData("text") : "";
    // A single-token paste (no separators) falls through to normal typing —
    // the user commits it with Enter. Multi-token paste splits into chips.
    if (text.indexOf(",") === -1 && text.indexOf("\n") === -1) return;
    evt.preventDefault();
    addMany(root, text);
    entry.value = "";
  });

  document.addEventListener("click", function (evt) {
    var btn = evt.target.closest && evt.target.closest(".dz-tags-remove");
    if (!btn) return;
    var root = btn.closest(".dz-tags");
    var chip = btn.closest(".dz-tags-chip");
    if (root && chip) removeChip(root, chip);
  });
})();
