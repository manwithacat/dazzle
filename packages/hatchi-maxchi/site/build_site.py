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

from blueprints import BLUEPRINTS  # noqa: E402
from build import (  # noqa: E402  (package build.py)
    DEFAULT_PREFIX,
    FONT_DIR,
    apply_prefix,
    build_css,
    build_js,
)
from highlight import render_code_block  # noqa: E402
from hyperpart import anatomy  # noqa: E402  (package tools/hyperpart.py)

# GitHub Pages resolves extensionless paths to ``*.html`` when the file exists
# (no Pages setting required). Emit clean ``href``s; keep ``*.html`` on disk
# and on iframe ``src`` / static assets so ``file://`` and simple static
# servers still resolve embeds.
#
# Examples (file stays ``confirm.html``):
#   hyperparts/confirm.html  →  hyperparts/confirm
#   guide.html               →  guide
#   ../index.html#foo        →  ../#foo
#   index.html               →  ./


def _prefix_code_figure(figure: str, prefix: str) -> str:
    """Prefix code Hyperpart chrome + token *class names*; leave source text intact.

    ``apply_prefix`` is a global ``dz-`` rewrite — safe for class/attr names, but
    it would also rewrite dual-lock strings inside Python source (e.g.
    ``data-dz-native-confirm`` in a docstring). Agents need those names exact.
    """
    m = re.search(r'(<code class="dz-code__source">)([\s\S]*?)(</code>)', figure)
    if not m:
        return apply_prefix(figure, prefix)
    head, body, tail = m.group(1), m.group(2), m.group(3)
    body_out = re.sub(
        r'class="([^"]*)"',
        lambda mm: 'class="' + apply_prefix(mm.group(1), prefix) + '"',
        body,
    )
    shell = figure[: m.start()] + head + "\0BODY\0" + tail + figure[m.end() :]
    return apply_prefix(shell, prefix).replace("\0BODY\0", body_out)


def _contracts_html_prefixed(hyperpart, prefix: str) -> str:  # type: ignore[no-untyped-def]
    """Contracts section with gallery class prefix, dual-lock source text preserved."""
    raw = _contracts_html(hyperpart)
    if not raw:
        return ""
    parts = re.split(r'(<figure class="dz-code"[\s\S]*?</figure>)', raw)
    out: list[str] = []
    for part in parts:
        if part.startswith('<figure class="dz-code"'):
            out.append(_prefix_code_figure(part, prefix))
        else:
            out.append(apply_prefix(part, prefix) if part else part)
    return "".join(out)


from icons import ICONS, LUCIDE_VERSION  # noqa: E402
from icons.sprite import build_symbol_sheet, sprite_use_html  # noqa: E402
from pretty import pretty_html  # noqa: E402
from registry import GROUPS, HYPERPARTS  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]

_ICON_RE = re.compile(r"\{icon:([a-z0-9-]+)\}")
_SVG_RE = re.compile(r"\{svg:([a-z0-9-]+)\}")

# Human-facing ELI5 glosses for part-page terms (agents use prose + tables).
# Avoid the substring "dz-" in tips — site build may run apply_prefix which
# strips that token from the published gallery namespace.
# Tooltips are non-critical hints (hover / keyboard focus); leads still explain.
_GLOSSARY: dict[str, tuple[str, str]] = {
    "hyperpart": (
        "Hyperpart",
        "Reusable unit of UI: the HTML the server sends, the request it may "
        "fire, and maybe a tiny bit of JS. Not a React component — pure hypermedia.",
    ),
    "partial": (
        "partial",
        "The HTML fragment the server renders — the look of the control, ready "
        "to paste or emit. No client state graph inside it.",
    ),
    "affordance": (
        "affordance",
        "Something the user can act on that starts a request — a Delete button "
        "with hx-delete, a search box that hx-gets results. Browser talks to "
        "server; server returns HTML.",
    ),
    "exchange": (
        "Server exchange",
        "The deal for one action: which request goes out, what HTML comes back, "
        "and where it lands. Classic hypermedia — not a private JSON API for a SPA.",
    ),
    "dom-contract": (
        "DOM contract",
        "Required shape of the HTML the server returns (which roots and "
        "attributes must be present). CI checks it so nobody invents freestyle markup.",
    ),
    "controller": (
        "controller",
        "Small vanilla-JS helper only when the platform lacks a primitive. "
        "No client store — it only reads and writes the DOM.",
    ),
    "dual-lock": (
        "dual-lock",
        "Same design, two namespaces: gallery demos use plain class names; "
        "Dazzle apps use a product prefix on classes and data attributes.",
    ),
}

_DEP_GLOSSARY: dict[str, str] = {
    "Primitive": "HTML + CSS only — no controller script required.",
    "Sprite": "Needs the icon symbol sheet inlined once on the page.",
    "Controller": "Ships a small vanilla-JS controller (still no SPA state).",
    "Endpoint": "Needs a server exchange — an API that returns HTML fragments.",
    "Composite": "Built by composing other Hyperparts (see Composed of).",
}


def _term(key: str, label: str | None = None) -> str:
    """Glossary term with multi-line CSS tooltip (gallery chrome, not product surface).

    ``<dfn class="hm-term">`` is human-facing confidence: hover or focus for
    an ELI5. Agents scrape the surrounding section prose and tables.
    """
    display, tip = _GLOSSARY[key]
    text = display if label is None else label
    return (
        f'<dfn class="hm-term" tabindex="0" '
        f'data-tooltip="{_html.escape(tip, quote=True)}">'
        f"{_html.escape(text)}</dfn>"
    )


def _exchanges_html(hyperpart) -> str:  # type: ignore[no-untyped-def]
    """Always-visible Server exchange section (every part page — same skeleton).

    Parts with no exchanges still render the section so agents/humans never
    wonder whether the page is incomplete. Empty state = pure client / presentation.
    """
    head = f'<section class="hm-ref" id="exchange"><h3>{_term("exchange")}</h3>'
    if not hyperpart.exchanges:
        return (
            head + f'<p class="hm-ref-lead">This {_term("hyperpart")} has <strong>no server '
            "exchange</strong> — it is presentation or client chrome only. htmx does "
            f"not issue a request on this part&#x27;s behalf. If you put an {_term('affordance')} "
            "(<code>hx-*</code>) on a control that uses this markup, that action&#x27;s "
            "exchange belongs to the action, not this part.</p></section>"
        )
    rows = []
    examples: list[str] = []
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
        if e.server_example.strip():
            examples.append(
                f'<h4><code class="hm-verb">{_html.escape(e.method)}</code> '
                f"<code>{_html.escape(e.endpoint)}</code> — example handler</h4>"
                '<p class="hm-ref-lead">HTMX4 / standalone HM: return HTML fragments. '
                "Dazzle often emits this for you from the model; agents building a "
                "plain FastAPI app should match this shape. "
                "Not a dual-lock module — application code.</p>"
                + render_code_block(
                    e.server_example.strip() + "\n",
                    language="python",
                    aria_label=f"{e.method} {e.endpoint} example",
                )
            )
    return (
        head + f'<p class="hm-ref-lead">When the client {_term("affordance")} finishes '
        "(click, confirm, keystroke…), htmx issues <strong>this</strong> request. "
        "Your API must return the response fragment described below — usually HTML, "
        "not JSON (unless the partial says otherwise). Gallery mocks (toasts, "
        "<code>/mock/*</code>) are not the contract. Dazzle often renders these "
        "routes from the app model; a standalone HTMX4 app implements them "
        "explicitly.</p>"
        '<table class="hm-contract-table"><thead><tr>'
        "<th>Request</th><th>Trigger</th><th>Response fragment</th><th>Swap</th><th>States</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>" + "".join(examples) + "</section>"
    )


def _contract_pydantic_model(mod):  # type: ignore[no-untyped-def]
    """First Pydantic BaseModel defined in *mod* (not re-exported)."""
    return next(
        (
            v
            for v in vars(mod).values()
            if isinstance(v, type)
            and hasattr(v, "model_json_schema")
            and v.__module__ == mod.__name__
        ),
        None,
    )


def _validator_label(validator: object) -> str:
    """Human-readable constraint from a contracts._kit validator instance."""
    name = type(validator).__name__
    if name == "Present":
        return "present (any value)"
    if name == "OneOf":
        values = getattr(validator, "values", ())
        return f"one of {list(values)}"
    if name == "JsonPairs":
        when = getattr(validator, "required_when", None)
        base = "JSON [[value, label], …]"
        if when:
            return f"{base}; required when {when}"
        return base
    return name


def _schema_field_rows(model) -> list[tuple[str, str, str]]:  # type: ignore[no-untyped-def]
    """(field, type, required|optional) rows from a Pydantic model JSON schema."""
    schema = model.model_json_schema()
    req = set(schema.get("required", ()))
    rows: list[tuple[str, str, str]] = []
    for name, prop in schema.get("properties", {}).items():
        typ = (
            prop.get("type")
            or " | ".join(a.get("type", "?") for a in prop.get("anyOf", ()))
            or "object"
        )
        enum = prop.get("enum")
        if enum:
            typ = f"{typ} ∈ {enum}"
        rows.append((name, str(typ), "required" if name in req else "optional"))
    return rows


def _dom_contract_rows(dc) -> list[tuple[str, str, str]]:  # type: ignore[no-untyped-def]
    """(selector, attr, constraint) rows from a DomContract."""
    rows: list[tuple[str, str, str]] = []
    for node in dc.nodes:
        if not node.attrs:
            rows.append((node.selector, "—", "—"))
            continue
        for attr, validator in node.attrs.items():
            rows.append((node.selector, attr, _validator_label(validator)))
    return rows


def _fastapi_route_sources(mod) -> list[str]:  # type: ignore[no-untyped-def]
    """Source of each FastAPI route endpoint defined on mod.app (if any)."""
    import inspect

    app = getattr(mod, "app", None)
    if app is None:
        return []
    chunks: list[str] = []
    seen: set[int] = set()
    for route in getattr(app, "routes", ()):
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None or getattr(endpoint, "__module__", None) != mod.__name__:
            continue
        key = id(endpoint)
        if key in seen:
            continue
        seen.add(key)
        try:
            chunks.append(inspect.getsource(endpoint))
        except (OSError, TypeError):
            continue
    return chunks


