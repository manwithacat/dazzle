"""Tests for HTML input sanitization (#135)."""

import pytest

from dazzle.http.runtime.sanitizer import strip_html_tags

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
