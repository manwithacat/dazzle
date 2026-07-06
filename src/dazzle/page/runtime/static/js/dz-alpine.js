/** @ts-check */
/**
 * dz-alpine.js — Alpine.js component registrations for Dazzle.
 *
 * Registers named Alpine.data() components that replace dz.js features.
 * Must load BEFORE alpine.min.js (uses alpine:init event).
 *
 * Components:
 *  - dzToast          — toast notification container
 *  - dzMoney          — multi-currency minor unit field
 *  - dzFileUpload     — drag-and-drop file upload
 *  - dzWizard         — multi-step form wizard
 *  - dzConfirmGate    — bulk-action typed-confirmation gate
 *  - dzSlideOver      — side sheet overlay with width control
 *  - dzThemeSwitcher  — light/dark/system theme toggle
 *
 * Removed in the HM migration (Bucket A2, v0.93.65): dzConfirm and
 * dzCommandPalette are now driven by the ingested HM controllers
 * (dz-confirm.js intercepts hx-confirm; dz-command.js drives dialog.dz-command
 * on ⌘K). dzPopover / dzTooltip / dzContextMenu / dzToggleGroup were dead
 * (their CSS was deleted in Bucket A; never instantiated in the app).
 *
 * Directives:
 *  - x-flip               — FLIP-style animations for list reorders (#960)
 *  - x-pull-to-refresh    — touch pull-down → refresh CustomEvent (#958)
 *  - x-swipe              — horizontal swipe → swipe-left/right CustomEvent (#958)
 *  - x-optimistic         — apply DOM change before htmx settle, rollback on error (#959)
 */

// ── Haptic feedback (#958 cycle 5) ──────────────────────────────────
//
// Opt-in haptic feedback via the Vibration API. Activated by the
// presence of `<meta name="dz-haptic" content="on">` in the page —
// emitted by base.html when `[ui] haptic = true` in dazzle.toml.
//
// Auto-fires on:
//   - showToast(success) → tap pattern (single 10ms pulse)
//   - showToast(error)   → error pattern (two short pulses)
//   - swipe-left / swipe-right → tap pattern
//   - htmx:after:request with status >= 400 → error pattern
//
// Silently no-ops when navigator.vibrate is unsupported (most
// desktop browsers), when the meta tag is absent, OR when the user
// has prefers-reduced-motion set (vibration is a motion adjacent
// signal and the same accessibility intent applies).
//
// Exposed as `window.dzHaptic` for adopters who want manual
// triggers (e.g. inside an Alpine handler).
(function () {
  const meta = document.querySelector('meta[name="dz-haptic"]');
  const enabled =
    meta &&
    meta.getAttribute("content") === "on" &&
    typeof navigator !== "undefined" &&
    typeof navigator.vibrate === "function";

  const reduce =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const vibrate = (pattern) => {
    if (!enabled || reduce) return false;
    try {
      return navigator.vibrate(pattern);
    } catch {
      return false;
    }
  };

  window.dzHaptic = {
    enabled: !!enabled && !reduce,
    tap: () => vibrate(10),
    success: () => vibrate(10),
    error: () => vibrate([20, 40, 20]),
    warning: () => vibrate([10, 30, 10]),
    raw: vibrate,
  };

  if (!enabled || reduce) return;

  // Auto-wire to standard event names. document.body may not exist
  // yet when this script runs — use document and let bubbling carry.
  document.addEventListener("showToast", (e) => {
    const detail = e && e.detail;
    if (detail && detail.type === "error") {
      window.dzHaptic.error();
    } else {
      window.dzHaptic.success();
    }
  });
  document.addEventListener("swipe-left", () => window.dzHaptic.tap());
  document.addEventListener("swipe-right", () => window.dzHaptic.tap());
  document.addEventListener("htmx:after:request", (e) => {
    const xhr = e && e.detail && e.detail.ctx && e.detail.ctx.response;
    if (xhr && xhr.status >= 400) window.dzHaptic.error();
  });
})();

