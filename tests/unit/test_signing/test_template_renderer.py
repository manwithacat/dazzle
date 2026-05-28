"""Unit tests for dazzle.signing.template_renderer (#1287)."""

from __future__ import annotations

from pathlib import Path

from dazzle.signing.template_renderer import (
    find_signing_template,
    render_signing_template_file,
)


class _Row:
    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class _Entity:
    name = "TestEntity"
    label = "Test Entity"


def test_substitutes_row_fields(tmp_path: Path) -> None:
    template = tmp_path / "t.html.j2"
    template.write_text("<p>Party: {{ row.party }}</p>")
    out = render_signing_template_file(template, row=_Row(party="ACME"), entity=_Entity())
    assert out == "<p>Party: ACME</p>"


def test_substitutes_entity_fields(tmp_path: Path) -> None:
    template = tmp_path / "t.html.j2"
    template.write_text("<h1>{{ entity.name }}</h1>")
    out = render_signing_template_file(template, row=_Row(), entity=_Entity())
    assert out == "<h1>TestEntity</h1>"


def test_escapes_user_content(tmp_path: Path) -> None:
    template = tmp_path / "t.html.j2"
    template.write_text("<p>{{ row.note }}</p>")
    out = render_signing_template_file(
        template,
        row=_Row(note="<script>alert('xss')</script>"),
        entity=_Entity(),
    )
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_unknown_placeholder_renders_empty(tmp_path: Path) -> None:
    template = tmp_path / "t.html.j2"
    template.write_text("<p>{{ row.missing }}</p>")
    out = render_signing_template_file(template, row=_Row(), entity=_Entity())
    assert out == "<p></p>"


def test_tolerates_extra_whitespace_in_braces(tmp_path: Path) -> None:
    template = tmp_path / "t.html.j2"
    template.write_text("<p>{{  row.party  }}</p>")
    out = render_signing_template_file(template, row=_Row(party="ACME"), entity=_Entity())
    assert out == "<p>ACME</p>"


def test_multiple_placeholders_in_one_template(tmp_path: Path) -> None:
    template = tmp_path / "t.html.j2"
    template.write_text("<p>{{ row.party }} signed on {{ row.date }}</p>")
    out = render_signing_template_file(
        template, row=_Row(party="Acme", date="2026-01-01"), entity=_Entity()
    )
    assert out == "<p>Acme signed on 2026-01-01</p>"


def test_find_signing_template_hit(tmp_path: Path) -> None:
    target = tmp_path / "templates" / "letters" / "TestDoc" / "default.html.j2"
    target.parent.mkdir(parents=True)
    target.write_text("hi")
    assert find_signing_template(tmp_path, "TestDoc") == target


def test_find_signing_template_miss(tmp_path: Path) -> None:
    assert find_signing_template(tmp_path, "Nothing") is None
