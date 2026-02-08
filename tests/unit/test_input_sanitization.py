"""Tests for HTML input sanitization (#135)."""

from __future__ import annotations

from dazzle_back.runtime.sanitizer import strip_dangerous_tags, strip_html_tags

# ---------------------------------------------------------------------------
# strip_html_tags (str fields)
# ---------------------------------------------------------------------------


class TestStripHtmlTags:
    """Tests for complete HTML tag stripping on str fields."""

    def test_script_tags_stripped(self):
        assert strip_html_tags('<script>alert("xss")</script>') == 'alert("xss")'

    def test_normal_text_preserved(self):
        assert strip_html_tags("Hello, World!") == "Hello, World!"

    def test_angle_brackets_in_normal_text(self):
        # Edge: a < b > c is not a valid tag
        assert strip_html_tags("3 < 5 is true") == "3 < 5 is true"

    def test_all_tags_removed(self):
        assert strip_html_tags("<b>bold</b> and <i>italic</i>") == "bold and italic"

    def test_empty_string(self):
        assert strip_html_tags("") == ""

    def test_nested_tags(self):
        assert strip_html_tags("<div><p>hello</p></div>") == "hello"

    def test_img_tag_removed(self):
        assert strip_html_tags('<img src="x" onerror="alert(1)">text') == "text"


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
