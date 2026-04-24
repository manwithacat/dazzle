"""Drift test for the dz/v1 analytics event vocabulary (v0.61.0 Phase 4).

Pins the exact set of events, parameters, and schema shape so any change
is intentional + CHANGELOG-worthy. Breaking the vocabulary without a
version bump is how analytics integrations silently rot; this test
prevents that by failing loudly.

If this test fails because you intentionally evolved the vocabulary:

1. Confirm the change is *additive* (new event / new optional param).
   Additions stay in dz/v1.
2. Update this test's EXPECTED_* constants.
3. Add a CHANGELOG entry under the relevant release.

If the change is *breaking* (rename, remove, or tighten semantics),
the correct response is to introduce dz/v2 alongside dz/v1 — not to
edit this test silently.
"""

from __future__ import annotations

from dazzle.compliance.analytics import (
    COMMON_PARAMS,
    EVENT_SCHEMAS,
    VOCABULARY_ID,
    VOCABULARY_VERSION,
    EventParam,
    EventSchema,
    get_event_schema,
    list_event_names,
)

# Every event declared in the vocabulary as of v0.61.0 Phase 4.
EXPECTED_EVENT_NAMES: set[str] = {
    "dz_page_view",
    "dz_action",
    "dz_transition",
    "dz_form_submit",
    "dz_search",
    "dz_api_error",
}

# Every (event_name, param_name) tuple — declares the required + optional
# parameters per event. Adding a row is an additive change; removing one
# or renaming is a breaking change requiring a new vocabulary version.
EXPECTED_EVENT_PARAMS: set[tuple[str, str]] = {
    # dz_page_view
    ("dz_page_view", "workspace"),
    ("dz_page_view", "surface"),
    ("dz_page_view", "persona_class"),
    ("dz_page_view", "url"),
    ("dz_page_view", "referrer"),
    # dz_action
    ("dz_action", "action_name"),
    ("dz_action", "entity"),
    ("dz_action", "surface"),
    ("dz_action", "entity_id"),
    # dz_transition
    ("dz_transition", "entity"),
    ("dz_transition", "from_state"),
    ("dz_transition", "to_state"),
    ("dz_transition", "trigger"),
    # dz_form_submit
    ("dz_form_submit", "form_name"),
    ("dz_form_submit", "entity"),
    ("dz_form_submit", "surface"),
    ("dz_form_submit", "validation_errors_count"),
    # dz_search
    ("dz_search", "surface"),
    ("dz_search", "entity"),
    ("dz_search", "result_count"),
    ("dz_search", "query"),
    # dz_api_error
    ("dz_api_error", "status_code"),
    ("dz_api_error", "surface"),
    ("dz_api_error", "error_code"),
}

# Required params per event. The drift test asserts both the set AND
# required-ness. Flipping optional → required on existing params is
# breaking even without a rename.
EXPECTED_REQUIRED_PARAMS: set[tuple[str, str]] = {
    ("dz_page_view", "workspace"),
    ("dz_page_view", "surface"),
    ("dz_action", "action_name"),
    ("dz_action", "entity"),
    ("dz_action", "surface"),
    ("dz_transition", "entity"),
    ("dz_transition", "from_state"),
    ("dz_transition", "to_state"),
    ("dz_transition", "trigger"),
    ("dz_form_submit", "form_name"),
    ("dz_form_submit", "entity"),
    ("dz_form_submit", "surface"),
    ("dz_search", "surface"),
    ("dz_search", "entity"),
    ("dz_search", "result_count"),
    ("dz_api_error", "status_code"),
    ("dz_api_error", "surface"),
}


class TestVocabularyVersion:
    def test_version_constants(self) -> None:
        assert VOCABULARY_VERSION == "1"
        assert VOCABULARY_ID == "dz/v1"


class TestEventSet:
    def test_event_names_are_frozen(self) -> None:
        actual = set(list_event_names())
        assert actual == EXPECTED_EVENT_NAMES, (
            "Event vocabulary changed. Review the drift: "
            f"added={actual - EXPECTED_EVENT_NAMES}, "
            f"removed={EXPECTED_EVENT_NAMES - actual}."
        )

    def test_all_event_names_dz_prefixed(self) -> None:
        for name in list_event_names():
            assert name.startswith("dz_"), (
                f"Event name {name!r} must use dz_ prefix to avoid clashes with "
                "other tag-manager vocabularies."
            )

    def test_schemas_are_tuple_not_list(self) -> None:
        """Protect against accidental mutation."""
        assert isinstance(EVENT_SCHEMAS, tuple)

    def test_every_schema_is_frozen_dataclass(self) -> None:
        import dataclasses

        import pytest

        schema = EVENT_SCHEMAS[0]
        with pytest.raises(dataclasses.FrozenInstanceError):
            schema.name = "evil"  # type: ignore[misc]


