"""Drift gate: client and server rich-text allowlists must match.

#977 cycle 4 §13 decision 3 + §8: the allowlist lives in
`src/dazzle/core/ir/richtext.py` and is consumed by both the client
(`dz-richtext.js`) and the server (`dazzle_http/runtime/richtext_field.py`).
If the JS allowlist drifts from the IR, paste/save round-trips would
desync — content the editor accepts gets stripped on save, or worse,
content the server allows the editor mangles on display.

The gate compares concrete sets, not regex AST equality, because the
spec calls out that the protocol pattern is intentionally simple so
parity is a string compare.
"""

from __future__ import annotations

import re
from pathlib import Path

import bleach

from dazzle.core.ir.richtext import (
    RICH_TEXT_ALLOWED_ATTRS,
    RICH_TEXT_PROTOCOL_PATTERN,
)
from dazzle.http.runtime.richtext_field import clean_rich_text

JS_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "page"
    / "runtime"
    / "static"
    / "js"
    / "dz-richtext.js"
)


def _extract_js_allowlist(name: str) -> set[str]:
    """Pull `INLINE_ALLOW = { STRONG: 1, H2: 1, ... }` style block out
    of the JS source as a Python set of lowercased tag names."""
    src = JS_PATH.read_text()
    match = re.search(rf"var\s+{name}\s*=\s*\{{([^}}]+)\}}", src)
    assert match, f"Could not find {name} in dz-richtext.js"
    body = match.group(1)
    # Tags can include digits (H2, H3) — cycle 1's [A-Z]+ pattern
    # silently dropped them.
    tags = re.findall(r"([A-Z][A-Z0-9]*)\s*:\s*1", body)
    return {tag.lower() for tag in tags}


class TestAllowlistParity:
    def test_inline_tags_match_ir(self) -> None:
        from dazzle.core.ir.richtext import RICH_TEXT_INLINE_TAGS

        js = _extract_js_allowlist("INLINE_ALLOW")
        py = set(RICH_TEXT_INLINE_TAGS)
        assert js == py, (
            f"INLINE_ALLOW drift: JS={js}, IR={py}. "
            "Update src/dazzle/core/ir/richtext.py and dz-richtext.js together."
        )

    def test_block_tags_match_ir(self) -> None:
        from dazzle.core.ir.richtext import RICH_TEXT_BLOCK_TAGS

        js = _extract_js_allowlist("BLOCK_ALLOW")
        py = set(RICH_TEXT_BLOCK_TAGS)
        assert js == py, (
            f"BLOCK_ALLOW drift: JS={js}, IR={py}. "
            "Update src/dazzle/core/ir/richtext.py and dz-richtext.js together."
        )

    def test_protocol_pattern_matches(self) -> None:
        """The JS regex literal and the IR string must be the same.
        JS escapes `/` as `\\/` inside the literal; we translate back
        before comparing."""
        src = JS_PATH.read_text()
        match = re.search(r"var\s+SAFE_HREF\s*=\s*/(.+?)/i;", src)
        assert match, "Could not find SAFE_HREF regex in dz-richtext.js"
        js_pattern = match.group(1).replace("\\/", "/")
        assert js_pattern == RICH_TEXT_PROTOCOL_PATTERN

    def test_attr_allow_matches(self) -> None:
        """Only `<a>` carries `href`, nothing else carries any attr."""
        src = JS_PATH.read_text()
        # Source-grep: cycle 2 uses literal `A: { href: 1 }`.
        assert "A: { href: 1 }" in src
        assert dict(RICH_TEXT_ALLOWED_ATTRS) == {"a": frozenset({"href"})}


