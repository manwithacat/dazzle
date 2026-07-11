#!/usr/bin/env python3
"""Lint HaTchi-MaXchi partial HTML for morph-safe hypermedia (decisions 0005–0008).

Shared by pytest gates and the agent-facing CLI. Rules are regex/fixture-level
on author-controlled partials — not a full HTML5 parser (see decision 0008).

Usage::

    python packages/hatchi-maxchi/tools/template_lint.py
    python packages/hatchi-maxchi/tools/template_lint.py --file path.html
    python packages/hatchi-maxchi/tools/template_lint.py --compose grid
    python packages/hatchi-maxchi/tools/template_lint.py --list-compositions

Exit 0 if clean; 1 if issues; 2 on usage/IO error.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]


# ── Patterns (normative for gates) ──────────────────────────────────────────

ALPINE_ATTR_RE = re.compile(
    r"""(?ix)
    \s(?:
        x-data | x-show | x-bind | x-model | x-effect | x-ref | x-for | x-if
        | x-cloak | x-transition | x-text | x-html | x-init | x-ignore
        | x-on:[a-z0-9_.:-]+
        | @[a-z]+(?:\.[a-z0-9_-]+)*
        | :class | :style | :disabled | :value | :href | :src
    )
    (?=[\s=/>])
    """
)

# Attribute name must be exactly `id` — not `data-…-id` (word-boundary alone
# matches the trailing `id=` in `data-dz-grid-row-id="…"`).
ID_ATTR_RE = re.compile(
    r"""(?<![A-Za-z0-9_-])id\s*=\s*(["'])(.*?)\1""",
    re.I | re.DOTALL,
)

UNSTABLE_ID_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("loop.index / for-loop index", re.compile(r"\{\{\s*(?:loop\.)?index0?\s*\}\}")),
    ("bare index placeholder", re.compile(r"\{\{\s*i\s*\}\}")),
    ("Math.random", re.compile(r"Math\.random", re.I)),
    ("uuid()/uuid4()", re.compile(r"uuid4?\s*\(")),
    ("Date.now", re.compile(r"Date\.now")),
    ("random()/rand()", re.compile(r"\brandom\s*\(")),
)

MORPH_TAG_RE = re.compile(
    r"""<([a-zA-Z][\w:-]*)((?:[^>"']|"[^"]*"|'[^']*')*?)\b"""
    r"""hx-swap\s*=\s*(["'])([^"']*[Mm]orph[^"']*)\3"""
    r"""((?:[^>"']|"[^"]*"|'[^']*')*)>""",
    re.DOTALL,
)

JS_INTERP_RE = re.compile(
    r"""(?ix)
    (?:
        \bon[a-z]+\s*=\s*["'][^"']*\{\{
        | \bx-on:[a-z0-9_.:-]+\s*=\s*["'][^"']*\{\{
        | \s@[a-z]+(?:\.[a-z0-9_-]+)*\s*=\s*["'][^"']*\{\{
        | \bhref\s*=\s*["']javascript:[^"']*\{\{
    )
    """
)

ISLAND_MARKER_RE = re.compile(
    r"""(?ix)
    \bdata-(?:hm|dz)-(?:
        island | morph-skip | preserve-boundary | preserve | widget
    )\b
    """
)

THIRD_PARTY_TRIGGERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pdf.js engine (data-dz-pdf-lib)", re.compile(r"\bdata-dz-pdf-lib\s*=")),
    ("<canvas>", re.compile(r"<canvas\b", re.I)),
    ("CDN script URL in markup", re.compile(r"cdn\.jsdelivr\.net|unpkg\.com", re.I)),
)

KNOWN_ISLAND_ROOTS_RE = re.compile(r"""(?ix)\bdata-dz-(?:pdf|widget)\b""")

BRITTLE_HX_TARGET_RE = re.compile(
    r"""(?ix)^\s*(?:
        closest\s+(?:div|span|p|section|article|li|td|th|tr)
        | find\s+
        | this
    )\s*$"""
)

DISPOSABLE_SURFACE_RE = re.compile(
    r"""(?ix)
    (?:
        \b(?:class|data-dz-variant|data-dz-tone)\s*=\s*["'][^"']*
        (?:toast|flash|snackbar)
        | \bdata-(?:dz-|hm-)?(?:toast|flash)\b
    )
    """
)

PERSISTENT_BODY_RE = re.compile(
    r"""(?ix)
    <([a-zA-Z][\w:-]*)
    ((?:[^>"']|"[^"]*"|'[^']*')*?)
    \bdata-(?:dz-)?grid-body\b
    ((?:[^>"']|"[^"]*"|'[^']*')*?)
    >"""
)