class TestEventParams:
    def test_param_set_is_frozen(self) -> None:
        actual: set[tuple[str, str]] = set()
        for schema in EVENT_SCHEMAS:
            for p in schema.core_params:
                actual.add((schema.name, p.name))
            for p in schema.optional_params:
                actual.add((schema.name, p.name))
        assert actual == EXPECTED_EVENT_PARAMS, (
            f"Parameter set drifted. added={actual - EXPECTED_EVENT_PARAMS}, "
            f"removed={EXPECTED_EVENT_PARAMS - actual}."
        )

    def test_required_param_set_is_frozen(self) -> None:
        actual: set[tuple[str, str]] = set()
        for schema in EVENT_SCHEMAS:
            for p in schema.core_params:
                if p.required:
                    actual.add((schema.name, p.name))
            for p in schema.optional_params:
                if p.required:
                    actual.add((schema.name, p.name))
        assert actual == EXPECTED_REQUIRED_PARAMS, (
            f"Required-param set drifted. "
            f"added={actual - EXPECTED_REQUIRED_PARAMS}, "
            f"removed={EXPECTED_REQUIRED_PARAMS - actual}."
        )

    def test_param_names_are_snake_case(self) -> None:
        import re

        pattern = re.compile(r"^[a-z][a-z0-9_]*$")
        for schema in EVENT_SCHEMAS:
            for p in [*schema.core_params, *schema.optional_params]:
                assert pattern.match(p.name), f"{schema.name}.{p.name} must be snake_case."

    def test_value_types_are_primitive(self) -> None:
        primitives = {"str", "int", "float", "bool"}
        for schema in EVENT_SCHEMAS:
            for p in [*schema.core_params, *schema.optional_params]:
                assert p.value_type in primitives, (
                    f"{schema.name}.{p.name} value_type {p.value_type!r} must be "
                    f"one of {primitives} — events carry primitives only."
                )

    def test_string_params_have_max_length(self) -> None:
        for schema in EVENT_SCHEMAS:
            for p in [*schema.core_params, *schema.optional_params]:
                if p.value_type == "str":
                    assert p.max_length > 0, (
                        f"{schema.name}.{p.name} is a string param — must declare "
                        "a positive max_length for clamping."
                    )
                    assert p.max_length <= 255, (
                        f"{schema.name}.{p.name} max_length {p.max_length} is "
                        "unusually large. Analytics dashboards don't need it."
                    )

    def test_pii_params_default_off(self) -> None:
        """No Phase 4 param may default to allow_pii=True."""
        for schema in EVENT_SCHEMAS:
            for p in [*schema.core_params, *schema.optional_params]:
                assert p.allow_pii is False, (
                    f"{schema.name}.{p.name} allow_pii is True but no PII "
                    "parameters ship in the v1 default vocabulary. "
                    "Review the design spec before changing this."
                )


class TestCommonParams:
    def test_schema_version_present_and_required(self) -> None:
        by_name = {p.name: p for p in COMMON_PARAMS}
        assert "dz_schema_version" in by_name
        assert by_name["dz_schema_version"].required is True

    def test_tenant_present(self) -> None:
        by_name = {p.name: p for p in COMMON_PARAMS}
        assert "dz_tenant" in by_name


class TestLookup:
    def test_get_known_event_returns_schema(self) -> None:
        s = get_event_schema("dz_page_view")
        assert isinstance(s, EventSchema)
        assert s.name == "dz_page_view"

    def test_get_unknown_returns_none(self) -> None:
        assert get_event_schema("no_such_event") is None


class TestEventParamMetadata:
    def test_every_event_has_fires_on_description(self) -> None:
        for schema in EVENT_SCHEMAS:
            assert schema.fires_on.strip(), (
                f"{schema.name} missing fires_on — docs-for-future-you requirement."
            )

    def test_every_event_has_description(self) -> None:
        for schema in EVENT_SCHEMAS:
            assert schema.description.strip(), f"{schema.name} missing description."

    def test_every_param_has_description(self) -> None:
        for schema in EVENT_SCHEMAS:
            for p in [*schema.core_params, *schema.optional_params]:
                assert p.description.strip(), f"{schema.name}.{p.name} missing description."


class TestParamObject:
    def test_event_param_is_frozen(self) -> None:
        import dataclasses

        import pytest

        p = EventParam(name="x", value_type="str", description="test")
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.name = "y"  # type: ignore[misc]
