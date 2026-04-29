"""Tests for scripts/css_clip_check.py — static CSS clipping detector.

Covers the bug class first hit on framework selector ``.dz-form-input``
(#930) and ``.dz-list-filter-select``: a rule declares fixed height +
padding, but the line-box (font-size × line-height) overflows the
remaining content area, clipping descenders on rendered text.

The scanner is intentionally conservative — it only analyses rules
whose declarations are self-contained (height, font-size, line-height,
padding all in the same block, all in px/rem units). False-positive
rate on the current Dazzle CSS bundle: 0.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "css_clip_check.py"
_spec = importlib.util.spec_from_file_location("css_clip_check", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
clip = importlib.util.module_from_spec(_spec)
sys.modules["css_clip_check"] = clip  # @dataclass needs the module registered
_spec.loader.exec_module(clip)


def _scan(css: str, tmp_path: Path) -> list[clip.Finding]:
    f = tmp_path / "x.css"
    f.write_text(css)
    return clip.scan_file(f)


class TestClipDetection:
    def test_pre_930_form_input_pattern_flags(self, tmp_path: Path) -> None:
        """The classic #930 reproduction: height 2rem + 8px 12px padding +
        14px font + 1.5 line-height ⇒ line-box 21px in a 16px content
        area = 5px overflow. Must flag."""
        findings = _scan(
            """
            .dz-form-input {
              height: 2rem;
              padding: 8px 12px;
              font-size: 14px;
              line-height: 1.5;
            }
            """,
            tmp_path,
        )
        assert len(findings) == 1
        f = findings[0]
        assert f.selector == ".dz-form-input"
        assert f.height_px == 32.0
        assert f.padding_top_px == 8.0
        assert f.padding_bottom_px == 8.0
        assert f.content_area_px == 16.0
        assert f.line_box_px == 21.0
        assert f.overflow_px == 5.0

    def test_post_930_min_height_pattern_passes(self, tmp_path: Path) -> None:
        """The fix for #930: height: auto + min-height. Scanner ignores
        rules where height isn't a definite px/rem value."""
        findings = _scan(
            """
            .dz-form-input {
              height: auto;
              min-height: 2.5rem;
              padding-block: 0.5rem;
              padding-inline: 0.75rem;
              font-size: 14px;
              line-height: 1.4;
            }
            """,
            tmp_path,
        )
        assert findings == []

    def test_sufficient_padding_passes(self, tmp_path: Path) -> None:
        """height 40 - padding 12+12 = 16 content; 14 × 1.0 = 14 line-box.
        14 < 16 ⇒ no overflow."""
        findings = _scan(
            """
            .ok {
              height: 40px;
              padding: 12px;
              font-size: 14px;
              line-height: 1.0;
            }
            """,
            tmp_path,
        )
        assert findings == []

    def test_rem_height_resolves_to_16px_base(self, tmp_path: Path) -> None:
        """1rem == 16px under the standard browser default."""
        findings = _scan(
            """
            .badge {
              height: 1rem;
              padding: 0;
              font-size: 14px;
              line-height: 1.5;
            }
            """,
            tmp_path,
        )
        assert len(findings) == 1
        assert findings[0].height_px == 16.0
        assert findings[0].line_box_px == 21.0

    def test_subpixel_tolerance_does_not_flag(self, tmp_path: Path) -> None:
        """0.4px overflow is below the 0.5px tolerance — browser sub-
        pixel rounding hides it. Don't flag."""
        findings = _scan(
            """
            .sub-pixel {
              height: 20px;
              padding: 1.8px 0;
              font-size: 12px;
              line-height: 1.4;
            }
            """,
            tmp_path,
        )
        # content = 20 - 3.6 = 16.4; line-box = 16.8 → overflow 0.4 < 0.5
        assert findings == []


