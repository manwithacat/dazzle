/** @ts-check */
/**
 * HYPERPART: toast
 *
 * Toast stack host — auto-dismiss, hover/focus pause, stack cap, dismiss
 * with leave motion, swipe-dismiss, opt-in enter cue, and client-initiated
 * toasts with server-parity markup (stem ssr-client-slot-parity).
 *
 * Contract (contracts/toast.py):
 *   Stack:  #dz-toast.dz-toast-stack  [data-dz-toast-cap]
 *   Toast:  .dz-toast[data-dz-toast-level][data-dz-remove-after]
 *   Slots:  .dz-toast__title | .dz-toast__message | .dz-toast__actions
 *           optional person: data-dz-toast-composition=person + __avatar / __actor
 *   Dismiss: [data-dz-toast-dismiss]
 *
 * Server path: OOB afterbegin into #dz-toast with data-dz-remove-after.
 * Client path: CustomEvent `showToast` (document/body) or `toast` on the
 * stack (window.dz.toast). Detail mirrors ToastSlots:
 *   { message, type?, title?, actions?, actor?: {name, avatar?},
 *     duration?, sound? }
 *
 * Sound: unit `data-dz-toast-sound=on` or detail.sound — page must also opt
 * in via meta dz-sound or data-dz-cue-sound (controllers/dz-cue.js).
 *
 * Timing: default 8s / 10s error. Leave ~300ms. Swipe toward stack edge
 * dismisses (threshold 48px). Zero hard deps. Survives htmx swaps.
 */

