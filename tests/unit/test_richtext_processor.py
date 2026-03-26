"""Tests for rich text processor (#coverage)."""

import pytest

from dazzle_back.runtime.richtext_processor import (
    HTMLProcessor,
    MarkdownProcessor,
    RichTextService,
)

# ---------------------------------------------------------------------------
# MarkdownProcessor — basic sanitization (no bleach dep needed)
# ---------------------------------------------------------------------------


class TestBasicSanitize:
    def test_strips_script_tags(self) -> None:
        proc = MarkdownProcessor()
        result = proc._basic_sanitize('<p>Hello</p><script>alert("xss")</script>')
        assert "<script>" not in result
        assert "alert" not in result
        assert "<p>Hello</p>" in result

    def test_strips_style_tags(self) -> None:
        proc = MarkdownProcessor()
        result = proc._basic_sanitize("<p>Hello</p><style>body{display:none}</style>")
        assert "<style>" not in result
        assert "<p>Hello</p>" in result

    def test_strips_iframe(self) -> None:
        proc = MarkdownProcessor()
        result = proc._basic_sanitize('<iframe src="evil.com"></iframe><p>safe</p>')
        assert "<iframe" not in result
        assert "<p>safe</p>" in result

    def test_strips_event_handlers(self) -> None:
        proc = MarkdownProcessor()
        result = proc._basic_sanitize('<div onclick="alert(1)">content</div>')
        assert "onclick" not in result
        assert "content" in result

    def test_strips_javascript_urls(self) -> None:
        proc = MarkdownProcessor()
        result = proc._basic_sanitize('<a href="javascript:alert(1)">click</a>')
        assert "javascript:" not in result

    def test_preserves_safe_attributes(self) -> None:
        proc = MarkdownProcessor()
        result = proc._basic_sanitize('<a href="https://example.com" title="link">click</a>')
        assert 'href="https://example.com"' in result
        assert 'title="link"' in result

    def test_nested_script_in_dangerous_tag(self) -> None:
        proc = MarkdownProcessor()
        html = "<script><script>nested</script></script><p>ok</p>"
        result = proc._basic_sanitize(html)
        assert "nested" not in result
        assert "<p>ok</p>" in result

    def test_preserves_plain_text(self) -> None:
        proc = MarkdownProcessor()
        assert proc._basic_sanitize("Hello, world!") == "Hello, world!"

    def test_empty_input(self) -> None:
        proc = MarkdownProcessor()
        assert proc._basic_sanitize("") == ""


# ---------------------------------------------------------------------------
# MarkdownProcessor — extract_text
# ---------------------------------------------------------------------------


class TestExtractText:
    def test_removes_images(self) -> None:
        proc = MarkdownProcessor()
        result = proc.extract_text("Hello ![alt](http://img.png) world")
        assert "alt" not in result
        assert "Hello" in result
        assert "world" in result

    def test_removes_links_keeps_text(self) -> None:
        proc = MarkdownProcessor()
        result = proc.extract_text("Visit [Google](https://google.com) now")
        assert "Google" in result
        assert "https://google.com" not in result

    def test_removes_formatting(self) -> None:
        proc = MarkdownProcessor()
        result = proc.extract_text("**bold** and _italic_ and ~~strike~~")
        assert "bold" in result
        assert "italic" in result
        assert "*" not in result
        assert "_" not in result

    def test_removes_code_block_markers(self) -> None:
        proc = MarkdownProcessor()
        result = proc.extract_text("Before ```python\ncode()\n``` after")
        assert "```" not in result
        assert "Before" in result

    def test_removes_inline_code_markers(self) -> None:
        proc = MarkdownProcessor()
        result = proc.extract_text("Use `foo()` here")
        assert "`" not in result
        assert "Use" in result

    def test_removes_html_tags(self) -> None:
        proc = MarkdownProcessor()
        result = proc.extract_text("Hello <strong>world</strong>")
        assert "<strong>" not in result
        assert "Hello" in result

    def test_normalizes_whitespace(self) -> None:
        proc = MarkdownProcessor()
        result = proc.extract_text("Hello   \n\n  world")
        assert result == "Hello world"

    def test_empty_string(self) -> None:
        proc = MarkdownProcessor()
        assert proc.extract_text("") == ""


# ---------------------------------------------------------------------------
# MarkdownProcessor — truncate
# ---------------------------------------------------------------------------


class TestTruncate:
    def test_short_text_not_truncated(self) -> None:
        proc = MarkdownProcessor()
        assert proc.truncate("Hello", max_length=100) == "Hello"

    def test_long_text_truncated(self) -> None:
        proc = MarkdownProcessor()
        text = "word " * 100  # ~500 chars
        result = proc.truncate(text, max_length=50)
        assert len(result) <= 55  # 50 + "..."
        assert result.endswith("...")

    def test_breaks_at_word_boundary(self) -> None:
        proc = MarkdownProcessor()
        text = "Hello beautiful world today"
        result = proc.truncate(text, max_length=20)
        assert result.endswith("...")
        # Should break at a space, not mid-word
        without_suffix = result[:-3]
        assert not without_suffix.endswith(" ")  # trimmed

    def test_custom_suffix(self) -> None:
        proc = MarkdownProcessor()
        text = "A very long text that needs to be cut"
        result = proc.truncate(text, max_length=15, suffix=" [more]")
        assert result.endswith("[more]")

    def test_strips_markdown_before_truncating(self) -> None:
        proc = MarkdownProcessor()
        text = "**Bold text** and _italic text_ more words here and more"
        result = proc.truncate(text, max_length=30)
        assert "*" not in result
        assert "_" not in result


