"""#1144 part 2: parser tests for `primary_composite:` on
cohort_strip lenses."""

from __future__ import annotations

import textwrap
from typing import Any

import pytest

from dazzle.core.errors import ParseError
from tests.unit.helpers.dsl import region_config

_MEMBER = """
entity Member "Member":
  id: uuid pk
  score: int
"""


def _parse_lens(lens_body: str) -> Any:
    """Parse one lens (`id: ao`, label set) whose remaining keys are ``lens_body``."""
    body = 'member_via: id\nlenses:\n  - id: ao\n    label: "AO breakdown"\n' + textwrap.indent(
        textwrap.dedent(lens_body).strip("\n"), " " * 4
    )
    cfg = region_config(entity=_MEMBER, display="cohort_strip", body=body)
    return cfg.lenses[0]


def test_parses_primary_composite_block() -> None:
    lens = _parse_lens(
        """
        primary_composite:
          separator: " | "
          parts:
            - field: ao1_score
            - field: ao2_score
              tone: good
            - field: ao3_score
              tone: bad
        """
    )
    assert lens.primary == ""
    composite = lens.primary_composite
    assert composite.separator == " | "
    assert [(p.field, p.tone) for p in composite.parts] == [
        ("ao1_score", ""),
        ("ao2_score", "good"),
        ("ao3_score", "bad"),
    ]


def test_default_separator_when_omitted() -> None:
    lens = _parse_lens("primary_composite:\n  parts:\n    - field: a\n    - field: b\n")
    assert lens.primary_composite.separator == " / "


def test_scalar_primary_still_works() -> None:
    """Regression — `primary: <ident>` keeps the existing shape."""
    lens = _parse_lens("primary: score\n")
    assert lens.primary == "score"
    assert lens.primary_composite is None


@pytest.mark.parametrize(
    ("lens_body", "error"),
    [
        pytest.param(
            # IR validator surfaces through the parser wrap.
            "primary: score\nprimary_composite:\n  parts:\n    - field: a\n",
            "mutually exclusive",
            id="primary-and-primary-composite",
        ),
        pytest.param("", "requires exactly one", id="neither-primary-form"),
        pytest.param(
            'primary_composite:\n  separator: " / "\n',
            "non-empty `parts:`",
            id="empty-parts",
        ),
        pytest.param(
            "primary_composite:\n  parts:\n    - tone: good\n      field: a\n",
            "must start with `field:`",
            id="part-entry-not-starting-with-field",
        ),
        pytest.param(
            "primary_composite:\n  bogus: nope\n  parts:\n    - field: a\n",
            "Unknown primary_composite key",
            id="unknown-composite-key",
        ),
    ],
)
def test_rejects_invalid_lens(lens_body: str, error: str) -> None:
    with pytest.raises((ParseError, ValueError), match=error):
        _parse_lens(lens_body)
