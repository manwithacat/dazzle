#!/usr/bin/env python3
"""Build the HaTchi-MaXchi static site — the extraction seed.

Produces a fully self-contained `hatchi-maxchi/` directory (relative asset
paths, fonts copied, mock-htmx shim so interactive components work with no
server). `cp -r hatchi-maxchi/ ../new-repo/` and serve it on GitHub Pages
as-is — that is the spin-out.

The gallery renders each registry component live AND shows its HTML as the
copy-paste snippet from the SAME string, so the docs cannot drift from the
demo (the shadcn ownership model, hypermedia-native).

Usage: python packages/hatchi-maxchi/site/build_site.py
"""

import argparse
import html as _html
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from build import (  # noqa: E402  (package build.py)
    DEFAULT_PREFIX,
    FONT_DIR,
    apply_prefix,
    build_css,
    build_js,
)
from hyperpart import anatomy  # noqa: E402  (package tools/hyperpart.py)
from icons import ICONS, LUCIDE_VERSION, lucide_svg_html  # noqa: E402
from icons.sprite import build_symbol_sheet, sprite_use_html  # noqa: E402
from pretty import pretty_html  # noqa: E402
from registry import GROUPS, HYPERPARTS  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]

_ICON_RE = re.compile(r"\{icon:([a-z0-9-]+)\}")
_SVG_RE = re.compile(r"\{svg:([a-z0-9-]+)\}")


def _exchanges_html(hyperpart) -> str:  # type: ignore[no-untyped-def]
    """Render a Hyperpart's hypermedia exchange contracts — the "endpoint
    response contract" half a server must satisfy for the partial to work."""
    if not hyperpart.exchanges:
        return ""
    rows = []
    for e in hyperpart.exchanges:
        states = " ".join(f"<code>{_html.escape(s)}</code>" for s in e.states) if e.states else "—"
        rows.append(
            "<tr>"
            f'<td><code class="hm-verb">{_html.escape(e.method)}</code> '
            f"<code>{_html.escape(e.endpoint)}</code></td>"
            f"<td>{_html.escape(e.trigger)}</td>"
            f"<td>{_html.escape(e.response)}</td>"
            f"<td>{_html.escape(e.swap)}</td>"
            f"<td>{states}</td>"
            "</tr>"
        )
    return (
        '<details class="hm-contract"><summary>Endpoint contract</summary>'
        '<table class="hm-contract-table"><thead><tr>'
        "<th>Request</th><th>Trigger</th><th>Response fragment</th><th>Swap</th><th>States</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        "<p>The partial above is only half the Hyperpart; the server must "
        "satisfy this contract for it to work. In Dazzle the response is "
        "rendered automatically — for any other htmx app, return matching "
        "markup from your endpoint.</p></details>"
    )


def _anatomy_html(hyperpart) -> str:  # type: ignore[no-untyped-def]
    """A one-line 'this Hyperpart is one unit spread across N files' note,
    for the interactive Hyperparts where the code is genuinely scattered."""
    if not hyperpart.controller:
        return ""
    a = anatomy(hyperpart.id)
    parts = ["<code>site/registry.py</code>"]
    parts += [f"<code>{_html.escape(s)}</code>" for s in a["styles"]]
    parts.append(f"<code>{_html.escape(a['controller'])}</code>")
    if a["mock"]:
        parts.append(f"mock <code>{_html.escape(a['mock'])}</code>")
    return (
        '<p class="hm-anatomy"><strong>One Hyperpart, {n} code items:</strong> '
        "{parts}. Distributed by the build (CSS layered, JS bundled) but "
        "bound by <code>HYPERPART: {id}</code> markers — <code>python "
        "tools/hyperpart.py {id}</code> lists them.</p>"
    ).format(n=len(parts) + 1, parts=" · ".join(parts), id=_html.escape(hyperpart.id))


# A copied sprite snippet is blank without the icon sheet — surface the
# dependency IN the snippet so it travels with a paste (the README note does
# not). Prepended once to any partial that uses the sprite `<use>` form.
_SPRITE_NOTE = "<!-- icons: include the icon sheet once per page (see Setup) -->\n"


_BY_ID = {h.id: h for h in HYPERPARTS}


