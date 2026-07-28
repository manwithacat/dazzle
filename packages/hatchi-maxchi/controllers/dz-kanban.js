/* HYPERPART: kanban */
/*
 * dz-kanban — board rearrange controller (Linear-class status move on HTMX).
 *
 * SPA technique (dnd-kit / Linear board): drag card → legal column → PATCH
 * status in a client store → re-render. HTMX recontext:
 *   1. SSR stamps capability in the DOM (rearrange attrs only when UPDATE
 *      is permitted; per-card data-dz-allowed-to from the state machine).
 *   2. Controller validates the drop against those attrs (hint only).
 *   3. PUT the existing entity update endpoint with {status_field, rank?}.
 *   4. GET-refresh the workspace region (data-dz-kanban-src) so the server
 *      owns the new board HTML — grid bulk-refresh pattern, morph-safe.
 *
 * Contract (when rearrange is on):
 *   - board:  [data-dz-kanban-board][data-dz-kanban-rearrange="status"]
 *             data-dz-kanban-status-field, data-dz-kanban-api,
 *             data-dz-kanban-src (region refresh URL)
 *             data-dz-kanban-rank-field (optional — enables in-column order)
 *   - card:   [data-dz-kanban-card][data-dz-entity-id][data-dz-from-state]
 *             [data-dz-allowed-to="a b c"]  (space-separated; empty = inert
 *             for *cross-column* only — same-column reorder still works when
 *             rank-field is set and the card is draggable)
 *             [data-dz-rank] optional numeric order key
 *             draggable="true" when rearrange-capable
 *   - stack:  [data-dz-kanban-stack][data-dz-to-state]
 *   - move:   [data-dz-kanban-move] <select> keyboard parity (column only)
 *
 * No Alpine. Document-delegated. Survives morph (re-reads attrs each event).
 */
