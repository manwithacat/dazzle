"""Client behaviour of ``feedback-widget.js`` (flense ship AB, #869; #1854).

Runs the shipped script under Node against a minimal fake DOM (no jsdom /
browser in the toolchain) and pins what the chrome wiring relies on:

* mounting creates the ``<dz-feedback>`` host with one floating button in its
  shadow root, and a second load of the script is a no-op (one button, one
  resolved-report poll);
* nothing is shown on load when the user has no newly resolved report — the
  #869 shape was a toast on every page load;
* a resolved report toasts once and is marked ``notification_sent``; the next
  page load (server no longer returns it) shows nothing;
* submit POSTs to ``/feedbackreports`` with the identity from the
  ``dz-user-email`` / ``dz-user-role`` meta tags, an ``Idempotency-Key``
  header equal to the ``idempotency_key`` field, and ``anchor`` / ``context``;
* with no signed-in identity the widget does not mount at all;
* #1842: the ``dz-feedback-shortcut`` meta configures the toggle key —
  ``none`` turns it off, a bare key is ignored while focus is in a field,
  select, button, link or contenteditable, a Ctrl combination works anywhere;
* #1841: the closed panel is ``inert`` + ``aria-hidden``, opening focuses it,
  Tab wraps inside it, Escape closes it and focus returns to the opener, the
  controls are labelled/grouped and the toggles expose ``aria-pressed``;
* #1854: categories and severities come from the metas; the review posture
  (``dz-feedback-review`` = 1) arms anchor mode from its chord or the
  "Point at it" button, a capture-phase click opens the note card and never
  reaches the page, Enter saves and Escape returns focus to the element, the
  anchor record and context are captured, the localStorage queue replays an
  unsent note under the same key and drops a rejected one, pins are
  re-anchored dz_anchor → css → text quote → rect (orphaned) and Resolve
  walks new → triaged → resolved; the screenshot control only appears under
  the ``optional`` policy with ``getDisplayMedia`` present on a desktop UA.

Skipped when ``node`` is not on PATH.
"""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WIDGET_JS = REPO_ROOT / "src/dazzle/page/runtime/static/js/feedback-widget.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

# A fake DOM just wide enough for the widget: element tree, classList,
# attributes, a compound-selector engine (no combinators), capture/bubble
# events across the shadow boundary, storage and a rule-driven fetch.
_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const src = fs.readFileSync(process.argv[2], "utf8");
const scenario = JSON.parse(process.argv[3]);
const focusState = { active: null };

// --- selectors: `tag#id.cls[attr="v"]:nth-of-type(n)`, comma lists ---
const TOKEN = /^(?:#([\w-]+)|\.([\w-]+)|\[([\w-]+)(?:="?([^\]"]*)"?)?\]|:nth-of-type\((\d+)\)|:not\(([^)]+)\))/;
function parseCompound(sel) {
  const out = { tag: null, id: null, classes: [], attrs: [], nth: null, nots: [] };
  let rest = sel.trim();
  if (/[\s>+~]/.test(rest.replace(/\[[^\]]*\]/g, ""))) throw new Error("unsupported selector: " + sel);
  const tag = rest.match(/^([a-z][\w-]*|\*)/i);
  if (tag) { if (tag[1] !== "*") out.tag = tag[1].toUpperCase(); rest = rest.slice(tag[0].length); }
  while (rest.length) {
    const m = rest.match(TOKEN);
    if (!m) throw new Error("bad selector: " + sel);
    if (m[1]) out.id = m[1];
    else if (m[2]) out.classes.push(m[2]);
    else if (m[3]) out.attrs.push([m[3], m[4]]);
    else if (m[5]) out.nth = parseInt(m[5], 10);
    else if (m[6]) out.nots.push(parseCompound(m[6]));
    rest = rest.slice(m[0].length);
  }
  return out;
}
function matchesCompound(el, c) {
  if (el.nodeType !== 1) return false;
  if (c.tag && el.tagName !== c.tag) return false;
  if (c.id && el.id !== c.id) return false;
  if (!c.classes.every((k) => el.classList.contains(k))) return false;
  if (!c.attrs.every(([k, v]) => el.hasAttribute(k) && (v === undefined || el.getAttribute(k) === v))) return false;
  if (c.nots.some((n) => matchesCompound(el, n))) return false;
  if (c.nth) {
    const sibs = (el.parent ? el.parent.children : []).filter((s) => s.nodeType === 1 && s.tagName === el.tagName);
    if (sibs.indexOf(el) + 1 !== c.nth) return false;
  }
  return true;
}
function matchesSel(el, sel) {
  return sel.split(",").some((s) => matchesCompound(el, parseCompound(s)));
}

let seq = 0;
function makeText(s) {
  return { nodeType: 3, _text: s, parent: null, get textContent() { return this._text; }, set textContent(v) { this._text = v; } };
}
function makeEl(tag) {
  const cl = [];
  cl.contains = (c) => cl.includes(c);
  cl.add = (c) => { if (!cl.includes(c)) cl.push(c); };
  cl.remove = (c) => { const i = cl.indexOf(c); if (i >= 0) cl.splice(i, 1); };
  cl.toggle = (c, on) => (on ? cl.add(c) : cl.remove(c));
  const el = {
    nodeType: 1, tagName: tag.toUpperCase(), children: [], parent: null, attrs: {}, listeners: [],
    _text: "", value: "", disabled: false, checked: false, style: {}, classList: cl, uid: ++seq,
    get className() { return cl.join(" "); },
    set className(v) { cl.splice(0, cl.length, ...String(v).split(/\s+/).filter(Boolean)); },
    get id() { return this.attrs.id || ""; }, set id(v) { this.attrs.id = v; },
    get parentElement() { return this.parent && this.parent.nodeType === 1 ? this.parent : null; },
    get parentNode() { return this.parent; },
    get firstChild() { return this.children[0] || null; },
    get firstElementChild() { return this.children.find((c) => c.nodeType === 1) || null; },
    get nextSibling() { const s = this.parent ? this.parent.children : []; return s[s.indexOf(this) + 1] || null; },
    get attributes() { return Object.entries(this.attrs).map(([name, value]) => ({ name, value })); },
    get textContent() { return this.children.length ? this.children.map((c) => c.textContent).join("") : this._text; },
    set textContent(v) { this.children = []; this._text = String(v); },
    setAttribute(k, v) { if (k === "class") this.className = v; else this.attrs[k] = String(v); },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    hasAttribute(k) { return k in this.attrs; },
    removeAttribute(k) { delete this.attrs[k]; },
    focus() { if (!this.inert) focusState.active = this; },
    appendChild(c) { if (c.parent) c.parent.removeChild(c); c.parent = this; this.children.push(c); return c; },
    removeChild(c) { this.children = this.children.filter((x) => x !== c); c.parent = null; },
    remove() { if (this.parent) this.parent.removeChild(this); },
    addEventListener(t, fn, opts) { this.listeners.push({ t, fn, capture: !!(opts === true || (opts && opts.capture)) }); },
    contains(n) { for (let x = n; x; x = x.parent) { if (x === this) return true; } return false; },
    all() { return this.children.flatMap((c) => (c.nodeType === 1 ? [c, ...c.all()] : [])); },
    matches(sel) { return matchesSel(this, sel); },
    closest(sel) { for (let x = this; x && x.nodeType === 1; x = x.parentElement) { if (x.matches(sel)) return x; } return null; },
    querySelectorAll(sel) { return this.all().filter((e) => matchesSel(e, sel)); },
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
    getBoundingClientRect() { const r = this.rect || [0, 0, 0, 0]; return { left: r[0], top: r[1], width: r[2], height: r[3], right: r[0] + r[2], bottom: r[1] + r[3] }; },
    cloneNode() { throw new Error("no snapshot in the fake DOM"); },
    click() { dispatch(this, "click", {}); },
    attachShadow() { return makeShadow(this); },
  };
  return el;
}
function makeShadow(host) {
  const root = makeEl("#shadow-root");
  root.host = host;
  root.parent = host; // so host.contains(inner) holds, as elementFromPoint retargets in a browser
  Object.defineProperty(root, "activeElement", { get: () => (focusState.active && root.contains(focusState.active) ? focusState.active : null) });
  host.shadowRoot = root;
  return root;
}