document.addEventListener("alpine:init", () => {
  const Alpine = window.Alpine;

  // #975: convert Alpine's default plain-object error throws into real
  // `Error` instances so site-fuzz / page-error harnesses get
  // actionable messages + stacks instead of an opaque "Object" event.
  //
  // Alpine 3's default `setErrorHandler` does
  // `setTimeout(() => { throw {message, el, expression} }, 0)`. The
  // thrown value is a plain object — Playwright's `page.on('pageerror')`
  // sees `String(obj)` which strips to `[object Object]`. Real Errors
  // give us message + stack + cause, which surfaces the failing
  // expression in fuzzer reports.
  if (typeof Alpine.setErrorHandler === "function") {
    Alpine.setErrorHandler((rawError, el, expression) => {
      const message = (rawError && rawError.message) || String(rawError);
      const err = new Error(
        `Alpine expression error: ${message}` +
          (expression ? ` (expression: ${expression})` : ""),
      );
      // @ts-expect-error: cause is widely supported in modern browsers
      err.cause = rawError;
      // Preserve Alpine's "throw async via setTimeout" shape so it
      // doesn't break in-flight evaluation.
      setTimeout(() => {
        throw err;
      }, 0);
    });
  }

  // ── x-flip directive (#960 layer 3) ─────────────────────────────────
  //
  // FLIP-style animation for list reorders (insert/remove/move). Apply
  // `x-flip` to a container; each direct child needs a stable
  // `data-flip-key` attribute (the user's row id, etc.) so the
  // directive can match before/after positions across re-renders.
  //
  // Algorithm: snapshot child rects → MutationObserver fires → snapshot
  // again → for each surviving child compute (before - after) delta,
  // apply inverse translate, then transition back to identity. Browser
  // does the heavy lifting via CSS transition on `transform`.
  //
  // Honours `prefers-reduced-motion: reduce` — observer is still wired
  // (so the snapshot stays current) but transitions are skipped.
  if (typeof Alpine.directive === "function") {
    Alpine.directive("flip", (el) => {
      const reduce =
        typeof window.matchMedia === "function" &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      // Map<flipKey, DOMRect>
      const lastRects = new Map();
      const snapshot = () => {
        const next = new Map();
        for (const child of el.children) {
          const key = child.dataset && child.dataset.flipKey;
          if (!key) continue;
          next.set(key, child.getBoundingClientRect());
        }
        return next;
      };
      // Initial snapshot — captures whatever's already rendered so the
      // first mutation has a "before" to compare against.
      for (const [k, r] of snapshot()) lastRects.set(k, r);

      const onMutation = () => {
        const newRects = snapshot();
        if (!reduce) {
          for (const child of el.children) {
            const key = child.dataset && child.dataset.flipKey;
            if (!key) continue;
            const before = lastRects.get(key);
            const after = newRects.get(key);
            if (!before || !after) continue;
            const dx = before.left - after.left;
            const dy = before.top - after.top;
            if (dx === 0 && dy === 0) continue;
            // Apply inverse instantly (no transition), then in next
            // frame clear and let the transition animate to identity.
            child.style.transition = "none";
            child.style.transform = `translate(${dx}px, ${dy}px)`;
            requestAnimationFrame(() => {
              child.style.transition =
                "transform var(--duration-base) var(--ease-spring-2)";
              child.style.transform = "";
            });
          }
        }
        // Refresh the cache regardless so the next mutation diffs
        // against the current state.
        lastRects.clear();
        for (const [k, r] of newRects) lastRects.set(k, r);
      };

      const observer = new MutationObserver(onMutation);
      observer.observe(el, { childList: true, subtree: false });

      // Cleanup hook for Alpine teardown (component removed from DOM).
      el._dzFlipObserver = observer;
    });

    // ── x-pull-to-refresh directive (#958 cycle 2) ────────────────────
    //
    // Pull-down-to-refresh on touch devices. Apply `x-pull-to-refresh`
    // to a list / dashboard container; the directive listens for a
    // touch-pull beyond `--dz-pull-threshold` (default 80px) and
    // dispatches a `refresh` CustomEvent on the element. Wire it to
    // an htmx swap by adding `hx-trigger="refresh"`:
    //
    //   <div x-pull-to-refresh
    //        hx-get="/users" hx-trigger="refresh"
    //        hx-target="this" hx-swap="innerHTML">
    //
    // Algorithm: capture touch start at scrollTop===0; track Y delta;
    // apply a damped translateY for visual feedback as the user pulls;
    // on release past threshold, fire `refresh`. Below threshold, snap
    // back. `prefers-reduced-motion: reduce` skips the transform but
    // still fires the event so the refresh works regardless.
    //
    // Touch-only via the same `pointer: coarse` rationale as
    // touch-targets.css — desktop mouse users don't get the gesture.
    if (typeof Alpine.directive === "function") {
      Alpine.directive("pull-to-refresh", (el) => {
        // Honour pointer:coarse only — desktop mouse drag would
        // otherwise hijack scroll. Falls back to no-op on
        // matchMedia-less environments.
        const isTouch =
          typeof window.matchMedia === "function" &&
          window.matchMedia("(pointer: coarse)").matches;
        if (!isTouch) return;

        const reduce =
          typeof window.matchMedia === "function" &&
          window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const threshold = 80;
        let startY = 0;
        let pulling = false;
        let pullDistance = 0;

        const onStart = (e) => {
          // Only engage when the container is scrolled to the top —
          // otherwise the user wants to scroll up, not refresh.
          if (el.scrollTop > 0) return;
          startY = e.touches[0].clientY;
          pulling = true;
          pullDistance = 0;
        };

        const onMove = (e) => {
          if (!pulling) return;
          pullDistance = Math.max(0, e.touches[0].clientY - startY);
          if (pullDistance > 0 && !reduce) {
            // Damped: pull half the distance, capped at 1.5× threshold.
            const visual = Math.min(pullDistance / 2, threshold * 1.5);
            el.style.transform = "translateY(" + visual + "px)";
          }
        };

        const onEnd = () => {
          if (!pulling) return;
          if (pullDistance >= threshold) {
            // Fire refresh — htmx (or any listener) picks it up.
            // `bubbles:true` so a parent's hx-trigger can also catch it.
            el.dispatchEvent(new CustomEvent("refresh", { bubbles: true }));
          }
          if (!reduce) {
            // Snap back smoothly.
            el.style.transition =
              "transform var(--duration-base) var(--ease-out)";
            el.style.transform = "";
            setTimeout(() => {
              el.style.transition = "";
            }, 200);
          }
          pulling = false;
          pullDistance = 0;
        };

        // Use { passive: true } so the browser doesn't have to wait
        // for our handler before handling native scroll — keeps the
        // page responsive even if the JS hangs.
        el.addEventListener("touchstart", onStart, { passive: true });
        el.addEventListener("touchmove", onMove, { passive: true });
        el.addEventListener("touchend", onEnd, { passive: true });
        el.addEventListener("touchcancel", onEnd, { passive: true });

        // Stash for potential teardown.
        el._dzPullToRefresh = { onStart, onMove, onEnd };
      });

      // ── x-swipe directive (#958 cycle 3) ────────────────────────────
      //
      // Horizontal swipe gesture on list rows (or any element).
      // Apply `x-swipe`; the directive fires `swipe-left` /
      // `swipe-right` CustomEvents on threshold-crossing horizontal
      // touch motion. Wire to Alpine handlers or htmx triggers:
      //
      //   <li x-swipe
      //       @swipe-left="archive(item.id)"
      //       @swipe-right="favorite(item.id)">
      //
      //   <li x-swipe
      //       hx-post="/tasks/{id}/done" hx-trigger="swipe-left">
      //
      // Heuristics:
      // - threshold 60px horizontal — deliberate movement, not a tap
      // - max vertical drift 40px — anything more is a scroll
      // - max duration 500ms — slower is a drag, not a swipe
      //
      // Touch-only via the same `pointer: coarse` rationale as
      // x-pull-to-refresh — desktop mouse drag would be ambiguous
      // with text selection.
      Alpine.directive("swipe", (el) => {
        const isTouch =
          typeof window.matchMedia === "function" &&
          window.matchMedia("(pointer: coarse)").matches;
        if (!isTouch) return;

        const threshold = 60;
        const maxVertical = 40;
        const maxDurationMs = 500;
        let startX = 0;
        let startY = 0;
        let startT = 0;
        let active = false;

        const onStart = (e) => {
          // Single-finger only — pinch / multi-touch is its own
          // gesture vocabulary; swipe with two fingers would also
          // be ambiguous with browser-level navigation gestures.
          if (e.touches.length !== 1) {
            active = false;
            return;
          }
          startX = e.touches[0].clientX;
          startY = e.touches[0].clientY;
          startT = Date.now();
          active = true;
        };

        const onEnd = (e) => {
          if (!active) return;
          active = false;
          // touchend's changedTouches carries the final position.
          const t = e.changedTouches && e.changedTouches[0];
          if (!t) return;
          const dx = t.clientX - startX;
          const dy = t.clientY - startY;
          const dt = Date.now() - startT;
          if (dt > maxDurationMs) return;
          if (Math.abs(dy) > maxVertical) return;
          if (Math.abs(dx) < threshold) return;
          // Detail carries the raw delta + duration so handlers can
          // do their own velocity-based logic (e.g. snap-vs-undo).
          const detail = { dx: dx, dy: dy, durationMs: dt };
          const name = dx < 0 ? "swipe-left" : "swipe-right";
          el.dispatchEvent(
            new CustomEvent(name, { bubbles: true, detail: detail }),
          );
        };

        el.addEventListener("touchstart", onStart, { passive: true });
        el.addEventListener("touchend", onEnd, { passive: true });
        el.addEventListener(
          "touchcancel",
          () => {
            active = false;
          },
          { passive: true },
        );

        el._dzSwipe = { onStart, onEnd };
      });

      // ── x-optimistic directive (#959 cycle 1) ──────────────────────
      //
      // Apply a visual change before the htmx response settles, then
      // either keep it (success) or roll back (4xx/5xx). Closes the
      // gap between "click delete" and "row disappears" — no waiting
      // for the round-trip.
      //
      // Shapes (cycle 1):
      //   x-optimistic="remove"                — drop the element itself
      //   x-optimistic="remove:closest tr"     — drop a different element
      //
      // Cycles 2+ (deferred):
      //   - prepend / append / replace shapes
      //   - reconciliation with server response (merge attributes)
      //   - undo stack integration
      //
      // Wire alongside an htmx mutation:
      //
      //   <button hx-delete="/_dazzle/tasks/{id}"
      //           hx-target="closest tr"
      //           hx-swap="outerHTML"
      //           x-optimistic="remove:closest tr">Delete</button>
      //
      // Rollback path: on htmx:response:error or htmx:error, the
      // removed node is re-inserted at its original position and a
      // toast surfaces the failure. Adopters can listen for
      // `dz:optimistic-rollback` if they want custom recovery UI.
      //
      // Cycle 3 — undo stack. Successful optimistic mutations push
      // an entry onto a session-level stack capped at 20. Cmd+Z
      // (Ctrl+Z elsewhere) pops the most recent entry, reverses the
      // DOM where possible (remove/replace via the captured snapshot),
      // and dispatches `dz:optimistic-undo` so the adopter can issue
      // the server-side reversal request (e.g. an `hx-post` on a
      // hidden form trigger).
      const _DZ_OPTIMISTIC_UNDO_MAX = 20;
      const _dzOptimisticUndoStack = [];
      // Cycle 4 — redo stack. Cmd+Z moves entries from undo→redo;
      // Shift+Cmd+Z moves them back. A NEW mutation push clears the
      // redo stack — standard editor convention (you can't redo
      // through a divergent history).
      const _dzOptimisticRedoStack = [];

      function _pushOptimisticUndo(entry) {
        _dzOptimisticUndoStack.push(entry);
        while (_dzOptimisticUndoStack.length > _DZ_OPTIMISTIC_UNDO_MAX) {
          _dzOptimisticUndoStack.shift();
        }
        // New mutation — divergent history, redo no longer applies.
        _dzOptimisticRedoStack.length = 0;
      }

      // Expose both stacks for tests + adopter introspection. Read-only
      // by convention; popping should go through the keyboard handler.
      window.dzOptimisticUndoStack = _dzOptimisticUndoStack;
      window.dzOptimisticRedoStack = _dzOptimisticRedoStack;

      // Single global keydown handler — registered once per page load
      // even with many x-optimistic instances.
      if (!window._dzOptimisticUndoBound) {
        window._dzOptimisticUndoBound = true;
        document.addEventListener("keydown", (e) => {
          // Cmd+Z on macOS, Ctrl+Z elsewhere.
          // Shift+Cmd+Z = redo (cycle 4).
          const isModified = (e.metaKey || e.ctrlKey) && e.key === "z";
          if (!isModified) return;

          // Don't hijack undo/redo when the user is typing — let the
          // input's native undo handle text edits.
          const t = e.target;
          if (t) {
            const tag = (t.tagName || "").toLowerCase();
            if (tag === "input" || tag === "textarea" || t.isContentEditable) {
              return;
            }
          }

          if (e.shiftKey) {
            // Redo: pop from redo, run redo(), push back to undo.
            const entry = _dzOptimisticRedoStack.pop();
            if (!entry) return;
            e.preventDefault();
            try {
              if (typeof entry.redo === "function") entry.redo();
              _dzOptimisticUndoStack.push(entry);
            } catch {
              // Defensive — stale entry shouldn't break later presses.
            }
            return;
          }

          // Undo: pop from undo, run undo(), push to redo.
          const entry = _dzOptimisticUndoStack.pop();
          if (!entry) return;
          e.preventDefault();
          try {
            entry.undo();
            _dzOptimisticRedoStack.push(entry);
          } catch {
            // Defensive — stale undo shouldn't break later presses.
          }
        });
      }

      Alpine.directive("optimistic", (el, { expression }) => {
        const action = (expression || "remove").trim();
        // Parse "<verb>:<selector>" — selector defaults to the element
        // itself for the bare "<verb>" form (most useful for `remove`).
        const colonIdx = action.indexOf(":");
        const verb =
          colonIdx === -1 ? action : action.slice(0, colonIdx).trim();
        const selectorRaw =
          colonIdx === -1 ? "" : action.slice(colonIdx + 1).trim();

        const KNOWN_VERBS = new Set(["remove", "prepend", "append", "replace"]);
        if (!KNOWN_VERBS.has(verb)) {
          // eslint-disable-next-line no-console
          console.warn(
            "x-optimistic: shape '" +
              verb +
              "' not recognised. Known shapes: " +
              [...KNOWN_VERBS].join(", "),
          );
          return;
        }

        const resolveTarget = () => {
          if (!selectorRaw) return el;
          // Mirror htmx's `closest <selector>` semantics for parity
          // — the most common pattern in DSL-rendered list rows.
          if (selectorRaw.startsWith("closest ")) {
            return el.closest(selectorRaw.slice("closest ".length).trim());
          }
          return document.querySelector(selectorRaw);
        };

        // Build a placeholder element for prepend / append / replace.
        // Sources, in priority order:
        //   1. `x-optimistic-template="<id>"` → clone of <template id> content
        //   2. Fallback: a generic "loading" div with aria-busy
        // Templates are the recommended path — adopters control exactly
        // what the placeholder looks like (matching row shape, etc.).
        const buildPlaceholder = () => {
          const templateId = el.getAttribute("x-optimistic-template");
          if (templateId) {
            const tpl = document.getElementById(templateId);
            if (tpl && tpl.content) {
              const wrapper = document.createElement("div");
              wrapper.appendChild(tpl.content.cloneNode(true));
              const node = wrapper.firstElementChild;
              if (node) {
                node.setAttribute("data-dz-optimistic-placeholder", "1");
                node.setAttribute("aria-busy", "true");
                return node;
              }
            }
          }
          const ph = document.createElement("div");
          ph.className = "dz-optimistic-placeholder";
          ph.setAttribute("data-dz-optimistic-placeholder", "1");
          ph.setAttribute("aria-busy", "true");
          return ph;
        };

        // State carried across the lifecycle:
        // - snapshot: captures (node, parent, nextSibling) for `remove`
        //   and `replace` rollback paths.
        // - placeholder: the inserted element for prepend / append /
        //   replace; removed on success or rollback.
        let snapshot = null;
        let placeholder = null;

        const removePlaceholder = () => {
          if (placeholder && placeholder.parentNode) {
            try {
              placeholder.parentNode.removeChild(placeholder);
            } catch {
              // Already detached; nothing to do.
            }
          }
          placeholder = null;
        };

        const onBeforeRequest = (ev) => {
          // Only react to htmx events fired by THIS element. Bubbled
          // events from children would otherwise mutate the wrong row.
          if (ev.target !== el) return;
          const target = resolveTarget();
          if (!target) return;

          if (verb === "remove") {
            if (!target.parentNode) return;
            snapshot = {
              node: target,
              parent: target.parentNode,
              nextSibling: target.nextSibling,
            };
            target.parentNode.removeChild(target);
            return;
          }

          if (verb === "prepend") {
            placeholder = buildPlaceholder();
            target.insertBefore(placeholder, target.firstChild);
            return;
          }

          if (verb === "append") {
            placeholder = buildPlaceholder();
            target.appendChild(placeholder);
            return;
          }

          if (verb === "replace") {
            if (!target.parentNode) return;
            // Replace combines remove + insert: snapshot the original
            // for rollback, then drop in the placeholder at its slot.
            snapshot = {
              node: target,
              parent: target.parentNode,
              nextSibling: target.nextSibling,
            };
            placeholder = buildPlaceholder();
            target.parentNode.replaceChild(placeholder, target);
          }
        };

        const restore = (reason) => {
          // For prepend / append: just drop the placeholder.
          // For remove / replace: re-insert the original node at its
          // recorded position.
          removePlaceholder();
          if (snapshot) {
            const { node, parent, nextSibling } = snapshot;
            try {
              if (nextSibling && nextSibling.parentNode === parent) {
                parent.insertBefore(node, nextSibling);
              } else {
                parent.appendChild(node);
              }
            } catch {
              // Parent is gone — nothing we can restore.
            }
            snapshot = null;
          }
          // Surface for adopter recovery hooks + user-visible nudge.
          el.dispatchEvent(
            new CustomEvent("dz:optimistic-rollback", {
              bubbles: true,
              detail: { reason: reason || "error", verb: verb },
            }),
          );
          document.body.dispatchEvent(
            new CustomEvent("showToast", {
              detail: {
                message: "Action could not be completed; restored",
                type: "error",
              },
            }),
          );
        };

        const onAfterRequest = (ev) => {
          if (ev.target !== el) return;
          const xhr = ev.detail && ev.detail.ctx && ev.detail.ctx.response;
          const ok =
            ev.detail && ev.detail.successful !== undefined
              ? ev.detail.successful
              : xhr && xhr.status < 400;
          if (ok) {
            // Success: drop the placeholder (htmx will have inserted
            // the real content alongside or in its place) and clear
            // the snapshot so we don't accidentally restore a stale
            // node on a later event.
            removePlaceholder();
            // Cycle 3 — push an undo entry so Cmd+Z reverses the
            // optimistic mutation. Capture `snapshot` by closure
            // BEFORE clearing it; the entry's `undo` runs at an
            // arbitrary later time when the directive's `snapshot`
            // local has already been set to null by another mutation.
            const undoSnapshot = snapshot;
            _pushOptimisticUndo({
              el: el,
              verb: verb,
              undo: () => {
                // DOM-level reversal where possible: re-insert the
                // captured node at its original position. Only meaningful
                // for `remove` and `replace` — `prepend`/`append` have
                // no captured snapshot (the placeholder was the only
                // tracked node, and it's already gone).
                if (undoSnapshot && (verb === "remove" || verb === "replace")) {
                  const { node, parent, nextSibling } = undoSnapshot;
                  try {
                    if (nextSibling && nextSibling.parentNode === parent) {
                      parent.insertBefore(node, nextSibling);
                    } else if (parent) {
                      parent.appendChild(node);
                    }
                  } catch {
                    // Parent gone — DOM-level undo not possible. The
                    // dz:optimistic-undo event still fires so the
                    // adopter can reconcile server-side state.
                  }
                }
                // Always dispatch — adopter wires the server-side
                // reversal (e.g. POST /restore endpoint) through this
                // event. Detail carries the verb + snapshot so the
                // handler can branch on what was originally done.
                el.dispatchEvent(
                  new CustomEvent("dz:optimistic-undo", {
                    bubbles: true,
                    detail: { verb: verb, snapshot: undoSnapshot },
                  }),
                );
              },
              // Cycle 4 — redo. Reverses the undo: removes the
              // restored node (remove/replace) and re-fires the
              // mutation event for adopter-wired forward action.
              redo: () => {
                if (
                  undoSnapshot &&
                  (verb === "remove" || verb === "replace") &&
                  undoSnapshot.node &&
                  undoSnapshot.node.parentNode
                ) {
                  try {
                    undoSnapshot.node.parentNode.removeChild(undoSnapshot.node);
                  } catch {
                    // Defensive — node already detached.
                  }
                }
                el.dispatchEvent(
                  new CustomEvent("dz:optimistic-redo", {
                    bubbles: true,
                    detail: { verb: verb, snapshot: undoSnapshot },
                  }),
                );
              },
            });
            // Cycle 4 — reconciliation hook. Adopters that need to
            // merge state (focus, scroll, custom attributes) between
            // the optimistic placeholder and the server response can
            // listen for `dz:optimistic-reconcile` on the bound
            // element. Detail carries the verb + the htmx response
            // xhr (when available) so handlers can inspect the
            // returned HTML before deciding what to merge.
            el.dispatchEvent(
              new CustomEvent("dz:optimistic-reconcile", {
                bubbles: true,
                detail: { verb: verb, xhr: xhr },
              }),
            );
            snapshot = null;
            return;
          }
          restore("response-error");
        };

        const onSendError = (ev) => {
          if (ev.target !== el) return;
          restore("send-error");
        };

        el.addEventListener("htmx:before:request", onBeforeRequest);
        el.addEventListener("htmx:after:request", onAfterRequest);
        el.addEventListener("htmx:error", onSendError);

        el._dzOptimistic = { onBeforeRequest, onAfterRequest, onSendError };
      });
    }
  }

  // ── Toast Notifications ─────────────────────────────────────────────

  Alpine.data("dzToast", () => ({
    toasts: [],
    _nextId: 0,

    init() {
      // Listen for HTMX server-sent showToast triggers
      document.body.addEventListener("showToast", (e) => {
        const d = /** @type {CustomEvent} */ (e).detail;
        if (d && d.message) this.show(d.message, d.type || "success");
      });
      // Listen for Alpine $dispatch('toast', ...) events
      this.$el.addEventListener("toast", (e) => {
        const d = /** @type {CustomEvent} */ (e).detail;
        if (d && d.message) this.show(d.message, d.type || "info");
      });
    },

    show(message, type = "info") {
      const id = ++this._nextId;
      this.toasts.push({ id, message, type, leaving: false });
      setTimeout(() => this.dismiss(id), 4000);
    },

    dismiss(id) {
      const t = this.toasts.find((t) => t.id === id);
      if (t) {
        t.leaving = true;
        setTimeout(() => {
          this.toasts = this.toasts.filter((t) => t.id !== id);
        }, 300);
      }
    },
  }));

  // Global toast function (backward compat with dz.toast)
  window.dz = window.dz || {};
  window.dz.toast = (message, type = "info") => {
    const el = document.getElementById("dz-toast");
    if (el)
      el.dispatchEvent(new CustomEvent("toast", { detail: { message, type } }));
  };

  /**
   * Download a CSV export via fetch + Blob (v0.61.2, #862).
   *
   * `<a download>` is ignored by Safari for same-origin responses with
   * `Content-Type: text/csv` — Safari treats the navigation as a document
   * load and renders the CSV inline, losing the user's workspace context.
   * The server-side `Content-Disposition: attachment` header is set
   * correctly but Safari honours its own heuristic over the header in
   * this case.
   *
   * This helper:
   *   1. Fetches the endpoint with same-origin credentials.
   *   2. Converts the response to a Blob (any Content-Type works).
   *   3. Creates a transient object-URL + synthetic <a download> element.
   *   4. Triggers a programmatic click (always a download, never a nav).
   *   5. Revokes the URL on next tick to free memory.
   *
   * Errors surface via toast + console — callers don't need to wrap.
   */
  window.dz.downloadCsv = async (endpoint, filename) => {
    const url = endpoint.includes("?")
      ? endpoint + "&format=csv"
      : endpoint + "?format=csv";
    try {
      const response = await fetch(url, { credentials: "same-origin" });
      if (!response.ok) {
        window.dz.toast(
          "CSV export failed: " + response.status + " " + response.statusText,
          "error",
        );
        return;
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename || "export.csv";
      // Appending to body is required on some browsers before click() works.
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      // Revoke on next tick so the browser has time to begin the download.
      setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    } catch (err) {
      window.dz.toast("CSV export failed: network error", "error");
      console.error("[dz.downloadCsv]", err);
    }
  };

  // ── Data Table ──────────────────────────────────────────────────────
  // dzTable was deleted in convergence C3 (2026-07-06): the HM grid
  // primitive (dz-grid.js) + its extensions (dz-grid-cols/-resize/-edit)
  // own the entire data-table behaviour surface — delegated, state-in-DOM,
  // no Alpine scope. See CHANGELOG v0.93.97 and the C1.1-C2.4 entries.

  // ── Money Field ─────────────────────────────────────────────────────

  const CURRENCY_SCALES = {
    GBP: 2,
    USD: 2,
    EUR: 2,
    AUD: 2,
    CAD: 2,
    CHF: 2,
    CNY: 2,
    INR: 2,
    NZD: 2,
    SGD: 2,
    HKD: 2,
    SEK: 2,
    NOK: 2,
    DKK: 2,
    ZAR: 2,
    MXN: 2,
    BRL: 2,
    JPY: 0,
    KRW: 0,
    VND: 0,
    CLP: 0,
    ISK: 0,
    BHD: 3,
    KWD: 3,
    OMR: 3,
    TND: 3,
    JOD: 3,
    IQD: 3,
    LYD: 3,
  };

  Alpine.data("dzMoney", () => ({
    displayValue: "",
    minorValue: "",
    _scale: 2,

    init() {
      // Determine scale from container attributes
      this._scale = this._getScale();
      // Populate display from minor on load (edit mode)
      if (this.minorValue && !this.displayValue) {
        this.displayValue = this._toDisplay(this.minorValue);
      }
    },

    onInput() {
      this.minorValue = String(this._toMinor(this.displayValue));
    },

    onBlur() {
      if (!this.displayValue.trim()) {
        this.minorValue = "";
        return;
      }
      const minor = this._toMinor(this.displayValue);
      this.minorValue = String(minor);
      this.displayValue = this._toDisplay(String(minor));
    },

    onCurrencyChange(event) {
      const opt = event.target.selectedOptions[0];
      if (opt && opt.dataset.scale !== undefined) {
        this._scale = parseInt(opt.dataset.scale, 10);
      }
      // Update prefix symbol
      const prefix = this.$el.querySelector(".dz-money-prefix");
      if (prefix && opt && opt.dataset.symbol) {
        prefix.textContent = opt.dataset.symbol;
      }
      // Re-convert with new scale
      if (this.displayValue) {
        const minor = this._toMinor(this.displayValue);
        this.minorValue = String(minor);
        this.displayValue = this._toDisplay(String(minor));
      }
    },

    _getScale() {
      const scaleAttr = this.$el.getAttribute("data-dz-scale");
      if (scaleAttr !== null) return parseInt(scaleAttr, 10);
      const code = this.$el.getAttribute("data-dz-currency") || "GBP";
      return CURRENCY_SCALES[code] !== undefined ? CURRENCY_SCALES[code] : 2;
    },

    _toMinor(val) {
      const num = parseFloat(val);
      if (isNaN(num)) return 0;
      return Math.round(num * Math.pow(10, this._scale));
    },

    _toDisplay(val) {
      const num = parseInt(val, 10);
      if (isNaN(num)) return "";
      return (num / Math.pow(10, this._scale)).toFixed(this._scale);
    },
  }));

  // ── File Upload ─────────────────────────────────────────────────────

  Alpine.data("dzFileUpload", () => ({
    filename: "",
    hasFile: false,
    uploading: false,
    progress: 0, // 0-100; bytes-uploaded percentage (#1213 Phase A)
    error: "",
    dragging: false,

    selectFile(event) {
      const files = event.target.files;
      if (files && files[0]) this.upload(files[0]);
    },

    onDrop(event) {
      event.preventDefault();
      this.dragging = false;
      if (event.dataTransfer?.files?.[0]) {
        this.upload(event.dataTransfer.files[0]);
      }
    },

    upload(file) {
      // XMLHttpRequest over fetch() to expose upload-progress events
      // (#1213 Phase A). The fetch() Streams body progress API is not
      // yet a uniform browser baseline, and `xhr.upload.onprogress`
      // is what the existing <progress> element needs to display real
      // bytes-loaded percentage instead of binary on/off.
      //
      // Phase C: when data-dz-file-mode="managed_upload" is present,
      // route through the ticket flow (POST /api/{entity}/upload-ticket
      // → presigned POST to S3 → set hidden input to s3_key). The
      // framework's verify_storage_field_keys hook on entity-create
      // POSTs runs the prefix-sandbox + head_object verification on
      // form submit, so no separate finalize round-trip is needed.
      this.error = "";
      this.uploading = true;
      this.progress = 0;

      const mode = this.$el.dataset.dzFileMode || "";
      if (mode === "managed_upload") {
        return this._uploadManaged(file);
      }
      return this._uploadSimple(file);
    },

    _uploadSimple(file) {
      const formData = new FormData();
      formData.append("file", file);

      const form = this.$el.closest("form");
      const entityName = form?.dataset.dazzleForm || "";
      const fieldName = this.$el.dataset.dzFile || "";
      if (entityName) formData.append("entity", entityName);
      if (fieldName) formData.append("field", fieldName);

      return new Promise((resolve) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/files/upload");
        xhr.responseType = "json";

        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable && event.total > 0) {
            this.progress = Math.round((event.loaded / event.total) * 100);
          }
        };

        xhr.onload = () => {
          this.uploading = false;
          if (xhr.status >= 200 && xhr.status < 300) {
            const data = xhr.response || {};
            this.filename = data.filename || file.name;
            this.hasFile = true;
            this.progress = 100;
            const hidden = this.$el.querySelector("[data-dz-file-value]");
            if (hidden) hidden.value = data.url || data.id;
          } else {
            const detail = (xhr.response && xhr.response.detail) || "";
            this.error = detail || "Upload failed";
            this.progress = 0;
          }
          resolve();
        };

        xhr.onerror = () => {
          this.uploading = false;
          this.progress = 0;
          this.error = "Upload failed";
          resolve();
        };

        xhr.send(formData);
      });
    },

    async _uploadManaged(file) {
      // managed_upload (#1213 Phase C): three steps.
      // 1) POST /api/{entity}/upload-ticket → ticket payload
      // 2) Direct presigned POST to ticket.upload.url with the file
      //    binary; xhr.upload.onprogress drives the <progress> bar
      // 3) Set hidden input value to ticket.s3_key — the entity-create
      //    route's verify_storage_field_keys hook validates it on
      //    form submit (prefix sandbox + head_object).
      const form = this.$el.closest("form");
      const entityName = form?.dataset.dazzleForm || "";
      const fieldName = this.$el.dataset.dzFile || "";
      if (!entityName) {
        this.uploading = false;
        this.error = "managed_upload requires data-dazzle-form on the form";
        return;
      }

      const ticketUrl = `/api/${entityName.toLowerCase()}/upload-ticket`;
      let ticket;
      try {
        const ticketResp = await fetch(ticketUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            filename: file.name,
            content_type: file.type || "application/octet-stream",
            field: fieldName,
          }),
        });
        if (!ticketResp.ok) {
          const errBody = await ticketResp.json().catch(() => ({}));
          throw new Error(
            errBody.error || `ticket request failed (${ticketResp.status})`,
          );
        }
        ticket = await ticketResp.json();
      } catch (err) {
        this.uploading = false;
        this.progress = 0;
        this.error = err.message || "Upload ticket request failed";
        return;
      }

      const presigned = (ticket && ticket.upload) || {};
      const s3Url = presigned.url;
      const s3Fields = presigned.fields || {};
      const s3Key = ticket.s3_key;
      if (!s3Url || !s3Key) {
        this.uploading = false;
        this.error = "Malformed upload ticket: missing url or s3_key";
        return;
      }

      const s3Form = new FormData();
      for (const [k, v] of Object.entries(s3Fields)) s3Form.append(k, v);
      s3Form.append("file", file);

      return new Promise((resolve) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", s3Url);

        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable && event.total > 0) {
            this.progress = Math.round((event.loaded / event.total) * 100);
          }
        };

        xhr.onload = () => {
          this.uploading = false;
          if (xhr.status >= 200 && xhr.status < 300) {
            this.filename = file.name;
            this.hasFile = true;
            this.progress = 100;
            const hidden = this.$el.querySelector("[data-dz-file-value]");
            if (hidden) hidden.value = s3Key;
          } else {
            this.error = `S3 upload failed (${xhr.status})`;
            this.progress = 0;
          }
          resolve();
        };

        xhr.onerror = () => {
          this.uploading = false;
          this.progress = 0;
          this.error = "S3 upload failed";
          resolve();
        };

        xhr.send(s3Form);
      });
    },

    clear() {
      this.filename = "";
      this.hasFile = false;
      this.progress = 0;
      this.error = "";
      const hidden = this.$el.querySelector("[data-dz-file-value]");
      if (hidden) hidden.value = "";
      const fileInput = this.$el.querySelector("[data-dz-file-input]");
      if (fileInput) fileInput.value = "";
    },
  }));

  // ── Wizard Form ─────────────────────────────────────────────────────

  Alpine.data("dzWizard", (totalSteps) => ({
    step: 0,
    total: totalSteps,

    showStage(idx) {
      this.step = idx;
    },

    next() {
      if (this.validateStage(this.step) && this.step < this.total - 1) {
        this.step++;
      }
    },

    prev() {
      if (this.step > 0) this.step--;
    },

    goToStep(idx) {
      if (idx <= this.step) {
        this.step = idx;
      } else if (idx === this.step + 1 && this.validateStage(this.step)) {
        this.step = idx;
      }
    },

    validateStage(idx) {
      const stages = this.$el.querySelectorAll("[data-dz-stage]");
      if (!stages[idx]) return true;
      const inputs = stages[idx].querySelectorAll(
        "input[required], select[required], textarea[required]",
      );
      let valid = true;
      inputs.forEach((input) => {
        if (!(/** @type {HTMLInputElement} */ (input).value)) {
          /** @type {HTMLInputElement} */ (input).reportValidity();
          valid = false;
        }
      });
      return valid;
    },

    isActive(idx) {
      return idx <= this.step;
    },
    isCurrent(idx) {
      return idx === this.step;
    },
  }));

  // ── Confirm gate ──────────────────────────────────────────────────────
  // v0.61.72 (#6) — confirm_action_panel checklist gate. Tracks the
  // count of required checkboxes that have been ticked; the primary
  // action enables only when `tickedRequired === requiredCount`. The
  // template binds via `enabled` (computed from the count).
  Alpine.data("dzConfirmGate", (totalRows) => ({
    total: totalRows,
    tickedRequired: 0,
    requiredCount: 0,

    init() {
      // Count required rows from the data-dz-required-count attribute
      // on the gate's root element. Falls back to scanning if absent.
      const declared = parseInt(
        this.$el.getAttribute("data-dz-required-count") || "0",
        10,
      );
      if (declared > 0) {
        this.requiredCount = declared;
      } else {
        const reqInputs = this.$el.querySelectorAll(
          'input[type="checkbox"][data-dz-required="true"]',
        );
        this.requiredCount = reqInputs.length;
      }
    },

    onToggle(event) {
      const target = event.target;
      if (!target || target.dataset.dzRequired !== "true") return;
      this.tickedRequired += target.checked ? 1 : -1;
      if (this.tickedRequired < 0) this.tickedRequired = 0;
    },

    get enabled() {
      // No required rows = always enabled (low-friction flow with
      // only optional checkboxes or no checkboxes at all).
      if (this.requiredCount === 0) return true;
      return this.tickedRequired >= this.requiredCount;
    },
  }));

  // ── Slide-Over (Enhanced) ─────────────────────────────────────────────

  Alpine.data("dzSlideOver", () => ({
    open: false,
    _width: "md",

    widthClass() {
      const map = {
        sm: "max-w-sm",
        md: "max-w-md",
        lg: "max-w-lg",
        xl: "max-w-xl",
        full: "max-w-full",
      };
      return map[this._width] || "max-w-md";
    },

    show() {
      this.open = true;
      this.$dispatch("dz:open");
    },
    hide() {
      this.open = false;
      this.$dispatch("dz:close");
    },

    init() {
      this._width = this.$el.dataset.dzWidth || "md";
      // Listen for open event from HTMX triggers
      window.addEventListener("dz:slideover-open", () => this.show());
      this.$el.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && this.open) this.hide();
      });
    },
  }));

  // ── Theme Switcher ──────────────────────────────────────────────────
  //
  // Phase C Patch 3: live app-shell theme switching.
  //
  // Server emits a `<script type="application/json" id="dz-app-themes">`
  // map of `{<theme_name>: [<url>, ...]}` (chain order, parent → leaf)
  // covering every theme discovered at startup. The component reads
  // the active theme from `<html data-theme-name>` (server-set), then
  // on `setTheme(name)` swaps the `<link data-theme-link>` chain to
  // the new theme's URLs and persists the choice via `dzPrefs` (or
  // localStorage as fallback for unauthenticated users).
  //
  // Usage in a template:
  //   <div x-data="dzThemeSwitcher">
  //     <template x-for="t in themes" :key="t">
  //       <button @click="setTheme(t)" :aria-pressed="active === t"
  //               x-text="t"></button>
  //     </template>
  //   </div>
  Alpine.data("dzThemeSwitcher", () => ({
    /** @type {string[]} */
    themes: [],
    /** @type {string} */
    active: "",

    init() {
      // Active theme = server-rendered `<html data-theme-name="...">`.
      this.active = document.documentElement.dataset.themeName || "";
      // Theme map shipped as inline JSON.
      const mapEl = document.getElementById("dz-app-themes");
      if (!mapEl) return;
      try {
        const map = JSON.parse(mapEl.textContent || "{}");
        this.themes = Object.keys(map).sort();
        this._urls = map; // { name: ['/static/css/themes/x.css', ...] }
      } catch (e) {
        /* malformed JSON — leave themes empty */
      }
      // Restore persisted choice (overrides server-rendered default
      // for THIS request only — server still honours its own resolution
      // for first-paint flash prevention on next navigation).
      const persisted = this._readPersisted();
      if (persisted && persisted !== this.active && this._urls[persisted]) {
        this.setTheme(persisted);
      }
    },

    setTheme(name) {
      if (!this._urls[name]) return; // unknown — silently ignore
      // Remove existing theme links
      document
        .querySelectorAll("link[data-theme-link]")
        .forEach((el) => el.parentNode && el.parentNode.removeChild(el));
      // Inject the new chain in cascade order (parent first → leaf last).
      // Defence in depth: even though the server emits the URL list as
      // inline JSON (see init()), validate each URL matches the
      // expected theme-CSS shape before assigning to `link.href`.
      // Closes CodeQL js/xss-through-dom (#81) — and rejects any
      // `javascript:` / `data:` payload that would otherwise reach the
      // DOM sink.
      const SAFE_THEME_URL = /^\/(?:static\/)?(?:css\/)?themes\/[\w-]+\.css$/;
      const head = document.head;
      this._urls[name].forEach((url) => {
        if (typeof url !== "string" || !SAFE_THEME_URL.test(url)) return;
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = url;
        link.dataset.themeLink = name;
        head.appendChild(link);
      });
      this.active = name;
      document.documentElement.dataset.themeName = name;
      this._persist(name);
      // Notify any listeners (e.g. data-island re-renders) that the
      // theme changed. Alpine bridges `dz:` events naturally.
      window.dispatchEvent(
        new CustomEvent("dz:theme-changed", { detail: { name } }),
      );
    },

    _persist(name) {
      // Prefer server-backed prefs (auth users); fall back to localStorage.
      if (window.dzPrefs && typeof window.dzPrefs.set === "function") {
        window.dzPrefs.set("app_theme", name);
      } else {
        try {
          localStorage.setItem("dz.app_theme", name);
        } catch (e) {
          /* private browsing — ignore */
        }
      }
    },

    _readPersisted() {
      // Try server prefs first (instant for auth users)
      if (window.dzPrefs && typeof window.dzPrefs.get === "function") {
        const v = window.dzPrefs.get("app_theme", null);
        if (v) return v;
      }
      try {
        return localStorage.getItem("dz.app_theme") || null;
      } catch (e) {
        return null;
      }
    },
  }));
});