OPEN_TAG_RE = re.compile(
    r"""<([a-zA-Z][\w:-]*)((?:[^>"']|"[^"]*"|'[^']*')*)>""",
    re.I,
)


@dataclass(frozen=True)
class LintIssue:
    """One lint finding."""

    code: str
    message: str
    location: str = ""

    def format(self) -> str:
        loc = f"{self.location}: " if self.location else ""
        return f"[{self.code}] {loc}{self.message}"


# ── Helpers ─────────────────────────────────────────────────────────────────


def ids_in(html: str) -> set[str]:
    return {m.group(2) for m in ID_ATTR_RE.finditer(html)}


def id_list(html: str) -> list[str]:
    return [m.group(2) for m in ID_ATTR_RE.finditer(html)]


def attr_refs(html: str, attr: str) -> list[str]:
    out: list[str] = []
    for m in re.finditer(rf"""\b{attr}\s*=\s*(["'])(.*?)\1""", html, re.I | re.DOTALL):
        out.extend(m.group(2).split())
    return out


def _strip_js_comments(src: str) -> str:
    no_block = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//.*?$", "", no_block, flags=re.M)


# ── Single-fragment rules ───────────────────────────────────────────────────


def lint_fragment(html: str, *, location: str = "") -> list[LintIssue]:
    """Run all single-fragment morph-safe rules on one HTML string."""
    issues: list[LintIssue] = []
    loc = location

    for m in ALPINE_ATTR_RE.finditer(html):
        start = max(0, m.start() - 24)
        end = min(len(html), m.end() + 24)
        issues.append(LintIssue("alpine", f"Alpine/reactive attr near …{html[start:end]!r}…", loc))

    for id_val, count in Counter(id_list(html)).items():
        if count > 1:
            issues.append(LintIssue("dup-id", f"id={id_val!r} appears {count} times", loc))

    for m in ID_ATTR_RE.finditer(html):
        id_val = m.group(2)
        for label, pat in UNSTABLE_ID_PATTERNS:
            if pat.search(id_val):
                issues.append(
                    LintIssue(
                        "unstable-id",
                        f"id={id_val!r} looks unstable ({label})",
                        loc,
                    )
                )

    for m in MORPH_TAG_RE.finditer(html):
        tag, pre, _q, swap, post = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        attrs = pre + post
        has_id = bool(re.search(r"\bid\s*=", attrs))
        has_data = bool(re.search(r"\bdata-[a-zA-Z0-9_-]+\s*=", attrs))
        if not (has_id or has_data):
            issues.append(
                LintIssue(
                    "morph-identity",
                    f"<{tag} hx-swap={swap!r}> needs id= or data-*",
                    loc,
                )
            )

    for m in JS_INTERP_RE.finditer(html):
        issues.append(
            LintIssue(
                "js-interp",
                f"template interpolation in JS/event binding: {m.group(0)[:80]!r}",
                loc,
            )
        )

    if re.search(
        r"""<script[^>]*type\s*=\s*["']application/json["']""",
        html,
        re.I,
    ):
        if re.search(
            r"""\bdata-(?:dz-)?(?:col|column|row|grid-col|grid-sort|grid-filter)\b""",
            html,
            re.I,
        ):
            issues.append(
                LintIssue(
                    "json-dup",
                    "application/json script alongside column/row data-*",
                    loc,
                )
            )
        if re.search(
            r"""["'](?:columns|sortable|actions|rows)["']\s*:""",
            html,
            re.I,
        ) and re.search(r"<t[hd]\b|<tr\b|<button\b", html, re.I):
            issues.append(
                LintIssue(
                    "json-dup",
                    "JSON keys columns/sortable/actions/rows while markup renders them",
                    loc,
                )
            )

    id_set = ids_in(html)
    for attr in ("aria-controls", "aria-labelledby", "aria-describedby", "aria-owns"):
        for ref in attr_refs(html, attr):
            if "{{" in ref or ref.startswith("{"):
                continue
            if ref not in id_set:
                issues.append(
                    LintIssue(
                        "aria-ref",
                        f"{attr}={ref!r} has no id={ref!r} in fragment",
                        loc,
                    )
                )
    for ref in attr_refs(html, "for"):
        if "{{" in ref or ref.startswith("{"):
            continue
        if ref not in id_set:
            issues.append(LintIssue("aria-ref", f"label for={ref!r} has no matching id", loc))

    for m in OPEN_TAG_RE.finditer(html):
        tag, attrs = m.group(1).lower(), m.group(2)
        role_m = re.search(r"""\brole\s*=\s*(["'])(.*?)\1""", attrs, re.I)
        role = (role_m.group(2).lower() if role_m else "") or ("dialog" if tag == "dialog" else "")
        if role not in ("dialog", "listbox", "menu", "tree", "tablist"):
            continue
        if re.search(r"\baria-label\s*=", attrs, re.I):
            continue
        if re.search(r"\baria-labelledby\s*=", attrs, re.I):
            continue
        issues.append(
            LintIssue(
                "a11y-name",
                f"<{tag} role={role or tag!r}> lacks aria-label / aria-labelledby",
                loc,
            )
        )

    for m in OPEN_TAG_RE.finditer(html):
        attrs = m.group(2)
        if not re.search(r"\baria-expanded\s*=", attrs, re.I):
            continue
        ctrl = re.search(r"""\baria-controls\s*=\s*(["'])(.*?)\1""", attrs, re.I)
        if not ctrl:
            continue
        for ref in ctrl.group(2).split():
            if "{{" in ref:
                continue
            if ref not in id_set:
                issues.append(
                    LintIssue(
                        "aria-expanded",
                        f"aria-controls={ref!r} without matching id",
                        loc,
                    )
                )

    for m in re.finditer(r"""\bhx-target\s*=\s*(["'])(.*?)\1""", html, re.I):
        target = m.group(2).strip()
        if target.startswith("#") and not re.search(r"[\s.\[>:]", target[1:]):
            tid = target[1:]
            if "{{" not in tid and tid not in id_set:
                issues.append(
                    LintIssue(
                        "hx-target",
                        f"hx-target={target!r} has no id={tid!r}",
                        loc,
                    )
                )
        if BRITTLE_HX_TARGET_RE.match(target):
            issues.append(
                LintIssue(
                    "hx-brittle",
                    f"hx-target={target!r} is brittle ancestry",
                    loc,
                )
            )

    for m in OPEN_TAG_RE.finditer(html):
        attrs = m.group(2)
        if not re.search(r"""\bhx-swap\s*=\s*(["'])[^"']*[Mm]orph[^"']*\1""", attrs):
            continue
        if DISPOSABLE_SURFACE_RE.search(attrs) or DISPOSABLE_SURFACE_RE.search(m.group(0)):
            issues.append(
                LintIssue(
                    "swap-policy",
                    "morph swap on toast/flash-like element",
                    loc,
                )
            )

    for m in PERSISTENT_BODY_RE.finditer(html):
        attrs = m.group(2) + m.group(3)
        swap_m = re.search(r"""\bhx-swap\s*=\s*(["'])(.*?)\1""", attrs, re.I)
        if not swap_m:
            continue
        swap = swap_m.group(2)
        if re.search(r"morph", swap, re.I) or re.search(r"\bnone\b", swap, re.I):
            continue
        issues.append(
            LintIssue(
                "swap-policy",
                f"data-*-grid-body hx-swap={swap!r} — prefer innerMorph",
                loc,
            )
        )

    hits = [label for label, pat in THIRD_PARTY_TRIGGERS if pat.search(html)]
    if hits and not (ISLAND_MARKER_RE.search(html) or KNOWN_ISLAND_ROOTS_RE.search(html)):
        issues.append(
            LintIssue(
                "island",
                f"third-party pattern {hits} without island boundary",
                loc,
            )
        )

    return issues


