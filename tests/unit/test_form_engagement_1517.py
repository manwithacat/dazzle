"""#1517 1a — usage-driven form-field inference (ADR-0050 Phase 5b).

The field-engagement signal (dz-usage.js first-focus beacons, aggregated per
entity) annotates form field dicts before primitive dispatch: the hottest
plain field gains ``autofocus``; a heavily-engaged long select upgrades to
the searchable ``combobox`` widget. Cold-start byte parity below the floor.
"""

import pytest

from dazzle.page.runtime.form_engagement_resolver import annotate_form_fields_by_usage
from dazzle.render.fragment.form_field import field_dict_to_primitive
from dazzle.render.fragment.primitives.forms import Combobox, Field, WidgetCombobox

pytestmark = pytest.mark.unit


def _fields():
    return [
        {"name": "title", "kind": "text", "label": "Title"},
        {"name": "notes", "kind": "textarea", "label": "Notes"},
        {
            "name": "category",
            "kind": "select",
            "label": "Category",
            "options": [(f"c{i}", f"C{i}") for i in range(10)],
        },
        {"name": "owner", "kind": "select", "label": "Owner", "ref_api": "/api/users"},
        {"name": "logo", "kind": "file", "label": "Logo"},
    ]


# ── cold-start parity ──────────────────────────────────────────────────────


def test_below_floor_is_untouched() -> None:
    fields = _fields()
    import copy

    before = copy.deepcopy(fields)
    annotate_form_fields_by_usage(fields, {"title": 3, "notes": 2})  # total 5 < 10
    assert fields == before


def test_no_usage_is_untouched() -> None:
    fields = _fields()
    import copy

    before = copy.deepcopy(fields)
    annotate_form_fields_by_usage(fields, {})
    assert fields == before


# ── autofocus ──────────────────────────────────────────────────────────────


def test_hottest_plain_field_gains_autofocus() -> None:
    fields = _fields()
    annotate_form_fields_by_usage(fields, {"notes": 30, "title": 10})
    assert fields[1].get("autofocus") is True
    assert "autofocus" not in fields[0]


def test_rich_fields_never_take_autofocus() -> None:
    # The ref-picker select and the file field are the hottest — both are
    # excluded, so the next-hottest plain field wins.
    fields = _fields()
    annotate_form_fields_by_usage(fields, {"owner": 50, "logo": 40, "title": 12})
    assert "autofocus" not in fields[3]
    assert "autofocus" not in fields[4]
    assert fields[0].get("autofocus") is True


def test_author_declared_widget_excluded_from_autofocus() -> None:
    fields = [
        {"name": "body", "kind": "textarea", "label": "Body", "widget": "rich_text"},
        {"name": "title", "kind": "text", "label": "Title"},
    ]
    annotate_form_fields_by_usage(fields, {"body": 40, "title": 11})
    assert "autofocus" not in fields[0]
    assert fields[1].get("autofocus") is True


def test_upgraded_select_does_not_take_autofocus() -> None:
    # The hottest field is a long select that the SAME pass upgrades to a
    # combobox — the upgrade must run first, so autofocus lands elsewhere.
    fields = _fields()
    annotate_form_fields_by_usage(fields, {"category": 50, "title": 12})
    assert fields[2].get("widget") == "combobox"
    assert "autofocus" not in fields[2]
    assert fields[0].get("autofocus") is True


# ── combobox upgrade ───────────────────────────────────────────────────────


def test_heavily_used_long_select_upgrades() -> None:
    fields = _fields()
    annotate_form_fields_by_usage(fields, {"category": 15})
    assert fields[2].get("widget") == "combobox"


def test_short_select_never_upgrades() -> None:
    fields = [
        {
            "name": "status",
            "kind": "select",
            "label": "Status",
            "options": [("a", "A"), ("b", "B")],
        },
    ]
    annotate_form_fields_by_usage(fields, {"status": 50})
    assert "widget" not in fields[0]


def test_cool_select_never_upgrades() -> None:
    fields = _fields()
    # Surface is above the total floor but the select itself is barely used.
    annotate_form_fields_by_usage(fields, {"title": 20, "category": 3})
    assert "widget" not in fields[2]


def test_author_widget_is_authoritative() -> None:
    fields = [
        {
            "name": "category",
            "kind": "select",
            "label": "Category",
            "widget": "tags",
            "options": [(f"c{i}", f"C{i}") for i in range(10)],
        },
    ]
    annotate_form_fields_by_usage(fields, {"category": 50})
    assert fields[0]["widget"] == "tags"


def test_ref_select_never_upgrades() -> None:
    fields = _fields()
    annotate_form_fields_by_usage(fields, {"owner": 50})
    assert "widget" not in fields[3]


# ── sections alias the flat entries ────────────────────────────────────────


def test_section_dicts_see_annotations() -> None:
    fields = _fields()
    sections = [{"name": "main", "fields": [fields[0], fields[1]]}]
    annotate_form_fields_by_usage(fields, {"notes": 30})
    assert sections[0]["fields"][1].get("autofocus") is True


# ── dispatch + emission carry the annotation ───────────────────────────────


def test_dispatch_threads_autofocus_to_field() -> None:
    prim = field_dict_to_primitive(
        {"name": "title", "kind": "text", "label": "Title", "autofocus": True}
    )
    assert isinstance(prim, Field) and prim.autofocus is True


def test_dispatch_threads_autofocus_to_combobox() -> None:
    prim = field_dict_to_primitive(
        {
            "name": "status",
            "kind": "select",
            "label": "Status",
            "options": [("a", "A")],
            "autofocus": True,
        }
    )
    assert isinstance(prim, Combobox) and prim.autofocus is True


def test_upgraded_dict_dispatches_to_widget_combobox() -> None:
    d = {
        "name": "category",
        "kind": "select",
        "label": "Category",
        "options": [(f"c{i}", f"C{i}") for i in range(10)],
    }
    annotate_form_fields_by_usage([d], {"category": 15})
    prim = field_dict_to_primitive(d)
    assert isinstance(prim, WidgetCombobox)


def test_upgrade_preserves_edit_value_and_required() -> None:
    """The usage upgrade must not lose the EDIT form's current selection or
    its required validation — a refactor dropping initial_value/required in
    the widget=combobox dispatch branch would silently clear the selection
    on every usage-upgraded select (review finding, v0.92.85)."""
    d = {
        "name": "category",
        "kind": "select",
        "label": "Category",
        "value": "c5",
        "required": True,
        "options": [(f"c{i}", f"C{i}") for i in range(10)],
    }
    annotate_form_fields_by_usage([d], {"category": 15})
    prim = field_dict_to_primitive(d)
    assert isinstance(prim, WidgetCombobox)
    assert prim.initial_value == "c5"
    assert prim.required is True


def test_emitted_html_carries_autofocus() -> None:
    from dazzle.render.fragment import FragmentRenderer

    r = FragmentRenderer()
    focused = r.render(Field(name="title", label="Title", autofocus=True))
    plain = r.render(Field(name="title", label="Title"))
    assert "autofocus" in focused
    assert "autofocus" not in plain


def test_emitted_select_carries_autofocus() -> None:
    from dazzle.render.fragment import FragmentRenderer

    html = FragmentRenderer().render(
        Combobox(name="status", label="Status", options=(("a", "A"),), autofocus=True)
    )
    assert "autofocus" in html
