"""Test #960 layer 1 — Open Props animation tokens are present in tokens.css.

The dist build reads tokens.css and concatenates it into dazzle.min.css.
If a refactor accidentally drops the spring ladder or named animation
shorthands, components consuming `var(--animation-fade-in)` would
silently fall back to no animation.

Pin each token name so the bundle drift test catches the regression.
"""

from __future__ import annotations

from pathlib import Path

import pytest

TOKENS_CSS = Path(__file__).resolve().parents[2] / "src/dazzle_ui/runtime/static/css/tokens.css"


@pytest.fixture(scope="module")
def css() -> str:
    assert TOKENS_CSS.is_file(), f"tokens.css not found at {TOKENS_CSS}"
    return TOKENS_CSS.read_text()


SPRING_LADDER = [
    "--ease-spring-1",
    "--ease-spring-2",
    "--ease-spring-3",
    "--ease-spring-4",
    "--ease-spring-5",
]


@pytest.mark.parametrize("name", SPRING_LADDER)
def test_spring_ladder_present(css: str, name: str) -> None:
    """The full spring-1..5 ladder is required so components can pick the
    smallest bounce that conveys the affordance (issue #960 layer 1)."""
    assert f"{name}:" in css, f"missing token {name}"


ELASTIC_LADDER = ["--ease-elastic-1", "--ease-elastic-2", "--ease-elastic-3"]


@pytest.mark.parametrize("name", ELASTIC_LADDER)
def test_elastic_ladder_present(css: str, name: str) -> None:
    assert f"{name}:" in css, f"missing token {name}"


ANIMATION_TOKENS = [
    "--animation-fade-in",
    "--animation-fade-out",
    "--animation-scale-up",
    "--animation-scale-down",
    "--animation-slide-in-up",
    "--animation-slide-in-down",
    "--animation-slide-in-left",
    "--animation-slide-in-right",
    "--animation-slide-out-up",
    "--animation-slide-out-down",
    "--animation-slide-out-left",
    "--animation-slide-out-right",
    "--animation-shake-x",
    "--animation-pulse",
]


@pytest.mark.parametrize("name", ANIMATION_TOKENS)
def test_animation_token_present(css: str, name: str) -> None:
    """Each named animation shorthand must declare a value the keyframe
    block below resolves. Missing tokens silently fall back to no
    animation in templates that consume them."""
    assert f"{name}:" in css, f"missing token {name}"


KEYFRAMES = [
    "dz-fade-in",
    "dz-fade-out",
    "dz-scale-up",
    "dz-scale-down",
    "dz-slide-in-up",
    "dz-slide-in-down",
    "dz-slide-in-left",
    "dz-slide-in-right",
    "dz-slide-out-up",
    "dz-slide-out-down",
    "dz-slide-out-left",
    "dz-slide-out-right",
    "dz-shake-x",
    "dz-pulse",
]


@pytest.mark.parametrize("name", KEYFRAMES)
def test_keyframe_definition_present(css: str, name: str) -> None:
    """Every animation token references a `dz-` prefixed keyframe; the
    keyframe block must define each one. The prefix avoids collisions
    with project-defined keyframes in customer apps."""
    assert f"@keyframes {name}" in css, f"missing keyframe {name}"


def test_animation_tokens_reference_existing_keyframes(css: str) -> None:
    """Catch typos: every `--animation-*` value's first identifier
    must match a defined `@keyframes dz-*` block. Walking the rules
    one by one would be fragile, so just assert the canonical pairs."""
    pairs = {
        "--animation-fade-in": "dz-fade-in",
        "--animation-slide-out-up": "dz-slide-out-up",
        "--animation-scale-up": "dz-scale-up",
        "--animation-shake-x": "dz-shake-x",
    }
    for token, keyframe in pairs.items():
        idx = css.find(f"{token}:")
        assert idx != -1, f"{token} not declared"
        # Look for the keyframe name within ~100 chars after the token decl.
        slice_ = css[idx : idx + 100]
        assert keyframe in slice_, f"{token} should reference {keyframe}"


def test_reduced_motion_guard_present(css: str) -> None:
    """The reduced-motion media query must collapse animations to
    near-instant for users who request reduced motion (#960 polish)."""
    assert "prefers-reduced-motion: reduce" in css
    assert "animation-duration: 0.01ms" in css
