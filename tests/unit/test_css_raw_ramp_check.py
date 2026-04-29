"""Tests for scripts/css_raw_ramp_check.py — design-system-wide
raw-ramp lint (#942 cycle 1e).

The lint scans component CSS for raw colour-ramp tokens
(``var(--neutral-100)``, ``var(--brand-500)``, …) which don't flip
under ``[data-theme="dark"]``. Catches the exact bug class that
shipped briefly in v0.61.115 / v0.61.116's pdf-viewer.css before
the cycle 1d visual gates surfaced it. The raw-ramp lint is the
source-side complement to the visual gate — fails CI before the
bug ever reaches a browser.

Tests cover:
- Detection of every flagged ramp family (neutral / brand / success
  / warning / danger)
- Exemption for theme-scoped rules (``[data-theme="dark"] {}`` and
  ``@media (prefers-color-scheme: dark) {}``)
- Exemption for token-defining files (tokens.css, design-system.css)
- Comment stripping (raw ramps inside ``/* ... */`` don't trigger)
- Multi-finding output preserves line numbers
- Pinned baseline: zero findings across the framework's component
  CSS today
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "css_raw_ramp_check.py"
_spec = importlib.util.spec_from_file_location("css_raw_ramp_check", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
ramp = importlib.util.module_from_spec(_spec)
sys.modules["css_raw_ramp_check"] = ramp
_spec.loader.exec_module(ramp)


def _scan(css: str, tmp_path: Path, *, name: str = "x.css") -> list[ramp.Finding]:
    f = tmp_path / name
    f.write_text(css)
    return ramp.scan_file(f)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


class TestDetection:
    def test_neutral_ramp_in_background_flags(self, tmp_path: Path) -> None:
        findings = _scan(".x { background: var(--neutral-100); }", tmp_path)
        assert len(findings) == 1
        assert findings[0].ramp == "neutral-100"

    def test_brand_ramp_flags(self, tmp_path: Path) -> None:
        findings = _scan(".x { color: var(--brand-500); }", tmp_path)
        assert len(findings) == 1
        assert findings[0].ramp == "brand-500"

    def test_success_warning_danger_ramps_flag(self, tmp_path: Path) -> None:
        findings = _scan(
            """
            .a { background: var(--success-500); }
            .b { background: var(--warning-500); }
            .c { background: var(--danger-500); }
            """,
            tmp_path,
        )
        assert len(findings) == 3
        assert {f.ramp for f in findings} == {
            "success-500",
            "warning-500",
            "danger-500",
        }

    def test_semantic_tokens_pass(self, tmp_path: Path) -> None:
        """``var(--colour-*)`` is the right answer — never flagged."""
        findings = _scan(
            """
            .x {
              background: var(--colour-bg);
              color: var(--colour-text);
              border: 1px solid var(--colour-border);
            }
            """,
            tmp_path,
        )
        assert findings == []

    def test_line_numbers_preserved(self, tmp_path: Path) -> None:
        findings = _scan(
            "/* line 1 — comment */\n"
            ".x {\n"
            "  background: var(--colour-bg);\n"
            "}\n"
            ".y {\n"
            "  background: var(--neutral-100);\n"
            "}\n",
            tmp_path,
        )
        assert len(findings) == 1
        assert findings[0].line == 6


# ---------------------------------------------------------------------------
# Exemptions
# ---------------------------------------------------------------------------


class TestThemeScopeExemption:
    def test_data_theme_dark_block_exempt(self, tmp_path: Path) -> None:
        """Raw ramps inside ``[data-theme="dark"] {…}`` are
        legitimate — that's the explicit dark-mode override."""
        findings = _scan(
            """
            [data-theme="dark"] .x {
              background: var(--neutral-900);
            }
            """,
            tmp_path,
        )
        assert findings == []

    def test_prefers_color_scheme_dark_block_exempt(self, tmp_path: Path) -> None:
        """Same exemption for the @media (prefers-color-scheme: dark)
        block."""
        findings = _scan(
            """
            @media (prefers-color-scheme: dark) {
              .x { background: var(--neutral-900); }
            }
            """,
            tmp_path,
        )
        assert findings == []

    def test_outside_theme_block_still_flags(self, tmp_path: Path) -> None:
        """A theme block exempts WHAT'S INSIDE IT, not the rest of
        the file. A raw ramp outside the block still fires."""
        findings = _scan(
            """
            [data-theme="dark"] .ok { background: var(--neutral-900); }
            .x { background: var(--neutral-100); }
            """,
            tmp_path,
        )
        assert len(findings) == 1
        assert findings[0].ramp == "neutral-100"

    def test_nested_theme_block_handled(self, tmp_path: Path) -> None:
        """Theme block with nested rules — depth tracking should
        still close out correctly so post-block declarations get
        scanned again."""
        findings = _scan(
            """
            [data-theme="dark"] {
              .a { background: var(--neutral-900); }
              .b { background: var(--neutral-800); }
            }
            .c { background: var(--neutral-100); }
            """,
            tmp_path,
        )
        assert len(findings) == 1
        assert findings[0].ramp == "neutral-100"


