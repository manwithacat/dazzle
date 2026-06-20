"""#1426: the `/app` path SSOT helper. Pins the formula every route + link derives
from, so registration and link generation can't drift on the path rule."""

from dazzle.page.app_paths import (
    create_path,
    detail_path,
    edit_path,
    entity_slug,
    list_path,
)


def test_entity_slug_lowercases_and_dashes_underscores():
    assert entity_slug("Task") == "task"
    assert entity_slug("AssessmentEvent") == "assessmentevent"
    assert entity_slug("invoice_line") == "invoice-line"


def test_path_builders_with_template_id():
    assert list_path("/app", "task") == "/app/task"
    assert create_path("/app", "task") == "/app/task/create"
    assert detail_path("/app", "task") == "/app/task/{id}"
    assert edit_path("/app", "task") == "/app/task/{id}/edit"


def test_detail_and_edit_with_concrete_id():
    assert detail_path("/app", "invoice-line", "abc-123") == "/app/invoice-line/abc-123"
    assert edit_path("/app", "invoice-line", "abc-123") == "/app/invoice-line/abc-123/edit"


def test_empty_prefix_is_supported():
    # Some callers build routes with no prefix (registration paths are prefix-stripped).
    assert list_path("", "task") == "/task"
    assert detail_path("", "task") == "/task/{id}"


def test_registration_template_round_trips_to_a_link():
    # The same function yields the registration template and a concrete link.
    slug = entity_slug("AssessmentEvent")
    assert detail_path("/app", slug) == "/app/assessmentevent/{id}"
    assert detail_path("/app", slug, "e-9") == "/app/assessmentevent/e-9"
