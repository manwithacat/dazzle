"""Exposed control-icon gate (issue #1841, INV-11).

An ``<svg>`` inside a button or link is either decorative (the control is named
by its text or ``aria-label``) or the control's only name. Decorative icons need
``aria-hidden="true"``; otherwise screen readers announce an unnamed graphic
inside a named control (IBM ``svg_graphics_labelled``). A named icon carries
``role="img"`` + ``aria-label`` or a ``<title>`` child — the scanner accepts
either. Wired into :func:`dazzle.testing.ux.contract_checker.check_contract`.
"""

from __future__ import annotations

from html.parser import HTMLParser

_CONTROL_TAGS = frozenset({"button", "a"})
# HTML void elements — no end tag, so never pushed on a scanner's stack.
VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)


class _ExposedControlIconScanner(HTMLParser):
    """Flag each ``<svg>`` under a button/link that is neither hidden from the
    accessibility tree nor named."""

    def __init__(self) -> None:
        super().__init__()
        # (tag, hidden-from-a11y-tree, control descriptor or None)
        self._stack: list[tuple[str, bool, str | None]] = []
        # Open <svg>s: the enclosing control's descriptor when the icon is
        # exposed and unnamed so far (a <title> child names it), else None.
        self._open_svg: list[str | None] = []
        self.found: list[str] = []

    def _hidden(self) -> bool:
        return any(hidden for _tag, hidden, _ctl in self._stack)

    def _control(self) -> str | None:
        for _tag, _hidden, ctl in reversed(self._stack):
            if ctl is not None:
                return ctl
        return None

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs_list)
        hidden = attrs.get("aria-hidden") == "true"
        if tag == "title" and self._open_svg:
            self._open_svg[-1] = None
        if tag == "svg":
            control = self._control()
            named = bool(attrs.get("aria-label") or attrs.get("aria-labelledby"))
            exposed = control is not None and not hidden and not self._hidden() and not named
            self._open_svg.append(control if exposed else None)
        if tag in VOID_TAGS:
            return
        ctl: str | None = None
        if tag in _CONTROL_TAGS:
            label = (attrs.get("aria-label") or "").strip()
            ctl = f'<{tag} aria-label="{label}">' if label else f"<{tag}>"
            if attrs.get("class"):
                ctl = ctl[:-1] + f' class="{attrs["class"]}">'
        self._stack.append((tag, hidden, ctl))

    def handle_startendtag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs_list)
        if tag == "svg":
            self._close_svg()
        if tag not in VOID_TAGS and self._stack and self._stack[-1][0] == tag:
            self._stack.pop()

    def _close_svg(self) -> None:
        if not self._open_svg:
            return
        control = self._open_svg.pop()
        if control is not None:
            self.found.append(control)

    def handle_endtag(self, tag: str) -> None:
        if tag == "svg":
            self._close_svg()
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                return


def find_exposed_control_icons(html: str) -> list[str]:
    """Return a descriptor of the enclosing control for each ``<svg>`` inside a
    ``<button>`` or ``<a>`` that is neither ``aria-hidden`` (itself or an
    ancestor) nor named (``aria-label`` / ``aria-labelledby`` / ``<title>``).
    ``[]`` means every control icon on the page is decorative-and-hidden or
    named. Gate for #1841 (INV-11).
    """
    scanner = _ExposedControlIconScanner()
    scanner.feed(html)
    return scanner.found