// Build a page from the scenario's JSON tree: {tag, attrs, text, children, rect, pageClick}.
const pageClicks = [];
function build(node, parent) {
  const el = makeEl(node.tag || "div");
  for (const [k, v] of Object.entries(node.attrs || {})) el.setAttribute(k, v);
  if (node.text) el.appendChild(makeText(node.text));
  if (node.rect) el.rect = node.rect;
  if (node.pageClick) el.addEventListener("click", () => pageClicks.push(node.pageClick));
  parent.appendChild(el);
  (node.children || []).forEach((c) => build(c, el));
  return el;
}

const docListeners = [];
let document, body, head, ctx, calls, timers;
function dispatch(target, type, init) {
  const path = [];
  for (let x = target; x; x = x.parent) path.push(x);
  const ev = Object.assign({ type, target, defaultPrevented: false, _stopped: false,
    preventDefault() { this.defaultPrevented = true; },
    stopPropagation() { this._stopped = true; }, stopImmediatePropagation() { this._stopped = true; },
    composedPath() { return path.concat([document]); } }, init || {});
  for (const l of docListeners) if (l.t === type && l.capture && !ev._stopped) l.fn(ev);
  for (const el of path) {
    if (ev._stopped) break;
    for (const l of el.listeners) if (l.t === type && !ev._stopped) l.fn(ev);
  }
  for (const l of docListeners) if (l.t === type && !l.capture && !ev._stopped) l.fn(ev);
  return ev;
}

function run(page) {
  calls = [];
  timers = [];
  head = makeEl("head");
  for (const [name, content] of Object.entries(page.meta || {})) {
    const m = makeEl("meta"); m.setAttribute("name", name); m.setAttribute("content", content); head.appendChild(m);
  }
  body = makeEl("body");
  for (const [k, v] of Object.entries(page.body || {})) body.setAttribute(k, v);
  (page.dom || []).forEach((n) => build(n, body));
  docListeners.length = 0;
  let pointAt = null;
  document = {
    readyState: "complete", body, title: "Page", referrer: "", visibilityState: "visible",
    get activeElement() { return focusState.active || body; },
    createElement: makeEl, createElementNS: (_ns, tag) => makeEl(tag), createTextNode: makeText,
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
    querySelectorAll(sel) { return [...head.all(), ...body.all()].filter((e) => matchesSel(e, sel)); },
    addEventListener(t, fn, opts) { docListeners.push({ t, fn, capture: !!(opts === true || (opts && opts.capture)) }); },
    elementFromPoint() { return pointAt; },
    setPointAt(el) { pointAt = el; },
  };
  focusState.active = null;
  const store = (init) => { const d = Object.assign({}, init || {}); return {
    getItem: (k) => (k in d ? d[k] : null), setItem: (k, v) => { d[k] = String(v); },
    removeItem: (k) => { delete d[k]; }, dump: () => Object.assign({}, d) }; };
  const resolved = page.resolved || [];
  const rules = page.fetch || [];
  const fetch = (url, opts) => {
    const method = (opts && opts.method) || "GET";
    const headers = (opts && opts.headers) || {};
    calls.push({ url, method, headers, body: opts && opts.body ? JSON.parse(opts.body) : null });
    const rule = rules.find((r) => (!r.method || r.method === method) && (!r.url || url.includes(r.url)));
    if (rule && rule.fail) return Promise.reject(new Error("network"));
    const status = rule ? rule.status : method === "POST" ? 201 : 200;
    let payload = rule && "body" in rule ? rule.body : method === "GET" ? { items: url.includes("page_url=") ? page.pins || [] : resolved } : { id: "new" };
    return Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(payload) });
  };
  ctx = {
    document, fetch, console, JSON, Date, String, Array, Object, Promise, Math, Reflect, Error, URL, encodeURIComponent,
    localStorage: store(page.localStorage), sessionStorage: store(page.sessionStorage),
    location: { href: "http://app.test/app/tasks?x=1#top", origin: "http://app.test", pathname: "/app/tasks" },
    navigator: navigatorFor(page.navigator || {}), HTMLCanvasElement: function () {},
    innerWidth: 1280, innerHeight: 800, scrollX: 0, scrollY: 0, devicePixelRatio: 2,
    crypto: { randomUUID: () => "uuid-" + (++uuidN) },
    setTimeout: (fn) => { timers.push(fn); return timers.length; }, clearTimeout() {},
    requestAnimationFrame: (fn) => { setImmediate(fn); return 1; },
    customElements: { get: () => undefined, define() {} },
    addEventListener(t, fn) { docListeners.push({ t: "window:" + t, fn, capture: false }); },
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  for (let i = 0; i < (page.loads || 1); i++) vm.runInContext(src, ctx);
}
let uuidN = 0;
function navigatorFor(given) {
  const nav = Object.assign({ userAgent: "node", language: "en-GB" }, given);
  if (nav.mediaDevices && nav.mediaDevices.getDisplayMedia) nav.mediaDevices.getDisplayMedia = () => Promise.reject(new Error("no"));
  return nav;
}
const settle = () => new Promise((r) => setImmediate(r));
const host = () => body.children.find((e) => e.tagName === "DZ-FEEDBACK");
const root = () => host().shadowRoot;
const sel = (s) => (s === "textarea" ? w()._textarea : s === "note" ? w()._noteText : document.querySelector(s) || root().querySelector(s));
const w = () => ctx.feedbackWidget;
const describeFocus = () => {
  const a = focusState.active;
  return a ? a.getAttribute("data-category") || a.className || a.tagName : null;
};
const dialogState = (d) => (d ? { open: d.classList.contains("open"), inert: d.hasAttribute("inert"), ariaHidden: d.getAttribute("aria-hidden") } : null);
function state() {
  const r = host() ? root() : null;
  const q = (s) => (r ? r.querySelectorAll(s) : []);
  const toast = q(".dz-feedback-toast")[0];
  const widget = w();
  return {
    buttons: q(".dz-feedback-btn").length,
    btnTitle: widget ? widget._btn.getAttribute("title") : null,
    btnKeys: widget ? widget._btn.getAttribute("aria-keyshortcuts") : null,
    toastVisible: !!toast && toast.classList.contains("visible"),
    toastText: toast ? toast.textContent : "",
    calls: calls.slice(),
    panel: widget ? Object.assign(dialogState(widget._panel), { focus: describeFocus() }) : null,
    card: widget && widget._card ? Object.assign(dialogState(widget._card), { path: widget._cardPath.textContent, focus: describeFocus(),
      category: widget._noteCategory.value, severity: widget._noteSeverity, shotCheck: !!widget._shotCheck }) : null,
    note: widget && widget._note ? Object.assign(dialogState(widget._note), { title: widget._noteTitle.textContent, meta: widget._noteMeta.textContent }) : null,
    armed: !!(widget && widget._armed),
    cursor: body.style.cursor || "",
    outline: widget && widget._outline ? { visible: widget._outline.classList.contains("visible"), label: widget._outline.firstElementChild.textContent,
      left: widget._outline.style.left, top: widget._outline.style.top } : null,
    pointButton: q(".dz-feedback-ghost").some((b) => b.textContent === "Point at it"),
    categories: q(".dz-feedback-cat-btn").map((b) => [b.getAttribute("data-category"), b.textContent, b.getAttribute("aria-pressed")]),
    severities: widget ? [...widget._sevRow.children].map((b) => [b.getAttribute("data-severity"), b.textContent, b.getAttribute("aria-pressed")]) : [],
    pins: q(".dz-feedback-pin").map((p) => ({ n: p.textContent, id: p.getAttribute("data-report-id"), status: p.getAttribute("data-status"),
      orphaned: p.hasAttribute("data-orphaned"), label: p.getAttribute("aria-label"), left: p.style.left, top: p.style.top })),
    pageClicks: pageClicks.slice(),
    queue: JSON.parse(ctx.localStorage.getItem("dz_feedback_pending") || "{}"),
    focus: describeFocus(),
    focusIs: focusState.active ? focusState.active.uid : null,
  };
}

