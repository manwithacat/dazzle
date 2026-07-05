/*
 * dz-grid-edit — inline cell editing, a DAZZLE EXTENSION on the HM grid
 * primitive's seams (convergence C2.3; the dzTable Alpine implementation is
 * deleted in C3 — its commit PATCHed `/api/{EntityName}/…` while the field
 * route mounts at `/{plural}/…`, so every commit silently 404'd).
 *
 * The ratified seam design: the CELL owns its edit affordance; the grid
 * stays out of the way. One display span per editable cell carries the
 * contract; the controller builds the editor input on demand, and the typed
 * BUFFER lives on the grid root (`root._dzEdit`) — out of the morph path —
 * so an in-flight edit survives a tbody swap (poll refresh, re-sort): the
 * before-swap hook captures the input's live value, the after-swap hook
 * re-opens the editor on the (morph-keyed) row and restores the buffer.
 *
 * Contract:
 *   - root:   `[data-dz-grid]` with `data-dz-grid-edit-url` = the entity API
 *             base; commits PUT `{base}/{rowId}` with a single-field JSON
 *             body — the entity's STANDARD gated update route (permit +
 *             scope pre-read + destination-scope + schema validation).
 *   - cell:   `[data-dz-grid-edit="<col>"]` (the display span) with
 *             `data-dz-edit-kind` (text|date|bool|select),
 *             `data-dz-edit-value` (the raw value), `data-dz-edit-label`
 *             (a11y), and for selects `data-dz-edit-options`
 *             (JSON [[value,label],…]).
 *   - open:   dblclick the span (dzTable parity; pointer-first — a keyboard
 *             entry point is tracked follow-up work).
 *   - keys:   Enter commits (text/date), Escape cancels, Tab / Shift-Tab
 *             commits then advances to the next/previous editable cell
 *             (wrapping to the adjacent row); bool/select commit on change.
 *   - state:  `is-saving` / `is-error` classes on the row (the same classes
 *             the Alpine `:class` bind used); a failed commit keeps the
 *             editor open with the server error in its `title`.
 *   - after a successful commit the controller fires `dz-grid:refresh` on
 *             the tbody — the server re-renders rows, so rich display chrome
 *             (badges, dates) stays server-owned.
 */