def lint_js_controller(src: str, *, location: str = "") -> list[LintIssue]:
    """Controllers must not inject Alpine attributes."""
    issues: list[LintIssue] = []
    code = _strip_js_comments(src)
    for m in ALPINE_ATTR_RE.finditer(code):
        issues.append(
            LintIssue("alpine-js", f"Alpine attr in controller: {m.group(0).strip()!r}", location)
        )
    if re.search(r"""setAttribute\s*\(\s*['"]x-""", code):
        issues.append(LintIssue("alpine-js", "setAttribute(x-…)", location))
    return issues


# ── Cross-partial composition ───────────────────────────────────────────────


def lint_composition(
    fragments: list[tuple[str, str]],
    *,
    name: str = "composition",
) -> list[LintIssue]:
    """Lint host + response fragments as one id universe (cross-partial ARIA/targets).

    Each fragment is still checked alone for Alpine/ids/swap policy. Additionally:
    - every ``aria-*`` / ``for`` / ``hx-target="#id"`` ref must resolve in the
      **union** of all fragment ids;
    - the same concrete id must not appear in two different fragments (OOB
      replace of the same node is allowed only when both fragments declare the
      same id once each *and* the response carries ``hx-swap-oob`` — then we
      skip the cross-dup for that id).
    """
    issues: list[LintIssue] = []
    for frag_name, html in fragments:
        issues.extend(lint_fragment(html, location=f"{name}/{frag_name}"))

    union: set[str] = set()
    per_frag: list[tuple[str, set[str], str]] = []
    for frag_name, html in fragments:
        ids = ids_in(html)
        per_frag.append((frag_name, ids, html))
        union |= ids

    # Cross-fragment duplicate ids (except intentional OOB same-id replace)
    id_owners: dict[str, list[str]] = {}
    for frag_name, ids, _html in per_frag:
        for i in ids:
            id_owners.setdefault(i, []).append(frag_name)
    for i, owners in sorted(id_owners.items()):
        if len(owners) < 2:
            continue
        # Allow if every owner fragment that is not the first is OOB for this id
        oob_ok = True
        for frag_name, _ids, html in per_frag:
            if frag_name not in owners:
                continue
            if frag_name == owners[0]:
                continue
            # OOB fragment should mention this id and hx-swap-oob
            if not (
                re.search(rf"""(?<![A-Za-z0-9_-])id\s*=\s*["']{re.escape(i)}["']""", html)
                and re.search(r"hx-swap-oob", html, re.I)
            ):
                oob_ok = False
                break
        if not oob_ok:
            issues.append(
                LintIssue(
                    "cross-dup-id",
                    f"id={i!r} in multiple fragments {owners} without OOB replace",
                    name,
                )
            )

    # Refs resolve in union
    for frag_name, _ids, html in per_frag:
        for attr in ("aria-controls", "aria-labelledby", "aria-describedby", "aria-owns", "for"):
            for ref in attr_refs(html, attr):
                if "{{" in ref or ref.startswith("{"):
                    continue
                if ref not in union:
                    issues.append(
                        LintIssue(
                            "cross-aria",
                            f"{name}/{frag_name}: {attr}={ref!r} not in composition id universe",
                            name,
                        )
                    )
        for m in re.finditer(r"""\bhx-target\s*=\s*(["'])(.*?)\1""", html, re.I):
            target = m.group(2).strip()
            if not target.startswith("#") or re.search(r"[\s.\[>:]", target[1:]):
                continue
            tid = target[1:]
            if "{{" in tid:
                continue
            if tid not in union:
                issues.append(
                    LintIssue(
                        "cross-hx-target",
                        f"{name}/{frag_name}: hx-target={target!r} not in composition",
                        name,
                    )
                )

    return issues


