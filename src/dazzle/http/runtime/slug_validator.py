"""Slug validation for the ``slug:`` field primitive (#1288 Phase 1+validator).

The bare ``slug`` field type generates a Pydantic ``AfterValidator`` that
enforces the rules below. Per-field overrides (``min_length:``,
``max_length:``, ``reserved_from:``) are out of scope for this phase —
projects that need a reserved-word check can layer their own validator
via the post-build hook from #1290.

Rules enforced here:
    * Length 3-40 inclusive
    * Lowercase ASCII letters, digits, and ASCII hyphens only
    * Must start and end with a letter or digit (no leading/trailing hyphen)
    * No double-hyphens anywhere

These mirror the constants used by AegisMark's ``pipeline/tenant/validation.py``
which we are upstreaming.
"""

from __future__ import annotations

import re

SLUG_MIN_LEN: int = 3
SLUG_MAX_LEN: int = 40

# Format: starts with [a-z0-9], optional middle run of [a-z0-9-] up to
# SLUG_MAX_LEN-2 chars, ends with [a-z0-9]. The 2-char minimum is handled by
# the alternation: a bare ``[a-z0-9]`` for length 1 is rejected by the length
# check before the regex runs, but the pattern itself accepts length 1 strings
# for the single-char case. The double-hyphen check runs separately so the
# error message is more specific than a generic regex failure.
_SLUG_RE = re.compile(rf"^[a-z0-9](?:[a-z0-9-]{{0,{SLUG_MAX_LEN - 2}}}[a-z0-9])?$")
_DOUBLE_HYPHEN_RE = re.compile(r"--")


def validate_slug(value: str) -> str:
    """Validate *value* as a slug; return it unchanged on success.

    Raises ``ValueError`` with a specific reason on any rule failure.
    Designed to be used as a Pydantic ``AfterValidator`` so the framework
    enforces the rules at the request boundary without each entity having
    to wire its own validator.
    """
    if not isinstance(value, str):
        raise ValueError("slug must be a string")
    if len(value) < SLUG_MIN_LEN:
        raise ValueError(f"slug must be at least {SLUG_MIN_LEN} characters")
    if len(value) > SLUG_MAX_LEN:
        raise ValueError(f"slug must be at most {SLUG_MAX_LEN} characters")
    if _DOUBLE_HYPHEN_RE.search(value):
        raise ValueError("slug must not contain double hyphens")
    if not _SLUG_RE.match(value):
        raise ValueError(
            "slug must be lowercase letters, digits, and hyphens; "
            "must start and end with a letter or digit"
        )
    return value
