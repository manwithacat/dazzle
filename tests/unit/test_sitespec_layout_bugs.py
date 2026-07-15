"""Regression gates for CyFuture pilot layout bugs #1590 / #1591.

These are pure CSS-contract assertions against HM ``sitespec.css`` so the
framework dual-lock cannot regress into app-level ``custom.css`` workarounds.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SITESPEC = ROOT / "packages" / "hatchi-maxchi" / "components" / "sitespec.css"

pytestmark = pytest.mark.gate


@pytest.fixture(scope="module")
def css() -> str:
    return SITESPEC.read_text(encoding="utf-8")


def test_steps_equal_columns_not_flex_grow_crush(css: str) -> None:
    """#1590: desktop step items use equal flex basis; connector is not flex:1."""
    # Equal-width columns (basis 0 so siblings share space evenly).
    assert re.search(
        r"\.dz-step-item(?:\s*,\s*\.dz-step-item\.is-not-last)?\s*\{[^}]*flex:\s*1\s+1\s+0",
        css,
        re.DOTALL,
    )
    # Connector on desktop is absolutely positioned (out of flex flow).
    assert ".dz-step-item.is-not-last .dz-step-connector" in css
    assert re.search(
        r"\.dz-step-item\.is-not-last\s+\.dz-step-connector\s*\{[^}]*position:\s*absolute",
        css,
        re.DOTALL,
    )
    # Must not reintroduce connector-as-flex:1 sibling crusher.
    connector_blocks = re.findall(
        r"\.dz-step-connector\s*\{[^}]+\}",
        css,
        re.DOTALL,
    )
    for block in connector_blocks:
        assert "flex: 1" not in block.replace("flex: 1 1 0", "")
        assert "flex:1" not in block.replace("flex:1 1 0", "")


def test_nav_items_wrap_on_narrow(css: str) -> None:
    """#1591: site nav / nav-items wrap instead of overflowing horizontally."""
    assert re.search(r"\.dz-nav-items\s*\{[^}]*flex-wrap:\s*wrap", css, re.DOTALL)
    assert re.search(
        r"@media\s*\(max-width:\s*767px\)\s*\{[^}]*\.dz-site-nav\s*\{[^}]*flex-wrap:\s*wrap",
        css,
        re.DOTALL,
    )
    assert "min(72rem, 100%)" in css or "min(72rem,100%)" in css
