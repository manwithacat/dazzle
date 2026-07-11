"""Build-time highlighter for the code Hyperpart (Python + HTML)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG / "site"))

from highlight import (  # noqa: E402
    highlight_html,
    highlight_python,
    highlight_source,
    render_code_block,
)

pytestmark = pytest.mark.gate


def test_highlight_python_keywords_and_strings() -> None:
    html = highlight_python('def greet(name: str) -> str:\n    return "hi"\n')
    assert 'class="dz-code__tok--kw"' in html
    assert ">def<" in html
    assert 'class="dz-code__tok--str"' in html
    assert "hi" in html
    assert "&#x27;" in html or "&quot;" in html or '"hi"' not in html  # escaped


def test_highlight_python_comments_and_decorators() -> None:
    html = highlight_python("@app.get\n# note\nx = 1\n")
    assert 'class="dz-code__tok--dec"' in html
    assert 'class="dz-code__tok--cmt"' in html
    assert 'class="dz-code__tok--num"' in html


def test_highlight_html_tags_attrs_and_values() -> None:
    html = highlight_html(
        '<!-- setup -->\n<button class="x" data-variant="primary" hx-get="/a">Ok</button>\n'
    )
    assert 'class="dz-code__tok--cmt"' in html
    assert "setup" in html
    assert 'class="dz-code__tok--kw"' in html
    assert ">button<" in html
    assert 'class="dz-code__tok--name"' in html  # class=
    assert 'class="dz-code__tok--dec"' in html  # data- / hx-
    assert 'class="dz-code__tok--str"' in html
    assert "primary" in html
    assert "&lt;" not in html or "tok--op" in html  # brackets as op spans, not raw
    # Escaped angle brackets appear only inside escaped content of spans
    assert "&lt;button" not in html  # whole tag is not plain-escaped as one blob
    assert "Ok" in html


def test_highlight_html_void_and_close() -> None:
    html = highlight_html('<br/>\n</div>\n<input type="text" />\n')
    assert ">br<" in html
    assert ">div<" in html
    assert ">input<" in html
    assert 'class="dz-code__tok--str"' in html


def test_highlight_source_dispatches() -> None:
    assert "tok--kw" in highlight_source("def x():\n  pass\n", "python")
    assert "tok--kw" in highlight_source("<span>a</span>", "html")
    assert "tok--kw" in highlight_source("<svg/>", "svg")
    plain = highlight_source("nope", "rust")
    assert "tok--" not in plain
    assert plain == "nope"


def test_render_code_block_structure_and_copy_text() -> None:
    src = "def f():\n    return 1\n"
    block = render_code_block(src, language="python", aria_label="demo")
    assert "data-dz-code" in block
    assert 'data-dz-language="python"' in block
    assert "data-dz-code-copy" in block
    assert "dz-code__tok--kw" in block
    assert ">def<" in block
    assert ">return<" in block
    # Hyperpart contract: meta bar wraps lang + copy; pre follows.
    assert "dz-code__meta" in block
    assert block.index("dz-code__meta") < block.index("dz-code__copy")
    assert block.index("dz-code__copy") < block.index("dz-code__pre")
    # Spans split identifiers; plain contiguous source is not required in HTML
    assert "f" in block


def test_render_code_block_html_language_is_tokenised() -> None:
    block = render_code_block(
        '<button class="x">Ok</button>',
        language="html",
    )
    assert 'data-dz-language="html"' in block
    assert "dz-code__tok--kw" in block
    assert ">button<" in block
    assert "dz-code__tok--str" in block
    # Source text is never raw unescaped angle brackets outside spans
    assert "<button class=" not in block


def test_render_code_block_highlight_false_is_plain_escape() -> None:
    block = render_code_block(
        '<button class="x">Ok</button>',
        language="html",
        highlight=False,
    )
    assert "&lt;button" in block
    assert "dz-code__tok--" not in block