class TestSelectorIgnoreList:
    def test_icon_selector_skipped(self, tmp_path: Path) -> None:
        findings = _scan(
            """
            .dz-card-icon {
              height: 16px;
              padding: 4px;
              font-size: 14px;
              line-height: 1.5;
            }
            """,
            tmp_path,
        )
        assert findings == []

    def test_skeleton_selector_skipped(self, tmp_path: Path) -> None:
        findings = _scan(
            """
            .dz-card-skeleton-line {
              height: 8px;
              padding: 2px;
              font-size: 12px;
              line-height: 1.5;
            }
            """,
            tmp_path,
        )
        assert findings == []

    def test_svg_selector_skipped(self, tmp_path: Path) -> None:
        findings = _scan(
            """
            svg.icon {
              height: 14px;
              padding: 2px;
              font-size: 14px;
              line-height: 1.5;
            }
            """,
            tmp_path,
        )
        assert findings == []

    def test_multi_selector_keeps_text_bearing_only(self, tmp_path: Path) -> None:
        """Comma-separated selector list: chrome selectors filtered out,
        text-bearing selectors still flagged."""
        findings = _scan(
            """
            .dz-form-input, .dz-card-icon, .dz-form-textarea {
              height: 2rem;
              padding: 8px 12px;
              font-size: 14px;
              line-height: 1.5;
            }
            """,
            tmp_path,
        )
        selectors = sorted(f.selector for f in findings)
        assert selectors == [".dz-form-input", ".dz-form-textarea"]


class TestSkipRulesWithoutEnoughInfo:
    def test_missing_font_size_skipped(self, tmp_path: Path) -> None:
        """Without font-size we can't compute a line-box."""
        findings = _scan(
            """
            .x {
              height: 2rem;
              padding: 8px;
              line-height: 1.5;
            }
            """,
            tmp_path,
        )
        assert findings == []

    def test_missing_line_height_skipped(self, tmp_path: Path) -> None:
        """Without line-height we can't compute a line-box."""
        findings = _scan(
            """
            .x {
              height: 2rem;
              padding: 8px;
              font-size: 14px;
            }
            """,
            tmp_path,
        )
        assert findings == []

    def test_var_font_size_skipped(self, tmp_path: Path) -> None:
        """CSS custom properties can't be resolved statically — skip
        rather than guess at a value."""
        findings = _scan(
            """
            .x {
              height: 2rem;
              padding: 8px;
              font-size: var(--text-sm);
              line-height: 1.5;
            }
            """,
            tmp_path,
        )
        assert findings == []

    def test_em_padding_skipped(self, tmp_path: Path) -> None:
        """em padding depends on parent font-size; skip rather than
        guess at the cascade."""
        findings = _scan(
            """
            .x {
              height: 2rem;
              padding: 0.5em 1em;
              font-size: 14px;
              line-height: 1.5;
            }
            """,
            tmp_path,
        )
        assert findings == []


class TestPaddingShorthand:
    def test_one_value(self, tmp_path: Path) -> None:
        findings = _scan(
            """
            .x { height: 24px; padding: 4px; font-size: 14px; line-height: 1.5; }
            """,
            tmp_path,
        )
        assert len(findings) == 1
        assert findings[0].padding_top_px == 4.0
        assert findings[0].padding_bottom_px == 4.0

    def test_two_values(self, tmp_path: Path) -> None:
        findings = _scan(
            """
            .x { height: 24px; padding: 4px 8px; font-size: 14px; line-height: 1.5; }
            """,
            tmp_path,
        )
        assert len(findings) == 1
        assert findings[0].padding_top_px == 4.0
        assert findings[0].padding_bottom_px == 4.0

    def test_three_values(self, tmp_path: Path) -> None:
        findings = _scan(
            """
            .x { height: 24px; padding: 4px 8px 6px; font-size: 14px; line-height: 1.5; }
            """,
            tmp_path,
        )
        assert len(findings) == 1
        assert findings[0].padding_top_px == 4.0
        assert findings[0].padding_bottom_px == 6.0

    def test_four_values(self, tmp_path: Path) -> None:
        findings = _scan(
            """
            .x { height: 24px; padding: 4px 8px 6px 10px; font-size: 14px; line-height: 1.5; }
            """,
            tmp_path,
        )
        assert len(findings) == 1
        assert findings[0].padding_top_px == 4.0
        assert findings[0].padding_bottom_px == 6.0

    def test_padding_block_overrides_shorthand(self, tmp_path: Path) -> None:
        """``padding-block`` takes precedence — newer logical-property
        spec, common in the Dazzle bundle."""
        findings = _scan(
            """
            .x {
              height: 24px;
              padding: 0;
              padding-block: 4px;
              font-size: 14px;
              line-height: 1.5;
            }
            """,
            tmp_path,
        )
        assert len(findings) == 1
        assert findings[0].padding_top_px == 4.0
        assert findings[0].padding_bottom_px == 4.0

    def test_padding_top_bottom_overrides_shorthand(self, tmp_path: Path) -> None:
        findings = _scan(
            """
            .x {
              height: 24px;
              padding: 12px;
              padding-top: 2px;
              padding-bottom: 6px;
              font-size: 14px;
              line-height: 1.5;
            }
            """,
            tmp_path,
        )
        assert len(findings) == 1
        assert findings[0].padding_top_px == 2.0
        assert findings[0].padding_bottom_px == 6.0