(async () => {
  run(scenario);
  await settle(); await settle();
  const out = { initial: state(), snapshots: {} };
  const key = (target, k, extra) => dispatch(target, "keydown", Object.assign({ key: k }, extra || {}));
  for (const op of scenario.ops || []) {
    if (op.op === "snapshot") out.snapshots[op.name] = state();
    else if (op.op === "settle") { await settle(); await settle(); }
    else if (op.op === "swap") {
      body.children.slice().forEach((c) => body.removeChild(c));
      dispatch(body, "htmx:after:swap", {});
    } else if (op.op === "key") {
      let target = body;
      if (op.on === "editable") { target = makeEl("div"); target.isContentEditable = true; body.appendChild(target); }
      else if (op.on) target = sel(op.on) || (() => { const t = makeEl(op.on); body.appendChild(t); return t; })();
      const ev = key(target, op.key, { ctrlKey: !!op.ctrl, shiftKey: !!op.shift, altKey: !!op.alt, metaKey: !!op.meta });
      out.snapshots[op.name || "key"] = Object.assign(state(), { prevented: ev.defaultPrevented });
    } else if (op.op === "focus") { sel(op.at).focus(); }
    else if (op.op === "hover") { const el = sel(op.at); document.setPointAt(el); dispatch(el, "pointermove", { clientX: 1, clientY: 1 }); }
    else if (op.op === "click") { const el = sel(op.at); document.setPointAt(el); const ev = dispatch(el, "click", { clientX: 1, clientY: 1 }); out.snapshots[op.name || "click"] = Object.assign(state(), { prevented: ev.defaultPrevented }); }
    else if (op.op === "type") { sel(op.at || "note").value = op.text; }
    else if (op.op === "call") { w()[op.name](...(op.args || [])); }
    else if (op.op === "htmx") { const c = { request: { method: op.method, action: op.url }, response: op.status ? { status: op.status } : null }; dispatch(body, "htmx:before:request", { detail: { ctx: c } }); if (op.status) dispatch(body, op.status >= 400 ? "htmx:response:error" : "htmx:after:request", { detail: { ctx: c } }); }
    else if (op.op === "error") { docListeners.filter((l) => l.t === "window:error").forEach((l) => l.fn({ message: op.message, filename: "app.js", lineno: 7 })); }
    else if (op.op === "consoleError") { vm.runInContext("console.error(" + JSON.stringify(op.message) + ", {code: 7})", ctx); }
    else if (op.op === "tab") {
      const a11y = {};
      const widget = w(); const p = widget._panel;
      const label = p.all().find((e) => e.tagName === "LABEL");
      const groups = p.all().filter((e) => e.getAttribute("role") === "group");
      const byId = (id) => p.all().find((e) => e.id === id);
      a11y.markup = { role: p.getAttribute("role"), ariaModal: p.getAttribute("aria-modal"),
        title: (byId(p.getAttribute("aria-labelledby")) || {}).textContent, labelFor: label ? label.getAttribute("for") : null,
        textareaId: widget._textarea.id, groups: groups.map((g) => (byId(g.getAttribute("aria-labelledby")) || {}).textContent),
        toastRole: widget._toast.getAttribute("role"), iconHidden: widget._btn.children[0].getAttribute("aria-hidden") };
      widget._submitBtn.focus();
      const tab = key(widget._submitBtn, "Tab");
      const wrappedTo = focusState.active.className;
      const back = key(focusState.active, "Tab", { shiftKey: true });
      a11y.tabWrapped = tab.defaultPrevented && wrappedTo === "dz-feedback-close" && back.defaultPrevented && focusState.active === widget._submitBtn;
      out.a11y = a11y;
    } else if (op.op === "reopenFromLink") {
      // An opener elsewhere on the page gets focus back.
      const link = makeEl("a"); body.appendChild(link); link.focus();
      w().open(); w().close();
      out.a11y.focusBackToLink = focusState.active === link;
    }
  }
  out.final = state();
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
"""

_IDENTITY = {"dz-user-email": "ada@example.test", "dz-user-role": "teacher"}
_REVIEW = dict(_IDENTITY, **{"dz-feedback-review": "1"})

# A tasks page: a region with one row and an action, a form field, a button
# the page itself listens to (to prove the armed click never reaches it).
_PAGE = {
    "body": {
        "data-dz-surface": "tasks",
        "data-dz-entity": "Task",
        "data-dz-record": "t-7",
        "data-dz-workspace": "ops",
        "data-dz-persona": "teacher",
    },
    "dom": [
        {
            "tag": "section",
            "attrs": {"data-dz-region-name": "open_tasks"},
            "children": [
                {
                    "tag": "tr",
                    "attrs": {"data-dz-row-id": "7"},
                    "children": [
                        {"tag": "td", "text": "Write the report "},
                        {
                            "tag": "button",
                            "attrs": {"data-dz-action": "complete", "id": "done"},
                            "text": "Complete",
                            "rect": [100, 200, 80, 24],
                            "pageClick": "complete",
                        },
                    ],
                }
            ],
        },
        {
            "tag": "div",
            "attrs": {"class": "dz-form-field"},
            "children": [
                {"tag": "label", "attrs": {"for": "title"}, "text": "Title"},
                {
                    "tag": "input",
                    "attrs": {"name": "title", "id": "title"},
                    "rect": [10, 300, 200, 30],
                },
            ],
        },
        {"tag": "p", "attrs": {"id": "intro"}, "text": "Welcome back", "rect": [10, 10, 100, 20]},
    ],
}


def _run(tmp_path: Path, scenario: dict[str, Any]) -> dict[str, Any]:
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
    result: dict[str, Any] = json.loads(proc.stdout)
    return result


def _calls(result: dict[str, Any], method: str, key: str = "final") -> list[dict[str, Any]]:
    return [c for c in result[key]["calls"] if c["method"] == method]


def _review_note(tmp_path: Path, ops: list[dict[str, Any]], **page: Any) -> dict[str, Any]:
    """Arm, click the Complete button, type a note, then run ``ops``."""
    scenario = dict(_PAGE, meta=_REVIEW, **page)
    scenario["ops"] = [
        {"op": "key", "key": "r", "alt": True, "shift": True, "name": "armed"},
        {"op": "hover", "at": "#done"},
        {"op": "snapshot", "name": "hovered"},
        {"op": "click", "at": "#done", "name": "clicked"},
        {"op": "type", "text": "Button label is unclear"},
    ] + ops
    return _run(tmp_path, scenario)


# --------------------------------------------------------------------------
# Mount, toast-once, identity (#869)
# --------------------------------------------------------------------------


def test_mount_is_idempotent_and_silent_on_load(tmp_path: Path) -> None:
    result = _run(tmp_path, {"meta": _IDENTITY, "loads": 2})
    assert result["initial"]["buttons"] == 1
    assert result["initial"]["toastVisible"] is False
    polls = _calls(result, "GET")
    assert len(polls) == 1
    assert polls[0]["url"] == (
        "/feedbackreports?reported_by=ada%40example.test&status=resolved&notification_sent=false"
    )


def test_resolved_report_toasts_once_then_never_again(tmp_path: Path) -> None:
    first = _run(
        tmp_path,
        {"meta": _IDENTITY, "resolved": [{"id": "r1", "description": "Totals are wrong"}]},
    )
    assert first["initial"]["toastVisible"] is True
    assert "has been resolved" in first["initial"]["toastText"]
    puts = _calls(first, "PUT")
    assert [(c["url"], c["body"]) for c in puts] == [
        ("/feedbackreports/r1", {"notification_sent": True})
    ]
    second = _run(tmp_path, {"meta": _IDENTITY, "resolved": []})
    assert second["initial"]["toastVisible"] is False


def test_submit_posts_report_with_meta_identity(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        {
            "meta": _IDENTITY,
            "ops": [
                {"op": "call", "name": "open"},
                {"op": "click", "at": '[data-category="bug"]'},
                {"op": "type", "at": "textarea", "text": "Totals are wrong"},
                {"op": "click", "at": ".dz-feedback-submit"},
                {"op": "settle"},
            ],
        },
    )
    posts = _calls(result, "POST")
    assert len(posts) == 1
    assert posts[0]["url"] == "/feedbackreports"
    body = posts[0]["body"]
    assert body["reported_by"] == "ada@example.test"
    assert body["persona"] == "teacher"
    assert body["category"] == "bug"
    assert body["severity"] == "minor"
    assert body["description"] == "Totals are wrong"
    assert body["anchor"] is None
    assert body["idempotency_key"] == posts[0]["headers"]["Idempotency-Key"]
    assert result["final"]["toastText"] == "Feedback submitted — thank you!"
    assert result["final"]["queue"] == {}
    assert result["final"]["panel"]["open"] is False


def test_no_identity_no_widget(tmp_path: Path) -> None:
    """Public / signed-out pages: no host, no poll."""
    result = _run(tmp_path, {"meta": {}})
    assert result["initial"]["buttons"] == 0
    assert _calls(result, "GET") == []


def test_nodes_reattach_after_htmx_body_swap(tmp_path: Path) -> None:
    result = _run(tmp_path, {"meta": _IDENTITY, "ops": [{"op": "swap"}]})
    assert result["final"]["buttons"] == 1


# --------------------------------------------------------------------------
# Panel accessibility (#1841)
# --------------------------------------------------------------------------

_A11Y_OPS: list[dict[str, Any]] = [
    {"op": "focus", "at": ".dz-feedback-btn"},
    {"op": "click", "at": ".dz-feedback-btn", "name": "opened"},
    {"op": "tab"},
    {"op": "click", "at": '[data-category="ux"]'},
    {"op": "click", "at": '[data-severity="blocker"]', "name": "pressed"},
    {"op": "key", "key": "Escape", "on": "textarea", "name": "escaped"},
    {"op": "reopenFromLink"},
]


def test_closed_panel_is_inert_and_hidden(tmp_path: Path) -> None:
    """#1841: the off-screen panel is out of the tab order and the a11y tree."""
    result = _run(tmp_path, {"meta": _IDENTITY, "ops": _A11Y_OPS})
    assert result["initial"]["panel"] == {
        "open": False,
        "inert": True,
        "ariaHidden": "true",
        "focus": None,
    }
    after = result["snapshots"]["escaped"]["panel"]
    assert after["inert"] is True
    assert after["ariaHidden"] == "true"


def test_panel_markup_names_its_controls(tmp_path: Path) -> None:
    result = _run(tmp_path, {"meta": _IDENTITY, "ops": _A11Y_OPS})
    markup = result["a11y"]["markup"]
    assert markup["role"] == "dialog"
    assert markup["ariaModal"] == "true"
    assert markup["title"] == "Send Feedback"
    assert markup["labelFor"] == markup["textareaId"] == "dz-feedback-description"
    assert markup["groups"] == ["Category", "Severity (optional)"]
    assert markup["toastRole"] == "status"
    assert markup["iconHidden"] == "true"


def test_open_focuses_panel_and_escape_returns_focus(tmp_path: Path) -> None:
    result = _run(tmp_path, {"meta": _IDENTITY, "ops": _A11Y_OPS})
    opened = result["snapshots"]["opened"]["panel"]
    assert opened == {"open": True, "inert": False, "ariaHidden": None, "focus": "bug"}
    assert result["a11y"]["tabWrapped"] is True
    escaped = result["snapshots"]["escaped"]
    assert escaped["prevented"] is True
    assert escaped["panel"]["open"] is False
    assert escaped["focus"] == "dz-feedback-btn"
    assert result["a11y"]["focusBackToLink"] is True


def test_toggles_expose_aria_pressed(tmp_path: Path) -> None:
    result = _run(tmp_path, {"meta": _IDENTITY, "ops": _A11Y_OPS})
    before = {c: p for c, _l, p in result["initial"]["severities"]}
    assert before == {"blocker": "false", "annoying": "false", "minor": "true"}
    pressed = result["snapshots"]["pressed"]
    cats = {c: p for c, _l, p in pressed["categories"]}
    sevs = {c: p for c, _l, p in pressed["severities"]}
    assert cats["ux"] == "true" and cats["bug"] == "false"
    assert sevs["blocker"] == "true" and sevs["minor"] == "false"


# --------------------------------------------------------------------------
# Shortcuts (#1842)
# --------------------------------------------------------------------------


def _keys(tmp_path: Path, shortcut: str | None, keys: list[dict[str, Any]]) -> dict[str, Any]:
    meta = dict(_IDENTITY)
    if shortcut is not None:
        meta["dz-feedback-shortcut"] = shortcut
    ops: list[dict[str, Any]] = []
    for i, k in enumerate(keys):
        ops.append(dict(k, op="key", name=f"k{i}"))
        ops.append({"op": "call", "name": "close"})
    result = _run(tmp_path, {"meta": meta, "ops": ops})
    states = [result["snapshots"][f"k{i}"]["panel"]["open"] for i in range(len(keys))]
    return {"states": states, "result": result}


def _button_attrs(tmp_path: Path, shortcut: str | None) -> tuple[str | None, str | None]:
    meta = dict(_IDENTITY)
    if shortcut is not None:
        meta["dz-feedback-shortcut"] = shortcut
    initial = _run(tmp_path, {"meta": meta})["initial"]
    return initial["btnTitle"], initial["btnKeys"]


_FOCUS_OWNERS = ["input", "textarea", "select", "button", "a", "editable"]


def test_default_backtick_ignores_focus_that_owns_the_key(tmp_path: Path) -> None:
    """#1842 / WCAG 2.1.4: no meta → backtick, never while a control owns keys."""
    keys: list[dict[str, Any]] = [{"key": "`"}] + [{"key": "`", "on": t} for t in _FOCUS_OWNERS]
    assert _keys(tmp_path, None, keys)["states"] == [True] + [False] * len(_FOCUS_OWNERS)
    assert _button_attrs(tmp_path, None) == ("Send feedback (`)", "`")


def test_shortcut_none_disables_the_key(tmp_path: Path) -> None:
    assert _keys(tmp_path, "none", [{"key": "`"}, {"key": "`", "ctrl": True}])["states"] == [
        False,
        False,
    ]
    assert _button_attrs(tmp_path, "none") == ("Send feedback", None)


@pytest.mark.parametrize("spec", ["ctrl-shift-f", "ctrl+shift+f"])
def test_modified_shortcut_works_from_any_focus(tmp_path: Path, spec: str) -> None:
    keys: list[dict[str, Any]] = [
        {"key": "F", "ctrl": True, "shift": True, "on": "textarea"},
        {"key": "f", "ctrl": True, "shift": True, "on": "select"},
        {"key": "f", "ctrl": True},
        {"key": "f"},
        {"key": "`"},
    ]
    assert _keys(tmp_path, spec, keys)["states"] == [True, True, False, False, False]
    assert _button_attrs(tmp_path, spec) == ("Send feedback (Ctrl+Shift+F)", "Control+Shift+F")


@pytest.mark.parametrize(("spec", "key"), [("f1", "F1"), ("slash", "/"), ("question", "?")])
def test_named_keys(tmp_path: Path, spec: str, key: str) -> None:
    shift = key == "?"
    assert _keys(tmp_path, spec, [{"key": key, "shift": shift}, {"key": "`"}])["states"] == [
        True,
        False,
    ]


# --------------------------------------------------------------------------
# Metas-driven categories and severities (#1854)
# --------------------------------------------------------------------------


def test_default_categories_and_severities_without_metas(tmp_path: Path) -> None:
    result = _run(tmp_path, {"meta": _IDENTITY})
    initial = result["initial"]
    assert [c[0] for c in initial["categories"]] == [
        "bug",
        "ux",
        "visual",
        "behaviour",
        "enhancement",
        "other",
    ]
    assert [s[0] for s in initial["severities"]] == ["blocker", "annoying", "minor"]
    assert [s[2] for s in initial["severities"]] == ["false", "false", "true"]
    assert initial["pointButton"] is False
    assert initial["card"] is None


def test_metas_drive_categories_severities_and_default(tmp_path: Path) -> None:
    meta = dict(
        _IDENTITY,
        **{
            "dz-feedback-categories": "bug, ux,copy,data",
            "dz-feedback-severities": "p1,p2,p3,note",
        },
    )
    result = _run(
        tmp_path,
        {
            "meta": meta,
            "ops": [
                {"op": "call", "name": "open"},
                {"op": "click", "at": '[data-category="copy"]'},
                {"op": "type", "at": "textarea", "text": "Typo in the heading"},
                {"op": "click", "at": ".dz-feedback-submit"},
                {"op": "settle"},
            ],
        },
    )
    initial = result["initial"]
    assert initial["categories"] == [
        ["bug", "Bug", "false"],
        ["ux", "Ux", "false"],
        ["copy", "Copy", "false"],
        ["data", "Data", "false"],
    ]
    assert initial["severities"] == [
        ["p1", "P1", "true"],
        ["p2", "P2", "false"],
        ["p3", "P3", "false"],
        ["note", "Note", "false"],
    ]
    body = _calls(result, "POST")[0]["body"]
    assert body["category"] == "copy"
    assert body["severity"] == "p1"


# --------------------------------------------------------------------------
# Review posture: arming, anchors, the note card (#1854)
# --------------------------------------------------------------------------


def test_no_review_meta_means_no_review_posture(tmp_path: Path) -> None:
    scenario = dict(
        _PAGE,
        meta=_IDENTITY,
        ops=[{"op": "key", "key": "r", "alt": True, "shift": True, "name": "chord"}],
    )
    result = _run(tmp_path, scenario)
    assert result["initial"]["pointButton"] is False
    assert result["snapshots"]["chord"]["armed"] is False
    assert not [c for c in result["final"]["calls"] if "page_url=" in c["url"]]


def test_review_chord_arms_and_escape_disarms(tmp_path: Path) -> None:
    scenario = dict(
        _PAGE,
        meta=_REVIEW,
        ops=[
            {"op": "key", "key": "r", "alt": True, "shift": True, "name": "armed"},
            {"op": "hover", "at": "#done"},
            {"op": "snapshot", "name": "hovered"},
            {"op": "key", "key": "Escape", "name": "disarmed"},
            {"op": "call", "name": "open"},
            {"op": "click", "at": ".dz-feedback-ghost", "name": "pointed"},
        ],
    )
    result = _run(tmp_path, scenario)
    assert result["initial"]["pointButton"] is True
    armed = result["snapshots"]["armed"]
    assert armed["armed"] is True and armed["prevented"] is True and armed["cursor"] == "crosshair"
    hovered = result["snapshots"]["hovered"]["outline"]
    assert hovered == {
        "visible": True,
        "label": "tasks/open_tasks/7/complete",
        "left": "100px",
        "top": "200px",
    }
    disarmed = result["snapshots"]["disarmed"]
    assert (
        disarmed["armed"] is False
        and disarmed["cursor"] == ""
        and disarmed["outline"]["visible"] is False
    )
    # "Point at it" in the panel closes the panel and arms.
    pointed = result["snapshots"]["pointed"]
    assert pointed["armed"] is True and pointed["panel"]["open"] is False


def test_review_chord_accepts_either_separator(tmp_path: Path) -> None:
    """The DSL lexer has no `+`, so the meta may say `alt-shift-r`."""
    for spec in ("alt-shift-r", "alt+shift+r"):
        result = _run(
            tmp_path,
            dict(
                _PAGE,
                meta=dict(_REVIEW, **{"dz-feedback-review-shortcut": spec}),
                ops=[{"op": "key", "key": "r", "alt": True, "shift": True, "name": "chord"}],
            ),
        )
        assert result["snapshots"]["chord"]["armed"] is True, spec


def test_review_shortcut_none_and_bare_key_rule(tmp_path: Path) -> None:
    off = _run(
        tmp_path,
        dict(
            _PAGE,
            meta=dict(_REVIEW, **{"dz-feedback-review-shortcut": "none"}),
            ops=[{"op": "key", "key": "r", "alt": True, "shift": True, "name": "chord"}],
        ),
    )
    assert off["snapshots"]["chord"]["armed"] is False
    bare = _run(
        tmp_path,
        dict(
            _PAGE,
            meta=dict(_REVIEW, **{"dz-feedback-review-shortcut": "r"}),
            ops=[
                {"op": "key", "key": "r", "on": "input", "name": "typing"},
                {"op": "key", "key": "r", "name": "free"},
            ],
        ),
    )
    assert bare["snapshots"]["typing"]["armed"] is False
    assert bare["snapshots"]["free"]["armed"] is True


def test_armed_click_is_captured_and_opens_the_card(tmp_path: Path) -> None:
    result = _review_note(tmp_path, [{"op": "snapshot", "name": "typed"}])
    clicked = result["snapshots"]["clicked"]
    assert clicked["prevented"] is True
    assert clicked["pageClicks"] == []  # htmx / the page never saw it
    assert clicked["armed"] is False
    card = clicked["card"]
    assert card["open"] is True and card["inert"] is False and card["ariaHidden"] is None
    assert card["focus"] == "dz-feedback-description"  # the note textarea, autofocused
    assert card["path"] == "tasks/open_tasks/7/complete"
    assert card["category"] == "ux"
    assert card["severity"] == "minor"
    assert card["shotCheck"] is False
    assert clicked["outline"]["visible"] is True


def test_enter_saves_the_note_with_anchor_and_context(tmp_path: Path) -> None:
    result = _review_note(
        tmp_path,
        [
            {"op": "key", "key": "Enter", "on": "note", "shift": True, "name": "newline"},
            {"op": "key", "key": "Enter", "on": "note", "name": "saved"},
            {"op": "settle"},
        ],
        sessionStorage={"dz_feedback_session": "2026-10-25-ab12"},
    )
    assert result["snapshots"]["newline"]["card"]["open"] is True
    assert result["snapshots"]["newline"]["prevented"] is False
    saved = result["snapshots"]["saved"]
    assert saved["prevented"] is True
    assert saved["card"]["open"] is False and saved["card"]["inert"] is True
    assert saved["focus"] == "BUTTON"  # back on the clicked element
    posts = _calls(result, "POST")
    assert len(posts) == 1
    body = posts[0]["body"]
    assert posts[0]["headers"]["Idempotency-Key"] == body["idempotency_key"]
    assert body["category"] == "ux" and body["severity"] == "minor"
    assert body["description"] == "Button label is unclear"
    assert body["page_url"] == "http://app.test/app/tasks"
    assert body["surface"] == "tasks"
    assert body["review_session"] == "2026-10-25-ab12"
    anchor = body["anchor"]
    assert anchor["dz_anchor"] == "tasks/open_tasks/7/complete"
    assert isinstance(anchor["css"], str) and anchor["css"]
    assert anchor["text_quote"] == {
        "exact": "Complete",
        "prefix": "Write the report ",
        "suffix": "",
    }
    assert anchor["rect"] == {"x": 100, "y": 200, "w": 80, "h": 24}
    assert anchor["scroll"] == {"x": 0, "y": 0}
    assert anchor["viewport"] == [1280, 800]
    assert anchor["tag"] == "button" and anchor["role"] is None
    ctx = body["context"]
    assert ctx["url"] == "http://app.test/app/tasks?x=1#top"
    assert (ctx["surface"], ctx["entity"], ctx["record"], ctx["workspace"], ctx["persona"]) == (
        "tasks",
        "Task",
        "t-7",
        "ops",
        "teacher",
    )
    assert ctx["viewport"] == [1280, 800] and ctx["dpr"] == 2 and ctx["lang"] == "en-GB"
    assert ctx["review_session"] == "2026-10-25-ab12"
    assert ctx["htmx_history"] == [] and ctx["console_errors"] == []
    assert result["final"]["toastText"] == "Note saved."
    assert result["final"]["queue"] == {}


def test_escape_cancels_the_card_and_returns_focus(tmp_path: Path) -> None:
    result = _review_note(
        tmp_path, [{"op": "key", "key": "Escape", "on": "note", "name": "cancelled"}]
    )
    cancelled = result["snapshots"]["cancelled"]
    assert cancelled["card"]["open"] is False and cancelled["card"]["inert"] is True
    assert cancelled["focus"] == "BUTTON"
    assert _calls(result, "POST") == []


def test_field_and_region_anchor_shapes(tmp_path: Path) -> None:
    """A form field anchors by its label's `for`; a bare paragraph has no path."""
    scenario = dict(
        _PAGE,
        meta=_REVIEW,
        ops=[
            {"op": "call", "name": "arm"},
            {"op": "click", "at": "#title", "name": "field"},
            {"op": "key", "key": "Escape", "on": "note"},
            {"op": "call", "name": "arm"},
            {"op": "click", "at": "#intro", "name": "para"},
        ],
    )
    result = _run(tmp_path, scenario)
    assert result["snapshots"]["field"]["card"]["path"] == "tasks/title"
    assert result["snapshots"]["field"]["outline"]["label"] == "tasks/title"
    assert result["snapshots"]["para"]["outline"]["label"] == "p"
    para_path = result["snapshots"]["para"]["card"]["path"]
    assert para_path != "" and "/" not in para_path  # the css selector stands in


def test_session_id_is_minted_per_tab(tmp_path: Path) -> None:
    result = _review_note(tmp_path, [{"op": "key", "key": "Enter", "on": "note"}, {"op": "settle"}])
    session = _calls(result, "POST")[0]["body"]["review_session"]
    assert len(session) == 15 and session[4] == session[7] == session[10] == "-"


def test_context_captures_htmx_history_and_console_errors(tmp_path: Path) -> None:
    result = _review_note(
        tmp_path,
        [
            {"op": "htmx", "method": "get", "url": "/tasks?page=2", "status": 200},
            {
                "op": "htmx",
                "method": "post",
                "url": "http://app.test/tasks/7/complete",
                "status": 500,
            },
            {"op": "error", "message": "x is not defined"},
            {"op": "consoleError", "message": "boom"},
            {"op": "key", "key": "Enter", "on": "note"},
            {"op": "settle"},
        ],
    )
    body = _calls(result, "POST")[0]["body"]
    history = body["context"]["htmx_history"]
    assert [(h["method"], h["path"], h["status"]) for h in history] == [
        ("GET", "/tasks", 200),
        ("POST", "/tasks/7/complete", 500),
    ]
    assert all(isinstance(h["ms"], int) for h in history)
    errors = body["context"]["console_errors"]
    assert errors == [
        "htmx 500 /tasks/7/complete",
        "x is not defined at app.js:7",
        'console.error: boom {"code":7}',
    ]
    assert body["console_errors"] == "\n".join(errors)


# --------------------------------------------------------------------------
# Queue and idempotent replay (#1854)
# --------------------------------------------------------------------------


def test_unsent_note_is_queued_and_replayed_under_the_same_key(tmp_path: Path) -> None:
    first = _review_note(
        tmp_path,
        [{"op": "key", "key": "Enter", "on": "note"}, {"op": "settle"}],
        fetch=[{"method": "POST", "fail": True}],
    )
    assert first["final"]["toastText"] == "Note saved offline — will retry."
    queue = first["final"]["queue"]
    (key,) = queue
    assert queue[key]["payload"]["idempotency_key"] == key
    assert queue[key]["payload"]["description"] == "Button label is unclear"
    # Next page load: the queued note is POSTed again with the same key and,
    # once the server answers 200 (a replay of a landed key), dropped.
    second = _run(
        tmp_path,
        dict(
            _PAGE,
            meta=_REVIEW,
            localStorage={"dz_feedback_pending": json.dumps(queue)},
            fetch=[{"method": "POST", "status": 200, "body": {"id": "r9"}}],
        ),
    )
    posts = _calls(second, "POST")
    assert len(posts) == 1
    assert posts[0]["headers"]["Idempotency-Key"] == key
    assert posts[0]["body"]["idempotency_key"] == key
    assert second["final"]["queue"] == {}


@pytest.mark.parametrize(
    ("status", "kept"), [(409, True), (429, True), (503, True), (422, False), (401, False)]
)
def test_server_status_decides_whether_the_note_stays_queued(
    tmp_path: Path, status: int, kept: bool
) -> None:
    result = _review_note(
        tmp_path,
        [{"op": "key", "key": "Enter", "on": "note"}, {"op": "settle"}],
        fetch=[{"method": "POST", "status": status, "body": {"detail": "no"}}],
    )
    assert (result["final"]["queue"] != {}) is kept
    toast = result["final"]["toastText"]
    assert ("will retry" in toast) is kept
    if not kept:
        assert f"HTTP {status}" in toast


def test_stale_queue_entries_are_dropped(tmp_path: Path) -> None:
    stale = {"old": {"payload": {"idempotency_key": "old"}, "ts": 1}}
    result = _run(
        tmp_path, {"meta": _IDENTITY, "localStorage": {"dz_feedback_pending": json.dumps(stale)}}
    )
    assert _calls(result, "POST") == []
    assert result["final"]["queue"] == {}


# --------------------------------------------------------------------------
# Pins (#1854)
# --------------------------------------------------------------------------

_PINS = [
    {
        "id": "a",
        "status": "new",
        "created_at": "2026-10-25T09:00:00",
        "description": "Label unclear",
        "severity": "minor",
        "category": "ux",
        "reported_by": "ada@example.test",
        "anchor": {
            "dz_anchor": "tasks/open_tasks/7/complete",
            "css": "#nope",
            "rect": {"x": 0, "y": 0, "w": 0, "h": 0},
        },
    },
    {
        "id": "b",
        "status": "triaged",
        "created_at": "2026-10-25T09:01:00",
        "description": "Field too narrow",
        "anchor": json.dumps(
            {
                "dz_anchor": "tasks/open_tasks/missing",
                "css": '[name="title"]',
                "rect": {"x": 0, "y": 0, "w": 0, "h": 0},
            }
        ),
    },
    {
        "id": "c",
        "status": "new",
        "created_at": "2026-10-25T09:02:00",
        "description": "Greeting is stale",
        "anchor": {
            "dz_anchor": None,
            "css": "#gone",
            "text_quote": {"exact": "Welcome back", "prefix": "", "suffix": ""},
            "tag": "p",
            "rect": {"x": 0, "y": 0, "w": 0, "h": 0},
        },
    },
    {
        "id": "d",
        "status": "new",
        "created_at": "2026-10-25T09:03:00",
        "description": "Old banner",
        "anchor": {
            "dz_anchor": "tasks/banner",
            "css": "#banner",
            "text_quote": {"exact": "Gone now", "prefix": "", "suffix": ""},
            "tag": "div",
            "rect": {"x": 500, "y": 40, "w": 200, "h": 30},
            "scroll": {"x": 0, "y": 120},
        },
    },
]


def test_pins_are_reanchored_in_order_and_orphaned_at_rect(tmp_path: Path) -> None:
    result = _run(tmp_path, dict(_PAGE, meta=_REVIEW, pins=_PINS))
    listing = [
        c for c in result["final"]["calls"] if c["method"] == "GET" and "page_url=" in c["url"]
    ]
    assert (
        listing[0]["url"]
        == "/feedbackreports?page_url=http%3A%2F%2Fapp.test%2Fapp%2Ftasks&status=new,triaged"
    )
    pins = result["final"]["pins"]
    assert [(p["n"], p["id"], p["status"], p["orphaned"]) for p in pins] == [
        ("1", "a", "new", False),
        ("2", "b", "triaged", False),
        ("3", "c", "new", False),
        ("4", "d", "new", True),
    ]
    # dz_anchor → the Complete button (100,200,80x24); css → the title input
    # (10,300,200x30); text quote → the intro paragraph (10,10,100x20); the
    # orphan sits at its recorded rect, shifted by the scroll delta (y 40+120).
    assert [(p["left"], p["top"]) for p in pins] == [
        ("169px", "189px"),
        ("199px", "289px"),
        ("99px", "-1px"),
        ("689px", "149px"),
    ]
    assert pins[3]["label"] == "Review note 4 (element not found): Old banner"
    assert pins[0]["label"] == "Review note 1: Label unclear"


def test_pins_reload_after_settle_and_resolve_walks_the_transitions(tmp_path: Path) -> None:
    scenario = dict(
        _PAGE,
        meta=_REVIEW,
        pins=_PINS[:2],
        ops=[
            {"op": "click", "at": '[data-report-id="a"]', "name": "note"},
            {"op": "click", "at": ".dz-feedback-resolve"},
            {"op": "settle"},
            {"op": "snapshot", "name": "resolved"},
            {"op": "click", "at": '[data-report-id="b"]'},
            {"op": "click", "at": ".dz-feedback-resolve"},
            {"op": "settle"},
            {"op": "snapshot", "name": "resolved2"},
        ],
    )
    result = _run(tmp_path, scenario)
    note = result["snapshots"]["note"]["note"]
    assert note["open"] is True and note["title"] == "Review note 1"
    assert (
        note["meta"]
        == "Minor · Ux · ada@example.test · 2026-10-25 09:00 · tasks/open_tasks/7/complete"
    )
    puts = [(c["url"], c["body"]) for c in _calls(result, "PUT")]
    assert puts[:2] == [
        ("/feedbackreports/a", {"status": "triaged"}),
        ("/feedbackreports/a", {"status": "resolved"}),
    ]
    resolved = result["snapshots"]["resolved"]
    assert [p["id"] for p in resolved["pins"]] == ["b"] and resolved["pins"][0]["n"] == "1"
    assert resolved["toastText"] == "Note resolved."
    assert resolved["note"]["open"] is False
    # A triaged report needs only the second transition.
    assert puts[2:] == [("/feedbackreports/b", {"status": "resolved"})]
    assert result["snapshots"]["resolved2"]["pins"] == []


def test_orphaned_note_shows_the_quote(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        dict(
            _PAGE,
            meta=_REVIEW,
            pins=_PINS[3:],
            ops=[{"op": "click", "at": ".dz-feedback-pin", "name": "note"}],
        ),
    )
    note = result["snapshots"]["note"]["note"]
    assert note["title"] == "Review note 1 — element not found"
    assert note["meta"].endswith("was: “Gone now”")


# --------------------------------------------------------------------------
# Screenshot gating, size cap, budget (#1854)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("policy", "navigator", "expected"),
    [
        ("optional", {"mediaDevices": {"getDisplayMedia": True}}, True),
        ("optional", {}, False),
        ("off", {"mediaDevices": {"getDisplayMedia": True}}, False),
        (None, {"mediaDevices": {"getDisplayMedia": True}}, False),
        (
            "optional",
            {"mediaDevices": {"getDisplayMedia": True}, "userAgent": "Mozilla/5.0 (iPhone) Mobile"},
            False,
        ),
    ],
)
def test_screenshot_control_only_under_optional_policy(
    tmp_path: Path, policy: str | None, navigator: dict[str, Any], expected: bool
) -> None:
    meta = dict(_REVIEW)
    if policy is not None:
        meta["dz-feedback-screenshot"] = policy
    scenario = dict(
        _PAGE,
        meta=meta,
        navigator=navigator,
        ops=[{"op": "call", "name": "arm"}, {"op": "click", "at": "#done", "name": "card"}],
    )
    result = _run(tmp_path, scenario)
    assert result["snapshots"]["card"]["card"]["shotCheck"] is expected


def test_description_and_context_respect_the_server_caps(tmp_path: Path) -> None:
    """description ≤ 4000; anchor + context + page_snapshot + console_errors ≤ 32 KB."""
    ops: list[dict[str, Any]] = [{"op": "consoleError", "message": "e" * 600} for _ in range(25)]
    ops += [
        {"op": "type", "text": "x" * 5000},
        {"op": "key", "key": "Enter", "on": "note"},
        {"op": "settle"},
    ]
    result = _review_note(tmp_path, ops)
    body = _calls(result, "POST")[0]["body"]
    assert len(body["description"]) == 4000
    assert len(body["context"]["console_errors"]) <= 20
    assert all(len(e) <= 500 for e in body["context"]["console_errors"])
    four = [body["anchor"], body["context"], body["page_snapshot"], body["console_errors"]]
    assert len(json.dumps(four)) <= 32 * 1024
    assert len(json.dumps(body)) < 60 * 1024


def test_widget_fits_the_size_budget() -> None:
    """The file carries the stylesheet and the vendored finder."""
    size = len(gzip.compress(WIDGET_JS.read_bytes(), 9))
    assert size <= 17 * 1024, f"feedback-widget.js is {size} B gzipped"
