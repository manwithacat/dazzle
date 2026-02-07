"""
Rich text processing for DNR.

Provides markdown processing, HTML sanitization, and inline image handling.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .file_storage import StorageBackend


class RichTextProcessingError(Exception):
    """Raised when rich text processing fails."""

    pass


class MarkdownProcessor:
    """
    Process markdown content with security and image handling.

    Features:
    - Markdown to HTML conversion
    - HTML sanitization (XSS prevention)
    - Inline image processing (base64 to storage)
    - Code block syntax highlighting
    """

    def __init__(
        self,
        storage: StorageBackend | None = None,
        allow_images: bool = True,
        allow_html: bool = False,
        sanitize: bool = True,
    ):
        """
        Initialize markdown processor.

        Args:
            storage: Storage backend for inline images
            allow_images: Whether to allow inline images
            allow_html: Whether to allow raw HTML in markdown
            sanitize: Whether to sanitize HTML output
        """
        self.storage = storage
        self.allow_images = allow_images
        self.allow_html = allow_html
        self.sanitize = sanitize

    @staticmethod
    def is_available() -> bool:
        """Check if markdown processing is available."""
        try:
            import markdown  # type: ignore[import-untyped]  # noqa: F401

            return True
        except ImportError:
            return False

    def render_html(self, markdown_text: str) -> str:
        """
        Render markdown to safe HTML.

        Args:
            markdown_text: Markdown content

        Returns:
            Sanitized HTML

        Raises:
            RichTextProcessingError: If rendering fails
        """
        try:
            import markdown as md
        except ImportError:
            raise RichTextProcessingError(
                "markdown package is required. Install with: pip install markdown"
            )

        try:
            # Configure extensions
            extensions = [
                "fenced_code",
                "tables",
                "nl2br",
                "sane_lists",
                "toc",
            ]

            # Render markdown to HTML
            html: str = md.markdown(markdown_text, extensions=extensions)

            # Sanitize if enabled
            if self.sanitize:
                html = self._sanitize_html(html)

            return html

        except Exception as e:
            raise RichTextProcessingError(f"Failed to render markdown: {e}")

    def _sanitize_html(self, html: str) -> str:
        """
        Sanitize HTML to prevent XSS attacks.

        Args:
            html: Raw HTML content

        Returns:
            Sanitized HTML
        """
        try:
            import bleach  # type: ignore[import-untyped]
        except ImportError:
            # Fallback: basic tag stripping
            return self._basic_sanitize(html)

        # Allowed tags
        allowed_tags = [
            "p",
            "br",
            "hr",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "strong",
            "em",
            "b",
            "i",
            "u",
            "s",
            "strike",
            "a",
            "img",
            "ul",
            "ol",
            "li",
            "code",
            "pre",
            "blockquote",
            "table",
            "thead",
            "tbody",
            "tfoot",
            "tr",
            "th",
            "td",
            "div",
            "span",
        ]

        # Allowed attributes
        allowed_attrs = {
            "a": ["href", "title", "rel", "target"],
            "img": ["src", "alt", "title", "width", "height"],
            "code": ["class"],  # For syntax highlighting
            "pre": ["class"],
            "th": ["colspan", "rowspan"],
            "td": ["colspan", "rowspan"],
        }

        # Allowed protocols
        allowed_protocols = ["http", "https", "mailto"]

        if not self.allow_images:
            allowed_tags.remove("img")

        sanitized: str = bleach.clean(
            html,
            tags=allowed_tags,
            attributes=allowed_attrs,
            protocols=allowed_protocols,
            strip=True,
        )

        return sanitized

    def _basic_sanitize(self, html: str) -> str:
        """
        Basic HTML sanitization without bleach.

        This is a fallback that removes script tags and event handlers.
        """
        # Remove script tags
        html = re.sub(
            r"<script[^>]*>.*?</script>",
            "",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )

        # Remove style tags
        html = re.sub(
            r"<style[^>]*>.*?</style>",
            "",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )

        # Remove event handlers
        html = re.sub(
            r'\s+on\w+\s*=\s*["\'][^"\']*["\']',
            "",
            html,
            flags=re.IGNORECASE,
        )

        # Remove javascript: URLs
        html = re.sub(
            r'href\s*=\s*["\']javascript:[^"\']*["\']',
            'href="#"',
            html,
            flags=re.IGNORECASE,
        )

        return html

    async def process_inline_images(
        self,
        markdown_text: str,
        entity_name: str | None = None,
        entity_id: str | None = None,
    ) -> str:
        """
        Process base64 inline images, upload them, and replace with URLs.

        Args:
            markdown_text: Markdown with potential inline images
            entity_name: Associated entity name
            entity_id: Associated entity ID

        Returns:
            Markdown with image URLs instead of base64 data

        Raises:
            RichTextProcessingError: If processing fails
        """
        if not self.storage:
            return markdown_text

        if not self.allow_images:
            return markdown_text

        # Pattern to match base64 images in markdown
        # ![alt](data:image/png;base64,...)
        pattern = r"!\[([^\]]*)\]\(data:([^;]+);base64,([^)]+)\)"

        async def replace_match(match: re.Match[str]) -> str:
            alt = match.group(1)
            content_type = match.group(2)
            base64_data = match.group(3)

            try:
                import base64
                from io import BytesIO
                from uuid import uuid4

                data = base64.b64decode(base64_data)
                file = BytesIO(data)

                ext = content_type.split("/")[-1]
                filename = f"inline_{uuid4().hex[:8]}.{ext}"

                path_prefix = "richtext"
                if entity_name:
                    path_prefix = f"richtext/{entity_name}"

                assert self.storage is not None  # checked at method entry
                metadata = await self.storage.store(
                    file, filename, content_type, path_prefix=path_prefix
                )

                return f"![{alt}]({metadata.url})"

            except Exception as e:
                raise RichTextProcessingError(f"Failed to process inline image: {e}")

        # Find all matches and process
        matches = list(re.finditer(pattern, markdown_text))

        if not matches:
            return markdown_text

        result = markdown_text
        for match in reversed(matches):  # Reverse to preserve positions
            replacement = await replace_match(match)
            result = result[: match.start()] + replacement + result[match.end() :]

        return result

    def extract_text(self, markdown_text: str) -> str:
        """
        Extract plain text from markdown.

        Useful for search indexing and previews.

        Args:
            markdown_text: Markdown content

        Returns:
            Plain text without formatting
        """
        # Remove images
        text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", markdown_text)

        # Remove links but keep text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

        # Remove formatting
        text = re.sub(r"[*_~`#]+", "", text)

        # Remove code blocks
        text = re.sub(r"```[^`]*```", "", text, flags=re.DOTALL)
        text = re.sub(r"`[^`]+`", "", text)

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def truncate(
        self,
        markdown_text: str,
        max_length: int = 200,
        suffix: str = "...",
    ) -> str:
        """
        Truncate markdown to a maximum length.

        Useful for previews and summaries.

        Args:
            markdown_text: Markdown content
            max_length: Maximum character length
            suffix: Suffix to add if truncated

        Returns:
            Truncated plain text
        """
        text = self.extract_text(markdown_text)

        if len(text) <= max_length:
            return text

        # Try to break at word boundary
        truncated = text[:max_length]
        last_space = truncated.rfind(" ")

        if last_space > max_length * 0.7:  # Break at word if reasonable
            truncated = truncated[:last_space]

        return truncated + suffix


class HTMLProcessor:
    """
    Process HTML content with sanitization.

    For when users input HTML directly instead of markdown.
    """

    def __init__(
        self,
        allow_images: bool = True,
        sanitize: bool = True,
    ):
        """
        Initialize HTML processor.

        Args:
            allow_images: Whether to allow img tags
            sanitize: Whether to sanitize HTML
        """
        self.allow_images = allow_images
        self.sanitize = sanitize
        self._markdown_processor = MarkdownProcessor(
            allow_images=allow_images,
            sanitize=sanitize,
        )

    def clean(self, html: str) -> str:
        """
        Clean and sanitize HTML.

        Args:
            html: Raw HTML content

        Returns:
            Sanitized HTML
        """
        if self.sanitize:
            return self._markdown_processor._sanitize_html(html)
        return html

    def extract_text(self, html: str) -> str:
        """
        Extract plain text from HTML.

        Args:
            html: HTML content

        Returns:
            Plain text
        """
        # Remove all tags
        text = re.sub(r"<[^>]+>", " ", html)

        # Decode HTML entities
        try:
            import html as html_module

            text = html_module.unescape(text)
        except ImportError:
            pass

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text


# =============================================================================
# Rich Text Service
# =============================================================================


class RichTextService:
    """
    High-level service for rich text processing.

    Handles both markdown and HTML content.
    """

    def __init__(
        self,
        storage: StorageBackend | None = None,
        default_format: str = "markdown",
        allow_images: bool = True,
        sanitize: bool = True,
    ):
        """
        Initialize rich text service.

        Args:
            storage: Storage backend for images
            default_format: Default format (markdown or html)
            allow_images: Whether to allow images
            sanitize: Whether to sanitize output
        """
        self.storage = storage
        self.default_format = default_format

        self.markdown_processor = MarkdownProcessor(
            storage=storage,
            allow_images=allow_images,
            sanitize=sanitize,
        )

        self.html_processor = HTMLProcessor(
            allow_images=allow_images,
            sanitize=sanitize,
        )

    def render_html(
        self,
        content: str,
        format: str | None = None,
    ) -> str:
        """
        Render content to HTML.

        Args:
            content: Raw content
            format: Content format (markdown or html)

        Returns:
            Rendered HTML
        """
        format = format or self.default_format

        if format == "markdown":
            return self.markdown_processor.render_html(content)
        else:
            return self.html_processor.clean(content)

    async def process_content(
        self,
        content: str,
        format: str | None = None,
        entity_name: str | None = None,
        entity_id: str | None = None,
    ) -> str:
        """
        Process content including inline images.

        Args:
            content: Raw content
            format: Content format
            entity_name: Associated entity
            entity_id: Associated entity ID

        Returns:
            Processed content (images uploaded, URLs replaced)
        """
        format = format or self.default_format

        if format == "markdown":
            return await self.markdown_processor.process_inline_images(
                content, entity_name, entity_id
            )

        return content

    def extract_text(self, content: str, format: str | None = None) -> str:
        """
        Extract plain text from content.

        Args:
            content: Raw content
            format: Content format

        Returns:
            Plain text
        """
        format = format or self.default_format

        if format == "markdown":
            return self.markdown_processor.extract_text(content)
        else:
            return self.html_processor.extract_text(content)

    def preview(
        self,
        content: str,
        max_length: int = 200,
        format: str | None = None,
    ) -> str:
        """
        Generate a text preview.

        Args:
            content: Raw content
            max_length: Maximum preview length
            format: Content format

        Returns:
            Truncated plain text preview
        """
        format = format or self.default_format

        if format == "markdown":
            return self.markdown_processor.truncate(content, max_length)
        else:
            text = self.html_processor.extract_text(content)
            if len(text) > max_length:
                text = text[:max_length].rsplit(" ", 1)[0] + "..."
            return text