class TestLineHeightForms:
    def test_unitless_multiplier(self, tmp_path: Path) -> None:
        findings = _scan(
            """
            .x { height: 16px; padding: 0; font-size: 14px; line-height: 1.7; }
            """,
            tmp_path,
        )
        assert len(findings) == 1
        assert findings[0].line_height_multiplier == 1.7
        assert findings[0].line_box_px == round(14.0 * 1.7, 3)

    def test_normal_resolves_to_1_2(self, tmp_path: Path) -> None:
        findings = _scan(
            """
            .x { height: 24px; padding: 0; font-size: 24px; line-height: normal; }
            """,
            tmp_path,
        )
        # line-box = 24 * 1.2 = 28.8 > 24 → overflow 4.8
        assert len(findings) == 1
        assert findings[0].line_height_multiplier == 1.2

    def test_absolute_px_line_height(self, tmp_path: Path) -> None:
        """``line-height: 18px`` with a 12px font means a 1.5 multiplier
        — convert and check overflow on that basis."""
        findings = _scan(
            """
            .x { height: 16px; padding: 0; font-size: 12px; line-height: 18px; }
            """,
            tmp_path,
        )
        assert len(findings) == 1
        assert findings[0].line_height_multiplier == 1.5


class TestParserRobustness:
    def test_comments_stripped(self, tmp_path: Path) -> None:
        """``/* … */`` comments must not interfere with rule parsing —
        especially when they contain braces or colons."""
        findings = _scan(
            """
            /* { height: 999px; } */
            .x {
              /* padding: 0; — stale */
              height: 32px;
              padding: 8px;
              font-size: 14px;
              line-height: 1.5;
            }
            """,
            tmp_path,
        )
        assert len(findings) == 1
        assert findings[0].selector == ".x"

    def test_at_rule_inner_blocks_scanned(self, tmp_path: Path) -> None:
        """Rules inside ``@media`` / ``@supports`` get checked too —
        same overflow bug class."""
        findings = _scan(
            """
            @media (max-width: 768px) {
              .x {
                height: 2rem;
                padding: 8px 12px;
                font-size: 14px;
                line-height: 1.5;
              }
            }
            """,
            tmp_path,
        )
        assert len(findings) == 1
        assert findings[0].selector == ".x"

    def test_zero_height_skipped(self, tmp_path: Path) -> None:
        """``height: 0`` is intentional collapsing chrome — never a
        clipping bug."""
        findings = _scan(
            """
            .x { height: 0; padding: 0; font-size: 14px; line-height: 1.5; }
            """,
            tmp_path,
        )
        assert findings == []


class TestFrameworkBundle:
    """Pin the framework's own CSS bundle: it must remain at zero
    findings. New rules that introduce a clipping regression fail the
    pinned baseline before they reach a deployed app."""

    def test_framework_bundle_has_zero_findings(self) -> None:
        findings = clip.scan_paths([Path(clip.DEFAULT_CSS_ROOTS[0])])
        if findings:
            rendered = "\n".join(f.render() for f in findings)
            raise AssertionError(
                f"css_clip_check found {len(findings)} clipping regression(s) "
                f"in the framework CSS bundle:\n{rendered}\n\n"
                "Either fix the offending rule (typical: switch height → "
                "min-height, increase padding-block, or reduce line-height) "
                "or — if the selector is non-text-bearing chrome — extend "
                "the SELECTOR_IGNORE_SUBSTRINGS list in scripts/"
                "css_clip_check.py."
            )


class TestExitCode:
    def test_clean_run_exits_zero(self, tmp_path: Path) -> None:
        f = tmp_path / "ok.css"
        f.write_text(".x { height: auto; padding: 8px; font-size: 14px; }")
        assert clip.main([str(f)]) == 0

    def test_findings_exit_one(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.css"
        f.write_text(".x { height: 2rem; padding: 8px 12px; font-size: 14px; line-height: 1.5; }")
        assert clip.main([str(f)]) == 1

    def test_max_findings_threshold_passes(self, tmp_path: Path) -> None:
        """Used for staged adoption: fail only when findings exceed the
        agreed baseline. Ships at default 0 — every new finding fails."""
        f = tmp_path / "bad.css"
        f.write_text(".x { height: 2rem; padding: 8px 12px; font-size: 14px; line-height: 1.5; }")
        assert clip.main([str(f), "--max-findings", "1"]) == 0
