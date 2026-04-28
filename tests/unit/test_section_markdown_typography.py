"""Regression tests for site-sections.css article-body typography (issue #921).

The `.dz-section h1/h2/h3/p` rules style marketing section *headlines* —
centred, large, heavy. Without scoped overrides, those rules bleed into
markdown article bodies (blog posts, generic content) where the same H2
elements appear inside `.dz-section-markdown` / `.dz-section .prose`
containers. The fix adds explicit article-body overrides so blog body
H2s render left-aligned at body sizes.
"""

from pathlib import Path

CSS_PATH = Path("src/dazzle_ui/runtime/static/css/site-sections.css")


class TestSectionMarkdownTypography:
    """Article body H1-H4 inside .dz-section must opt out of headline styling."""

    def _read_css(self) -> str:
        return CSS_PATH.read_text()

    def test_markdown_h2_text_align_override_exists(self):
        css = self._read_css()
        assert ".dz-section-markdown h2" in css
        assert ".dz-section .prose h2" in css

    def test_markdown_h2_starts_left_not_centred(self):
        """The override must declare text-align: start (or left)."""
        css = self._read_css()
        # Find the article-body override block
        marker = "/* --- Article body / markdown typography ---"
        assert marker in css, "article-body override block missing"
        block_start = css.index(marker)
        block = css[block_start : block_start + 2000]
        assert "text-align: start" in block or "text-align: left" in block

    def test_markdown_h2_smaller_than_section_headline(self):
        """Article H2s should be ~1.5rem, not the 2.25rem of section headlines."""
        css = self._read_css()
        marker = "/* --- Article body / markdown typography ---"
        block_start = css.index(marker)
        block = css[block_start : block_start + 2500]
        assert "font-size: 1.5rem" in block

    def test_all_article_levels_overridden(self):
        """h1, h2, h3, h4, p should all have markdown overrides."""
        css = self._read_css()
        marker = "/* --- Article body / markdown typography ---"
        block_start = css.index(marker)
        block = css[block_start : block_start + 3000]
        for selector in (
            ".dz-section-markdown h1",
            ".dz-section-markdown h2",
            ".dz-section-markdown h3",
            ".dz-section-markdown h4",
            ".dz-section-markdown p",
            ".dz-section .prose h1",
            ".dz-section .prose h2",
            ".dz-section .prose h3",
            ".dz-section .prose h4",
            ".dz-section .prose p",
        ):
            assert selector in block, f"{selector} missing from article-body block"

    def test_responsive_markdown_override_exists(self):
        """The responsive .dz-section h2 rule must have a markdown override.

        The file has multiple @media (max-width: 768px) blocks; we want the
        one that contains the .dz-section h2 mobile override. Find that
        block and assert the markdown override sits right alongside it.
        """
        css = self._read_css()
        # Find the .dz-section h2 rule inside a 768px @media block
        anchor = "  .dz-section h2 {\n    font-size: 1.75rem;\n  }"
        assert anchor in css, "responsive .dz-section h2 rule not found"
        idx = css.index(anchor)
        # Inspect the surrounding 1500 chars (after the anchor)
        nearby = css[idx : idx + 1500]
        assert ".dz-section-markdown h2" in nearby
        assert ".dz-section .prose h2" in nearby

    def test_section_headline_rule_still_centred(self):
        """The base .dz-section h2 rule must still apply to marketing headlines —
        we only ADD overrides, we don't remove the centred-headline behaviour."""
        css = self._read_css()
        # The original rule has text-align: center
        # Find the .dz-section h2 block (not .dz-section-markdown / .prose)
        # Look for the specific block that opens with `.dz-section h2 {` on its own line
        idx = css.index("\n.dz-section h2 {\n")
        block = css[idx : idx + 400]
        assert "text-align: center" in block