def _contracts_html(hyperpart) -> str:  # type: ignore[no-untyped-def]
    """Always-visible DOM / ingestion contract — tables + code, no accordion.

    Every part page includes this section. Empty state when no ``contracts/``
    module is registered: treat Copy this as the surface.
    """
    head = f'<section class="hm-ref" id="dom-contract"><h3>{_term("dom-contract")}</h3>'
    if not hyperpart.contracts:
        return (
            head + '<p class="hm-ref-lead">No typed dual-lock module in '
            "<code>contracts/</code> for this part yet. Treat <strong>Copy this</strong> "
            "as the required surface — preserve the root class and "
            "<code>data-*</code> modifiers so the CSS/JS bundle matches. "
            "Author <code>contracts/&lt;part&gt;.py</code> when CI should "
            "stop-ship attribute drift "
            "(see <code>contracts/AUTHORING.md</code>).</p></section>"
        )
    import importlib
    import inspect

    blocks: list[str] = []
    for ref in hyperpart.contracts:
        mod = importlib.import_module(ref.removesuffix(".py").replace("/", "."))
        model = _contract_pydantic_model(mod)
        dc = getattr(mod, "DOM_CONTRACT", None)
        render_fn = getattr(mod, "render", None)
        exemplars = getattr(mod, "EXEMPLARS", ())
        fastapi_src = _fastapi_route_sources(mod)

        parts: list[str] = [f'<h4 class="hm-ref-mod"><code>{_html.escape(ref)}</code></h4>']

        if dc is not None:
            parts.append(
                f'<p class="hm-ref-lead"><strong>Required in the DOM:</strong> root '
                f"<code>{_html.escape(dc.root)}</code>"
                f" (part <code>{_html.escape(dc.part)}</code>). "
                "Emit only these attributes — inventing extras is fine only if "
                "controllers ignore them; omitting required ones fails CI "
                "(<code>tests/test_contracts.py</code>).</p>"
            )
            drows = _dom_contract_rows(dc)
            if drows:
                body = "".join(
                    f"<tr><td><code>{_html.escape(sel)}</code></td>"
                    f"<td><code>{_html.escape(attr)}</code></td>"
                    f"<td>{_html.escape(constraint)}</td></tr>"
                    for sel, attr, constraint in drows
                )
                parts.append(
                    '<table class="hm-contract-table"><thead><tr>'
                    "<th>Node</th><th>Attr</th><th>Constraint</th>"
                    f"</tr></thead><tbody>{body}</tbody></table>"
                )
            elif not model and not fastapi_src:
                parts.append(
                    '<p class="hm-ref-lead">Root-only contract — the root selector '
                    "must match; no per-node attribute list.</p>"
                )

        if model is not None:
            srows = _schema_field_rows(model)
            body = "".join(
                f"<tr><td><code>{_html.escape(n)}</code></td>"
                f"<td><code>{_html.escape(t)}</code></td>"
                f"<td>{_html.escape(r)}</td></tr>"
                for n, t, r in srows
            )
            parts.append(
                f"<h4>Ingestion model <code>{_html.escape(model.__name__)}</code></h4>"
                '<p class="hm-ref-lead">Server-side shape before render — one '
                "normalisation boundary for producers.</p>"
                f'<table class="hm-contract-table"><thead><tr>'
                "<th>Field</th><th>Type</th><th>Required</th>"
                f"</tr></thead><tbody>{body}</tbody></table>"
            )

        if render_fn and exemplars:
            live = render_fn(exemplars[0])
            parts.append(
                "<h4>Exemplar <code>render()</code></h4>"
                '<p class="hm-ref-lead">Executable in CI — model → conforming markup.</p>'
                + render_code_block(
                    inspect.getsource(render_fn),
                    language="python",
                    aria_label=f"Exemplar render for {ref}",
                )
                + f'<div class="hm-contract-live">{live}</div>'
            )

        if fastapi_src:
            app = getattr(mod, "app", None)
            title = getattr(app, "title", None) if app is not None else None
            h = f" — {_html.escape(title)}" if title else ""
            parts.append(
                f"<h4>FastAPI feed example{h}</h4>"
                '<p class="hm-ref-lead">Package exemplar for feeding this seam '
                "(not the gallery mock). Prefer the part&#x27;s "
                '<a href="#exchange">Server exchange</a> '
                "<code>server_example</code> when present — that is the product "
                "handler shape. Avoid <code>from __future__ import annotations</code> "
                "in real FastAPI route files (ADR-0014).</p>"
                + render_code_block(
                    "\n\n".join(fastapi_src),
                    language="python",
                    aria_label=f"FastAPI exemplar for {ref}",
                )
            )

        # Thin / DOM-only: show the whole module (usually a short DOM_CONTRACT).
        if model is None and not (render_fn and exemplars) and not fastapi_src:
            try:
                full = inspect.getsource(mod)
            except (OSError, TypeError):
                full = ""
            if full:
                parts.append(
                    "<h4>Module source</h4>"
                    '<p class="hm-ref-lead">Import path is monorepo/package-local '
                    "(<code>from contracts._kit import …</code>). "
                    "Source-token form often uses <code>data-dz-*</code>; gallery demos "
                    "above are unprefixed. Do not copy this into app routes.</p>"
                    + render_code_block(
                        full,
                        language="python",
                        aria_label=f"Module source {ref}",
                    )
                )

        blocks.append("".join(parts))

    return (
        head + '<p class="hm-ref-lead">What the <strong>emitted HTML</strong> must satisfy — '
        "the table is the required surface; Python under <code>contracts/</code> is "
        f"the package-internal {_term('dual-lock')} CI runs "
        "(<code>tests/test_contracts.py</code>), not an app route. "
        "Standalone HTMX4: implement the API so responses match this markup. "
        "Dazzle: the agent emits SSR that already satisfies it. "
        "Do not invent attrs outside these tables. "
        'For request/response wiring see <a href="#exchange">Server exchange</a>.'
        "</p>" + "".join(blocks) + "</section>"
    )


def _default_how_to_seams(hyperpart) -> list[str]:  # type: ignore[no-untyped-def]
    """Minimal seams when Guidance is not authored — still a full How-to section."""
    seams = [
        "copy the partial under Copy this; keep root class and data-* modifiers "
        "so the CSS/JS bundle matches",
    ]
    if hyperpart.controller:
        seams.append(
            f"load the controller (`{hyperpart.controller}` — included in "
            "hatchi-maxchi.js when you ship the bundle)"
        )
    if hyperpart.exchanges:
        seams.append("implement Server exchange endpoints; return HTML fragments, not JSON")
    else:
        seams.append("no Server exchange on this part — pure presentation or client chrome")
    if hyperpart.contracts:
        seams.append("satisfy the DOM contract tables (CI stop-ship)")
    else:
        seams.append("no typed contracts/ module yet — the partial is the surface of record")
    return seams


def _guidance_html(hyperpart) -> str:  # type: ignore[no-untyped-def]
    """How-to guidance — always present on every part page (same skeleton)."""

    def _ul(items) -> str:  # type: ignore[no-untyped-def]
        return "<ul>" + "".join(f"<li>{_html.escape(i)}</li>" for i in items) + "</ul>"

    g = hyperpart.guidance
    blocks = ['<section class="hm-ref" id="how-to"><h3>How to use it</h3>']
    if g is None:
        blocks.append(
            '<p class="hm-ref-lead">No extended guidance authored yet — start from '
            "Copy this and the dependency chips (Primitive = markup only; "
            f"{_term('controller')} = load listed JS; Endpoint = implement "
            f"{_term('exchange')}).</p>"
        )
        blocks.append(f"<h4>Seams</h4>{_ul(_default_how_to_seams(hyperpart))}")
        blocks.append("</section>")
        return "".join(blocks)

    if g.seams:
        blocks.append(f"<h4>Seams</h4>{_ul(g.seams)}")
    if g.do_dont:
        rows = "".join(
            f"<tr><td>{_html.escape(do)}</td><td>{_html.escape(dont)}</td></tr>"
            for do, dont in g.do_dont
        )
        blocks.append(
            '<h4>Do / Don\'t</h4><table class="hm-contract-table">'
            f"<thead><tr><th>Do</th><th>Don't</th></tr></thead><tbody>{rows}</tbody></table>"
        )
    if g.pitfalls:
        blocks.append(f"<h4>Pitfalls</h4>{_ul(g.pitfalls)}")
    if g.a11y_keys:
        blocks.append(f"<h4>Keyboard / AT</h4>{_ul(g.a11y_keys)}")
    if g.composes_with:
        links = " ".join(f'<a href="{pid}"><code>{pid}</code></a>' for pid in g.composes_with)
        blocks.append(f"<h4>Related parts</h4><p>{links}</p>")
    blocks.append("</section>")
    return "".join(blocks)


def _notes_html(hyperpart, prefix: str) -> str:  # type: ignore[no-untyped-def]
    """Registry notes as an open section (not a disclosure)."""
    if not hyperpart.notes:
        return ""
    return (
        '<section class="hm-ref" id="notes"><h3>Notes</h3>'
        f'<div class="hm-notes">{apply_prefix(hyperpart.notes, prefix)}</div>'
        "</section>"
    )


def _dialect_html() -> str:
    return (
        '<p class="hm-dialect"><strong>Markup dialect:</strong> demos on this page '
        "are <strong>unprefixed</strong> (standalone HaTchi-MaXchi / copy-paste). "
        "Dazzle apps use the <code>dz-</code> class and <code>data-dz-*</code> "
        f"attribute form. {_term('dom-contract')} Python below is "
        f"{_term('dual-lock')} source (often still <code>data-dz-*</code>). "
        "Match the CSS/JS bundle you load. "
        '<span class="hm-term-hint">Dotted terms explain on hover or keyboard focus '
        "— hypermedia, not a black box.</span></p>"
    )


