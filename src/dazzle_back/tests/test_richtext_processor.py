"""
Tests for rich text processor.

Tests markdown rendering, HTML sanitization, and text extraction.
"""

import pytest

# Check if dependencies are available
try:
    import markdown  # noqa: F401

    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False

try:
    import bleach  # noqa: F401

    BLEACH_AVAILABLE = True
except ImportError:
    BLEACH_AVAILABLE = False

from dazzle_back.runtime.richtext_processor import (
    HTMLProcessor,
    MarkdownProcessor,
    RichTextService,
)

# =============================================================================
# MarkdownProcessor Tests
# =============================================================================


class TestMarkdownProcessor:
    """Tests for MarkdownProcessor."""

    def test_is_available(self):
        """Test availability check."""
        assert MarkdownProcessor.is_available() == MARKDOWN_AVAILABLE

    @pytest.mark.skipif(not MARKDOWN_AVAILABLE, reason="markdown not installed")
    def test_render_basic_markdown(self):
        """Test basic markdown rendering."""
        processor = MarkdownProcessor()
        html = processor.render_html("# Hello World")

        assert "<h1" in html
        assert "Hello World" in html

    @pytest.mark.skipif(not MARKDOWN_AVAILABLE, reason="markdown not installed")
    def test_render_emphasis(self):
        """Test emphasis rendering."""
        processor = MarkdownProcessor()

        html = processor.render_html("**bold** and *italic*")

        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html

    @pytest.mark.skipif(not MARKDOWN_AVAILABLE, reason="markdown not installed")
    def test_render_links(self):
        """Test link rendering."""
        processor = MarkdownProcessor()
        html = processor.render_html("[Link](https://example.com)")

        assert '<a href="https://example.com">' in html
        assert "Link</a>" in html

    @pytest.mark.skipif(not MARKDOWN_AVAILABLE, reason="markdown not installed")
    def test_render_code_blocks(self):
        """Test code block rendering."""
        processor = MarkdownProcessor()
        md = "```python\nprint('hello')\n```"
        html = processor.render_html(md)

        assert "<code" in html
        assert "print" in html

    @pytest.mark.skipif(not MARKDOWN_AVAILABLE, reason="markdown not installed")
    def test_render_lists(self):
        """Test list rendering."""
        processor = MarkdownProcessor()
        md = "- Item 1\n- Item 2\n- Item 3"
        html = processor.render_html(md)

        assert "<ul>" in html
        assert "<li>" in html
        assert "Item 1" in html

    @pytest.mark.skipif(not MARKDOWN_AVAILABLE, reason="markdown not installed")
    def test_render_tables(self):
        """Test table rendering."""
        processor = MarkdownProcessor()
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        html = processor.render_html(md)

        assert "<table>" in html
        assert "<th>" in html or "<td>" in html

    @pytest.mark.skipif(not MARKDOWN_AVAILABLE, reason="markdown not installed")
    @pytest.mark.skipif(not BLEACH_AVAILABLE, reason="bleach not installed")
    def test_sanitize_script_tags(self):
        """Test that script tags are removed."""
        processor = MarkdownProcessor(sanitize=True)
        md = 'Hello <script>alert("xss")</script> World'
        html = processor.render_html(md)

        # bleach strips tags but may keep text content
        assert "<script>" not in html
        assert "</script>" not in html

    @pytest.mark.skipif(not MARKDOWN_AVAILABLE, reason="markdown not installed")
    def test_sanitize_event_handlers(self):
        """Test that event handlers are removed."""
        processor = MarkdownProcessor(sanitize=True)
        md = '<img src="x" onerror="alert(1)">'
        html = processor.render_html(md)

        assert "onerror" not in html

    @pytest.mark.skipif(not MARKDOWN_AVAILABLE, reason="markdown not installed")
    @pytest.mark.skipif(not BLEACH_AVAILABLE, reason="bleach not installed")
    def test_sanitize_javascript_urls(self):
        """Test that javascript: URLs are blocked."""
        processor = MarkdownProcessor(sanitize=True)
        md = "[Click](javascript:alert(1))"
        html = processor.render_html(md)

        assert "javascript:" not in html

    def test_extract_text_basic(self):
        """Test basic text extraction."""
        processor = MarkdownProcessor()
        md = "# Title\n\nSome **bold** and *italic* text."
        text = processor.extract_text(md)

        assert "Title" in text
        assert "Some bold and italic text" in text
        assert "**" not in text
        assert "*" not in text
        assert "#" not in text

    def test_extract_text_with_links(self):
        """Test text extraction from links."""
        processor = MarkdownProcessor()
        md = "Check [this link](https://example.com) out."
        text = processor.extract_text(md)

        assert "this link" in text
        assert "https://example.com" not in text

    def test_extract_text_with_images(self):
        """Test text extraction removes images."""
        processor = MarkdownProcessor()
        md = "See ![image](https://example.com/img.png) here."
        text = processor.extract_text(md)

        assert "image" not in text
        assert "https://example.com" not in text

    def test_extract_text_with_code(self):
        """Test text extraction removes inline code markers."""
        processor = MarkdownProcessor()
        md = "Run `print()` to output."
        text = processor.extract_text(md)

        assert "`" not in text
        assert "print" in text  # Content is kept, just backticks removed

    def test_truncate_short_text(self):
        """Test truncation of short text."""
        processor = MarkdownProcessor()
        md = "Short text"
        result = processor.truncate(md, max_length=100)

        assert result == "Short text"

    def test_truncate_long_text(self):
        """Test truncation of long text."""
        processor = MarkdownProcessor()
        md = "This is a longer piece of text that should be truncated."
        result = processor.truncate(md, max_length=20)

        assert len(result) < len(md)
        assert result.endswith("...")

    def test_truncate_at_word_boundary(self):
        """Test truncation at word boundary."""
        processor = MarkdownProcessor()
        md = "Hello world this is a test"
        result = processor.truncate(md, max_length=15)

        # Should break at "world" not mid-word
        assert result in ["Hello world...", "Hello..."]


