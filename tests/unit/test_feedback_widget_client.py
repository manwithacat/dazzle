"""Client behaviour of ``feedback-widget.js`` (flense ship AB, #869).

Runs the shipped script under Node against a minimal fake DOM (no jsdom /
browser in the toolchain) and pins what the chrome wiring relies on:

* mounting creates the floating button, and a second load of the script on
  the same page is a no-op (one button, one resolved-report poll);
* nothing is shown on load when the user has no newly resolved report — the
  #869 shape was a toast on every page load;
* a resolved report toasts once and is marked ``notification_sent``; the next
  page load (server no longer returns it) shows nothing;
* submit POSTs to ``/feedbackreports`` with the identity from the
  ``dz-user-email`` / ``dz-user-role`` meta tags;
* with no signed-in identity the widget does not mount at all;
* #1841: the closed panel is ``inert`` + ``aria-hidden``, opening focuses it,
  Tab wraps inside it, Escape closes it and focus returns to the opener, the
  controls are labelled/grouped and the toggles expose ``aria-pressed``.

Skipped when ``node`` is not on PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WIDGET_JS = REPO_ROOT / "src/dazzle/page/runtime/static/js/feedback-widget.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

# A fake DOM just wide enough for the widget: element tree, classList,
# attributes, events, meta lookup, storage and a recording fetch.
_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const src = fs.readFileSync(process.argv[2], "utf8");
const scenario = JSON.parse(process.argv[3]);

const focusState = { active: null };

function makeEl(tag) {
  const el = {
    tagName: tag.toUpperCase(), children: [], parent: null, attrs: {},
    listeners: {}, textContent: "", value: "", disabled: false, className: "",
    dataset: {},
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    hasAttribute(k) { return k in this.attrs; },
    removeAttribute(k) { delete this.attrs[k]; },
    focus() { focusState.active = this; },
    appendChild(c) { if (c.parent) c.parent.removeChild(c); c.parent = this; this.children.push(c); return c; },
    removeChild(c) { this.children = this.children.filter((x) => x !== c); c.parent = null; },
    remove() { if (this.parent) this.parent.removeChild(this); },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    click() { (this.listeners.click || []).forEach((fn) => fn({ target: this })); },
    contains(n) { for (let x = n; x; x = x.parent) { if (x === this) return true; } return false; },
    all() { return this.children.flatMap((c) => [c, ...c.all()]); },
    querySelectorAll(sel) {
      const parts = sel.split(",").map((x) => x.trim());
      return this.all().filter((e) => parts.some((p) => p.startsWith(".")
        ? e.classList.contains(p.slice(1)) : e.tagName === p.toUpperCase()));
    },
    cloneNode() { throw new Error("no snapshot in the fake DOM"); },
  };
  el.classList = {
    _set: new Set(),
    add(c) { this._set.add(c); }, remove(c) { this._set.delete(c); },
    contains(c) { return this._set.has(c) || el.className.split(" ").includes(c); },
    toggle(c, on) { on ? this._set.add(c) : this._set.delete(c); },
  };
  return el;
}

function run(page) {
  const calls = [];
  const head = makeEl("head");
  for (const [name, content] of Object.entries(page.meta || {})) {
    const m = makeEl("meta"); m.setAttribute("name", name); m.setAttribute("content", content);
    head.appendChild(m);
  }
  const body = makeEl("body");
  const docListeners = {};
  const document = {
    readyState: "complete", body, title: "Page",
    get activeElement() { return focusState.active || body; },
    createElement: makeEl,
    createElementNS: (_ns, tag) => makeEl(tag),
    querySelector(sel) {
      const m = sel.match(/^meta\[name="([^"]+)"\]$/);
      if (!m) return null;
      return head.children.find((e) => e.getAttribute("name") === m[1]) || null;
    },
    addEventListener(t, fn) { (docListeners[t] = docListeners[t] || []).push(fn); },
  };
  focusState.active = null;
  const store = () => { const d = {}; return {
    getItem: (k) => (k in d ? d[k] : null), setItem: (k, v) => { d[k] = String(v); },
    removeItem: (k) => { delete d[k]; } }; };
  const resolved = page.resolved || [];
  const fetch = (url, opts) => {
    const method = (opts && opts.method) || "GET";
    calls.push({ url, method, body: opts && opts.body ? JSON.parse(opts.body) : null });
    const payload = method === "GET" ? { items: resolved } : {};
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payload) });
  };
  const timers = [];
  const ctx = {
    document, fetch, console, JSON, Date, String, Array, Promise,
    localStorage: store(), sessionStorage: store(),
    location: { href: "http://app.test/app/tasks" },
    navigator: { userAgent: "node" }, innerWidth: 1280, innerHeight: 800,
    crypto: { randomUUID: () => "uuid-1" },
    setTimeout: (fn) => { timers.push(fn); return timers.length; },
    addEventListener() {},
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  for (let i = 0; i < (page.loads || 1); i++) vm.runInContext(src, ctx);
  return { ctx, body, calls, docListeners };
}

const settle = () => new Promise((r) => setImmediate(r));

(async () => {
  const { ctx, body, calls, docListeners } = run(scenario);
  await settle(); await settle();
  const btns = body.children.filter((e) => e.className === "dz-feedback-btn");
  const toast = body.children.find((e) => e.className === "dz-feedback-toast");
  const out = {
    buttons: btns.length,
    toastVisible: !!toast && toast.classList.contains("visible"),
    toastText: toast ? toast.textContent : "",
    calls: calls.slice(),
  };
  if (scenario.swap) {
    body.children.slice().forEach((c) => body.removeChild(c));
    (docListeners["htmx:after:swap"] || []).forEach((fn) => fn({}));
    out.buttonsAfterSwap = body.children.filter((e) => e.className === "dz-feedback-btn").length;
  }
  const key = (target, k, extra) => {
    const ev = Object.assign({ key: k, target, defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; } }, extra || {});
    for (let el = target; el && el !== body; el = el.parent) {
      (el.listeners.keydown || []).forEach((fn) => fn(ev));
    }
    (docListeners.keydown || []).forEach((fn) => fn(ev));
    return ev;
  };
  const panelState = (w) => ({
    open: w._panel.classList.contains("open"),
    inert: w._panel.hasAttribute("inert"),
    ariaHidden: w._panel.getAttribute("aria-hidden"),
    focus: focusState.active ? (focusState.active.getAttribute("data-category")
      || focusState.active.className || focusState.active.tagName) : null,
  });
  if (scenario.a11y) {
    const w = ctx.feedbackWidget;
    const p = w._panel;
    const textarea = w._textarea;
    const label = p.all().find((e) => e.tagName === "LABEL");
    const groups = p.all().filter((e) => e.getAttribute("role") === "group");
    const byId = (id) => p.all().find((e) => e.id === id);
    out.markup = {
      role: p.getAttribute("role"),
      ariaModal: p.getAttribute("aria-modal"),
      title: (byId(p.getAttribute("aria-labelledby")) || {}).textContent,
      labelFor: label ? label.getAttribute("for") : null,
      textareaId: textarea.id,
      groups: groups.map((g) => (byId(g.getAttribute("aria-labelledby")) || {}).textContent),
      toastRole: toast.getAttribute("role"),
      iconHidden: w._btn.children[0].getAttribute("aria-hidden"),
    };
    out.closed = panelState(w);
    // Open from the floating button: focus moves into the panel.
    w._btn.focus();
    w._btn.click();
    out.opened = panelState(w);
    // Tab from the last control wraps to the first (the close button), and
    // Shift+Tab from there wraps back to submit.
    w._submitBtn.focus();
    const tab = key(w._submitBtn, "Tab");
    const wrappedTo = focusState.active.className;
    const back = key(focusState.active, "Tab", { shiftKey: true });
    out.tabWrapped = tab.defaultPrevented && wrappedTo === "dz-feedback-close"
      && back.defaultPrevented && focusState.active === w._submitBtn;
    // Toggle state is exposed through aria-pressed.
    const cat = (c) => p.querySelectorAll(".dz-feedback-cat-btn").find((b) => b.getAttribute("data-category") === c);
    const sev = (v) => p.querySelectorAll(".dz-feedback-sev-btn").find((b) => b.getAttribute("data-severity") === v);
    const sevBefore = { minor: sev("minor").getAttribute("aria-pressed"), blocker: sev("blocker").getAttribute("aria-pressed") };
    cat("ux").click();
    sev("blocker").click();
    out.pressed = {
      ux: cat("ux").getAttribute("aria-pressed"), bug: cat("bug").getAttribute("aria-pressed"),
      sevBefore,
      blocker: sev("blocker").getAttribute("aria-pressed"), minor: sev("minor").getAttribute("aria-pressed"),
    };
    // Escape inside the panel closes it and returns focus to the opener.
    const esc = key(textarea, "Escape");
    out.escapePrevented = esc.defaultPrevented;
    out.afterEscape = panelState(w);
    out.focusIsOpener = focusState.active === w._btn;
    // An opener elsewhere on the page gets focus back.
    const link = makeEl("a"); body.appendChild(link); link.focus();
    w.open(); w.close();
    out.focusBackToLink = focusState.active === link;
  }
  if (scenario.submit) {
    const w = ctx.feedbackWidget;
    w.open();
    w._panel.querySelectorAll(".dz-feedback-cat-btn").find((b) => b.getAttribute("data-category") === "bug").click();
    w._textarea.value = "Totals are wrong";
    w._submitBtn.click();
    await settle(); await settle();
    out.calls = calls.slice();
    out.toastText = toast.textContent;
  }
  process.stdout.write(JSON.stringify(out));
})();
"""