(function () {
  "use strict";

  var MIME = "application/x-dz-kanban-card";
  var _ghostEl = null;

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

  function rankFieldOf(board) {
    return (board.getAttribute("data-dz-kanban-rank-field") || "").trim();
  }

  /** Cross-column legal? Same-column is always legal when rank is on. */
  function canCross(card, toState) {
    if (!toState) return false;
    var from = card.getAttribute("data-dz-from-state") || "";
    if (toState === from) return false;
    return parseAllowed(card).indexOf(toState) !== -1;
  }

  function canAccept(card, toState, board) {
    var from = card.getAttribute("data-dz-from-state") || "";
    if (toState === from) {
      // In-column: only when rank field is declared (persistable reorder).
      return !!rankFieldOf(board);
    }
    return canCross(card, toState);
  }

  /**
   * Resolve the drop stack under the pointer. Whole column is the surface
   * (header + padding + cards), not just the stack element itself.
   */
  function dropStackFrom(el, board) {
    if (!el || !el.closest || !board) return null;
    var stack = el.closest("[data-dz-kanban-stack][data-dz-to-state]");
    if (stack && board.contains(stack)) return stack;
    var col = el.closest(".dz-kanban-column");
    if (!col || !board.contains(col)) return null;
    stack = col.querySelector("[data-dz-kanban-stack][data-dz-to-state]");
    return stack && board.contains(stack) ? stack : null;
  }

  /** Cards in stack excluding the dragged card, document order. */
  function siblingCards(stack, dragged) {
    return Array.prototype.slice
      .call(stack.querySelectorAll("[data-dz-kanban-card]"))
      .filter(function (c) {
        return c !== dragged;
      });
  }

  /**
   * Insert slot under the pointer: before which sibling (or null = append).
   * Half-height split — same grammar as Trello / Linear lists.
   */
  function insertBeforeCard(stack, clientY, dragged) {
    var cards = siblingCards(stack, dragged);
    for (var i = 0; i < cards.length; i++) {
      var r = cards[i].getBoundingClientRect();
      if (clientY < r.top + r.height / 2) return cards[i];
    }
    return null;
  }

  function clearDropHints(board) {
    board
      .querySelectorAll(
        ".is-drop-target, .is-drop-deny, .is-drop-column, .is-drop-column-deny, .is-drop-before",
      )
      .forEach(function (el) {
        el.classList.remove("is-drop-target");
        el.classList.remove("is-drop-deny");
        el.classList.remove("is-drop-column");
        el.classList.remove("is-drop-column-deny");
        el.classList.remove("is-drop-before");
      });
  }

  function markDropHint(stack, ok, beforeCard) {
    var col = stack.closest(".dz-kanban-column");
    stack.classList.add(ok ? "is-drop-target" : "is-drop-deny");
    if (col) col.classList.add(ok ? "is-drop-column" : "is-drop-column-deny");
    if (ok && beforeCard) beforeCard.classList.add("is-drop-before");
  }

  function csrfHeaders() {
    var headers = {
      "Content-Type": "application/json",
      Accept: "application/json",
    };
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
      if (typeof window !== "undefined" && window.location)
        window.location.reload();
      return;
    }
    var target = regionTarget(board);
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

  function readRank(el) {
    if (!el) return null;
    var n = Number(el.getAttribute("data-dz-rank"));
    return Number.isFinite(n) ? n : null;
  }

  /**
   * Rank between prev/next siblings (or ends). Float midpoints so we only
   * need one PUT for the moved card.
   */
  function rankBetween(prev, next) {
    var p = readRank(prev);
    var n = readRank(next);
    if (p == null && n == null) return 1000;
    if (p == null) return n / 2;
    if (n == null) return p + 1000;
    if (n > p) return (p + n) / 2;
    // Degenerate: re-space after prev.
    return p + 1000;
  }

  /**
   * Persist column change and/or in-column rank. `beforeCard` is the sibling
   * the moved card should land *before* (null = append).
   */
  function putMove(board, card, toState, beforeCard) {
    var api = (board.getAttribute("data-dz-kanban-api") || "").replace(
      /\/$/,
      "",
    );
    var statusField =
      board.getAttribute("data-dz-kanban-status-field") || "status";
    var rankField = rankFieldOf(board);
    var id = card.getAttribute("data-dz-entity-id") || "";
    if (!api || !id) return Promise.reject(new Error("missing api/id"));

    var from = card.getAttribute("data-dz-from-state") || "";
    var body = {};
    if (toState !== from) body[statusField] = toState;

    if (rankField) {
      var destStack = null;
      if (beforeCard) {
        destStack = beforeCard.closest("[data-dz-kanban-stack]");
      }
      if (!destStack) {
        board
          .querySelectorAll("[data-dz-kanban-stack][data-dz-to-state]")
          .forEach(function (s) {
            if (s.getAttribute("data-dz-to-state") === toState) destStack = s;
          });
      }
      var prev = null;
      if (destStack && beforeCard) {
        var sibs = siblingCards(destStack, card);
        var idx = sibs.indexOf(beforeCard);
        prev = idx > 0 ? sibs[idx - 1] : null;
      } else if (destStack) {
        var all = siblingCards(destStack, card);
        prev = all.length ? all[all.length - 1] : null;
      }
      body[rankField] = rankBetween(prev, beforeCard);
    }

    if (!Object.keys(body).length) {
      return Promise.resolve();
    }

    card.classList.add("is-moving");
    board.classList.add("is-busy");
    announce(board, toState === from ? "Reordering…" : "Moving card…");
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
      announce(
        board,
        toState === from
          ? "Reordered"
          : "Moved to " + toState.replace(/_/g, " "),
      );
      refreshBoard(board);
    });
  }

  /** Ghost image anchored under the cursor at the card's pick-up point. */
  function setCardDragImage(e, card) {
    try {
      var rect = card.getBoundingClientRect();
      var ox = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
      var oy = Math.max(0, Math.min(rect.height, e.clientY - rect.top));
      // Clone so the ghost is independent of is-dragging opacity / transforms.
      var ghost = card.cloneNode(true);
      ghost.removeAttribute("id");
      ghost.classList.remove("is-dragging");
      ghost.classList.add("is-drag-ghost");
      ghost.setAttribute("aria-hidden", "true");
      ghost.style.position = "fixed";
      ghost.style.top = "-10000px";
      ghost.style.left = "-10000px";
      ghost.style.width = rect.width + "px";
      ghost.style.boxSizing = "border-box";
      ghost.style.pointerEvents = "none";
      ghost.style.margin = "0";
      document.body.appendChild(ghost);
      _ghostEl = ghost;
      e.dataTransfer.setDragImage(ghost, ox, oy);
      // Remove after the browser has snapshotted the image.
      window.setTimeout(function () {
        if (_ghostEl && _ghostEl.parentNode)
          _ghostEl.parentNode.removeChild(_ghostEl);
        _ghostEl = null;
      }, 0);
    } catch (_) {
      /* setDragImage unsupported — browser default */
    }
  }

  // ── Drag ────────────────────────────────────────────────────────────

  var dragState = null;

  document.addEventListener("dragstart", function (e) {
    var card =
      e.target && e.target.closest
        ? e.target.closest("[data-dz-kanban-card][draggable='true']")
        : null;
    if (!card) return;
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
    // Need either a legal cross-column edge or rank reorder capability.
    var hasCross = parseAllowed(card).length > 0;
    var hasRank = !!rankFieldOf(board);
    if (!hasCross && !hasRank) {
      e.preventDefault();
      return;
    }
    // Capture drag image BEFORE is-dragging opacity mutates the card.
    setCardDragImage(e, card);
    dragState = {
      card: card,
      board: board,
      fromState: card.getAttribute("data-dz-from-state") || "",
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
      /* ignore */
    }
  });

  document.addEventListener("dragend", function () {
    if (!dragState) return;
    dragState.card.classList.remove("is-dragging");
    dragState.board.classList.remove("is-dragging");
    clearDropHints(dragState.board);
    dragState = null;
    if (_ghostEl && _ghostEl.parentNode) {
      _ghostEl.parentNode.removeChild(_ghostEl);
      _ghostEl = null;
    }
  });

  document.addEventListener("dragover", function (e) {
    if (!dragState) return;
    var stack = dropStackFrom(e.target, dragState.board);
    if (!stack) {
      clearDropHints(dragState.board);
      return;
    }
    var to = stack.getAttribute("data-dz-to-state") || "";
    var ok = canAccept(dragState.card, to, dragState.board);
    e.preventDefault();
    try {
      e.dataTransfer.dropEffect = ok ? "move" : "none";
    } catch (_) {
      /* ignore */
    }
    clearDropHints(dragState.board);
    var before = ok ? insertBeforeCard(stack, e.clientY, dragState.card) : null;
    // Same position no-op highlight still ok (shows intent).
    markDropHint(stack, ok, before);
  });

  document.addEventListener("drop", function (e) {
    if (!dragState) return;
    var stack = dropStackFrom(e.target, dragState.board);
    if (!stack) return;
    e.preventDefault();
    var to = stack.getAttribute("data-dz-to-state") || "";
    var card = dragState.card;
    var board = dragState.board;
    var before = insertBeforeCard(stack, e.clientY, card);
    clearDropHints(board);
    if (!canAccept(card, to, board)) {
      announce(board, "That move is not allowed");
      return;
    }
    // No-op when same column and insert slot is already our position.
    var from = card.getAttribute("data-dz-from-state") || "";
    if (to === from) {
      var nextCard = card.nextElementSibling;
      while (
        nextCard &&
        !(nextCard.matches && nextCard.matches("[data-dz-kanban-card]"))
      ) {
        nextCard = nextCard.nextElementSibling;
      }
      if (before) {
        if (before === nextCard) return;
      } else if (!nextCard) {
        // Append and already last among cards.
        return;
      }
    }
    putMove(board, card, to, before).catch(function () {
      /* announced */
    });
  });

  // ── Keyboard / pointer-free: native select (column only) ──

  document.addEventListener("change", function (e) {
    var sel = e.target;
    if (!sel || !sel.matches || !sel.matches("select[data-dz-kanban-move]"))
      return;
    var card = sel.closest("[data-dz-kanban-card]");
    var board = boardOf(sel);
    if (!card || !board) return;
    var to = sel.value;
    if (!to) return;
    if (
      !canCross(card, to) &&
      to !== (card.getAttribute("data-dz-from-state") || "")
    ) {
      announce(board, "That move is not allowed");
      sel.value = "";
      return;
    }
    // Keyboard column move: append to destination.
    putMove(board, card, to, null).catch(function () {
      sel.value = "";
    });
  });
})();