def _guide_body() -> str:
    """guide.html body — the ONE theory track (spec decision 3). Prose is
    theory only; every code/markup/contract block is EMBEDDED from a
    drift-gated source (registry partials via the normal renderers, contract
    modules via _contracts_html) so the gates see everything the guide shows."""
    grid = _BY_ID["grid"]
    sections = []
    sections.append(
        '<section class="hm-comp" id="why"><h2>1 · Why hypermedia</h2>'
        "<p>HaTchi-MaXchi is an htmx4-native design system: the server renders "
        "markup, the browser swaps fragments, and there is no client state "
        "graph. State lives in two places only — on the server, and in the DOM "
        "itself (attributes, <code>.checked</code>, <code>aria-*</code>). A "
        f"component here is a {_term('hyperpart')}: a {_term('partial')} plus its "
        f"{_term('exchange', 'exchange')} contracts plus, only where the platform "
        f"lacks a primitive, a small delegated vanilla-JS {_term('controller')}. "
        "If you arrive with React priors, the renaming is deliberate: there is "
        "nothing to hydrate, no composition tree, and morphing swaps will discard "
        "any state a JS object tries to hold. "
        '<span class="hm-term-hint">Dotted terms: hover or focus for a plain-language '
        "gloss — these are fundamental hypermedia techniques, not a proprietary box."
        "</span></p></section>"
    )
    sections.append(
        '<section class="hm-comp" id="tokens"><h2>2 · Tokens &amp; theming</h2>'
        "<p>All variation flows through design tokens. Components reference "
        "semantic custom properties; schemes (light/dark) and aesthetic "
        "families override tokens, never rules. The theme toggle on every page "
        "of this site flips <code>data-theme</code> on the root — no component "
        "opts in, because no component names a raw colour. When styling looks "
        "wrong, the first question is always <em>which token should this be "
        "reading?</em>, not <em>which rule should I add?</em></p></section>"
    )
    sections.append(
        '<section class="hm-comp" id="anatomy"><h2>3 · Anatomy of a Hyperpart '
        "— the grid, worked</h2>"
        "<p>One Hyperpart is one logical unit distributed across files by build "
        "necessity: the partial and exchange contracts in the registry, CSS in "
        "layer order, an optional controller, and — for data-bearing parts — a "
        "typed contract module. The grid family shows every piece at once; its "
        "inline-edit extension is the canonical example of the morph-survival "
        "idiom (the typed edit buffer lives on the grid root, out of the swap "
        "path).</p>" + _anatomy_html(grid) + "</section>"
    )
    sections.append(
        '<section class="hm-comp" id="contracts"><h2>4 · '
        f"{_term('exchange', 'Exchanges')} &amp; contracts</h2>"
        f"<p>A {_term('hyperpart')} is only half markup. The other half is the "
        "contract the server must satisfy: the exchange (request/response "
        f"round-trip each {_term('affordance')} initiates) and, for data-bearing "
        "seams, the <em>typed contract module</em> — ingestion model, "
        f"{_term('dom-contract')}, and an executable exemplar that CI renders and "
        "validates. Both halves for the grid:</p>"
        + _exchanges_html(grid)
        + _contracts_html(grid)
        + "</section>"
    )
    bp_links = " · ".join(
        f'<a href="blueprints/{bp.id}">{_html.escape(bp.title)}</a>' for bp in BLUEPRINTS
    )
    sections.append(
        '<section class="hm-comp" id="blueprints"><h2>5 · Composing '
        "Blueprints</h2>"
        "<p>Whole pages compose from published Hyperparts and Layout primitives "
        "only — a <strong>Blueprint</strong> is the thing you copy when starting "
        "a page. Layout responsiveness is intrinsic (primitives wrap on their "
        "own minimums; no media queries), which is what makes a Blueprint "
        "testable at any viewport. Study them live: " + bp_links + ".</p>"
        "<p>Building a NEW part instead? Follow the contract-first path in "
        "<code>contracts/AUTHORING.md</code> — decision test, contract module, "
        "controller, registry, consumer emitter.</p></section>"
    )
    return "".join(sections)


def _plain_notes(notes: str) -> str:
    """Strip simple HTML from registry notes for agent markdown."""
    text = re.sub(r"<br\s*/?>", "\n", notes, flags=re.I)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return _html.unescape(text).strip()


def _agent_md(hyperpart, snippet_src: str) -> str:  # type: ignore[no-untyped-def]
    """agents/<id>.md — linear scrape target aligned with the part HTML page.

    Order: identity → dialect → partial → exchange → how-to → DOM contract →
    notes → files. Same sections as hyperparts/<id>.html so agents and humans
    share one mental model.
    """
    lines = [
        f"# {hyperpart.title} (`{hyperpart.id}`)",
        "",
        hyperpart.blurb,
        "",
        "> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). "
        "DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` "
        "(Dazzle dual-lock). Match the CSS/JS bundle you load.",
        "",
        "## Copy this",
        "",
        "```html",
        snippet_src.rstrip("\n"),
        "```",
        "",
    ]
    # Always emit Server exchange / How to use / DOM contract (same skeleton as HTML).
    lines += ["## Server exchange", ""]
    if not hyperpart.exchanges:
        lines += [
            "This Hyperpart has **no server exchange** — presentation or client "
            "chrome only. If you put `hx-*` on a control that uses this markup, "
            "that action's exchange belongs to the action, not this part.",
            "",
        ]
    else:
        lines += [
            "When the client affordance finishes, htmx issues **this** request. "
            "Return the HTML fragment described (not gallery mock toasts). "
            "Dazzle often implements these from the app model; a standalone HTMX4 "
            "app implements them explicitly.",
            "",
            "| Request | Trigger | Response fragment | Swap | States |",
            "|---|---|---|---|---|",
        ]
        for e in hyperpart.exchanges:
            states = " ".join(e.states) if e.states else "—"
            row = (
                f"| `{e.method} {e.endpoint}` | {e.trigger} | {e.response} | {e.swap} | {states} |"
            )
            lines.append(row.replace("\n", " "))
        lines.append("")
        for e in hyperpart.exchanges:
            if not e.server_example.strip():
                continue
            lines += [
                f"### `{e.method} {e.endpoint}` — example handler",
                "",
                "Application code (not the dual-lock module). FastAPI-shaped; "
                "do not use `from __future__ import annotations` in route files (ADR-0014).",
                "",
                "```python",
                e.server_example.strip(),
                "```",
                "",
            ]

    lines += ["## How to use it", ""]
    g = hyperpart.guidance
    if g is None:
        lines += [
            "No extended guidance authored yet — start from Copy this and the dependency chips.",
            "",
            "### Seams",
            "",
        ]
        lines += [f"- {s}" for s in _default_how_to_seams(hyperpart)] + [""]
    else:
        for heading, items in (
            ("Seams", g.seams),
            ("Do / Don't", None),
            ("Pitfalls", g.pitfalls),
            ("Keyboard / AT", g.a11y_keys),
        ):
            if heading == "Do / Don't":
                if g.do_dont:
                    lines += ["### Do / Don't", "", "| Do | Don't |", "|---|---|"]
                    lines += [f"| {do} | {dont} |" for do, dont in g.do_dont] + [""]
                continue
            if items:
                lines += [f"### {heading}", ""] + [f"- {i}" for i in items] + [""]
        if g.composes_with:
            lines += ["### Related parts", ""]
            lines += [f"- `{pid}` — agents/{pid}.md" for pid in g.composes_with] + [""]

    lines += ["## DOM contract", ""]
    if not hyperpart.contracts:
        lines += [
            "No typed dual-lock module in `contracts/` for this part yet. "
            "Treat **Copy this** as the required surface — preserve root class and "
            "`data-*` modifiers. Author `contracts/<part>.py` when CI should "
            "stop-ship attribute drift (`contracts/AUTHORING.md`).",
            "",
        ]
    else:
        import importlib
        import inspect

        lines += [
            "What emitted markup must satisfy (CI: `tests/test_contracts.py`). "
            "Do not invent attrs outside the tables. Python modules under "
            "`contracts/` are **package-internal dual-locks** "
            "(`from contracts._kit import …`) — not FastAPI business handlers. "
            "App servers implement **Server exchange** endpoints; this section "
            "constrains the HTML those endpoints return.",
            "",
        ]
        for ref in hyperpart.contracts:
            lines.append(f"### `{ref}`")
            lines.append("")
            mod = importlib.import_module(ref.removesuffix(".py").replace("/", "."))
            model = _contract_pydantic_model(mod)
            dc = getattr(mod, "DOM_CONTRACT", None)
            render_fn = getattr(mod, "render", None)
            exemplars = getattr(mod, "EXEMPLARS", ())
            fastapi_src = _fastapi_route_sources(mod)

            if dc is not None:
                lines += [f"- **Required root:** `{dc.root}` (part `{dc.part}`)"]
                drows = _dom_contract_rows(dc)
                if drows:
                    lines += [
                        "",
                        "| Node | Attr | Constraint |",
                        "|---|---|---|",
                    ]
                    lines += [
                        f"| `{sel}` | `{attr}` | {constraint} |" for sel, attr, constraint in drows
                    ]
                lines.append("")

            if model is not None:
                lines += [
                    f"#### Ingestion model `{model.__name__}`",
                    "",
                    "| Field | Type | Required |",
                    "|---|---|---|",
                ]
                for name, typ, req in _schema_field_rows(model):
                    lines.append(f"| `{name}` | `{typ}` | {'yes' if req == 'required' else 'no'} |")
                lines.append("")

            if render_fn and exemplars:
                try:
                    rsrc = inspect.getsource(render_fn)
                except (OSError, TypeError):
                    rsrc = ""
                if rsrc:
                    lines += [
                        "#### Exemplar `render()`",
                        "",
                        "```python",
                        rsrc.rstrip("\n"),
                        "```",
                        "",
                    ]

            if fastapi_src:
                app = getattr(mod, "app", None)
                title = getattr(app, "title", None) if app is not None else None
                sub = f" — {title}" if title else ""
                lines += [
                    f"#### FastAPI feed example{sub}",
                    "",
                    "```python",
                    "\n\n".join(s.rstrip("\n") for s in fastapi_src),
                    "```",
                    "",
                ]

            if model is None and not (render_fn and exemplars) and not fastapi_src:
                try:
                    full = inspect.getsource(mod)
                except (OSError, TypeError):
                    full = ""
                if full:
                    lines += [
                        "#### Module source",
                        "",
                        "Monorepo dual-lock only — import `contracts._kit` from the "
                        "HM package. Do not paste into app route modules.",
                        "",
                        "```python",
                        full.rstrip("\n"),
                        "```",
                        "",
                    ]
    if hyperpart.notes:
        lines += ["## Notes", "", _plain_notes(hyperpart.notes), ""]
    lines += ["## Source files", ""]
    lines.append("- `site/registry.py` (partial + exchanges + guidance)")
    for ref in hyperpart.contracts:
        lines.append(f"- `{ref}`")
    if hyperpart.controller:
        lines.append(f"- `{hyperpart.controller}`")
        lines += [f"- `{e}`" for e in hyperpart.extensions]
    lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _anatomy_html(hyperpart) -> str:  # type: ignore[no-untyped-def]
    """Source files — always present so every part page shares one skeleton."""
    parts = ["<code>site/registry.py</code>"]
    for ref in hyperpart.contracts:
        parts.append(f"<code>{_html.escape(ref)}</code>")
    if hyperpart.controller:
        a = anatomy(hyperpart.id)
        parts += [f"<code>{_html.escape(s)}</code>" for s in a["styles"]]
        parts.append(f"<code>{_html.escape(a['controller'])}</code>")
        parts += [f"<code>{_html.escape(e)}</code>" for e in a["extensions"]]
        if a["mock"]:
            parts.append(f"mock <code>{_html.escape(a['mock'])}</code>")
        lead = (
            "One logical Hyperpart, {n} code items "
            "(CSS layered, JS bundled). Bound by <code>HYPERPART: {id}</code> — "
            "<code>python tools/hyperpart.py {id}</code> lists them."
        )
    else:
        lead = (
            "Canonical registration in the registry. No dedicated controller — "
            "CSS for this part lives in the layered bundle."
        )
    return (
        '<section class="hm-ref" id="files"><h3>Source files</h3>'
        f'<p class="hm-ref-lead">{lead}</p>'
        f'<p class="hm-anatomy">{" · ".join(parts)}</p></section>'
    ).format(n=len(parts), id=_html.escape(hyperpart.id))


