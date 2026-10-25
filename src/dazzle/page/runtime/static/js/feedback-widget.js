/**
 * Dazzle Feedback Widget — feedback reports and review notes.
 *
 * Mounted by the app chrome under `feedback_widget: enabled`, in a
 * `<dz-feedback>` host on <body> with an open shadow root (STYLES is its
 * stylesheet). DOM is built with createElement; user text uses textContent.
 *
 * Metas (defaults when absent): dz-user-email / dz-user-role (no email → no
 * mount), dz-feedback-shortcut (#1842; backtick, `none` off), -categories
 * and -severities (comma lists), -screenshot (off|optional),
 * -review-shortcut (alt+shift+r, `none` off), -review ("1": review posture).
 * Body data-dz-surface / -entity / -record / -workspace / -persona name the page.
 *
 * Report posture: button or shortcut → panel → POST /feedbackreports with an
 * Idempotency-Key, queued in localStorage until the server has it. Review
 * posture: the chord or "Point at it" arms anchor mode; hover outlines the
 * element, a capture-phase click (htmx never sees it) opens a note card
 * beside it; Enter saves, Shift+Enter newline, Esc cancels, focus returns to
 * the element. Open notes on the page are numbered pins re-anchored
 * dz_anchor → css → text quote → rect (orphaned).
 *
 * Mounting is idempotent, the host is put back after an htmx body swap, and
 * nothing shows on load except one toast per newly resolved report (#869).
 * #1841: dialogs are inert + aria-hidden while closed, trap Tab, close on
 * Escape and return focus to their opener.
 */
