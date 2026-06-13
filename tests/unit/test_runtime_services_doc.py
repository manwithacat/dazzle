"""Doc-contract test for `RuntimeServices` (#1121).

The class docstring is the authoritative reference for extension
authors writing custom renderers / primitives / route overrides —
which framework services they may legitimately reach for and what
each one carries. If the docstring drifts away from the actual
attribute set, extension authors get bad context.

Two contracts pinned here:

1. Every dataclass field on `RuntimeServices` is mentioned in the
   docstring. Adding a new attribute without documenting it fails
   this test — the framework's commitment is that what's surfaced
   IS the public API, not "whatever happens to be in `__init__`."

2. The docstring explicitly names the required-vs-optional split,
   so extension authors can branch on `None` correctly for optional
   services without having to read the source.
"""

from __future__ import annotations

import dataclasses

from dazzle.back.runtime.services import RuntimeServices


def test_every_field_is_mentioned_in_the_docstring() -> None:
    """All public dataclass fields must appear in the class docstring
    by name. Drift in either direction (field added without doc,
    doc mentions a field that was removed) fails this test."""
    doc = RuntimeServices.__doc__ or ""
    fields = [f.name for f in dataclasses.fields(RuntimeServices)]

    missing = [f for f in fields if f not in doc]
    assert not missing, (
        f"RuntimeServices fields not documented in the class docstring: "
        f"{missing}. Add each to the docstring (with type, purpose, and "
        f"required-vs-optional note) so extension authors have a complete "
        f"reference. See #1121."
    )


def test_docstring_names_required_vs_optional_split() -> None:
    """Extension authors need to know which services they can rely
    on (always present) vs which they must branch on `None` for.
    The docstring must explicitly call out both groups."""
    doc = RuntimeServices.__doc__ or ""
    assert "Required services" in doc, (
        "RuntimeServices docstring must explicitly label the always-"
        "present services so extension authors know what they can rely on."
    )
    assert "Optional services" in doc, (
        "RuntimeServices docstring must explicitly label the maybe-None "
        "services so extension authors know to branch on None."
    )


def test_docstring_points_at_worked_example() -> None:
    """Discoverability gate from #1117 — when an extension author
    reads the RuntimeServices source to figure out what's in scope,
    they should land on the worked example."""
    doc = RuntimeServices.__doc__ or ""
    assert "fixtures/custom_renderer" in doc, (
        "RuntimeServices docstring must link to the worked example so "
        "extension authors land on a real implementation, not just an "
        "abstract attribute list."
    )
