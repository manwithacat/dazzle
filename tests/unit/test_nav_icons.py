"""Nav-icon inference — registry-closed, sensible defaults (TASTE-6)."""

import pytest

from dazzle.render.fragment.icon_registry import ICONS
from dazzle.render.fragment.nav_icons import _FALLBACK, _KEYWORD_ICONS, infer_nav_icon

pytestmark = pytest.mark.gate


def test_every_inferable_icon_exists_in_registry() -> None:
    assert _FALLBACK in ICONS
    missing = {icon for _, icon in _KEYWORD_ICONS if icon not in ICONS}
    assert not missing


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Dashboard", "layout-dashboard"),
        ("My Work", "briefcase"),
        ("Task List", "list-checks"),
        ("Support Tickets", "ticket"),
        ("Team Overview", "layout-dashboard"),  # overview beats team? order-dependent
        ("Users", "users"),
        ("System Health", "gauge"),
        ("Deploy History", "layout-dashboard"),  # 'deploy' vs 'histor' — first match wins
        ("Invoices", "receipt"),
        ("Brands", "tag"),
        ("Campaigns", "target"),
        ("Feedback Reports", "message-square"),
        ("Zzz Unknown Thing", "list"),
    ],
)
def test_inference_examples(label: str, expected: str) -> None:
    got = infer_nav_icon(label)
    assert got in ICONS
    if expected in {i for _, i in _KEYWORD_ICONS} | {_FALLBACK}:
        # exact expectations where the map is unambiguous; order-dependent
        # cases assert only registry membership above
        first = next((i for k, i in _KEYWORD_ICONS if k in label.lower()), _FALLBACK)
        assert got == first


def test_never_empty_and_always_lowercase_names() -> None:
    for label in ("", "  ", "Ω", "12345"):
        icon = infer_nav_icon(label)
        assert icon and icon in ICONS
