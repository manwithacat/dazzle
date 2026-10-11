"""Profile-card empty must not dump generic 'No profile data' (oral #227)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.render.breadcrumbs import (
    clerk_empty_profile_title,
    entity_path_labels_from_spec,
)
from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.region._builders_cards import _BuildersCardsMixin

HR = Path("examples/hr_records")


class _A(_BuildersCardsMixin):
    pass


def _region(**overrides: object) -> object:
    base: dict[str, object] = {
        "name": "system_identity",
        "title": "System identity",
        "empty_message": None,
        "source": "System",
    }
    base.update(overrides)
    return type("R", (), base)()


def _render_profile(region: object, ctx: dict[str, object] | None = None) -> str:
    payload: dict[str, object] = {"profile_card_data": {}}
    payload.update(ctx or {})
    return FragmentRenderer().render(_A()._build_profile_card(region, payload))


def test_clerk_empty_profile_title_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_empty_profile_title(junk) == "No profile data"


def test_hr_person_profile_is_person() -> None:
    spec = load_project(HR)
    person = next(e for e in spec.domain.entities if e.name == "Person")
    assert person.title == "Person"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_empty_profile_title("Person", labels) == "No person profile"


def test_profile_empty_is_system_not_no_profile_data() -> None:
    html = _render_profile(_region())
    assert "dz-empty-state__title" in html
    assert "No system profile" in html
    assert "No profile data" not in html
    assert "No systemss" not in html


def test_profile_empty_ctx_source_entity_still_splits() -> None:
    html = _render_profile(_region(source=""), {"source_entity": "System"})
    assert "No system profile" in html
    assert "No profile data" not in html


def test_profile_empty_missing_entity_stays_no_profile_data() -> None:
    html = _render_profile(_region(source=""))
    assert "No profile data" in html
    assert "No systems" not in html


def test_profile_empty_leftover_invents_no_collection() -> None:
    html = _render_profile(_region(source="zzz"))
    assert "No profile data" in html
    assert "No zzz" not in html


def test_profile_empty_card_title_item_fallback_does_not_invent() -> None:
    html = _render_profile(_region(source="System"), {"entity_name": "Item"})
    assert "No system profile" in html
    assert "No profile data" not in html


def test_profile_authored_empty_still_wins() -> None:
    html = _render_profile(_region(empty_message="No system on this desk"))
    assert "No system on this desk" in html
    assert "No profile data" not in html
    assert "No system profile" not in html


def test_profile_populated_still_renders_identity() -> None:
    html = _render_profile(
        _region(),
        {"profile_card_data": {"primary": "api-gateway", "initials": "AG"}},
    )
    assert "api-gateway" in html
    assert "No profile data" not in html
    assert "No system profile" not in html