// ── HTMX morph-swap → Alpine.initTree bridge (#924) ───────────────────
//
// htmx-morph swaps mutate the DOM in-place — they don't fire the
// MutationObserver patterns Alpine relies on for auto-discovery of new
// `x-data` roots. When a sidebar workspace link morphs `#main-content`
// from one workspace to another, the new `<div x-data="dzDashboardBuilder()">`
// element lands in the DOM but Alpine never calls `init()` on it, so
// `<template x-for>` directives stay inert and the JSON layout island
// renders as raw text.
//
// The fix is the standard Alpine + HTMX bridge: after every swap settles,
// walk the swapped subtree and call `Alpine.initTree(target)`. Alpine
// tags processed elements internally so re-initing inited components is
// a no-op — safe to fire on every settle.
//
// Listen on `htmx:after:settle` (not `afterSwap`) for the same reason as
// the per-component listener in dashboard-builder.js: under the morph
// extension `afterSwap` fires before idiomorph commits child-node text,
// so the JSON data island still holds stale text at that point. See
// #919 (the original fix) and #924 (this follow-up).
document.body.addEventListener("htmx:after:settle", (e) => {
  const target = e && e.detail && e.detail.target;
  if (!target) return;
  if (window.Alpine && typeof window.Alpine.initTree === "function") {
    window.Alpine.initTree(target);
  }

  // #936 → #945 → #948: workspace component re-hydration on same-URL morph.
  //
  // Same-URL morph (clicking the active workspace's sidebar link)
  // keeps the `<div x-data="dzDashboardBuilder()">` element in place.
  // The initial `Alpine.initTree(target)` above is a no-op for it
  // (Alpine sees the root as already-initialised), so the watcher
  // graph stays bound to the ORIGINAL Alpine proxy.
  //
  // Pre-#948 this would silently break `<template x-for="card in cards">`
  // because the cards reactive array's watcher detached from the new
  // proxy. Cards collapsed to 0. Cycle 945 fixed it via destroy +
  // re-init.
  //
  // Post-#948: cards are server-rendered HTML and the DOM is the
  // source of truth for layout — no cards array, no x-for, no
  // staleness bug class. The destroy + re-init still does the right
  // thing for ephemeral state (resets stale `saveState` / `showPicker`
  // and re-attaches the grid-container event delegation listeners),
  // so we keep the pattern as defense-in-depth. The trigger is now
  // the workspace root's `data-workspace-name` attribute rather than
  // the (removed) `#dz-workspace-layout` data island.
  const root =
    (target.querySelector && target.querySelector("[data-workspace-name]")) ||
    document.querySelector("[data-workspace-name]");
  if (!root || !window.Alpine) return;
  // Skip when the swap target isn't the root or its parent — avoids
  // re-init on unrelated swaps (e.g. drawer content) that happen to
  // share a page with the workspace root.
  if (target !== root && !target.contains(root) && !root.contains(target)) {
    return;
  }

  if (
    typeof window.Alpine.destroyTree === "function" &&
    typeof window.Alpine.initTree === "function"
  ) {
    window.Alpine.destroyTree(root);
    window.Alpine.initTree(root);
  }
});

