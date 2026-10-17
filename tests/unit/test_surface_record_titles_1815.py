"""Record-interpolating view titles, authored breadcrumbs, labelled quick_actions.

#1815 (AegisMark WP21): a view surface's ``title:`` interpolates the row
(``"{agreement_type|upper} — {school.name}"``) into the page heading, the
document ``<title>`` and the breadcrumb leaf; entity_card ``quick_actions``
take ``id "Label"`` and never print raw snake_case.
#1810 (AegisMark WP20): ``ux: breadcrumb: off`` suppresses the shell trail and
``ux: breadcrumb: "A" -> target > "{field}"`` replaces it.

All cases run the public path: DSL → AppSpec → validate / compile → render.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dazzle.core.errors import ParseError
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.core.validation.surface_titles import validate_surface_titles_and_breadcrumbs
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.http.runtime.workspace_card_fetchers import _build_entity_card_sections
from dazzle.page.converters.template_compiler import compile_appspec_to_templates
from dazzle.render.dispatch import dispatch_render_page
from dazzle.render.fragment.renderer import FragmentRenderer
from dazzle.render.text_template import record_page_chrome

_ENTITIES = """module t
app T "T"

entity School "School":
  id: uuid pk
  name: str(200) required

entity Agreement "Agreement":
  id: uuid pk
  agreement_type: enum[msa,dpa]=msa
  signed_on: date
  note: str(50)
  school: ref School required

surface agreement_list "Agreements":
  uses entity Agreement
  mode: list
  section main:
    field agreement_type "Type"

workspace hub "Hub":
  purpose: "Home"
  agreements:
    source: Agreement
    display: list
"""

_DETAIL = """
surface agreement_detail "Agreement":
  uses entity Agreement
  mode: view
{body}
  section main:
    field agreement_type "Type"
