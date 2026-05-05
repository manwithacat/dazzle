"""Single source of truth for CSS class names.

Both renderers (Fragment, Jinja) call into here. Inline class string literals
in either renderer are forbidden by `tests/unit/test_no_inline_classes.py`
(added in Plan 3).
"""

from typing import Protocol


class _ClassyNode(Protocol):
    kind: str


# Per-kind token attribute mapping. Each entry: kind -> token attribute names
# whose values become CSS modifier classes. Add new kinds here as primitives
# are introduced. A kind not present in this map gets only the base `dz-<kind>`
# class — the safe default.
_KIND_TOKENS: dict[str, tuple[str, ...]] = {
    "card": ("radius", "border", "padding", "shadow"),
    "button": ("variant", "size"),
}


def classes_for(node: _ClassyNode, tokens: object) -> list[str]:
    """Compute the CSS class list for an IR node, sorted and deduplicated.

    Format: `dz-<kind>` for the base class, `dz-<kind>--<token-name>-<value>`
    for each token-driven modifier. The `dz-` prefix namespaces all framework
    classes; app-local primitives may use their own prefix (e.g. `ak-` for
    Aegismark) but should not emit `dz-` classes.
    """
    base = f"dz-{node.kind}"
    out = {base}
    for attr in _KIND_TOKENS.get(node.kind, ()):
        value = getattr(tokens, attr, None)
        if value is not None:
            out.add(f"{base}--{attr}-{value}")
    return sorted(out)