(function () {
  "use strict";

  if (window.feedbackWidget) return;

  var ENDPOINT = "/feedbackreports";
  var PENDING_KEY = "dz_feedback_pending";
  var NAV_KEY = "dz_feedback_nav";
  var SESSION_KEY = "dz_feedback_session";
  var MAX_AGE = 24 * 60 * 60 * 1000;
  var MAX_JSON = 60 * 1024;
  var MAX_FIELDS = 30 * 1024;
  var MAX_SHOT = 1.5 * 1024 * 1024;
  var DEFAULT_CATEGORIES = "bug,ux,visual,behaviour,enhancement,other";
  var DEFAULT_SEVERITIES = "blocker,annoying,minor";

  // Shadow stylesheet: px units, colours from the page's tokens. The
  // description border uses --colour-border-control (3:1, WCAG 1.4.11, #1842).
  var STYLES =
    ":host{display:block;font:14px/1.4 var(--font-system,system-ui,sans-serif);color:var(--colour-text);direction:ltr}" +
    "*{box-sizing:border-box}button,select,textarea{font:inherit;color:inherit}" +
    ".dz-feedback-btn{position:fixed;bottom:24px;right:24px;width:48px;height:48px;border-radius:50%;background:var(--colour-brand);color:var(--colour-brand-contrast);border:0;cursor:pointer;z-index:9998;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 12px rgb(0 0 0/.15)}" +
    ".dz-feedback-btn svg{width:20px;height:20px}" +
    ".dz-feedback-panel{position:fixed;top:0;right:0;width:384px;max-width:100vw;height:100dvh;background:var(--colour-surface);border-left:1px solid var(--colour-border);box-shadow:-4px 0 12px rgb(0 0 0/.1);z-index:9999;transform:translateX(100%);display:flex;flex-direction:column;overflow-y:auto}" +
    ".dz-feedback-panel.open{transform:none}" +
    ".dz-feedback-header{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid var(--colour-border)}" +
    ".dz-feedback-header h3{margin:0;font-size:16px;font-weight:600}" +
    ".dz-feedback-close{background:0;border:0;cursor:pointer;font-size:20px;padding:4px}" +
    ".dz-feedback-body{padding:20px;flex:1;display:flex;flex-direction:column;gap:16px}" +
    ".dz-feedback-categories{display:grid;grid-template-columns:1fr 1fr;gap:8px}" +
    ".dz-feedback-severities,.dz-feedback-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}" +
    ".dz-feedback-cat-btn,.dz-feedback-sev-btn,.dz-feedback-ghost{padding:8px 12px;border:1px solid var(--colour-border);border-radius:6px;background:var(--colour-surface-muted);cursor:pointer;font-size:13px}" +
    ".dz-feedback-sev-btn{flex:1;padding:6px 8px;font-size:12px}.dz-feedback-ghost{background:var(--colour-surface)}" +
    ".selected{background:var(--colour-brand);color:var(--colour-brand-contrast);border-color:var(--colour-brand)}" +
    ".selected[data-severity=blocker],.selected[data-severity=p1]{background:var(--danger-600);border-color:var(--danger-600);color:#fff}" +
    ".selected[data-severity=annoying],.selected[data-severity=p2]{background:var(--warning-600);border-color:var(--warning-600);color:#fff}" +
    ".selected[data-severity=minor],.selected[data-severity=p3]{background:var(--success-600);border-color:var(--success-600);color:#fff}" +
    ".dz-feedback-description,.dz-feedback-select{width:100%;padding:8px 12px;border:1px solid var(--colour-border-control);border-radius:6px;background:var(--colour-surface)}" +
    ".dz-feedback-description{min-height:96px;resize:vertical}.dz-feedback-card .dz-feedback-description{min-height:72px}" +
    ".dz-feedback-description:focus,.dz-feedback-select:focus{outline:2px solid var(--colour-brand);outline-offset:-1px}" +
    ".dz-feedback-submit{padding:10px 16px;border:0;border-radius:6px;background:var(--colour-brand);color:var(--colour-brand-contrast);font-weight:600;cursor:pointer}" +
    ".dz-feedback-body .dz-feedback-submit{width:100%}.dz-feedback-submit:disabled{opacity:.5;cursor:not-allowed}" +
    ".dz-feedback-label{font-size:13px;font-weight:500;display:block}.dz-feedback-hint{font-size:12px;color:var(--colour-text-muted)}.dz-feedback-row .dz-feedback-hint{margin-left:auto}" +
    ".dz-feedback-toast{position:fixed;bottom:80px;right:24px;max-width:360px;padding:12px 20px;border-radius:6px;background:var(--success-600);color:#fff;z-index:10001;display:none}.dz-feedback-toast.visible{display:block}" +
    ".dz-feedback-backdrop{position:fixed;inset:0;background:rgb(0 0 0/.3);z-index:9998;display:none}.dz-feedback-backdrop.visible{display:block}" +
    ".dz-feedback-outline{position:fixed;pointer-events:none;z-index:10000;border:2px solid var(--colour-brand);border-radius:4px;display:none}.dz-feedback-outline.visible{display:block}" +
    ".dz-feedback-outline span,.dz-feedback-path{font:11px/1.4 ui-monospace,Menlo,monospace;word-break:break-all}" +
    ".dz-feedback-outline span{position:absolute;left:-2px;bottom:100%;margin-bottom:2px;max-width:60vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;background:var(--colour-brand);color:var(--colour-brand-contrast);padding:1px 6px;border-radius:3px}" +
    ".dz-feedback-path{color:var(--colour-text-muted)}" +
    ".dz-feedback-card,.dz-feedback-note{position:fixed;z-index:10001;width:320px;max-width:calc(100vw - 16px);background:var(--colour-surface);border:1px solid var(--colour-border);border-radius:10px;box-shadow:0 8px 28px rgb(0 0 0/.25);padding:12px;display:none;flex-direction:column;gap:8px}" +
    ".dz-feedback-card.open,.dz-feedback-note.open{display:flex}.dz-feedback-note p{margin:0;white-space:pre-wrap;word-break:break-word}" +
    ".dz-feedback-pin{position:fixed;z-index:9997;width:22px;height:22px;border-radius:50%;border:2px solid #fff;background:var(--danger-600);color:#fff;font:700 11px/1 var(--font-system,system-ui,sans-serif);cursor:pointer;padding:0;box-shadow:0 2px 6px rgb(0 0 0/.3)}" +
    ".dz-feedback-pin[data-status=triaged]{background:var(--warning-600)}.dz-feedback-pin[data-orphaned]{background:var(--colour-text-muted);border-style:dashed}" +
    ".dz-feedback-shot{position:fixed;inset:0;z-index:10002;background:rgb(0 0 0/.75);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:16px;color:#fff}" +
    ".dz-feedback-shot canvas{max-width:100%;max-height:calc(100vh - 80px);cursor:crosshair;background:#fff}";

  function mk(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function set(e, attrs) {
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }

  function btn(cls, text, onClick) {
    var b = mk("button", cls, text);
    b.type = "button";
    b.addEventListener("click", onClick);
    return b;
  }

  function chatIcon() {
    var ns = "http://www.w3.org/2000/svg";
    var svg = set(document.createElementNS(ns, "svg"), {
      viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2",
      "aria-hidden": "true", focusable: "false",
    });
    svg.appendChild(set(document.createElementNS(ns, "path"), {
      d: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
    }));
    return svg;
  }

  function metaRaw(name) {
    var el = document.querySelector('meta[name="' + name + '"]');
    return el ? el.getAttribute("content") : null;
  }

  function meta(name) {
    return (metaRaw(name) || "").trim();
  }

  function metaList(name, fallback) {
    var out = [];
    (meta(name) || fallback).split(",").forEach(function (v) {
      if (v.trim()) out.push(v.trim());
    });
    return out.length ? out : fallback.split(",");
  }

  function sentence(v) {
    return v.charAt(0).toUpperCase() + v.slice(1);
  }

  function bodyData(name) {
    var b = document.body;
    return (b && b.getAttribute("data-dz-" + name)) || "";
  }

  function esc(v) {
    return window.CSS && CSS.escape ? CSS.escape(v) : String(v).replace(/["\\]/g, "\\$&");
  }

  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      return (c === "x" ? r : (r & 3) | 8).toString(16);
    });
  }

  function collapse(s) {
    return String(s || "").replace(/\s+/g, " ").trim();
  }

  function headers(extra) {
    var h = { "Content-Type": "application/json" };
    var csrf = meta("csrf-token");
    if (csrf) h["X-CSRF-Token"] = csrf;
    for (var k in extra) h[k] = extra[k];
    return h;
  }

  /** The page without query or hash: what pins are listed by. */
  function pageKey() {
    return location.origin + location.pathname;
  }

  function store(kind, key, value) {
    try {
      var s = window[kind];
      if (value === undefined) return s.getItem(key);
      if (value === null) s.removeItem(key);
      else s.setItem(key, value);
    } catch (_) {
      return null;
    }
  }

  function parseJson(v, fallback) {
    if (v && typeof v === "object") return v;
    try {
      return v ? JSON.parse(v) : fallback;
    } catch (_) {
      return fallback;
    }
  }

  function safeJson(v) {
    try {
      return JSON.stringify(v);
    } catch (_) {
      return String(v);
    }
  }

  /** The real event target, through the shadow boundary. */
  function target(e) {
    var p = e.composedPath ? e.composedPath() : null;
    return (p && p[0]) || e.target;
  }

  /** Closed: `inert` + `aria-hidden`; open: neither (#1841). */
  function setHidden(el, hidden) {
    if (hidden) set(el, { inert: "", "aria-hidden": "true" });
    else {
      el.removeAttribute("inert");
      el.removeAttribute("aria-hidden");
    }
    el.inert = hidden;
  }

  function setPressed(b, on) {
    b.classList.toggle("selected", on);
    b.setAttribute("aria-pressed", on ? "true" : "false");
  }

  /* @medv/finder 4.0.2 — MIT, Copyright (c) 2018 Anton Medvedev,
     https://github.com/antonmedv/finder. Vendored in ES5 (generators
     unrolled); attribute predicate limited to data-dz-*, name, id,
     data-test-id; 200 ms timeout; a 0-match candidate is skipped. */

  function wordLike(name) {
    if (!/^[a-z\-]{3,}$/i.test(name)) return false;
    var words = name.split(/-|[A-Z]/);
    for (var i = 0; i < words.length; i++) {
      if (words[i].length <= 2 || /[^aeiou]{4,}/i.test(words[i])) return false;
    }
    return true;
  }

  function attrOk(name, value) {
    var ok = { name: 1, id: 1, "data-test-id": 1 }[name] || name.indexOf("data-dz-") === 0;
    return !!ok && value.length > 0 && value.length < 100 && !/[\s"\\]/.test(value);
  }

  function nthIndex(input, tag) {
    var parent = input.parentNode;
    if (!parent || !parent.firstChild) return;
    var i = 0;
    for (var c = parent.firstChild; c; c = c.nextSibling) {
      if (c.nodeType === 1 && (!tag || c.tagName.toLowerCase() === tag)) i++;
      if (c === input) return i;
    }
  }

  function tie(el) {
    var level = [], i;
    var id = el.getAttribute("id");
    if (id && wordLike(id)) level.push({ name: "#" + esc(id), penalty: 0 });
    for (i = 0; i < el.classList.length; i++) {
      if (wordLike(el.classList[i])) level.push({ name: "." + esc(el.classList[i]), penalty: 1 });
    }
    for (i = 0; i < el.attributes.length; i++) {
      var a = el.attributes[i];
      if (attrOk(a.name, a.value)) level.push({ name: "[" + esc(a.name) + '="' + esc(a.value) + '"]', penalty: 2 });
    }
    var tag = el.tagName.toLowerCase();
    level.push({ name: tag, penalty: 5 });
    var idx = nthIndex(el, tag);
    if (idx) level.push({ name: tag + ":nth-of-type(" + idx + ")", penalty: 10 });
    var nth = nthIndex(el);
    if (nth) level.push({ name: tag + ":nth-child(" + nth + ")", penalty: 50 });
    return level;
  }

  function selectorOf(path) {
    var node = path[0], q = node.name;
    for (var i = 1; i < path.length; i++) {
      q = path[i].name + (node.level === (path[i].level || 0) - 1 ? " > " : " ") + q;
      node = path[i];
    }
    return q;
  }

  function byPenalty(a, b) {
    var pa = 0, pb = 0, i;
    for (i = 0; i < a.length; i++) pa += a[i].penalty;
    for (i = 0; i < b.length; i++) pb += b[i].penalty;
    return pa - pb;
  }

  function combinations(stack, path, out) {
    if (!stack.length) out.push(path);
    else for (var i = 0; i < stack[0].length; i++) combinations(stack.slice(1), path.concat(stack[0][i]), out);
    return out;
  }

  function matches(path) {
    try {
      return document.querySelectorAll(selectorOf(path));
    } catch (_) {
      return [];
    }
  }

  function optimize(path, input, deadline, out) {
    if (path.length > 2) {
      for (var i = 1; i < path.length - 1 && Date.now() < deadline; i++) {
        var shorter = path.slice(0, i).concat(path.slice(i + 1)), m = matches(shorter);
        if (m.length === 1 && m[0] === input) {
          out.push(shorter);
          optimize(shorter, input, deadline, out);
        }
      }
    }
    return out;
  }

  /** A unique CSS selector for `input` under document.body. */
  function finder(input) {
    var root = document.body, deadline = Date.now() + 200;
    var stack = [], paths = [], found = null, late = false, level = 0;
    var check = function (cands) {
      cands.sort(byPenalty);
      for (var k = 0; k < cands.length && !found && !late; k++) {
        if (Date.now() > deadline) late = true;
        else if (matches(cands[k]).length === 1) found = cands[k];
      }
      return found || late;
    };
    for (var cur = input; cur && cur !== root && !check([]); cur = cur.parentElement) {
      var lvl = tie(cur);
      for (var n = 0; n < lvl.length; n++) lvl[n].level = level;
      stack.push(lvl);
      level++;
      paths = combinations(stack, [], paths);
      if (level >= 3 && !check(paths)) paths = [];
    }
    if (!found && !late) check(paths);
    if (!found) {
      paths = [];
      for (var c = input, i = 0; c && c !== root; c = c.parentElement) {
        var t = c.tagName.toLowerCase();
        paths.push({ name: t + ":nth-of-type(" + (nthIndex(c, t) || 1) + ")", level: i++ });
      }
      return paths.length ? selectorOf(paths) : null;
    }
    var better = optimize(found, input, deadline, []);
    better.sort(byPenalty);
    return selectorOf(better[0] || found);
  }

  /* Anchors */

  function fieldName(field) {
    var label = field.querySelector("label[for]"), input = field.querySelector("[name]");
    return label ? label.getAttribute("for") : input ? input.getAttribute("name") : "";
  }

  /** "surface/region/row-or-field/action" walking up from `el`; null when
   *  only the surface is known. */
  function dzAnchor(el) {
    var parts = [], seen = {};
    for (var n = el; n && n !== document.body && n.nodeType === 1; n = n.parentElement) {
      var v = null;
      if (!seen.a && n.hasAttribute("data-dz-action")) {
        v = n.getAttribute("data-dz-action");
        seen.a = 1;
      } else if (!seen.r && n.hasAttribute("data-dz-row-id")) {
        v = n.getAttribute("data-dz-row-id");
        seen.r = 1;
      } else if (!seen.r && n.classList.contains("dz-form-field")) {
        v = fieldName(n);
        seen.r = 1;
      } else if (!seen.g && n.hasAttribute("data-dz-region-name")) {
        v = n.getAttribute("data-dz-region-name");
        seen.g = 1;
      }
      if (v) parts.unshift(v);
    }
    return parts.length ? [bodyData("surface") || "*"].concat(parts).join("/") : null;
  }

  function resolveDzAnchor(path) {
    if (!path) return null;
    var segs = path.split("/"), surface = bodyData("surface");
    if (segs[0] !== "*" && surface && segs[0] !== surface) return null;
    var node = document.body;
    for (var i = 1; i < segs.length && node; i++) {
      var q = esc(segs[i]);
      var hit = node.querySelector('label[for="' + q + '"],[name="' + q + '"]');
      node =
        node.querySelector('[data-dz-region-name="' + q + '"],[data-dz-row-id="' + q + '"]') ||
        (hit && hit.closest(".dz-form-field")) ||
        node.querySelector('[data-dz-action="' + q + '"]');
    }
    return node === document.body ? null : node;
  }

  function textQuote(el) {
    var exact = collapse(el.textContent).slice(0, 64);
    if (!exact) return null;
    var around = el.parentElement ? collapse(el.parentElement.textContent) : "";
    var at = around.indexOf(exact);
    return {
      exact: exact,
      prefix: at > 0 ? around.slice(Math.max(0, at - 32), at) : "",
      suffix: at >= 0 ? around.slice(at + exact.length, at + exact.length + 32) : "",
    };
  }

  function anchorRecord(el) {
    var r = el.getBoundingClientRect();
    return {
      dz_anchor: dzAnchor(el),
      css: finder(el),
      text_quote: textQuote(el),
      rect: { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) },
      scroll: { x: Math.round(window.scrollX || 0), y: Math.round(window.scrollY || 0) },
      viewport: [window.innerWidth, window.innerHeight],
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute("role") || null,
    };
  }

  /** Place a fixed box beside `rect`: right, else left, else below; clamped. */
  function placeBeside(box, rect, w, h) {
    var vw = window.innerWidth, vh = window.innerHeight;
    var left = rect.left + rect.width + 8, top = rect.top;
    if (left + w > vw) left = rect.left - w - 8;
    if (left < 8) {
      left = Math.max(8, Math.min(rect.left, vw - w - 8));
      top = rect.top + rect.height + 8;
    }
    box.style.left = Math.round(left) + "px";
    box.style.top = Math.round(Math.min(Math.max(8, top), Math.max(8, vh - h - 8))) + "px";
  }

  /* Shortcuts (#1842, WCAG 2.1.4) */

  var KEY_ALIASES = {
    backtick: "`", backquote: "`", grave: "`", slash: "/", backslash: "\\", question: "?",
    period: ".", comma: ",", semicolon: ";", quote: "'", space: " ", esc: "Escape",
  };
  var MODIFIERS = { ctrl: "ctrl", control: "ctrl", alt: "alt", option: "alt",
    shift: "shift", meta: "meta", cmd: "meta", command: "meta" };
  var OFF_VALUES = { "": 1, none: 1, off: 1, disabled: 1, "false": 1 };

  /** {key, ctrl, alt, shift, meta}, or null when off. No meta → `fallback`.
   *  Combos join with `+` or `-` (`ctrl+shift+f`); the last part is the key. */
  function parseShortcut(raw, fallback) {
    var spec = raw == null ? fallback : String(raw).trim();
    if (OFF_VALUES[spec.toLowerCase()]) return null;
    var parts = spec.length === 1 ? [spec] : spec.split(/[+-](?=.)/);
    var out = { key: "", ctrl: false, alt: false, shift: false, meta: false };
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i].trim(), lower = p.toLowerCase();
      if (i < parts.length - 1 && MODIFIERS[lower]) out[MODIFIERS[lower]] = true;
      else out.key = KEY_ALIASES[lower] || p;
    }
    return out.key ? out : null;
  }

  /** "Ctrl+Shift+F" for the tooltip; with `Control`, aria-keyshortcuts. */
  function describeShortcut(sc, ctrlName) {
    var parts = [];
    if (sc.ctrl) parts.push(ctrlName);
    if (sc.alt) parts.push("Alt");
    if (sc.shift) parts.push("Shift");
    if (sc.meta) parts.push("Meta");
    parts.push(sc.key === " " ? "Space" : sc.key.length === 1 ? sc.key.toUpperCase() : sc.key);
    return parts.join("+");
  }

  // Focus targets where a bare key belongs to the control: typing, a
  // select's type-ahead, keys pressed on a button or link.
  var OWN_KEY_TAGS = { INPUT: 1, TEXTAREA: 1, SELECT: 1, BUTTON: 1, A: 1 };

  function ownsBareKeys(t) {
    if (!t) return false;
    if (OWN_KEY_TAGS[t.tagName || ""] || t.isContentEditable) return true;
    return !!(t.closest && t.closest('[contenteditable]:not([contenteditable="false"])'));
  }

  function matchesShortcut(sc, e) {
    if (!e.key || e.key.toLowerCase() !== sc.key.toLowerCase()) return false;
    if (!!e.ctrlKey !== sc.ctrl || !!e.altKey !== sc.alt || !!e.metaKey !== sc.meta) return false;
    // Shift is part of a letter or named key; for punctuation it is how the
    // character is typed ("?" is Shift+/), so it only counts when declared.
    var punctuation = sc.key.length === 1 && !/[a-z0-9]/i.test(sc.key);
    return sc.shift ? !!e.shiftKey : punctuation || !e.shiftKey;
  }

  /** A bare key never fires while focus owns it; a combination works anywhere. */
  function bindShortcut(sc, fn) {
    if (!sc) return;
    var bare = !(sc.ctrl || sc.alt || sc.meta);
    document.addEventListener("keydown", function (e) {
      if (!matchesShortcut(sc, e) || (bare && ownsBareKeys(target(e)))) return;
      e.preventDefault();
      fn();
    });
  }

  /* Widget */

  function FeedbackWidget() {
    var self = this;
    this._errors = [];
    this._htmx = [];
    this._inflight = {};
    this._mem = {};
    this._pins = [];
    this._reports = [];
    this._shortcut = parseShortcut(metaRaw("dz-feedback-shortcut"), "backtick");
    this._categories = metaList("dz-feedback-categories", DEFAULT_CATEGORIES);
    this._severities = metaList("dz-feedback-severities", DEFAULT_SEVERITIES);
    // The first declared severity is the default; the framework list keeps `minor`.
    this._defaultSeverity = this._severities.join(",") === DEFAULT_SEVERITIES ? "minor" : this._severities[0];
    this._category = null;
    this._severity = this._defaultSeverity;
    this._review = meta("dz-feedback-review") === "1";
    this._reviewShortcut = this._review ? parseShortcut(metaRaw("dz-feedback-review-shortcut"), "alt+shift+r") : null;
    this._armed = false;
    this._capture();
    this._build();
    bindShortcut(this._shortcut, function () {
      self.isOpen() ? self.close() : self.open();
    });
    bindShortcut(this._reviewShortcut, function () {
      self._armed ? self.disarm() : self.arm();
    });
    document.addEventListener("htmx:after:swap", function () {
      // A boosted navigation swaps the body and drops the host; put it back.
      if (!document.body.contains(self._host)) document.body.appendChild(self._host);
    });
    document.addEventListener("htmx:after:settle", function () {
      if (self._review) self._loadPins();
    });
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") self._retryPending();
    });
    this._retryPending();
    this._checkResolved();
    if (this._review) this._bindReview();
  }

  var P = FeedbackWidget.prototype;

  P._pushError = function (msg) {
    this._errors.push(String(msg).slice(0, 500));
    if (this._errors.length > 20) this._errors.shift();
  };

  /** Context capture: errors, htmx 4 request history (no bodies), navigation. */
  P._capture = function () {
    var self = this;
    window.addEventListener("error", function (e) {
      self._pushError(e.message + " at " + (e.filename || "") + ":" + (e.lineno || ""));
    });
    window.addEventListener("unhandledrejection", function (e) {
      self._pushError("Unhandled rejection: " + String(e.reason));
    });
    var orig = console.error;
    console.error = function () {
      var parts = [];
      for (var i = 0; i < arguments.length; i++) {
        var a = arguments[i];
        parts.push(a && a.message ? a.message : typeof a === "object" ? safeJson(a) : String(a));
      }
      self._pushError("console.error: " + parts.join(" "));
      return orig.apply(console, arguments);
    };
    document.addEventListener("htmx:before:request", function (e) {
      var ctx = e.detail && e.detail.ctx;
      if (ctx) ctx._dzFeedbackT0 = Date.now();
    });
    var record = function (e) {
      var ctx = e.detail && e.detail.ctx;
      if (!ctx || ctx._dzFeedbackLogged) return;
      ctx._dzFeedbackLogged = true;
      var req = ctx.request || {}, path = req.action || req.url || "";
      try {
        path = new URL(path, location.href).pathname;
      } catch (_) {
        /* keep raw */
      }
      var status = ctx.response ? ctx.response.status : null;
      self._htmx.push({
        method: (req.method || "GET").toUpperCase(),
        path: path,
        status: status,
        ms: ctx._dzFeedbackT0 ? Date.now() - ctx._dzFeedbackT0 : null,
      });
      if (self._htmx.length > 10) self._htmx.shift();
      if (status >= 400) self._pushError("htmx " + status + " " + path);
    };
    document.addEventListener("htmx:after:request", record);
    document.addEventListener("htmx:response:error", record);
    var nav = parseJson(store("sessionStorage", NAV_KEY), []);
    nav.push(location.href);
    store("sessionStorage", NAV_KEY, JSON.stringify(nav.slice(-5)));
  };

  /** One review walk per tab: `YYYY-MM-DD-xxxx` in sessionStorage. */
  P._session = function () {
    var s = store("sessionStorage", SESSION_KEY);
    if (!s) {
      s = new Date().toISOString().slice(0, 10) + "-" + uuid().slice(0, 4);
      store("sessionStorage", SESSION_KEY, s);
    }
    return s;
  };

  P._snapshot = function () {
    try {
      var clone = document.body.cloneNode(true);
      clone.querySelectorAll("dz-feedback,script,style,link[rel=stylesheet]").forEach(function (el) {
        el.remove();
      });
      var walker = document.createTreeWalker(clone, NodeFilter.SHOW_TEXT), nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      nodes.forEach(function (n) {
        n.textContent = "";
      });
      return clone.outerHTML.substring(0, 10240);
    } catch (_) {
      return "";
    }
  };

  P._context = function () {
    var scheme = "";
    try {
      scheme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    } catch (_) {
      /* noop */
    }
    return {
      url: location.href,
      referrer: document.referrer || "",
      surface: bodyData("surface"),
      entity: bodyData("entity"),
      record: bodyData("record"),
      workspace: bodyData("workspace"),
      persona: bodyData("persona") || meta("dz-user-role"),
      viewport: [window.innerWidth, window.innerHeight],
      dpr: window.devicePixelRatio || 1,
      ua: navigator.userAgent,
      lang: navigator.language || "",
      color_scheme: scheme,
      review_session: this._session(),
      htmx_history: this._htmx.slice(),
      console_errors: this._errors.slice(),
    };
  };

  /** A dialog in the shadow root: inert while closed, Escape closes, Tab wraps. */
  P._dialog = function (cls, titleId, onEscape, onEnter) {
    var self = this;
    var d = set(mk("div", cls), { role: "dialog", "aria-modal": "true", "aria-labelledby": titleId });
    setHidden(d, true);
    d.addEventListener("keydown", function (e) {
      if (e.key === "Escape" || e.key === "Esc") {
        e.preventDefault();
        onEscape();
      } else if (e.key === "Tab") self._trapTab(e, d);
      else if (onEnter && e.key === "Enter" && !e.shiftKey) onEnter(e);
    });
    return d;
  };

  P._build = function () {
    var self = this;
    // A valid custom-element name takes a shadow root without a definition.
    this._host = document.createElement("dz-feedback");
    this._root = this._host.attachShadow({ mode: "open" });
    this._root.appendChild(mk("style", null, STYLES));

    this._btn = btn("dz-feedback-btn", null, function () {
      self.open();
    });
    var hint = this._shortcut ? " (" + describeShortcut(this._shortcut, "Ctrl") + ")" : "";
    set(this._btn, { "aria-label": "Send feedback", title: "Send feedback" + hint });
    if (this._shortcut) this._btn.setAttribute("aria-keyshortcuts", describeShortcut(this._shortcut, "Control"));
    this._btn.appendChild(chatIcon());
    this._root.appendChild(this._btn);

    this._backdrop = mk("div", "dz-feedback-backdrop");
    this._backdrop.addEventListener("click", function () {
      self.close();
    });
    this._root.appendChild(this._backdrop);

    var panel = (this._panel = this._dialog("dz-feedback-panel", "dz-feedback-title", function () {
      self.close();
    }));
    var header = mk("div", "dz-feedback-header"), h3 = mk("h3", null, "Send Feedback");
    h3.id = "dz-feedback-title";
    header.appendChild(h3);
    header.appendChild(set(btn("dz-feedback-close", "\u00d7", function () {
      self.close();
    }), { "aria-label": "Close feedback panel" }));
    panel.appendChild(header);

    var body = mk("div", "dz-feedback-body");
    if (this._review) {
      var point = btn("dz-feedback-ghost", "Point at it", function () {
        self.close();
        self.arm();
      });
      if (this._reviewShortcut) {
        set(point, {
          title: "Point at it (" + describeShortcut(this._reviewShortcut, "Ctrl") + ")",
          "aria-keyshortcuts": describeShortcut(this._reviewShortcut, "Control"),
        });
      }
      body.appendChild(point);
    }
    var catLabel = mk("div", "dz-feedback-label", "Category");
    catLabel.id = "dz-feedback-category-label";
    body.appendChild(catLabel);
    var grid = set(mk("div", "dz-feedback-categories"), { role: "group", "aria-labelledby": catLabel.id });
    this._categories.forEach(function (cat) {
      var b = btn("dz-feedback-cat-btn", sentence(cat), function () {
        self._category = cat;
        grid.querySelectorAll(".dz-feedback-cat-btn").forEach(function (x) {
          setPressed(x, x.getAttribute("data-category") === cat);
        });
      });
      grid.appendChild(set(b, { "data-category": cat, "aria-pressed": "false" }));
    });
    body.appendChild(grid);
    var sevLabel = mk("div", "dz-feedback-label", "Severity (optional)");
    sevLabel.id = "dz-feedback-severity-label";
    body.appendChild(sevLabel);
    this._sevRow = this._severityRow(sevLabel.id, function (sev) {
      self._severity = sev;
    });
    body.appendChild(this._sevRow);
    body.appendChild(set(mk("label", "dz-feedback-label", "Describe what you observed"), { "for": "dz-feedback-description" }));
    this._textarea = set(mk("textarea", "dz-feedback-description"), { placeholder: "What happened?" });
    this._textarea.id = "dz-feedback-description";
    body.appendChild(this._textarea);
    this._submitBtn = btn("dz-feedback-submit", "Submit Feedback", function () {
      self._submit();
    });
    body.appendChild(this._submitBtn);
    panel.appendChild(body);
    this._root.appendChild(panel);

    this._toast = set(mk("div", "dz-feedback-toast"), { role: "status", "aria-live": "polite" });
    this._root.appendChild(this._toast);

    if (this._review) this._buildReview();
    document.body.appendChild(this._host);
  };

  /** A labelled group of severity pills with the default pre-selected. */
  P._severityRow = function (labelId, onPick) {
    var self = this;
    var row = set(mk("div", "dz-feedback-severities"), { role: "group", "aria-labelledby": labelId });
    this._severities.forEach(function (sev) {
      var b = btn("dz-feedback-sev-btn", sentence(sev), function () {
        onPick(sev);
        self._markSeverity(row, sev);
      });
      b.setAttribute("data-severity", sev);
      setPressed(b, sev === self._defaultSeverity);
      row.appendChild(b);
    });
    return row;
  };

  P._markSeverity = function (row, sev) {
    row.querySelectorAll(".dz-feedback-sev-btn").forEach(function (b) {
      setPressed(b, b.getAttribute("data-severity") === sev);
    });
  };

  /** The focused element, seen through the shadow boundary. */
  P._active = function () {
    return this._root.activeElement || document.activeElement;
  };

  P._trapTab = function (e, dialog) {
    var controls = [], all = dialog.querySelectorAll("button, textarea, select, input");
    for (var i = 0; i < all.length; i++) if (!all[i].disabled) controls.push(all[i]);
    if (!controls.length) return;
    var first = controls[0], last = controls[controls.length - 1], active = this._active();
    if (e.shiftKey && active === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
  };

  P.isOpen = function () {
    return this._panel.classList.contains("open");
  };

  P.open = function () {
    if (this.isOpen()) return;
    this._idempotencyKey = uuid();
    var active = this._active();
    this._opener = active && active !== document.body ? active : this._btn;
    setHidden(this._panel, false);
    this._panel.classList.add("open");
    this._backdrop.classList.add("visible");
    this._panel.querySelector(".dz-feedback-cat-btn").focus();
  };

  P.close = function () {
    if (!this.isOpen()) return;
    this._panel.classList.remove("open");
    this._backdrop.classList.remove("visible");
    setHidden(this._panel, true);
    this._restoreFocus(this._opener);
    this._opener = null;
  };

  /** Focus `el` if it is still on the page and takes focus, else the button. */
  P._restoreFocus = function (el) {
    if (el && (document.body.contains(el) || this._root.contains(el)) && el.focus) el.focus();
    if (this._active() !== el) this._btn.focus();
  };

  P._showToast = function (msg) {
    var toast = this._toast;
    toast.textContent = msg;
    toast.classList.add("visible");
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(function () {
      toast.classList.remove("visible");
    }, 3000);
  };

  P._submit = function () {
    var description = (this._textarea.value || "").trim();
    if (!this._category) return this._showToast("Please select a category.");
    if (!description) return this._showToast("Please describe the issue.");
    this._submitBtn.disabled = true;
    var self = this;
    var payload = this._report({ category: this._category, severity: this._severity, description: description, anchor: null }, this._idempotencyKey);
    this._enqueue(payload);
    this._send(payload.idempotency_key, function (kind, status) {
      if (kind === "failed") {
        self._submitBtn.disabled = false;
        return self._showToast("Could not send feedback (HTTP " + status + ").");
      }
      self._showToast(kind === "sent" ? "Feedback submitted \u2014 thank you!" : "Saved offline \u2014 will retry on next page load.");
      self.close();
      self._category = null;
      self._severity = self._defaultSeverity;
      self._textarea.value = "";
      self._submitBtn.disabled = false;
      self._panel.querySelectorAll(".dz-feedback-cat-btn").forEach(function (b) {
        setPressed(b, false);
      });
      self._markSeverity(self._sevRow, self._defaultSeverity);
    });
  };

  /** The FeedbackReport row for a report or note, trimmed to the caps
   *  (the snapshot first, then the logs). */
  P._report = function (fields, key) {
    var ctx = this._context();
    var payload = {
      idempotency_key: key,
      reported_by: meta("dz-user-email"),
      persona: meta("dz-user-role"),
      category: fields.category,
      severity: fields.severity,
      description: fields.description.slice(0, 4000),
      page_url: pageKey(),
      page_title: document.title,
      surface: ctx.surface,
      review_session: ctx.review_session,
      viewport: ctx.viewport[0] + "x" + ctx.viewport[1],
      user_agent: ctx.ua,
      console_errors: ctx.console_errors.join("\n"),
      nav_history: store("sessionStorage", NAV_KEY) || "[]",
      page_snapshot: this._snapshot(),
      anchor: fields.anchor,
      context: ctx,
    };
    // The server caps anchor + context + page_snapshot + console_errors at
    // 32 KB serialised and the whole body is kept under 60 KB.
    var size = function () {
      return JSON.stringify([payload.anchor, payload.context, payload.page_snapshot, payload.console_errors]).length;
    };
    while (size() > MAX_FIELDS && payload.page_snapshot) {
      var half = Math.floor(payload.page_snapshot.length / 2);
      payload.page_snapshot = half < 256 ? "" : payload.page_snapshot.slice(0, half);
    }
    if (size() > MAX_FIELDS) {
      ctx.console_errors = ctx.console_errors.slice(-3);
      payload.console_errors = ctx.console_errors.join("\n");
      ctx.htmx_history = ctx.htmx_history.slice(-3);
    }
    if (JSON.stringify(payload).length > MAX_JSON) payload.nav_history = "[]";
    if (fields.screenshot_data) payload.screenshot_data = fields.screenshot_data;
    return payload;
  };

  /* Submission queue: localStorage, keyed by the idempotency key. The
     screenshot stays in memory; the rest is persisted for retries. */

  P._queue = function () {
    var q = parseJson(store("localStorage", PENDING_KEY), {});
    return q && !Array.isArray(q) ? q : {};
  };

  P._saveQueue = function (q) {
    store("localStorage", PENDING_KEY, Object.keys(q).length ? JSON.stringify(q) : null);
  };

  P._enqueue = function (payload) {
    var q = this._queue(), slim = {};
    for (var k in payload) if (k !== "screenshot_data") slim[k] = payload[k];
    q[payload.idempotency_key] = { payload: slim, ts: Date.now() };
    this._saveQueue(q);
    this._mem[payload.idempotency_key] = { payload: payload };
  };

  /** POST one queued report. `done(kind, status)`: "sent" (2xx, incl. a 200
   *  replay), "queued" (409 in flight, 429, 5xx or network: kept for later)
   *  or "failed" (any other 4xx: dropped). */
  P._send = function (key, done) {
    var item = this._mem[key] || this._queue()[key];
    if (!item || this._inflight[key]) return;
    this._inflight[key] = true;
    var self = this;
    var finish = function (kind, status) {
      delete self._inflight[key];
      if (kind !== "queued") {
        var q = self._queue();
        delete q[key];
        self._saveQueue(q);
        delete self._mem[key];
      }
      if (done) done(kind, status);
    };
    fetch(ENDPOINT, {
      method: "POST",
      headers: headers({ "Idempotency-Key": key }),
      credentials: "same-origin",
      body: JSON.stringify(item.payload),
    }).then(function (r) {
      finish(r.ok ? "sent" : r.status === 409 || r.status === 429 || r.status >= 500 ? "queued" : "failed", r.status);
    }, function () {
      finish("queued", 0);
    });
  };

  P._retryPending = function () {
    var q = this._queue(), now = Date.now();
    for (var key in q) if (now - (q[key].ts || 0) > MAX_AGE) delete q[key];
    this._saveQueue(q);
    for (var k in q) this._send(k);
  };

  /** One toast per newly resolved report (#721, #869). */
  P._checkResolved = function () {
    var self = this;
    this._get("?reported_by=" + encodeURIComponent(meta("dz-user-email")) + "&status=resolved&notification_sent=false", function (items) {
      items.forEach(function (report) {
        self._showToast('Your feedback "' + (report.description || "").substring(0, 60) + '" has been resolved.');
        self._put(report.id, { notification_sent: true });
      });
    });
  };

  P._get = function (query, onItems) {
    fetch(ENDPOINT + query, { credentials: "same-origin" })
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (data) {
        var items = data && (data.items || data);
        if (Array.isArray(items)) onItems(items);
      })
      .catch(function () {
        /* best effort */
      });
  };

  P._put = function (id, body) {
    return fetch(ENDPOINT + "/" + encodeURIComponent(id), {
      method: "PUT", headers: headers({}), credentials: "same-origin", body: JSON.stringify(body),
    });
  };

  /* Review posture: arm, outline, note card, pins */

  P._buildReview = function () {
    var self = this;
    this._outline = set(mk("div", "dz-feedback-outline"), { "aria-hidden": "true" });
    this._outline.appendChild(mk("span"));
    this._root.appendChild(this._outline);

    var card = (this._card = this._dialog("dz-feedback-card", "dz-feedback-card-title", function () {
      self._closeCard(true);
    }, function (e) {
      if (target(e) === self._noteText || e.ctrlKey || e.metaKey) {
        e.preventDefault();
        self._saveNote();
      }
    }));
    var title = mk("div", "dz-feedback-label", "Review note");
    title.id = "dz-feedback-card-title";
    card.appendChild(title);
    this._cardPath = mk("div", "dz-feedback-path");
    card.appendChild(this._cardPath);
    card.appendChild(set(mk("label", "dz-feedback-label", "Note"), { "for": "dz-feedback-note-text" }));
    this._noteText = set(mk("textarea", "dz-feedback-description"), { placeholder: "What is wrong or notable here?" });
    this._noteText.id = "dz-feedback-note-text";
    card.appendChild(this._noteText);
    var sevLabel = mk("div", "dz-feedback-label", "Severity");
    sevLabel.id = "dz-feedback-card-severity-label";
    card.appendChild(sevLabel);
    this._noteSevRow = this._severityRow(sevLabel.id, function (sev) {
      self._noteSeverity = sev;
    });
    card.appendChild(this._noteSevRow);
    card.appendChild(set(mk("label", "dz-feedback-label", "Category"), { "for": "dz-feedback-note-category" }));
    this._noteCategory = mk("select", "dz-feedback-select");
    this._noteCategory.id = "dz-feedback-note-category";
    this._categories.forEach(function (cat) {
      var o = mk("option", null, sentence(cat));
      o.value = cat;
      self._noteCategory.appendChild(o);
    });
    card.appendChild(this._noteCategory);
    if (this._screenshotAllowed()) {
      var shotRow = mk("label", "dz-feedback-row dz-feedback-hint");
      this._shotCheck = mk("input", "dz-feedback-shot-check");
      this._shotCheck.type = "checkbox";
      shotRow.appendChild(this._shotCheck);
      shotRow.appendChild(document.createTextNode(" Attach screenshot"));
      card.appendChild(shotRow);
    }
    var row = mk("div", "dz-feedback-row");
    row.appendChild(btn("dz-feedback-submit dz-feedback-save", "Save note", function () {
      self._saveNote();
    }));
    row.appendChild(btn("dz-feedback-ghost dz-feedback-cancel", "Cancel", function () {
      self._closeCard(true);
    }));
    row.appendChild(mk("span", "dz-feedback-hint", "Enter saves \u00b7 Shift+Enter newline \u00b7 Esc cancels"));
    card.appendChild(row);
    this._root.appendChild(card);

    var note = (this._note = this._dialog("dz-feedback-note", "dz-feedback-note-title", function () {
      self._closeNote();
    }));
    this._noteTitle = mk("div", "dz-feedback-label");
    this._noteTitle.id = "dz-feedback-note-title";
    this._noteBody = mk("p");
    this._noteMeta = mk("div", "dz-feedback-path");
    note.appendChild(this._noteTitle);
    note.appendChild(this._noteBody);
    note.appendChild(this._noteMeta);
    var noteRow = mk("div", "dz-feedback-row");
    noteRow.appendChild(btn("dz-feedback-submit dz-feedback-resolve", "Resolve", function () {
      self._resolveNote();
    }));
    noteRow.appendChild(btn("dz-feedback-ghost", "Close", function () {
      self._closeNote();
    }));
    note.appendChild(noteRow);
    this._root.appendChild(note);
  };

  P._isOwn = function (el) {
    return !!el && (el === this._host || this._host.contains(el));
  };

  /** Capture-phase listeners: the page (and htmx) never sees an armed click. */
  P._bindReview = function () {
    var self = this;
    document.addEventListener("pointermove", function (e) {
      if (!self._armed) return;
      var el = document.elementFromPoint(e.clientX, e.clientY);
      if (!el || self._isOwn(el)) self._outline.classList.remove("visible");
      else self._outlineAt(el);
    }, { capture: true, passive: true });
    document.addEventListener("click", function (e) {
      if (!self._armed) return;
      var el = document.elementFromPoint(e.clientX, e.clientY) || e.target;
      if (self._isOwn(el)) return;
      e.preventDefault();
      e.stopPropagation();
      if (e.stopImmediatePropagation) e.stopImmediatePropagation();
      self._openCard(el);
    }, true);
    document.addEventListener("keydown", function (e) {
      if (!self._armed) return;
      var t = target(e);
      if (e.key === "Escape" || e.key === "Esc") {
        e.preventDefault();
        self.disarm();
      } else if ((e.key === "Enter" || e.key === " ") && t && t !== document.body && !self._isOwn(t)) {
        // Keyboard pick: the focused element is the anchor.
        e.preventDefault();
        e.stopPropagation();
        self._openCard(t);
      }
    }, true);
    var reposition = function () {
      if (self._pins.length && !self._raf) {
        self._raf = requestAnimationFrame(function () {
          self._raf = 0;
          self._positionPins();
        });
      }
    };
    window.addEventListener("scroll", reposition, { capture: true, passive: true });
    window.addEventListener("resize", reposition);
    this._loadPins();
  };

  P.arm = function () {
    if (this._armed) return;
    this._armed = true;
    this._host.setAttribute("data-armed", "");
    this._prevCursor = document.body.style.cursor;
    document.body.style.cursor = "crosshair";
    this._showToast("Review: click the element to note (or focus it and press Enter). Esc cancels.");
  };

  P.disarm = function () {
    if (!this._armed) return;
    this._armed = false;
    this._host.removeAttribute("data-armed");
    document.body.style.cursor = this._prevCursor || "";
    this._outline.classList.remove("visible");
  };

  P._outlineAt = function (el) {
    var r = el.getBoundingClientRect(), s = this._outline.style;
    s.left = r.left + "px";
    s.top = r.top + "px";
    s.width = r.width + "px";
    s.height = r.height + "px";
    this._outline.firstElementChild.textContent = dzAnchor(el) || el.tagName.toLowerCase();
    this._outline.classList.add("visible");
  };

  P._openCard = function (el) {
    this.disarm();
    this._anchorEl = el;
    this._anchor = anchorRecord(el);
    this._noteKey = uuid();
    this._cardPath.textContent = this._anchor.dz_anchor || this._anchor.css || this._anchor.tag;
    this._noteText.value = "";
    this._noteSeverity = this._defaultSeverity;
    this._markSeverity(this._noteSevRow, this._defaultSeverity);
    this._noteCategory.value = this._categories.indexOf("ux") >= 0 ? "ux" : this._categories[0];
    if (this._shotCheck) this._shotCheck.checked = false;
    this._outlineAt(el);
    setHidden(this._card, false);
    this._card.classList.add("open");
    placeBeside(this._card, el.getBoundingClientRect(), 320, 360);
    this._noteText.focus();
  };

  P._closeCard = function (restore) {
    this._card.classList.remove("open");
    setHidden(this._card, true);
    this._outline.classList.remove("visible");
    var el = this._anchorEl;
    this._anchorEl = null;
    if (restore) this._restoreFocus(el);
  };

  P._saveNote = function () {
    var text = (this._noteText.value || "").trim();
    if (!text) return this._showToast("Please write the note first.");
    var self = this;
    var fields = { category: this._noteCategory.value, severity: this._noteSeverity, description: text, anchor: this._anchor };
    var key = this._noteKey, el = this._anchorEl;
    var finish = function (shot) {
      if (shot) fields.screenshot_data = shot;
      var payload = self._report(fields, key);
      self._enqueue(payload);
      self._closeCard(false);
      self._restoreFocus(el);
      self._send(key, function (kind, status) {
        self._showToast(kind === "failed" ? "Could not save the note (HTTP " + status + ")." : kind === "sent" ? "Note saved." : "Note saved offline \u2014 will retry.");
        if (kind === "sent") self._loadPins();
      });
    };
    if (this._shotCheck && this._shotCheck.checked) {
      this._card.classList.remove("open");
      this._outline.classList.remove("visible");
      this._screenshot().then(finish, function () {
        finish(null);
      });
    } else finish(null);
  };

  P._loadPins = function () {
    var self = this;
    this._get("?page_url=" + encodeURIComponent(pageKey()) + "&status=new,triaged", function (items) {
      items.sort(function (a, b) {
        return String(a.created_at || "").localeCompare(String(b.created_at || ""));
      });
      self._reports = items;
      self._renderPins();
    });
  };

  /** dz_anchor → css → text quote; null means orphaned (drawn at rect). */
  P._resolve = function (a) {
    if (!a) return null;
    var el = resolveDzAnchor(a.dz_anchor);
    if (!el && a.css) {
      try {
        el = document.querySelector(a.css);
      } catch (_) {
        el = null;
      }
    }
    if (!el && a.text_quote && a.text_quote.exact) {
      var all = document.body.querySelectorAll(a.tag || "*");
      for (var i = 0; i < all.length && i < 5000 && !el; i++) {
        if (collapse(all[i].textContent).slice(0, 64) === a.text_quote.exact) el = all[i];
      }
    }
    return el && !this._isOwn(el) ? el : null;
  };

  P._renderPins = function () {
    var self = this;
    this._pins.forEach(function (p) {
      p.el.remove();
    });
    this._pins = [];
    this._reports.forEach(function (report, i) {
      var anchor = parseJson(report.anchor, null), el = self._resolve(anchor);
      var pin = btn("dz-feedback-pin", String(i + 1), function () {
        self._openNote(report, pin, !el);
      });
      set(pin, {
        "data-report-id": report.id,
        "data-status": report.status || "new",
        "aria-label": "Review note " + (i + 1) + (el ? "" : " (element not found)") + ": " + (report.description || "").slice(0, 60),
      });
      if (!el) pin.setAttribute("data-orphaned", "");
      self._root.appendChild(pin);
      self._pins.push({ el: pin, target: el, anchor: anchor, report: report });
    });
    this._positionPins();
  };

  P._positionPins = function () {
    this._pins.forEach(function (p) {
      var x = window.innerWidth - 40, y = 80;
      if (p.target) {
        var r = p.target.getBoundingClientRect();
        x = r.left + r.width;
        y = r.top;
      } else if (p.anchor && p.anchor.rect) {
        var a = p.anchor, sc = a.scroll || { x: 0, y: 0 };
        x = a.rect.x + a.rect.w + sc.x - (window.scrollX || 0);
        y = a.rect.y + sc.y - (window.scrollY || 0);
      }
      p.el.style.left = Math.round(x - 11) + "px";
      p.el.style.top = Math.round(y - 11) + "px";
    });
  };

  P._openNote = function (report, pin, orphaned) {
    this._noteReport = report;
    this._notePin = pin;
    var a = parseJson(report.anchor, null) || {};
    this._noteTitle.textContent = "Review note " + pin.textContent + (orphaned ? " \u2014 element not found" : "");
    this._noteBody.textContent = report.description || "";
    var parts = [sentence(report.severity || ""), sentence(report.category || ""), report.reported_by || "",
      (report.created_at || "").slice(0, 16).replace("T", " "),
      orphaned && a.text_quote && a.text_quote.exact ? "was: \u201c" + a.text_quote.exact + "\u201d" : a.dz_anchor || ""];
    this._noteMeta.textContent = parts.filter(Boolean).join(" \u00b7 ");
    setHidden(this._note, false);
    this._note.classList.add("open");
    placeBeside(this._note, pin.getBoundingClientRect(), 320, 200);
    this._note.querySelector("button").focus();
  };

  P._closeNote = function () {
    this._note.classList.remove("open");
    setHidden(this._note, true);
    this._restoreFocus(this._notePin);
    this._noteReport = null;
  };

  /** new → triaged → resolved: the entity's transitions, one PUT each. */
  P._resolveNote = function () {
    var report = this._noteReport, self = this;
    if (!report) return;
    var ok = function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
    };
    (report.status === "new" ? this._put(report.id, { status: "triaged" }).then(ok) : Promise.resolve())
      .then(function () {
        return self._put(report.id, { status: "resolved" }).then(ok);
      })
      .then(function () {
        self._reports = self._reports.filter(function (x) {
          return x.id !== report.id;
        });
        self._closeNote();
        self._renderPins();
        self._showToast("Note resolved.");
      })
      .catch(function () {
        self._showToast("Could not resolve the note.");
      });
  };

  /* Screenshot: policy `optional`, feature-detected, never on mobile. */

  P._screenshotAllowed = function () {
    var md = navigator.mediaDevices;
    return meta("dz-feedback-screenshot") === "optional" && !!md && typeof md.getDisplayMedia === "function" &&
      !!window.HTMLCanvasElement && !/Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
  };

  /** webp q0.8, scaled down until under 1.5 MB; null if it never fits. */
  function encodeShot(canvas) {
    for (var i = 0; i < 5; i++) {
      var url = canvas.toDataURL("image/webp", 0.8);
      if ((url.length - url.indexOf(",") - 1) * 0.75 <= MAX_SHOT) return url;
      var smaller = document.createElement("canvas");
      smaller.width = Math.round(canvas.width * 0.7);
      smaller.height = Math.round(canvas.height * 0.7);
      smaller.getContext("2d").drawImage(canvas, 0, 0, smaller.width, smaller.height);
      canvas = smaller;
    }
    return null;
  }

  /** One frame of this tab via getDisplayMedia (two frames after play so the
   *  hidden widget is gone), then the redaction pass. */
  P._screenshot = function () {
    var self = this, host = this._host, stream;
    var done = function (v) {
      if (stream) stream.getTracks().forEach(function (t) {
        t.stop();
      });
      host.style.visibility = "";
      return v;
    };
    host.style.visibility = "hidden";
    return navigator.mediaDevices
      .getDisplayMedia({ video: { displaySurface: "browser" }, audio: false, preferCurrentTab: true, selfBrowserSurface: "include", surfaceSwitching: "exclude" })
      .then(function (s) {
        stream = s;
        var video = document.createElement("video");
        video.muted = true;
        video.srcObject = s;
        return video.play().then(function () {
          return new Promise(function (resolve) {
            requestAnimationFrame(function () {
              requestAnimationFrame(resolve);
            });
          });
        }).then(function () {
          var canvas = document.createElement("canvas");
          canvas.width = video.videoWidth;
          canvas.height = video.videoHeight;
          canvas.getContext("2d").drawImage(video, 0, 0);
          return self._redact(canvas);
        });
      })
      .then(function (canvas) {
        return done(canvas ? encodeShot(canvas) : null);
      }, function () {
        return done(null);
      });
  };

  /** Drag to black out rectangles; resolves the canvas, or null on discard. */
  P._redact = function (canvas) {
    var self = this;
    return new Promise(function (resolve) {
      var shot = set(mk("div", "dz-feedback-shot"), { role: "dialog", "aria-label": "Redact the screenshot: drag to hide an area" });
      var ctx = canvas.getContext("2d"), drag = null;
      var pos = function (e) {
        var r = canvas.getBoundingClientRect();
        return [((e.clientX - r.left) / r.width) * canvas.width, ((e.clientY - r.top) / r.height) * canvas.height];
      };
      canvas.addEventListener("pointerdown", function (e) {
        drag = pos(e);
        if (canvas.setPointerCapture) canvas.setPointerCapture(e.pointerId);
      });
      canvas.addEventListener("pointerup", function (e) {
        if (!drag) return;
        var p = pos(e);
        ctx.fillStyle = "#000";
        ctx.fillRect(Math.min(drag[0], p[0]), Math.min(drag[1], p[1]), Math.abs(p[0] - drag[0]), Math.abs(p[1] - drag[1]));
        drag = null;
      });
      shot.appendChild(canvas);
      var finish = function (keep) {
        shot.remove();
        resolve(keep ? canvas : null);
      };
      var row = mk("div", "dz-feedback-row");
      row.appendChild(mk("span", "dz-feedback-hint", "Drag over anything to hide it, then attach."));
      row.appendChild(btn("dz-feedback-submit", "Attach", function () {
        finish(true);
      }));
      row.appendChild(btn("dz-feedback-ghost", "Discard", function () {
        finish(false);
      }));
      shot.appendChild(row);
      shot.addEventListener("keydown", function (e) {
        if (e.key === "Escape" || e.key === "Esc") finish(false);
      });
      self._root.appendChild(shot);
      row.querySelector("button").focus();
    });
  };

  /** Mount once, only for a signed-in user (public pages get no widget). */
  function mount() {
    if (window.feedbackWidget || !meta("dz-user-email")) return;
    window.feedbackWidget = new FeedbackWidget();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
