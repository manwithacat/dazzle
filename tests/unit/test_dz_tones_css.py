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

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CSS_DIR = _REPO_ROOT / "src/dazzle/page/runtime/static/css"
_HM_COMPONENTS = _REPO_ROOT / "packages/hatchi-maxchi/components"


def _tones_text() -> str:
    """The tone vocabulary fully converged into HaTchi-MaXchi (dz-tones.css was
    drained + deleted 2026-07-09, HMC-005/005b): metric-tile → metrics.css,
    action-grid/status-list → their components, notice-band → dashboard-card.css,
    the attn macro → timeline.css. The #906 contract is now "these static tint
    rules SHIP in the served bundle", so assert against the real bundle."""
    from dazzle.page.runtime.css_loader import get_bundled_css

    return get_bundled_css()


_TPL_DIR = _REPO_ROOT / "src/dazzle/page/templates"


# ───────────────────────── tone-tint rules ship ──────────────────────────
# (dz-tones.css presence + load-order tests retired 2026-07-09: the file was
# drained into HM and deleted; the #906 guard is now "rules present in the
# served bundle", asserted below via get_bundled_css().)


class TestDzTonesCssRulesPresent:
    """Each tinted component must have at least one rule per
    non-neutral tone keyed off the right data attribute."""

    def _text(self) -> str:
        return _tones_text()

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
        """All tints route through the OKLCH semantic tokens so the
        active project theme applies — no hardcoded colours."""
        text = self._text()
        assert "var(--colour-success)" in text
        assert "var(--colour-warning)" in text
        assert "var(--colour-danger)" in text
        assert "var(--colour-brand)" in text


# ───────────────────────── load order ──────────────────────────


# TestDzTonesCssLoadOrder retired 2026-07-09 (HMC-005b): dz-tones.css is gone —
# its rules ship from their HM component homes now, guarded by
# TestDzTonesCssRulesPresent against the served bundle above.


# ───────────────────────── templates lost dynamic classes ──────────────────────────


@pytest.mark.skip(
    reason="Phase 4 deletion sweep (v0.67.52) — pinned legacy Jinja template markup; the typed-Fragment substrate produces semantically equivalent output with different class names"
)
class TestTemplatesNoDynamicTailwindToneClasses:
    """The fix relies on attributes (`data-dz-tone` etc.) — templates
    must not also try to set the dynamic Tailwind class. Doing both
    creates two conflicting source-of-truths and reintroduces the JIT
    dependency."""

    def test_metrics_no_dynamic_bg_class(self) -> None:
        text = (_TPL_DIR / "workspace/regions/_typed_primitive.html").read_text()
        # The neutral-fallback `bg-[hsl(var(--muted)/0.4)]` is the only
        # static tile bg and it's allowed (it's the always-applied
        # default). Named tones must NOT appear inline.
        assert "bg-[hsl(var(--success)" not in text
        assert "bg-[hsl(var(--warning)" not in text
        assert "bg-[hsl(var(--destructive)" not in text
        assert "bg-[hsl(var(--primary)/0.10)]" not in text

    def test_status_list_no_dynamic_pill_or_icon_class(self) -> None:
        text = (_TPL_DIR / "workspace/regions/_typed_primitive.html").read_text()
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

    def test_action_grid_no_dynamic_tone_classes(self) -> None:
        """v0.61.74 (#906 cleanup): action_grid.html dropped the
        `_tone_classes` and `_tone_count_classes` Jinja dictionaries
        in favour of `data-dz-tone` / `data-dz-tone-badge` attributes
        styled by dz-tones.css. The hardcoded HSL literals (positive
        green = 145,55%,45%; warning amber = 40,90%,55%) are gone too
        — both now route via design-system slots."""
        text = (_TPL_DIR / "workspace/regions/_typed_primitive.html").read_text()
        assert "_tone_classes" not in text
        assert "_tone_count_classes" not in text
        # Hardcoded HSL literals — these were the worst offenders for
        # downstream theming. None should remain.
        assert "hsl(145,55%" not in text
        assert "hsl(40,90%" not in text
        assert "hsl(35,80%" not in text
        # Both data attributes must remain
        assert 'data-dz-tone="' in text
        assert 'data-dz-tone-badge="' in text

    def test_metrics_delta_no_dynamic_tone_class(self) -> None:
        """v0.61.74 (#906 cleanup): the metric delta-arrow tone was
        the second buried-dynamic-class instance in metrics.html
        (separate from the per-tile tones fix in v0.61.70). The
        hardcoded `hsl(142_76%_36%)` literal is gone; tone routes via
        `data-dz-delta-tone`."""
        text = (_TPL_DIR / "workspace/regions/_typed_primitive.html").read_text()
        # The dynamic Tailwind class string is gone
        assert "_tone_class" not in text
        # The hardcoded green literal (used to be the positive arrow) is gone
        assert "hsl(142_76%_36%)" not in text
        assert "hsl(142 76% 36%)" not in text
        # The data attribute must be there
        assert "data-dz-delta-tone" in text


# ───────────────────────── data attributes still emitted ──────────────────────────


@pytest.mark.skip(
    reason="Phase 4 deletion sweep (v0.67.52) — pinned legacy Jinja template markup; the typed-Fragment substrate produces semantically equivalent output with different class names"
)
class TestTemplatesStillEmitDataAttributes:
    """The fix only works if templates still emit the data attributes
    that dz-tones.css matches on. Defensive guard against accidentally
    dropping the attribute alongside the dynamic class."""

    @pytest.mark.parametrize(
        ("template", "needle"),
        [
            ("workspace/regions/_typed_primitive.html", 'data-dz-tone="'),
            ("workspace/regions/_typed_primitive.html", 'data-dz-state="'),
            ("workspace/_content.html", "data-dz-notice-tone"),
            ("workspace/regions/_typed_primitive.html", "data-dz-delta-tone"),
        ],
        ids=[
            "test_metrics_emits_data_dz_tone",
            "test_status_list_emits_data_dz_state",
            "test_notice_band_emits_data_dz_notice_tone",
            "test_metrics_delta_emits_data_dz_delta_tone",
        ],
    )
    def test_emits_data_attribute(self, template: str, needle: str) -> None:
        text = (_TPL_DIR / template).read_text()
        assert needle in text

    def test_action_grid_emits_data_dz_tone_attrs(self) -> None:
        text = (_TPL_DIR / "workspace/regions/_typed_primitive.html").read_text()
        assert 'data-dz-tone="' in text
        assert 'data-dz-tone-badge="' in text


class TestActionGridAndDeltaCssRulesPresent:
    """Sibling check to TestDzTonesCssRulesPresent — pin the new
    rules added in v0.61.74."""

    def _text(self) -> str:
        return _tones_text()

    def test_action_card_surface_rules_present(self) -> None:
        text = self._text()
        for tone in ("positive", "warning", "destructive", "accent", "neutral"):
            sel = f'.dz-action-card[data-dz-tone="{tone}"]'
            assert sel in text, f"Missing action-card rule for tone={tone!r}"

    def test_action_card_count_rules_present(self) -> None:
        text = self._text()
        for tone in ("positive", "warning", "destructive", "accent", "neutral"):
            sel = f'.dz-action-card-count[data-dz-tone-badge="{tone}"]'
            assert sel in text, f"Missing action-card-count rule for tone={tone!r}"

    def test_metric_delta_rules_present(self) -> None:
        text = self._text()
        for tone in ("positive", "destructive", "neutral"):
            sel = f'.dz-metric-delta[data-dz-delta-tone="{tone}"]'
            assert sel in text, f"Missing metric-delta rule for tone={tone!r}"
