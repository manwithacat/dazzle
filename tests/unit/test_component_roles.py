"""
Unit tests for component roles (v0.5.0 feature).

Tests ComponentRole and role-based classification of components.
"""

import pytest

from dazzle.page.specs.actions import (
    ActionSpec,
    FetchEffect,
    PatchOp,
    PatchSpec,
    TransitionSpec,
)
from dazzle.page.specs.component import (
    ComponentCategory,
    ComponentRole,
    ComponentSpec,
    PropFieldSpec,
    PropsSchema,
)
from dazzle.page.specs.state import StateScope, StateSpec


class TestComponentRoleEnum:
    """Tests for ComponentRole enum values."""

    def test_presentational_value(self):
        """Test presentational role value."""
        assert ComponentRole.PRESENTATIONAL == "presentational"

    def test_container_value(self):
        """Test container role value."""
        assert ComponentRole.CONTAINER == "container"


class TestExplicitRoles:
    """Tests for explicitly set component roles."""

    def test_explicit_presentational(self):
        """Test component explicitly marked as presentational."""
        comp = ComponentSpec(
            name="Button",
            role=ComponentRole.PRESENTATIONAL,
            props_schema=PropsSchema(
                fields=[
                    PropFieldSpec(name="label", type="str", required=True),
                    PropFieldSpec(name="onClick", type="Action"),
                ]
            ),
        )
        assert comp.is_presentational is True
        assert comp.is_container is False
        assert comp.role == ComponentRole.PRESENTATIONAL

    def test_explicit_container(self):
        """Test component explicitly marked as container."""
        comp = ComponentSpec(
            name="DataLoader",
            role=ComponentRole.CONTAINER,
        )
        assert comp.is_presentational is False
        assert comp.is_container is True
        assert comp.role == ComponentRole.CONTAINER

    def test_explicit_role_overrides_inference(self):
        """Test that explicit role overrides automatic inference."""
        # This component has state, so would normally be inferred as container
        # But we explicitly mark it as presentational
        comp = ComponentSpec(
            name="ControlledInput",
            role=ComponentRole.PRESENTATIONAL,
            state=[StateSpec(name="value", scope=StateScope.LOCAL, initial="")],
        )
        assert comp.is_presentational is True
        assert comp.is_container is False


class TestInferredRoles:
    """Tests for automatic role inference when role is None."""

    @pytest.mark.parametrize(
        "scenario,is_presentational",
        [
            ("no_state_no_effects", True),
            ("pure_actions_only", True),
            ("has_state", False),
            ("has_impure_action", False),
        ],
        ids=[
            "test_inferred_presentational_no_state_no_effects",
            "test_inferred_presentational_pure_actions_only",
            "test_inferred_container_has_state",
            "test_inferred_container_has_impure_action",
        ],
    )
    def test_role_inference(self, scenario: str, is_presentational: bool):
        if scenario == "no_state_no_effects":
            comp = ComponentSpec(
                name="Icon",
                props_schema=PropsSchema(
                    fields=[PropFieldSpec(name="name", type="str", required=True)]
                ),
            )
        elif scenario == "pure_actions_only":
            comp = ComponentSpec(
                name="Toggle",
                state=[],
                actions=[
                    ActionSpec(
                        name="toggle",
                        transitions=[
                            TransitionSpec(
                                target_state="isOn",
                                update=PatchSpec(op=PatchOp.SET, path="isOn", value=True),
                            )
                        ],
                        effect=None,
                    )
                ],
            )
        elif scenario == "has_state":
            comp = ComponentSpec(
                name="Counter",
                state=[StateSpec(name="count", scope=StateScope.LOCAL, initial=0)],
            )
        else:  # has_impure_action
            comp = ComponentSpec(
                name="DataFetcher",
                actions=[
                    ActionSpec(
                        name="loadData",
                        effect=FetchEffect(backend_service="list_data"),
                    )
                ],
            )
        assert comp.role is None
        assert comp.is_presentational is is_presentational
        assert comp.is_container is (not is_presentational)

    def test_inferred_container_mixed_actions(self):
        """Test container inference with both pure and impure actions."""
        comp = ComponentSpec(
            name="Form",
            actions=[
                # Pure action
                ActionSpec(
                    name="setField",
                    transitions=[
                        TransitionSpec(
                            target_state="value",
                            update=PatchSpec(op=PatchOp.SET, path="value", value=None),
                        )
                    ],
                ),
                # Impure action
                ActionSpec(
                    name="submit",
                    effect=FetchEffect(backend_service="submit_form"),
                ),
            ],
        )
        # Has at least one impure action -> container
        assert comp.is_container is True


class TestRoleWithCategories:
    """Tests for role and category interaction."""

    def test_primitive_with_presentational_role(self):
        """Test primitive component can be presentational."""
        comp = ComponentSpec(
            name="Card",
            category=ComponentCategory.PRIMITIVE,
            role=ComponentRole.PRESENTATIONAL,
        )
        assert comp.is_primitive is True
        assert comp.is_presentational is True

    def test_pattern_with_container_role(self):
        """Test pattern component can be container."""
        comp = ComponentSpec(
            name="DataTable",
            category=ComponentCategory.PATTERN,
            role=ComponentRole.CONTAINER,
        )
        assert comp.is_pattern is True
        assert comp.is_container is True

    def test_custom_component_role_inference(self):
        """Test custom component with inferred role."""
        comp = ComponentSpec(
            name="UserCard",
            category=ComponentCategory.CUSTOM,
            # No explicit role, will be inferred
        )
        # No state or effects -> presentational
        assert comp.is_custom is True
        assert comp.is_presentational is True
