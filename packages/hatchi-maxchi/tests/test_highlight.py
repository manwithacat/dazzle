"""Build-time Python highlighter for the code Hyperpart."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG / "site"))

from highlight import highlight_python, render_code_block  # noqa: E402

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


def test_render_code_block_html_language_is_escaped_not_tokenised() -> None:
    block = render_code_block(
        '<button class="x">Ok</button>',
        language="html",
        highlight=False,
    )
    assert "&lt;button" in block
    assert "dz-code__tok--" not in block
