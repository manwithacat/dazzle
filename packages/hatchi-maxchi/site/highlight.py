"""Build-time source highlighting for the code Hyperpart (stdlib only).

Emits ``<span class="dz-code__tok--*">`` wrappers. Prefer this over a
browser highlighter: static Pages, agent-scrapeable HTML, no runtime dep.

Languages:
- ``python`` — keywords, strings, comments, numbers, decorators
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


def highlight_source(source: str, language: str | None = None) -> str:
    """Highlight *source* for *language*; always HTML-escaped at minimum."""
    if not source:
        return ""
    lang = (language or "").strip().lower()
    if lang in ("python", "py"):
        return highlight_python(source)
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

    When *highlight* is True and language is python, tokens are coloured;
    otherwise the body is escaped plain text. Copy uses ``textContent`` so
    spans never leak into the clipboard.
    """
    lang = (language or "").strip()
    body = highlight_source(source, lang if highlight else None)
    label = aria_label or (f"{lang} code" if lang else "Code")
    lang_attr = f' data-dz-language="{html.escape(lang, quote=True)}"' if lang else ""
    lang_chip = (
        f'<span class="dz-code__lang">{html.escape(lang)}</span>'
        if lang
        else '<span class="dz-code__lang"></span>'
    )
    copy_btn = ""
    if copy:
        copy_btn = (
            '<button type="button" class="dz-code__copy" data-dz-code-copy '
            'aria-label="Copy code to clipboard">'
            '<span class="dz-code__copy-idle">Copy</span>'
            '<span class="dz-code__copy-done">Copied</span>'
            "</button>"
        )
    return (
        f'<figure class="dz-code" data-dz-code{lang_attr}>'
        f'<div class="dz-code__meta">{lang_chip}{copy_btn}</div>'
        f'<pre class="dz-code__pre" tabindex="0" role="region" '
        f'aria-label="{html.escape(label, quote=True)}">'
        f'<code class="dz-code__source">{body}</code></pre></figure>'
    )