(function () {
  "use strict";

  function rootOf(el) {
    return el.closest ? el.closest("[data-dz-grid]") : null;
  }

  function cellSpan(root, rowId, colKey) {
    var row = root.querySelector('[data-dz-row-id="' + rowId + '"]');
    return row && row.querySelector('[data-dz-grid-edit="' + colKey + '"]');
  }

  function buildEditor(edit) {
    var el;
    if (edit.kind === "bool") {
      el = document.createElement("input");
      el.type = "checkbox";
      el.className = "dz-inline-edit-checkbox";
      el.checked = edit.value === "true";
    } else if (edit.kind === "select") {
      el = document.createElement("select");
      el.className = "dz-inline-edit-input dz-inline-edit-select";
      var opts = [];
      try {
        opts = JSON.parse(edit.options || "[]");
      } catch (e) {
        opts = [];
      }
      for (var i = 0; i < opts.length; i++) {
        var o = document.createElement("option");
        o.value = String(opts[i][0]);
        o.textContent = String(opts[i][1]);
        if (String(opts[i][0]) === edit.value) o.selected = true;
        el.appendChild(o);
      }
    } else {
      el = document.createElement("input");
      el.type = edit.kind === "date" ? "date" : "text";
      el.className = "dz-inline-edit-input";
      el.value = edit.value;
    }
    el.setAttribute("data-dz-grid-editor", "");
    el.setAttribute("aria-label", "Edit " + (edit.label || edit.colKey));
    return el;
  }

  // Project the root's edit state into the DOM: hide the display span, put
  // the editor next to it, focus. Returns false when the target cell is gone
  // (e.g. the row was filtered away by the swap that interrupted the edit).
  function openEditor(root) {
    var edit = root._dzEdit;
    if (!edit) return false;
    var span = cellSpan(root, edit.rowId, edit.colKey);
    if (!span) return false;
    var editor = buildEditor(edit);
    span.style.display = "none";
    span.parentNode.insertBefore(editor, span.nextSibling);
    editor.focus();
    if (editor.select && edit.kind === "text") editor.select();
    return true;
  }

  function closeEditor(root) {
    var editor = root.querySelector("[data-dz-grid-editor]");
    if (editor) {
      var span = editor.previousSibling;
      editor.parentNode.removeChild(editor);
      if (span && span.style) span.style.display = "";
    }
    root._dzEdit = null;
  }

  function editorValue(editor, kind) {
    return kind === "bool" ? String(editor.checked) : editor.value;
  }

  function rowOf(root, rowId) {
    return root.querySelector('[data-dz-row-id="' + rowId + '"]');
  }

  // The row's editable columns, in DOM order — Tab-advance derives the ring
  // from the markup itself (no config list to drift).
  function editableKeys(root, rowId) {
    var row = rowOf(root, rowId);
    if (!row) return [];
    var spans = row.querySelectorAll("[data-dz-grid-edit]");
    var keys = [];
    for (var i = 0; i < spans.length; i++) {
      keys.push(spans[i].getAttribute("data-dz-grid-edit"));
    }
    return keys;
  }

  function nextEditable(root, rowId, colKey, direction) {
    var keys = editableKeys(root, rowId);
    var at = keys.indexOf(colKey);
    if (at < 0) return null;
    if (direction === "next" && at < keys.length - 1) {
      return { rowId: rowId, colKey: keys[at + 1] };
    }
    if (direction === "prev" && at > 0) {
      return { rowId: rowId, colKey: keys[at - 1] };
    }
    // Wrap to the adjacent row's first/last editable cell.
    var rows = root.querySelectorAll("[data-dz-row-id]");
    var ids = [];
    for (var i = 0; i < rows.length; i++) {
      ids.push(rows[i].getAttribute("data-dz-row-id"));
    }
    var rowAt = ids.indexOf(rowId);
    if (direction === "next" && rowAt >= 0 && rowAt < ids.length - 1) {
      var nk = editableKeys(root, ids[rowAt + 1]);
      return nk.length ? { rowId: ids[rowAt + 1], colKey: nk[0] } : null;
    }
    if (direction === "prev" && rowAt > 0) {
      var pk = editableKeys(root, ids[rowAt - 1]);
      return pk.length
        ? { rowId: ids[rowAt - 1], colKey: pk[pk.length - 1] }
        : null;
    }
    return null;
  }

  function startEdit(root, span) {
    if (root._dzEdit) closeEditor(root); // one edit at a time
    var row = span.closest("[data-dz-row-id]");
    if (!row) return;
    root._dzEdit = {
      rowId: row.getAttribute("data-dz-row-id"),
      colKey: span.getAttribute("data-dz-grid-edit"),
      kind: span.getAttribute("data-dz-edit-kind") || "text",
      value: span.getAttribute("data-dz-edit-value") || "",
      label: span.getAttribute("data-dz-edit-label") || "",
      options: span.getAttribute("data-dz-edit-options") || "",
    };
    openEditor(root);
  }

  function commit(root, value, andThen) {
    var edit = root._dzEdit;
    if (!edit || edit.saving) return;
    edit.saving = true;
    var row = rowOf(root, edit.rowId);
    if (row) {
      row.classList.add("is-saving");
      row.classList.remove("is-error");
    }
    var base = root.getAttribute("data-dz-grid-edit-url") || "";
    // Commit through the entity's STANDARD update route (PUT, all-optional
    // update schema + exclude_unset = partial update) with a single-field
    // JSON body — full RBAC (permit + scope pre-read + #1312 destination
    // scope), storage verification, and schema validation for free. (The old
    // dzTable posted a bespoke /field/ route that was never mounted.)
    var payload = {};
    payload[edit.colKey] = edit.kind === "bool" ? value === "true" : value;
    // Raw fetch bypasses dz-csrf.js (which wires the token onto htmx requests
    // only), so echo the double-submit cookie here — without it the commit
    // 403s wherever the Sec-Fetch-Site origin gate is absent (Safari <16.4).
    var csrf =
      (document.cookie.match(/(?:^|; )dazzle_csrf=([^;]*)/) || [])[1] || "";
    var headers = { "Content-Type": "application/json" };
    if (csrf) headers["X-CSRF-Token"] = decodeURIComponent(csrf);
    fetch(base + "/" + encodeURIComponent(edit.rowId), {
      method: "PUT",
      headers: headers,
      body: JSON.stringify(payload),
      credentials: "same-origin",
    })
      .then(function (resp) {
        if (row) row.classList.remove("is-saving");
        if (!resp.ok) {
          return resp.text().then(function (text) {
            edit.saving = false;
            if (row) row.classList.add("is-error");
            var editor = root.querySelector("[data-dz-grid-editor]");
            if (editor) editor.title = text || "Error " + resp.status;
            return;
          });
        }
        closeEditor(root);
        // Server-owned rendering: refresh the rows so badge/date chrome is
        // re-rendered rather than patched client-side.
        var body = root.querySelector("[data-dz-grid-body]");
        if (body) {
          body.dispatchEvent(
            new CustomEvent("dz-grid:refresh", { bubbles: true }),
          );
        }
        if (andThen) andThen();
      })
      .catch(function (err) {
        edit.saving = false;
        if (row) {
          row.classList.remove("is-saving");
          row.classList.add("is-error");
        }
        var editor = root.querySelector("[data-dz-grid-editor]");
        if (editor) editor.title = (err && err.message) || "Network error";
      });
  }

  document.addEventListener("dblclick", function (evt) {
    var span =
      evt.target &&
      evt.target.closest &&
      evt.target.closest("[data-dz-grid-edit]");
    if (!span) return;
    var root = rootOf(span);
    if (!root || !root.hasAttribute("data-dz-grid-edit-url")) return;
    startEdit(root, span);
  });

  document.addEventListener("change", function (evt) {
    var t = evt.target;
    if (!t || !t.matches || !t.matches("[data-dz-grid-editor]")) return;
    var root = rootOf(t);
    if (!root || !root._dzEdit) return;
    var kind = root._dzEdit.kind;
    // bool / select / date commit on change (dzTable parity); text commits
    // on Enter/Tab so a blur-out mid-thought doesn't write.
    if (kind === "bool" || kind === "select" || kind === "date") {
      commit(root, editorValue(t, kind));
    }
  });

  document.addEventListener("keydown", function (evt) {
    var t = evt.target;
    if (!t || !t.matches || !t.matches("[data-dz-grid-editor]")) return;
    var root = rootOf(t);
    if (!root || !root._dzEdit) return;
    var edit = root._dzEdit;
    if (evt.key === "Escape") {
      evt.preventDefault();
      closeEditor(root);
    } else if (evt.key === "Enter" && edit.kind !== "select") {
      evt.preventDefault();
      commit(root, editorValue(t, edit.kind));
    } else if (evt.key === "Tab") {
      evt.preventDefault();
      var target = nextEditable(
        root,
        edit.rowId,
        edit.colKey,
        evt.shiftKey ? "prev" : "next",
      );
      commit(root, editorValue(t, edit.kind), function () {
        if (!target) return;
        var span = cellSpan(root, target.rowId, target.colKey);
        if (span) startEdit(root, span);
      });
    }
  });

  // Morph safety: capture the live buffer before a swap replaces the editor,
  // re-project it after. If the row is gone (filtered away), the edit drops.
  function onBeforeSwap() {
    var grids = document.querySelectorAll("[data-dz-grid]");
    for (var i = 0; i < grids.length; i++) {
      var edit = grids[i]._dzEdit;
      if (!edit) continue;
      var editor = grids[i].querySelector("[data-dz-grid-editor]");
      if (editor) edit.value = editorValue(editor, edit.kind);
    }
  }
  document.addEventListener("htmx:before:swap", onBeforeSwap); // htmx 4
  document.addEventListener("htmx:beforeSwap", onBeforeSwap); // htmx ≤2

  function onAfterSwap() {
    var grids = document.querySelectorAll("[data-dz-grid]");
    for (var i = 0; i < grids.length; i++) {
      var edit = grids[i]._dzEdit;
      if (!edit || edit.saving) continue;
      // The swap destroyed the editor element; re-open on the morph-keyed
      // row with the captured buffer (or drop if the row vanished).
      var stale = grids[i].querySelector("[data-dz-grid-editor]");
      if (stale) stale.parentNode.removeChild(stale);
      if (!openEditor(grids[i])) grids[i]._dzEdit = null;
    }
  }
  document.addEventListener("htmx:after:swap", onAfterSwap); // htmx 4
  document.addEventListener("htmx:afterSwap", onAfterSwap); // htmx ≤2
})();
