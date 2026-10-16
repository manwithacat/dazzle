"""No Alpine.js attributes in emitted markup (AGENTS.md "UI Invariants").

Alpine was deprecated 2026-07-06 and its vendored runtime removed; client
behaviour is HM delegated controllers + ``dz-utils.js``. An ``x-*`` or ``@event``
attribute that reaches the DOM is inert at best. Nothing gated it after the
flense retired the per-feature Alpine tests, so this is the one gate: every
non-minified source that can emit markup (Python renderers' string literals,
JS, HTML, CSS) under the page, render and HaTchi-MaXchi trees is free of Alpine
attribute syntax outside comments and docstrings.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
ROOTS = (
    REPO / "src" / "dazzle" / "page",
    REPO / "src" / "dazzle" / "render",
    REPO / "packages" / "hatchi-maxchi" / "components",
    REPO / "packages" / "hatchi-maxchi" / "controllers",
    REPO / "packages" / "hatchi-maxchi" / "site",
)
SUFFIXES = {".py", ".js", ".html", ".css"}
SKIP_PARTS = {"dist", "node_modules", "__pycache__", "vendor"}

ALPINE_ATTR = re.compile(
    r"(?<![\w.-])(?:x-(?:data|init|show|bind|on|text|html|model|modelable|for|transition|"
    r"effect|ignore|ref|cloak|teleport|if|id)(?:[:.][\w.-]+)?|@(?:click|submit|input|change|"
    r"keydown|keyup|focus|blur)(?:\.[\w.-]+)?)\s*="
)
_BLOCK_COMMENTS = re.compile(r"/\*.*?\*/|<!--.*?-->|\{#.*?#\}", re.S)
_LINE_COMMENT = re.compile(r"^\s*//.*$", re.M)


def _python_literals(source: str) -> str:
    """Every string literal that is not a docstring, joined with newlines."""
    tree = ast.parse(source)
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))
    return "\n".join(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    )


def _markup_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        return _python_literals(text)
    text = _BLOCK_COMMENTS.sub("", text)
    if path.suffix == ".js":
        text = _LINE_COMMENT.sub("", text)
    return text


def _sources() -> list[Path]:
    out: list[Path] = []
    for root in ROOTS:
        for p in root.rglob("*"):
            if (
                p.is_file()
                and p.suffix in SUFFIXES
                and ".min." not in p.name
                and not SKIP_PARTS.intersection(p.relative_to(root).parts)
            ):
                out.append(p)
    return out


def test_no_alpine_attributes_in_emitted_markup() -> None:
    offenders: list[str] = []
    for path in _sources():
        for match in ALPINE_ATTR.finditer(_markup_text(path)):
            offenders.append(f"{path.relative_to(REPO)}: {match.group(0).strip()}")
    assert not offenders, (
        "Alpine attribute syntax in emitted markup (AGENTS.md: never author x-* / @event; "
        "use HM delegated controllers + data-* state):\n  " + "\n  ".join(sorted(offenders))
    )