def _own_classes(hyperpart) -> list[str]:  # type: ignore[no-untyped-def]
    """A single Hyperpart's own dependency classes (not its children's)."""
    deps: list[str] = []
    if "{svg:" in hyperpart.partial or "{icon:" in hyperpart.partial:
        deps.append("Sprite")
    if hyperpart.controller:
        deps.append("Controller")
    if hyperpart.exchanges:
        deps.append("Endpoint")
    return deps


def _dependency_classes(hyperpart) -> list[str]:  # type: ignore[no-untyped-def]
    """The hidden-contract dependency classes a consumer must preserve when
    copying a component (agent-review taxonomy). A composite is `Composite`
    plus the UNION of its own and its children's classes (one level) — so a
    reader sees a composite inherits the sheet/endpoint/controller needs of
    what it embeds. A component with nothing is a Primitive."""
    deps = _own_classes(hyperpart)
    if hyperpart.composes:
        for cid in hyperpart.composes:
            child = _BY_ID.get(cid)
            if child:
                deps += _own_classes(child)
        deps = ["Composite", *deps]
    return list(dict.fromkeys(deps)) or ["Primitive"]


def _composed_of_html(hyperpart) -> str:  # type: ignore[no-untyped-def]
    """A 'Composed of: X · Y' note linking a composite to the child Hyperparts
    it embeds — the composition made visible."""
    if not hyperpart.composes:
        return ""
    links = []
    for cid in hyperpart.composes:
        child = _BY_ID.get(cid)
        title = child.title if child else cid
        links.append(f'<a href="#{cid}">{_html.escape(title)}</a>')
    return f'<p class="hm-composed"><strong>Composed of:</strong> {" · ".join(links)}</p>'


def _dependency_chips(hyperpart) -> str:  # type: ignore[no-untyped-def]
    return "".join(
        f'<span class="hm-dep" data-dep="{d.lower()}" title="Dependency class: {d}">{d}</span>'
        for d in _dependency_classes(hyperpart)
    )


def _require(name: str) -> str:
    """Fail the build loud on an unknown icon token — a typo'd ``{svg:...}``
    should not silently render the fallback and slip into the gallery."""
    if name not in ICONS:
        raise ValueError(f"unknown icon token '{name}' — add it via icons/gen_registry.py")
    return name


def expand_icons(markup: str) -> str:
    """Expand ``{icon:name}`` / ``{svg:name}`` tokens to the sprite ``<use>``
    form — one short line that references the injected symbol sheet. Source
    classes stay ``dz-``-prefixed; the caller's ``apply_prefix`` strips them
    for the (unprefixed) gallery. The demo renders because the page carries
    the sheet; the copied snippet reads as canonical ``<use>`` markup."""
    markup = _ICON_RE.sub(
        lambda m: sprite_use_html(_require(m.group(1)), cls="dz-icon dz-icon--size-sm"), markup
    )
    markup = _SVG_RE.sub(lambda m: sprite_use_html(_require(m.group(1)), cls="dz-icon"), markup)
    return markup


