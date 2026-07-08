"""
CSS loader for Dazzle UI runtime.

Loads and concatenates CSS files from static/ to produce the bundled
stylesheet served at /styles/dazzle.css.

Uses CSS Cascade Layers (@layer) for explicit ordering. THIS LIST is
the source of truth for the dev bundle (``static/css/dazzle.css`` is a
human-readable reference of the Dazzle-side files only — the design
system arrives pre-layered via the HM dist artifact, which that file
cannot @import). ``scripts/build_dist.py`` mirrors this list; the
Phase-3 lockstep gate (tests/unit/test_hm_boundary.py) keeps the two
aligned on the package seam.

Generates an inline source map for DevTools debugging.
"""

import base64
import json
from pathlib import Path
from types import ModuleType

_STATIC_DIR = Path(__file__).parent / "static"
# HaTchi-MaXchi design-system sources live in the extractable package
# (packages/hatchi-maxchi/). Entries prefixed "@hm:" resolve there.
_HM_ROOT = Path(__file__).resolve().parents[4] / "packages" / "hatchi-maxchi"

# Cascade layer order — must match `static/css/dazzle.css`. Anything
# in a later layer wins over earlier layers regardless of selector
# specificity. `overrides` is reserved for project-level escape-hatch
# rules; the loader never emits into it.
CSS_LAYER_ORDER = "@layer reset, vendor, tokens, base, utilities, components, overrides;"

# Layered source files in cascade order. Each entry is
# ``(layer_name, path_relative_to_static)``. Order WITHIN a layer
# also matters for ties resolved by source position; keep this list
# byte-for-byte aligned with the @import order in
# ``static/css/dazzle.css`` (#920).
CSS_SOURCE_FILES: tuple[tuple[str | None, str], ...] = (
    ("reset", "css/reset.css"),
    ("vendor", "vendor/tom-select.css"),
    ("vendor", "vendor/flatpickr.css"),
    # HaTchi-MaXchi — consumed as its PUBLISHED dist artifact (boundary
    # Phase 2), not per-source files. The bundle is pre-layered by the
    # package's build.py (vendor fonts, tokens, base, components — the
    # same layer names as ours), so it loads raw (layer=None). After
    # editing package CSS, run `python packages/hatchi-maxchi/build.py`;
    # the package's dist drift gate fails CI when forgotten.
    (None, "@hm-build:dz-"),
    # vendor/quill.snow.css removed in #977 cycle 4 — Quill replaced by
    # dz-richtext (Dazzle-native, bundled).
    # vendor/pickr.css removed in #976 — `widget=color` uses native
    # <input type="color">, no vendor CSS required.
    ("utilities", "css/utilities.css"),
    ("components", "css/components/dashboard.css"),
    ("components", "css/components/detail.css"),
    ("components", "css/components/fragments.css"),
    ("components", "css/components/pdf-viewer.css"),
    # regions.css removed from the bundle (HMC-007): it is now 130 lines of
    # pure tombstone comments (every region family promoted to HM) — zero CSS
    # rules, so shipping it to every browser was dead weight. File retained on
    # disk as the provenance index (+ read by a few content-union tests).
    ("components", "css/components/mobile-scroll.css"),
    # #977 cycle 1 — Dazzle-native rich-text editor (replaces Quill in cycle 4).
    ("components", "css/components/richtext.css"),
    # v0.71.x guided onboarding (overlay primitives for the eight step kinds).
    ("components", "css/components/onboarding.css"),
    # dazzle-layer.css removed from the bundle (HMC-003b, 2026-07-08): its
    # remaining rules are all dead for the main HM runtime — `#app`/`.dz-app`
    # (root layout; the main shell is `<body class="dz-page">` + `.dz-app-shell`,
    # which owns its own min-height:100vh in HM app-shell.css), `.dz-app__main`
    # + `.dz-text-muted` (used ONLY by the legacy pre-HM `dnr-ui`/`build-ui`
    # export, never by render/page emitters), empty no-op hooks
    # (`.dz-workspace`/`__header`/`__sidebar`/`__footer`; HM workspace-shell.css
    # owns the real `.dz-workspace`), and a commented-out `[data-dazzle-entity]`
    # rule. Empty-state styling was folded into HM in HMC-003c. Provably inert
    # removal — no main-runtime emitter references any of these. File retained on
    # disk for the legacy dnr export (its generator is defunct; committed dnr-ui
    # snapshots bake their own CSS).
    ("components", "css/site-sections.css"),
)