// #970: ref-entity filter dropdown population.
//
// Previously this was inline `<template x-for="opt in options">` inside
// the `<select>`. Idiomorph's attribute-morph loop evaluated the cloned
// `<option>` elements' `:value` / `x-text` bindings before Alpine
// re-established the x-for scope, throwing
// `Alpine Expression Error: opt is not defined` once per option per
// morph (300 errors / 5min in AegisMark site-fuzz on v0.63.11).
//
// Fix: render `<option>` elements via direct DOM manipulation in this
// helper. `x-init="dzFilterRefSelect($el)"` invokes it once when Alpine
// first hydrates the `<select>`. The morph then sees ordinary DOM nodes
// with no Alpine attributes — nothing for idiomorph to evaluate
// prematurely. Same fix shape as #964 (skip Alpine event attrs in
// morph) and #968 (single-quote attrs containing tojson) — all
// "remove the surface idiomorph trips on" rather than "make idiomorph
// understand Alpine."
//
// Reads two data-* attributes from the <select>:
//   - data-ref-api: API endpoint (e.g. /clients) to fetch options from
//   - data-selected-value: the persisted filter value to pre-select
//
// Both are HTML-escaped server-side (no tojson-in-attr footgun).
window.dz = window.dz || {};
window.dz.filterRefSelect = function (selectEl) {
  if (!selectEl || selectEl.tagName !== "SELECT") return;
  const refApi = selectEl.dataset.refApi;
  if (!refApi) return;
  const selectedValue = selectEl.dataset.selectedValue || "";
  // #973 (round 2): wire AbortController to both htmx:before:swap and
  // pagehide. Round 1 only checked `document.body.contains(selectEl)`
  // in .catch — that worked for in-page htmx swaps but not for full
  // browser navigation (Playwright `page.goto`, link clicks, form
  // submits). On full nav the fetch rejects with `TypeError: Failed
  // to fetch` BEFORE the element leaves the DOM, so the contains-
  // check fired too early and the warn still logged.
  //
  // The robust discriminator is an explicit AbortController. We trip
  // it on:
  //   - htmx:before:swap (htmx is about to morph the DOM under us)
  //   - pagehide (full browser navigation, also covers BFCache)
  // Both fire BEFORE the fetch is cancelled, so the rejection arrives
  // as a known AbortError we can swallow cleanly.
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  window.addEventListener("htmx:before:swap", onAbort, { once: true });
  window.addEventListener("pagehide", onAbort, { once: true });

  fetch(refApi + "?page_size=100", {
    headers: { Accept: "application/json" },
    signal: controller.signal,
  })
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((data) => {
      const items = data.items || [];
      const display = (item) => {
        return (
          item.__display__ ||
          item.name ||
          item.company_name ||
          ((item.first_name || "") + " " + (item.last_name || "")).trim() ||
          item.title ||
          item.label ||
          item.email ||
          item.id ||
          ""
        );
      };
      const fragment = document.createDocumentFragment();
      for (const item of items) {
        const opt = document.createElement("option");
        opt.value = item.id;
        opt.textContent = display(item);
        if (String(item.id) === String(selectedValue)) {
          opt.selected = true;
        }
        fragment.appendChild(opt);
      }
      selectEl.appendChild(fragment);
    })
    .catch((err) => {
      // Explicit AbortError from our controller — silent. Covers both
      // htmx swap and full-browser-nav cancellation paths.
      if (err && err.name === "AbortError") return;
      // Defense-in-depth: if the element is gone (e.g. ancestor
      // removed without firing one of our abort signals), still
      // swallow.
      if (!document.body.contains(selectEl)) return;
      console.warn("Filter ref-entity load failed for", refApi, ":", err);
    })
    .finally(() => {
      // Detach listeners — listener accumulation across many filter
      // dropdowns on one page would otherwise grow unbounded. After
      // pagehide this is moot (page going away) but harmless.
      window.removeEventListener("htmx:before:swap", onAbort);
      window.removeEventListener("pagehide", onAbort);
    });
};
// Alpine x-init reads the function from the global scope by bare name.
window.dzFilterRefSelect = window.dz.filterRefSelect;

