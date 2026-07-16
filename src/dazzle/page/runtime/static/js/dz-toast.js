/** @ts-check */
/**
 * HYPERPART: toast
 *
 * Toast stack host — auto-dismiss, hover/focus pause, stack cap, dismiss
 * with leave motion, and client-initiated toasts with server-parity markup.
 *
 * Contract (contracts/toast.py):
 *   Stack:  #dz-toast.dz-toast-stack  [data-dz-toast-cap]
 *   Toast:  .dz-toast[data-dz-toast-level][data-dz-remove-after]
 *   Slots:  .dz-toast__title | .dz-toast__message | .dz-toast__actions
 *   Dismiss: [data-dz-toast-dismiss]
 *
 * Server path: OOB afterbegin into #dz-toast with data-dz-remove-after.
 * Client path: CustomEvent `showToast` (document/body) or `toast` on the
 * stack (window.dz.toast). Detail: { message, type?, title?, actions? }
 * where actions is [{ label, href? }].
 *
 * Timing: default 8s (readable + action-friendly). Leave animation ~300ms
 * before DOM removal. Zero dependencies. Survives htmx swaps.
 */

(function () {
  "use strict";

  var DEFAULT_CAP = 8;
  /** Penguin-aligned default; long enough to read title + act. */
  var DEFAULT_DELAY = "8s";
  /** Match CSS --duration-slow leave; hard ceiling if animationend missed. */
  var LEAVE_MS = 320;

  /** Parse htmx-style timing ("5s", "300ms", bare seconds) → ms. */
  function parseDelayMs(value) {
    if (!value) return 8000;
    var m = String(value)
      .trim()
      .match(/^(\d+(?:\.\d+)?)\s*(ms|s)?$/);
    if (!m) return 8000;
    var n = parseFloat(m[1]);
    if (m[2] === "ms") return n;
    return n * 1000;
  }

  function stackEl() {
    return document.getElementById("dz-toast");
  }

  function toastSelector() {
    // Prefixed source form; apply_prefix rewrites for unprefixed gallery.
    return ".dz-toast";
  }

  function capOf(stack) {
    var raw = stack.getAttribute("data-dz-toast-cap");
    if (raw == null || raw === "") return DEFAULT_CAP;
    var n = parseInt(raw, 10);
    return Number.isFinite(n) && n > 0 ? n : DEFAULT_CAP;
  }

  function enforceCap(stack) {
    var sel = toastSelector();
    var items = stack.querySelectorAll(sel + ":not(.dz-toast-leave)");
    var cap = capOf(stack);
    // Stack prepends newest first — drop from the end (oldest).
    while (items.length > cap) {
      var last = items[items.length - 1];
      dismissToast(last);
      items = stack.querySelectorAll(sel + ":not(.dz-toast-leave)");
    }
  }

  /**
   * Play leave motion then remove. Safe to call multiple times.
   * @param {Element} el
   */
  function dismissToast(el) {
    if (!el || el.__dzToastLeaving) return;
    el.__dzToastLeaving = true;
    if (typeof el.__dzToastPause === "function") el.__dzToastPause();
    el.classList.remove("dz-toast-enter");
    el.classList.add("dz-toast-leave");

    var done = false;
    function finish() {
      if (done) return;
      done = true;
      if (el.parentNode) el.remove();
    }

    el.addEventListener("animationend", finish, { once: true });
    // Fallback when reduced-motion collapses animation or event is missed.
    setTimeout(finish, LEAVE_MS);
  }

  /**
   * Schedule auto-dismiss with pause/resume. Each toast is scheduled once
   * (`__dzRemoveScheduled`). Hover or focus on the stack pauses all timers;
   * leave resumes with remaining time.
   */
  function scheduleOne(el) {
    if (el.__dzRemoveScheduled || el.__dzToastLeaving) return;
    el.__dzRemoveScheduled = true;

    var total = parseDelayMs(el.getAttribute("data-dz-remove-after"));
    var remaining = total;
    var deadline = Date.now() + remaining;
    var timer = null;
    var paused = false;

    function clear() {
      if (timer != null) {
        clearTimeout(timer);
        timer = null;
      }
    }

    function arm() {
      clear();
      if (remaining <= 0) {
        dismissToast(el);
        return;
      }
      deadline = Date.now() + remaining;
      timer = setTimeout(function () {
        dismissToast(el);
      }, remaining);
    }

    el.__dzToastPause = function () {
      if (paused || el.__dzToastLeaving) return;
      paused = true;
      remaining = Math.max(0, deadline - Date.now());
      clear();
    };

    el.__dzToastResume = function () {
      if (!paused || el.__dzToastLeaving) return;
      paused = false;
      arm();
    };

    arm();
  }

  function forEachToast(stack, fn) {
    stack.querySelectorAll(toastSelector()).forEach(fn);
  }

  function pauseAll(stack) {
    forEachToast(stack, function (el) {
      if (typeof el.__dzToastPause === "function") el.__dzToastPause();
    });
  }

  function resumeAll(stack) {
    forEachToast(stack, function (el) {
      if (typeof el.__dzToastResume === "function") el.__dzToastResume();
    });
  }

  function wireStackOnce(stack) {
    if (stack.__dzToastHostWired) return;
    stack.__dzToastHostWired = true;

    // mouseover/out bubble through children (stack itself is pointer-events:none).
    stack.addEventListener("mouseover", function () {
      pauseAll(stack);
    });
    stack.addEventListener("mouseout", function (e) {
      var related = e.relatedTarget;
      if (related && stack.contains(related)) return;
      resumeAll(stack);
    });
    stack.addEventListener("focusin", function () {
      pauseAll(stack);
    });
    stack.addEventListener("focusout", function (e) {
      var related = e.relatedTarget;
      if (related && stack.contains(related)) return;
      resumeAll(stack);
    });

    stack.addEventListener("click", function (e) {
      var t = e.target;
      if (!t || !t.closest) return;
      var dismiss = t.closest("[data-dz-toast-dismiss]");
      if (!dismiss || !stack.contains(dismiss)) return;
      var toast = dismiss.closest(toastSelector());
      if (toast) dismissToast(toast);
    });
  }

  function scan(root) {
    var stack = stackEl();
    if (stack) {
      wireStackOnce(stack);
      forEachToast(stack, function (el) {
        if (!el.classList.contains("dz-toast-enter") && !el.classList.contains("dz-toast-leave")) {
          // OOB-inserted toasts may lack the enter class — give them motion.
          el.classList.add("dz-toast-enter");
        }
        scheduleOne(el);
      });
      enforceCap(stack);
    }
    // Also schedule any data-dz-remove-after outside the stack (legacy).
    var scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll("[data-dz-remove-after]").forEach(function (el) {
      if (el.classList && el.classList.contains("dz-toast")) {
        scheduleOne(el);
      } else if (!el.__dzRemoveScheduled) {
        // Non-toast remove-after (if any): simple timeout, no pause.
        el.__dzRemoveScheduled = true;
        setTimeout(function () {
          el.remove();
        }, parseDelayMs(el.getAttribute("data-dz-remove-after")));
      }
    });
    if (scope !== document) {
      document.querySelectorAll(".dz-toast[data-dz-remove-after]").forEach(scheduleOne);
    }
  }

  /**
   * @param {string|object} messageOrOpts
   * @param {string} [level]
   */
  function clientToast(messageOrOpts, level) {
    var stack = stackEl();
    if (!stack) return;

    var opts =
      messageOrOpts && typeof messageOrOpts === "object"
        ? messageOrOpts
        : { message: messageOrOpts, type: level };

    var message = opts.message;
    if (!message) return;

    var tone = opts.type || opts.level || "info";
    var title = opts.title || null;
    var actions = opts.actions || null;
    var duration = opts.duration || DEFAULT_DELAY;

    var toast = document.createElement("div");
    toast.className = "dz-toast dz-toast-enter";
    toast.setAttribute("data-dz-toast-level", tone);
    toast.setAttribute("data-dz-remove-after", duration);
    toast.setAttribute("role", tone === "error" ? "alert" : "status");

    var body = document.createElement("div");
    body.className = "dz-toast__body";

    if (title) {
      var titleEl = document.createElement("div");
      titleEl.className = "dz-toast__title";
      titleEl.textContent = String(title);
      body.appendChild(titleEl);
    }

    var msgEl = document.createElement("div");
    msgEl.className = "dz-toast__message";
    msgEl.textContent = String(message);
    body.appendChild(msgEl);

    if (actions && actions.length) {
      var row = document.createElement("div");
      row.className = "dz-toast__actions";
      for (var i = 0; i < actions.length; i++) {
        var a = actions[i] || {};
        var label = a.label || a.text;
        if (!label) continue;
        var node;
        if (a.href) {
          node = document.createElement("a");
          node.className = "dz-toast__action";
          node.href = String(a.href);
          node.textContent = String(label);
        } else {
          node = document.createElement("button");
          node.type = "button";
          node.className = "dz-toast__action";
          node.setAttribute("data-dz-toast-dismiss", "");
          node.textContent = String(label);
        }
        row.appendChild(node);
      }
      if (row.childNodes.length) body.appendChild(row);
    }

    toast.appendChild(body);

    var close = document.createElement("button");
    close.type = "button";
    close.className = "dz-toast__close";
    close.setAttribute("data-dz-toast-dismiss", "");
    close.setAttribute("aria-label", "Dismiss");
    toast.appendChild(close);

    stack.insertBefore(toast, stack.firstChild);
    enforceCap(stack);
    scheduleOne(toast);
  }

  // window.dz.toast(msg, type) → CustomEvent `toast` on the stack (no bubble).
  document.addEventListener(
    "toast",
    function (e) {
      var t = e && e.target;
      if (!t || t.id !== "dz-toast") return;
      var d = e.detail || {};
      clientToast(d);
    },
    true,
  );

  // Optimistic rollback / HX-Trigger path — showToast on document/body.
  document.addEventListener(
    "showToast",
    function (e) {
      var d = (e && e.detail) || {};
      clientToast(d);
    },
    true,
  );

  document.addEventListener("htmx:after:swap", function (e) {
    scan(e && e.target);
  });
  // htmx 2 legacy alias if present
  document.addEventListener("htmx:afterSwap", function (e) {
    scan(e && e.target);
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      scan(document);
    });
  } else {
    scan(document);
  }

  // Optional global for demos / window.dz parity.
  if (typeof window !== "undefined") {
    window.dz = window.dz || {};
    if (typeof window.dz.toast !== "function") {
      window.dz.toast = function (message, type) {
        var stack = stackEl();
        if (!stack) {
          clientToast(message, type);
          return;
        }
        stack.dispatchEvent(
          new CustomEvent("toast", {
            detail:
              message && typeof message === "object"
                ? message
                : { message: message, type: type },
          }),
        );
      };
    }
  }
})();
