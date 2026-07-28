/* HYPERPART: kanban */
/*
 * dz-kanban — board rearrange controller (Linear-class status move on HTMX).
 *
 * SPA technique (dnd-kit / Linear board): drag card → legal column → PATCH
 * status in a client store → re-render. HTMX recontext:
 *   1. SSR stamps capability in the DOM (rearrange attrs only when UPDATE
 *      is permitted; per-card data-dz-allowed-to from the state machine).
 *   2. Controller validates the drop against those attrs (hint only).
 *   3. PUT the existing entity update endpoint with {status_field: to}.
 *   4. GET-refresh the workspace region (data-dz-kanban-src) so the server
 *      owns the new board HTML — grid bulk-refresh pattern, morph-safe.
 *
 * Contract (when rearrange is on):
 *   - board:  [data-dz-kanban-board][data-dz-kanban-rearrange="status"]
 *             data-dz-kanban-status-field, data-dz-kanban-api,
 *             data-dz-kanban-src (region refresh URL)
 *   - card:   [data-dz-kanban-card][data-dz-entity-id][data-dz-from-state]
 *             [data-dz-allowed-to="a b c"]  (space-separated; empty = inert)
 *             draggable="true" when allowed_to non-empty
 *   - stack:  [data-dz-kanban-stack][data-dz-to-state]
 *   - move:   [data-dz-kanban-move] <select> keyboard parity
 *
 * No Alpine. Document-delegated. Survives morph (re-reads attrs each event).
 */