MOCK_HTMX = """/* Minimal htmx4 mock — enough for the static gallery demos.
   Supports: hx-get (canned responses), hx-confirm -> htmx:confirm event,
   hx-boost no-op. NOT a real htmx; the point is that the SAME markup that
   runs against a Dazzle server also demos statically here. */
(function () {
  "use strict";
  var RESPONSES = {
    "/mock/command": '<div class="dz-command__group">Workspaces</div>' +
      '<a class="dz-command__item" href="#" role="option">{i:layout-dashboard}<span>Operations Dashboard</span></a>' +
      '<a class="dz-command__item" href="#" role="option">{i:settings}<span>Platform Admin</span></a>' +
      '<div class="dz-command__group">Records</div>' +
      '<a class="dz-command__item" href="#" role="option">{i:receipt}<span>Invoices</span></a>' +
      '<a class="dz-command__item" href="#" role="option">{i:users}<span>Customers</span></a>' +
      '<a class="dz-command__item" href="#" role="option">{i:triangle-alert}<span>Alerts</span></a>',
    "/mock/master-detail/inv-001": '<div class="dz-card dz-card-body"><div class="dz-card-label">INV-001 · Acme</div><div class="dz-card-value">£1,250.00</div><div class="dz-card-delta">Paid · 2 days ago</div></div>',
    "/mock/master-detail/inv-002": '<div class="dz-card dz-card-body"><div class="dz-card-label">INV-002 · Globex</div><div class="dz-card-value">£3,400.00</div><div class="dz-card-delta">Pending · due Friday</div></div>',
    "/mock/master-detail/inv-003": '<div class="dz-card dz-card-body"><div class="dz-card-label">INV-003 · Initech</div><div class="dz-card-value">£820.00</div><div class="dz-card-delta">Overdue · 6 days</div></div>',
    "/mock/pagination/2": '<div class="hm-pag-row">INV-004 · Umbrella</div><div class="hm-pag-row">INV-005 · Stark</div><div class="hm-pag-row">INV-006 · Wonka</div>',
    "/mock/pagination/3": '<div class="hm-pag-row">INV-007 · Tyrell</div><div class="hm-pag-row">INV-008 · Cyberdyne</div><div class="hm-pag-row">INV-009 · Soylent</div>',
    "/mock/pagination/9": '<div class="hm-pag-row">INV-025 · Hooli</div><div class="hm-pag-row">INV-026 · Pied Piper</div><div class="hm-pag-row">INV-027 · Aviato</div>',
    "/mock/tabs/activity": '<p class="hm-demo-muted">3 events today — INV-004 paid, INV-005 sent, a comment added.</p>',
    "/mock/tabs/settings": '<p class="hm-demo-muted">Notifications, access, and billing preferences live here.</p>'
  };
  // icon placeholders resolved from a tiny inline map (built by the site gen)
  function icon(name) { return window.__HM_ICONS__ ? (window.__HM_ICONS__[name] || "") : ""; }
  function expand(h) { return h.replace(/\\{i:([a-z0-9-]+)\\}/g, function (_, n) {
    return '<span class="dz-icon dz-icon--size-sm">' + icon(n) + '</span>'; }); }

  function fire(el, name, detail) {
    var evt = new CustomEvent(name, { bubbles: true, cancelable: true, detail: detail });
    el.dispatchEvent(evt);
    return evt;
  }

  function doGet(el) {
    var url = el.getAttribute("hx-get");
    var body = expand(RESPONSES[url] || '<div class="dz-command__empty">No results.</div>');
    var sel = el.getAttribute("hx-target");
    var target = null;
    if (sel && sel.indexOf("next ") === 0) {
      var cls = sel.slice(5).trim();
      // htmx `next <sel>` = the first element matching sel that appears
      // AFTER el in document order (not just the immediate sibling). This
      // matches real htmx and frees the markup to wrap the input.
      var all = document.querySelectorAll(cls);
      for (var i = 0; i < all.length; i++) {
        if (el.compareDocumentPosition(all[i]) & Node.DOCUMENT_POSITION_FOLLOWING) {
          target = all[i];
          break;
        }
      }
    } else if (sel) {
      // plain selector (e.g. an id `#region-body`, as pagination + most real
      // htmx targets use) — resolve like htmx's default querySelector.
      target = document.querySelector(sel);
    } else {
      // no hx-target → the element swaps its own content (htmx default), as
      // the lazy tab panels do.
      target = el;
    }
    if (target) {
      target.innerHTML = body;
      fire(target, "htmx:afterSwap", { elt: target });
    }
  }

  // hx-get on focus/input — INPUTS only (e.g. the command palette's
  // `focus once`). Non-input `[hx-get]` affordances (links/buttons) fire on
  // click below, matching real htmx's default trigger for those elements.
  document.addEventListener("focus", function (e) {
    if (e.target.matches && e.target.matches("input[hx-get]")) doGet(e.target);
  }, true);
  document.addEventListener("input", function (e) {
    if (e.target.matches && e.target.matches("[hx-get]")) doGet(e.target);
  });
  // hx-get on click (non-input affordances, e.g. master-detail list links)
  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest("[hx-get]");
    if (!el || el.matches("input")) return;
    e.preventDefault();
    doGet(el);
  });

  // hx-confirm -> htmx:confirm (drives dz-confirm.js).
  // Fires the REAL htmx-4 event shape: the config lives under `detail.ctx`
  // (sourceElement + confirm), and the request is issued/dropped via the two
  // functions on `detail`. (Earlier this mock fired the htmx-2 shape
  // {elt, question} — which no real htmx-4 consumer sees, so it silently
  // masked the htmx-4 detail-shape break in dz-confirm.js.)
  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest("[hx-confirm]");
    if (!el) return;
    e.preventDefault();
    var issued = false;
    fire(el, "htmx:confirm", {
      ctx: { sourceElement: el, confirm: el.getAttribute("hx-confirm") },
      issueRequest: function () {
        issued = true;
        // demo: flash a toast-ish confirmation
        var note = document.createElement("div");
        note.className = "hm-toast";
        note.textContent = "Deleted (demo).";
        document.body.appendChild(note);
        setTimeout(function () { note.remove(); }, 1800);
      },
      dropRequest: function () { issued = false; }
    });
  });

  // intersect-once: a lazy panel (hx-trigger contains "intersect") loads the
  // first time it becomes visible — the tab controller reveals a hidden panel,
  // which then intersects. Mirrors real htmx's `intersect once` trigger.
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { io.unobserve(e.target); doGet(e.target); }
      });
    });
    var observeLazy = function () {
      var els = document.querySelectorAll("[hx-get][hx-trigger]");
      for (var i = 0; i < els.length; i++) {
        if ((els[i].getAttribute("hx-trigger") || "").indexOf("intersect") >= 0) io.observe(els[i]);
      }
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", observeLazy);
    else observeLazy();
  }

  window.htmx = { version: "mock-4" };
})();
"""