def _part_breadcrumb(part_id: str, title: str) -> str:
    """Dogfood the breadcrumb Hyperpart for part-page chrome navigation."""
    return (
        '<nav class="dz-breadcrumb" aria-label="Breadcrumb"><ol>'
        f'<li><a href="../#{_html.escape(part_id)}">Hyperparts</a></li>'
        f'<li aria-current="page">{_html.escape(title)}</li>'
        "</ol></nav>"
    )


def _dogfood_banner() -> str:
    """Human-facing note: product UX on the page is HaTchi-MaXchi itself."""
    return (
        '<p class="hm-dogfood" role="note">'
        "<strong>Dogfood:</strong> the live demo, code snippets "
        f"({_term('partial')} + code Hyperpart), theme control (toggle-group), "
        "and this breadcrumb are HaTchi-MaXchi. Page layout chrome "
        "(<code>hm-*</code> grid/nav) is gallery scaffolding on the same tokens "
        "— not a separate UI kit."
        "</p>"
    )


# A copied sprite snippet is blank without the icon sheet — surface the
# dependency IN the snippet so it travels with a paste (the README note does
# not). Prepended once to any partial that uses the sprite `<use>` form.
_SPRITE_NOTE = (
    "<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->\n"
)


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
        # Sibling part pages (extensionless for GitHub Pages).
        links.append(f'<a href="{cid}">{_html.escape(title)}</a>')
    return (
        '<section class="hm-ref" id="composed">'
        f'<h3>Composed of</h3><p class="hm-composed">{" · ".join(links)}</p>'
        "</section>"
    )