"""

_ROW: dict[str, Any] = {
    "id": "a1",
    "agreement_type": "msa",
    "signed_on": "2026-09-01",
    "note": None,
    "school": {"id": "s1", "name": "Oakwood <Academy>"},
}


def _appspec(tmp_path: Path, extra: str) -> Any:
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()
    (dsl_dir / "app.dsl").write_text(_ENTITIES + extra)
    return build_appspec(parse_modules([dsl_dir / "app.dsl"]), "t")


def _detail_appspec(tmp_path: Path, body: str) -> Any:
    return _appspec(tmp_path, _DETAIL.format(body=body))


def _surface(appspec: Any, name: str) -> Any:
    return next(s for s in appspec.surfaces if s.name == name)


def _detail_page(appspec: Any, row: dict[str, Any]) -> str:
    """Compile the detail surface, apply the record chrome, render the full page."""
    ctx = compile_appspec_to_templates(appspec, app_prefix="/app")["/app/agreement/{id}"]
    surface = _surface(appspec, "agreement_detail")
    heading, trail = record_page_chrome(surface.title_template, ctx.breadcrumb_trail, row)
    update: dict[str, Any] = {"current_route": "/app/agreement/a1"}
    if heading:
        update["page_title"] = heading
    if trail is not None:
        update["breadcrumb_trail"] = trail
    return dispatch_render_page(ctx.model_copy(update=update), "<p>body</p>")


# ───────────────────────── #1815.1 record titles ─────────────────────────


@pytest.mark.parametrize(
    ("title", "row", "expected"),
    [
        ('"{agreement_type|upper} — {school.name}"', _ROW, "MSA — Oakwood &lt;Academy&gt;"),
        ('"{school.name|lower} {signed_on|date}"', _ROW, "oakwood &lt;academy&gt; "),
        ('"{note}{school}"', _ROW, "Oakwood &lt;Academy&gt;"),
        ('"{{draft}} {agreement_type|title}"', _ROW, "{draft} Msa"),
    ],
    ids=["filter-and-fk-hop", "lower-and-date", "null-empty-and-fk-display", "literal-braces"],
)
def test_view_title_names_heading_document_title_and_breadcrumb_leaf(
    tmp_path: Path, title: str, row: dict[str, Any], expected: str
) -> None:
    appspec = _detail_appspec(tmp_path, f"  title: {title}")
    assert validate_surface_titles_and_breadcrumbs(appspec) == ([], [])
    html = _detail_page(appspec, row)
    assert f"<title>{expected}" in html
    assert f'<li aria-current="page">{expected}' in html
    heading, _ = record_page_chrome(_surface(appspec, "agreement_detail").title_template, None, row)
    surface_html = FragmentRenderer().render(
        FragmentSurfaceAdapter().build(
            _surface(appspec, "agreement_detail"), {"heading": heading, "fields": []}
        )
    )
    assert f">{expected}" in surface_html
    assert "<script" not in html + surface_html


def test_all_null_title_keeps_the_static_surface_title(tmp_path: Path) -> None:
    appspec = _detail_appspec(tmp_path, '  title: "{note}"')
    assert "<title>Agreement — T</title>" in _detail_page(appspec, _ROW)


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ('  title: "{nope}"', "E_TEMPLATE_UNKNOWN_FIELD"),
        ('  title: "{school.nope}"', "E_TEMPLATE_UNKNOWN_FIELD"),
        ('  title: "{note.name}"', "E_TEMPLATE_PATH_NOT_REF"),
        (
            '  ux:\n    breadcrumb: "Agreements" -> nowhere > "{school.name}"',
            "E_BREADCRUMB_DEAD_TARGET",
        ),
        ('  ux:\n    breadcrumb: "A" > "B" -> agreement_list', "E_BREADCRUMB_LEAF_LINK"),
        ('  ux:\n    breadcrumb: "A" -> agreement_detail > "B"', "E_BREADCRUMB_TARGET_NEEDS_ROW"),
    ],
)
def test_validate_rejects_unresolvable_titles_and_trails(
    tmp_path: Path, body: str, code: str
) -> None:
    errors, _ = validate_surface_titles_and_breadcrumbs(_detail_appspec(tmp_path, body))
    assert any(e.startswith(code) for e in errors), errors


@pytest.mark.parametrize(
    ("extra", "code"),
    [
        (
            '\nsurface agreement_new "New":\n  uses entity Agreement\n  mode: create\n'
            '  title: "{note}"\n  section main:\n    field note "Note"\n',
            "E_SURFACE_TITLE_MODE",
        ),
        (
            '\nsurface agreement_new "New":\n  uses entity Agreement\n  mode: create\n'
            '  section main:\n    field note "Note"\n  ux:\n    breadcrumb: "{note}"\n',
            "E_BREADCRUMB_PLACEHOLDER_MODE",
        ),
    ],
)
def test_validate_rejects_interpolation_off_view_surfaces(
    tmp_path: Path, extra: str, code: str
) -> None:
    errors, _ = validate_surface_titles_and_breadcrumbs(_appspec(tmp_path, extra))
    assert any(e.startswith(code) for e in errors), errors


@pytest.mark.parametrize(
    ("title", "code"),
    [
        ('"{agreement_type|shout}"', "E_TEMPLATE_UNKNOWN_FILTER"),
        ('"{a.b.c}"', "E_TEMPLATE_PATH_TOO_DEEP"),
        ('"{school.name"', "E_TEMPLATE_UNCLOSED"),
    ],
)
def test_malformed_title_template_is_a_parse_error(tmp_path: Path, title: str, code: str) -> None:
    with pytest.raises(ParseError, match=code):
        _detail_appspec(tmp_path, f"  title: {title}")


# ───────────────────────── #1810 breadcrumbs ─────────────────────────


def test_breadcrumb_off_suppresses_the_shell_trail(tmp_path: Path) -> None:
    html = _detail_page(_detail_appspec(tmp_path, "  ux:\n    breadcrumb: off"), _ROW)
    assert "dz-breadcrumb" not in html


def test_authored_breadcrumb_replaces_the_url_trail(tmp_path: Path) -> None:
    appspec = _detail_appspec(
        tmp_path,
        '  ux:\n    breadcrumb: "Home" -> hub > "Agreements" -> agreement_list > "{school.name}"',
    )
    assert validate_surface_titles_and_breadcrumbs(appspec) == ([], [])
    html = _detail_page(appspec, _ROW)
    assert '<a href="/app/workspaces/hub"' in html
    assert '<a href="/app/agreement"' in html
    assert '<li aria-current="page">Oakwood &lt;Academy&gt;</li>' in html
    assert ">App<" not in html


def test_static_breadcrumb_on_a_list_surface(tmp_path: Path) -> None:
    appspec = _appspec(
        tmp_path,
        '\nsurface school_list "Schools":\n  uses entity School\n  mode: list\n'
        '  section main:\n    field name "Name"\n  ux:\n    breadcrumb: "Hub" -> hub > "Schools"\n',
    )
    ctx = compile_appspec_to_templates(appspec, app_prefix="/app")["/app/school"]
    html = dispatch_render_page(ctx.model_copy(update={"current_route": "/app/school"}), "")
    assert '<a href="/app/workspaces/hub"' in html
    assert '<li aria-current="page">Schools</li>' in html


# ───────────────────────── #1815.2 labelled quick_actions ─────────────────────────


def test_quick_actions_take_authored_labels_surface_titles_or_humanised_ids(
    tmp_path: Path,
) -> None:
    appspec = _appspec(
        tmp_path,
        """
workspace card "Card":
  purpose: "One school"
  school_360:
    source: School
    display: entity_card
    entity_card_config:
      sections:
        - name: actions
          mode: quick_actions
          actions: [agreement_list, log_behaviour, send_reply "Reply to parent"]
""",
    )
    ws = next(w for w in appspec.workspaces if w.name == "card")
    config = ws.regions[0].entity_card_config
    body = _build_entity_card_sections(
        items=[{"id": "s1"}],
        config=config,
        action_titles={s.name: s.title for s in appspec.surfaces if s.title},
    )[0]["body"]
    assert ">Agreements</button>" in body
    assert ">Log behaviour</button>" in body
    assert 'data-dz-action="send_reply">Reply to parent</button>' in body