class TestFileExemption:
    def test_tokens_css_exempt(self, tmp_path: Path) -> None:
        """tokens.css DEFINES the semantic family in terms of
        ramps — no findings expected even though raw ramps are
        everywhere."""
        findings = _scan(
            ".x { background: var(--neutral-100); }",
            tmp_path,
            name="tokens.css",
        )
        assert findings == []

    def test_design_system_css_exempt(self, tmp_path: Path) -> None:
        findings = _scan(
            ".x { background: var(--neutral-100); }",
            tmp_path,
            name="design-system.css",
        )
        assert findings == []


# ---------------------------------------------------------------------------
# Parser robustness
# ---------------------------------------------------------------------------


class TestParser:
    def test_comments_stripped(self, tmp_path: Path) -> None:
        """Raw ramps mentioned inside a ``/* … */`` comment must NOT
        flag — they're documentation, not declarations."""
        findings = _scan(
            """
            .x {
              /* Earlier draft used var(--neutral-100) — switched to
                 colour-bg in cycle 1d. */
              background: var(--colour-bg);
            }
            """,
            tmp_path,
        )
        assert findings == []

    def test_zero_findings_on_empty_file(self, tmp_path: Path) -> None:
        assert _scan("", tmp_path) == []


# ---------------------------------------------------------------------------
# Pinned baseline
# ---------------------------------------------------------------------------


class TestComponentBaseline:
    """Pin the framework's own component CSS at zero findings. Any
    new component CSS that ships with a raw ramp regression fails
    CI before reaching a browser — complements cycle 1d's visual
    gates which catch the same class at runtime."""

    def test_component_css_has_zero_findings(self) -> None:
        findings = ramp.scan_paths([Path(ramp.COMPONENT_CSS_ROOT)])
        if findings:
            rendered = "\n\n".join(f.render() for f in findings)
            raise AssertionError(
                f"css_raw_ramp_check found {len(findings)} regression(s) "
                "in framework component CSS:\n\n"
                f"{rendered}\n\n"
                "Replace each raw ramp with a --colour-* semantic token "
                "(see tokens.css). The semantic family flips correctly "
                'under [data-theme="dark"]; raw ramps don\'t.'
            )


# ---------------------------------------------------------------------------
# Exit code
# ---------------------------------------------------------------------------


class TestExitCode:
    def test_clean_run_exits_zero(self, tmp_path: Path) -> None:
        f = tmp_path / "ok.css"
        f.write_text(".x { background: var(--colour-bg); }")
        assert ramp.main([str(f)]) == 0

    def test_findings_exit_one(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.css"
        f.write_text(".x { background: var(--neutral-100); }")
        assert ramp.main([str(f)]) == 1