(function () {
  "use strict";

  var DEFAULT_CAP = 8;
  var DEFAULT_DELAY = "8s";
  var ERROR_DELAY = "10s";
  var LEAVE_MS = 320;
  var SWIPE_PX = 48;

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

  function defaultDelayFor(level) {
    return level === "error" ? ERROR_DELAY : DEFAULT_DELAY;
  }

  var ICON_SHAPES = {
    info: [
      ["circle", { cx: "12", cy: "12", r: "10" }],
      ["path", { d: "M12 16v-4" }],
      ["path", { d: "M12 8h.01" }],
    ],
    success: [
      ["circle", { cx: "12", cy: "12", r: "10" }],
      ["path", { d: "m9 12 2 2 4-4" }],
    ],
    warning: [
      [
        "path",
        {
          d:
            "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3",
        },
      ],
      ["path", { d: "M12 9v4" }],
      ["path", { d: "M12 17h.01" }],
    ],
    error: [
      ["circle", { cx: "12", cy: "12", r: "10" }],
      ["path", { d: "m15 9-6 6" }],
      ["path", { d: "m9 9 6 6" }],
    ],
  };

  function makeIcon(tone) {
    var shapes = ICON_SHAPES[tone] || ICON_SHAPES.info;
    var wrap = document.createElement("span");
    wrap.className = "dz-toast__icon";
    wrap.setAttribute("aria-hidden", "true");
    var NS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    for (var i = 0; i < shapes.length; i++) {
      var spec = shapes[i];
      var node = document.createElementNS(NS, spec[0]);
      var attrs = spec[1];
      for (var k in attrs) {
        if (Object.prototype.hasOwnProperty.call(attrs, k)) {
          node.setAttribute(k, attrs[k]);
        }
      }
      svg.appendChild(node);
    }
    wrap.appendChild(svg);
    return wrap;
  }

  function makeAvatar(actorName, avatarUrl) {
    if (avatarUrl) {
      var img = document.createElement("img");
      img.className = "dz-toast__avatar";
      img.src = String(avatarUrl);
      img.alt = "";
      img.width = 32;
      img.height = 32;
      img.decoding = "async";
      return img;
    }
    var span = document.createElement("span");
    span.className = "dz-toast__avatar dz-toast__avatar--fallback";
    span.setAttribute("aria-hidden", "true");
    var name = String(actorName || "?").trim();
    span.textContent = (name.charAt(0) || "?").toUpperCase();
    return span;
  }

  function isPersonToast(el) {
    return el.getAttribute("data-dz-toast-composition") === "person";
  }

  function ensureIcon(el) {
    if (isPersonToast(el)) return;
    if (el.querySelector(".dz-toast__icon, .dz-toast-icon, .dz-toast__avatar")) return;
    var tone = el.getAttribute("data-dz-toast-level") || "info";
    var body = el.querySelector(".dz-toast__body");
    var icon = makeIcon(tone);
    if (body && body.parentNode === el) {
      el.insertBefore(icon, body);
    } else {
      el.insertBefore(icon, el.firstChild);
    }
  }

  function ensureProgress(el, totalMs) {
    var bar = el.querySelector(".dz-toast__progress");
    if (!bar) {
      bar = document.createElement("div");
      bar.className = "dz-toast__progress";
      bar.setAttribute("aria-hidden", "true");
      el.appendChild(bar);
    }
    bar.style.animationDuration = totalMs + "ms";
    return bar;
  }

  function setProgressPaused(el, paused) {
    var bar = el.querySelector(".dz-toast__progress");
    if (bar) bar.style.animationPlayState = paused ? "paused" : "running";
  }

  function stackEl() {
    return document.getElementById("dz-toast");
  }

  function toastSelector() {
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
    while (items.length > cap) {
      var last = items[items.length - 1];
      dismissToast(last);
      items = stack.querySelectorAll(sel + ":not(.dz-toast-leave)");
    }
  }

  function playEnterCue(el) {
    var unitWants =
      el.getAttribute("data-dz-toast-sound") === "on" ||
      el.getAttribute("data-dz-toast-sound") === "true";
    if (!unitWants) return;
    var tone = el.getAttribute("data-dz-toast-level") || "info";
    if (window.dzCue && typeof window.dzCue.play === "function") {
      window.dzCue.play(tone);
    }
  }

  function dismissToast(el) {
    if (!el || el.__dzToastLeaving) return;
    el.__dzToastLeaving = true;
    if (typeof el.__dzToastPause === "function") el.__dzToastPause();
    el.classList.remove("dz-toast-enter");
    el.classList.add("dz-toast-leave");
    setProgressPaused(el, true);
    el.style.transform = "";
    el.style.opacity = "";

    var done = false;
    function finish() {
      if (done) return;
      done = true;
      if (el.parentNode) el.remove();
    }

    function onEnd(e) {
      if (e && e.target !== el) return;
      if (e && e.animationName && e.animationName.indexOf("toast-out") === -1) return;
      finish();
    }
    el.addEventListener("animationend", onEnd);
    setTimeout(finish, LEAVE_MS);
  }

  /**
   * Horizontal swipe toward the stack's outer edge → dismiss.
   * Threshold 48px; ignores mostly-vertical gestures.
   */
  function wireSwipe(el) {
    if (el.__dzToastSwipeWired) return;
    el.__dzToastSwipeWired = true;
    var startX = 0;
    var startY = 0;
    var tracking = false;

    el.addEventListener("pointerdown", function (e) {
      if (el.__dzToastLeaving) return;
      if (e.button != null && e.button !== 0) return;
      tracking = true;
      startX = e.clientX;
      startY = e.clientY;
      try {
        el.setPointerCapture(e.pointerId);
      } catch (_err) {
        /* ignore */
      }
    });

    el.addEventListener("pointermove", function (e) {
      if (!tracking || el.__dzToastLeaving) return;
      var dx = e.clientX - startX;
      var dy = e.clientY - startY;
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
      // Prefer horizontal
      if (Math.abs(dx) > Math.abs(dy)) {
        // Top-right stack: positive dx (outward) feels natural
        var shift = Math.max(0, dx);
        el.style.transform = "translateX(" + shift + "px)";
        el.style.opacity = String(Math.max(0.35, 1 - shift / 120));
      }
    });

    function endPointer(e) {
      if (!tracking) return;
      tracking = false;
      var dx = e.clientX - startX;
      var dy = e.clientY - startY;
      el.style.transform = "";
      el.style.opacity = "";
      if (el.__dzToastLeaving) return;
      if (dx >= SWIPE_PX && Math.abs(dx) > Math.abs(dy)) {
        dismissToast(el);
      }
    }

    el.addEventListener("pointerup", endPointer);
    el.addEventListener("pointercancel", endPointer);
  }

  function scheduleOne(el) {
    if (el.__dzRemoveScheduled || el.__dzToastLeaving) return;
    el.__dzRemoveScheduled = true;

    var total = parseDelayMs(el.getAttribute("data-dz-remove-after"));
    var remaining = total;
    var deadline = Date.now() + remaining;
    var timer = null;
    var paused = false;

    ensureProgress(el, total);
    wireSwipe(el);
    playEnterCue(el);

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
      setProgressPaused(el, true);
    };

    el.__dzToastResume = function () {
      if (!paused || el.__dzToastLeaving) return;
      paused = false;
      setProgressPaused(el, false);
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
          el.classList.add("dz-toast-enter");
        }
        ensureIcon(el);
        scheduleOne(el);
      });
      enforceCap(stack);
    }
    var scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll("[data-dz-remove-after]").forEach(function (el) {
      if (el.classList && el.classList.contains("dz-toast")) {
        scheduleOne(el);
      } else if (!el.__dzRemoveScheduled) {
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
    var duration = opts.duration || defaultDelayFor(tone);
    var actor = opts.actor || null;
    var actorName = (actor && actor.name) || opts.actor_name || null;
    var actorAvatar =
      (actor && (actor.avatar || actor.avatar_url)) || opts.actor_avatar || null;
    var wantSound = !!(opts.sound || opts.cue);

    var toast = document.createElement("div");
    toast.className = "dz-toast dz-toast-enter";
    toast.setAttribute("data-dz-toast-level", tone);
    toast.setAttribute("data-dz-remove-after", duration);
    toast.setAttribute("role", tone === "error" ? "alert" : "status");
    if (wantSound) toast.setAttribute("data-dz-toast-sound", "on");

    var isPerson = !!(actorName && String(actorName).trim());
    if (isPerson) {
      toast.setAttribute("data-dz-toast-composition", "person");
      toast.appendChild(makeAvatar(actorName, actorAvatar));
    } else {
      toast.appendChild(makeIcon(tone));
    }

    var body = document.createElement("div");
    body.className = "dz-toast__body";

    if (isPerson) {
      var actorEl = document.createElement("div");
      actorEl.className = "dz-toast__title dz-toast__actor";
      actorEl.textContent = String(actorName);
      body.appendChild(actorEl);
      if (title) {
        var sub = document.createElement("div");
        sub.className = "dz-toast__subtitle";
        sub.textContent = String(title);
        body.appendChild(sub);
      }
    } else if (title) {
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

  document.addEventListener(
    "toast",
    function (e) {
      var t = e && e.target;
      if (!t || t.id !== "dz-toast") return;
      clientToast(e.detail || {});
    },
    true,
  );

  document.addEventListener(
    "showToast",
    function (e) {
      clientToast((e && e.detail) || {});
    },
    true,
  );

  document.addEventListener("htmx:after:swap", function (e) {
    scan(e && e.target);
  });
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