# ── Built-in compositions (host + exchange-shaped fragments) ────────────────

# Minimal server-shaped row set + OOB footer for the grid host (decision 0005/0006).
_GRID_ROWS = """
<tr class="dz-tr-row" id="dz-grid-row-c1" data-dz-grid-row-id="c1">
  <td class="dz-tr-checkbox-cell"><input type="checkbox" data-dz-grid-select data-dz-grid-row-id="c1" aria-label="Select c1"></td>
  <td class="dz-tr-cell" data-dz-col="first">Ada</td>
  <td class="dz-tr-cell" data-dz-col="last">Lovelace</td>
  <td class="dz-tr-cell" data-dz-col="plan">Pro</td>
  <td class="dz-tr-cell" data-dz-col="signed">2024-01-01</td>
</tr>
<tr class="dz-tr-row" id="dz-grid-row-c2" data-dz-grid-row-id="c2">
  <td class="dz-tr-checkbox-cell"><input type="checkbox" data-dz-grid-select data-dz-grid-row-id="c2" aria-label="Select c2"></td>
  <td class="dz-tr-cell" data-dz-col="first">Grace</td>
  <td class="dz-tr-cell" data-dz-col="last">Hopper</td>
  <td class="dz-tr-cell" data-dz-col="plan">Team</td>
  <td class="dz-tr-cell" data-dz-col="signed">2024-02-01</td>
</tr>
"""

_GRID_OOB_FOOTER = """
<nav class="dz-pagination" id="dz-grid-pagination" data-dz-grid-pagination
     data-dz-grid-total="2" hx-swap-oob="true" aria-label="Pagination">
  <span class="dz-pagination-summary">2 rows</span>
  <div class="dz-pagination-pages">
    <button type="button" class="dz-pagination-page is-current" aria-current="page">1</button>
  </div>
</nav>
"""

