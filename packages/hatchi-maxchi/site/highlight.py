"""Build-time source highlighting for the code Hyperpart (stdlib only).

Emits ``<span class="dz-code__tok--*">`` wrappers. Prefer this over a
browser highlighter: static Pages, agent-scrapeable HTML, no runtime dep.

Languages:
- ``python`` / ``py`` — keywords, strings, comments, numbers, decorators
- ``html`` / ``htm`` / ``xml`` — tags, attributes, values, comments
- anything else / ``None`` — HTML-escaped plain text (still prettified by caller)

Token class names use the ``dz-`` namespace so ``apply_prefix`` rewrites them
for the unprefixed gallery.
"""

from __future__ import annotations

import html
import re

# Python 3.12-ish keyword set (stdlib keyword.kwlist without importing if frozen)
_PY_KEYWORDS = frozenset(
    {
        "False",
        "None",
        "True",
        "and",
        "as",
        "assert",
        "async",
        "await",
        "break",
        "class",
        "continue",
        "def",
        "del",
        "elif",
        "else",
        "except",
        "finally",
        "for",
        "from",
        "global",
        "if",
        "import",
        "in",
        "is",
        "lambda",
        "nonlocal",
        "not",
        "or",
        "pass",
        "raise",
        "return",
        "try",
        "while",
        "with",
        "yield",
        "match",
        "case",
        "type",
    }
)

_PY_BUILTINS = frozenset(
    {
        "abs",
        "all",
        "any",
        "bool",
        "dict",
        "enumerate",
        "filter",
        "float",
        "format",
        "getattr",
        "hasattr",
        "int",
        "isinstance",
        "len",
        "list",
        "map",
        "max",
        "min",
        "object",
        "open",
        "print",
        "range",
        "repr",
        "reversed",
        "set",
        "sorted",
        "str",
        "sum",
        "super",
        "tuple",
        "type",
        "zip",
        "self",
        "cls",
    }
)

# Tokenizer: one of string / comment / decorator / number / name / other
_PY_TOKEN_RE = re.compile(
    r"(?P<str>"
    r'"""[\s\S]*?"""|'
    r"'''[\s\S]*?'''|"
    r'"(?:\\.|[^"\\])*"|'
    r"'(?:\\.|[^'\\])*'"
    r")"
    r"|(?P<cmt>#[^\n]*)"
    r"|(?P<dec>@[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<num>\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)"
    r"|(?P<name>\b[A-Za-z_][A-Za-z0-9_]*\b)"
    r"|(?P<op>[^\s#@A-Za-z0-9_'\"]+)"
    r"|(?P<ws>\s+)",
)


def _span(kind: str, text: str) -> str:
    if not text:
        return ""
    if kind == "plain":
        return html.escape(text)
    return f'<span class="dz-code__tok--{kind}">{html.escape(text)}</span>'


def highlight_python(source: str) -> str:
    """Return HTML (no outer tags) with token spans for Python source."""
    out: list[str] = []
    pos = 0
    for m in _PY_TOKEN_RE.finditer(source):
        if m.start() > pos:
            out.append(_span("plain", source[pos : m.start()]))
        if m.lastgroup == "str":
            out.append(_span("str", m.group()))
        elif m.lastgroup == "cmt":
            out.append(_span("cmt", m.group()))
        elif m.lastgroup == "dec":
            out.append(_span("dec", m.group()))
        elif m.lastgroup == "num":
            out.append(_span("num", m.group()))
        elif m.lastgroup == "name":
            name = m.group()
            if name in _PY_KEYWORDS:
                out.append(_span("kw", name))
            elif name in _PY_BUILTINS:
                out.append(_span("builtin", name))
            else:
                out.append(_span("name", name))
        elif m.lastgroup == "op":
            out.append(_span("op", m.group()))
        else:  # ws
            out.append(html.escape(m.group()))
        pos = m.end()
    if pos < len(source):
        out.append(_span("plain", source[pos:]))
    return "".join(out)


# Tag open / full comment / text. Tag interiors are tokenised separately.
_HTML_CHUNK_RE = re.compile(
    r"(?P<cmt><!--[\s\S]*?-->)"
    r"|(?P<tag><[!?/]?[A-Za-z][\w:.-]*"  # <div  </div  <!DOCTYPE  <?xml
    r"(?:\s+[A-Za-z_:][\w:.-]*(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\"'=<>`]+))?)*"
    r"\s*/?>)"
    r"|(?P<text>[^<]+)"
    r"|(?P<lt><)",  # stray <
)

_HTML_TAG_RE = re.compile(
    r"^(?P<br_open></?|[!?])"
    r"(?P<name>[A-Za-z][\w:.-]*)"
    r"(?P<body>[\s\S]*?)"
    r"(?P<br_close>/?>)$"
)

