"""Console-domain regression gates — no browser needed.

1. Every ``dz-*`` class used in the registry's canonical HTML has a rule
   in the built bundle (the "no unstyled published markup" contract).
2. The committed gallery CSS equals a fresh ``build_css()`` — catches
   editing component CSS without rebuilding the gallery.
3. The prefix transform is total: no ``dz-`` survives ``--prefix ax-``.
"""

import re
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(PKG / "site"))

from build import build_css, build_js  # noqa: E402
from registry import COMPONENTS  # noqa: E402

# Structural wrappers that intentionally carry no rule of their own
# (styled via inheritance / parent selectors). Additions here need a
# comment in the component's CSS explaining why.
SEMANTIC_ONLY = {
    "dz-alert__body",
    "dz-empty-state__description",
}


def _used_classes() -> set[str]:
    used: set[str] = set()
    for c in COMPONENTS:
        for m in re.finditer(r'class="([^"]+)"', c.html):
            used.update(cls for cls in m.group(1).split() if cls.startswith("dz-"))
    return used


def test_every_registry_class_has_a_rule() -> None:
    css = build_css()
    missing = sorted(
        cls for cls in _used_classes() if f".{cls}" not in css and cls not in SEMANTIC_ONLY
    )
    assert not missing, (
        f"registry HTML uses classes with no rule in the bundle: {missing}. "
        "Style them or (if genuinely structural) add to SEMANTIC_ONLY with a comment."
    )


def test_semantic_only_list_is_not_stale() -> None:
    css = build_css()
    stale = sorted(cls for cls in SEMANTIC_ONLY if f".{cls}" in css)
    assert not stale, f"now styled — remove from SEMANTIC_ONLY: {stale}"


def test_committed_dist_is_current() -> None:
    """dist/ is committed so jsDelivr can serve it straight from the repo
    at any tag (https://cdn.jsdelivr.net/gh/manwithacat/hatchi-maxchi@TAG/dist/…).
    A stale committed dist would be served to CDN users — fail loudly."""
    css = (PKG / "dist" / "hatchi-maxchi.css").read_text(encoding="utf-8")
    js = (PKG / "dist" / "hatchi-maxchi.js").read_text(encoding="utf-8")
    assert css == build_css() and js == build_js(), (
        "dist/ is stale — run `python build.py` and commit (CDN users get the committed files)"
    )
    for font in ("geist-var.woff2", "geist-mono-var.woff2", "OFL.txt"):
        assert (PKG / "dist" / "fonts" / font).exists(), f"dist/fonts/{font} missing"


def test_committed_gallery_css_is_current() -> None:
    committed = (PKG / "site" / "hatchi-maxchi.css").read_text(encoding="utf-8")
    assert committed == build_css(), (
        "site/hatchi-maxchi.css is stale — re-run the gallery build "
        "(in the Dazzle monorepo: python packages/hatchi-maxchi/site/build_site.py)"
    )


def test_committed_gallery_js_carries_current_controllers() -> None:
    committed = (PKG / "site" / "hatchi-maxchi.js").read_text(encoding="utf-8")
    assert build_js() in committed, (
        "site/hatchi-maxchi.js does not embed the current controllers — re-run the gallery build"
    )


def test_gallery_regenerates_byte_identically(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The committed gallery must equal a fresh standalone rebuild — the
    boundary acceptance test (Phase 3): the split repo regenerates its own
    docs with zero Dazzle code, and what it regenerates is what's shipped."""
    import build_site

    build_site.build(tmp_path)
    for name in ("index.html", "hatchi-maxchi.css", "hatchi-maxchi.js"):
        fresh = (tmp_path / name).read_text(encoding="utf-8")
        committed = (PKG / "site" / name).read_text(encoding="utf-8")
        assert fresh == committed, (
            f"site/{name} is stale or the build is nondeterministic — "
            "re-run python site/build_site.py and commit"
        )


def test_prefix_transform_is_total() -> None:
    css = build_css(prefix="ax-")
    js = build_js(prefix="ax-")
    assert "dz-" not in css and "dz-" not in js
    assert ".ax-button" in css and ".ax-alert" in css
    assert "ax-command" in js and "data-ax-native-confirm" in js


def test_default_prefix_is_dz() -> None:
    assert ".dz-button" in build_css()