def _dependency_chips(hyperpart) -> str:  # type: ignore[no-untyped-def]
    chips = []
    for d in _dependency_classes(hyperpart):
        tip = _DEP_GLOSSARY.get(d, f"Dependency class: {d}")
        chips.append(
            f'<span class="hm-dep" data-dep="{d.lower()}" '
            f'tabindex="0" data-tooltip="{_html.escape(tip, quote=True)}">{d}</span>'
        )
    return "".join(chips)


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
    // Mock: <button> not <a href="#"> — hash links scroll the gallery page to top.
    "/mock/command": '<div class="dz-command__group">Workspaces</div>' +
      '<button type="button" class="dz-command__item" role="option">{i:layout-dashboard}<span>Operations Dashboard</span></button>' +
      '<button type="button" class="dz-command__item" role="option">{i:settings}<span>Platform Admin</span></button>' +
      '<div class="dz-command__group">Records</div>' +
      '<button type="button" class="dz-command__item" role="option">{i:receipt}<span>Invoices</span></button>' +
      '<button type="button" class="dz-command__item" role="option">{i:users}<span>Customers</span></button>' +
      '<button type="button" class="dz-command__item" role="option">{i:triangle-alert}<span>Alerts</span></button>',
    "/mock/master-detail/inv-001": '<div class="dz-card dz-card-body"><div class="dz-card-label">INV-001 · Acme</div><div class="dz-card-value">£1,250.00</div><div class="dz-card-delta">Paid · 2 days ago</div></div>',
    "/mock/master-detail/inv-002": '<div class="dz-card dz-card-body"><div class="dz-card-label">INV-002 · Globex</div><div class="dz-card-value">£3,400.00</div><div class="dz-card-delta">Pending · due Friday</div></div>',
    "/mock/master-detail/inv-003": '<div class="dz-card dz-card-body"><div class="dz-card-label">INV-003 · Initech</div><div class="dz-card-value">£820.00</div><div class="dz-card-delta">Overdue · 6 days</div></div>',
    "/mock/pagination/2": '<div class="hm-pag-row">INV-004 · Umbrella</div><div class="hm-pag-row">INV-005 · Stark</div><div class="hm-pag-row">INV-006 · Wonka</div>',
    "/mock/pagination/3": '<div class="hm-pag-row">INV-007 · Tyrell</div><div class="hm-pag-row">INV-008 · Cyberdyne</div><div class="hm-pag-row">INV-009 · Soylent</div>',
    "/mock/pagination/9": '<div class="hm-pag-row">INV-025 · Hooli</div><div class="hm-pag-row">INV-026 · Pied Piper</div><div class="hm-pag-row">INV-027 · Aviato</div>',
    "/mock/typeahead": '<div class="dz-search-result-row" hx-get="/mock/typeahead/select" hx-target="#hm-ss-results" hx-swap="innerHTML"><div class="dz-search-result-name">Aurora Energy Ltd</div><div class="dz-search-result-secondary">Company no. 09182736</div></div><div class="dz-search-result-row" hx-get="/mock/typeahead/select" hx-target="#hm-ss-results" hx-swap="innerHTML"><div class="dz-search-result-name">Aurora Foods plc</div></div>',
    "/mock/typeahead/select": '<div class="dz-select-result-confirm">Selected: Aurora Energy Ltd</div>',
    "/mock/search": '<div class="dz-search-box-result-count">2 results</div><ul class="dz-search-box-result-list" role="list"><li class="dz-search-box-result"><a href="#" class="dz-search-box-result-link"><span class="dz-search-box-result-title">Aurora <mark>Substation</mark></span><ul class="dz-search-box-result-snippets"><li class="dz-search-box-result-snippet"><span class="dz-search-box-result-snippet-field">Region:</span><span class="dz-search-box-result-snippet-text">North grid, <mark>substation</mark> cluster A</span></li></ul></a></li><li class="dz-search-box-result"><a href="#" class="dz-search-box-result-link"><span class="dz-search-box-result-title">Beacon <mark>Substation</mark></span></a></li></ul>',
    "/mock/drawer/detail": '<h3>Aurora Substation</h3><p>Region: North · Load: 82%</p><p>Commissioned 2019; last inspection 14 June. Two open work orders.</p>',
    "/mock/shell/dashboard": '<div class="dz-stack" data-dz-gap="md"><h1>Dashboard</h1><div class="dz-auto-grid" style="--dz-grid-min: 10rem"><div class="dz-card dz-card-body"><div class="dz-card-label">Outstanding</div><div class="dz-card-value">£12,450</div></div><div class="dz-card dz-card-body"><div class="dz-card-label">Paid</div><div class="dz-card-value">£48,900</div></div></div></div>',
    "/mock/shell/invoices": '<div class="dz-stack" data-dz-gap="md"><h1>Invoices</h1><p class="hm-demo-muted">The routed workspace swapped — the shell, sidebar state, and scroll position persist; only the main slot changed.</p></div>',
    "/mock/tabs/activity": '<p class="hm-demo-muted">3 events today — INV-004 paid, INV-005 sent, a comment added.</p>',
    "/mock/tabs/settings": '<p class="hm-demo-muted">Notifications, access, and billing preferences live here.</p>'
  };

  // The grid tbody hydrates, filters, and re-sorts its rows over the wire — the
  // SERVER owns the order and the WHERE. Held as data (not markup) so the mock
  // can filter + ORDER BY the query params the controller puts on the request,
  // mirroring a real list endpoint. Each row renders a stable `id`
  // (`dz-grid-row-<rowid>`, the idiomorph morph key) + `data-dz-grid-row-id`
  // (the bulk payload anchor); the two agree. Values span DISTINCT sort orders
  // per column (first vs last name vs plan vs date all reorder differently) so
  // the demo legibly shows WHICH column you sorted. `status` is a filter-only
  // field (not a visible column). The unsorted (insertion) order below is
  // deliberately scrambled so "no sort" is visibly distinct from every column
  // sort. NB on dates: a real server sorts a typed date column (SQL is
  // type-aware); the mock sorts the ISO-8601 strings, whose LEXICAL order
  // equals chronological order — a faithful stand-in, not string luck.
  var GRID_ROWS = [
    { id: "cust_1", first: "Mia", last: "Chen", plan: "Team", signed: "2025-06-20", status: "Active" },
    { id: "cust_2", first: "Ravi", last: "Patel", plan: "Enterprise", signed: "2023-08-09", status: "Active" },
    { id: "cust_3", first: "Amir", last: "Okafor", plan: "Pro", signed: "2026-01-15", status: "Active" },
    { id: "cust_4", first: "Sofia", last: "Alvarez", plan: "Free", signed: "2026-07-01", status: "Trialing" },
    { id: "cust_5", first: "Noah", last: "Bright", plan: "Pro", signed: "2022-03-14", status: "Churned" },
    { id: "cust_6", first: "Jane", last: "Zimmerman", plan: "Free", signed: "2024-11-02", status: "Trialing" }
  ];
  // Query params handled specially, NOT as exact-match filters: sort/paging
  // control + the free-text search `q`.
  var GRID_CONTROL = { sort: 1, dir: 1, page: 1, page_size: 1, q: 1 };
  function parseQuery(url) {
    var out = {}, qs = (url.split("?")[1] || "");
    qs.split("&").forEach(function (p) {
      if (!p) return;
      var kv = p.split("=");
      out[kv[0]] = decodeURIComponent(kv[1] || "");
    });
    return out;
  }
  // Escape interpolated field values — the canned data is safe, but this mock
  // sits next to the documented server contract, so it must model the correct
  // idiom (never build row HTML from unescaped data).
  function htmlEnc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  var GRID_PAGE_SIZE = 4; // the server's default page size for this demo

  // The full result set for a query — search + filters + sort, WITHOUT paging.
  // The row slice and the pagination total both derive from this, so they can
  // never disagree (the bug class #847-#851 chased for charts).
  function matchedRows(q) {
    var rows = GRID_ROWS.slice();
    // Free-text search: case-insensitive substring across the visible text
    // fields (the server's ILIKE/full-text). Composes with the exact filters.
    if (q.q) {
      var needle = q.q.toLowerCase();
      rows = rows.filter(function (r) {
        return (r.first + " " + r.last + " " + r.plan).toLowerCase().indexOf(needle) >= 0;
      });
    }
    // Filters: every non-control param narrows by an exact field match (the
    // server's WHERE). An empty value ("Any …") is never sent, so never narrows.
    Object.keys(q).forEach(function (k) {
      if (GRID_CONTROL[k] || q[k] === "") return;
      rows = rows.filter(function (r) { return String(r[k]) === q[k]; });
    });
    if (q.sort) {
      rows.sort(function (a, b) {
        var x = a[q.sort], y = b[q.sort];
        var c = x < y ? -1 : (x > y ? 1 : 0);
        return q.dir === "desc" ? -c : c;
      });
    }
    return rows;
  }
  function gridPaging(q, total) {
    var size = parseInt(q.page_size, 10) || GRID_PAGE_SIZE;
    var pages = Math.max(1, Math.ceil(total / size));
    var page = Math.min(Math.max(1, parseInt(q.page, 10) || 1), pages);
    return { size: size, page: page, pages: pages };
  }
  function renderGridRows(url) {
    var q = parseQuery(url);
    var rows = matchedRows(q);
    var pg = gridPaging(q, rows.length);
    var start = (pg.page - 1) * pg.size;
    // Zero rows → empty tbody, so the `:has(tbody tr td)` empty-state shows.
    // Editable cells emit the inline-edit seam: ONE display span per cell
    // carrying kind/value/label (+ options for selects). The dz-grid-edit
    // extension builds the editor on dblclick and commits a single-field PUT
    // to the root's data-dz-grid-edit-url; cells stay server-rendered.
    function editSpan(col, kind, value, label, options) {
      return '<span class="dz-tr-cell-display" data-dz-grid-edit="' + col + '" ' +
        'data-dz-edit-kind="' + kind + '" data-dz-edit-value="' + htmlEnc(value) + '" ' +
        'data-dz-edit-label="' + label + '"' +
        (options ? ' data-dz-edit-options="' + htmlEnc(JSON.stringify(options)) + '"' : "") +
        ">" + htmlEnc(value) + "</span>";
    }
    var PLAN_OPTIONS = [["Free", "Free"], ["Pro", "Pro"], ["Team", "Team"],
      ["Enterprise", "Enterprise"]];
    return rows.slice(start, start + pg.size).map(function (r) {
      var id = htmlEnc(r.id), name = htmlEnc(r.first + " " + r.last);
      // data-dz-col on every data cell = the column-visibility target;
      // data-dz-row-id on the tr = the extensions' row anchor (Dazzle parity).
      return '<tr class="dz-tr-row" id="dz-grid-row-' + id + '" data-dz-row-id="' + id + '">' +
        '<td class="dz-tr-checkbox-cell"><input type="checkbox" class="dz-tr-checkbox" ' +
        'data-dz-grid-select data-dz-grid-row-id="' + id + '" aria-label="Select ' + name + '"></td>' +
        '<td class="dz-tr-cell" data-dz-col="first">' +
        editSpan("first", "text", r.first, "First name") + '</td>' +
        '<td class="dz-tr-cell" data-dz-col="last">' +
        editSpan("last", "text", r.last, "Last name") + '</td>' +
        '<td class="dz-tr-cell" data-dz-col="plan">' +
        editSpan("plan", "select", r.plan, "Plan", PLAN_OPTIONS) + '</td>' +
        '<td class="dz-tr-cell" data-dz-col="signed">' +
        editSpan("signed", "date", r.signed, "Signed up") + '</td></tr>';
    }).join("");
  }
  // The server renders the pagination footer too (state-in-DOM: the page
  // controls carry their target; the current page + total live in the markup).
  // The client only intercepts the clicks and re-requests.
  function renderGridFooter(url) {
    var q = parseQuery(url);
    var total = matchedRows(q).length;
    var pg = gridPaging(q, total);
    var start = total ? (pg.page - 1) * pg.size + 1 : 0;
    var end = Math.min(pg.page * pg.size, total);
    var summary = total ? start + "-" + end + " of " + total : "0 of 0";
    // The summary is the Dazzle-faithful PAIR: a bulk-count mirror shown while
    // a selection exists, the row window otherwise (CSS-toggled off the root's
    // data-dz-bulk-count — see table.css .dz-bulk-summary-*).
    var html = '<span class="dz-pagination-summary">' +
      '<span class="dz-bulk-summary-selected">' +
      '<span data-dz-bulk-count-target>0</span> of ' + total + ' selected</span>' +
      '<span class="dz-bulk-summary-rows">' + summary + "</span></span>";
    html += '<div class="dz-pagination-pages">';
    html += '<button type="button" class="dz-pagination-page" data-dz-grid-page-prev ' +
      (pg.page <= 1 ? "disabled " : "") + 'aria-label="Previous page">‹</button>';
    for (var i = 1; i <= pg.pages; i++) {
      html += '<button type="button" class="dz-pagination-page' +
        (i === pg.page ? " is-current" : "") + '" data-dz-grid-goto="' + i + '"' +
        (i === pg.page ? ' aria-current="page"' : "") + ">" + i + "</button>";
    }
    html += '<button type="button" class="dz-pagination-page" data-dz-grid-page-next ' +
      (pg.page >= pg.pages ? "disabled " : "") + 'aria-label="Next page">›</button>';
    return html + "</div>";
  }
  function updateGridFooter(root, url) {
    var nav = root && root.querySelector("[data-dz-grid-pagination]");
    if (!nav) return;
    // The server stamps the matched TOTAL on the footer nav
    // (data-dz-grid-total) — the all-matching affordance reads it ("Select
    // all N matching") and the controller uses it for the selection count.
    // In a real htmx app the OOB `<nav hx-swap-oob>` carries the attribute.
    nav.setAttribute("data-dz-grid-total", String(matchedRows(parseQuery(url)).length));
    nav.innerHTML = renderGridFooter(url);
  }

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
    var body;
    if (url.split("?")[0] === "/mock/grid/rows") {
      // the grid rows are computed from the sort/dir query (server owns ORDER BY)
      body = renderGridRows(url);
    } else {
      body = expand(RESPONSES[url] || '<div class="dz-command__empty">No results.</div>');
    }
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
    // htmx applies `.htmx-request` to the request-initiating element for the
    // duration of the in-flight request — the loading overlay + other CSS states
    // key off it. Mirror that protocol here (add before the swap, remove after).
    // The mock is SYNCHRONOUS, so there is no repaint between add/remove: the
    // overlay never visually renders during gallery hydration (real htmx is
    // async, so it does). The CSS rule itself is exercised by
    // test_grid_loading_overlay_is_wired_to_htmx_request, which injects the class.
    // NB event NAMES are the htmx-4 colon-namespaced family (htmx:after:swap,
    // NOT htmx-2's htmx:afterSwap) — the vendored htmx-4 fires ONLY these. A
    // mock firing the legacy names masks dead listeners fleet-wide (the
    // v0.93.66 confirm-shape lesson, second verse).
    el.classList.add("htmx-request");
    fire(el, "htmx:before:request", { elt: el });
    if (target) {
      target.innerHTML = body;
      // The server re-renders the pagination footer alongside the rows (in a
      // real htmx app: an OOB `<nav>` or a wrapping region swap; here the mock
      // updates it directly). Rows + footer come from the SAME query, so they
      // agree on total / current page.
      if (url.split("?")[0] === "/mock/grid/rows") {
        updateGridFooter(target.closest("[data-dz-grid]"), url);
      }
      fire(target, "htmx:after:swap", { elt: target });
      // Real htmx fires after:settle once, after ALL swaps (OOB included)
      // settle — it's the only event where the OOB footer is guaranteed
      // final, so focus restoration listens there, not on after:swap.
      fire(target, "htmx:after:settle", { elt: target });
    }
    el.classList.remove("htmx-request");
    fire(el, "htmx:after:request", { elt: el });
  }

  // Bulk action POST (e.g. Delete). Mirrors the server contract §15: fire
  // htmx:config:request (the REAL htmx-4 shape: config nested under
  // detail.ctx, the body a FormData) so the grid controller injects the
  // selection payload (action + selected_ids + all_matching/excluded + a
  // query echo), then apply it and swap the refreshed rows for the grid's
  // CURRENT query. A real server re-validates permissions + re-scopes to the
  // query and never trusts the client ids; the mock just deletes the named
  // rows from its data.
  // The bulk-payload keys, as distinct from the echoed query params.
  var BULK_KEYS = { action: 1, selected_ids: 1, all_matching_selected: 1, excluded_ids: 1 };
  function applyBulkDelete(params) {
    var doomed;
    if (params.all_matching_selected === "true") {
      // All-matching: re-run the ECHOED query server-side and apply the action
      // to the whole matched set minus the exclusions — the visible ids are
      // informational only (§15: never trust client ids; re-scope the query).
      var q = {};
      Object.keys(params).forEach(function (k) {
        if (!BULK_KEYS[k]) q[k] = params[k];
      });
      var excluded = params.excluded_ids || [];
      doomed = matchedRows(q).map(function (r) { return r.id; })
        .filter(function (id) { return excluded.indexOf(id) < 0; });
    } else {
      doomed = params.selected_ids || [];
    }
    GRID_ROWS = GRID_ROWS.filter(function (r) { return doomed.indexOf(r.id) < 0; });
  }
  function doPost(el) {
    var url = el.getAttribute("hx-post") || "";
    // Real htmx-4 config:request: the config lives under detail.ctx and the
    // request body is form data the listener APPENDS to (there is no
    // detail.parameters object — that was htmx ≤2).
    var fd = new FormData();
    var ctx = { sourceElement: el, request: { method: "post", action: url, body: fd } };
    fire(el, "htmx:config:request", { ctx: ctx });
    // Decode the form body back into the mock server's params (the known
    // array keys via getAll — form encoding repeats them).
    var params = { selected_ids: fd.getAll("selected_ids"), excluded_ids: fd.getAll("excluded_ids") };
    fd.forEach(function (v, k) { if (!(k in params)) params[k] = v; });
    window.__lastBulk = params; // expose the payload for the gallery tests
    if (url.split("?")[0] === "/mock/grid/bulk") applyBulkDelete(params);
    // Two-request pattern: the POST applies the action and returns nothing to
    // swap (a real server answers JSON/204). The button's
    // data-dz-grid-bulk-refresh makes the controller re-fetch rows + footer
    // for the current query after the request settles — the same GET path
    // every other state change uses.
    el.classList.add("htmx-request");
    fire(el, "htmx:before:request", { elt: el });
    el.classList.remove("htmx-request");
    fire(el, "htmx:after:request", { elt: el });
  }

  // Inline-edit commits (dz-grid-edit.js) use a raw fetch — a PUT to the
  // entity's STANDARD update route with a single-field JSON body — not an
  // htmx exchange, so the mock intercepts window.fetch for /mock/grid/<id>.
  // A real server runs its full update gate (RBAC, scope, validation) here.
  var realFetch = window.fetch ? window.fetch.bind(window) : null;
  window.fetch = function (url, opts) {
    var m = typeof url === "string" && url.match(/^\\/mock\\/grid\\/([^/?]+)$/);
    if (m && opts && String(opts.method).toUpperCase() === "PUT") {
      var patch = {};
      try { patch = JSON.parse(opts.body || "{}"); } catch (e) { patch = {}; }
      var hit = null;
      GRID_ROWS.forEach(function (r) { if (r.id === decodeURIComponent(m[1])) hit = r; });
      if (!hit) return Promise.resolve(new Response("{}", { status: 404 }));
      Object.keys(patch).forEach(function (k) {
        if (k in hit) hit[k] = String(patch[k]);
      });
      return Promise.resolve(new Response("{}", {
        status: 200, headers: { "Content-Type": "application/json" }
      }));
    }
    return realFetch ? realFetch(url, opts) : Promise.reject(new Error("no fetch"));
  };

  // dz-grid:refresh — a custom event the grid controller fires on the tbody
  // after a sort/filter change (real htmx catches it via the tbody's hx-trigger;
  // here the mock does). The controller has already rewritten the tbody's hx-get
  // query, so doGet re-reads it and returns the re-ordered rows.
  document.addEventListener("dz-grid:refresh", function (e) {
    var el = e.target;
    if (el && el.matches && el.matches("[hx-get]")) doGet(el);
  });

  // hx-get on focus/input — INPUTS only (e.g. the command palette's
  // `focus once`). Non-input `[hx-get]` affordances (links/buttons) fire on
  // click below, matching real htmx's default trigger for those elements.
  document.addEventListener("focus", function (e) {
    if (e.target.matches && e.target.matches("input[hx-get]")) doGet(e.target);
  }, true);
  document.addEventListener("input", function (e) {
    if (e.target.matches && e.target.matches("[hx-get]")) doGet(e.target);
  });
  // hx-get on click (non-input affordances, e.g. master-detail list links).
  // Respect hx-trigger: an element with an EXPLICIT non-click trigger
  // (load / intersect / input) must NOT re-fire on a click inside it — else
  // selecting a checkbox inside a `load`-hydrated tbody re-fetches and wipes
  // the selection. Real htmx fires these on their declared trigger only; a
  // click-triggered affordance (master-detail/pagination) has no hx-trigger,
  // so its default IS click.
  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest("[hx-get]");
    if (!el || el.matches("input")) return;
    var trig = el.getAttribute("hx-trigger") || "";
    if (trig && trig.indexOf("click") < 0) return;
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
        // A confirmed hx-post issues the real (mock) request — e.g. a bulk
        // action. Other confirmed affordances (the confirm Hyperpart's demo
        // hx-delete, which has no endpoint) just flash a toast.
        if (el.getAttribute("hx-post")) { doPost(el); return; }
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

  // hx-trigger="load": fire once when the element is ready (the grid tbody
  // hydrates its rows this way). Deferred via setTimeout(0): this mock IIFE is
  // concatenated BEFORE the controllers in the built bundle, so a synchronous
  // call here would fire the swap's htmx:after:swap before dz-grid's delegated
  // listener is attached. A macrotask runs after every controller IIFE has
  // executed, so the initial after:swap re-sync lands (matters once rows can
  // arrive pre-selected, e.g. URL-restored selection).
  var fireLoads = function () {
    var els = document.querySelectorAll("[hx-get][hx-trigger]");
    for (var i = 0; i < els.length; i++) {
      if ((els[i].getAttribute("hx-trigger") || "").indexOf("load") >= 0) doGet(els[i]);
    }
  };
  setTimeout(fireLoads, 0);

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
/* minmax(0,1fr) — long unwrapped code lines must scroll inside the code Hyperpart,
   not force the main track wider than the viewport (Pages overflow at 1280). */
