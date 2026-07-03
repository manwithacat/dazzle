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

from build import FONT_DIR, build_css, build_js  # noqa: E402  (package build.py)
from registry import COMPONENTS, GROUPS  # noqa: E402

from dazzle.render.fragment.icon_html import lucide_icon_html, lucide_svg_html  # noqa: E402
from dazzle.render.fragment.icon_registry import ICONS, LUCIDE_VERSION  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]

_ICON_RE = re.compile(r"\{icon:([a-z0-9-]+)\}")
_SVG_RE = re.compile(r"\{svg:([a-z0-9-]+)\}")


def expand_icons(markup: str) -> str:
    markup = _ICON_RE.sub(
        lambda m: lucide_icon_html(m.group(1), cls="dz-icon dz-icon--size-sm"), markup
    )
    markup = _SVG_RE.sub(lambda m: lucide_svg_html(m.group(1), cls=""), markup)
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
      '<a class="dz-command__item" href="#" role="option">{i:triangle-alert}<span>Alerts</span></a>'
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
      var n = el.nextElementSibling;
      while (n && !n.matches(cls)) n = n.nextElementSibling;
      target = n;
    }
    if (target) {
      target.innerHTML = body;
      fire(target, "htmx:afterSwap", { elt: target });
    }
  }

  // hx-get on input/focus/change
  document.addEventListener("focus", function (e) {
    if (e.target.matches && e.target.matches("[hx-get]")) doGet(e.target);
  }, true);
  document.addEventListener("input", function (e) {
    if (e.target.matches && e.target.matches("[hx-get]")) doGet(e.target);
  });

  // hx-confirm -> htmx:confirm (drives dz-confirm.js)
  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest("[hx-confirm]");
    if (!el) return;
    e.preventDefault();
    fire(el, "htmx:confirm", {
      elt: el,
      question: el.getAttribute("hx-confirm"),
      issueRequest: function () {
        // demo: flash a toast-ish confirmation
        var note = document.createElement("div");
        note.className = "hm-toast";
        note.textContent = "Deleted (demo).";
        document.body.appendChild(note);
        setTimeout(function () { note.remove(); }, 1800);
      }
    });
  });

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
.hm-notes { font-size: var(--text-sm); color: var(--colour-text-muted); margin-top: .75rem; }
.hm-notes code { background: var(--colour-bg); padding: .05rem .3rem; border-radius: var(--radius-sm); }
.hm-toast { position: fixed; bottom: 1.5rem; left: 50%; transform: translateX(-50%);
  background: var(--colour-text); color: var(--colour-bg); padding: .5rem 1rem;
  border-radius: var(--radius-md); font-size: var(--text-sm); box-shadow: var(--shadow-lg); }
.hm-tag { display:inline-block; font-size: .625rem; text-transform: uppercase; letter-spacing: .05em;
  padding: .05rem .35rem; border-radius: var(--radius-full); margin-left: .5rem;
  background: var(--colour-brand-soft); color: var(--colour-brand); vertical-align: middle; }
"""


def build(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── assets (self-contained, relative paths) ──
    # CSS is the package's own design-system bundle (build.py), NOT the
    # full Dazzle bundle — the gallery styles exactly what it ships.
    fonts_out = out_dir / "fonts"
    fonts_out.mkdir(exist_ok=True)
    if fonts_out.resolve() != FONT_DIR.resolve():
        for f in FONT_DIR.iterdir():
            if f.is_file():
                shutil.copyfile(f, fonts_out / f.name)
    (out_dir / "hatchi-maxchi.css").write_text(build_css(), encoding="utf-8")

    # controllers the demos need + the mock htmx
    controllers = "\n" + build_js()
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
    (out_dir / "hatchi-maxchi.js").write_text(icon_map + MOCK_HTMX + controllers, encoding="utf-8")

    # ── gallery HTML ──
    nav_parts = [
        '<div class="hm-brand">HaTchi-MaXchi<small>htmx4-native design system</small></div>'
    ]
    body_parts = []
    for group in GROUPS:
        comps = [c for c in COMPONENTS if c.group == group]
        if not comps:
            continue
        nav_parts.append(f'<div class="hm-nav-group">{group}</div>')
        for c in comps:
            nav_parts.append(f'<a href="#{c.id}">{_html.escape(c.title)}</a>')

    # Copy button: dedicated gallery chrome (NOT dz-button-ghost — the
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

    for c in COMPONENTS:
        live = expand_icons(c.html)
        snippet = _html.escape(c.html)
        tag = f'<span class="hm-tag">{c.tags[0]}</span>' if c.tags else ""
        notes = f'<div class="hm-notes">{c.notes}</div>' if c.notes else ""
        body_parts.append(
            f'<section class="hm-comp" id="{c.id}">'
            f"<h2>{_html.escape(c.title)}{tag}</h2>"
            f'<p class="blurb">{_html.escape(c.blurb)}</p>'
            f'<div class="hm-preview">{live}</div>'
            f'<div class="hm-code">{copy_button}'
            f"<pre><code>{snippet}</code></pre></div>"
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

    opener_js = (
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
        "b.__hmCopyTimer=setTimeout(function(){b.removeAttribute('data-copied');},1600);});});"
    )
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
<div class="hm-wrap">
<nav class="hm-nav">{"".join(nav_parts)}</nav>
<main class="hm-main">
<div class="hm-topbar">
  <div class="hm-hero">
    <h1>HaTchi-MaXchi</h1>
    <p>An htmx4-native design system. Server-rendered markup, one accent, dark as a
    material, and lifecycle-driven motion — the maturity of the modern component
    aesthetic without a client framework. Vendored Geist + Lucide {LUCIDE_VERSION}.</p>
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
    print(f"built {len(COMPONENTS)} components -> {out_dir}/index.html")


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
        "```html\n"
        '<link rel="stylesheet" href="hatchi-maxchi.css">\n'
        '<script src="hatchi-maxchi.js" defer></script>\n'
        "```\n\n"
        "Copy any component's HTML from the gallery. In a real app, swap the mock\n"
        "htmx for [htmx](https://htmx.org) and point the `hx-*` attributes at your\n"
        "endpoints (e.g. the command palette's `hx-get` at your search route).\n\n"
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
