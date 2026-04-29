"""Tests for #964 — Idiomorph patch skips Alpine event directives.

Background: idiomorph's attribute-morph loop calls
`target.setAttribute(s.name, s.value)` for every attribute on the new
node. Alpine's event-listener shorthand uses `@`-prefixed names (`@click`,
`@click.away`). Chromium enforces the HTML attribute-name production
strictly and rejects `@`, throwing `InvalidCharacterError`. Firefox and
Safari accept it silently.

Fix: install a one-time `beforeAttributeUpdated` callback on
`Idiomorph.defaults.callbacks` that returns `false` for any `@`-prefixed
attribute, signalling idiomorph to skip the setAttribute call.

These tests pin the patch's presence and shape so the fix can't silently
regress.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DZ_ALPINE = REPO_ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "js" / "dz-alpine.js"


def test_idiomorph_patch_present() -> None:
    """The Idiomorph patch IIFE must be present in dz-alpine.js."""
    js = DZ_ALPINE.read_text()
    assert "patchIdiomorphForAlpineDirectives" in js, (
        "Missing the Idiomorph @-attribute skip patch (#964). "
        "Look for `patchIdiomorphForAlpineDirectives` in dz-alpine.js."
    )


def test_idiomorph_patch_targets_at_prefix() -> None:
    """The patch must skip on `@`-prefixed names (charCode 64)."""
    js = DZ_ALPINE.read_text()
    # The patch checks charCodeAt(0) === 64 to identify Alpine event
    # directives without paying for a full string compare each time.
    assert "charCodeAt(0) === 64" in js, (
        "Idiomorph patch must check `charCodeAt(0) === 64` to identify "
        "@-prefixed Alpine event attributes (#964)."
    )


def test_idiomorph_patch_returns_false_to_skip() -> None:
    """The patch must signal skip via `return false` (idiomorph contract)."""
    js = DZ_ALPINE.read_text()
    # Find the patch block by anchoring on its name.
    start = js.find("patchIdiomorphForAlpineDirectives")
    assert start >= 0
    # Patch is short; body fits in ~60 lines.
    block = js[start : start + 3000]
    assert "return false" in block, (
        "Idiomorph patch must `return false` for @-prefixed attrs to skip "
        "the setAttribute call (#964)."
    )


def test_idiomorph_patch_is_idempotent() -> None:
    """Patch must guard against double-install via __dzAlpinePatched flag."""
    js = DZ_ALPINE.read_text()
    assert "__dzAlpinePatched" in js, (
        "Patch must guard against double-installation (idempotency flag — #964)."
    )


def test_idiomorph_patch_chains_existing_callback() -> None:
    """Patch must chain to any pre-existing beforeAttributeUpdated callback."""
    js = DZ_ALPINE.read_text()
    start = js.find("patchIdiomorphForAlpineDirectives")
    assert start >= 0
    block = js[start : start + 3000]
    # Original callback must be captured and called for non-@ attributes.
    assert "original" in block and "original.call" in block, (
        "Patch must capture and chain the original beforeAttributeUpdated "
        "callback so it doesn't shadow other consumers (#964)."
    )
