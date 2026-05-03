"""Test #960 layer 3 — x-flip Alpine directive registration.

The directive lives in dz-alpine.js and provides FLIP-style
animations for list reorders. Pin its presence so a refactor
can't silently drop it from the bundle, breaking any template
that relies on `x-flip` + `data-flip-key`.

Browser-level behaviour (rect diff, transform application) is
not covered here — those depend on real DOM APIs. This test
just guards the registration path + the reduced-motion guard.
"""

from __future__ import annotations

from pathlib import Path

import pytest

DZ_ALPINE_JS = Path(__file__).resolve().parents[2] / "src/dazzle_ui/runtime/static/js/dz-alpine.js"


@pytest.fixture(scope="module")
def js() -> str:
    assert DZ_ALPINE_JS.is_file(), f"dz-alpine.js not found at {DZ_ALPINE_JS}"
    return DZ_ALPINE_JS.read_text()


def test_flip_directive_registered(js: str) -> None:
    """Alpine.directive('flip', ...) call must be present so x-flip
    in templates resolves to our handler rather than a no-op."""
    assert 'Alpine.directive("flip"' in js


def test_flip_directive_uses_mutation_observer(js: str) -> None:
    """The implementation must observe child-list mutations on the
    container — that's how it picks up Alpine x-for re-renders."""
    assert "MutationObserver" in js
    assert "childList: true" in js


def test_flip_directive_reads_data_flip_key(js: str) -> None:
    """Children are matched across re-renders by `data-flip-key`.
    Without this dataset access, surviving children can't be paired
    with their before-positions."""
    assert "flipKey" in js


def test_flip_directive_honours_reduced_motion(js: str) -> None:
    """Users with `prefers-reduced-motion: reduce` should still get
    correct DOM state but no animation — the directive must check
    matchMedia and skip the transform path."""
    assert "prefers-reduced-motion: reduce" in js


def test_flip_directive_uses_spring_token(js: str) -> None:
    """The transition timing references the Open Props spring token
    expansion from #960 layer 1. If the token gets renamed, this
    test catches the mismatch instead of users seeing linear motion."""
    assert "var(--ease-spring-2)" in js
    assert "var(--duration-base)" in js


def test_flip_directive_applies_inverse_then_identity(js: str) -> None:
    """The two-step pattern (apply inverse, rAF, clear to identity)
    is what makes FLIP smooth — without rAF the browser batches both
    style writes and the transition never plays."""
    assert "requestAnimationFrame" in js
    assert "translate(" in js


def test_directives_listed_in_module_header(js: str) -> None:
    """File header documents the public API — `x-flip` should be
    listed alongside the dz* components."""
    assert "x-flip" in js
