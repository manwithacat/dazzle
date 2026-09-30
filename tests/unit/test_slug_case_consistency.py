"""A mixed-case surface/workspace name must slug identically everywhere (#1717).

Why this exists
---------------
The canonical rule is ``dazzle.core.strings.entity_slug`` —
``name.lower().replace("_", "-")``. Five sites re-derived it, and three omitted
the ``.lower()`` entirely:

- ``http/converters/surface_converter.py`` — the URL router
- ``page/converters/workspace_converter.py`` — the route builder
- ``agent/missions/discovery.py`` — the ``url_hint`` handed to agents
- ``http/runtime/page_routes.py`` — the plural slug, built one line below an
  ``entity_slug`` call
- ``testing/playwright_codegen.py`` — ``f"/{entity}"`` routes

A mixed-case name therefore produced a **registered route that the breadcrumb
link did not match** — the dead-link class of #1421/#1426. No example uses a
mixed-case name today, so this is a latent gap rather than a live break.

Why this is a scoped source pin and not a general gate
------------------------------------------------------
The obvious move is to broaden ``test_no_inline_entity_slug`` to also flag a bare
``.replace("_", "-")``. Measured against the tree, **5 of the 7 hits were
legitimately different rules** — CLI flags (``--param-name``), locale codes
(``en_GB`` → ``en-GB``), free-text search candidates, and word-splitting for a
label. A gate that fires on those gets disabled inside a week, so it was not
shipped. Catching the partial form in general needs a URL-context-aware check,
which is separate work.

Instead this pins the five *specific* production call sites, where the partial
pattern is unambiguous because the result is interpolated into a URL. That is
precise, has no false positives, and fails loudly if any of them regresses.

What this does catch
--------------------
A re-introduced bare ``.replace("_", "-")`` in any of the five files.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dazzle.core.strings import entity_slug

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
_SRC = REPO / "src" / "dazzle"

# Files where `.replace("_", "-")` unambiguously builds a URL segment.
_URL_SLUG_SITES = [
    "http/converters/surface_converter.py",
    "page/converters/workspace_converter.py",
    "agent/missions/discovery.py",
    "http/runtime/page_routes.py",
    "testing/playwright_codegen.py",
]

# A `.replace("_", "-")` that is NOT the full canonical formula.
_PARTIAL_SLUG = re.compile(r"""\.replace\((['"])_\1, (['"])-\2\)""")

_DIVERGENT_NAMES = ["Task_List", "HR_Records", "MixedCase", "ALLCAPS"]


@pytest.mark.parametrize("name", _DIVERGENT_NAMES)
def test_entity_slug_lowercases(name: str) -> None:
    """The canonical helper is the reference every other site must match."""
    assert entity_slug(name) == name.lower().replace("_", "-")
    assert entity_slug(name) == entity_slug(name).lower()


@pytest.mark.parametrize("rel", _URL_SLUG_SITES)
def test_url_sites_do_not_rederive_the_slug(rel: str) -> None:
    """No URL-building site re-derives `entity_slug` inline."""
    path = _SRC / rel
    assert path.is_file(), f"{rel} moved — re-check the #1717 site list"
    text = path.read_text(encoding="utf-8")
    offenders = [
        f"{rel}:{lineno}"
        for lineno, line in enumerate(text.splitlines(), start=1)
        if _PARTIAL_SLUG.search(line) and ".lower()" not in line
    ]
    assert not offenders, (
        "A URL-building site re-derives the slug without `.lower()`, so a "
        "mixed-case name registers a route the breadcrumb link will not match "
        "(#1717). Use `dazzle.core.strings.entity_slug(name)`:\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("rel", _URL_SLUG_SITES)
def test_url_sites_use_the_canonical_helper(rel: str) -> None:
    """Each of the five actually calls `entity_slug`, so the pin above cannot be
    satisfied by simply deleting the slug."""
    text = (_SRC / rel).read_text(encoding="utf-8")
    assert "entity_slug" in text, (
        f"{rel} no longer references entity_slug — confirm the #1717 fix is still needed"
    )


# --- Detector self-tests -----------------------------------------------------
#
# A clean tree only proves nothing currently matches; it cannot prove the matcher
# matches what it was written for. These pin the detector's real behaviour,
# including its limits.
#
# The important finding from writing them: the *pattern* is deliberately
# over-broad, and the safety comes entirely from the file scoping. `_PARTIAL_SLUG`
# matches `--param-name` and `en-GB` just as readily as a URL slug. That is why
# the broad version of this gate was abandoned — a repo-wide rule would fire on
# every CLI flag and locale code in the tree.


# Built by concatenation so the synthetic source lines contain the literal
# characters the regex looks for, without this file being unreadable.
_Q, _US, _DASH = chr(39), chr(95), chr(45)
_REPLACE_2 = f".replace({_Q}{_US}{_Q}, {_Q}{_DASH}{_Q})"


def _bare_replace_line(receiver: str) -> str:
    """A source line with a bare underscore->dash replace and no `.lower()`."""
    return f"        x = {receiver}{_REPLACE_2}"


def test_pattern_matches_the_footgun() -> None:
    """The exact form the three original sites used: a URL built from a bare
    ``.replace`` with no ``.lower()``."""
    assert _PARTIAL_SLUG.search(_bare_replace_line("surface.name")), (
        "detector must match a bare slug re-derivation"
    )


def test_pattern_matches_the_plural_form() -> None:
    """`page_routes.py` derived a plural slug the same way."""
    assert _PARTIAL_SLUG.search(_bare_replace_line("to_api_plural(_entity.name)"))


def test_pattern_is_intentionally_over_broad() -> None:
    """Pins the known limitation, so nobody widens the pattern to "fix" it.

    The pattern cannot tell a URL slug from a CLI flag or a locale code. All of
    these match; the *file list* is what keeps the gate precise.
    """
    assert _PARTIAL_SLUG.search(_bare_replace_line("param_name")), "CLI flag"
    assert _PARTIAL_SLUG.search(_bare_replace_line("en_GB")), "locale code"
    canonical = f"    return entity_name.lower(){_REPLACE_2}"
    assert _PARTIAL_SLUG.search(canonical), (
        "the canonical formula also matches; the file list is what excludes it"
    )


def test_gate_scope_excludes_cli_flag_and_locale_files() -> None:
    """The two files that would false-positive are deliberately not in scope.

    If someone adds `mcp/cli_help.py` or `i18n/display_locale.py` to
    `_URL_SLUG_SITES`, this fails — which is the guard rail against re-widening.
    """
    assert "mcp/cli_help.py" not in _URL_SLUG_SITES
    assert "i18n/display_locale.py" not in _URL_SLUG_SITES
    assert "core/docs_gen.py" not in _URL_SLUG_SITES


def test_every_scoped_site_still_uses_the_canonical_helper() -> None:
    """The scoping is only trustworthy if the five files really do use it."""
    for rel in _URL_SLUG_SITES:
        text = (_SRC / rel).read_text(encoding="utf-8")
        assert "entity_slug" in text, f"{rel} does not reference entity_slug"
