"""htmx 2 event names in project client code (#1845).

Dazzle bundles htmx 4, which dispatches colon-namespaced events only
(``htmx:after:swap``, ``htmx:after:settle``, ``htmx:config:request`` …). A
listener written against an htmx 2 camelCase name (``htmx:afterSettle``) or an
htmx 2 ``hx-on::after-swap`` attribute stays in place, never fires, and nothing
reports it. This module is the pure scanner behind the ``dazzle lint`` /
``dazzle validate`` warning: text in, findings out, no file I/O.

The rename map is built from the event names the vendored htmx 4 bundle
(``src/dazzle/page/runtime/static/vendor/htmx.min.js``) dispatches. Where htmx 4
has no equivalent the finding says so (``replacement is None``).
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

SourceKind = Literal["js", "html", "python"]


class HtmxEventRename(BaseModel):
    """One htmx 2 event name and what htmx 4 fires instead."""

    model_config = ConfigDict(frozen=True)

    legacy: str
    replacement: str | None
    note: str = ""


class HtmxEventFinding(BaseModel):
    """An htmx 2 event name found in a project file."""

    model_config = ConfigDict(frozen=True)

    path: str
    line: int
    column: int
    legacy: str
    """The name as written (``htmx:afterSwap``, or ``hx-on::after-swap``)."""
    replacement: str | None
    note: str = ""
    via: Literal["event", "hx-on"] = "event"

    @property
    def message(self) -> str:
        where = f"{self.path}:{self.line}"
        if self.via == "hx-on":
            what = f"`{self.legacy}` handles an htmx 2 event name"
            if self.replacement:
                fix = f"use `hx-on:{self.replacement}` (or `hx-on::{self.replacement[5:]}`)"
            else:
                fix = "htmx 4 has no equivalent event"
        else:
            what = f"`{self.legacy}` is an htmx 2 event name"
            fix = (
                f"htmx 4 fires `{self.replacement}`"
                if self.replacement
                else "htmx 4 has no equivalent event"
            )
        tail = f" ({self.note})" if self.note else ""
        hint = (
            " A host enhancement that runs after a workspace region loads can listen for"
            " Dazzle's `dz:region-loaded` instead."
            if self.replacement in ("htmx:after:swap", "htmx:after:settle")
            else ""
        )
        return (
            f"{where}: {what} and never fires under the bundled htmx 4; {fix}{tail} (#1845).{hint}"
        )


def _r(legacy: str, replacement: str | None, note: str = "") -> HtmxEventRename:
    return HtmxEventRename(legacy=legacy, replacement=replacement, note=note)


_NO_HISTORY_CACHE = "htmx 4 keeps no history snapshot cache"
_ERRORS = "htmx 4 reports every request/swap failure as `htmx:error`"

#: htmx 2 event name → htmx 4. Keys are the exact htmx 2 spellings.
HTMX4_EVENT_RENAMES: dict[str, HtmxEventRename] = {
    r.legacy: r
    for r in (
        _r("htmx:configRequest", "htmx:config:request"),
        _r("htmx:beforeRequest", "htmx:before:request"),
        _r("htmx:beforeSend", "htmx:before:request", "htmx 4 has no separate pre-send event"),
        _r("htmx:afterRequest", "htmx:after:request"),
        _r("htmx:beforeOnLoad", "htmx:before:response"),
        _r("htmx:afterOnLoad", "htmx:after:request"),
        _r("htmx:beforeSwap", "htmx:before:swap"),
        _r("htmx:afterSwap", "htmx:after:swap"),
        _r("htmx:afterSettle", "htmx:after:settle"),
        _r("htmx:oobBeforeSwap", "htmx:before:swap", "out-of-band swaps are ordinary swap tasks"),
        _r("htmx:oobAfterSwap", "htmx:after:swap", "out-of-band swaps are ordinary swap tasks"),
        _r("htmx:oobErrorNoTarget", "htmx:error", _ERRORS),
        _r("htmx:beforeProcessNode", "htmx:before:process"),
        _r("htmx:afterProcessNode", "htmx:after:process"),
        _r("htmx:beforeCleanupElement", "htmx:before:cleanup"),
        _r("htmx:afterCleanupElement", "htmx:after:cleanup"),
        _r("htmx:beforeTransition", "htmx:before:viewTransition"),
        _r("htmx:beforeHistoryUpdate", "htmx:before:history:update"),
        _r("htmx:pushedIntoHistory", "htmx:after:history:push"),
        _r("htmx:replacedInHistory", "htmx:after:history:replace"),
        _r("htmx:historyRestore", "htmx:before:history:restore"),
        _r("htmx:beforeHistorySave", None, _NO_HISTORY_CACHE),
        _r("htmx:historyCacheError", None, _NO_HISTORY_CACHE),
        _r("htmx:historyCacheHit", None, _NO_HISTORY_CACHE),
        _r("htmx:historyCacheMiss", None, _NO_HISTORY_CACHE),
        _r("htmx:historyCacheMissLoad", None, _NO_HISTORY_CACHE),
        _r("htmx:historyCacheMissLoadError", None, _NO_HISTORY_CACHE),
        _r("htmx:historyItemCreated", None, _NO_HISTORY_CACHE),
        _r("htmx:responseError", "htmx:response:error"),
        _r("htmx:sendError", "htmx:error", _ERRORS),
        _r("htmx:swapError", "htmx:error", _ERRORS),
        _r("htmx:targetError", "htmx:error", _ERRORS),
        _r("htmx:onLoadError", "htmx:error", _ERRORS),
        _r("htmx:sendAbort", "htmx:abort"),
        _r("htmx:validateUrl", None, "htmx 4 has no URL-validation event"),
        _r("htmx:noSSESourceError", None, "SSE is native `hx-sse:connect` in htmx 4"),
        _r("htmx:sseError", None, "SSE is native `hx-sse:connect` in htmx 4"),
        _r("htmx:sseOpen", None, "SSE is native `hx-sse:connect` in htmx 4"),
        _r("htmx:sseBeforeMessage", None, "SSE is native `hx-sse:connect` in htmx 4"),
        _r("htmx:sseMessage", None, "SSE is native `hx-sse:connect` in htmx 4"),
        _r("htmx:sseClose", None, "SSE is native `hx-sse:connect` in htmx 4"),
        # Lower-case htmx 2 names that htmx 4 no longer fires.
        _r("htmx:load", "htmx:after:init", "fires once per initialised element"),
        _r("htmx:timeout", "htmx:error", _ERRORS),
        _r("htmx:xhr:abort", None, "htmx 4 uses fetch(), not XMLHttpRequest"),
        _r("htmx:xhr:loadstart", None, "htmx 4 uses fetch(), not XMLHttpRequest"),
        _r("htmx:xhr:loadend", None, "htmx 4 uses fetch(), not XMLHttpRequest"),
        _r("htmx:xhr:progress", None, "htmx 4 uses fetch(), not XMLHttpRequest"),
        _r("htmx:validation:validate", None, "htmx 4 leaves validation to the browser"),
        _r("htmx:validation:failed", None, "htmx 4 leaves validation to the browser"),
        _r("htmx:validation:halted", None, "htmx 4 leaves validation to the browser"),
    )
}

# Lookup by the htmx 2 name with case and dashes folded, for `hx-on` attributes
# (HTML lower-cases attribute names, so htmx 2 docs wrote `hx-on::after-swap`).
_FOLDED: dict[str, HtmxEventRename] = {
    k.lower().replace("-", ""): v for k, v in HTMX4_EVENT_RENAMES.items() if ":" not in k[5:]
}

#: A camelCase htmx 2 name: ``htmx:`` + lower-case word + an upper-case letter.
_CAMEL_RE = re.compile(r"(?<![\w:-])htmx:[a-z]+[A-Z][A-Za-z]*\b")
#: The lower-case htmx 2 names htmx 4 dropped; the colon guards stop
#: ``htmx:load`` matching inside ``htmx:after:load``-style names.
_LOWER_RE = re.compile(
    r"(?<![\w:-])(?:"
    + "|".join(re.escape(k) for k in HTMX4_EVENT_RENAMES if not re.search(r"[A-Z]", k))
    + r")(?![\w:-])"
)
#: ``hx-on::name`` / ``hx-on:htmx:name`` / htmx 2's JSX-safe ``hx-on--name``
#: (also ``data-hx-on``); the event part may carry dashes (htmx 2 kebab
#: spelling) or upper case (as authored). htmx 4 only reads the colon forms, so
#: a dash-form handler is dead whatever its event.
_HX_ON_RE = re.compile(
    r"(?<![\w-])(?:data-)?hx-on(?P<sep>:htmx:|::|-htmx-|--)(?P<event>[A-Za-z][\w-]*)(?=[\s=>/]|$)"
)


def _blank(match: re.Match[str]) -> str:
    """Replace a comment with spaces, keeping its newlines (line numbers hold)."""
    return re.sub(r"[^\n]", " ", match.group(0))


_JS_TOKEN_RE = re.compile(
    r"""//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`""",
    re.DOTALL,
)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _strip_js_comments(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        tok = m.group(0)
        return _blank(m) if tok.startswith(("//", "/*")) else tok

    return _JS_TOKEN_RE.sub(repl, text)


def _position(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    col = offset - (text.rfind("\n", 0, offset) + 1) + 1
    return line, col


def _without_comments(text: str, kind: SourceKind) -> str:
    if kind == "js":
        return _strip_js_comments(text)
    if kind == "html":
        return _HTML_COMMENT_RE.sub(_blank, text)
    return text


def _hx_on_note(rename: HtmxEventRename | None, dash_form: bool) -> str:
    if rename is not None:
        return rename.note
    return (
        "htmx 4 reads only `hx-on:` colon forms" if dash_form else "not an event name htmx 4 fires"
    )


def _hx_on_findings(body: str, path: str) -> list[HtmxEventFinding]:
    findings: list[HtmxEventFinding] = []
    for m in _HX_ON_RE.finditer(body):
        event = m.group("event")
        rename = _FOLDED.get(f"htmx:{event.lower().replace('-', '')}")
        dash_form = m.group("sep").startswith("-")
        if rename is None and not dash_form and event.islower() and "-" not in event:
            continue  # an htmx 4 one-word event (`hx-on::error`, `hx-on::confirm`)
        line, col = _position(body, m.start())
        findings.append(
            HtmxEventFinding(
                path=path,
                line=line,
                column=col,
                legacy=m.group(0),
                replacement=rename.replacement if rename else None,
                note=_hx_on_note(rename, dash_form),
                via="hx-on",
            )
        )
    return findings


def _event_name_findings(body: str, path: str) -> list[HtmxEventFinding]:
    # The look-behinds keep `hx-on:htmx:afterSettle` (an hx-on finding) out.
    findings: list[HtmxEventFinding] = []
    for regex in (_CAMEL_RE, _LOWER_RE):
        for m in regex.finditer(body):
            rename = HTMX4_EVENT_RENAMES.get(m.group(0))
            line, col = _position(body, m.start())
            findings.append(
                HtmxEventFinding(
                    path=path,
                    line=line,
                    column=col,
                    legacy=m.group(0),
                    replacement=rename.replacement if rename else None,
                    note=rename.note if rename else "",
                )
            )
    return findings


def scan_htmx_event_names(text: str, *, path: str, kind: SourceKind) -> list[HtmxEventFinding]:
    """Find htmx 2 event names in one file's text.

    ``kind`` decides comment handling: JS comments and HTML comments are
    ignored (a comment naming the old event is documentation, not a listener);
    Python route files are scanned whole, since their HTML and inline scripts
    live in string literals.
    """
    body = _without_comments(text, kind)
    findings = _hx_on_findings(body, path) + _event_name_findings(body, path)
    return sorted(findings, key=lambda f: (f.line, f.column))


def colon_twin_bound(finding: HtmxEventFinding, text: str) -> bool:
    """Whether ``text`` also names the htmx 4 twin of an htmx 2 finding.

    Framework controllers that must run under htmx 2 and htmx 4 bind both
    names; a finding is only a bug there when the htmx 4 name is missing.
    """
    return finding.replacement is not None and f'"{finding.replacement}"' in text