PAGE_CSS = """
/* color-scheme comes from the bundle (tokens.css advertises `light dark`
   on :root and binds [data-theme] to it) — declaring it again here would
   override the [data-theme="dark"] flip at equal specificity, later in
   document order, and kill the theme toggle. */
body { background: var(--colour-bg); color: var(--colour-text);
  font-family: var(--font-sans); margin: 0; }
.hm-wrap { display: grid; grid-template-columns: 15rem 1fr; min-height: 100vh; }
.hm-nav { position: sticky; top: 0; align-self: start; height: 100vh; overflow-y: auto;
  border-inline-end: 1px solid var(--colour-border); padding: 1.5rem 1rem; }
.hm-brand { font-weight: var(--weight-bold); font-size: 1.1rem; letter-spacing: -.01em; }
.hm-brand small { display:block; font-weight: var(--weight-regular); color: var(--colour-text-muted);
  font-size: .7rem; margin-top: .25rem; }
.hm-nav-group { font-size: .7rem; text-transform: uppercase; letter-spacing: .08em;
  color: var(--colour-text-muted); margin: 1.25rem 0 .375rem; }
.hm-nav a { display:block; padding: .25rem .5rem; border-radius: var(--radius-sm);
  color: var(--colour-text); text-decoration: none; font-size: var(--text-sm); }
.hm-nav a:hover { background: var(--colour-bg); color: var(--colour-brand); }
.hm-main { padding: 3rem 4rem; max-width: 60rem; }
.hm-hero h1 { font-size: 2.75rem; letter-spacing: -.02em; margin: 0 0 .25rem; }
.hm-hero p { color: var(--colour-text-muted); margin: 0 0 1rem; max-width: 40rem; }
.hm-theme-toggle { margin-left: auto; }
.hm-topbar { display:flex; align-items:center; gap:1rem; margin-bottom: 2rem; }
.hm-comp { border-block-start: 1px solid var(--colour-border); padding-block: 2.5rem; }
.hm-comp h2 { font-size: 1.25rem; margin: 0 0 .25rem; scroll-margin-top: 1rem; }
.hm-comp .blurb { color: var(--colour-text-muted); margin: 0 0 1.25rem; font-size: var(--text-sm); }
.hm-preview { padding: 2rem; border: 1px solid var(--colour-border);
  border-radius: var(--radius-md); background: var(--colour-surface); margin-bottom: .75rem; }
.hm-demo-row { display:flex; gap: 1rem; align-items:center; flex-wrap: wrap; }
.hm-grow { flex: 1 1 0; min-width: 0; }
.hm-pag-list { border: 1px solid var(--colour-border); border-radius: var(--radius-md); overflow: hidden; }
.hm-pag-row { padding: .6rem .9rem; font-size: var(--text-sm); }
.hm-pag-row + .hm-pag-row { border-block-start: 1px solid var(--colour-border); }
.hm-inline { display:inline-flex; align-items:center; gap: .5rem; font-size: var(--text-sm); }
.hm-code { position: relative; }
.hm-code pre { margin: 0; padding: 1rem 4rem 1rem 1.25rem; overflow-x: auto;
  background: var(--neutral-900); color: var(--neutral-100); border-radius: var(--radius-md);
  font-family: var(--font-mono); font-size: .75rem; line-height: 1.6; }
.hm-copy { position: absolute; top: .5rem; right: .5rem; display: inline-flex; align-items: center;
  background: var(--neutral-800); color: var(--neutral-100); border: 1px solid var(--neutral-700);
  border-radius: var(--radius-sm); padding: .3rem .65rem; font-size: .75rem;
  font-family: var(--font-sans); font-weight: var(--weight-medium); cursor: pointer;
  transition: background 120ms var(--ease-default, ease); }
.hm-copy:hover { background: var(--neutral-700); }
.hm-copy:active { background: var(--neutral-600); }
.hm-copy:focus-visible { outline: var(--focus-ring-width) solid var(--focus-ring-color);
  outline-offset: var(--focus-ring-offset); }
.hm-copy svg { width: .875rem; height: .875rem; }
.hm-copy__idle, .hm-copy__done { display: inline-flex; align-items: center; gap: .4rem; }
.hm-copy__done { display: none; color: var(--success-500); }
.hm-copy[data-copied] .hm-copy__idle { display: none; }
.hm-copy[data-copied] .hm-copy__done { display: inline-flex; }
.hm-anatomy { font-size: .75rem; color: var(--colour-text-muted); margin-top: .6rem;
  padding: .5rem .7rem; border-left: 2px solid var(--colour-brand); background: var(--colour-brand-soft);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0; }
.hm-anatomy code { font-family: var(--font-mono); font-size: .9em; }
.hm-notes { font-size: var(--text-sm); color: var(--colour-text-muted); margin-top: .75rem; }
.hm-notes code { background: var(--colour-bg); padding: .05rem .3rem; border-radius: var(--radius-sm); }
.hm-contract { margin-top: .75rem; border: 1px solid var(--colour-border);
  border-radius: var(--radius-md); background: var(--colour-brand-soft); }
.hm-contract > summary { cursor: pointer; padding: .5rem .75rem; font-size: var(--text-sm);
  font-weight: var(--weight-medium); color: var(--colour-brand-text); list-style-position: inside; }
.hm-contract-table { width: 100%; border-collapse: collapse; font-size: .75rem;
  background: var(--colour-surface); }
.hm-contract-table th, .hm-contract-table td { text-align: left; vertical-align: top;
  padding: .4rem .6rem; border-top: 1px solid var(--colour-border); }
.hm-contract-table th { color: var(--colour-text-muted); font-weight: var(--weight-medium);
  text-transform: uppercase; letter-spacing: .04em; font-size: .625rem; }
.hm-contract-table code { font-family: var(--font-mono); }
.hm-verb { color: var(--colour-brand-text); font-weight: var(--weight-semibold); }
.hm-contract > p { font-size: var(--text-sm); color: var(--colour-text-muted);
  margin: 0; padding: .6rem .75rem; }
.hm-toast { position: fixed; bottom: 1.5rem; left: 50%; transform: translateX(-50%);
  background: var(--colour-text); color: var(--colour-bg); padding: .5rem 1rem;
  border-radius: var(--radius-md); font-size: var(--text-sm); box-shadow: var(--shadow-lg); }
.hm-tag { display:inline-block; font-size: .625rem; text-transform: uppercase; letter-spacing: .05em;
  padding: .05rem .35rem; border-radius: var(--radius-full); margin-left: .5rem;
  background: var(--colour-brand-soft); color: var(--colour-brand-text); vertical-align: middle; }
/* Dependency-class chips — the hidden contract a copied component carries.
   Neutral by design: the text label distinguishes the class, not colour
   (WCAG 1.4.1) — and scheme-aware muted text keeps contrast in dark. */
.hm-dep { display:inline-block; font-size: .625rem; font-weight: var(--weight-medium);
  letter-spacing: .02em; padding: .05rem .4rem; border-radius: var(--radius-full);
  margin-left: .4rem; vertical-align: middle; border: 1px solid var(--colour-border);
  color: var(--colour-text-muted); background: var(--colour-surface); }
/* Demo-layout utilities (hm- = gallery scaffolding, NOT component contract —
   replace with your app's own layout when copying a snippet). */
.hm-measure { max-width: 22rem; }
.hm-measure-lg { max-width: 34rem; }
.hm-stack { display: flex; flex-direction: column; gap: .75rem; }
.hm-demo-title { font-weight: var(--weight-semibold); font-size: var(--text-sm); margin-bottom: .25rem; }
.hm-demo-muted { margin: 0; font-size: var(--text-sm); color: var(--colour-text-muted); }
.hm-hero-def { font-size: var(--text-sm); color: var(--colour-text-muted); max-width: 42rem; margin-top: .5rem; }
.hm-composed { font-size: var(--text-sm); color: var(--colour-text-muted); margin-top: .6rem; }
.hm-composed a { color: var(--colour-brand-text); text-decoration: underline; }
"""