.hm-wrap { display: grid; grid-template-columns: 15rem minmax(0, 1fr); min-height: 100vh; }
.hm-wrap.hm-single { display: block; max-width: 72rem; margin-inline: auto; }
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
.hm-main { padding: 3rem 4rem; max-width: 60rem; min-width: 0; }
.hm-hero h1 { font-size: 2.75rem; letter-spacing: -.02em; margin: 0 0 .25rem; }
.hm-hero p { color: var(--colour-text-muted); margin: 0 0 1rem; max-width: 40rem; }
.hm-theme-toggle { margin-left: auto; }
.hm-topbar { display:flex; align-items:center; gap:1rem; margin-bottom: 2rem; }
.hm-comp { border-block-start: 1px solid var(--colour-border); padding-block: 2.5rem; }
.hm-comp h2 { font-size: 1.25rem; margin: 0 0 .25rem; scroll-margin-top: 1rem; }
.hm-comp h3 { font-size: 1.05rem; margin: 1.75rem 0 .5rem; scroll-margin-top: 1rem;
  letter-spacing: -.01em; }
.hm-comp h4 { font-size: var(--text-sm); margin: 1.25rem 0 .4rem;
  color: var(--colour-text); font-weight: var(--weight-semibold); }
.hm-comp .blurb { color: var(--colour-text-muted); margin: 0 0 .75rem; font-size: var(--text-sm); }
/* Linear reference sections (part pages) — no accordions; agent-scrapeable. */
.hm-ref { margin-top: 1.25rem; }
.hm-ref-lead { font-size: var(--text-sm); color: var(--colour-text-muted);
  margin: 0 0 .75rem; max-width: 46rem; line-height: 1.55; }
.hm-ref-mod { font-family: var(--font-mono); font-weight: var(--weight-medium); }
.hm-dialect { font-size: var(--text-sm); color: var(--colour-text-muted);
  margin: 0 0 1.25rem; padding: .55rem .75rem; max-width: 46rem;
  border: 1px solid var(--colour-border); border-radius: var(--radius-md);
  background: var(--colour-surface); line-height: 1.5; }
.hm-dialect code { font-size: .9em; }
/* Glossary terms — human confidence on agent-primary pages (non-critical).
   Product data-tooltip is nowrap; these wrap for short ELI5 paragraphs. */
.hm-term {
  font-style: normal;
  font-weight: inherit;
  border-bottom: 1px dotted color-mix(in oklab, var(--colour-brand) 55%, var(--colour-border));
  cursor: help;
  text-underline-offset: .15em;
}
.hm-term:focus { outline: none; }
.hm-term:focus-visible {
  outline: 2px solid var(--colour-brand);
  outline-offset: 2px;
  border-radius: 2px;
}
.hm-term[data-tooltip]::after {
  white-space: normal;
  width: max(12rem, min(20rem, 70vw));
  max-width: 20rem;
  text-align: start;
  font-weight: var(--weight-regular);
  line-height: 1.4;
  padding: .4rem .55rem;
  box-shadow: var(--shadow-md, 0 4px 16px oklab(0% 0 0 / .18));
}
.hm-term[data-tooltip]:hover::after,
.hm-term[data-tooltip]:focus::after,
.hm-term[data-tooltip]:focus-visible::after {
  opacity: 1;
  transition-delay: 180ms;
}
.hm-dep[data-tooltip] { cursor: help; }
.hm-dep[data-tooltip]::after {
  white-space: normal;
  width: max(10rem, min(16rem, 60vw));
  max-width: 16rem;
  text-align: start;
  font-weight: var(--weight-regular);
  line-height: 1.35;
  padding: .35rem .5rem;
}
.hm-dep[data-tooltip]:hover::after,
.hm-dep[data-tooltip]:focus::after,
.hm-dep[data-tooltip]:focus-visible::after {
  opacity: 1;
  transition-delay: 180ms;
}
.hm-term-hint {
  display: block;
  margin-top: .45rem;
  font-size: var(--text-xs, .75rem);
  color: var(--colour-text-muted);
  opacity: .92;
}
.hm-dogfood {
  font-size: var(--text-sm);
  color: var(--colour-text-muted);
  margin: 0 0 1rem;
  padding: .5rem .75rem;
  max-width: 46rem;
  border-inline-start: 3px solid var(--colour-brand);
  background: var(--colour-brand-soft, var(--colour-surface));
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  line-height: 1.5;
}
.hm-dogfood code { font-size: .9em; }
.hm-hero .breadcrumb { margin-bottom: .5rem; }
.hm-preview { padding: 2rem; border: 1px solid var(--colour-border);
  border-radius: var(--radius-md); background: var(--colour-surface); margin-bottom: .75rem; }
.hm-demo-row { display:flex; gap: 1rem; align-items:center; flex-wrap: wrap; }
.hm-grow { flex: 1 1 0; min-width: 0; }
.hm-pag-list { border: 1px solid var(--colour-border); border-radius: var(--radius-md); overflow: hidden; }
.hm-pag-row { padding: .6rem .9rem; font-size: var(--text-sm); }
.hm-pag-row + .hm-pag-row { border-block-start: 1px solid var(--colour-border); }
.hm-inline { display:inline-flex; align-items:center; gap: .5rem; font-size: var(--text-sm); }
/* Snippet / contract source blocks use the code Hyperpart (.dz-code) — not gallery chrome. */
.hm-anatomy { font-size: .75rem; color: var(--colour-text-muted); margin-top: .6rem;
  padding: .5rem .7rem; border-left: 2px solid var(--colour-brand); background: var(--colour-brand-soft);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0; }
.hm-anatomy code { font-family: var(--font-mono); font-size: .9em; }
.hm-setup { margin: 0 0 1.5rem; border: 1px solid var(--colour-border); border-radius: var(--radius-md); }
.hm-setup > summary { cursor: pointer; padding: .6rem .9rem; font-weight: 600; font-size: var(--text-sm); }
.hm-setup-body { padding: 0 .9rem .75rem; font-size: var(--text-sm); color: var(--colour-text-muted); max-width: 46rem; }
.hm-setup-body code { background: var(--colour-bg); padding: .05rem .3rem; border-radius: var(--radius-sm); }
.hm-setup-body a { color: var(--colour-brand); }
/* Notes prose + contract tables (always visible on part pages). */
.hm-notes { font-size: var(--text-sm); color: var(--colour-text-muted);
  margin: 0; max-width: 46rem; line-height: 1.55; }
.hm-notes code { background: var(--colour-bg); padding: .05rem .3rem; border-radius: var(--radius-sm); }
.hm-contract-table { width: 100%; border-collapse: collapse; font-size: .75rem;
  background: var(--colour-surface); margin: 0 0 .75rem;
  border: 1px solid var(--colour-border); border-radius: var(--radius-md); overflow: hidden; }
.hm-contract-table th, .hm-contract-table td { text-align: left; vertical-align: top;
  padding: .45rem .65rem; border-top: 1px solid var(--colour-border); }
.hm-contract-table thead th { border-top: 0; background: var(--colour-bg); }
.hm-contract-table th { color: var(--colour-text-muted); font-weight: var(--weight-medium);
  text-transform: uppercase; letter-spacing: .04em; font-size: .625rem; }
