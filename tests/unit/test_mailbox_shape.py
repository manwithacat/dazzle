"""Linear mailbox-shape check (CodeQL py/polynomial-redos #227).

The leftover-honest regex ``^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$`` is
quadratic on ``!@!.`` + ``!.`` * n. ``is_mailbox_shape`` is O(n).
"""

from __future__ import annotations

import time

import pytest

from dazzle.http.runtime.mailbox_shape import MAILBOX_SHAPE_MAX, is_mailbox_shape


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ada@acme.test", True),
        ("ada+ops@acme.test", True),
        ("ada.lovelace@mail.acme.test", True),
        ("zzz", False),
        ("zzz@ghost", False),
        ("ada@", False),
        ("@acme.test", False),
        ("a@b..c", False),
        ("a@.c", False),
        ("a@b.c.", False),
        ("ada@acme.test extra", False),
        ("", False),
        ("a@" + ("x" * (MAILBOX_SHAPE_MAX + 1)) + ".t", False),
    ],
    ids=[
        "valid",
        "plus-local",
        "nested-domain",
        "no-at",
        "no-dot",
        "local-only",
        "no-local",
        "empty-label",
        "leading-dot",
        "trailing-dot",
        "space",
        "empty",
        "overlong",
    ],
)
def test_is_mailbox_shape(text: str, expected: bool) -> None:
    assert is_mailbox_shape(text) is expected


def test_codeql_redos_payload_is_linear() -> None:
    payload = "!@!." + ("!." * 20_000)
    start = time.perf_counter()
    assert is_mailbox_shape(payload) is False
    assert time.perf_counter() - start < 0.25
