/**
 * Dazzle Feedback Widget — in-app feedback collection.
 *
 * All DOM construction uses document.createElement() — no innerHTML with user
 * content. User-supplied text uses textContent exclusively.
 *
 * Security: description and auto-captured context are submitted as JSON via
 * fetch() and rendered server-side by Dazzle's auto-escaping templates.
 *
 * Mounted by the app chrome when the DSL declares `feedback_widget: enabled`.
 * The signed-in identity comes from `<meta name="dz-user-email">` /
 * `<meta name="dz-user-role">`, emitted alongside the script on signed-in
 * pages; without it the widget does not mount. Mounting is
 * idempotent (a second load of the script is a no-op) and the widget's nodes
 * are re-attached after an htmx swap replaces the body. Nothing is shown on
 * load except a one-shot toast per newly resolved report (#869).
 */
(function () {
  "use strict";

  if (window.feedbackWidget) return;

  var MAX_REPORTS_PER_HOUR = 10;
  var RATE_LIMIT_KEY = "dz_feedback_rate";
  var PENDING_KEY = "dz_feedback_pending";
  var NAV_HISTORY_KEY = "dz_feedback_nav";
  var PENDING_MAX_AGE_MS = 24 * 60 * 60 * 1000;
  var SVG_NS = "http://www.w3.org/2000/svg";

  /** Create an SVG chat-bubble icon using safe DOM methods. */
  function createChatIcon() {
    var svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    var path = document.createElementNS(SVG_NS, "path");
    path.setAttribute(
      "d",
      "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
    );
    svg.appendChild(path);
    return svg;
  }

  /** Content of `<meta name="...">`, or "". */
  function metaContent(name) {
    var el = document.querySelector('meta[name="' + name + '"]');
    return el ? (el.getAttribute("content") || "").trim() : "";
  }

  function userEmail() {
    return metaContent("dz-user-email");
  }

  function FeedbackWidget() {
    this._errors = [];
    this._opener = null;
    this._category = null;
    this._severity = "minor";
    this._idempotencyKey = null;
    this._initErrorCapture();
    this._trackNavigation();
    this._buildUI();
    this._bindShortcut();
    this._bindSwapReattach();
    this._retryPending();
    this._checkResolved();
  }

  /* ------------------------------------------------------------------ */
  /* Error capture                                                       */
  /* ------------------------------------------------------------------ */

  FeedbackWidget.prototype._initErrorCapture = function () {
    var self = this;
    window.addEventListener("error", function (e) {
      self._errors.push(
        e.message + " at " + (e.filename || "") + ":" + (e.lineno || ""),
      );
      if (self._errors.length > 20) self._errors.shift();
    });
    window.addEventListener("unhandledrejection", function (e) {
      self._errors.push("Unhandled rejection: " + String(e.reason));
      if (self._errors.length > 20) self._errors.shift();
    });
    document.addEventListener("htmx:response:error", function (e) {
      self._errors.push(
        "htmx:response:error " +
          (e.detail && e.detail.ctx && e.detail.ctx.response ? e.detail.ctx.response.status : ""),
      );
    });
    document.addEventListener("htmx:error", function () {
      self._errors.push("htmx:error");
    });
  };

  /* ------------------------------------------------------------------ */
  /* Navigation tracking                                                 */
  /* ------------------------------------------------------------------ */

  FeedbackWidget.prototype._trackNavigation = function () {
    try {
      var history = JSON.parse(sessionStorage.getItem(NAV_HISTORY_KEY) || "[]");
      history.push(location.href);
      if (history.length > 5) history = history.slice(-5);
      sessionStorage.setItem(NAV_HISTORY_KEY, JSON.stringify(history));
    } catch (_) {
      /* sessionStorage may be unavailable */
    }
  };

  /* ------------------------------------------------------------------ */
  /* Page snapshot                                                        */
  /* ------------------------------------------------------------------ */

  FeedbackWidget.prototype._getPageSnapshot = function () {
    try {
      var clone = document.body.cloneNode(true);
      clone
        .querySelectorAll(
          ".dz-feedback-btn,.dz-feedback-panel,.dz-feedback-backdrop,.dz-feedback-toast,script,style,link[rel=stylesheet]",
        )
        .forEach(function (el) {
          el.remove();
        });
      var walker = document.createTreeWalker(clone, NodeFilter.SHOW_TEXT);
      var textNodes = [];
      while (walker.nextNode()) textNodes.push(walker.currentNode);
      textNodes.forEach(function (n) {
        n.textContent = "";
      });
      var html = clone.outerHTML;
      if (html.length > 10240) html = html.substring(0, 10240);
      return html;
    } catch (_) {
      return "";
    }
  };

  /* ------------------------------------------------------------------ */
  /* Rate limiting                                                        */
  /* ------------------------------------------------------------------ */

  FeedbackWidget.prototype._checkRateLimit = function () {
    try {
      var data = JSON.parse(localStorage.getItem(RATE_LIMIT_KEY) || "{}");
      var now = Date.now();
      if (data.reset && data.reset < now - 3600000) {
        data = { count: 0, reset: now };
      }
      if (!data.reset) data.reset = now;
      if ((data.count || 0) >= MAX_REPORTS_PER_HOUR) return false;
      data.count = (data.count || 0) + 1;
      localStorage.setItem(RATE_LIMIT_KEY, JSON.stringify(data));
      return true;
    } catch (_) {
      return true;
    }
  };

  /* ------------------------------------------------------------------ */
  /* UI construction (safe DOM methods only)                              */
  /* ------------------------------------------------------------------ */

  FeedbackWidget.prototype._buildUI = function () {
    var self = this;

    // Floating button
    this._btn = document.createElement("button");
    this._btn.type = "button";
    this._btn.className = "dz-feedback-btn";
    this._btn.setAttribute("aria-label", "Send feedback");
    this._btn.setAttribute("title", "Send feedback (`)");
    this._btn.appendChild(createChatIcon());
    this._btn.addEventListener("click", function () {
      self.open();
    });
    document.body.appendChild(this._btn);

    // Backdrop
    this._backdrop = document.createElement("div");
    this._backdrop.className = "dz-feedback-backdrop";
    this._backdrop.addEventListener("click", function () {
      self.close();
    });
    document.body.appendChild(this._backdrop);

    // Panel. #1841: while closed it is `inert` + `aria-hidden`, so its
    // controls are out of the tab order and the accessibility tree (it is
    // only translated off-screen, never display:none).
    this._panel = document.createElement("div");
    this._panel.className = "dz-feedback-panel";
    this._panel.setAttribute("role", "dialog");
    this._panel.setAttribute("aria-modal", "true");
    this._panel.setAttribute("aria-labelledby", "dz-feedback-title");
    this._setPanelHidden(true);
    this._panel.addEventListener("keydown", function (e) {
      if (e.key === "Escape" || e.key === "Esc") {
        e.preventDefault();
        self.close();
      } else if (e.key === "Tab") {
        self._trapTab(e);
      }
    });

    // Header
    var header = document.createElement("div");
    header.className = "dz-feedback-header";
    var h3 = document.createElement("h3");
    h3.id = "dz-feedback-title";
    h3.textContent = "Send Feedback";
    var closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "dz-feedback-close";
    closeBtn.setAttribute("aria-label", "Close feedback panel");
    closeBtn.textContent = "\u00d7";
    closeBtn.addEventListener("click", function () {
      self.close();
    });
    header.appendChild(h3);
    header.appendChild(closeBtn);
    this._panel.appendChild(header);

    // Body
    var body = document.createElement("div");
    body.className = "dz-feedback-body";

    // Category (a named group of toggle buttons, #1841)
    var catLabel = document.createElement("div");
    catLabel.className = "dz-feedback-label";
    catLabel.id = "dz-feedback-category-label";
    catLabel.textContent = "Category";
    body.appendChild(catLabel);

    var catGrid = document.createElement("div");
    catGrid.className = "dz-feedback-categories";
    catGrid.setAttribute("role", "group");
    catGrid.setAttribute("aria-labelledby", "dz-feedback-category-label");
    ["bug", "ux", "visual", "behaviour", "enhancement", "other"].forEach(
      function (cat) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "dz-feedback-cat-btn";
        btn.setAttribute("data-category", cat);
        btn.setAttribute("aria-pressed", "false");
        btn.textContent = cat;
        btn.addEventListener("click", function () {
          self._selectCategory(cat, catGrid);
        });
        catGrid.appendChild(btn);
      },
    );
    body.appendChild(catGrid);

    // Severity
    var sevLabel = document.createElement("div");
    sevLabel.className = "dz-feedback-label";
    sevLabel.id = "dz-feedback-severity-label";
    sevLabel.textContent = "Severity (optional)";
    body.appendChild(sevLabel);

    var sevRow = document.createElement("div");
    sevRow.className = "dz-feedback-severities";
    sevRow.setAttribute("role", "group");
    sevRow.setAttribute("aria-labelledby", "dz-feedback-severity-label");
    ["blocker", "annoying", "minor"].forEach(function (sev) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "dz-feedback-sev-btn";
      if (sev === "minor") btn.classList.add("selected");
      btn.setAttribute("aria-pressed", sev === "minor" ? "true" : "false");
      btn.setAttribute("data-severity", sev);
      btn.textContent = sev;
      btn.addEventListener("click", function () {
        self._selectSeverity(sev, sevRow);
      });
      sevRow.appendChild(btn);
    });
    body.appendChild(sevRow);

    // Description (a real <label for>, #1841)
    var descLabel = document.createElement("label");
    descLabel.className = "dz-feedback-label";
    descLabel.setAttribute("for", "dz-feedback-description");
    descLabel.textContent = "Describe what you observed";
    body.appendChild(descLabel);

    this._textarea = document.createElement("textarea");
    this._textarea.id = "dz-feedback-description";
    this._textarea.className = "dz-feedback-description";
    this._textarea.setAttribute("placeholder", "What happened?");
    body.appendChild(this._textarea);

    // Submit
    this._submitBtn = document.createElement("button");
    this._submitBtn.type = "button";
    this._submitBtn.className = "dz-feedback-submit";
    this._submitBtn.textContent = "Submit Feedback";
    this._submitBtn.addEventListener("click", function () {
      self._submit();
    });
    body.appendChild(this._submitBtn);

    this._panel.appendChild(body);
    document.body.appendChild(this._panel);

    // Toast
    this._toast = document.createElement("div");
    this._toast.className = "dz-feedback-toast";
    this._toast.setAttribute("role", "status");
    this._toast.setAttribute("aria-live", "polite");
    document.body.appendChild(this._toast);
  };

  /** Selected state on a toggle: the class for the CSS, `aria-pressed`
   *  for assistive tech (#1841). */
  function setPressed(btn, on) {
    btn.classList.toggle("selected", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  }

  FeedbackWidget.prototype._selectCategory = function (cat, grid) {
    this._category = cat;
    grid.querySelectorAll(".dz-feedback-cat-btn").forEach(function (b) {
      setPressed(b, b.getAttribute("data-category") === cat);
    });
  };

  FeedbackWidget.prototype._selectSeverity = function (sev, row) {
    this._severity = sev;
    row.querySelectorAll(".dz-feedback-sev-btn").forEach(function (b) {
      setPressed(b, b.getAttribute("data-severity") === sev);
    });
  };

  /* ------------------------------------------------------------------ */
  /* Shortcut                                                             */
  /* ------------------------------------------------------------------ */

  FeedbackWidget.prototype._bindShortcut = function () {
    var self = this;
    document.addEventListener("keydown", function (e) {
      if (e.key !== "`") return;
      var tag = (e.target && e.target.tagName) || "";
      if (
        tag === "TEXTAREA" ||
        tag === "INPUT" ||
        (e.target && e.target.isContentEditable)
      )
        return;
      e.preventDefault();
      if (self._panel.classList.contains("open")) {
        self.close();
      } else {
        self.open();
      }
    });
  };

  /* ------------------------------------------------------------------ */
  /* htmx body swaps                                                      */
  /* ------------------------------------------------------------------ */

  /** A boosted navigation swaps the body and drops the appended nodes;
   *  put them back (state lives on the existing nodes, so nothing resets). */
  FeedbackWidget.prototype._bindSwapReattach = function () {
    var self = this;
    var reattach = function () {
      [self._btn, self._backdrop, self._panel, self._toast].forEach(function (el) {
        if (el && !document.body.contains(el)) document.body.appendChild(el);
      });
    };
    document.addEventListener("htmx:after:swap", reattach);
  };

  /* ------------------------------------------------------------------ */
  /* Open / Close                                                         */
  /* ------------------------------------------------------------------ */

  /** Closed: `inert` + `aria-hidden`; open: neither (#1841). */
  FeedbackWidget.prototype._setPanelHidden = function (hidden) {
    if (hidden) {
      this._panel.setAttribute("inert", "");
      this._panel.setAttribute("aria-hidden", "true");
    } else {
      this._panel.removeAttribute("inert");
      this._panel.removeAttribute("aria-hidden");
    }
    this._panel.inert = hidden;
  };

  /** `aria-modal` panel: Tab and Shift+Tab wrap inside it. */
  FeedbackWidget.prototype._trapTab = function (e) {
    var controls = [];
    var all = this._panel.querySelectorAll("button, textarea");
    for (var i = 0; i < all.length; i++) {
      if (!all[i].disabled) controls.push(all[i]);
    }
    if (!controls.length) return;
    var first = controls[0];
    var last = controls[controls.length - 1];
    var active = document.activeElement;
    if (e.shiftKey && active === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
  };

  FeedbackWidget.prototype.isOpen = function () {
    return this._panel.classList.contains("open");
  };

  FeedbackWidget.prototype.open = function () {
    if (this.isOpen()) return;
    this._idempotencyKey = crypto.randomUUID();
    var active = document.activeElement;
    this._opener = active && active !== document.body ? active : this._btn;
    this._setPanelHidden(false);
    this._panel.classList.add("open");
    this._backdrop.classList.add("visible");
    // Focus the first control (the first category toggle).
    var first = this._panel.querySelectorAll(".dz-feedback-cat-btn")[0];
    if (first && typeof first.focus === "function") first.focus();
  };

  FeedbackWidget.prototype.close = function () {
    if (!this.isOpen()) return;
    this._panel.classList.remove("open");
    this._backdrop.classList.remove("visible");
    this._setPanelHidden(true);
    // Return focus to whatever opened the panel, if it is still on the page.
    var opener = this._opener;
    this._opener = null;
    if (!opener || !document.body.contains(opener)) opener = this._btn;
    if (opener && typeof opener.focus === "function") opener.focus();
  };

  /* ------------------------------------------------------------------ */
  /* Submit                                                               */
  /* ------------------------------------------------------------------ */

  FeedbackWidget.prototype._submit = function () {
    var description = (this._textarea.value || "").trim();
    if (!this._category) {
      this._showToast("Please select a category.");
      return;
    }
    if (!description) {
      this._showToast("Please describe the issue.");
      return;
    }

    if (!this._checkRateLimit()) {
      this._showToast("Rate limit reached \u2014 try again later.");
      return;
    }

    this._submitBtn.disabled = true;

    var navHistory = "";
    try {
      navHistory = sessionStorage.getItem(NAV_HISTORY_KEY) || "[]";
    } catch (_) {
      /* noop */
    }

    var payload = {
      reported_by: userEmail(),
      category: this._category,
      severity: this._severity,
      description: description,
      page_url: location.href,
      page_title: document.title,
      persona: metaContent("dz-user-role"),
      viewport: window.innerWidth + "x" + window.innerHeight,
      user_agent: navigator.userAgent,
      console_errors: this._errors.join("\n"),
      nav_history: navHistory,
      page_snapshot: this._getPageSnapshot(),
    };

    this._doPost(payload, this._idempotencyKey);
  };

  FeedbackWidget.prototype._doPost = function (
    payload,
    idempotencyKey,
    silent,
  ) {
    var csrfToken = "";
    var csrfMeta = document.querySelector('meta[name="csrf-token"]');
    if (csrfMeta) csrfToken = csrfMeta.getAttribute("content") || "";

    var headers = {
      "Content-Type": "application/json",
      "X-Idempotency-Key": idempotencyKey,
    };
    if (csrfToken) headers["X-CSRF-Token"] = csrfToken;

    var self = this;
    fetch("/feedbackreports", {
      method: "POST",
      headers: headers,
      credentials: "same-origin",
      body: JSON.stringify(payload),
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        if (!silent) self._onSuccess();
      })
      .catch(function () {
        if (!silent) {
          self._savePending(payload, idempotencyKey);
          self._showToast("Saved offline \u2014 will retry on next page load.");
          self.close();
          self._resetForm();
        }
      });
  };

  FeedbackWidget.prototype._onSuccess = function () {
    this._showToast("Feedback submitted \u2014 thank you!");
    this.close();
    this._resetForm();
  };

  FeedbackWidget.prototype._resetForm = function () {
    this._category = null;
    this._severity = "minor";
    this._textarea.value = "";
    this._submitBtn.disabled = false;
    this._panel.querySelectorAll(".dz-feedback-cat-btn").forEach(function (b) {
      setPressed(b, false);
    });
    this._panel.querySelectorAll(".dz-feedback-sev-btn").forEach(function (b) {
      setPressed(b, b.getAttribute("data-severity") === "minor");
    });
  };

  /* ------------------------------------------------------------------ */
  /* Offline retry                                                        */
  /* ------------------------------------------------------------------ */

  FeedbackWidget.prototype._savePending = function (payload, key) {
    try {
      var pending = JSON.parse(localStorage.getItem(PENDING_KEY) || "[]");
      pending.push({ payload: payload, key: key, ts: Date.now() });
      localStorage.setItem(PENDING_KEY, JSON.stringify(pending));
    } catch (_) {
      /* noop */
    }
  };

  FeedbackWidget.prototype._retryPending = function () {
    try {
      var pending = JSON.parse(localStorage.getItem(PENDING_KEY) || "[]");
      if (!pending.length) return;
      // Clear storage first to prevent duplicate retries on reload (#693)
      localStorage.removeItem(PENDING_KEY);
      var now = Date.now();
      var self = this;
      pending.forEach(function (item) {
        if (now - item.ts > PENDING_MAX_AGE_MS) return;
        self._doPost(item.payload, item.key, true);
      });
    } catch (_) {
      /* noop */
    }
  };

  /* ------------------------------------------------------------------ */
  /* Resolved-report notification (#721)                                  */
  /* ------------------------------------------------------------------ */

  FeedbackWidget.prototype._checkResolved = function () {
    var email = userEmail();
    if (!email) return;
    var self = this;
    fetch(
      "/feedbackreports?reported_by=" +
        encodeURIComponent(email) +
        "&status=resolved&notification_sent=false",
      { credentials: "same-origin" },
    )
      .then(function (resp) {
        if (!resp.ok) return;
        return resp.json();
      })
      .then(function (data) {
        if (!data) return;
        var items = data.items || data;
        if (!Array.isArray(items) || !items.length) return;
        items.forEach(function (report) {
          var desc = (report.description || "").substring(0, 60);
          self._showToast('Your feedback "' + desc + '" has been resolved.');
          self._markNotified(report.id);
        });
      })
      .catch(function () {
        /* silent — best-effort notification */
      });
  };

  FeedbackWidget.prototype._markNotified = function (reportId) {
    var csrfToken = "";
    var csrfMeta = document.querySelector('meta[name="csrf-token"]');
    if (csrfMeta) csrfToken = csrfMeta.getAttribute("content") || "";
    var headers = { "Content-Type": "application/json" };
    if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
    fetch("/feedbackreports/" + reportId, {
      method: "PUT",
      headers: headers,
      credentials: "same-origin",
      body: JSON.stringify({ notification_sent: true }),
    }).catch(function () {
      /* silent */
    });
  };

  /* ------------------------------------------------------------------ */
  /* Toast                                                                */
  /* ------------------------------------------------------------------ */

  FeedbackWidget.prototype._showToast = function (msg) {
    this._toast.textContent = msg;
    this._toast.classList.add("visible");
    var toast = this._toast;
    setTimeout(function () {
      toast.classList.remove("visible");
    }, 3000);
  };

  /** Mount once, and only for a signed-in user (the identity meta is
   *  emitted on authenticated app pages; public pages get no widget). */
  function mount() {
    if (window.feedbackWidget || !userEmail()) return;
    window.feedbackWidget = new FeedbackWidget();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