.hm-contract-table code { font-family: var(--font-mono); }
.hm-verb { color: var(--colour-brand-text); font-weight: var(--weight-semibold); }
.hm-contract-live { margin: .5rem 0 1rem; padding: .75rem;
  border: 1px dashed var(--colour-border); border-radius: var(--radius-md);
  background: var(--colour-surface); }
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
.hm-demo-box { padding: .5rem .75rem; border: 1px dashed var(--colour-border); border-radius: var(--radius-sm); font-size: var(--text-sm); color: var(--colour-text-muted); background: var(--colour-bg); }
.hm-blueprint-page { max-width: 72rem; margin-inline: auto; padding: 2rem 1.5rem 4rem; }
.hm-blueprint-head { margin-block-end: 2rem; }
.hm-blueprint-head a { color: var(--colour-brand); text-decoration: none; font-size: var(--text-sm); }
.hm-blueprint-head h1 { margin: .5rem 0 .25rem; letter-spacing: -.02em; }
.hm-bp-toolbar { display: flex; align-items: center; gap: .5rem; margin-block-end: .75rem; }
.hm-bp-toolbar button { font: inherit; font-size: var(--text-sm); padding: .25rem .75rem; border-radius: var(--radius-sm); border: 1px solid var(--colour-border); background: var(--colour-surface); color: var(--colour-text-muted); cursor: pointer; }
.hm-bp-toolbar button[aria-current="true"] { border-color: var(--colour-brand); color: var(--colour-text); }
.hm-bp-open { margin-inline-start: auto; font-size: var(--text-sm); color: var(--colour-brand); text-decoration: none; }
.hm-bp-stage { display: flex; justify-content: center; background: var(--colour-bg); border: 1px solid var(--colour-border); border-radius: var(--radius-md); padding: .75rem; }
.hm-bp-frame { width: 100%; height: 40rem; max-width: 100%; border: 0; border-radius: var(--radius-sm); background: var(--colour-surface); transition: width var(--duration-base) var(--ease-out); }
.hm-hp-frame { display: block; inline-size: 100%; block-size: 22rem; border: 1px solid var(--colour-border); border-radius: var(--radius-md); background: var(--colour-surface); }
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

    # Blueprints: full-page motifs on their own sub-pages (the Blocks
    # analogue) — nav links out rather than anchoring.
    nav_parts.append('<div class="hm-nav-group">Learn</div>')
    nav_parts.append('<a href="guide">Guide</a>')
    nav_parts.append('<div class="hm-nav-group">Blueprints</div>')
    for bp in BLUEPRINTS:
        nav_parts.append(f'<a href="blueprints/{bp.id}">{_html.escape(bp.title)}</a>')

    theme_js = (
        "function hmTheme(t){document.documentElement.setAttribute('data-theme',t);"
        "localStorage.setItem('hm-theme',t);}"
        "(function(){var t=localStorage.getItem('hm-theme');if(t){"
        "document.documentElement.setAttribute('data-theme',t);"
        "document.addEventListener('DOMContentLoaded',function(){"
        "var r=document.querySelector('input[name=hm-theme][data-hm-theme='+t+']');"
        "if(r)r.checked=true;});}})();"
    )

    part_sections: list = []  # (hyperpart, full-depth section html) — emitted as hyperparts/<id>.html
    agent_docs: list = []  # (id, markdown) — emitted as agents/<id>.md
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
        # framed Hyperparts (fixed-position compositions) render as a
        # STANDALONE live page embedded via iframe — the same treatment
        # the Blueprints got (2026-07-06 Pages-layout breakage class):
        # nothing full-page ever shares a DOM with gallery chrome, and
        # the translateZ containment hack is gone. The snippet below
        # stays the pure partial (partial-is-snippet holds).
        if c.framed:
            hp_dir = out_dir / "hyperparts"
            hp_dir.mkdir(exist_ok=True)
            hp_live_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(c.title)} — live</title>
<link rel="stylesheet" href="../hatchi-maxchi.css">
<script>{theme_js}
// live-update the scheme when the parent gallery toggles it
window.addEventListener('storage', function (e) {{
  if (e.key === 'hm-theme' && e.newValue)
    document.documentElement.setAttribute('data-theme', e.newValue);
}});</script>
</head>
<body>
{sheet}
{live}
<script src="../hatchi-maxchi.js" defer></script>
</body>
</html>"""
            (hp_dir / f"{c.id}-live.html").write_text(hp_live_doc + "\n", encoding="utf-8")
            framed_live = (
                f'<iframe class="hm-hp-frame" src="hyperparts/{c.id}-live.html" '
                f'title="{_html.escape(c.title)} — live preview"></iframe>'
            )
        else:
            framed_live = live
        # The live demo uses the compact one-line `live`; the SNIPPET is
        # pretty-printed so the structure is legible (render-faithful — see
        # site/pretty.py). Sprite-dependency note prepended to the snippet only.
        pretty = pretty_html(live)
        snippet_src = _SPRITE_NOTE + pretty if '<use href="#i-' in live else pretty
        # Dogfood the code Hyperpart: surface + copy; HTML is escaped plain
        # (pretty already legible). Python colour is reserved for contract blocks.
        snippet_block = apply_prefix(
            render_code_block(
                snippet_src,
                language="html",
                aria_label=f"Code for {c.title}",
                highlight=False,
            ),
            prefix,
        )
        tag = f'<span class="hm-tag">{c.tags[0]}</span>' if c.tags else ""
        deps = _dependency_chips(c)
        # Linear part page (no accordions): demo → copy → exchange → how-to
        # → DOM contract → notes → files. Same order as agents/<id>.md.
        framed_live_part = framed_live.replace('src="hyperparts/', 'src="')
        part_sections.append(
            (
                c,
                (
                    f'<section class="hm-comp" id="{c.id}">'
                    f"<h2>{_html.escape(c.title)}{tag}{deps}</h2>"
                    f'<p class="blurb">{apply_prefix(_html.escape(c.blurb), prefix)}</p>'
                    f"{_dialect_html()}"
                    f"{apply_prefix(_dogfood_banner(), prefix)}"
                    f'<div class="hm-preview">{framed_live_part}</div>'
                    f'<section class="hm-ref" id="copy"><h3>Copy this</h3>'
                    f"{snippet_block}</section>"
                    # Linear skeleton on EVERY part (empty states when N/A):
                    # exchange → how-to → DOM contract → notes → files.
                    f"{apply_prefix(_exchanges_html(c), prefix)}"
                    f"{apply_prefix(_guidance_html(c), prefix)}"
                    # Contract Python keeps dual-lock names (data-dz-*).
                    f"{_contracts_html_prefixed(c, prefix)}"
                    f"{_notes_html(c, prefix)}"
                    f"{_anatomy_html(c)}"
                    f"{_composed_of_html(c)}"
                    f"</section>"
                ),
            )
        )
        agent_docs.append((c.id, _agent_md(c, snippet_src)))
        # SIMPLE gallery section (spec decision 5): demo + snippet + link.
        # No exchanges/contract/guidance/anatomy disclosures on the index.
        body_parts.append(
            f'<section class="hm-comp" id="{c.id}">'
            f"<h2>{_html.escape(c.title)}{tag}</h2>"
            f'<p class="blurb">{apply_prefix(_html.escape(c.blurb), prefix)}</p>'
            f'<div class="hm-preview">{framed_live}</div>'
            f"{snippet_block}"
            f'<p class="hm-more"><a href="hyperparts/{c.id}">Full reference: '
            f"contracts, guidance, anatomy →</a></p></section>"
        )

    # opener references the published selectors (dialog.dz-command,
    # .dz-command__input) — reprefix to match the shipped namespace.
    # Command palette opener only — code copy lives in controllers/dz-code.js
    # (code Hyperpart), not gallery chrome.
    opener_js = apply_prefix(
        "document.addEventListener('click',function(e){"
        "var b=e.target.closest('[data-hm-open-command]');if(!b)return;"
        "var dlg=document.querySelector('dialog.dz-command');"
        "if(dlg){dlg.showModal();var i=dlg.querySelector('.dz-command__input');if(i)i.focus();}});",
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
<details class="hm-setup" id="setup">
  <summary>Setup — what a copied snippet needs</summary>
  <div class="hm-setup-body">
    <p><strong>1. The bundle.</strong> One CSS + one JS file, hosted on the
    jsDelivr CDN pinned to a release tag. Every
    <a href="https://github.com/manwithacat/hatchi-maxchi/releases">release</a>'s
    notes carry the ready-to-paste <code>&lt;link&gt;</code>/<code>&lt;script&gt;</code>
    snippet with that version's SRI hashes; or vendor
    <code>dist/hatchi-maxchi.css</code> + <code>dist/hatchi-maxchi.js</code>.</p>
    <p><strong>2. Icons.</strong> Snippets reference icons as
    <code>&lt;svg&gt;&lt;use href="#name"&gt;&lt;/svg&gt;</code> against a symbol
    sheet included <em>once per page</em> — copy
    <a href="sprite_sheet.svg"><code>sprite_sheet.svg</code></a> inline into your
    layout (this page embeds it at the top of <code>&lt;body&gt;</code>).</p>
    <p><strong>3. The server half.</strong> Interactive Hyperparts are htmx4
    partials: your endpoints must return the fragments documented in each
    component's <em>Endpoint contract</em>. Tables/lists that swap with
    <code>hx-swap="innerMorph"</code> need the idiomorph extension. This gallery
    runs a static mock instead of a server, so everything here works offline.</p>
    <p>Full details (theming, prefixing, releases):
    <a href="https://github.com/manwithacat/hatchi-maxchi#readme">the README</a>.</p>
  </div>
</details>
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

    # ── Per-part pages: the canonical deep reference AND the atomic test
    #    fixture (spec 2026-07-10-hm-docs-pedagogy-atomic-testing). Same
    #    bundle/sheet/theme chrome as the index, one part per page.
    hp_dir = out_dir / "hyperparts"
    hp_dir.mkdir(exist_ok=True)
    # Demo assets referenced RELATIVELY by partials (partial-is-snippet means
    # the path can't change per page) must exist at both levels: the index dir
    # and hyperparts/. Source of truth sits next to this script.
    sample_pdf = Path(__file__).resolve().parent / "sample.pdf"
    if sample_pdf.exists():
        (out_dir / "sample.pdf").write_bytes(sample_pdf.read_bytes())
        (hp_dir / "sample.pdf").write_bytes(sample_pdf.read_bytes())
    theme_toggle = (
        '<div class="hm-theme-toggle"><div class="dz-toggle-group" role="radiogroup">'
        '<label><input type="radio" name="hm-theme" data-hm-theme="light" '
        "onclick=\"hmTheme('light')\"><span>Light</span></label>"
        '<label><input type="radio" name="hm-theme" data-hm-theme="dark" '
        "onclick=\"hmTheme('dark')\"><span>Dark</span></label></div></div>"
    )
    for c, section in part_sections:
        part_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(c.title)} — HaTchi-MaXchi</title>
<link rel="stylesheet" href="../hatchi-maxchi.css">
<style>{PAGE_CSS}</style>
<script>{theme_js}</script>
</head>
<body>
{sheet}
<div class="hm-wrap hm-single">
<main class="hm-main">
<div class="hm-topbar">
  <div class="hm-hero">
    {apply_prefix(_part_breadcrumb(c.id, c.title), prefix)}
    <h1>{_html.escape(c.title)}</h1>
  </div>
  {theme_toggle}
</div>
{section}
<footer style="border-block-start:1px solid var(--colour-border);padding-block:2rem;color:var(--colour-text-muted);font-size:var(--text-sm)">
Generated from the design-system sources by <code>site/build_site.py</code>.
The demo above renders the exact snippet — copy it into any htmx4 app.
<strong>Dazzle monorepo:</strong> dual-lock attrs use the <code>data-dz-*</code>
prefix (and <code>dz-*</code> classes when <code>DEFAULT_PREFIX</code> is applied);
this gallery’s demos are unprefixed by design. Do not paste gallery markup into
Dazzle without the package prefixer / dual-lock contract.
</footer>
</main>
</div>
<script src="../hatchi-maxchi.js" defer></script>
<script>{opener_js}</script>
</body>
</html>"""
        (hp_dir / f"{c.id}.html").write_text(part_doc + "\n", encoding="utf-8")

    # Contract modules that are extensions of a parent Hyperpart (no standalone
    # registry id) still need stable gallery URLs — agents deep-link
    # ``/hyperparts/grid-edit`` (or legacy ``.html``) from dual-lock inventories.
    # Emit thin alias pages so GitHub Pages does not 404.
    _CONTRACT_PAGE_ALIASES: dict[str, tuple[str, str]] = {
        # alias_id: (canonical_hyperpart_id, short_reason)
        "grid-edit": (
            "grid",
            "Inline cell editing is a grid extension (contracts/grid_edit.py); "
            "documented on the Data table Hyperpart page.",
        ),
        "grid-cols": (
            "grid",
            "Column visibility is a grid extension (contracts/grid_cols.py); "
            "documented on the Data table Hyperpart page.",
        ),
        "grid-resize": (
            "grid",
            "Column resize is a grid extension (contracts/grid_resize.py); "
            "documented on the Data table Hyperpart page.",
        ),
    }
    for alias_id, (canonical_id, reason) in _CONTRACT_PAGE_ALIASES.items():
        if any(c.id == alias_id for c, _ in part_sections):
            continue  # real page already exists
        if not any(c.id == canonical_id for c, _ in part_sections):
            continue
        alias_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(alias_id)} → {_html.escape(canonical_id)} — HaTchi-MaXchi</title>