def build(out_dir: Path, prefix: str = DEFAULT_PREFIX) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── assets (self-contained, relative paths) ──
    # CSS is the package's own design-system bundle (build.py), NOT the
    # full Dazzle bundle — the gallery styles exactly what it ships. The
    # published default is UNPREFIXED (clean `.button` etc.); the same
    # `prefix` is applied to CSS, JS, and the demo markup so the whole
    # gallery is internally consistent.
    fonts_out = out_dir / "fonts"
    fonts_out.mkdir(exist_ok=True)
    if fonts_out.resolve() != FONT_DIR.resolve():
        for f in FONT_DIR.iterdir():
            if f.is_file():
                shutil.copyfile(f, fonts_out / f.name)
    (out_dir / "hatchi-maxchi.css").write_text(build_css(prefix), encoding="utf-8")

    # controllers the demos need + the mock htmx. build_js already applied
    # the prefix to the controllers; the mock's canned markup carries the
    # namespace too, so reprefix it to match.
    controllers = "\n" + build_js(prefix)
    # inline icon map for the mock htmx canned command results
    icon_map = "window.__HM_ICONS__ = {"
    for name in ("layout-dashboard", "settings", "receipt", "users", "triangle-alert"):
        inner = ICONS[name].replace("'", "\\'")
        icon_map += (
            f'\'{name}\':\'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            f'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round">{inner}</svg>\','
        )
    icon_map += "};\n"
    (out_dir / "hatchi-maxchi.js").write_text(
        (apply_prefix(icon_map + MOCK_HTMX, prefix) + controllers).rstrip("\n") + "\n",
        encoding="utf-8",
    )

    # Icon symbol sheet — every `<use href="#name">` in the snippets/demos
    # references it. Shipped as a standalone file (a consumer inlines it once)
    # AND inlined into index.html below so the gallery renders self-contained.
    sheet = build_symbol_sheet(ICONS)
    (out_dir / "sprite_sheet.svg").write_text(sheet, encoding="utf-8")

    # ── gallery HTML ──
    nav_parts = [
        '<div class="hm-brand">HaTchi-MaXchi<small>htmx4-native design system</small></div>'
    ]
    body_parts = []
    for group in GROUPS:
        comps = [c for c in HYPERPARTS if c.group == group]
        if not comps:
            continue
        nav_parts.append(f'<div class="hm-nav-group">{group}</div>')
        for c in comps:
            nav_parts.append(f'<a href="#{c.id}">{_html.escape(c.title)}</a>')

    # Copy button: dedicated gallery chrome (NOT a data-dz-variant="ghost"
    # button — the
    # ghost hover wash is near-white in light scheme and fought the dark
    # code block), with icon feedback: clipboard -> check "Copied".
    copy_icon = lucide_svg_html("copy", cls="")
    check_icon = lucide_svg_html("check", cls="")
    copy_button = (
        '<button class="hm-copy" type="button" aria-label="Copy snippet to clipboard">'
        f'<span class="hm-copy__idle">{copy_icon}Copy</span>'
        f'<span class="hm-copy__done">{check_icon}Copied</span>'
        "</button>"
    )

    for c in HYPERPARTS:
        # Expand icon placeholders ONCE and use the SAME string for the
        # live demo and the snippet — so copied markup carries real
        # inline SVG (a {icon:...} placeholder in the snippet would be
        # dead text in a consumer's app), and demo/docs cannot drift.
        # The partial, its snippet, and the endpoint-contract prose are the
        # PUBLISHED markup a consumer copies — reprefix them. The anatomy
        # note is NOT reprefixed: it references source-tree filenames
        # (e.g. controllers/dz-command.js) and HYPERPART markers, which keep
        # the source form regardless of the published class namespace.
        live = apply_prefix(expand_icons(c.partial), prefix)
        # The live demo uses the compact one-line `live`; the SNIPPET is
        # pretty-printed so the structure is legible (render-faithful — see
        # site/pretty.py). Sprite-dependency note prepended to the snippet only.
        pretty = pretty_html(live)
        snippet_src = _SPRITE_NOTE + pretty if '<use href="#i-' in live else pretty
        snippet = _html.escape(snippet_src)
        tag = f'<span class="hm-tag">{c.tags[0]}</span>' if c.tags else ""
        deps = _dependency_chips(c)
        notes = f'<div class="hm-notes">{c.notes}</div>' if c.notes else ""
        body_parts.append(
            f'<section class="hm-comp" id="{c.id}">'
            f"<h2>{_html.escape(c.title)}{tag}{deps}</h2>"
            f'<p class="blurb">{_html.escape(c.blurb)}</p>'
            f'<div class="hm-preview">{live}</div>'
            f'<div class="hm-code">{copy_button}'
            f'<pre tabindex="0" role="region" aria-label="Code for {_html.escape(c.title)}">'
            f"<code>{snippet}</code></pre></div>"
            f"{apply_prefix(_exchanges_html(c), prefix)}"
            f"{_composed_of_html(c)}"
            f"{_anatomy_html(c)}"
            f"{notes}</section>"
        )

    theme_js = (
        "function hmTheme(t){document.documentElement.setAttribute('data-theme',t);"
        "localStorage.setItem('hm-theme',t);}"
        "(function(){var t=localStorage.getItem('hm-theme');if(t){"
        "document.documentElement.setAttribute('data-theme',t);"
        "document.addEventListener('DOMContentLoaded',function(){"
        "var r=document.querySelector('input[name=hm-theme][data-hm-theme='+t+']');"
        "if(r)r.checked=true;});}})();"
    )

    # opener references the published selectors (dialog.dz-command,
    # .dz-command__input) — reprefix to match the shipped namespace.
    opener_js = apply_prefix(
        "document.addEventListener('click',function(e){"
        "var b=e.target.closest('[data-hm-open-command]');if(!b)return;"
        "var dlg=document.querySelector('dialog.dz-command');"
        "if(dlg){dlg.showModal();var i=dlg.querySelector('.dz-command__input');if(i)i.focus();}});"
        # Copy-to-clipboard with icon feedback; blur() so no focus/hover
        # state lingers on the button after the click.
        "document.addEventListener('click',function(e){"
        "var b=e.target.closest('.hm-copy');if(!b)return;"
        "var code=b.parentElement.querySelector('code');"
        "navigator.clipboard.writeText(code.textContent).then(function(){"
        "b.setAttribute('data-copied','');b.blur();"
        "clearTimeout(b.__hmCopyTimer);"
        "b.__hmCopyTimer=setTimeout(function(){b.removeAttribute('data-copied');},1600);});});",
        prefix,
    )
    # `sheet` (built in the assets section) is inlined once per page so every
    # `<use href="#name">` resolves same-document (renders on file:// + Pages).
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HaTchi-MaXchi — htmx4-native design system</title>
<link rel="stylesheet" href="hatchi-maxchi.css">
<style>{PAGE_CSS}</style>
<script>{theme_js}</script>
</head>
<body>
{sheet}
<div class="hm-wrap">
<nav class="hm-nav">{"".join(nav_parts)}</nav>
<main class="hm-main">
<div class="hm-topbar">
  <div class="hm-hero">
    <h1>HaTchi-MaXchi</h1>
    <p>An htmx4-native design system. Server-rendered markup, one accent, dark as a
    material, and lifecycle-driven motion — the maturity of the modern component
    aesthetic without a client framework. Vendored Geist + Lucide {LUCIDE_VERSION}.</p>
    <p class="hm-hero-def"><strong>“htmx4-native”</strong> here means server-rendered
    htmx partials, no hydration, lifecycle-aware CSS/JS affordances, and endpoint
    contracts colocated with components — it is not an official htmx distribution.</p>
  </div>
  <div class="hm-theme-toggle">
    <div class="dz-toggle-group" role="radiogroup">
      <label><input type="radio" name="hm-theme" data-hm-theme="light" onclick="hmTheme('light')"><span>Light</span></label>
      <label><input type="radio" name="hm-theme" data-hm-theme="dark" onclick="hmTheme('dark')"><span>Dark</span></label>
    </div>
  </div>