_IDENTITY = {"dz-user-email": "ada@example.test", "dz-user-role": "teacher"}


def _run(tmp_path: Path, scenario: dict[str, object]) -> dict[str, object]:
    harness = tmp_path / "harness.js"
    harness.write_text(_HARNESS)
    proc = subprocess.run(
        ["node", str(harness), str(WIDGET_JS), json.dumps(scenario)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    result: dict[str, object] = json.loads(proc.stdout)
    return result


def _polls(result: dict[str, object]) -> list[dict[str, object]]:
    calls = result["calls"]
    assert isinstance(calls, list)
    return [c for c in calls if c["method"] == "GET"]


def test_mount_is_idempotent_and_silent_on_load(tmp_path: Path) -> None:
    result = _run(tmp_path, {"meta": _IDENTITY, "loads": 2})
    assert result["buttons"] == 1
    assert result["toastVisible"] is False
    polls = _polls(result)
    assert len(polls) == 1
    assert polls[0]["url"] == (
        "/feedbackreports?reported_by=ada%40example.test&status=resolved&notification_sent=false"
    )


def test_resolved_report_toasts_once_then_never_again(tmp_path: Path) -> None:
    first = _run(
        tmp_path,
        {"meta": _IDENTITY, "resolved": [{"id": "r1", "description": "Totals are wrong"}]},
    )
    assert first["toastVisible"] is True
    assert "has been resolved" in str(first["toastText"])
    calls = first["calls"]
    assert isinstance(calls, list)
    assert {"url": "/feedbackreports/r1", "method": "PUT", "body": {"notification_sent": True}} in (
        calls
    )
    # The next page load: the server filters notification_sent=false, so the
    # report is gone and nothing shows.
    second = _run(tmp_path, {"meta": _IDENTITY, "resolved": []})
    assert second["toastVisible"] is False


def test_submit_posts_report_with_meta_identity(tmp_path: Path) -> None:
    result = _run(tmp_path, {"meta": _IDENTITY, "submit": True})
    calls = result["calls"]
    assert isinstance(calls, list)
    posts = [c for c in calls if c["method"] == "POST"]
    assert len(posts) == 1
    assert posts[0]["url"] == "/feedbackreports"
    body = posts[0]["body"]
    assert body["reported_by"] == "ada@example.test"
    assert body["persona"] == "teacher"
    assert body["category"] == "bug"
    assert body["description"] == "Totals are wrong"
    assert result["toastText"] == "Feedback submitted — thank you!"


def test_no_identity_no_widget(tmp_path: Path) -> None:
    """Public / signed-out pages: no button, no poll."""
    result = _run(tmp_path, {"meta": {}})
    assert result["buttons"] == 0
    assert _polls(result) == []


def test_nodes_reattach_after_htmx_body_swap(tmp_path: Path) -> None:
    result = _run(tmp_path, {"meta": _IDENTITY, "swap": True})
    assert result["buttonsAfterSwap"] == 1


def test_closed_panel_is_inert_and_hidden(tmp_path: Path) -> None:
    """#1841: the off-screen panel is out of the tab order and the a11y tree."""
    result = _run(tmp_path, {"meta": _IDENTITY, "a11y": True})
    assert result["closed"] == {"open": False, "inert": True, "ariaHidden": "true", "focus": None}
    assert result["afterEscape"]["inert"] is True
    assert result["afterEscape"]["ariaHidden"] == "true"


def test_panel_markup_names_its_controls(tmp_path: Path) -> None:
    result = _run(tmp_path, {"meta": _IDENTITY, "a11y": True})
    markup = result["markup"]
    assert isinstance(markup, dict)
    assert markup["role"] == "dialog"
    assert markup["ariaModal"] == "true"
    assert markup["title"] == "Send Feedback"
    assert markup["labelFor"] == markup["textareaId"] == "dz-feedback-description"
    assert markup["groups"] == ["Category", "Severity (optional)"]
    assert markup["toastRole"] == "status"
    assert markup["iconHidden"] == "true"


def test_open_focuses_panel_and_escape_returns_focus(tmp_path: Path) -> None:
    result = _run(tmp_path, {"meta": _IDENTITY, "a11y": True})
    assert result["opened"] == {"open": True, "inert": False, "ariaHidden": None, "focus": "bug"}
    assert result["tabWrapped"] is True
    assert result["escapePrevented"] is True
    assert result["afterEscape"]["open"] is False
    assert result["focusIsOpener"] is True
    assert result["focusBackToLink"] is True


def test_toggles_expose_aria_pressed(tmp_path: Path) -> None:
    result = _run(tmp_path, {"meta": _IDENTITY, "a11y": True})
    assert result["pressed"] == {
        "ux": "true",
        "bug": "false",
        "sevBefore": {"minor": "true", "blocker": "false"},
        "blocker": "true",
        "minor": "false",
    }