/* ------------------------------------------------------------------ */
/* #1233 — row_action client handler                                  */
/* ------------------------------------------------------------------ */
/**
 * Delegated click handler for [data-dz-row-action] buttons emitted by
 * `_render_row_action_button` (workspace_card_bodies.py). The button
 * carries:
 *   data-dz-row-action       — the action_id (declared surface action)
 *   data-dz-row-args         — JSON payload of bound row values
 *   data-dz-row-action-url   — POST endpoint resolved server-side from
 *                              the appspec's CREATE surfaces (#1233)
 *
 * When data-dz-row-action-url is present, POST the JSON payload via
 * htmx.ajax so CSRF + redirect/swap behaviour matches the rest of the
 * HTMX-driven runtime. When missing (no matching CREATE surface in the
 * AppSpec), emit a console.warn and no-op — preserves the pre-#1233
 * shape rather than 404ing.
 */
document.addEventListener("click", function (evt) {
  const btn = evt.target.closest("[data-dz-row-action]");
  if (!btn) return;
  // Don't double-fire if a parent already handled this (e.g. surface
  // action machinery hijacks the same data attribute).
  if (evt.defaultPrevented) return;

  const url = btn.getAttribute("data-dz-row-action-url") || "";
  const actionId = btn.getAttribute("data-dz-row-action") || "";
  if (!url) {
    console.warn(
      "[dz] row_action '" +
        actionId +
        "' has no resolved URL " +
        "(data-dz-row-action-url missing) — declare a matching CREATE " +
        "surface in the DSL or check the surface name.",
    );
    return;
  }

  let args = {};
  const argsRaw = btn.getAttribute("data-dz-row-args");
  if (argsRaw) {
    try {
      args = JSON.parse(argsRaw);
    } catch (parseErr) {
      console.warn(
        "[dz] row_action '" +
          actionId +
          "': data-dz-row-args is not " +
          "valid JSON; sending empty body. (" +
          parseErr.message +
          ")",
      );
    }
  }

  evt.preventDefault();
  btn.classList.add("dz-loading");
  btn.disabled = true;

  // htmx.ajax composes CSRF + drives swap. Settle handler restores the
  // button so subsequent clicks fire (no-op rather than disabled forever).
  const htmx = window.htmx;
  if (!htmx || typeof htmx.ajax !== "function") {
    console.warn(
      "[dz] row_action '" +
        actionId +
        "': htmx is not loaded; " +
        "cannot POST. Ensure the runtime bundle is loaded.",
    );
    btn.classList.remove("dz-loading");
    btn.disabled = false;
    return;
  }

  htmx
    .ajax("POST", url, {
      values: args,
      // No target/swap — server typically responds 303 → GET, which
      // htmx follows. If the response is HTML, default swap into body.
      target: "body",
      swap: "none",
    })
    .then(function () {
      btn.classList.remove("dz-loading");
      btn.disabled = false;
    })
    .catch(function (ajaxErr) {
      console.warn(
        "[dz] row_action '" + actionId + "' POST to " + url + " failed: ",
        ajaxErr,
      );
      btn.classList.remove("dz-loading");
      btn.disabled = false;
    });
});

