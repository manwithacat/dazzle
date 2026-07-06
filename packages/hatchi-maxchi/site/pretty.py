"""Pretty-print a gallery snippet — structured, indented HTML (stdlib only).

Partials are authored as one-line strings (compact to write); the copy-paste
SNIPPET re-indents them so the nesting is legible. Rules:

- A **block** element with block children puts each child on its own line,
  indented. A block element with only inline/text content stays on one line.
- **Inline** elements (an icon next to its label, a badge's contents) never
  break — significant whitespace inside a run is preserved verbatim.

Fidelity contract (gated by test_pretty.py): collapsing the inter-tag
whitespace of the output — ``re.sub(r">\\s+<", "><", out)`` — reproduces the
input exactly. So the pretty form renders identically to the one-line demo;
only insignificant (between-block) whitespace is added.
"""

from html.parser import HTMLParser

# Truly inline-flow tags: they never force their parent onto multiple lines,
# and their own content is kept on one line. NB `label`/`li`/`summary` are
# deliberately NOT here — they are block-for-layout (own line) with inline
# content. SVG internals are inline so an icon stays a one-liner.
_INLINE = frozenset(
    {
        "a",
        "span",
        "button",
        "strong",
        "em",
        "b",
        "i",
        "code",
        "kbd",
        "small",
        "abbr",
        "sub",
        "sup",
        "time",
        "mark",
        "u",
        "s",
        "q",
        "cite",
        "svg",
        "use",
        "path",
        "circle",
        "rect",
        "line",
        "polyline",
        "polygon",
        "g",
        "input",
        "br",
        "img",
        "wbr",
    }
)
# HTML void elements — serialized with no closing tag.
_VOID = frozenset({"input", "br", "img", "hr", "meta", "link", "wbr", "col", "area", "source"})


class _Node:
    __slots__ = ("tag", "attrs", "children", "text", "self_close")

    def __init__(self, tag=None, attrs=None, text=None, self_close=False):  # type: ignore[no-untyped-def]
        self.tag = tag
        self.attrs = attrs or []
        self.children: list[_Node] = []
        self.text = text
        self.self_close = self_close

    @property
    def is_text(self) -> bool:
        return self.tag is None and self.text is not None


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node(tag="#root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):  # type: ignore[no-untyped-def]
        node = _Node(tag=tag, attrs=attrs)
        self.stack[-1].children.append(node)
        if tag not in _VOID:  # void tags have no close — don't push
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):  # type: ignore[no-untyped-def]
        self.stack[-1].children.append(_Node(tag=tag, attrs=attrs, self_close=True))

    def handle_endtag(self, tag):  # type: ignore[no-untyped-def]
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):  # type: ignore[no-untyped-def]
        if data:
            self.stack[-1].children.append(_Node(text=data))

    def handle_comment(self, data):  # type: ignore[no-untyped-def]
        self.stack[-1].children.append(_Node(text="<!--" + data + "-->"))


def _has_class(node: _Node, cls: str) -> bool:
    return any(name == "class" and value and cls in value.split() for name, value in node.attrs)


def _multiline(node: _Node) -> bool:
    """True iff the node should put its children on their own lines — i.e. it
    has a block-tag child (or a child that is itself multi-line)."""
    if node.is_text or node.self_close or node.tag in _VOID:
        return False
    # `hm-demo-row` is the gallery's "N variants side by side" container — its
    # children are discrete demo instances, not an inline text run, so break
    # each onto its own line even when the instances (button/badge) are inline.
    if _has_class(node, "hm-demo-row"):
        return True
    for c in node.children:
        if c.is_text:
            continue
        if c.tag not in _INLINE or _multiline(c):
            return True
    return False


# html.parser lowercases attribute names, but SVG attributes are
# case-SENSITIVE — a snippet with `viewbox` renders a broken svg when
# copied. Restore the camelCase forms the spec defines.
_SVG_CASE = {
    "viewbox": "viewBox",
    "preserveaspectratio": "preserveAspectRatio",
    "gradientunits": "gradientUnits",
    "gradienttransform": "gradientTransform",
    "patternunits": "patternUnits",
    "clippathunits": "clipPathUnits",
    "markerwidth": "markerWidth",
    "markerheight": "markerHeight",
    "refx": "refX",
    "refy": "refY",
    "stddeviation": "stdDeviation",
    "tablevalues": "tableValues",
}


def _attrs(attrs) -> str:  # type: ignore[no-untyped-def]
    out = []
    for name, value in attrs:
        name = _SVG_CASE.get(name, name)
        out.append(" " + name if value is None else f' {name}="{value}"')
    return "".join(out)


def _render(node: _Node, depth: int) -> str:
    if node.is_text:
        return node.text or ""
    open_tag = "<" + node.tag + _attrs(node.attrs)
    if node.self_close:
        return open_tag + "/>"
    if node.tag in _VOID:
        return open_tag + ">"
    close_tag = "</" + node.tag + ">"
    if not _multiline(node):
        inner = "".join(_render(c, depth) for c in node.children)
        return open_tag + ">" + inner + close_tag
    child_indent = "  " * (depth + 1)
    lines = [open_tag + ">"]
    lines += [child_indent + _render(c, depth + 1) for c in node.children]
    lines.append("  " * depth + close_tag)
    return "\n".join(lines)


def pretty_html(markup: str) -> str:
    """Re-indent one-line ``markup`` into structured HTML (see module docstring)."""
    builder = _TreeBuilder()
    builder.feed(markup)
    builder.close()
    return "\n".join(_render(c, 0) for c in builder.root.children)
