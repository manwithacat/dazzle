"""Issue #1018 (v0.67.11): regression tests for the
`cohort_strip_config:` DSL block parser.

The parser pilot for the discriminated typed-config blocks in the
#1015–#1018 region-primitive quartet. Establishes the syntax shape
and the required-field / lens-validation contracts that #1015,
#1016, #1017's config-block parsers mirror.
"""

from __future__ import annotations

from typing import Any

import pytest

from dazzle.core.errors import ParseError
from tests.unit.helpers.dsl import region_config

_MEMBER = """
entity Member "Member":
  id: uuid pk
  name: str(100) required
  status: str(50)
  score: int
"""


def _parse(body: str) -> Any:
    return region_config(entity=_MEMBER, display="cohort_strip", body=body)


def test_parses_minimal_config() -> None:
    cfg = _parse(
        """
        member_via: id
        lenses:
          - id: status
            label: Status
            primary: status
        """
    )
    assert cfg.member_via == "id"
    assert cfg.default_lens == ""  # optional, defaults empty
    assert [(lens.id, lens.label, lens.primary) for lens in cfg.lenses] == [
        ("status", "Status", "status")
    ]
    assert cfg.lenses[0].threshold is None


def test_parses_default_lens_and_multiple_lenses() -> None:
    """Also pins the integer threshold → float coercion."""
    cfg = _parse(
        """
        member_via: id
        default_lens: score
        lenses:
          - id: status
            label: Status
            primary: status
          - id: score
            label: "Score"
            primary: score
            threshold: 80
        """
    )
    assert cfg.default_lens == "score"
    assert [lens.id for lens in cfg.lenses] == ["status", "score"]
    assert cfg.lenses[1].threshold == 80.0


@pytest.mark.parametrize(
    ("label_src", "expected"),
    [
        pytest.param('"Response time (P95)"', "Response time (P95)", id="quoted-with-punctuation"),
        pytest.param("Status", "Status", id="bare-identifier"),
    ],
)
def test_parses_lens_label(label_src: str, expected: str) -> None:
    cfg = _parse(
        f"""
        member_via: id
        lenses:
          - id: x
            label: {label_src}
            primary: score
        """
    )
    assert cfg.lenses[0].label == expected


@pytest.mark.parametrize(
    ("body", "error"),
    [
        pytest.param(
            "lenses:\n  - id: x\n    label: X\n    primary: score\n",
            "member_via",
            id="missing-member-via",
        ),
        pytest.param("member_via: id\n", "at least one lens", id="empty-lenses"),
        pytest.param(
            "member_via: id\ndefault_lens: ghost\n"
            "lenses:\n  - id: status\n    label: Status\n    primary: status\n",
            "default_lens",
            id="default-lens-not-declared",
        ),
        pytest.param(
            "member_via: id\nlenses:\n  - id: x\n    primary: score\n",
            "label",
            id="lens-missing-label",
        ),
        pytest.param(
            "member_via: id\nlenses:\n  - id: x\n    label: X\n",
            "primary",
            id="lens-missing-primary",
        ),
        pytest.param(
            "member_via: id\nbogus: 1\nlenses:\n  - id: x\n    label: X\n    primary: score\n",
            "Unknown cohort_strip_config key",
            id="unknown-top-level-key",
        ),
        pytest.param(
            "member_via: id\nlenses:\n  - id: x\n    label: X\n    primary: score\n    weird: 1\n",
            "Unknown lenses key",
            id="unknown-lens-key",
        ),
        pytest.param(
            "member_via: id\nlenses:\n  id: x\n",
            "must start with `- id:",
            id="lens-entry-without-dash",
        ),
        pytest.param(
            "member_via: id\nlenses:\n  - label: X\n    id: x\n    primary: score\n",
            "must start with `id:`",
            id="lens-entry-starting-with-non-id-key",
        ),
    ],
)
def test_rejects_invalid_config(body: str, error: str) -> None:
    with pytest.raises(ParseError, match=error):
        _parse(body)
