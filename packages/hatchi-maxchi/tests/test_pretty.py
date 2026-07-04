"""Snippet pretty-printer gates (site/pretty.py).

The critical contract: pretty-printing only adds *insignificant* (between-block)
whitespace — so a pasted snippet renders identically to the one-line demo.
Verified by collapsing the output's inter-tag whitespace and requiring the
exact source back, for every real partial (in its expanded/prefixed form).
"""

import re
import sys
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(PKG / "site"))

from build import DEFAULT_PREFIX, apply_prefix  # noqa: E402
from build_site import expand_icons  # noqa: E402
from pretty import pretty_html  # noqa: E402
from registry import HYPERPARTS  # noqa: E402

pytestmark = pytest.mark.gate


def _collapse(s: str) -> str:
    return re.sub(r">\s+<", "><", s)


def _live(hp) -> str:  # type: ignore[no-untyped-def]
    return apply_prefix(expand_icons(hp.partial), DEFAULT_PREFIX)


@pytest.mark.parametrize("hp", HYPERPARTS, ids=lambda h: h.id)
def test_pretty_is_render_faithful(hp) -> None:  # type: ignore[no-untyped-def]
    live = _live(hp)
    assert _collapse(pretty_html(live)) == live, (
        f"{hp.id}: pretty-print changed significant whitespace — the snippet "
        "would not render like the demo"
    )


def test_pretty_indents_block_structure() -> None:
    card = next(h for h in HYPERPARTS if h.id == "card")
    out = pretty_html(_live(card))
    assert "\n  <div" in out, "nested block elements should be indented onto their own lines"


def test_pretty_keeps_inline_runs_together() -> None:
    # a badge is all-inline: its icon span + label stay on ONE line (no break)
    badge = next(h for h in HYPERPARTS if h.id == "badge")
    out = pretty_html(_live(badge))
    assert "</svg></span>Approved</span>" in out.replace("\n", "|"), (
        "inline runs (icon + label) must not be broken across lines"
    )
