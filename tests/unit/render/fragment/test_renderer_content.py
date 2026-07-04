"""Renderer support for Icon/Badge/EmptyState/Skeleton.

Text and Heading are covered by test_renderer_skeleton."""

from dazzle.render.fragment import (
    Badge,
    EmptyState,
    Icon,
    Skeleton,
    Text,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def test_render_icon() -> None:
    r = FragmentRenderer()
    out = r.render(Icon(name="check"))
    # "check" is in the vendored registry -> inline SVG, no client hydration
    assert "<svg" in out and 'aria-hidden="true"' in out
    assert "dz-icon--size-md" in out


def test_render_badge() -> None:
    r = FragmentRenderer()
    out = r.render(Badge(label="new", variant="success"))
    assert "new" in out
    assert "dz-badge--variant-success" in out


def test_render_empty_state() -> None:
    r = FragmentRenderer()
    out = r.render(EmptyState(title="Nothing here", description="Add an item"))
    assert "Nothing here" in out
    assert "Add an item" in out


def test_render_empty_state_with_action() -> None:
    """EmptyState.action is typed as object — emit if present."""
    r = FragmentRenderer()
    out = r.render(
        EmptyState(
            title="Empty",
            description="Add one",
            action=Text("placeholder"),  # would be Button after Task 21; using Text for now
        )
    )
    assert "placeholder" in out


def test_render_skeleton_lines() -> None:
    r = FragmentRenderer()
    out = r.render(Skeleton(lines=4))
    # adopts the HM skeleton Hyperpart: N text-shaped `dz-skeleton` lines
    # stacked by `dz-skeleton-lines` (the old `dz-skeleton__line` child had
    # no CSS rule — invisible lines).
    assert out.count('data-dz-shape="text"') == 4
    assert 'class="dz-skeleton-lines"' in out
