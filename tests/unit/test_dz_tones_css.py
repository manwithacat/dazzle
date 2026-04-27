"""Regression tests for #906 — tone tints must be styled by static
CSS rules in `dz-tones.css`, NOT by dynamic Tailwind arbitrary-value
classes that the JIT can't observe at build time.

The bug shipped against v0.61.65 (tones), v0.61.68 (notice band),
and v0.61.69 (status_list pill). All three components emitted class
names like `bg-[hsl(var(--primary)/0.10)]` from server-side template
logic — Tailwind compiled none of them and tile/pill backgrounds
shipped transparent.

The v0.61.70 fix:
  - Adds `dz-tones.css` with rules keyed off `[data-dz-tone]` /
    `[data-dz-state]` / `[data-dz-notice-tone]` attributes.
  - Drops the dynamic `bg-[hsl(...)]` classes from each template.
  - Wires `dz-tones.css` into `dazzle-framework.css`, `css_loader.py`,
    and `build_dist.py` so it ships with every install.

These tests pin the absence of the dynamic classes AND the presence
of the static rules so a future "let me re-add inline tone classes"
temptation can't quietly reintroduce the JIT-invisible regression.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CSS_DIR = _REPO_ROOT / "src/dazzle_ui/runtime/static/css"
_TPL_DIR = _REPO_ROOT / "src/dazzle_ui/templates"


# ───────────────────────── dz-tones.css presence ──────────────────────────


class TestDzTonesCssExists:
    def test_file_exists(self) -> None:
        assert (_CSS_DIR / "dz-tones.css").is_file(), (
            "dz-tones.css missing — #906 fix required this file to ship "
            "static tint rules instead of dynamic Tailwind classes"
        )

    def test_file_is_not_empty(self) -> None:
        text = (_CSS_DIR / "dz-tones.css").read_text()
        assert len(text) > 200, "dz-tones.css suspiciously short"


class TestDzTonesCssRulesPresent:
    """Each tinted component must have at least one rule per
    non-neutral tone keyed off the right data attribute."""

    def _text(self) -> str:
        return (_CSS_DIR / "dz-tones.css").read_text()

    def test_metric_tile_rules_present(self) -> None:
        text = self._text()
        for tone in ("positive", "warning", "destructive", "accent"):
            sel = f'.dz-metric-tile[data-dz-tone="{tone}"]'
            assert sel in text, f"Missing metric-tile rule for tone={tone!r}"

    def test_notice_band_rules_present(self) -> None:
        text = self._text()
        for tone in ("positive", "warning", "destructive", "accent", "neutral"):
            sel = f'.dz-notice-band[data-dz-notice-tone="{tone}"]'
            assert sel in text, f"Missing notice-band rule for tone={tone!r}"

    def test_status_list_pill_rules_present(self) -> None:
        text = self._text()
        for state in ("positive", "warning", "destructive", "accent"):
            sel = f'.dz-status-list-entry[data-dz-state="{state}"] .dz-status-list-pill'
            assert sel in text, f"Missing status-list pill rule for state={state!r}"

    def test_status_list_icon_rules_present(self) -> None:
        text = self._text()
        for state in ("positive", "warning", "destructive", "accent"):
            sel = f'.dz-status-list-entry[data-dz-state="{state}"] .dz-status-list-icon'
            assert sel in text, f"Missing status-list icon rule for state={state!r}"

    def test_uses_design_system_tokens(self) -> None:
        """All tints route through HSL design-system slots so the
        active project theme applies — no hardcoded colours."""
        text = self._text()
        assert "var(--success)" in text
        assert "var(--warning)" in text
        assert "var(--destructive)" in text
        assert "var(--primary)" in text


# ───────────────────────── load order ──────────────────────────


class TestDzTonesCssLoadOrder:
    """`dz-tones.css` must be wired into all three load paths:
    the @import bundle, the css_loader runtime concatenation, and
    the build_dist concat for the dist/ bundle. Forgetting any one
    means some deployment shape ships without the rules — which is
    exactly the failure mode #906 surfaced."""

    def test_imported_in_dazzle_framework_css(self) -> None:
        text = (_CSS_DIR / "dazzle-framework.css").read_text()
        assert '@import "dz-tones.css"' in text

    def test_in_css_loader_unlayered_files(self) -> None:
        text = (_REPO_ROOT / "src/dazzle_ui/runtime/css_loader.py").read_text()
        assert "dz-tones.css" in text, (
            "css_loader.py must include dz-tones.css in CSS_UNLAYERED_FILES"
        )

    def test_in_build_dist_sources(self) -> None:
        text = (_REPO_ROOT / "scripts/build_dist.py").read_text()
        assert "dz-tones.css" in text, (
            "build_dist.py must include dz-tones.css so the dist/ bundle ships with the rules"
        )


# ───────────────────────── templates lost dynamic classes ──────────────────────────


class TestTemplatesNoDynamicTailwindToneClasses:
    """The fix relies on attributes (`data-dz-tone` etc.) — templates
    must not also try to set the dynamic Tailwind class. Doing both
    creates two conflicting source-of-truths and reintroduces the JIT
    dependency."""

    def test_metrics_no_dynamic_bg_class(self) -> None:
        text = (_TPL_DIR / "workspace/regions/metrics.html").read_text()
        # The neutral-fallback `bg-[hsl(var(--muted)/0.4)]` is the only
        # static tile bg and it's allowed (it's the always-applied
        # default). Named tones must NOT appear inline.
        assert "bg-[hsl(var(--success)" not in text
        assert "bg-[hsl(var(--warning)" not in text
        assert "bg-[hsl(var(--destructive)" not in text
        assert "bg-[hsl(var(--primary)/0.10)]" not in text

    def test_status_list_no_dynamic_pill_or_icon_class(self) -> None:
        text = (_TPL_DIR / "workspace/regions/status_list.html").read_text()
        assert "_pill_classes" not in text, (
            "status_list.html lost the dynamic pill class lookup — pill "
            "tints come from dz-tones.css now (#906)"
        )
        assert "_icon_classes" not in text
        # Spot-check: the specific JIT-invisible classes are gone
        assert "bg-[hsl(var(--success)/0.15)]" not in text
        assert "text-[hsl(var(--destructive))]" not in text

    def test_notice_band_no_dynamic_bg_class(self) -> None:
        text = (_TPL_DIR / "workspace/_content.html").read_text()
        # Notice-band tone backgrounds were inside a `:class="{...}"`
        # Alpine binding — the literal class strings should now be gone.
        assert "bg-[hsl(var(--success)/0.08)]" not in text
        assert "bg-[hsl(var(--warning)/0.10)] border-[hsl(var(--warning))]" not in text
        # The data attribute must remain (it's the new source of truth)
        assert "data-dz-notice-tone" in text


# ───────────────────────── data attributes still emitted ──────────────────────────


class TestTemplatesStillEmitDataAttributes:
    """The fix only works if templates still emit the data attributes
    that dz-tones.css matches on. Defensive guard against accidentally
    dropping the attribute alongside the dynamic class."""

    def test_metrics_emits_data_dz_tone(self) -> None:
        text = (_TPL_DIR / "workspace/regions/metrics.html").read_text()
        assert 'data-dz-tone="' in text

    def test_status_list_emits_data_dz_state(self) -> None:
        text = (_TPL_DIR / "workspace/regions/status_list.html").read_text()
        assert 'data-dz-state="' in text

    def test_notice_band_emits_data_dz_notice_tone(self) -> None:
        text = (_TPL_DIR / "workspace/_content.html").read_text()
        assert "data-dz-notice-tone" in text