# Files loaded unlayered (after every @layer block) so they can
# override earlier rules regardless of layer position. Layered styles
# always lose to unlayered styles in the CSS cascade.
CSS_UNLAYERED_FILES: tuple[str, ...] = (
    "css/dz.css",
    "css/dz-widgets.css",
    "css/dz-tones.css",
)


def _hm_build() -> ModuleType:
    """Load the HaTchi-MaXchi package's build module (packages/…/build.py).

    HM publishes UNPREFIXED (`.button`); Dazzle applies its own `dz-`
    namespace at ingest by calling `build_css("dz-")` — a no-op transform
    on the `dz-`-prefixed source, so the result is byte-identical to the
    pre-flip bundle while the standalone/CDN artifact stays clean. This is
    the production exercise of the prefix mechanism. Loaded by explicit path
    (not `import build`) to avoid clobbering any other `build` module."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_hm_build", _HM_ROOT / "build.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_css_file(rel_path: str) -> str:
    """Load a CSS source. `@hm-build:<prefix>` builds the HaTchi-MaXchi bundle
    with that namespace; `@hm:` resolves a file in the package; everything
    else is relative to static/."""
    if rel_path.startswith("@hm-build:"):
        prefix = rel_path[len("@hm-build:") :]
        # Font URLs come standalone-relative from build_css; rewrite to
        # Dazzle's /static/fonts/ mount at the consumption seam.
        built: str = _hm_build().build_css(prefix)
        return built.replace('url("fonts/', 'url("/static/fonts/')
    if rel_path.startswith("@hm:"):
        path = _HM_ROOT / rel_path[len("@hm:") :]
    else:
        path = _STATIC_DIR / rel_path
    if not path.exists():
        raise FileNotFoundError(f"CSS file not found: {path}")
    css = path.read_text(encoding="utf-8")
    if rel_path.startswith("@hm:dist/"):
        # The published artifact is standalone-first: font URLs are relative
        # to the CSS file. Dazzle serves fonts at /static/fonts/ — rewrite at
        # the consumption seam.
        css = css.replace('url("fonts/', 'url("/static/fonts/')
    return css


def get_bundled_css(theme_css: str | None = None) -> str:
    """
    Concatenate all framework CSS into one bundle, layered to match
    ``static/css/dazzle.css``.

    Args:
        theme_css: Optional generated theme CSS to prepend (from ThemeSpec).
            Inlined into the ``tokens`` layer so generated custom-property
            values participate in the same cascade as the static tokens.

    Returns:
        Concatenated CSS with @layer wrappers and an inline source map.
    """
    parts: list[str] = [
        CSS_LAYER_ORDER,
        "",
        "/* =============================================================================",
        "   DAZZLE Framework CSS Bundle",
        "   Auto-generated by css_loader.py (source of truth: CSS_SOURCE_FILES)",
        "   ============================================================================= */",
        "",
    ]

    # Generated theme CSS lands in the tokens layer alongside the
    # static custom-property declarations.
    if theme_css:
        parts.append("/* --- theme.css (generated) --- */")
        parts.append(f"@layer tokens {{\n{theme_css}\n}}")
        parts.append("")

    for layer, rel_path in CSS_SOURCE_FILES:
        parts.append(f"/* --- {rel_path} --- */")
        if layer is None:
            # Pre-layered artifact (HM dist) — its own @layer blocks use
            # the same layer names; wrapping it again would nest layers.
            parts.append(_load_css_file(rel_path))
        else:
            parts.append(f"@layer {layer} {{\n{_load_css_file(rel_path)}\n}}")
        parts.append("")

    # Unlayered files come last so they win the cascade.
    for rel_path in CSS_UNLAYERED_FILES:
        parts.append(f"/* --- {rel_path} (unlayered — cascade override) --- */")
        parts.append(_load_css_file(rel_path))
        parts.append("")

    all_sources = [path for _, path in CSS_SOURCE_FILES] + list(CSS_UNLAYERED_FILES)
    source_map = {"version": 3, "sources": all_sources, "mappings": ""}
    map_b64 = base64.b64encode(json.dumps(source_map).encode()).decode()
    parts.append(f"/*# sourceMappingURL=data:application/json;base64,{map_b64} */")

    return "\n".join(parts)