<meta http-equiv="refresh" content="0; url={canonical_id}">
<link rel="canonical" href="{canonical_id}">
<link rel="stylesheet" href="../hatchi-maxchi.css">
<style>{PAGE_CSS}</style>
<script>{theme_js}</script>
</head>
<body>
{sheet}
<div class="hm-wrap hm-single">
<main class="hm-main">
<div class="hm-topbar">
  <div class="hm-hero">
    <p class="hm-more"><a href="../">← All Hyperparts</a></p>
    <h1><code>{_html.escape(alias_id)}</code></h1>
  </div>
  {theme_toggle}
</div>
<p class="blurb">{_html.escape(reason)}</p>
<p><a class="button" data-variant="primary" href="{canonical_id}">
Open the <code>{_html.escape(canonical_id)}</code> Hyperpart →</a></p>
<footer style="border-block-start:1px solid var(--colour-border);padding-block:2rem;color:var(--colour-text-muted);font-size:var(--text-sm)">
Alias page generated by <code>site/build_site.py</code> so dual-lock / agent
deep links resolve on GitHub Pages.
</footer>
</main>
</div>
<script src="../hatchi-maxchi.js" defer></script>
</body>
</html>
"""
        (hp_dir / f"{alias_id}.html").write_text(alias_doc + "\n", encoding="utf-8")

    # ── Per-part agent files: one fetchable chunk per part (llms.txt lists them).
    ag_dir = out_dir / "agents"
    ag_dir.mkdir(exist_ok=True)
    for part_id, md in agent_docs:
        (ag_dir / f"{part_id}.md").write_text(md, encoding="utf-8")

    # ── guide.html: the one theory track. Same chrome as a part page.
    guide_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Guide — HaTchi-MaXchi</title>
<link rel="stylesheet" href="hatchi-maxchi.css">
<style>{PAGE_CSS}</style>
<script>{theme_js}</script>
</head>
<body>
{sheet}
<div class="hm-wrap hm-single">
<main class="hm-main">
<div class="hm-topbar">
  <div class="hm-hero">
    <p class="hm-more"><a href="./">← Gallery</a></p>
    <h1>The HaTchi-MaXchi Guide</h1>
    <p>Theory in five short sections — everything embedded below is a live,
    drift-gated artifact, not hand-typed documentation.</p>
  </div>
  {theme_toggle}
</div>
{apply_prefix(_guide_body(), prefix)}
<footer style="border-block-start:1px solid var(--colour-border);padding-block:2rem;color:var(--colour-text-muted);font-size:var(--text-sm)">
Generated from the design-system sources by <code>site/build_site.py</code>.
</footer>
</main>
</div>
<script src="hatchi-maxchi.js" defer></script>
<script>{opener_js}</script>
</body>
</html>"""
    (out_dir / "guide.html").write_text(guide_doc + "\n", encoding="utf-8")

    # ── Blueprint sub-pages ──
    # Each Blueprint renders to blueprints/<id>.html: the SAME bundle/sheet/
    # theme chrome, the composed page live, and a view-source disclosure of
    # the identical string — the page IS the snippet.
    bp_dir = out_dir / "blueprints"
    bp_dir.mkdir(exist_ok=True)
    for bp in BLUEPRINTS:
        bp_live = apply_prefix(expand_icons(bp.partial), prefix)
        bp_snippet_block = apply_prefix(
            render_code_block(
                pretty_html(bp_live),
                language="html",
                aria_label=f"Page source for {bp.title}",
                highlight=False,
            ),
            prefix,
        )
        bp_notes = (
            f'<details class="hm-guidance"><summary>Agent Implementation '
            f'Guidance</summary><div class="hm-notes">{apply_prefix(bp.notes, prefix)}'
            f"</div></details>"
            if bp.notes
            else ""
        )
        composes = " · ".join(f'<a href="../#{cid}">{_html.escape(cid)}</a>' for cid in bp.composes)
        # Standalone LIVE page — the blueprint rendered as a real page
        # (its own browsing context), so fixed positioning, dvh units and
        # media queries behave exactly as shipped. The doc page embeds it
        # via iframe; nothing full-page ever shares a DOM with docs
        # chrome again (the 2026-07-06 Pages-layout breakage class).
        live_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(bp.title)} — live</title>
<link rel="stylesheet" href="../hatchi-maxchi.css">
<script>{theme_js}
// live-update the scheme when the parent gallery toggles it
window.addEventListener('storage', function (e) {{
  if (e.key === 'hm-theme' && e.newValue)
    document.documentElement.setAttribute('data-theme', e.newValue);
}});</script>
</head>
<body>
{sheet}
{bp_live}
<script src="../hatchi-maxchi.js" defer></script>
</body>
</html>"""
        (bp_dir / f"{bp.id}-live.html").write_text(live_doc + "\n", encoding="utf-8")

        bp_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(bp.title)} — HaTchi-MaXchi Blueprint</title>
<link rel="stylesheet" href="../hatchi-maxchi.css">
<style>{PAGE_CSS}</style>
<script>{theme_js}</script>
</head>
<body>
{sheet}
<div class="hm-blueprint-page">
<header class="hm-blueprint-head">
<a href="../">&larr; HaTchi-MaXchi</a>
<h1>{_html.escape(bp.title)}</h1>
<p class="hm-hero-def">{_html.escape(bp.blurb)}</p>
<p class="hm-composed"><strong>Composed of:</strong> {composes}</p>
</header>
<div class="hm-bp-toolbar" role="group" aria-label="Preview viewport">
<button type="button" data-bp-width="390">390</button>
<button type="button" data-bp-width="834">834</button>
<button type="button" data-bp-width="" aria-current="true">Full</button>
<a class="hm-bp-open" href="{bp.id}-live" target="_blank" rel="noopener">Open full page &nearr;</a>
</div>
<div class="hm-bp-stage">
<iframe class="hm-bp-frame" src="{bp.id}-live.html" title="{_html.escape(bp.title)} — live preview"></iframe>
</div>
<script>
document.addEventListener('click', function (e) {{
  var b = e.target.closest('[data-bp-width]');
  if (!b) return;
  var f = document.querySelector('.hm-bp-frame');
  var w = b.getAttribute('data-bp-width');
  f.style.width = w ? w + 'px' : '100%';
  document.querySelectorAll('[data-bp-width]').forEach(function (x) {{
    if (x === b) x.setAttribute('aria-current', 'true');
    else x.removeAttribute('aria-current');
  }});
}});
</script>
<details class="hm-contract"><summary>Page source — the whole page is the snippet</summary>
{bp_snippet_block}</details>
{bp_notes}
</div>
<script src="../hatchi-maxchi.js" defer></script>
</body>
</html>"""
        (bp_dir / f"{bp.id}.html").write_text(bp_doc + "\n", encoding="utf-8")

    # llms.txt (https://llmstxt.org): the LLM-facing map of this site —
    # points agents at the machine-readable sources instead of the HTML.
    (out_dir / "llms.txt").write_text(
        "# HaTchi-MaXchi\n\n"
        "> An htmx4-native design system. The unit of reuse is a Hyperpart: a\n"
        "> server-rendered partial + its endpoint exchange contracts + an\n"
        "> optional vanilla-JS controller. No client framework.\n\n"
        "## Sources\n\n"
        "- [Component registry (source of truth)]"
        "(https://github.com/manwithacat/hatchi-maxchi/blob/main/site/registry.py):"
        " canonical markup + exchange contracts per component — parse this,"
        " don't scrape the gallery\n"
        "- [Contract modules (typed)]"
        "(https://github.com/manwithacat/hatchi-maxchi/tree/main/contracts):"
        " per-part typed ingestion model + DOM contract + executable exemplar;"
        " authoring path in contracts/AUTHORING.md\n"
        "- [AGENTS.md]"
        "(https://github.com/manwithacat/hatchi-maxchi/blob/main/AGENTS.md):"
        " consuming + contributing with a coding agent\n"
        "- [README]"
        "(https://github.com/manwithacat/hatchi-maxchi#readme):"
        " setup, theming, prefixing, releases\n"
        "- [Guide](https://manwithacat.github.io/hatchi-maxchi/guide):"
        " the theory track — hypermedia model, tokens, Hyperpart anatomy,"
        " exchanges & contracts, Blueprints\n\n"
        "## Per-part agent files (one chunk per Hyperpart)\n\n"
        + "".join(
            f"- [{h.title}](https://manwithacat.github.io/hatchi-maxchi/"
            f"agents/{h.id}.md): {h.blurb}\n"
            for h in HYPERPARTS
        )
        + "\n"
        "## Blueprints (full-page layout motifs)\n\n"
        + "".join(
            f"- [{bp.title}](https://manwithacat.github.io/hatchi-maxchi/"
            f"blueprints/{bp.id}): {bp.blurb}\n"
            for bp in BLUEPRINTS
        )
        + "\n"
        "- [CONTRIBUTING]"
        "(https://github.com/manwithacat/hatchi-maxchi/blob/main/CONTRIBUTING.md):"
        " this repo is a synced mirror of the Dazzle monorepo; PRs land via a"
        " credited port\n",
        encoding="utf-8",
    )

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