# =============================================================================
# HTMLProcessor Tests
# =============================================================================


class TestHTMLProcessor:
    """Tests for HTMLProcessor."""

    def test_clean_basic(self):
        """Test basic HTML cleaning."""
        processor = HTMLProcessor()
        html = "<p>Hello <b>World</b></p>"
        cleaned = processor.clean(html)

        assert "<p>" in cleaned
        assert "Hello" in cleaned

    @pytest.mark.skipif(not BLEACH_AVAILABLE, reason="bleach not installed")
    def test_clean_removes_script(self):
        """Test script tag removal."""
        processor = HTMLProcessor()
        html = "<p>Safe</p><script>alert(1)</script>"
        cleaned = processor.clean(html)

        # bleach strips tags but may keep text content
        assert "<script>" not in cleaned
        assert "</script>" not in cleaned
        assert "Safe" in cleaned

    def test_extract_text(self):
        """Test text extraction from HTML."""
        processor = HTMLProcessor()
        html = "<p>Hello <b>World</b></p><div>More text</div>"
        text = processor.extract_text(html)

        assert "Hello World" in text
        assert "More text" in text
        assert "<p>" not in text
        assert "<b>" not in text

    def test_extract_text_with_entities(self):
        """Test HTML entity decoding."""
        processor = HTMLProcessor()
        html = "<p>&amp; &lt; &gt; &quot;</p>"
        text = processor.extract_text(html)

        assert "&" in text
        assert "<" in text
        assert ">" in text


# =============================================================================
# RichTextService Tests
# =============================================================================


class TestRichTextService:
    """Tests for RichTextService."""

    def test_default_format_markdown(self):
        """Test default markdown format."""
        service = RichTextService(default_format="markdown")
        assert service.default_format == "markdown"

    def test_default_format_html(self):
        """Test default html format."""
        service = RichTextService(default_format="html")
        assert service.default_format == "html"

    @pytest.mark.skipif(not MARKDOWN_AVAILABLE, reason="markdown not installed")
    def test_render_html_markdown(self):
        """Test rendering markdown to HTML."""
        service = RichTextService()
        html = service.render_html("# Hello", format="markdown")

        assert "<h1" in html
        assert "Hello" in html

    def test_render_html_raw(self):
        """Test rendering raw HTML."""
        service = RichTextService()
        html = service.render_html("<p>Hello</p>", format="html")

        assert "<p>" in html
        assert "Hello" in html

    def test_extract_text_markdown(self):
        """Test text extraction from markdown."""
        service = RichTextService()
        text = service.extract_text("# Title\n\n**Bold** text", format="markdown")

        assert "Title" in text
        assert "Bold text" in text
        assert "#" not in text
        assert "**" not in text

    def test_extract_text_html(self):
        """Test text extraction from HTML."""
        service = RichTextService()
        text = service.extract_text("<h1>Title</h1><p>Text</p>", format="html")

        assert "Title" in text
        assert "Text" in text
        assert "<h1>" not in text

    def test_preview_markdown(self):
        """Test markdown preview."""
        service = RichTextService()
        long_text = "# Title\n\n" + "Word " * 100
        preview = service.preview(long_text, max_length=50, format="markdown")

        assert len(preview) < 100
        assert preview.endswith("...")

    def test_preview_html(self):
        """Test HTML preview."""
        service = RichTextService()
        html = "<p>" + "Word " * 100 + "</p>"
        preview = service.preview(html, max_length=50, format="html")

        assert len(preview) < 100
        assert "<p>" not in preview


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_content(self):
        """Test handling empty content."""
        processor = MarkdownProcessor()
        text = processor.extract_text("")

        assert text == ""

    def test_whitespace_only(self):
        """Test handling whitespace-only content."""
        processor = MarkdownProcessor()
        text = processor.extract_text("   \n\n   ")

        assert text == ""

    @pytest.mark.skipif(not MARKDOWN_AVAILABLE, reason="markdown not installed")
    def test_deeply_nested_formatting(self):
        """Test deeply nested formatting."""
        processor = MarkdownProcessor()
        md = "***bold and italic***"
        html = processor.render_html(md)

        assert "bold and italic" in html

    def test_unicode_content(self):
        """Test handling unicode content."""
        processor = MarkdownProcessor()
        md = "# 你好世界\n\nEmoji: 🎉"
        text = processor.extract_text(md)

        assert "你好世界" in text
        assert "🎉" in text

    @pytest.mark.skipif(not MARKDOWN_AVAILABLE, reason="markdown not installed")
    def test_malformed_markdown(self):
        """Test handling malformed markdown."""
        processor = MarkdownProcessor()
        # Unclosed formatting
        md = "**unclosed bold"
        html = processor.render_html(md)

        # Should not crash
        assert "unclosed bold" in html

    def test_very_long_content(self):
        """Test handling very long content."""
        processor = MarkdownProcessor()
        long_md = "# Title\n\n" + ("Paragraph text. " * 1000)
        text = processor.extract_text(long_md)

        assert "Title" in text
        assert len(text) > 1000

    @pytest.mark.skipif(not MARKDOWN_AVAILABLE, reason="markdown not installed")
    def test_nested_code_blocks(self):
        """Test nested code in code blocks."""
        processor = MarkdownProcessor()
        md = "```\n```nested```\n```"
        html = processor.render_html(md)

        # Should handle gracefully
        assert "<code" in html or "nested" in html
