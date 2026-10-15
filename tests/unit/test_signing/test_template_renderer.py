"""File-based signing templates: lookup and rendering (#1287)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.signing.template_renderer import find_signing_template, render_signing_template_file

_ENTITY = SimpleNamespace(name="TestEntity", label="Test Entity")


@pytest.mark.parametrize(
    ("template", "row", "expected"),
    [
        pytest.param(
            "<p>Party: {{ row.party }}</p>", {"party": "ACME"}, "<p>Party: ACME</p>", id="row-field"
        ),
        pytest.param("<h1>{{ entity.name }}</h1>", {}, "<h1>TestEntity</h1>", id="entity-field"),
        pytest.param(
            "<p>{{ row.missing }}</p>", {}, "<p></p>", id="unknown-placeholder-renders-empty"
        ),
        pytest.param(
            "<p>{{  row.party  }}</p>", {"party": "ACME"}, "<p>ACME</p>", id="extra-whitespace"
        ),
        pytest.param(
            "<p>{{ row.party }} signed on {{ row.date }}</p>",
            {"party": "Acme", "date": "2026-01-01"},
            "<p>Acme signed on 2026-01-01</p>",
            id="several-placeholders",
        ),
        pytest.param(
            "<p>{{ row.note }}</p>",
            {"note": "<script>alert('xss')</script>"},
            "<p>&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;</p>",
            id="user-content-is-html-escaped",
        ),
    ],
)
def test_render(template: str, row: dict[str, str], expected: str, tmp_path: Path) -> None:
    path = tmp_path / "t.html.j2"
    path.write_text(template)
    assert (
        render_signing_template_file(path, row=SimpleNamespace(**row), entity=_ENTITY) == expected
    )


@pytest.mark.parametrize(("entity", "found"), [("TestDoc", True), ("Nothing", False)])
def test_find_signing_template(entity: str, found: bool, tmp_path: Path) -> None:
    target = tmp_path / "templates" / "letters" / "TestDoc" / "default.html.j2"
    target.parent.mkdir(parents=True)
    target.write_text("hi")
    assert find_signing_template(tmp_path, entity) == (target if found else None)