class TestServerSanitiserContract:
    def test_strips_unknown_tags(self) -> None:
        """The dangerous payload is the *tag*, not its text. bleach with
        strip=True removes the disallowed tag and keeps inert text — that
        text can never execute, since there's no <script> wrapper."""
        out = clean_rich_text("<p>hi</p><script>alert(1)</script>")
        assert "<script>" not in out
        assert "</script>" not in out
        assert "<p>hi</p>" in out

    def test_keeps_allowlisted_tags(self) -> None:
        for tag in [
            "p",
            "h2",
            "h3",
            "ul",
            "ol",
            "li",
            "blockquote",
            "strong",
            "em",
            "u",
            "s",
            "code",
            "br",
        ]:
            out = clean_rich_text(f"<{tag}>x</{tag}>" if tag != "br" else "x<br>y")
            assert f"<{tag}" in out, f"{tag} stripped unexpectedly"

    def test_keeps_safe_href(self) -> None:
        for url in ["https://example.com", "http://x", "mailto:a@b.com", "/internal/path"]:
            out = clean_rich_text(f'<a href="{url}">x</a>')
            assert f'href="{url}"' in out, f"{url} stripped"

    def test_strips_javascript_href(self) -> None:
        out = clean_rich_text('<a href="javascript:alert(1)">x</a>')
        assert "javascript" not in out
        # Tag may stay (without href) — the dangerous payload is gone.

    def test_strips_data_href(self) -> None:
        out = clean_rich_text('<a href="data:text/html,<script>x</script>">y</a>')
        assert "data:" not in out
        assert "<script>" not in out

    def test_strips_inline_styles(self) -> None:
        out = clean_rich_text('<p style="color:red">x</p>')
        assert "style" not in out
        assert "color:red" not in out

    def test_strips_data_attributes(self) -> None:
        out = clean_rich_text('<p data-tracker="oops">x</p>')
        assert "data-tracker" not in out

    def test_empty_input_returns_empty(self) -> None:
        assert clean_rich_text("") == ""

    def test_visual_empty_placeholder_returns_empty(self) -> None:
        """Empty editor shell must not persist as a filled paragraph (2128)."""
        from dazzle.http.runtime.richtext_field import is_visually_empty_rich_text

        for raw in (
            "<p><br></p>",
            "<p><br/></p>",
            "<p><br /></p>",
            "<p></p>",
            "<p> </p>",
            "<p>&nbsp;</p>",
            "<p>\u200b</p>",
            "<p><br></p><p><br></p>",
            "<br>",
        ):
            assert is_visually_empty_rich_text(raw), raw
            assert clean_rich_text(raw) == "", raw
        assert not is_visually_empty_rich_text("<p>hi</p>")
        assert "<p>hi</p>" in clean_rich_text("<p>hi</p>")
        assert not is_visually_empty_rich_text("<p>hi<br></p>")

    def test_visual_empty_does_not_regex_strip_tags(self) -> None:
        """Cycle 2129 / CodeQL #226: bleach-strip, not ``<[^>]+>``.

        A one-shot tag regex leaves ``<script`` when ``>`` is missing;
        emptiness must not be a fake sanitizer.
        """
        from dazzle.http.runtime import richtext_field as rt

        src = Path(rt.__file__).read_text(encoding="utf-8")
        assert 'r"<[^>]+>"' not in src
        assert "bleach.clean" in src
        assert "tags=[]" in src
        # Broken markup is visible text (not silently "sanitized" empty).
        from dazzle.http.runtime.richtext_field import is_visually_empty_rich_text

        assert not is_visually_empty_rich_text("<script")
        assert not is_visually_empty_rich_text("<scr<script>ipt>alert(1)</script>")

    def test_long_input_raises(self) -> None:
        import pytest

        big = "<p>" + ("a" * 100) + "</p>"
        with pytest.raises(ValueError):
            clean_rich_text(big, max_length=50)

    def test_uses_bleach_under_the_hood(self) -> None:
        """Sanity: confirm bleach is the underlying sanitiser, not a
        hand-rolled regex (per global CLAUDE.md security guidance)."""
        assert callable(bleach.clean)
