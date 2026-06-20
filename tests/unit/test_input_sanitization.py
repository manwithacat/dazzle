"""Tests for HTML input sanitization (#135)."""

import pytest

from dazzle.http.runtime.sanitizer import strip_dangerous_tags, strip_html_tags

# ---------------------------------------------------------------------------
# strip_html_tags (str fields)
# ---------------------------------------------------------------------------


class TestStripHtmlTags:
    """Tests for complete HTML tag stripping on str fields."""

    @pytest.mark.parametrize(
        ("input_str", "expected"),
        [
            ('<script>alert("xss")</script>', 'alert("xss")'),
            ("Hello, World!", "Hello, World!"),  # normal text preserved
            ("3 < 5 is true", "3 < 5 is true"),  # `<` not followed by tag-name
            ("<b>bold</b> and <i>italic</i>", "bold and italic"),
            ("", ""),
            ("<div><p>hello</p></div>", "hello"),  # nested tags
            ('<img src="x" onerror="alert(1)">text', "text"),
        ],
        ids=[
            "script_tags_stripped",
            "normal_text_preserved",
            "angle_brackets_in_normal_text",
            "all_tags_removed",
            "empty_string",
            "nested_tags",
            "img_tag_removed",
        ],
    )
    def test_strip(self, input_str, expected) -> None:
        assert strip_html_tags(input_str) == expected


# ---------------------------------------------------------------------------
# strip_dangerous_tags (text fields)
# ---------------------------------------------------------------------------


class TestStripDangerousTags:
    """Tests for selective dangerous tag stripping on text fields."""

    def test_script_stripped(self):
        result = strip_dangerous_tags("Hello <script>alert(1)</script> World")
        assert "<script>" not in result
        assert "Hello" in result
        assert "World" in result

    def test_iframe_stripped(self):
        result = strip_dangerous_tags('<iframe src="evil.com"></iframe>')
        assert "<iframe" not in result

    def test_safe_html_preserved(self):
        html = "<p>Hello <b>bold</b> and <a href='/page'>link</a></p>"
        assert strip_dangerous_tags(html) == html

    def test_event_handler_stripped(self):
        result = strip_dangerous_tags('<div onclick="alert(1)">click</div>')
        assert "onclick" not in result
        assert "click" in result

    def test_onerror_stripped(self):
        result = strip_dangerous_tags('<img src="x" onerror="alert(1)">')
        assert "onerror" not in result

    def test_javascript_protocol_stripped(self):
        result = strip_dangerous_tags('<a href="javascript:alert(1)">link</a>')
        assert "javascript:" not in result

    def test_empty_string(self):
        assert strip_dangerous_tags("") == ""

    def test_plain_text_preserved(self):
        assert strip_dangerous_tags("no html here") == "no html here"

    def test_form_tags_stripped(self):
        result = strip_dangerous_tags(
            '<form action="/steal"><input type="hidden" name="token"></form>'
        )
        assert "<form" not in result
        assert "<input" not in result
