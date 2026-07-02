"""Render compiled scope predicates as plain English for the spec brief.

The scope algebra is closed (``dazzle.core.ir.predicates``), so this is a
deterministic, total rendering — every node kind has an arm, and anything
genuinely unrenderable falls back to a neutral phrase rather than raising.
The output is stakeholder prose: no column/SQL vocabulary.

Integrity rule: the rendering must not claim MORE than the predicate enforces.
When in doubt, prefer the vaguer-but-true phrase.
"""

from __future__ import annotations

import re
from typing import Any

# CompOp values → connective phrases. Equality reads as "is"; the rest are
# spelled out. IN/NOT_IN read naturally over a literal list.
_OP_PHRASES: dict[str, str] = {
    # Keyed by BOTH the CompOp member name (EQ, NEQ, …) and its symbol value
    # ("=", "!=") — whichever shape reaches us renders the same phrase.
    "eq": "is",
    "=": "is",
    "neq": "is not",
    "!=": "is not",
    "gt": "is greater than",
    ">": "is greater than",
    "lt": "is less than",
    "<": "is less than",
    "gte": "is at least",
    ">=": "is at least",
    "lte": "is at most",
    "<=": "is at most",
    "in": "is one of",
    "not_in": "is not one of",
    "is": "is",
    "is_not": "is not",
}


def _op_phrase(op: Any) -> str:
    for candidate in (getattr(op, "name", None), getattr(op, "value", None), str(op)):
        if candidate and str(candidate).lower() in _OP_PHRASES:
            return _OP_PHRASES[str(candidate).lower()]
    return str(getattr(op, "value", op))


def _humanize(identifier: str) -> str:
    """``assessment_event`` → ``assessment event``; ``BlockList`` → ``block
    list``; strip a trailing ``_id``."""
    if identifier.endswith("_id") and len(identifier) > 3:
        identifier = identifier[:-3]
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", identifier)
    return spaced.replace("_", " ").lower()


def _user_attr_phrase(user_attr: str) -> str:
    """``entity_id`` is the persona's own backing record (``backed_by``) — to a
    reader that is simply "the signed-in user"; any other attribute is theirs."""
    if user_attr == "entity_id":
        return "the signed-in user"
    return f"the user's {_humanize(user_attr)}"


def _value_phrase(value: Any) -> str:
    """Render a ``ValueRef`` as prose."""
    if value is None:
        return "empty"
    if getattr(value, "literal_null", False):
        return "empty"
    if getattr(value, "current_user", False):
        return "the signed-in user"
    if getattr(value, "current_tenant", False):
        return "the current tenant"
    user_attr = getattr(value, "user_attr", None)
    if user_attr:
        return _user_attr_phrase(str(user_attr))
    literal = getattr(value, "literal", None)
    if isinstance(literal, (list, tuple)):
        return ", ".join(repr(x) for x in literal)
    if literal is None:
        return "empty"
    return repr(literal)


def _render_column_check(predicate: Any) -> str:
    subject = f"its {_humanize(str(predicate.field))}"
    return f"{subject} {_op_phrase(predicate.op)} {_value_phrase(predicate.value)}"


def _render_user_attr_check(predicate: Any) -> str:
    return (
        f"its {_humanize(str(predicate.field))} {_op_phrase(predicate.op)} "
        f"{_user_attr_phrase(str(predicate.user_attr))}"
    )


def _render_path_check(predicate: Any) -> str:
    path = [str(seg) for seg in (predicate.path or [])]
    if len(path) >= 2:
        *hops, leaf = path
        subject = f"the {_humanize(leaf)} of its {' → '.join(_humanize(h) for h in hops)}"
    elif path:
        subject = f"its {_humanize(path[0])}"
    else:
        subject = "a linked record"
    return f"{subject} {_op_phrase(predicate.op)} {_value_phrase(predicate.value)}"


def _render_exists_check(predicate: Any) -> str:
    target = _humanize(str(predicate.target_entity))
    if getattr(predicate, "negated", False):
        return f"no {target} record links it to the user"
    return f"a {target} record links it to the user"


def _render_poly_path_check(predicate: Any) -> str:
    type_value = getattr(predicate, "type_value", None)
    sub = predicate_to_english(getattr(predicate, "sub", None))
    return f"when it refers to a {_humanize(str(type_value))}, {sub}"


def _render_bool_composite(predicate: Any) -> str:
    op_val = getattr(getattr(predicate, "op", None), "value", None) or str(
        getattr(predicate, "op", "")
    )
    joiner = " or " if str(op_val).lower() == "or" else " and "
    parts = [predicate_to_english(c) for c in (getattr(predicate, "children", None) or [])]
    parts = [p for p in parts if p]
    if not parts:
        return "all records"
    if len(parts) == 1:
        return parts[0]
    return "(" + joiner.join(parts) + ")"


def _render_column_ref_check(predicate: Any) -> str:
    return (
        f"its {_humanize(str(predicate.field))} {_op_phrase(predicate.op)} "
        f"its own {_humanize(str(predicate.other_field))}"
    )


_RENDERERS: dict[str, Any] = {
    "tautology": lambda _p: "all records",
    "contradiction": lambda _p: "no records",
    "column_check": _render_column_check,
    "user_attr_check": _render_user_attr_check,
    "path_check": _render_path_check,
    "exists_check": _render_exists_check,
    "poly_path_check": _render_poly_path_check,
    "bool_composite": _render_bool_composite,
    "column_ref_check": _render_column_ref_check,
}


def predicate_to_english(predicate: Any) -> str:
    """Best-effort plain-English rendering of a compiled scope predicate."""
    if predicate is None:
        return "all records"
    renderer = _RENDERERS.get(getattr(predicate, "kind", None) or "")
    if renderer is None:
        # Unknown node — vaguer-but-true fallback; never overclaim, never raise.
        return "a declared access rule applies"
    return str(renderer(predicate))
