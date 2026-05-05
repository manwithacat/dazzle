"""Single source of truth for element IDs.

Both renderers (Fragment, Jinja) call into here. Inline string literals for
ids in either renderer are forbidden by `tests/unit/test_no_inline_classes.py`
(added in Plan 3).
"""

import re
from typing import Protocol

_VALID_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_KNOWN_KINDS = frozenset(
    {
        "surface",
        "region",
        "fragment",
        "field",
        "action",
        "form",
        "row",
    }
)


class IRNode(Protocol):
    kind: str
    name: str
    parent: "IRNode | None"


def id_for(node: IRNode) -> str:
    """Compute the DOM id for an IR node.

    Format: `<kind>-[<parent.name>-]<node.name>`. Walks the parent chain so a
    region's id includes its enclosing surface's name; this is what makes
    htmx targets stable across Fragment/Jinja boundary crossings.
    """
    if node.kind not in _KNOWN_KINDS:
        raise ValueError(f"unknown ir kind: {node.kind!r}")
    if not _VALID_NAME.match(node.name):
        raise ValueError(f"invalid name {node.name!r} for ir kind {node.kind!r}")

    # Walk parent chain inner->outer, then reverse so the final order reads
    # outer->inner; the node's own name comes last so the id terminates with
    # the leaf (matches htmx target conventions).
    ancestors: list[str] = []
    parent = node.parent
    while parent is not None:
        if not _VALID_NAME.match(parent.name):
            raise ValueError(f"invalid parent name {parent.name!r}")
        ancestors.append(parent.name)
        parent = parent.parent
    ancestors.reverse()

    return "-".join([node.kind, *ancestors, node.name])