# ---------------------------------------------------------------------------
# MarkdownProcessor — render_html (requires markdown package)
# ---------------------------------------------------------------------------


class TestRenderHtml:
    def test_render_basic(self) -> None:
        proc = MarkdownProcessor(sanitize=False)
        if not proc.is_available():
            pytest.skip("markdown package not installed")
        html = proc.render_html("# Hello")
        assert "<h1" in html
        assert "Hello" in html

    def test_render_with_fenced_code(self) -> None:
        proc = MarkdownProcessor(sanitize=False)
        if not proc.is_available():
            pytest.skip("markdown package not installed")
        html = proc.render_html("```python\nprint('hi')\n```")
        assert "<code" in html
        assert "print" in html

    def test_render_with_table(self) -> None:
        proc = MarkdownProcessor(sanitize=False)
        if not proc.is_available():
            pytest.skip("markdown package not installed")
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        html = proc.render_html(md)
        assert "<table>" in html


# ---------------------------------------------------------------------------
# MarkdownProcessor — is_available
# ---------------------------------------------------------------------------


class TestIsAvailable:
    def test_returns_bool(self) -> None:
        result = MarkdownProcessor.is_available()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# MarkdownProcessor — process_inline_images
# ---------------------------------------------------------------------------


class TestProcessInlineImages:
    @pytest.mark.asyncio
    async def test_no_storage_returns_unchanged(self) -> None:
        proc = MarkdownProcessor(storage=None)
        text = "![img](data:image/png;base64,abc123)"
        assert await proc.process_inline_images(text) == text

    @pytest.mark.asyncio
    async def test_images_not_allowed_returns_unchanged(self) -> None:
        proc = MarkdownProcessor(allow_images=False)
        text = "![img](data:image/png;base64,abc123)"
        assert await proc.process_inline_images(text) == text

    @pytest.mark.asyncio
    async def test_no_base64_images_returns_unchanged(self) -> None:
        from unittest.mock import MagicMock

        proc = MarkdownProcessor(storage=MagicMock())
        text = "![img](https://example.com/img.png)"
        assert await proc.process_inline_images(text) == text


# ---------------------------------------------------------------------------
# HTMLProcessor
# ---------------------------------------------------------------------------


class TestHTMLProcessor:
    def test_clean_sanitizes(self) -> None:
        proc = HTMLProcessor()
        result = proc.clean("<p>Hello</p><script>evil()</script>")
        assert "<script>" not in result
        assert "<p>Hello</p>" in result

    def test_clean_no_sanitize(self) -> None:
        proc = HTMLProcessor(sanitize=False)
        html = "<script>alert(1)</script>"
        assert proc.clean(html) == html

    def test_extract_text(self) -> None:
        proc = HTMLProcessor()
        result = proc.extract_text("<p>Hello <strong>World</strong></p>")
        assert "Hello" in result
        assert "World" in result
        assert "<" not in result

    def test_extract_text_decodes_entities(self) -> None:
        proc = HTMLProcessor()
        result = proc.extract_text("<p>A &amp; B</p>")
        assert "A & B" in result


# ---------------------------------------------------------------------------
# RichTextService
# ---------------------------------------------------------------------------


class TestRichTextService:
    def test_render_html_markdown(self) -> None:
        svc = RichTextService()
        if not MarkdownProcessor.is_available():
            pytest.skip("markdown package not installed")
        html = svc.render_html("**bold**", format="markdown")
        assert "bold" in html

    def test_render_html_passthrough(self) -> None:
        svc = RichTextService()
        result = svc.render_html("<p>Hello</p><script>x</script>", format="html")
        assert "<script>" not in result
        assert "<p>Hello</p>" in result

    def test_extract_text_markdown(self) -> None:
        svc = RichTextService(default_format="markdown")
        assert "bold" in svc.extract_text("**bold** text")

    def test_extract_text_html(self) -> None:
        svc = RichTextService(default_format="html")
        assert "Hello" in svc.extract_text("<p>Hello</p>")

    def test_preview_markdown(self) -> None:
        svc = RichTextService(default_format="markdown")
        text = "word " * 100
        result = svc.preview(text, max_length=50)
        assert len(result) <= 55

    def test_preview_html(self) -> None:
        svc = RichTextService(default_format="html")
        text = "<p>" + "word " * 100 + "</p>"
        result = svc.preview(text, max_length=50)
        assert len(result) <= 55

    @pytest.mark.asyncio
    async def test_process_content_html_passthrough(self) -> None:
        svc = RichTextService()
        result = await svc.process_content("<p>Hello</p>", format="html")
        assert result == "<p>Hello</p>"