</div>
{"".join(body_parts)}
<footer style="border-block-start:1px solid var(--colour-border);padding-block:2rem;color:var(--colour-text-muted);font-size:var(--text-sm)">
Generated from the design-system sources by <code>site/build_site.py</code>.
Every snippet is the live example — copy it into any htmx4 app.
</footer>
</main>
</div>
<script src="hatchi-maxchi.js" defer></script>
<script>{opener_js}</script>
</body>
</html>"""
    (out_dir / "index.html").write_text(doc + "\n", encoding="utf-8")

    (out_dir / "README.md").write_text(_readme(), encoding="utf-8")
    print(f"built {len(HYPERPARTS)} Hyperparts -> {out_dir}/index.html")


def _readme() -> str:
    return (
        "# HaTchi-MaXchi\n\n"
        "An **htmx4-native design system** — the maturity of the modern component\n"
        "aesthetic without a client framework. Server-rendered markup, semantic\n"
        "`dz-*` classes + `data-dz-*` modifiers, design tokens for all variation,\n"
        "and interactions built on the htmx request lifecycle.\n\n"
        "This directory is self-contained: `hatchi-maxchi.css`, `hatchi-maxchi.js`\n"
        "(behaviour controllers + a mock htmx for the static demos), vendored fonts,\n"
        "and `index.html` (the component gallery). Serve it on GitHub Pages as-is.\n\n"
        "## Use\n\n"
        "Two one-time includes — the stylesheet and the icon symbol sheet:\n\n"
        "```html\n"
        '<link rel="stylesheet" href="hatchi-maxchi.css">\n'
        '<script src="hatchi-maxchi.js" defer></script>\n'
        "\n"
        "<!-- inline the icon sheet ONCE per page (near the top of <body>) -->\n"
        '<!-- so every `<use href="#name">` in a snippet resolves -->\n'
        "<!-- (copy the contents of sprite_sheet.svg, or fetch + inline it) -->\n"
        "```\n\n"
        "Copy any component's HTML from the gallery. Icons appear as the sprite\n"
        'form `<svg class="icon"><use href="#name"/></svg>` — short and legible,\n'
        "but they render only when the icon sheet above is present on the page. (An\n"
        "icon inline-`<svg>` with the full path data is self-contained if you prefer\n"
        "no sheet dependency.) In a real app, swap the mock htmx for\n"
        "[htmx](https://htmx.org) and point the `hx-*` attributes at your endpoints\n"
        "(e.g. the command palette's `hx-get` at your search route).\n\n"
        "Generated from the [Dazzle](https://github.com/manwithacat/dazzle) source of\n"
        "truth by `scripts/hm_site/build_site.py`. Geist (OFL) and Lucide (ISC) are\n"
        "vendored; see `fonts/OFL.txt`.\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="packages/hatchi-maxchi/site")
    args = ap.parse_args()
    build(ROOT / args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