_HTML_ATTR_RE = re.compile(
    r"(?P<ws>\s+)"
    r"|(?P<attr>[A-Za-z_:][\w:.-]*)"
    r"|(?P<eq>=)"
    r"|(?P<val>\"[^\"]*\"|'[^']*'|[^\s\"'=<>`]+)"
    r"|(?P<other>.)"
)


def _highlight_html_tag(tag: str) -> str:
    """Colour one ``<…>`` token: brackets, name, attrs, values."""
    # Normalise <?xml … ?> / <!DOCTYPE …> openers into br_open + name.
    if tag.startswith("<!"):
        # <!-- already handled as comment; DOCTYPE / other declarations
        m = re.match(r"^(<!/?)\s*([A-Za-z][\w:.-]*)([\s\S]*?)(/?>)$", tag)
        if not m:
            return _span("op", tag)
        br_open, name, body, br_close = m.groups()
    elif tag.startswith("<?"):
        m = re.match(r"^(<\?)\s*([A-Za-z][\w:.-]*)([\s\S]*?)(\?>)$", tag)
        if not m:
            return _span("op", tag)
        br_open, name, body, br_close = m.groups()
    else:
        m = _HTML_TAG_RE.match(tag)
        if not m:
            return _span("op", tag)
        br_open, name, body, br_close = (
            m.group("br_open"),
            m.group("name"),
            m.group("body"),
            m.group("br_close"),
        )

    parts = [_span("op", br_open), _span("kw", name)]
    for am in _HTML_ATTR_RE.finditer(body):
        if am.lastgroup == "ws":
            parts.append(html.escape(am.group()))
        elif am.lastgroup == "attr":
            # data-*/hx-* look like “directives” — same token family as decorators
            attr = am.group()
            kind = "dec" if attr.startswith(("data-", "hx-", "x-", "aria-")) else "name"
            parts.append(_span(kind, attr))
        elif am.lastgroup == "eq":
            parts.append(_span("op", "="))
        elif am.lastgroup == "val":
            parts.append(_span("str", am.group()))
        else:
            parts.append(_span("op", am.group()))
    parts.append(_span("op", br_close))
    return "".join(parts)


def highlight_html(source: str) -> str:
    """Return HTML (no outer tags) with token spans for HTML/XML markup."""
    out: list[str] = []
    pos = 0
    for m in _HTML_CHUNK_RE.finditer(source):
        if m.start() > pos:
            out.append(_span("plain", source[pos : m.start()]))
        if m.lastgroup == "cmt":
            out.append(_span("cmt", m.group()))
        elif m.lastgroup == "tag":
            out.append(_highlight_html_tag(m.group()))
        elif m.lastgroup == "text":
            out.append(_span("plain", m.group()))
        else:  # stray <
            out.append(_span("op", m.group()))
        pos = m.end()
    if pos < len(source):
        out.append(_span("plain", source[pos:]))
    return "".join(out)


def highlight_source(source: str, language: str | None = None) -> str:
    """Highlight *source* for *language*; always HTML-escaped at minimum."""
    if not source:
        return ""
    lang = (language or "").strip().lower()
    if lang in ("python", "py"):
        return highlight_python(source)
    if lang in ("html", "htm", "xml", "svg"):
        return highlight_html(source)
    return html.escape(source)


def render_code_block(
    source: str,
    *,
    language: str | None = None,
    aria_label: str | None = None,
    copy: bool = True,
    highlight: bool = True,
) -> str:
    """Emit a full ``dz-code`` figure. *source* is plain text (not pre-escaped).

    When *highlight* is True and language is python or html, tokens are coloured;
    otherwise the body is escaped plain text. Copy uses ``textContent`` so
    spans never leak into the clipboard.
    """
    lang = (language or "").strip()
    body = highlight_source(source, lang if highlight else None)
    label = aria_label or (f"{lang} code" if lang else "Code")
    lang_attr = f' data-dz-language="{html.escape(lang, quote=True)}"' if lang else ""
    # Meta bar is part of the Hyperpart contract: lang (optional) + copy.
    # Copy uses margin-inline-start:auto so it stays trailing without absolute
    # positioning (absolute drifted left on nested part-page containers).
    lang_chip = f'<span class="dz-code__lang">{html.escape(lang)}</span>' if lang else ""
    copy_btn = ""
    if copy:
        copy_btn = (
            '<button type="button" class="dz-code__copy" data-dz-code-copy '
            'aria-label="Copy code to clipboard">'
            '<span class="dz-code__copy-idle">Copy</span>'
            '<span class="dz-code__copy-done">Copied</span>'
            "</button>"
        )
    meta = (
        f'<div class="dz-code__meta">{lang_chip}{copy_btn}</div>' if (lang_chip or copy_btn) else ""
    )
    return (
        f'<figure class="dz-code" data-dz-code{lang_attr}>'
        f"{meta}"
        f'<pre class="dz-code__pre" tabindex="0" role="region" '
        f'aria-label="{html.escape(label, quote=True)}">'
        f'<code class="dz-code__source">{body}</code></pre></figure>'
    )
