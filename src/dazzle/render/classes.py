"""Single source of truth for CSS class names.

Both renderers (Fragment, Jinja) call into here. Inline class string literals
in either renderer are forbidden by `tests/unit/test_no_inline_classes.py`
(added in Plan 3).
"""

from typing import Protocol


class _ClassyNode(Protocol):
    kind: str


class _TokensProto(Protocol):
    pass  # accessed dynamically via getattr


def classes_for(node: _ClassyNode, tokens: object) -> list[str]:
    """Compute the CSS class list for an IR node, sorted and deduplicated.

    Format: `dz-<kind>` for the base class, `dz-<kind>--<token-name>-<value>`
    for each token-driven modifier. The `dz-` prefix namespaces all framework
    classes; app-local primitives may use their own prefix (e.g. `ak-` for
    Aegismark) but should not emit `dz-` classes.
    """
    base = f"dz-{node.kind}"
    out = {base}

    # Discover token modifiers via dataclass-style attribute introspection.
    # Specific kinds care about specific tokens; the mapping is enumerated here
    # rather than driven by reflection so the surface stays auditable.
    if node.kind == "card":
        for attr in ("radius", "border", "padding", "shadow"):
            value = getattr(tokens, attr, None)
            if value is not None:
                out.add(f"{base}--{attr}-{value}")
    elif node.kind == "button":
        for attr in ("variant", "size"):
            value = getattr(tokens, attr, None)
            if value is not None:
                out.add(f"{base}--{attr}-{value}")
    # Add new kinds here. Each must enumerate the token attrs that affect its
    # class output. Forgetting to add a kind means it gets only the base class
    # (safe default).

    return sorted(out)
