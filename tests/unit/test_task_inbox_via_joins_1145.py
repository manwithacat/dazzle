"""#1145 part 2: `via:` cross-entity alias map for task_inbox
`as_task:` templates.

Pre-fix `{{ student.forename }}` couldn't reach across FK joins —
the template grammar resolved paths against the source row only,
and a `BehaviourIncident` row has no `student.forename` path. Every
"behaviour follow-up" surface fell back to a route override.

After #1145 part 2, the `as_task.via:` block names aliases that map
to dotted paths on the row; the runtime injects the resolved value
under the alias before interpolation. No extra DB queries — relies
on rows arriving with FK-hydrated sub-dicts.
"""

from __future__ import annotations

from dazzle.core.ir.workspaces import TaskSourceTemplate
from dazzle.http.runtime.workspace_card_data import _items_from_template


def test_via_alias_resolves_to_fk_hydrated_subdict() -> None:
    """The canonical case: row has `student` as an FK-hydrated dict;
    alias maps to that key and `{{ student.forename }}` resolves."""
    template = TaskSourceTemplate(
        icon="behaviour",
        title="Follow up with {{ student.forename }}",
        meta="{{ incident_type }}",
        via_joins={"student": "behaviour_student.student_profile"},
    )
    items = [
        {
            "id": "i1",
            "incident_type": "uniform",
            "behaviour_student": {"student_profile": {"forename": "Alice", "surname": "Smith"}},
        }
    ]
    out = _items_from_template(items, template, prefix="src0-")
    assert out[0]["title"] == "Follow up with Alice"
    assert out[0]["meta"] == "uniform"


def test_via_alias_with_scalar_target() -> None:
    """The dotted path can resolve to a scalar — the alias becomes
    that scalar, usable bare in templates."""
    template = TaskSourceTemplate(
        icon="x",
        title="Reply to {{ recipient_email }}",
        via_joins={"recipient_email": "contact.email"},
    )
    items = [
        {
            "id": "i1",
            "contact": {"email": "alice@example.com", "name": "Alice"},
        }
    ]
    out = _items_from_template(items, template, prefix="")
    assert out[0]["title"] == "Reply to alice@example.com"


def test_via_alias_missing_path_renders_empty() -> None:
    """Unresolved FK path → alias resolves to None → template
    renders empty for that placeholder. Graceful degradation, matches
    the `{{ field }}` fallback contract."""
    template = TaskSourceTemplate(
        icon="x",
        title="Follow up with {{ student.forename }}",
        via_joins={"student": "behaviour_student.student_profile"},
    )
    items = [{"id": "i1"}]  # no FK dict at all
    out = _items_from_template(items, template, prefix="")
    assert out[0]["title"] == "Follow up with "


def test_via_does_not_mutate_input_row() -> None:
    """The runtime injects into a shallow copy of the row, not the
    input. Verified by the absence of the alias key on the original
    item afterwards — important when the same row is consumed by
    multiple sources (one per source's via_joins)."""
    template = TaskSourceTemplate(
        icon="x",
        title="{{ student.forename }}",
        via_joins={"student": "student_profile"},
    )
    item = {
        "id": "i1",
        "student_profile": {"forename": "Alice"},
    }
    _items_from_template([item], template, prefix="")
    assert "student" not in item


def test_no_via_joins_unchanged() -> None:
    """Regression guard: templates without `via:` declared behave
    exactly as before — the row passes through to interpolation
    untouched (no copy, no alias injection)."""
    template = TaskSourceTemplate(icon="x", title="Hello {{ name }}")
    items = [{"id": "i1", "name": "World"}]
    out = _items_from_template(items, template, prefix="")
    assert out[0]["title"] == "Hello World"
    assert out[0]["item_id"] == "i1"


def test_multiple_via_aliases() -> None:
    """Multiple aliases in one template — each resolves
    independently via its declared path."""
    template = TaskSourceTemplate(
        icon="x",
        title="{{ pupil.forename }} ({{ year.label }})",
        via_joins={"pupil": "student_profile", "year": "year_group"},
    )
    items = [
        {
            "id": "i1",
            "student_profile": {"forename": "Bob"},
            "year_group": {"label": "Year 9"},
        }
    ]
    out = _items_from_template(items, template, prefix="")
    assert out[0]["title"] == "Bob (Year 9)"