# Command palette: results fragment that fills aria-controls target.
_COMMAND_RESULTS = """
<button type="button" class="dz-command__item" id="dz-command-item-1" role="option">Open invoices</button>
<button type="button" class="dz-command__item" id="dz-command-item-2" role="option">New customer</button>
"""


def builtin_compositions() -> dict[str, list[tuple[str, str]]]:
    """Named compositions: list of (fragment_name, html). Lazy registry load."""
    sys.path.insert(0, str(PKG))
    sys.path.insert(0, str(PKG / "site"))
    from registry import HYPERPARTS  # noqa: E402

    by_id = {h.id: h for h in HYPERPARTS}
    return {
        "grid": [
            ("host", by_id["grid"].partial),
            ("rows", _GRID_ROWS),
            ("oob-footer", _GRID_OOB_FOOTER),
        ],
        "command": [
            ("host", by_id["command"].partial),
            ("results", _COMMAND_RESULTS),
        ],
    }


def lint_registry() -> list[LintIssue]:
    """Lint every Hyperpart + Blueprint partial and controllers."""
    sys.path.insert(0, str(PKG))
    sys.path.insert(0, str(PKG / "site"))
    from blueprints import BLUEPRINTS  # noqa: E402
    from registry import HYPERPARTS  # noqa: E402

    issues: list[LintIssue] = []
    for c in HYPERPARTS:
        issues.extend(lint_fragment(c.partial, location=c.id))
        # Morph exchange documented?
        morph_swaps = [e for e in c.exchanges if e.swap and re.search(r"morph", e.swap, re.I)]
        if morph_swaps:
            if not re.search(r"innerMorph|outerMorph", c.partial, re.I):
                notes = c.notes or ""
                if not re.search(r"innerMorph|outerMorph|morph", notes, re.I):
                    issues.append(
                        LintIssue(
                            "morph-exchange",
                            "exchanges declare morph but partial/notes lack Morph signal",
                            c.id,
                        )
                    )
        for e in c.exchanges:
            if not e.swap:
                continue
            if re.search(r"morph", e.swap, re.I) and re.search(
                r"toast|flash|snackbar", e.swap, re.I
            ):
                issues.append(
                    LintIssue(
                        "swap-policy",
                        f"exchange morph of toast/flash: {e.swap[:80]!r}",
                        c.id,
                    )
                )
    for bp in BLUEPRINTS:
        issues.extend(lint_fragment(bp.partial, location=f"blueprint:{bp.id}"))

    for path in sorted((PKG / "controllers").glob("dz-*.js")):
        issues.extend(lint_js_controller(path.read_text(encoding="utf-8"), location=path.name))
    return issues


def lint_compositions(names: list[str] | None = None) -> list[LintIssue]:
    comps = builtin_compositions()
    if names is None:
        names = sorted(comps)
    issues: list[LintIssue] = []
    for name in names:
        if name not in comps:
            issues.append(LintIssue("usage", f"unknown composition {name!r}", name))
            continue
        issues.extend(lint_composition(comps[name], name=name))
    return issues


# ── CLI ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Lint HM partial HTML for morph-safe hypermedia (0005–0008)."
    )
    ap.add_argument(
        "--file",
        "-f",
        action="append",
        default=[],
        help="HTML file to lint (repeatable). Default: full registry if none.",
    )
    ap.add_argument(
        "--compose",
        "-c",
        action="append",
        default=[],
        help="Built-in composition name (grid, command). Repeatable.",
    )
    ap.add_argument(
        "--list-compositions",
        action="store_true",
        help="List built-in composition names and exit.",
    )
    ap.add_argument(
        "--registry",
        action="store_true",
        help="Lint all Hyperpart + Blueprint partials and controllers.",
    )
    args = ap.parse_args(argv)

    if args.list_compositions:
        for name in sorted(builtin_compositions()):
            print(name)
        return 0

    issues: list[LintIssue] = []
    ran = False

    if args.file:
        ran = True
        for f in args.file:
            path = Path(f)
            if not path.is_file():
                print(f"error: not a file: {path}", file=sys.stderr)
                return 2
            issues.extend(lint_fragment(path.read_text(encoding="utf-8"), location=str(path)))

    if args.compose:
        ran = True
        issues.extend(lint_compositions(args.compose))

    if args.registry or not ran:
        ran = True
        issues.extend(lint_registry())
        # Default also run compositions when doing full registry (CI-shaped).
        if not args.compose and not args.file:
            issues.extend(lint_compositions())

    if not issues:
        print("OK — no template lint issues")
        return 0

    for issue in issues:
        print(issue.format(), file=sys.stderr)
    print(f"\n{len(issues)} issue(s)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