// ── #1294 — App-shell sidebar toggle + persistence ──────────────────
// SSR emits `data-dz-sidebar` on `.dz-app-shell` (default "open") so the
// nav is reachable on first paint. This vanilla, event-delegated
// controller (a) reads the `dz_sidebar` cookie on load and applies it as
// a universal persistence fallback for render paths that default to
// "open", and (b) flips the state + writes the cookie when the topbar
// toggle is clicked. No Alpine dependency — survives HTMX swaps.
(function () {
  "use strict";
  var COOKIE = "dz_sidebar";
  var MAX_AGE = 60 * 60 * 24 * 365; // 1 year
  function shell() {
    return document.querySelector(".dz-app-shell");
  }
  function readCookie() {
    var m = document.cookie.match(/(?:^|;\s*)dz_sidebar=(open|closed)\b/);
    return m ? m[1] : null;
  }
  function syncToggle(state) {
    var t = document.querySelector("[data-dz-sidebar-toggle]");
    if (t) t.setAttribute("aria-expanded", state === "open" ? "true" : "false");
  }
  function apply(state) {
    var el = shell();
    if (!el) return;
    el.setAttribute("data-dz-sidebar", state);
    syncToggle(state);
  }
  function init() {
    var el = shell();
    if (!el) return;
    var persisted = readCookie();
    if (persisted && persisted !== el.getAttribute("data-dz-sidebar")) {
      apply(persisted);
    } else {
      syncToggle(el.getAttribute("data-dz-sidebar") || "open");
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  document.addEventListener("click", function (e) {
    var btn =
      e.target && e.target.closest
        ? e.target.closest("[data-dz-sidebar-toggle]")
        : null;
    if (!btn) return;
    var el = shell();
    if (!el) return;
    var next =
      el.getAttribute("data-dz-sidebar") === "open" ? "closed" : "open";
    apply(next);
    document.cookie =
      COOKIE + "=" + next + "; path=/; max-age=" + MAX_AGE + "; SameSite=Lax";
  });
})();