(function () {
  "use strict";

  var DRAG_THRESHOLD_PX = 6;
  var MIME = "application/x-dz-kanban-card";

  function boardOf(el) {
    return el && el.closest
      ? el.closest("[data-dz-kanban-board][data-dz-kanban-rearrange]")
      : null;
  }

  function parseAllowed(card) {
    var raw = (card.getAttribute("data-dz-allowed-to") || "").trim();
    if (!raw) return [];
    return raw.split(/\s+/).filter(Boolean);
  }

  function canDrop(card, toState) {
    if (!toState) return false;
    var from = card.getAttribute("data-dz-from-state") || "";
    if (toState === from) return false;
    return parseAllowed(card).indexOf(toState) !== -1;
  }

  function csrfHeaders() {
    var headers = {
      "Content-Type": "application/json",
      Accept: "application/json",
    };
    // Prefer dazzle csrf helper when present (dz-csrf / window.dz).
    try {
      var meta = document.querySelector('meta[name="csrf-token"]');
      if (meta && meta.content) headers["X-CSRF-Token"] = meta.content;
      var m = document.cookie.match(/(?:^|;\s*)dazzle_csrf=([^;]+)/);
      if (m) headers["X-CSRF-Token"] = decodeURIComponent(m[1]);
    } catch (_) {
      /* ignore */
    }
    return headers;
  }

  function announce(board, msg) {
    var live = board.querySelector("[data-dz-kanban-announce]");
    if (live) live.textContent = msg;
  }

  function regionTarget(board) {
    return board.closest("[data-dz-region]") || board;
  }

  function refreshBoard(board) {
    var src = board.getAttribute("data-dz-kanban-src") || "";
    if (!src) {
      // Fallback: full page reload if host forgot src (still better than silent).
      if (typeof window !== "undefined" && window.location)
        window.location.reload();
      return;
    }
    var target = regionTarget(board);
    // Prefer outerHTML when replacing the board or a region shell so we
    // never nest a board inside itself (gallery mock has no htmx.ajax).
    var useOuter =
      target === board ||
      target.hasAttribute("data-dz-region") ||
      target.hasAttribute("data-dz-kanban-board");
    if (window.htmx && typeof window.htmx.ajax === "function") {
      window.htmx.ajax("GET", src, {
        target: target,
        swap: useOuter ? "outerHTML" : "innerHTML",
        headers: { "HX-Request": "true" },
      });
      return;
    }
    // No htmx: fetch + replace (gallery / tests).
    fetch(src, {
      headers: { "HX-Request": "true", Accept: "text/html" },
      credentials: "same-origin",
    })
      .then(function (r) {
        if (!r.ok) throw new Error("refresh " + r.status);
        return r.text();
      })
      .then(function (html) {
        if (useOuter) {
          target.outerHTML = html;
        } else {
          target.innerHTML = html;
        }
      })
      .catch(function () {
        announce(board, "Board refresh failed");
      });
  }

  function putStatus(board, card, toState) {
    var api = (board.getAttribute("data-dz-kanban-api") || "").replace(
      /\/$/,
      "",
    );
    var field = board.getAttribute("data-dz-kanban-status-field") || "status";
    var id = card.getAttribute("data-dz-entity-id") || "";
    if (!api || !id) return Promise.reject(new Error("missing api/id"));
    var body = {};
    body[field] = toState;
    card.classList.add("is-moving");
    board.classList.add("is-busy");
    announce(board, "Moving card…");
    return fetch(api + "/" + encodeURIComponent(id), {
      method: "PUT",
      headers: csrfHeaders(),
      credentials: "same-origin",
      body: JSON.stringify(body),
    }).then(function (r) {
      card.classList.remove("is-moving");
      board.classList.remove("is-busy");
      if (!r.ok) {
        announce(board, "Move failed (" + r.status + ")");
        throw new Error("put " + r.status);
      }
      announce(board, "Moved to " + toState.replace(/_/g, " "));
      refreshBoard(board);
    });
  }

  // ── Drag (HTML5 DnD — progressive enhancement; keyboard uses <select>) ──

  var dragState = null;

  document.addEventListener("dragstart", function (e) {
    var card =
      e.target && e.target.closest
        ? e.target.closest("[data-dz-kanban-card][draggable='true']")
        : null;
    if (!card) return;
    // Don't start drag from hub drill links.
    if (
      e.target.closest &&
      e.target.closest(
        "a[data-dz-kanban-drill], a, button, select, input, textarea, label",
      )
    ) {
      e.preventDefault();
      return;
    }
    var board = boardOf(card);
    if (!board) return;
    if (!parseAllowed(card).length) {
      e.preventDefault();
      return;
    }
    dragState = {
      card: card,
      board: board,
      startX: e.clientX,
      startY: e.clientY,
    };
    card.classList.add("is-dragging");
    board.classList.add("is-dragging");
    try {
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData(
        MIME,
        card.getAttribute("data-dz-entity-id") || "",
      );
      e.dataTransfer.setData(
        "text/plain",
        card.getAttribute("data-dz-entity-id") || "",
      );
    } catch (_) {
      /* IE / locked DT */
    }
  });

  document.addEventListener("dragend", function () {
    if (!dragState) return;
    dragState.card.classList.remove("is-dragging");
    dragState.board.classList.remove("is-dragging");
    dragState.board.querySelectorAll(".is-drop-target").forEach(function (el) {
      el.classList.remove("is-drop-target");
      el.classList.remove("is-drop-deny");
    });
    dragState = null;
  });

  document.addEventListener("dragover", function (e) {
    if (!dragState) return;
    var stack = e.target.closest
      ? e.target.closest("[data-dz-kanban-stack][data-dz-to-state]")
      : null;
    if (!stack || !dragState.board.contains(stack)) return;
    var to = stack.getAttribute("data-dz-to-state") || "";
    var ok = canDrop(dragState.card, to);
    e.preventDefault();
    try {
      e.dataTransfer.dropEffect = ok ? "move" : "none";
    } catch (_) {
      /* ignore */
    }
    dragState.board
      .querySelectorAll(".is-drop-target, .is-drop-deny")
      .forEach(function (el) {
        el.classList.remove("is-drop-target");
        el.classList.remove("is-drop-deny");
      });
    stack.classList.add(ok ? "is-drop-target" : "is-drop-deny");
  });

  document.addEventListener("drop", function (e) {
    if (!dragState) return;
    var stack = e.target.closest
      ? e.target.closest("[data-dz-kanban-stack][data-dz-to-state]")
      : null;
    if (!stack || !dragState.board.contains(stack)) return;
    e.preventDefault();
    var to = stack.getAttribute("data-dz-to-state") || "";
    var card = dragState.card;
    var board = dragState.board;
    if (!canDrop(card, to)) {
      announce(board, "That move is not allowed");
      return;
    }
    putStatus(board, card, to).catch(function () {
      /* announced */
    });
  });

  // ── Keyboard / pointer-free: native select ──

  document.addEventListener("change", function (e) {
    var sel = e.target;
    if (!sel || !sel.matches || !sel.matches("select[data-dz-kanban-move]"))
      return;
    var card = sel.closest("[data-dz-kanban-card]");
    var board = boardOf(sel);
    if (!card || !board) return;
    var to = sel.value;
    if (!to) return;
    if (!canDrop(card, to)) {
      announce(board, "That move is not allowed");
      sel.value = "";
      return;
    }
    putStatus(board, card, to).catch(function () {
      sel.value = "";
    });
  });
})();
